#!/usr/bin/env python3
"""
ledger.py - 个人日常记账 CLI

稳定层：SQLite CRUD + 汇总/日报成文。
规则变更请改 rules.py，本文件不需要修改。

输出为 key=value 纯文本；错误以 error=... 开头并返回非零退出码。
日报正文在 report 命令的 stdout 中以多行文本输出（非 key=value）。
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from urllib.request import pathname2url

import rules

_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_DIR)
PERSIST_DIR = os.environ.get(
    "LEDGER_DATA_DIR",
    os.environ.get("TRACKER_DATA_DIR", os.path.join(_ROOT, "data", "user_persistent_data")),
)
DB_PATH = os.environ.get("LEDGER_DB", os.path.join(PERSIST_DIR, "ledger.db"))
AUDIT_PATH = os.path.join(os.path.dirname(DB_PATH), "ledger_audit_log.jsonl")
SCHEMA_PATH = os.path.join(_DIR, "schema.sql")
LOCK_DIR = os.environ.get("LEDGER_LOCK_DIR", os.environ.get("TRACKER_LOCK_DIR", "/tmp"))
LOCK_PATH = os.path.join(
    LOCK_DIR, "ledger-" + hashlib.md5(DB_PATH.encode("utf-8")).hexdigest() + ".lock")
LOCK_TIMEOUT = float(os.environ.get("LEDGER_LOCK_TIMEOUT", "60"))

_TZ = timezone(timedelta(hours=8))


def _connect():
    uri = "file:" + pathname2url(DB_PATH) + "?nolock=1"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA locking_mode = EXCLUSIVE")
    conn.execute("PRAGMA journal_mode = MEMORY")
    conn.execute("PRAGMA synchronous = OFF")
    return conn


@contextmanager
def _db_lock():
    try:
        os.makedirs(LOCK_DIR, exist_ok=True)
        fd = os.open(LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o644)
    except OSError as e:
        _die(f"db_lock_open_error path={LOCK_PATH} detail={e}", 6)
    try:
        deadline = time.monotonic() + LOCK_TIMEOUT
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() > deadline:
                    _die(f"db_lock_timeout path={LOCK_PATH} timeout={LOCK_TIMEOUT}s", 6)
                time.sleep(0.05)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _ensure_schema(conn):
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    # 旧库升级：补列
    cols = {r[1] for r in conn.execute("PRAGMA table_info(txn)").fetchall()}
    if "member_id" not in cols:
        conn.execute("ALTER TABLE txn ADD COLUMN member_id TEXT DEFAULT ''")
    if "recorded_by_id" not in cols:
        conn.execute("ALTER TABLE txn ADD COLUMN recorded_by_id TEXT DEFAULT ''")


def _split_aliases(s):
    if not s:
        return []
    return [p.strip() for p in re.split(r"[；;，,]", s) if p.strip()]


def _join_aliases(items):
    return "；".join(items)


def _like_escape(s):
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _resolve(conn, query):
    """查找成员：id / name / at_name 精确，再 alias 模糊。"""
    if not query:
        return None
    q = query.strip()
    if q.startswith("@"):
        q = q[1:]
    row = conn.execute("SELECT * FROM member WHERE id = ?", (q,)).fetchone()
    if row:
        return row
    row = conn.execute(
        "SELECT * FROM member WHERE name = ? OR at_name = ? OR at_name = ? "
        "ORDER BY sort_order, id LIMIT 1",
        (q, q, "@" + q),
    ).fetchone()
    if row:
        return row
    return conn.execute(
        "SELECT * FROM member WHERE alias <> '' AND alias LIKE ? ESCAPE '\\' "
        "ORDER BY sort_order, id LIMIT 1",
        (f"%{_like_escape(q)}%",),
    ).fetchone()


def _require_member(conn, query, label="member"):
    m = _resolve(conn, query)
    if not m:
        _die(f"member_not_found query={query} | 请先建档或改用会自动建档的 add")
    if m["status"] == "exited":
        _die(f"member_exited id={m['id']} name={m['name']}")
    return m


def _next_user_id(conn) -> str:
    """自动建档 id，对齐跑团风格：user_1 / user_2 / …（与展示名解耦）。"""
    rows = conn.execute(
        "SELECT id FROM member WHERE id GLOB 'user_[0-9]*'"
    ).fetchall()
    max_n = 0
    for r in rows:
        mid = r["id"] or ""
        suffix = mid[5:]  # after "user_"
        if suffix.isdigit():
            max_n = max(max_n, int(suffix))
    return f"user_{max_n + 1}"


def _ensure_member(conn, query, *, at_name="", is_admin=0):
    """按昵称/别名解析；不存在则自动建档（id=user_N，name=展示名）。"""
    q = (query or "").strip()
    if not q:
        _die("member_required | 需要成员昵称（sender_nickname 或话里点名的人）")
    at = ""
    name = q
    if q.startswith("@"):
        at = q
        name = q[1:].strip() or q
    m = _resolve(conn, q) or _resolve(conn, name)
    if m:
        if m["status"] == "exited":
            # 重新入账：自动恢复 active
            conn.execute("UPDATE member SET status='active' WHERE id=?", (m["id"],))
            m = conn.execute("SELECT * FROM member WHERE id=?", (m["id"],)).fetchone()
        return m, False
    mid = _next_user_id(conn)
    conn.execute(
        "INSERT INTO member (id, name, at_name, alias, sort_order, status, "
        "is_admin, description, created_at) VALUES (?,?,?,?,0,'active',?,?,?)",
        (mid, name, at_name or at, "", int(is_admin or 0), "auto", _now()),
    )
    _audit("add_member_auto", mid, name=name)
    m = conn.execute("SELECT * FROM member WHERE id=?", (mid,)).fetchone()
    return m, True


def _print_member(m):
    _print_kv(
        id=m["id"], name=m["name"], at_name=m["at_name"] or None,
        alias=m["alias"] or None, sort=m["sort_order"],
        status=m["status"], is_admin=int(m["is_admin"] or 0),
        description=m["description"] or None,
    )


@contextmanager
def _db():
    with _db_lock():
        conn = _connect()
        try:
            _ensure_schema(conn)
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _now() -> str:
    return datetime.now(_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _die(msg, code=2):
    print(f"error={msg}", file=sys.stderr)
    sys.exit(code)


def _audit(command, target, **extra):
    os.makedirs(os.path.dirname(AUDIT_PATH) or ".", exist_ok=True)
    row = {"ts": _now(), "command": command, "target": target, **extra}
    with open(AUDIT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _date_part(value: str) -> str:
    return (value or "")[:10]


def _print_kv(**kwargs):
    parts = []
    for k, v in kwargs.items():
        if v is None:
            continue
        if isinstance(v, float):
            parts.append(f"{k}={rules.money(v)}")
        else:
            parts.append(f"{k}={v}")
    print(" ".join(parts))


def _next_txn_id(conn, occurred_at: str) -> str:
    day = _date_part(occurred_at)
    prefix = day + "_"
    cur = conn.execute(
        "SELECT txn_id FROM txn WHERE txn_id LIKE ? ORDER BY txn_id DESC LIMIT 1",
        (prefix + "%",),
    ).fetchone()
    if not cur:
        return f"{day}_01"
    try:
        n = int(cur["txn_id"].split("_")[-1])
    except ValueError:
        n = 0
    return f"{day}_{n + 1:02d}"


def _parse_asof(value: str | None) -> datetime:
    if not value:
        return rules.now_bj()
    return rules.parse_dt(value)


def _active_filter(sql_alias=""):
    col = f"{sql_alias}.deleted_at" if sql_alias else "deleted_at"
    return f"({col} IS NULL OR {col}='')"


def _fetch_txns(conn, date_from=None, date_to=None, category=None,
                recorded_for=None, member_id=None, include_deleted=False):
    clauses = []
    params = []
    if not include_deleted:
        clauses.append(_active_filter())
    if date_from:
        clauses.append("substr(occurred_at,1,10) >= ?")
        params.append(_date_part(date_from))
    if date_to:
        clauses.append("substr(occurred_at,1,10) <= ?")
        params.append(_date_part(date_to))
    if category:
        clauses.append("category = ?")
        params.append(rules.normalize_category(category))
    if member_id:
        clauses.append("member_id = ?")
        params.append(member_id)
    elif recorded_for:
        # 兼容旧数据：按展示名；若能解析成员则优先 member_id
        m = _resolve(conn, recorded_for)
        if m:
            clauses.append("(member_id = ? OR recorded_for = ? OR recorded_for = ?)")
            params.extend([m["id"], m["name"], recorded_for])
        else:
            clauses.append("recorded_for = ?")
            params.append(recorded_for)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return conn.execute(
        f"SELECT * FROM txn{where} ORDER BY occurred_at, txn_id", params
    ).fetchall()


def _txn_member_label(r) -> str:
    return (r["recorded_for"] or "").strip() or (r["member_id"] or "").strip() or "未署名"


def _actor_can_edit(conn, actor_query, txn_row):
    """本人可改自己的；管理员可改任何人。actor 空则放行（兼容旧调用，SKILL 要求必传）。"""
    if not actor_query:
        return True
    actor = _resolve(conn, actor_query)
    if not actor:
        _die(f"actor_not_found query={actor_query}")
    if int(actor["is_admin"] or 0) == 1:
        return True
    owner = (txn_row["member_id"] or "").strip()
    if owner and owner == actor["id"]:
        return True
    # 旧数据无 member_id：按展示名比对
    if not owner and (txn_row["recorded_for"] or "") in (actor["name"], actor["id"], actor_query):
        return True
    _die(f"forbidden_not_owner_or_admin actor={actor['id']} txn={txn_row['txn_id']}")


def cmd_add_member(args):
    status = args.status or "active"
    if status not in ("active", "exited"):
        _die("invalid_status")
    with _db() as conn:
        alias = _join_aliases(_split_aliases(args.alias)) if args.alias else ""
        try:
            conn.execute(
                "INSERT INTO member (id, name, at_name, alias, sort_order, status, "
                "is_admin, description, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (args.id, args.name, args.at_name or "", alias, int(args.sort or 0),
                 status, int(args.is_admin or 0), args.description or "", _now()),
            )
        except sqlite3.IntegrityError:
            _die(f"member_exists id={args.id}")
        _audit("add_member", args.id)
        _print_member(conn.execute("SELECT * FROM member WHERE id=?", (args.id,)).fetchone())


def cmd_update_member(args):
    with _db() as conn:
        m = _require_member(conn, args.query)
        fields = {}
        if args.name is not None:
            fields["name"] = args.name
        if args.at_name is not None:
            fields["at_name"] = args.at_name
        if args.alias is not None:
            fields["alias"] = _join_aliases(_split_aliases(args.alias))
        if args.sort is not None:
            fields["sort_order"] = int(args.sort)
        if args.status is not None:
            if args.status not in ("active", "exited"):
                _die("invalid_status")
            fields["status"] = args.status
        if args.is_admin is not None:
            fields["is_admin"] = int(args.is_admin)
        if args.description is not None:
            fields["description"] = args.description
        if not fields:
            _die("nothing_to_update")
        clause = ", ".join(f"{k}=?" for k in fields)
        conn.execute(f"UPDATE member SET {clause} WHERE id=?", (*fields.values(), m["id"]))
        _audit("update_member", m["id"], changes=fields)
        _print_member(conn.execute("SELECT * FROM member WHERE id=?", (m["id"],)).fetchone())


def cmd_add_alias(args):
    with _db() as conn:
        m = _require_member(conn, args.query)
        existing = _split_aliases(m["alias"])
        added = []
        for a in _split_aliases(args.alias):
            if a not in existing:
                existing.append(a)
                added.append(a)
        if not added:
            _die("no_new_alias")
        conn.execute("UPDATE member SET alias=? WHERE id=?", (_join_aliases(existing), m["id"]))
        _audit("add_alias", m["id"], reason="+".join(added))
        _print_member(conn.execute("SELECT * FROM member WHERE id=?", (m["id"],)).fetchone())


def cmd_find_member(args):
    with _db() as conn:
        m = _resolve(conn, args.query)
        if not m:
            _die(f"member_not_found query={args.query}")
        _print_member(m)


def cmd_list_members(args):
    with _db() as conn:
        rows = conn.execute("SELECT * FROM member ORDER BY sort_order, id").fetchall()
        if not rows:
            print("(empty)")
            return
        for m in rows:
            _print_member(m)


def _sum_expense(rows) -> float:
    return sum(float(r["amount"]) for r in rows if r["direction"] == "expense")


def _sum_income(rows) -> float:
    return sum(float(r["amount"]) for r in rows if r["direction"] == "income")


def _budget_snapshot(conn, asof: datetime, prefer_period=None, category=""):
    """取最贴合的预算：优先 prefer_period，否则 month>week>day；category 精确匹配优先总预算。"""
    cat = (category or "").strip()
    rows = conn.execute(
        "SELECT * FROM budget ORDER BY CASE period "
        "WHEN 'day' THEN 1 WHEN 'week' THEN 2 WHEN 'month' THEN 3 ELSE 4 END"
    ).fetchall()
    if not rows:
        return None

    def match(period):
        # 先分类精确，再总预算
        for r in rows:
            if r["period"] != period:
                continue
            if (r["category"] or "") == cat:
                return r
        if cat:
            for r in rows:
                if r["period"] == period and not (r["category"] or ""):
                    return r
        return None

    order = [prefer_period] if prefer_period else ["month", "week", "day"]
    order = [p for p in order if p]
    chosen = None
    for p in order:
        chosen = match(p)
        if chosen:
            break
    if not chosen:
        return None

    start, end = rules.period_range(chosen["period"], asof)
    spent_rows = _fetch_txns(
        conn, date_from=start, date_to=end,
        category=chosen["category"] or None,
    )
    spent = _sum_expense(spent_rows)
    amount = float(chosen["amount"])
    return {
        "period": chosen["period"],
        "amount": amount,
        "spent": spent,
        "remaining": amount - spent,
        "category": chosen["category"] or "",
        "from": start,
        "to": end,
    }


def cmd_add(args):
    try:
        amount = float(args.amount)
    except (TypeError, ValueError):
        _die("bad_amount")
    if amount <= 0:
        _die("amount_must_be_positive")

    direction = args.direction or "expense"
    if direction not in ("expense", "income"):
        _die("bad_direction")

    occurred = args.occurred_at or rules.now_bj().strftime("%Y-%m-%d")
    try:
        rules.parse_dt(occurred)
    except ValueError as e:
        _die(str(e))

    category = rules.normalize_category(args.category)
    note = args.note or ""
    image_url = args.image_url or ""
    source_msg = args.source_msg or ""
    # 归属：--member 优先，否则 --recorded-for；默认自动建档（群 sender_nickname / 话里点名）
    owner_q = (args.member or args.recorded_for or "").strip()
    if not owner_q:
        _die("member_required | 必须 --member <sender_nickname 或话里点名的人>")
    by_q = (args.recorded_by or args.actor or owner_q).strip()

    with _db() as conn:
        owner, owner_created = _ensure_member(conn, owner_q)
        by, by_created = _ensure_member(conn, by_q)
        day = _date_part(occurred)
        dup = conn.execute(
            f"SELECT txn_id FROM txn WHERE {_active_filter()} "
            "AND substr(occurred_at,1,10)=? AND amount=? AND category=? AND direction=? "
            "AND member_id=? LIMIT 1",
            (day, amount, category, direction, owner["id"]),
        ).fetchone()
        txn_id = _next_txn_id(conn, occurred)
        conn.execute(
            "INSERT INTO txn (txn_id, member_id, direction, amount, occurred_at, category, note, "
            "image_url, recorded_for, recorded_by, recorded_by_id, source_msg, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (txn_id, owner["id"], direction, amount, occurred, category, note, image_url,
             owner["name"], by["name"], by["id"], source_msg, _now()),
        )
        _audit("add", txn_id, amount=amount, category=category, direction=direction,
               occurred_at=occurred, note=note, member_id=owner["id"])

    _print_kv(
        ok=1, txn_id=txn_id, member_id=owner["id"], direction=direction, amount=amount,
        occurred_at=occurred, category=category, note=note,
        image_url=image_url or None, recorded_for=owner["name"],
        recorded_by=by["name"],
        member_created=1 if owner_created else None,
        recorder_created=1 if by_created else None,
        possible_duplicate=dup["txn_id"] if dup else None,
    )


def cmd_list(args):
    with _db() as conn:
        mid = None
        rf = args.recorded_for or args.member or ""
        if args.member:
            m = _resolve(conn, args.member)
            if m:
                mid = m["id"]
                rf = None
        rows = _fetch_txns(
            conn,
            date_from=args.date_from or args.date,
            date_to=args.date_to or args.date,
            category=args.category,
            recorded_for=rf,
            member_id=mid,
            include_deleted=bool(args.include_deleted),
        )
    if not rows:
        print("(empty)")
        return
    for r in rows:
        _print_kv(
            txn_id=r["txn_id"], member_id=r["member_id"] or None,
            direction=r["direction"], amount=float(r["amount"]),
            occurred_at=r["occurred_at"], category=r["category"],
            note=r["note"] or None, image_url=r["image_url"] or None,
            recorded_for=r["recorded_for"] or None,
            deleted=1 if r["deleted_at"] else None,
        )


def cmd_correct(args):
    reason = (args.reason or "").strip()
    if not reason:
        _die("reason_required")
    with _db() as conn:
        row = conn.execute("SELECT * FROM txn WHERE txn_id=?", (args.txn_id,)).fetchone()
        if not row:
            _die("txn_not_found")
        if row["deleted_at"]:
            _die("txn_deleted")
        _actor_can_edit(conn, args.actor, row)

        fields = {}
        if args.amount is not None:
            try:
                amt = float(args.amount)
            except ValueError:
                _die("bad_amount")
            if amt <= 0:
                _die("amount_must_be_positive")
            fields["amount"] = amt
        if args.direction:
            if args.direction not in ("expense", "income"):
                _die("bad_direction")
            fields["direction"] = args.direction
        if args.occurred_at:
            try:
                rules.parse_dt(args.occurred_at)
            except ValueError as e:
                _die(str(e))
            fields["occurred_at"] = args.occurred_at
        if args.category is not None:
            fields["category"] = rules.normalize_category(args.category)
        if args.note is not None:
            fields["note"] = args.note
        if args.image_url is not None:
            fields["image_url"] = args.image_url
        if args.member is not None or args.recorded_for is not None:
            q = args.member or args.recorded_for
            owner = _require_member(conn, q)
            fields["member_id"] = owner["id"]
            fields["recorded_for"] = owner["name"]
        if not fields:
            _die("nothing_to_correct")

        sets = ", ".join(f"{k}=?" for k in fields)
        conn.execute(
            f"UPDATE txn SET {sets} WHERE txn_id=?",
            (*fields.values(), args.txn_id),
        )
        _audit("correct", args.txn_id, reason=reason, changes=fields, actor=args.actor)

    _print_kv(ok=1, txn_id=args.txn_id, reason=reason, **fields)


def cmd_delete(args):
    reason = (args.reason or "").strip()
    if not reason:
        _die("reason_required")
    with _db() as conn:
        row = conn.execute("SELECT * FROM txn WHERE txn_id=?", (args.txn_id,)).fetchone()
        if not row:
            _die("txn_not_found")
        if row["deleted_at"]:
            _die("already_deleted")
        _actor_can_edit(conn, args.actor, row)
        conn.execute(
            "UPDATE txn SET deleted_at=?, deleted_reason=? WHERE txn_id=?",
            (_now(), reason, args.txn_id),
        )
        _audit("delete", args.txn_id, reason=reason, actor=args.actor,
               amount=float(row["amount"]), category=row["category"])
    _print_kv(ok=1, txn_id=args.txn_id, deleted=1, reason=reason)


def cmd_calc(args):
    asof = _parse_asof(args.asof)
    date_from, date_to = args.date_from, args.date_to
    scope = "range"
    if getattr(args, "all", False):
        date_from, date_to = None, None
        scope = "all"
    elif args.period:
        date_from, date_to = rules.period_range(args.period, asof)
        scope = args.period
    elif args.date:
        date_from = date_to = args.date
        scope = "day"
    elif not date_from and not date_to:
        # 无范围参数时默认全部（「一共多少」）；要今日请显式 --period day
        date_from, date_to = None, None
        scope = "all"

    with _db() as conn:
        mid = None
        rf = args.recorded_for or ""
        if getattr(args, "member", None):
            m = _resolve(conn, args.member)
            if not m:
                _die(f"member_not_found query={args.member}")
            mid = m["id"]
            rf = None
        elif rf:
            m = _resolve(conn, rf)
            if m:
                mid = m["id"]
                rf = None
        rows = _fetch_txns(
            conn, date_from=date_from, date_to=date_to,
            category=args.category, recorded_for=rf, member_id=mid,
        )
        bud = _budget_snapshot(
            conn, asof,
            prefer_period=args.period or "week",
            category=args.category or "",
        )

    expense = _sum_expense(rows)
    income = _sum_income(rows)
    by_cat: dict[str, float] = {}
    by_member: dict[str, float] = {}
    for r in rows:
        if r["direction"] != "expense":
            continue
        c = r["category"] or "其它"
        by_cat[c] = by_cat.get(c, 0.0) + float(r["amount"])
        mk = _txn_member_label(r)
        by_member[mk] = by_member.get(mk, 0.0) + float(r["amount"])

    from_s = date_from or "-"
    to_s = date_to or "-"
    print(f"scope={scope} from={from_s} to={to_s} count={len(rows)} "
          f"expense={rules.money(expense)} income={rules.money(income)} "
          f"net={rules.money(income - expense)}")
    if not getattr(args, "no_by_member", False):
        for name, amt in sorted(by_member.items(), key=lambda x: x[0]):
            print(f"member={name} expense={rules.money(amt)}")
    for cat, amt in sorted(by_cat.items(), key=lambda x: -x[1]):
        print(f"category={cat} expense={rules.money(amt)}")
    if args.detail:
        for r in rows:
            _print_kv(
                txn_id=r["txn_id"], member_id=r["member_id"] or None,
                direction=r["direction"],
                amount=float(r["amount"]), occurred_at=r["occurred_at"],
                category=r["category"], note=r["note"] or None,
                recorded_for=_txn_member_label(r),
            )
    if bud:
        print(
            f"budget_period={bud['period']} budget={rules.money(bud['amount'])} "
            f"budget_spent={rules.money(bud['spent'])} "
            f"budget_remaining={rules.money(bud['remaining'])} "
            f"budget_category={bud['category'] or '-'}"
        )


def cmd_report(args):
    asof = _parse_asof(args.date or args.asof)
    period = args.period or "day"

    with _db() as conn:
        if period == "day":
            day = asof.date().isoformat()
            date_from = date_to = day
            week_from, week_to = rules.week_range(asof)
            rows_raw = _fetch_txns(conn, date_from=day, date_to=day)
            week_rows = _fetch_txns(conn, date_from=week_from, date_to=week_to)
            week_expense = _sum_expense(week_rows)
            title, subtitle = "一起记账小本本", day
            empty = "今日无记录 🕊️"
            foot = "今日累计支出"
        elif period == "week":
            date_from, date_to = rules.week_range(asof)
            rows_raw = _fetch_txns(conn, date_from=date_from, date_to=date_to)
            week_expense = _sum_expense(rows_raw)
            title, subtitle = "一起记账 · 周账单", f"{date_from} ~ {date_to}"
            empty = "本周无记录 🕊️"
            foot = "本周累计支出"
        elif period == "month":
            date_from, date_to = rules.month_range(asof)
            rows_raw = _fetch_txns(conn, date_from=date_from, date_to=date_to)
            week_expense = _sum_expense(rows_raw)
            title, subtitle = "一起记账 · 月账单", f"{date_from} ~ {date_to}"
            empty = "本月无记录 🕊️"
            foot = "本月累计支出"
        else:
            _die("bad_period")

        bud = _budget_snapshot(conn, asof, prefer_period=period if period != "day" else "week")

    rows = [
        {
            "direction": r["direction"],
            "amount": float(r["amount"]),
            "category": r["category"],
            "note": r["note"] or "",
            "recorded_for": _txn_member_label(r),
        }
        for r in rows_raw
    ]

    if period == "day":
        text = rules.format_daily_report(subtitle, rows, week_expense, bud)
    else:
        text = rules.format_period_report(
            title, subtitle, rows, bud, empty_text=empty, foot_prefix=foot,
        )

    print(f"ok=1 period={period} from={date_from} to={date_to} "
          f"count={len(rows)} expense={rules.money(_sum_expense(rows_raw))}")
    print(text)


def cmd_set_budget(args):
    period = args.period
    if period not in ("day", "week", "month"):
        _die("bad_period")
    try:
        amount = float(args.amount)
    except (TypeError, ValueError):
        _die("bad_amount")
    if amount <= 0:
        _die("amount_must_be_positive")
    # 未传 / 空串 = 总预算；显式分类走 normalize
    if args.category is None or not str(args.category).strip():
        category = ""
    else:
        category = rules.normalize_category(args.category)

    with _db() as conn:
        conn.execute(
            "INSERT INTO budget (period, amount, category, note, updated_at) "
            "VALUES (?,?,?,?,?) "
            "ON CONFLICT(period, category) DO UPDATE SET "
            "amount=excluded.amount, note=excluded.note, updated_at=excluded.updated_at",
            (period, amount, category, args.note or "", _now()),
        )
        _audit("set_budget", f"{period}:{category or '*'}", amount=amount)
        asof = rules.now_bj()
        snap = _budget_snapshot(conn, asof, prefer_period=period, category=category)

    _print_kv(
        ok=1, period=period, amount=amount, category=category or "-",
        spent=snap["spent"] if snap else 0,
        remaining=snap["remaining"] if snap else amount,
    )


def cmd_show_budget(args):
    asof = _parse_asof(args.asof)
    with _db() as conn:
        rows = conn.execute("SELECT * FROM budget ORDER BY period, category").fetchall()
        if not rows:
            print("(empty)")
            return
        for r in rows:
            snap = _budget_snapshot(
                conn, asof, prefer_period=r["period"], category=r["category"] or "",
            )
            print(
                f"period={r['period']} amount={rules.money(float(r['amount']))} "
                f"category={r['category'] or '-'} "
                f"spent={rules.money(snap['spent']) if snap else 0} "
                f"remaining={rules.money(snap['remaining']) if snap else rules.money(float(r['amount']))} "
                f"from={snap['from'] if snap else '-'} to={snap['to'] if snap else '-'}"
            )


def cmd_query(args):
    sql = (args.sql or "").strip().rstrip(";")
    low = sql.lower()
    if not low.startswith("select"):
        _die("query_readonly_only")
    forbidden = (" insert ", " update ", " delete ", " drop ", " alter ",
                 " attach ", " pragma ")
    padded = f" {low} "
    if any(x in padded for x in forbidden):
        _die("query_forbidden_keyword")
    with _db() as conn:
        cur = conn.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchall()
    if not rows:
        print("(empty)")
        return
    print("columns=" + ",".join(cols))
    for r in rows:
        print(" | ".join(str(r[c]) for c in cols))


def _build_parser():
    p = argparse.ArgumentParser(prog="ledger.py", description="个人日常记账 CLI")
    s = p.add_subparsers(dest="command", required=True)

    a = s.add_parser("add_member")
    a.add_argument("id")
    a.add_argument("name")
    a.add_argument("--at-name", dest="at_name", default="")
    a.add_argument("--alias", default="")
    a.add_argument("--sort", default=0)
    a.add_argument("--status", default="active")
    a.add_argument("--is-admin", dest="is_admin", type=int, default=0)
    a.add_argument("--description", default="")

    a = s.add_parser("update_member")
    a.add_argument("query")
    a.add_argument("--name", default=None)
    a.add_argument("--at-name", dest="at_name", default=None)
    a.add_argument("--alias", default=None)
    a.add_argument("--sort", default=None)
    a.add_argument("--status", default=None)
    a.add_argument("--is-admin", dest="is_admin", type=int, default=None)
    a.add_argument("--description", default=None)

    a = s.add_parser("add_alias")
    a.add_argument("query")
    a.add_argument("alias")

    a = s.add_parser("find_member")
    a.add_argument("query")

    a = s.add_parser("list_members")

    a = s.add_parser("add")
    a.add_argument("amount")
    a.add_argument("--direction", default="expense", choices=["expense", "income"])
    a.add_argument("--occurred-at", dest="occurred_at", default="")
    a.add_argument("--category", default="")
    a.add_argument("--note", default="")
    a.add_argument("--image-url", dest="image_url", default="")
    a.add_argument("--member", default="", help="归属成员 id|name|@名|别名")
    a.add_argument("--recorded-for", dest="recorded_for", default="", help="同 --member（兼容）")
    a.add_argument("--recorded-by", dest="recorded_by", default="")
    a.add_argument("--actor", default="", help="操作者（默认=归属人）")
    a.add_argument("--source-msg", dest="source_msg", default="")

    a = s.add_parser("list")
    a.add_argument("--date", default="")
    a.add_argument("--from", dest="date_from", default="")
    a.add_argument("--to", dest="date_to", default="")
    a.add_argument("--category", default="")
    a.add_argument("--member", default="")
    a.add_argument("--recorded-for", dest="recorded_for", default="")
    a.add_argument("--include-deleted", action="store_true")

    a = s.add_parser("correct")
    a.add_argument("txn_id")
    a.add_argument("--reason", required=True)
    a.add_argument("--actor", default="", help="操作者；改他人账需管理员")
    a.add_argument("--amount", default=None)
    a.add_argument("--direction", default=None)
    a.add_argument("--occurred-at", dest="occurred_at", default=None)
    a.add_argument("--category", default=None)
    a.add_argument("--note", default=None)
    a.add_argument("--image-url", dest="image_url", default=None)
    a.add_argument("--member", default=None)
    a.add_argument("--recorded-for", dest="recorded_for", default=None)

    a = s.add_parser("delete")
    a.add_argument("txn_id")
    a.add_argument("--reason", required=True)
    a.add_argument("--actor", default="", help="操作者；删他人账需管理员")

    a = s.add_parser("calc")
    a.add_argument("--period", choices=["day", "week", "month"], default=None)
    a.add_argument("--all", action="store_true", help="全部未删除流水（一共多少）")
    a.add_argument("--date", default="")
    a.add_argument("--from", dest="date_from", default="")
    a.add_argument("--to", dest="date_to", default="")
    a.add_argument("--asof", default="")
    a.add_argument("--category", default="")
    a.add_argument("--member", default="")
    a.add_argument("--recorded-for", dest="recorded_for", default="")
    a.add_argument("--detail", action="store_true")
    a.add_argument("--no-by-member", action="store_true")

    a = s.add_parser("report")
    a.add_argument("--period", choices=["day", "week", "month"], default="day")
    a.add_argument("--date", default="")
    a.add_argument("--asof", default="")

    a = s.add_parser("set_budget")
    a.add_argument("--period", required=True, choices=["day", "week", "month"])
    a.add_argument("--amount", required=True)
    a.add_argument("--category", default=None)
    a.add_argument("--note", default="")

    a = s.add_parser("show_budget")
    a.add_argument("--asof", default="")

    a = s.add_parser("query")
    a.add_argument("--sql", required=True)

    return p


COMMANDS = {
    "add_member": cmd_add_member,
    "update_member": cmd_update_member,
    "add_alias": cmd_add_alias,
    "find_member": cmd_find_member,
    "list_members": cmd_list_members,
    "add": cmd_add,
    "list": cmd_list,
    "correct": cmd_correct,
    "delete": cmd_delete,
    "calc": cmd_calc,
    "report": cmd_report,
    "set_budget": cmd_set_budget,
    "show_budget": cmd_show_budget,
    "query": cmd_query,
}


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    fn = COMMANDS.get(args.command)
    if not fn:
        _die(f"unknown_command {args.command}")
    fn(args)


if __name__ == "__main__":
    main()
