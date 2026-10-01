"""记账台账 App 的机器可读 contract（operation / 字段 / 可见性）。

visibility / agentAllowed 语义：
  - agentAllowed=True  → 模型（Agent）可通过 _run.py ledger_api 调用
  - agentAllowed=False → 仅 App 页面可通过 tools/call → POST /app/call 直调（跳过模型）

记账卡片流是唯一链路：draft_txn 出可编辑草稿卡（不落库），用户在卡片上点确认后
才 commit_txn 落库。模型没有任何直接写流水的入口——assets/tracker.py 不对模型开放。
"""

from __future__ import annotations

from difflib import get_close_matches
from typing import Any

from vocab import ACCOUNTS, CATEGORIES, CURRENCIES, TRANSACTION_TYPES

TRANSACTION_TYPE_IDS = tuple(TRANSACTION_TYPES)
ACCOUNT_IDS = tuple(ACCOUNTS)
CATEGORY_IDS = tuple(sorted({cid for group in CATEGORIES.values() for cid in group}))


class ContractError(ValueError):
    pass


_TYPE_HINT = " / ".join(f"{k}（{v}）" for k, v in TRANSACTION_TYPES.items())

OPERATIONS: dict[str, dict[str, Any]] = {
    "draft_txn": {
        "description": (
            "识别到记账语义后，出一张【可编辑记账草稿卡片】（信息有啥放啥，允许不全）。"
            "不落库、不写任何表——只把已知字段回显到卡片，等用户在卡片上点确认再落库。"
            f"业务字段三项：owner（归属人）、transaction_type（{_TYPE_HINT}）、amount（金额）。"
            "【user_id 必填】填本轮触发这张卡的那个人的匿名标识（上下文 extra 里的 user_1 / user_2）。"
            "A 帮 B 记时 user_id=A 的 user_N，owner 仍是 B。禁止留空、禁止填归属人名/成员 id/元宝。"
            "【建档前置】owner 必须是已建档成员（与跑团同一条）。未建档直接报 "
            "MEMBER_NOT_FOUND，不出卡——先用人话请用户建档，等用户明确同意后再自己建档，"
            "建档完成后再 draft。不要为了出卡自动建档。对用户禁止贴 python / tracker 命令。"
            "已知成员 id 时把它传进 owner_id 更准（客户端回传的 "
            "ownerName.raw.memberId 就是它）。"
            "【缺失字段怎么办】owner 缺省=谁发的记谁名下（「我的」填 extra 群昵称；"
            "替别人记填对方姓名。禁止填 sender_id / user_N，那是本轮匿名号、每轮会变）；"
            "occurred_at 缺省=当天；category / account 判断不出来不要反问，直接留空，"
            "服务端会兜底成 other；merchant / note 可为空。"
            "只有 transaction_type 和 amount 这两项缺失时才要开口问用户——"
            "但仍然要先出卡（把已知字段填上），让用户在卡片上补，别只发一句文字提问。"
            "多笔账（如一次说了三笔消费）请分别调用多次，每次一个独立 card_id。"
            "用户要求纠正某张【还没确认】的卡时：另开一张【新 card_id】的卡承载纠正后的字段，"
            "并把被纠正那张卡的旧 card_id 填到 supersedes。"
            "带 supersedes 时本调用会同时下发：旧卡 update 为已取消 + 新卡 create。"
        ),
        "required": ["user_id"],
        "optional": [
            "card_id", "owner", "owner_id", "occurred_at",
            "transaction_type", "amount", "currency", "category", "account",
            "merchant", "note", "image_url", "quote", "group_id", "today",
            "txn_id", "supersedes",
        ],
        "types": {
            "card_id": "string", "user_id": "string",
            "owner": "string", "owner_id": "string",
            "occurred_at": "string",
            "transaction_type": "string", "amount": "number", "currency": "string",
            "category": "string", "account": "string", "merchant": "string",
            "note": "string", "image_url": "string", "quote": "object",
            "group_id": "string", "today": "string", "txn_id": "string",
            "supersedes": "string",
        },
        "outputPhases": ["bookkeeping_card"],
        "agentAllowed": True,
        "example": {
            "operation": "draft_txn", "user_id": "user_1", "owner": "翘翘",
            "transaction_type": "expense",
            "amount": 38.5, "category": "dining", "account": "wechat",
            "merchant": "麦当劳", "note": "晚饭", "occurred_at": "2026-08-09",
            "today": "2026-08-09",
        },
    },
    "commit_txn": {
        "description": (
            "用户在卡片上点确认后调用：把该卡的记账信息【落库】成一条真实流水。"
            "一卡=一条流水；同一张卡重复确认是幂等的（不会记成两笔）。"
            "落库前必须字段齐全：owner 或 owner_id 二选一 / occurred_at / transaction_type / amount。"
            "【建档前置】归属人必须已建档，未建档直接报 MEMBER_NOT_FOUND——"
            "此时提示用户建档，绝不为了记账自动建档、也不要绕过卡片写库。"
            "优先传 owner_id（客户端回传的 ownerName.raw.memberId）；有 owner_id 时可以不传 owner。"
            "【用户点确认】成功：只 update 那张卡为 confirmed，不出新卡，文案才能说已记账。"
            "失败：update 旧卡为 cancelled + create 一张待确认新卡，然后停手等用户再点确认；"
            "禁止本轮对 new_card_id 再 commit，禁止再说已记账。"
            "【修改已落盘记录】带 txn_id 时为『编辑模式』：不新增，而是用卡片上的最新字段"
            "整体更正那条已存在的流水（txn_id 不变）。txn_id 由 find_txn 查得，"
            "并在 draft_txn 出预填卡片时一路带到 commit。"
            "【卡片状态】四态：pending 待确认 / recording 待录入 / confirmed 已确认 / cancelled 已取消。"
            "待录入是端上点确认到模型回包的中间态，本 op 不吐。"
            "默认落成 confirmed（用户点了确认）。五分钟超时自动结算请传 auto=true："
            "成功只 update 为 confirmed；失败只 update 为 cancelled，不 create、不落库。"
            "【更新目标】卡片挂在历史消息上时必须带 update_seq_id（客户端经 app.env 上报的那条消息 seq_id），"
            "否则客户端不知道去哪条消息里找这张卡。"
        ),
        "required": ["occurred_at", "transaction_type", "amount", "today"],
        "optional": [
            "card_id", "user_id", "owner", "owner_id", "currency", "category", "account",
            "merchant", "note", "image_url", "quote", "group_id", "txn_id",
            "update_seq_id", "auto",
        ],
        "types": {
            "card_id": "string", "user_id": "string",
            "owner": "string", "owner_id": "string",
            "occurred_at": "string",
            "transaction_type": "string", "amount": "number", "currency": "string",
            "category": "string", "account": "string", "merchant": "string",
            "note": "string", "image_url": "string", "quote": "object",
            "group_id": "string", "today": "string", "txn_id": "string",
            "update_seq_id": "string", "auto": "boolean",
        },
        "outputPhases": ["bookkeeping_card"],
        "agentAllowed": True,
        "example": {
            "operation": "commit_txn", "card_id": "card_9a1b2c3d4e", "owner": "翘翘",
            "occurred_at": "2026-08-09", "transaction_type": "expense", "amount": 38.5,
            "category": "dining", "account": "wechat", "merchant": "麦当劳",
            "update_seq_id": "10237", "today": "2026-08-09",
        },
    },
    "cancel_txn": {
        "description": (
            "用户在卡片上点【取消】后调用：把那张待确认卡片打成 cancelled 终态。"
            "不落库、不产生任何流水，也没有 txn_id 可删——这张卡从来没写过库。"
            "必须带 card_id 指明取消哪张卡；卡片挂在历史消息上时把 update_seq_id 一并带上。"
            "【要把卡面字段一起传回来】owner / transaction_type / amount / category / account "
            "等字段虽然是可选的，但取消后那张卡仍要置灰常驻在消息流里——不传的话卡面会变成一片空行。"
            "请把该卡当前显示的字段原样带上。"
        ),
        "required": ["card_id"],
        "optional": [
            "user_id", "owner", "owner_id", "occurred_at", "transaction_type",
            "amount", "currency", "category", "account", "merchant", "note",
            "group_id", "today", "update_seq_id",
        ],
        "types": {
            "card_id": "string", "user_id": "string",
            "owner": "string", "owner_id": "string",
            "occurred_at": "string",
            "transaction_type": "string", "amount": "number", "currency": "string",
            "category": "string", "account": "string", "merchant": "string",
            "note": "string", "group_id": "string", "today": "string",
            "update_seq_id": "string",
        },
        "outputPhases": ["bookkeeping_card"],
        "agentAllowed": True,
        "example": {
            "operation": "cancel_txn", "card_id": "card_9a1b2c3d4e",
            "update_seq_id": "10237", "owner": "翘翘",
        },
    },
    "find_txn": {
        "description": (
            "只读查询已落库的流水（不写库、不出卡）。专供『用户要修改/删除一条已经记过的账』时"
            "定位其 txn_id 与当前字段：查到后用 draft_txn 出一张预填好现有值的编辑卡片"
            "（把 txn_id 一并带上），用户改完点确认，commit_txn（编辑模式）再整体更正。"
            "按 owner / date / month / transaction_type 过滤，至少给一个条件以缩小范围。"
            "也可用来回答『我这个月花了多少』这类统计问题——回包里带 summary。"
            "给了 owner 但这个人没建档时回 member_not_found=true + 空列表，"
            "这跟『这人有档但没记录』不是一回事，回复用户时说法要区分开。"
        ),
        "required": [],
        "optional": ["owner", "owner_id", "date", "month", "transaction_type",
                     "group_id", "today", "limit"],
        "types": {
            "owner": "string", "owner_id": "string", "date": "string",
            "month": "string", "transaction_type": "string", "group_id": "string",
            "today": "string", "limit": "integer",
        },
        "outputPhases": ["bookkeeping_list"],
        "agentAllowed": True,
        "example": {"operation": "find_txn", "owner": "翘翘", "month": "2026-08"},
    },
    "delete_txn": {
        "description": (
            "删除一条【已落库】的流水（软删，不出卡、不改动前端任何已完成的卡片）。"
            "只按 txn_id 删除：先用 find_txn 定位到目标记录的 txn_id 再删。"
            "【何时可直接删】用户指令强硬清晰、明确指向唯一一条（如『删掉我 8/9 那笔麦当劳』）："
            "find_txn 命中唯一一条即可直接 delete_txn。"
            "【何时先确认】指令模糊、或 find_txn 命中多条：把候选列给用户，让其指明删哪条，不要擅自删。"
            "删除后回执带该归属人当月最新收支合计，据此口头反馈。"
        ),
        "required": ["txn_id"],
        "optional": ["reason", "group_id", "today"],
        "types": {
            "txn_id": "string", "reason": "string", "group_id": "string",
            "today": "string",
        },
        "outputPhases": ["bookkeeping_deleted"],
        "agentAllowed": True,
        "example": {"operation": "delete_txn", "txn_id": "翘翘_2026-08-09_01",
                    "reason": "用户要求删除"},
    },
}

