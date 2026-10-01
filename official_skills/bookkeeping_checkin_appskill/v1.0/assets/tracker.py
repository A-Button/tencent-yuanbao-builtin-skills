#!/usr/bin/env python3
"""记账台账的持久层（SQLite）：成员档案 + 流水。

与跑团打卡那个 tracker 的关键区别：本模块**同时被 import 和当 CLI 用**。
跑团那边 tracker.py 是先于 App 存在的独立 CLI，ledger_api 只能 subprocess 调它，
于是要处理 flock、env 传递、key=value 回读解析三层麻烦。这里 ledger_api 直接
import，少三层出错面；CLI 只留给模型做成员管理。

**职责边界（重要）**：
  成员管理（建档/改名/加别名/查询）→ 模型走本文件的 CLI，输出 key=value（与跑团同款）
  流水只读查询（list_txns/summary/query）→ 模型可用，排查与统计
  流水写入（add_txn/correct/delete_txn）→ **是 ledger_api 的内部实现，不给模型调用**。
      命令留在 CLI 里是为了人工排查与补录；模型落库只能走「卡片确认后的 commit_txn」，
      这条约束由 SKILL.md 明文管住（与跑团同一处理方式）。

「台账 == db」：txn 只存 member_id，展示用的归属人姓名一律 JOIN member 实时取。
成员改名后历史流水的展示名跟着变，不需要回填。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.request import pathname2url

ASSETS_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(ASSETS_DIR)
SCHEMA_PATH = os.path.join(ASSETS_DIR, "schema.sql")

if ASSETS_DIR not in sys.path:
    sys.path.insert(0, ASSETS_DIR)
import persist_paths  # noqa: E402

PERSIST_DIR, DB_PATH = persist_paths.resolve_db_path(SKILL_ROOT)

_TZ = timezone(timedelta(hours=8))

# 落库时兜底的合法取值。真正的归一在 scripts/vocab.py，这里只是最后一道防线：
# 万一有人绕过 ledger_api 直接调本模块，也不能把非法枚举写进库。
_TYPES = ("income", "expense")
_ACCOUNTS = ("wechat", "alipay", "bank_card", "cash", "credit_card", "other")
_CURRENCIES = (
    "人民币", "美元", "欧元", "日元", "英镑", "港元", "澳元", "加元", "瑞士法郎", "新加坡元",
)
_CURRENCY_ALIASES = {
    "CNY": "人民币", "RMB": "人民币", "人民币": "人民币",
    "USD": "美元", "美元": "美元", "美金": "美元",
    "EUR": "欧元", "欧元": "欧元",
    "JPY": "日元", "日元": "日元",
    "GBP": "英镑", "英镑": "英镑",
    "HKD": "港元", "港元": "港元", "港币": "港元",
    "AUD": "澳元", "澳元": "澳元", "澳币": "澳元",
    "CAD": "加元", "加元": "加元", "加币": "加元",
    "CHF": "瑞士法郎", "瑞士法郎": "瑞士法郎",
    "SGD": "新加坡元", "新加坡元": "新加坡元", "新元": "新加坡元",
}
# 流水行状态：新写入一律 confirmed。expired 仅兼容旧库已落盘的超时结算行。
_TXN_STATUSES = ("confirmed", "expired")
_MEMBER_STATUSES = ("active", "exited")

# 别名分隔符：模型可能用中文分号/逗号，统一切开后用 ; 存。
_ALIAS_SPLIT = re.compile(r"[；;，,、]+")

# 群聊链路里的请求级匿名 id（user_1 / user_2），每轮会变，绝不能当成员主键。
_ANON_USER_RE = re.compile(r"^user_\d+$")


def is_anon_user_id(value: str) -> bool:
    """消息 extra 里的 user_N 是请求级匿名 id，不能当成员主键。"""
    return bool(_ANON_USER_RE.fullmatch(str(value or "").strip()))


def _next_member_id(conn: sqlite3.Connection) -> str:
    """分配下一个数字 id（'1' / '2' / …）。旧的拼音、user_N 不参与序号。"""
    max_n = 0
    for row in conn.execute("SELECT id FROM member").fetchall():
        s = str(row["id"] or "").strip()
        if s.isdigit():
            max_n = max(max_n, int(s))
    return str(max_n + 1)


class TrackerError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def now_iso() -> str:
    return datetime.now(_TZ).isoformat(timespec="seconds")


def today_str() -> str:
    return datetime.now(_TZ).strftime("%Y-%m-%d")


def connect() -> sqlite3.Connection:
    """建库并保证 schema 就绪。

    nolock=1 + journal_mode=MEMORY 与跑团那边一致：沙箱的持久化目录在部分环境下
    不支持 POSIX 文件锁，默认模式会直接 "database is locked"。
    """
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    open(DB_PATH, "a").close()
    uri = "file:" + pathname2url(DB_PATH) + "?nolock=1"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = MEMORY")
    conn.execute("PRAGMA synchronous = OFF")
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


# ---------------------------------------------------------------------------
# 成员档案
# ---------------------------------------------------------------------------

def _norm_aliases(text: str) -> list[str]:
    return [a.strip() for a in _ALIAS_SPLIT.split(str(text or "")) if a.strip()]


def _norm_currency(text: str) -> str:
    """ISO 码 / 中文名 -> 词表中文名。空则默认人民币；表外币种原样保留。"""
    raw = str(text or "").strip()
    if not raw:
        return "人民币"
    if raw in _CURRENCIES:
        return raw
    hit = _CURRENCY_ALIASES.get(raw) or _CURRENCY_ALIASES.get(raw.upper())
    if hit:
        return hit
    return raw


def add_member(conn: sqlite3.Connection, name: str, *,
               at_name: str = "", alias: str = "", sort_order: int = 0,
               status: str = "active", description: str = "") -> dict[str, Any]:
    """建档：id 由库内自增，调用方只传姓名。禁止传入 user_N / 自拟拼音 id。"""
    name = str(name or "").strip()
    if not name:
        raise TrackerError("INVALID_ARGUMENT", "name 必填")
    if is_anon_user_id(name):
        raise TrackerError(
            "INVALID_ARGUMENT",
            "不要把 user_N 当姓名建档，请传群昵称（如「用户zhou」）")
    if status not in _MEMBER_STATUSES:
        raise TrackerError("INVALID_ARGUMENT", f"status 非法：{status}")
    for _ in range(8):
        member_id = _next_member_id(conn)
        try:
            conn.execute(
                "INSERT INTO member (id, name, at_name, alias, sort_order, status, "
                "description, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (member_id, name, str(at_name or "").strip(),
                 ";".join(_norm_aliases(alias)), int(sort_order or 0), status,
                 str(description or "").strip(), now_iso()))
            conn.commit()
            return get_member(conn, member_id) or {}
        except sqlite3.IntegrityError:
            continue
    raise TrackerError("MEMBER_EXISTS", "分配成员 id 失败，请重试")


def update_member(conn: sqlite3.Connection, query: str,
                  fields: dict[str, Any]) -> dict[str, Any]:
    """只改提供的字段。alias 传入即【整体覆盖】（传空串清空），只想追加用 add_alias。"""
    member = resolve_member(conn, query)
    allowed = ("name", "at_name", "alias", "sort_order", "status", "description")
    sets, params = [], []
    for key in allowed:
        if key not in fields:
            continue
        value = fields[key]
        if key == "status" and value not in _MEMBER_STATUSES:
            raise TrackerError("INVALID_ARGUMENT", f"status 非法：{value}")
        if key == "alias":
            value = ";".join(_norm_aliases(value))
        if key == "sort_order":
            value = int(value or 0)
        sets.append(f"{key}=?")
        params.append(value)
    if not sets:
        return member
    params.append(member["id"])
    conn.execute(f"UPDATE member SET {', '.join(sets)} WHERE id=?", params)
    conn.commit()
    return get_member(conn, member["id"]) or {}


def add_alias(conn: sqlite3.Connection, query: str, alias: str) -> dict[str, Any]:
    """给已建档成员【追加】别名（去重，不覆盖已有）。"""
    member = resolve_member(conn, query)
    existing = _norm_aliases(member.get("alias", ""))
    for a in _norm_aliases(alias):
        if a not in existing:
            existing.append(a)
    conn.execute("UPDATE member SET alias=? WHERE id=?",
                 (";".join(existing), member["id"]))
    conn.commit()
    return get_member(conn, member["id"]) or {}


def get_member(conn: sqlite3.Connection, member_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM member WHERE id=?", (member_id,)).fetchone()
    return _row_to_dict(row) if row else None


def find_member(conn: sqlite3.Connection, query: str) -> dict[str, Any] | None:
    """按 name/at_name（精确）→ alias（模糊）匹配；命中多人取 sort_order 最小者。

    不按档案 id 查：模型拿不到稳定 id（会话里的 user_N 每轮会变，自增 id 也不下发）。
    """
    q = str(query or "").strip()
    if not q:
        return None
    if is_anon_user_id(q):
        raise TrackerError(
            "USE_SENDER_NAME",
            "find_member 请传 sender_name（群昵称，如「用户zhou」），"
            "不要传 sender_id / user_N（那是本轮匿名号，每轮会变）")
    row = conn.execute(
        "SELECT * FROM member WHERE name=? OR (at_name!='' AND at_name=?) "
        "ORDER BY sort_order LIMIT 1", (q, q)).fetchone()
    if row:
        return _row_to_dict(row)
    row = conn.execute(
        "SELECT * FROM member WHERE alias!='' AND alias LIKE ? "
        "ORDER BY sort_order LIMIT 1", (f"%{q}%",)).fetchone()
    return _row_to_dict(row) if row else None


def resolve_member(conn: sqlite3.Connection, query: str) -> dict[str, Any]:
    """find_member 的强制版：查不到直接报错（绝不擅自建档）。"""
    member = find_member(conn, query)
    if not member:
        raise TrackerError("MEMBER_NOT_FOUND",
                           f"成员未找到：{query}（请先在群里确认并建档）")
    return member


def list_members(conn: sqlite3.Connection, *, include_exited: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT * FROM member"
    if not include_exited:
        sql += " WHERE status='active'"
    sql += " ORDER BY sort_order, name"
    return [_row_to_dict(r) for r in conn.execute(sql).fetchall()]


# ---------------------------------------------------------------------------
# 流水
# ---------------------------------------------------------------------------

def _next_seq(conn: sqlite3.Connection, member_id: str, occurred_at: str) -> int:
    """同一人同一天的第几笔。软删的也占号，避免删了再记撞主键。"""
    prefix = f"{member_id}_{occurred_at}_"
    rows = conn.execute(
        "SELECT txn_id FROM txn WHERE txn_id LIKE ?", (prefix + "%",)).fetchall()
    used = []
    for r in rows:
        tail = str(r["txn_id"])[len(prefix):]
        if tail.isdigit():
            used.append(int(tail))
    return (max(used) + 1) if used else 1


def add_txn(conn: sqlite3.Connection, *, member_id: str, occurred_at: str,
            transaction_type: str, amount: float, currency: str = "人民币",
            category: str = "other", account: str = "other",
            merchant_name: str = "", note: str = "", group_id: str = "default",
            card_id: str = "", status: str = "confirmed") -> dict[str, Any]:
    """落一条流水。返回完整行（含生成的 txn_id 与 JOIN 出的 member_name）。

    member_id 必须已建档——外键与这里的显式校验双保险，绝不为记账自动建档。
    幂等：同一个非空 card_id 重复落库会撞唯一索引，抛 DUPLICATE_TXN，
    由 ledger_api 转成"这张卡已经录过了"的回执，而不是记成两笔。
    """
    member = get_member(conn, str(member_id or "").strip())
    if not member:
        raise TrackerError("MEMBER_NOT_FOUND",
                           f"成员未建档：{member_id}（记账前必须先建档）")
    if transaction_type not in _TYPES:
        raise TrackerError("INVALID_ARGUMENT",
                           f"transaction_type 非法：{transaction_type}")
    if account not in _ACCOUNTS:
        raise TrackerError("INVALID_ARGUMENT", f"account 非法：{account}")
    if status not in _TXN_STATUSES:
        raise TrackerError("INVALID_ARGUMENT", f"status 非法：{status}")
    try:
        amount_val = round(float(amount), 2)
    except (TypeError, ValueError):
        raise TrackerError("INVALID_ARGUMENT", f"amount 必须是数字：{amount!r}") from None
    if amount_val <= 0:
        raise TrackerError("INVALID_ARGUMENT", "amount 必须为正数")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(occurred_at or "")):
        raise TrackerError("INVALID_ARGUMENT", f"occurred_at 必须是 YYYY-MM-DD：{occurred_at!r}")

    seq = _next_seq(conn, member["id"], occurred_at)
    txn_id = f"{member['id']}_{occurred_at}_{seq:02d}"
    try:
        conn.execute(
            "INSERT INTO txn (txn_id, group_id, card_id, member_id, occurred_at, "
            "transaction_type, amount, currency, category, account, merchant_name, "
            "note, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (txn_id, group_id or "default", card_id or "", member["id"], occurred_at,
             transaction_type, amount_val, _norm_currency(currency),
             category or "other", account or "other", merchant_name or "",
             note or "", status, now_iso()))
        conn.commit()
    except sqlite3.IntegrityError as exc:
        if "idx_txn_card" in str(exc) or "card_id" in str(exc):
            existing = find_by_card(conn, card_id)
            raise TrackerError(
                "DUPLICATE_TXN",
                f"该卡片已录入过流水：card_id={card_id}"
                + (f" txn_id={existing['txn_id']}" if existing else "")) from None
        raise TrackerError("DB_ERROR", str(exc)) from None
    return get_txn(conn, txn_id) or {}


_TXN_SELECT = (
    "SELECT t.*, COALESCE(m.name, t.member_id) AS member_name, "
    "COALESCE(m.at_name,'') AS member_at_name "
    "FROM txn t LEFT JOIN member m ON m.id = t.member_id"
)


def get_txn(conn: sqlite3.Connection, txn_id: str) -> dict[str, Any] | None:
    row = conn.execute(_TXN_SELECT + " WHERE t.txn_id=?", (txn_id,)).fetchone()
    return _row_to_dict(row) if row else None


def find_by_card(conn: sqlite3.Connection, card_id: str) -> dict[str, Any] | None:
    if not card_id:
        return None
    row = conn.execute(
        _TXN_SELECT + " WHERE t.card_id=? AND t.deleted_at IS NULL LIMIT 1",
        (card_id,)).fetchone()
    return _row_to_dict(row) if row else None


def list_txns(conn: sqlite3.Connection, *, member_id: str = "", date: str = "",
              month: str = "", transaction_type: str = "", group_id: str = "",
              limit: int = 50) -> list[dict[str, Any]]:
    """按条件查已落库流水（不含软删）。member_id 精确匹配（调用方先 resolve）。"""
    sql = _TXN_SELECT + " WHERE t.deleted_at IS NULL"
    params: list[Any] = []
    if member_id:
        sql += " AND t.member_id=?"
        params.append(member_id)
    if date:
        sql += " AND t.occurred_at=?"
        params.append(date)
    if month:
        sql += " AND t.occurred_at LIKE ?"
        params.append(f"{month}%")
    if transaction_type:
        sql += " AND t.transaction_type=?"
        params.append(transaction_type)
    if group_id:
        sql += " AND t.group_id=?"
        params.append(group_id)
    sql += " ORDER BY t.occurred_at DESC, t.created_at DESC LIMIT ?"
    params.append(max(1, int(limit)))
    return [_row_to_dict(r) for r in conn.execute(sql, params).fetchall()]


def update_txn(conn: sqlite3.Connection, txn_id: str,
               fields: dict[str, Any]) -> dict[str, Any]:
    """整体更正一条已落库流水（编辑模式）。txn_id 不变，不新增行。"""
    existing = get_txn(conn, txn_id)
    if not existing or existing.get("deleted_at"):
        raise TrackerError("TXN_NOT_FOUND", f"未找到要修改的流水：txn_id={txn_id}")
    allowed = ("member_id", "occurred_at", "transaction_type", "amount", "currency",
               "category", "account", "merchant_name", "note")
    sets, params = [], []
    for key in allowed:
        if key not in fields:
            continue
        value = fields[key]
        if key == "amount":
            value = round(float(value), 2)
            if value <= 0:
                raise TrackerError("INVALID_ARGUMENT", "amount 必须为正数")
        if key == "transaction_type" and value not in _TYPES:
            raise TrackerError("INVALID_ARGUMENT", f"transaction_type 非法：{value}")
        if key == "account" and value not in _ACCOUNTS:
            raise TrackerError("INVALID_ARGUMENT", f"account 非法：{value}")
        if key == "currency":
            value = _norm_currency(value)
        if key == "member_id" and not get_member(conn, value):
            raise TrackerError("MEMBER_NOT_FOUND", f"成员未建档：{value}")
        sets.append(f"{key}=?")
        params.append(value)
    if not sets:
        return existing
    sets.append("updated_at=?")
    params.append(now_iso())
    params.append(txn_id)
    conn.execute(f"UPDATE txn SET {', '.join(sets)} WHERE txn_id=?", params)
    conn.commit()
    return get_txn(conn, txn_id) or {}


# 通用改单字段（与跑团 tracker 的 correct 同形）：table -> 主键列。
# 只放这两张业务表，避免拿它去改索引或 sqlite 内部表。
_CORRECTABLE = {"txn": "txn_id", "member": "id"}

# 允许 correct 改的列白名单。主键、created_at、以及软删标记不在内——
# 删除走 delete_txn 才有 deleted_reason 留痕，绕 correct 改 deleted_at 等于无痕删除。
_CORRECTABLE_FIELDS = {
    "txn": ("group_id", "card_id", "member_id", "occurred_at", "transaction_type",
            "amount", "currency", "category", "account", "merchant_name", "note",
            "status"),
    "member": ("name", "at_name", "alias", "sort_order", "status", "description"),
}


def correct(conn: sqlite3.Connection, table: str, pk: str, field: str,
            value: Any, reason: str = "") -> dict[str, Any]:
    """人工排查用的单字段更正。reason 仅回显在输出里做操作记录，不入库
    （与跑团一致：库里没有审计表；txn 会顺带刷新 updated_at）。"""
    pk_col = _CORRECTABLE.get(table)
    if not pk_col:
        raise TrackerError("INVALID_ARGUMENT",
                           f"不可更正的表：{table}（可选 {'/'.join(_CORRECTABLE)}）")
    if field not in _CORRECTABLE_FIELDS[table]:
        raise TrackerError(
            "INVALID_ARGUMENT",
            f"{table} 不允许更正字段 {field}（可选 {', '.join(_CORRECTABLE_FIELDS[table])}）")
    row = conn.execute(f"SELECT {field} FROM {table} WHERE {pk_col}=?", (pk,)).fetchone()
    if row is None:
        raise TrackerError("ROW_NOT_FOUND", f"未找到记录：{pk_col}={pk}")
    before = row[0]
    if table == "txn":
        # 复用 update_txn 的校验（枚举合法性、金额正数、member_id 已建档）
        update_txn(conn, pk, {field: value})
    else:
        update_member(conn, pk, {field: value})
    after = conn.execute(
        f"SELECT {field} FROM {table} WHERE {pk_col}=?", (pk,)).fetchone()[0]
    return {"table": table, "pk": pk, "field": field, "before": before,
            "after": after, "reason": reason or "(未填)"}


def delete_txn(conn: sqlite3.Connection, txn_id: str, reason: str = "") -> dict[str, Any]:
    """软删一条已落库流水。"""
    existing = get_txn(conn, txn_id)
    if not existing or existing.get("deleted_at"):
        raise TrackerError("TXN_NOT_FOUND", f"未找到要删除的流水：txn_id={txn_id}")
    conn.execute("UPDATE txn SET deleted_at=?, deleted_reason=? WHERE txn_id=?",
                 (now_iso(), reason or "用户要求删除", txn_id))
    conn.commit()
    return get_txn(conn, txn_id) or {}


def summary(conn: sqlite3.Connection, *, member_id: str = "", month: str = "",
            group_id: str = "") -> dict[str, Any]:
    """某人某月的收支合计。落库回执里带上，让元宝能顺口反馈"这个月花了多少"。"""
    sql = ("SELECT transaction_type, COUNT(*) AS n, COALESCE(SUM(amount),0) AS total "
           "FROM txn WHERE deleted_at IS NULL")
    params: list[Any] = []
    if member_id:
        sql += " AND member_id=?"
        params.append(member_id)
    if month:
        sql += " AND occurred_at LIKE ?"
        params.append(f"{month}%")
    if group_id:
        sql += " AND group_id=?"
        params.append(group_id)
    sql += " GROUP BY transaction_type"
    out: dict[str, Any] = {
        "member_id": member_id, "month": month,
        "income_total": 0.0, "income_count": 0,
        "expense_total": 0.0, "expense_count": 0,
    }
    for r in conn.execute(sql, params).fetchall():
        if r["transaction_type"] == "income":
            out["income_total"] = round(float(r["total"]), 2)
            out["income_count"] = int(r["n"])
        elif r["transaction_type"] == "expense":
            out["expense_total"] = round(float(r["total"]), 2)
            out["expense_count"] = int(r["n"])
    out["net"] = round(out["income_total"] - out["expense_total"], 2)
    return out


# ---------------------------------------------------------------------------
# CLI
#
# 与跑团 tracker 同一套定位：成员管理 + 只读查询给模型用，写流水的
# add_txn / correct / delete_txn 是 ledger_api 的内部实现、留给人工排查与补录，
# 模型不得调用（SKILL.md 明文管住）。
#
# 输出格式：结构固定的单行结果打 key=value（与跑团一致，便于回读）；
# list_txns / query 打 JSON——因为备注/商户里可能有空格，key=value 会被截断。
# ---------------------------------------------------------------------------

def _member_line(m: dict[str, Any]) -> str:
    return (f"id={m['id']} name={m['name']} at_name={m.get('at_name','')} "
            f"alias={m.get('alias','')} status={m.get('status','')} "
            f"sort={m.get('sort_order',0)}")


def main() -> int:
    parser = argparse.ArgumentParser(prog="tracker.py", add_help=True)
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("add_member")
    p.add_argument("tokens", nargs="+", metavar="name",
                   help="姓名；旧写法 add_member <id> <姓名> 仍能跑，但 id 会被丢掉")
    p.add_argument("--at-name", default="")
    p.add_argument("--alias", default="")
    p.add_argument("--sort", type=int, default=0)
    p.add_argument("--status", default="active")
    p.add_argument("--description", default="")

    p = sub.add_parser("update_member")
    p.add_argument("query")
    p.add_argument("--name")
    p.add_argument("--at-name")
    p.add_argument("--alias")
    p.add_argument("--sort", type=int)
    p.add_argument("--status")
    p.add_argument("--description")

    p = sub.add_parser("add_alias")
    p.add_argument("query")
    p.add_argument("alias")

    p = sub.add_parser("find_member")
    p.add_argument(
        "query",
        help="对象姓名 / @名 / 别名。「我的」用 extra 群昵称，替别人记用对方名字。不要传 sender_id / user_N",
    )

    p = sub.add_parser("list_members")
    p.add_argument("--include-exited", action="store_true")

    p = sub.add_parser("list_txns")
    p.add_argument("--member", default="")
    p.add_argument("--date", default="")
    p.add_argument("--month", default="")
    p.add_argument("--type", dest="transaction_type", default="")
    p.add_argument("--limit", type=int, default=50)

    p = sub.add_parser("summary")
    p.add_argument("--member", default="")
    p.add_argument("--month", default="")

    p = sub.add_parser("query")
    p.add_argument("--sql", required=True)

    # 以下三个是写口：ledger_api 的内部实现，人工排查/补录用，模型不要调用。
    p = sub.add_parser("add_txn")
    p.add_argument("owner")
    p.add_argument("--date", required=True)
    p.add_argument("--type", dest="transaction_type", required=True)
    p.add_argument("--amount", type=float, required=True)
    p.add_argument("--currency", default="人民币")
    p.add_argument("--category", default="other")
    p.add_argument("--account", default="other")
    p.add_argument("--merchant", default="")
    p.add_argument("--note", default="")
    p.add_argument("--group", default="default")
    p.add_argument("--card-id", dest="card_id", default="")
    p.add_argument("--status", default="confirmed")

    p = sub.add_parser("correct")
    p.add_argument("table", choices=sorted(_CORRECTABLE))
    p.add_argument("pk")
    p.add_argument("field")
    p.add_argument("value")
    p.add_argument("--reason", default="")

    p = sub.add_parser("delete_txn")
    p.add_argument("txn_id")
    p.add_argument("--reason", default="")

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        return 2

    conn = connect()
    try:
        if args.cmd == "add_member":
            if len(args.tokens) == 1:
                name = args.tokens[0]
            elif len(args.tokens) == 2:
                # 兼容旧签名 add_member <自填id> <姓名>：丢掉 id，只取姓名。
                name = args.tokens[1]
            else:
                raise TrackerError(
                    "INVALID_ARGUMENT",
                    "add_member 只需要姓名，不要自己填 id")
            m = add_member(conn, name, at_name=args.at_name,
                           alias=args.alias, sort_order=args.sort,
                           status=args.status, description=args.description)
            print(_member_line(m))
        elif args.cmd == "update_member":
            fields = {}
            for key, val in (("name", args.name), ("at_name", args.at_name),
                             ("alias", args.alias), ("sort_order", args.sort),
                             ("status", args.status), ("description", args.description)):
                if val is not None:
                    fields[key] = val
            print(_member_line(update_member(conn, args.query, fields)))
        elif args.cmd == "add_alias":
            print(_member_line(add_alias(conn, args.query, args.alias)))
        elif args.cmd == "find_member":
            m = find_member(conn, args.query)
            print(_member_line(m) if m else f"error=member_not_found query={args.query}")
            if not m:
                return 1
        elif args.cmd == "list_members":
            rows = list_members(conn, include_exited=args.include_exited)
            for m in rows:
                print(_member_line(m))
            print(f"count={len(rows)}")
        elif args.cmd == "list_txns":
            member_id = ""
            if args.member:
                found = find_member(conn, args.member)
                if not found:
                    print(f"error=member_not_found query={args.member}")
                    return 1
                member_id = found["id"]
            rows = list_txns(conn, member_id=member_id, date=args.date,
                             month=args.month,
                             transaction_type=args.transaction_type,
                             limit=args.limit)
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        elif args.cmd == "summary":
            member_id = ""
            if args.member:
                found = find_member(conn, args.member)
                if not found:
                    print(f"error=member_not_found query={args.member}")
                    return 1
                member_id = found["id"]
            s = summary(conn, member_id=member_id, month=args.month)
            print(" ".join(f"{k}={v}" for k, v in s.items()))
        elif args.cmd == "query":
            sql = args.sql.strip()
            # 只读：不接受任何会改库的语句，避免用它绕开 delete_txn 的软删留痕。
            if not sql.lower().startswith("select"):
                print("error=readonly_only message=query --sql 只允许 SELECT")
                return 1
            rows = [_row_to_dict(r) for r in conn.execute(sql).fetchall()]
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        elif args.cmd == "add_txn":
            member = resolve_member(conn, args.owner)
            row = add_txn(conn, member_id=member["id"], occurred_at=args.date,
                          transaction_type=args.transaction_type,
                          amount=args.amount, currency=args.currency,
                          category=args.category, account=args.account,
                          merchant_name=args.merchant, note=args.note,
                          group_id=args.group, card_id=args.card_id,
                          status=args.status)
            print(f"txn_id={row['txn_id']} member={row['member_name']} "
                  f"occurred_at={row['occurred_at']} type={row['transaction_type']} "
                  f"amount={row['amount']} category={row['category']} "
                  f"account={row['account']} status={row['status']}")
        elif args.cmd == "correct":
            r = correct(conn, args.table, args.pk, args.field, args.value, args.reason)
            print(f"table={r['table']} pk={r['pk']} field={r['field']} "
                  f"before={r['before']} after={r['after']} reason={r['reason']}")
        elif args.cmd == "delete_txn":
            row = delete_txn(conn, args.txn_id, args.reason)
            print(f"txn_id={row['txn_id']} member={row['member_name']} "
                  f"deleted_at={row['deleted_at']} reason={row['deleted_reason']}")
    except TrackerError as exc:
        print(f"error={exc.code.lower()} message={exc.message}")
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
