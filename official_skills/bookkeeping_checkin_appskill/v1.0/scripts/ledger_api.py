#!/usr/bin/env python3
"""记账台账 App 的业务 handler（operation 路由）。

唯一链路是记账卡片流：
  draft_txn   出可编辑草稿卡（不落库）
  用户在卡片上点确认 / 五分钟超时
  commit_txn  落库一条流水；点取消走 cancel_txn（不落库）

另有两个不出卡的只读/维护 op：find_txn（查询定位 txn_id）、delete_txn（软删）。

**建档前置**（与跑团打卡同一条规矩）：归属人必须是已建档成员。
  draft_txn / commit_txn 都致命：查不到直接 MEMBER_NOT_FOUND，不出卡、不落库。
  绝不为记账自动建档。

输出：单个 JSON（structuredContent），phase=bookkeeping_card / bookkeeping_list /
bookkeeping_deleted / error。_run.py 只在 phase=bookkeeping_card 且 operation=draft_txn
时挂卡片资源。

字段命名分三套，别混：
  工具入参     owner / owner_id / occurred_at / transaction_type / amount / merchant
  card_data    ownerName（raw={text,memberId}）/ date / transactionType / amount / currencyUnit / merchantName
  库表列       member_id / occurred_at / transaction_type / amount / merchant_name
三者各自演进，转换只发生在本文件里。
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import card_schema
import vocab
from cli_contract import ContractError, validate_operation

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
ASSETS_DIR = os.path.join(SKILL_ROOT, "assets")

# tracker 是可导入模块（不像跑团那边要走子进程），直接 import 少一层出错面。
if ASSETS_DIR not in sys.path:
    sys.path.insert(0, ASSETS_DIR)
import tracker  # noqa: E402

_TZ = timezone(timedelta(hours=8))


class LedgerError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class AwaitUserConfirm(LedgerError):
    """确认失败换卡后，模型本轮又对本卡 commit。不走换卡，只拒。"""


# 卡片四态：pending 待确认 / recording 待录入 / confirmed 已确认 / cancelled 已取消。
# recording 是端上点确认到模型回包的中间态，本 skill 不吐。
# 超时自动结算：字段齐全则落库打成 confirmed，校验失败则 cancelled。
STATUS_PENDING = "pending"
STATUS_RECORDING = "recording"
STATUS_CONFIRMED = "confirmed"
STATUS_CANCELLED = "cancelled"
TERMINAL_STATUSES = (STATUS_CONFIRMED, STATUS_CANCELLED)
EMITTED_STATUSES = (STATUS_PENDING, STATUS_CONFIRMED, STATUS_CANCELLED)

# 待确认卡片的存活时长。超过未操作由服务端定时任务自动结算（成功 confirmed / 失败 cancelled）。
CARD_EXPIRE_SECONDS = 300


def _now() -> str:
    return datetime.now(_TZ).isoformat(timespec="seconds")


def _gen_id(prefix: str, *parts: str) -> str:
    seed = "|".join([*parts, _now(), os.urandom(4).hex()])
    return f"{prefix}_{hashlib.md5(seed.encode()).hexdigest()[:10]}"


def _coerce_float(value) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f


def _expire_at(status: str) -> int:
    """只有待确认卡给倒计时；待录入/已确认/已取消一律归零。"""
    if status == STATUS_PENDING:
        return int(datetime.now(_TZ).timestamp()) + CARD_EXPIRE_SECONDS
    return 0


def _is_auto(args: dict) -> bool:
    """超时自动确认：只 update，失败不换新卡。"""
    for key in ("auto", "timeout", "auto_confirm"):
        v = args.get(key)
        if v is True or str(v).lower() in ("1", "true", "yes"):
            return True
    return False


# ---------------------------------------------------------------------------
# 成员解析（建档前置）
# ---------------------------------------------------------------------------

def _try_resolve_owner(conn, args: dict) -> tuple[bool, str, str]:
    """非致命地解析归属人；返回 (registered, display_name, member_id)。

    优先按模型显式给的 owner_id 查（客户端把 ownerName.raw.memberId 回传上来的
    就是它），否则按 owner 文本走 id→name/at_name→alias 匹配。查不到不报错，
    只是 registered=False——draft / commit 都会据此拒掉，不出卡。
    """
    owner_id = str(args.get("owner_id") or "").strip()
    # user_N 是会话匿名 id，不是档案主键，不能拿去撞 member.id。
    if owner_id and not tracker.is_anon_user_id(owner_id):
        member = tracker.get_member(conn, owner_id)
        if member:
            return True, member["name"], member["id"]
    query = str(args.get("owner") or "").strip()
    if not query:
        return False, "", ""
    member = tracker.find_member(conn, query)
    if member:
        return True, member["name"], member["id"]
    return False, query, ""


def _resolve_owner(conn, args: dict) -> dict[str, Any]:
    """致命版：解析不到就 MEMBER_NOT_FOUND。落库路径专用，绝不擅自建档。"""
    registered, name, member_id = _try_resolve_owner(conn, args)
    if not registered:
        query = str(args.get("owner_id") or args.get("owner") or "").strip()
        raise LedgerError(
            "MEMBER_NOT_FOUND",
            f"归属人未建档：{query or '（空）'}。请先用人话请用户把这个人建成群成员，"
            "用户明确同意后再建档；未建档不要出卡，也不要为了记账自动建档。"
            "对用户禁止贴任何命令。")
    return {"id": member_id, "name": name}


# ---------------------------------------------------------------------------
# 字段归一
# ---------------------------------------------------------------------------

def _resolved_fields(args: dict) -> dict[str, Any]:
    """把工具入参归一成 card_data 要的取值，并套上业务兜底规则。

    兜底规则（与 spec 一致）：
      日期缺失      -> 当天
      分类判断不出  -> other（但类型未定时留空：分类选项按类型分组，类型不定则分类无从谈起）
      账户判断不出  -> other
      类型/金额缺失 -> 留空，进 missing 清单让用户在卡片上补

    归属人不在这里处理——它要查库，见 _try_resolve_owner。
    """
    transaction_type = vocab.normalize_transaction_type(args.get("transaction_type", ""))
    occurred_at = str(args.get("occurred_at") or args.get("today") or "").strip()
    if not occurred_at:
        occurred_at = tracker.today_str()

    if transaction_type:
        category = vocab.normalize_category(transaction_type, args.get("category", ""))
    else:
        category = ""

    return {
        "occurred_at": occurred_at,
        "transaction_type": transaction_type,
        "amount": _coerce_float(args.get("amount")),
        "currency": vocab.normalize_currency(args.get("currency")),
        "category": category,
        "account": vocab.normalize_account(args.get("account", "")),
        "merchant_name": str(args.get("merchant") or "").strip(),
        "note": str(args.get("note") or "").strip(),
    }


def _txn_missing(card_data: dict[str, Any], *, member_registered: bool) -> list[str]:
    """卡片落库最小字段缺失清单（供 UI 提示 / 确认门槛）。

    从 card_data 的 sections 里回读 raw 值，键名用 fieldId——这样"下发给客户端的
    那份"和"校验依据的那份"是同一份数据，客户端在编辑面板改完回传后，同一个函数
    可以直接复用来判断能不能确认落库。member_registered 是唯一的例外：它不是卡面
    上的字段，而是"这个人在不在库里"，只能由服务端查库得知。
    """
    missing: list[str] = []
    if not card_schema.owner_name_of(card_data).strip():
        missing.append("ownerName")
    elif not member_registered:
        missing.append("member_registered")
    if card_schema.field_raw(card_data, "transactionType") not in vocab.TRANSACTION_TYPES:
        missing.append("transactionType")
    amount = _coerce_float(card_schema.field_raw(card_data, "amount"))
    if amount is None or amount <= 0:
        missing.append("amount")
    if not str(card_schema.field_raw(card_data, "date") or "").strip():
        missing.append("date")
    return missing


def _build_card(conn, operation: str, args: dict, *, status: str,
                receipt: dict | None = None,
                owner: dict[str, Any] | None = None) -> dict[str, Any]:
    """把卡片字段整理成 structuredContent（draft / commit / cancel 共用回包结构）。

    信封上只留路由与状态：card_id / operate_type / status / expire_at；改旧卡再加 update_seq_id。
    渲染要用的一切都在 card_data 里。image_url / quote 这些不上卡面的留在信封里
    供模型用，由 _run.py 的白名单裁掉后再发给客户端。

    owner 已解析时（commit 路径）直接传进来复用，避免重复查库。
    """
    if status not in EMITTED_STATUSES:
        raise LedgerError(
            "INVALID_ARGUMENT",
            f"skill 不吐卡片状态 {status!r}（待录入 recording 由端上本地切，"
            "只下发 pending / confirmed / cancelled）")
    if owner is not None:
        registered, owner_name, owner_id = True, owner["name"], owner["id"]
    else:
        registered, owner_name, owner_id = _try_resolve_owner(conn, args)
    resolved = _resolved_fields(args)
    # card_id 要先算出来：它既是信封的主键，也进 card_data.cardId 给客户端对卡。
    card_id = args.get("card_id") or _gen_id("card", str(args.get("group_id") or "default"))
    card_data = card_schema.build_card_data(
        card_id=card_id,
        owner_name=owner_name,
        owner_id=owner_id or None,
        occurred_date=resolved["occurred_at"],
        transaction_type=resolved["transaction_type"],
        amount=resolved["amount"],
        currency=resolved["currency"],
        category=resolved["category"],
        account=resolved["account"],
        merchant_name=resolved["merchant_name"],
        note=resolved["note"],
        status=status,
    )
    missing = _txn_missing(card_data, member_registered=registered)
    out: dict[str, Any] = {
        "phase": "bookkeeping_card",
        "operation": operation,
        "group_id": args.get("group_id", "default"),
        "card_id": card_id,
        # 发起人：谁触发了这次记账。与 card_data 平级而不在卡面字段里——它不是要展示的
        # 一行，只标记这张卡的来源。注意它和「归属人」是两回事：A 帮 B 记一笔时
        # user_id 是 A，card_data 里的 ownerName 是 B。
        # user_id 是这张卡的发起人。普通出卡模型填 user_N，群聊 agent 出卡前还原成真实 uid 再下发；
        # 模型漏填时服务端用本轮发言人补。确认链路用 action.user_id。
        "user_id": str(args.get("user_id") or ""),
        "status": status,
        "operate_type": "update" if status != STATUS_PENDING else "create",
        # expire_at 在信封而不在 card_data：它不是卡面上的一行，客户端拿它做本地倒计时。
        "expire_at": _expire_at(status),
        "card_data": card_data,
        # 图片/引用不进协议 card_data（卡片不展示），留在信封里供模型使用。
        "image_url": args.get("image_url", "") or "",
        "quote": args.get("quote") or {},
        "member_registered": registered,
        "min_ready": not missing,
        "missing": missing,
    }
    if status != STATUS_PENDING:
        # 改已有卡：update_seq_id 由群聊服务端从当前 GUI_ACTION/app.env 消息 extra 填写。
        out["update_seq_id"] = str(args.get("update_seq_id") or "")
    # 编辑模式：把 txn_id 带进 structuredContent，让"修改已落盘记录"的卡片一路带到 commit。
    if args.get("txn_id"):
        out["txn_id"] = str(args["txn_id"])
    # 纠正新卡：supersedes 指向被替代的旧 card_id。真正置灰靠同轮再吐一张 cancelled update。
    if args.get("supersedes"):
        out["supersedes"] = str(args["supersedes"])
    if receipt is not None:
        out["receipt"] = receipt
    return out


def _month_of(date_str: str) -> str:
    text = str(date_str or "").strip()
    return text[:7] if len(text) >= 7 else ""


def _receipt_summary(conn, member_id: str, occurred_at: str,
                     group_id: str) -> dict[str, Any]:
    """回执里带当月收支合计，让元宝能顺口反馈"这个月花了多少"。"""
    return tracker.summary(conn, member_id=member_id, month=_month_of(occurred_at),
                           group_id=group_id or "")


# ---------------------------------------------------------------------------
# operations
# ---------------------------------------------------------------------------

def op_draft_txn(conn, args) -> dict[str, Any]:
    """出可编辑记账草稿卡片——不落库、不写表，只回显已知字段供卡片渲染。

    建档前置与跑团一致：归属人未建档直接 MEMBER_NOT_FOUND，不出卡。
    纠正（带 supersedes）：同轮 update 旧卡为已取消 + create 新卡。
    """
    _resolve_owner(conn, args)
    new_card = _build_card(conn, "draft_txn", args, status=STATUS_PENDING)
    return _with_supersede_cancel(conn, args, new_card)


def _with_supersede_cancel(conn, args: dict, new_card: dict[str, Any]) -> dict[str, Any]:
    """纠正未确认卡：先 update 旧卡 cancelled，再 create 新卡。"""
    old_id = str(args.get("supersedes") or "").strip()
    new_id = str(new_card.get("card_id") or "")
    if not old_id or old_id == new_id:
        return new_card
    old_card = _build_card(
        conn, "cancel_txn", dict(args, card_id=old_id), status=STATUS_CANCELLED)
    return {
        "phase": "bookkeeping_card",
        "operation": "draft_txn",
        "card_id": new_id,
        "supersedes": old_id,
        "cancelled_card_id": old_id,
        "status": STATUS_PENDING,
        "cards": [old_card, new_card],
    }


def op_cancel_txn(conn, args) -> dict[str, Any]:
    """用户在卡片上点取消：只把卡片打成 cancelled 终态，不写库、不产生任何流水。

    与 delete_txn 的区别是这张卡从来没落过库，所以没有 txn_id 可删，
    也不需要回合计数据——纯粹是把待确认的草稿卡收掉。
    """
    return _build_card(conn, "cancel_txn", args, status=STATUS_CANCELLED)


def _lock_reissued_card(conn, new_card_id: str, source_card_id: str, source_seq_id: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO reissue_lock"
        "(card_id, source_card_id, source_seq_id, created_at) VALUES (?,?,?,?)",
        (new_card_id, source_card_id, source_seq_id, _now()),
    )
    conn.commit()


def _reject_same_turn_reissue_commit(conn, args: dict) -> None:
    """失败换出的新卡，同一轮（同一个 update_seq_id）禁止再 commit。"""
    card_id = str(args.get("card_id") or "").strip()
    if not card_id:
        return
    row = conn.execute(
        "SELECT source_seq_id FROM reissue_lock WHERE card_id=?", (card_id,)
    ).fetchone()
    if row is None:
        return
    incoming_seq = str(args.get("update_seq_id") or "").strip()
    source_seq = str(row["source_seq_id"] or "").strip()
    if incoming_seq == source_seq or not incoming_seq:
        raise AwaitUserConfirm(
            "AWAIT_USER_CONFIRM",
            f"这张卡 {card_id} 是确认失败后新出的待确认卡，必须等用户再次点确认。"
            "本轮不要 commit，也不要说已记账。",
        )
    conn.execute("DELETE FROM reissue_lock WHERE card_id=?", (card_id,))
    conn.commit()


def _reissue_after_commit_fail(conn, args: dict, exc: BaseException) -> dict[str, Any]:
    """确认链路校验/落库失败：旧卡取消 + 新出一张待确认卡。

    用户已经点了确认，旧卡不能再停在 pending。失败原因写给模型，两张卡由
    _run.py 拆成两条 sentinel 下发。
    """
    code = getattr(exc, "code", type(exc).__name__)
    message = getattr(exc, "message", str(exc))
    old_id = str(args.get("card_id") or "").strip()
    cards: list[dict[str, Any]] = []
    if old_id:
        cards.append(_build_card(
            conn, "cancel_txn", dict(args, card_id=old_id),
            status=STATUS_CANCELLED))
    new_id = _gen_id("card", str(args.get("group_id") or "default"), old_id or "reissue")
    draft_args = dict(args, card_id=new_id)
    if old_id:
        draft_args["supersedes"] = old_id
    cards.append(_build_card(conn, "draft_txn", draft_args, status=STATUS_PENDING))
    _lock_reissued_card(
        conn, new_id, old_id, str(args.get("update_seq_id") or "").strip())
    old_hint = f"（{old_id}）" if old_id else ""
    return {
        "phase": "error",
        "code": code,
        "message": (
            f"落库失败：{message}。旧卡已取消{old_hint}，已新出一张待确认卡 {new_id}。"
            "请让用户在新卡上核对/补齐后再点确认；不要对旧卡再 commit，也不要再自己 draft。"
        ),
        "reissued": True,
        "cancelled_card_id": old_id,
        "new_card_id": new_id,
        "cards": cards,
    }


def _cancel_after_timeout_fail(conn, args: dict, exc: BaseException) -> dict[str, Any]:
    """超时自动结算校验/落库失败：只取消旧卡，不再出新卡。

    过期确认只落到 confirmed（写库成功）或 cancelled（写库失败）两种终态。
    """
    code = getattr(exc, "code", type(exc).__name__)
    message = getattr(exc, "message", str(exc))
    old_id = str(args.get("card_id") or "").strip()
    cards: list[dict[str, Any]] = []
    if old_id:
        cards.append(_build_card(
            conn, "cancel_txn", dict(args, card_id=old_id),
            status=STATUS_CANCELLED))
    return {
        "phase": "error",
        "code": code,
        "message": f"超时结算未落库：{message}。",
        "reissued": False,
        "cancelled_card_id": old_id,
        "cards": cards,
    }


def op_commit_txn(conn, args) -> dict[str, Any]:
    """用户确认后落库：校验必填 + 归属人已建档 → 写一条流水（或编辑模式整体更正）。"""
    _reject_same_turn_reissue_commit(conn, args)
    resolved = _resolved_fields(args)
    if resolved["transaction_type"] not in vocab.TRANSACTION_TYPES:
        raise LedgerError(
            "INVALID_ARGUMENT",
            f"transaction_type 非法：{args.get('transaction_type')!r}"
            f"（须为 {', '.join(vocab.TRANSACTION_TYPES)} 之一）")
    amount = resolved["amount"]
    if amount is None or amount <= 0:
        raise LedgerError("INVALID_ARGUMENT", "amount 必须为正数")
    # 建档前置：未建档在这里就断掉，不写库。
    owner = _resolve_owner(conn, args)
    # 类型确定后分类才有意义：commit 这一轮把兜底补齐（draft 时类型可能还没定）。
    category = vocab.normalize_category(resolved["transaction_type"], args.get("category", ""))
    group_id = str(args.get("group_id") or "default")
    status = STATUS_CONFIRMED

    txn_id = str(args.get("txn_id") or "").strip()
    if txn_id:
        row = tracker.update_txn(conn, txn_id, {
            "member_id": owner["id"],
            "occurred_at": resolved["occurred_at"],
            "transaction_type": resolved["transaction_type"],
            "amount": amount,
            "currency": resolved["currency"],
            "category": category,
            "account": resolved["account"],
            "merchant_name": resolved["merchant_name"],
            "note": resolved["note"],
        })
        receipt = {
            "txn_id": row.get("txn_id", txn_id),
            "member_name": row.get("member_name", owner["name"]),
            "edited": True,
            "summary": _receipt_summary(conn, owner["id"],
                                        resolved["occurred_at"], group_id),
        }
        return _build_card(conn, "commit_txn", args, status=status,
                           receipt=receipt, owner=owner)

    card_id = str(args.get("card_id") or "").strip()
    try:
        row = tracker.add_txn(
            conn,
            member_id=owner["id"],
            occurred_at=resolved["occurred_at"],
            transaction_type=resolved["transaction_type"],
            amount=amount,
            currency=resolved["currency"],
            category=category,
            account=resolved["account"],
            merchant_name=resolved["merchant_name"],
            note=resolved["note"],
            group_id=group_id,
            card_id=card_id,
            status=status,
        )
    except tracker.TrackerError as exc:
        if exc.code == "DUPLICATE_TXN":
            # 幂等：同一张卡重复确认 / 客户端重试 → 视为已录入，回执标 duplicate。
            existing = tracker.find_by_card(conn, card_id) or {}
            receipt = {
                "txn_id": existing.get("txn_id", ""),
                "member_name": existing.get("member_name", owner["name"]),
                "duplicate": True,
                "summary": _receipt_summary(conn, owner["id"],
                                            resolved["occurred_at"], group_id),
            }
            return _build_card(conn, "commit_txn", args, status=status,
                               receipt=receipt, owner=owner)
        raise LedgerError(exc.code, exc.message) from None

    receipt = {
        "txn_id": row.get("txn_id", ""),
        "member_name": row.get("member_name", owner["name"]),
        "transaction_type": row.get("transaction_type", ""),
        "amount": row.get("amount"),
        "category": row.get("category", ""),
        "account": row.get("account", ""),
        "summary": _receipt_summary(conn, owner["id"],
                                    resolved["occurred_at"], group_id),
    }
    return _build_card(conn, "commit_txn", args, status=status,
                       receipt=receipt, owner=owner)


def _record_view(row: dict[str, Any]) -> dict[str, Any]:
    """给模型看的流水视图：机器码 + 中文标签都给，省得模型自己查表。
    member_name 是 JOIN 出来的实时姓名，不是落库时的快照。"""
    ttype = row.get("transaction_type", "")
    return {
        "txn_id": row.get("txn_id", ""),
        "member_id": row.get("member_id", ""),
        "member_name": row.get("member_name", ""),
        "occurred_at": row.get("occurred_at", ""),
        "transaction_type": ttype,
        "transaction_type_label": vocab.type_label(ttype),
        "amount": row.get("amount"),
        "currency": vocab.normalize_currency(row.get("currency")),
        "currency_label": vocab.currency_label(row.get("currency")),
        "amount_text": vocab.format_money(row.get("amount"),
                                          row.get("currency")),
        "category": row.get("category", ""),
        "category_label": vocab.category_label(ttype, row.get("category", "")),
        "account": row.get("account", ""),
        "account_label": vocab.account_label(row.get("account", "")),
        "merchant_name": row.get("merchant_name", ""),
        "note": row.get("note", ""),
        "status": row.get("status", ""),
    }


def op_find_txn(conn, args) -> dict[str, Any]:
    """只读查询已落库流水（供"修改/删除已落盘记录"定位 txn_id + 现有字段预填卡片）。
    不写库、不出卡。回包带 summary，也能直接回答"这个月花了多少"。

    给了 owner 但查不到这个人时不报错，而是回 member_not_found=true + 空列表——
    让模型能区分"这人不存在"和"这人没有记录"，说法不一样。
    """
    month = str(args.get("month") or "").strip()
    date = str(args.get("date") or "").strip()
    group_id = str(args.get("group_id") or "").strip()

    member_id = ""
    member_name = ""
    if args.get("owner") or args.get("owner_id"):
        registered, name, mid = _try_resolve_owner(conn, args)
        if not registered:
            return {
                "phase": "bookkeeping_list",
                "operation": "find_txn",
                "group_id": args.get("group_id", "default"),
                "member_not_found": True,
                "query": str(args.get("owner_id") or args.get("owner") or ""),
                "records": [],
                "summary": None,
            }
        member_id, member_name = mid, name

    rows = tracker.list_txns(
        conn,
        member_id=member_id,
        date=date,
        month=month,
        transaction_type=vocab.normalize_transaction_type(args.get("transaction_type", "")),
        group_id=group_id,
        limit=int(args.get("limit") or 50),
    )
    # 统计口径：给了 month 就按 month，否则按 date 所在月，都没给就不限月。
    scope_month = month or _month_of(date)
    return {
        "phase": "bookkeeping_list",
        "operation": "find_txn",
        "group_id": args.get("group_id", "default"),
        "member_id": member_id,
        "member_name": member_name,
        "records": [_record_view(r) for r in rows],
        "summary": tracker.summary(conn, member_id=member_id, month=scope_month,
                                   group_id=group_id),
    }


def op_delete_txn(conn, args) -> dict[str, Any]:
    """删除一条【已落库】流水（软删 deleted_at）。不出卡、不改动前端已完成的卡片，
    仅回文本回执 + 该归属人当月最新合计。
    只按 txn_id 删除（由 find_txn 先定位）；指令模糊时应先 find_txn 让用户确认。"""
    txn_id = str(args.get("txn_id") or "").strip()
    if not txn_id:
        raise LedgerError("INVALID_ARGUMENT",
                          "delete_txn 必须提供 txn_id（先用 find_txn 定位目标记录）。")
    reason = str(args.get("reason") or "").strip() or "用户要求删除流水"
    try:
        row = tracker.delete_txn(conn, txn_id, reason)
    except tracker.TrackerError as exc:
        if exc.code == "TXN_NOT_FOUND":
            raise LedgerError(
                "TXN_NOT_FOUND",
                f"未找到要删除的流水：txn_id={txn_id}（可能已删除，请用 find_txn 重新确认）"
            ) from None
        raise LedgerError(exc.code, exc.message) from None
    group_id = str(args.get("group_id") or "").strip()
    # phase 非 bookkeeping_card ⇒ _run.py 不挂 UI 资源 ⇒ 不出卡，仅由元宝文字回复。
    return {
        "phase": "bookkeeping_deleted",
        "operation": "delete_txn",
        "group_id": args.get("group_id", "default"),
        "txn_id": txn_id,
        "receipt": {
            "deleted": True,
            "txn_id": txn_id,
            "member_name": row.get("member_name", ""),
            "amount_text": vocab.format_money(row.get("amount"),
                                               row.get("currency")),
            "summary": _receipt_summary(conn, row.get("member_id", ""),
                                         row.get("occurred_at", ""), group_id),
        },
    }


_OPS = {
    "draft_txn": op_draft_txn,
    "commit_txn": op_commit_txn,
    "cancel_txn": op_cancel_txn,
    "find_txn": op_find_txn,
    "delete_txn": op_delete_txn,
}


def execute(operation: str, args: dict, *, agent_call: bool = False) -> dict[str, Any]:
    # 用校验后的返回值（而不是原始 args）——validate_operation 会把 "38.5" / "¥38.5"
    # 这类数字字段的字符串笔误安全转换成真正的 number，不接住的话下游拿到的还是字符串。
    raw_args = dict(args)
    conn = tracker.connect()
    try:
        try:
            # 先看换卡锁，再做字段校验：同一轮对失败新卡再 commit
            # （哪怕参数又缺）也只能拒，不能再 cancel + 出第三张卡。
            if operation == "commit_txn":
                _reject_same_turn_reissue_commit(conn, raw_args)
            coerced_args = validate_operation(operation, args, agent_call=agent_call)
            return _OPS[operation](conn, coerced_args)
        except AwaitUserConfirm as exc:
            return {
                "phase": "error",
                "code": exc.code,
                "message": exc.message,
                "reissued": False,
                "await_user_confirm": True,
                "card_id": str(raw_args.get("card_id") or ""),
            }
        except (ContractError, LedgerError, tracker.TrackerError) as exc:
            if operation == "commit_txn":
                if _is_auto(raw_args):
                    return _cancel_after_timeout_fail(conn, raw_args, exc)
                return _reissue_after_commit_fail(conn, raw_args, exc)
            raise
    finally:
        conn.close()


def main() -> int:
    raw = sys.argv[1] if len(sys.argv) > 1 else "{}"
    operation = ""
    try:
        args = json.loads(raw)
        if not isinstance(args, dict):
            raise LedgerError("INVALID_ARGUMENT", "请求参数必须为对象。")
        operation = args.pop("operation", "")
        result = execute(operation, args)
    except (json.JSONDecodeError, ContractError, LedgerError, tracker.TrackerError) as exc:
        code = getattr(exc, "code", "INVALID_JSON")
        message = getattr(exc, "message", str(exc))
        result = {"phase": "error", "code": code, "message": message}
    result.setdefault("operation", operation)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