# 模型常见的字段名笔误 -> 正确字段名。
FIELD_SUGGESTIONS = {
    "date": "occurred_at",
    "type": "transaction_type",
    "money": "amount",
    "price": "amount",
    "member": "owner",
    "member_id": "owner_id",
    "owner_name": "owner",
    "merchant_name": "merchant",
    "event_id": "txn_id",
    "account_name": "account",
}


def _default_today() -> str:
    """东八区当天日期；模型漏传 today 时兜底，避免 commit_txn 因缺参失败后空口答应。"""
    from datetime import datetime, timedelta, timezone
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")


def normalize_operation_args(operation: str, args: dict[str, Any]) -> dict[str, Any]:
    """校验前归一化常见模型笔误（须在「未知字段」检查之前执行）。"""
    out = dict(args)
    if operation in ("commit_txn", "draft_txn") and not out.get("today"):
        out["today"] = _default_today()
    # 记账日期漏传：默认当天（规则：日期缺失时默认当天）。
    if operation in ("draft_txn", "commit_txn") and not out.get("occurred_at"):
        if out.get("today"):
            out["occurred_at"] = out["today"]
    return out


def describe_contract() -> dict[str, Any]:
    return {
        "app": "bookkeeping_checkin_appskill",
        "invocation": "python3 /data/skills/bookkeeping_checkin_appskill/scripts/_run.py ledger_api '<json>'",
        "describe": "python3 /data/skills/bookkeeping_checkin_appskill/scripts/_run.py describe",
        "enums": {
            "transaction_type": list(TRANSACTION_TYPE_IDS),
            "account": list(ACCOUNT_IDS),
            "category": {tid: list(group) for tid, group in CATEGORIES.items()},
            "currency": list(CURRENCIES),
        },
        "commonError": {
            "fields": {
                "operation": "string", "phase": "error",
                "code": "string", "message": "string",
            }
        },
        "scripts": [{
            "name": "ledger_api",
            "description": "记账台账 App 的唯一 Agent/App CLI。",
            "operations": OPERATIONS,
        }],
    }


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    return False


def _coerce_update_seq_id(value: Any) -> Any:
    """模型偶尔把 update_seq_id 写成数字 2327 而不是 "2327"。
    int / float / 数字字符串一律转成 string，再交给类型检查。
    None / 空串原样返回，由调用方省略，不因此报必须是 string。
    """
    if value is None or value == "":
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value)
    if isinstance(value, str):
        return value
    return value


def _coerce_numeric_string(value: Any, expected: str) -> Any:
    """模型在嵌套 JSON（bash 里套一层 JSON 字符串）里偶尔会把数字字段写成带引号的
    字符串，如 amount="38.5"。这里只做"确实是合法数字"的安全转换，转换失败
    （真正的非数字字符串、bool、list 等）原样返回，交给 _matches_type 正常判失败——
    不放过真正的类型错误，只兜底这一种常见的模型笔误。

    金额还要多剥一层：模型有时会写成 "¥38.5" 或 "38.5元"。
    """
    if expected not in ("number", "integer") or not isinstance(value, str):
        return value
    text = value.strip()
    for ch in ("¥", "￥", "$", "元", "块", "RMB", "rmb", ","):
        text = text.replace(ch, "")
    try:
        coerced = float(text.strip())
    except (TypeError, ValueError):
        return value
    if expected == "integer":
        if not coerced.is_integer():
            return value
        return int(coerced)
    return coerced


# commit_txn 一旦校验失败，模型容易转头去找别的写库路径把账记上——而 assets/tracker.py
# 的 CLI 里确实有 add_txn / correct / delete_txn 这几条能写库的命令（它们是本 API 的内部
# 实现，只供人工排查补录）。落库只允许走卡片确认后的 commit_txn，所以把警告写进报错信息
# 本身，让模型在刚失败、马上要决定下一步时就看到，而不是等它自己去翻 SKILL.md。
_LEDGER_WRITE_OPS = {"commit_txn"}
_BYPASS_WARNING = (
    "（这不是让你转去跑 assets/tracker.py add_txn / correct / delete_txn 把账记上的信号——"
    "确认失败时 skill 会取消旧卡并新出一张待确认卡。请让用户在新卡上补齐后再确认，"
    "绝不要绕过卡片直接写库，也不要对旧卡再 commit，也不要在没落库时宣称已经记上。）"
)


def _raise(operation: str, message: str) -> None:
    if operation in _LEDGER_WRITE_OPS:
        message = f"{message} {_BYPASS_WARNING}"
    raise ContractError(message)


def validate_operation(operation: str, args: dict[str, Any], *, agent_call: bool) -> dict[str, Any]:
    spec = OPERATIONS.get(operation)
    if spec is None:
        raise ContractError(f"不支持的 operation：{operation}")
    if agent_call and not spec["agentAllowed"]:
        raise ContractError(f"Agent 不允许执行 operation：{operation}（该动作仅 App 页面可触发）")
    if not isinstance(args, dict):
        raise ContractError("参数必须是对象")

    args = normalize_operation_args(operation, args)

    allowed = set(spec["required"]) | set(spec["optional"])
    unknown = sorted(set(args) - allowed)
    if unknown:
        messages = []
        for name in unknown:
            known = FIELD_SUGGESTIONS.get(name)
            suggestion = [known] if known in allowed else get_close_matches(
                name, sorted(allowed), n=1, cutoff=0.45)
            messages.append(f"{name} 是否应为 {suggestion[0]}" if suggestion else name)
        _raise(operation, f"不允许字段：{', '.join(messages)}")

    missing = [name for name in spec["required"] if args.get(name) in (None, "", [])]
    if operation == "commit_txn":
        has_owner = args.get("owner") not in (None, "", [])
        has_owner_id = args.get("owner_id") not in (None, "", [])
        if not has_owner and not has_owner_id:
            missing.append("owner")
    if missing:
        _raise(operation, f"缺少参数：{', '.join(missing)}")

    coerced_args = dict(args)
    for name, value in args.items():
        expected = spec["types"].get(name)
        if expected:
            coerced_args[name] = _coerce_numeric_string(value, expected)

    if "update_seq_id" in coerced_args:
        coerced = _coerce_update_seq_id(coerced_args["update_seq_id"])
        if coerced in (None, ""):
            coerced_args.pop("update_seq_id", None)
        else:
            coerced_args["update_seq_id"] = coerced

    for name, value in coerced_args.items():
        expected = spec["types"].get(name)
        if expected and not _matches_type(value, expected):
            _raise(operation, f"{name} 必须是 {expected}")
    return coerced_args
