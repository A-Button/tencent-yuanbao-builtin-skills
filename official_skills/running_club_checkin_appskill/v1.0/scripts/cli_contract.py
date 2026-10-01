"""跑团打卡台账 App 的机器可读 contract（operation / 字段 / 可见性）。

visibility / agentAllowed 语义：
  - agentAllowed=True  → 模型（Agent）可通过 _run.py ledger_api 调用（draft_checkin / commit_checkin）
  - agentAllowed=False → 仅 App 页面可通过 tools/call → POST /app/call 直调（跳过模型）

打卡卡片流是唯一链路：draft_checkin 出可编辑草稿卡（不落库），用户在卡片上点确认后
才 commit_checkin 落库。已下线旧台账 operation（list_ledger / ingest_image / attribute /
set_redeem_rules / redeem / delete_ledger）——模型无任何直接写 checkin 的入口。
"""

from __future__ import annotations

from difflib import get_close_matches
from typing import Any

class ContractError(ValueError):
    pass


# display_mode（可选，"widget"|"card"）：由 _run.py 读取，决定本次结果挂载哪个 UI 资源
# （ui://running_club_checkin_appskill/ledger 或 .../card）；对 ledger_api 本身的业务逻辑无影响。
OPERATIONS: dict[str, dict[str, Any]] = {
    "draft_checkin": {
        "description": (
            "识别到打卡语义后，出一张【可编辑打卡草稿卡片】（信息有啥放啥，允许不全）。"
            "不落库、不写任何表——只把已知字段回显到卡片，等用户在卡片上点确认再落库。"
            "【user_id 必填】填本轮触发这张卡的那个人的匿名标识（上下文 extra 里的 user_1 / user_2）。"
            "A 替 B 打卡时 user_id=A 的 user_N，member 仍是 B。禁止留空、禁止填成员名/成员 id/元宝。"
            "多条待打卡记录请分别调用多次，每次一个独立 card_id；"
            "每张卡须单独一次 bash（command 里只能有一行 _run.py），禁止在同一条 bash 里串多个 draft_checkin。"
            "member 按语序填：说明文字管它前面最近的图；一条消息多图+「我的」=整组都是发送人。"
            "「我的」填 extra 的群昵称；「evan的」填 evan。禁止填 sender_id / user_N（每轮会变）。"
            "不要把附件 2 匀给另一个人来凑人数。对象没定的记录先问、先不要 draft。"
            "quote 是该卡引用的『那条带图/打卡消息』：优先引用图片那条消息，带上其 seq_id（供前端点击跳转）、"
            "image_url，text 用 [图片] 这类占位而非 @元宝 原句；draft 时固化、随卡不变。"
            "用户要求纠正某张【还没确认】的卡时：另开一张【新 card_id】的卡片承载纠正后的字段，"
            "并把被纠正那张卡的旧 card_id 填到 supersedes。"
            "带 supersedes 时本调用会同时下发：旧卡 update 为已取消 + 新卡 create。"
        ),
        "required": ["user_id"],
        "optional": [
            "card_id", "member", "member_id", "subject", "distance_raw",
            "distance_km", "unit", "activity_type", "occurred_at", "duration_seconds",
            "img_id", "note", "quote", "location", "group_id", "today",
            "display_mode", "event_id", "supersedes",
        ],
        "types": {
            "member_id": "string", "subject": "string", "user_id": "string",
            "card_id": "string", "member": "string", "distance_raw": "number",
            "distance_km": "number", "unit": "string", "activity_type": "string",
            "occurred_at": "string", "duration_seconds": "integer",
            "img_id": "string", "note": "string", "quote": "object", "location": "string",
            "group_id": "string", "today": "string",
            "display_mode": "string", "event_id": "string", "supersedes": "string",
        },
        "outputPhases": ["checkin_card"],
        "agentAllowed": True,
        "example": {
            "operation": "draft_checkin", "user_id": "user_1", "member": "谢飞桐",
            "distance_raw": 5, "unit": "km",
            "activity_type": "outdoor_run", "occurred_at": "2026-08-05",
            "img_id": "40c6222367a53fad8a543496e2f91611",
            "quote": {"seq_id": "12", "sender": "谢飞桐", "text": "[图片]", "image_url": "https://image_1"},
            "today": "2026-08-05",
        },
    },
    "commit_checkin": {
        "description": (
            "用户在卡片上点确认后调用：把该卡的打卡信息【落库】成一条真实 checkin（封装 tracker add_checkin，"
            "一条命令原子落库）。member 必须已建档（未建档先在群里建档，勿在此自动建档）。"
            "一卡=一条 checkin。落库前请确保最小字段齐全：member / occurred_at / activity_type / "
            "distance_raw / duration_seconds（配速由时长+距离自动算出；60+ age_exempt 成员可缺时长）。"
            "跑步类配速不合理"
            "（>10'00\"/km 或 <2'00\"/km）会直接拒绝落库，不会写入 valid=0 的脏行。"
            "禁止只传 card_id：脚本读不到「卡片当前数据如下」/ app.env，必须把快照译成上述英文字段一并传入。"
            "快照里某字段为（空）时禁止从历史/draft/card_id 补填，照缺参传入由 skill 走失败协议。"
            "【修改已落盘记录】带 event_id 时为『编辑模式』：不新增，而是用卡片上的最新字段整体更正那条已存在的 "
            "checkin（同一条 ledger_api 调用内原子完成，event_id 不变、引用不变）。event_id 由 find_checkin 查得，"
            "并在 draft_checkin 出预填卡片时一路带到 commit。"
            "【卡片状态】四态：pending 待确认 / recording 待录入 / confirmed 已确认 / cancelled 已取消。"
            "待录入是端上点确认到模型回包的中间态，本 op 不吐。"
            "默认落成 confirmed（用户点了确认）。用户点确认失败：update 旧卡 cancelled + create 待确认新卡。"
            "五分钟超时自动结算请传 auto=true：成功只 update 为 confirmed；失败只 update 为 cancelled，不 create、不落库。"
            "【更新目标】卡片挂在历史消息上时必须带 update_seq_id（客户端经 app.env 上报的那条消息 seq_id），"
            "否则客户端不知道去哪条消息里找这张卡。"
        ),
        "required": ["member", "occurred_at", "activity_type", "distance_raw", "today"],
        "optional": [
            "card_id", "user_id", "member_id", "subject", "distance_km", "unit",
            "duration_seconds",
            "img_id", "note", "quote", "location", "group_id",
            "display_mode", "event_id", "update_seq_id", "auto",
        ],
        "types": {
            "member_id": "string", "subject": "string", "user_id": "string",
            "card_id": "string", "member": "string", "occurred_at": "string",
            "activity_type": "string", "distance_raw": "number", "distance_km": "number",
            "unit": "string", "duration_seconds": "integer",
            "img_id": "string", "note": "string", "quote": "object", "location": "string",
            "today": "string", "group_id": "string",
            "display_mode": "string", "event_id": "string",
            "update_seq_id": "string", "auto": "boolean",
        },
        "outputPhases": ["checkin_card"],
        "agentAllowed": True,
        "example": {
            "operation": "commit_checkin", "member": "谢飞桐", "occurred_at": "2026-08-05",
            "activity_type": "outdoor_run", "distance_raw": 5, "unit": "km",
            "duration_seconds": 1800, "img_id": "40c6222367a53fad8a543496e2f91611", "today": "2026-08-05",
        },
    },
    "cancel_checkin": {
        "description": (
            "用户在卡片上点【取消】后调用：把那张待确认卡片打成 cancelled 终态。"
            "不落库、不产生任何 checkin，也没有 event_id 可删——这张卡从来没写过库。"
            "必须带 card_id 指明取消哪张卡；卡片挂在历史消息上时把 update_seq_id 一并带上。"
        ),
        "required": ["card_id"],
        "optional": [
            "user_id", "member", "member_id", "subject", "distance_raw", "unit",
            "activity_type", "occurred_at", "duration_seconds", "location", "group_id",
            "today", "update_seq_id",
        ],
        "types": {
            "card_id": "string", "member": "string", "distance_raw": "number",
            "member_id": "string", "subject": "string", "user_id": "string",
            "unit": "string", "activity_type": "string", "occurred_at": "string",
            "duration_seconds": "integer", "location": "string",
            "group_id": "string", "today": "string", "update_seq_id": "string",
        },
        "outputPhases": ["checkin_card"],
        "agentAllowed": True,
        "example": {
            "operation": "cancel_checkin", "card_id": "card_7f3a91c2",
            "update_seq_id": "10237", "member": "谢飞桐",
        },
    },
    "find_checkin": {
        "description": (
            "只读查询已落库的打卡记录（不写库、不出卡）。专供『用户要修改一条已经录入的打卡』时定位其 event_id "
            "与当前字段：查到后用 draft_checkin 出一张预填好现有值的编辑卡片（把 event_id 一并带上），"
            "用户在卡片上改完点确认，commit_checkin（编辑模式）再整体更正那条记录。"
            "按 member / period / date 过滤，至少给一个过滤条件以缩小范围。"
        ),
        "required": [],
        "optional": ["member", "period", "date", "group_id", "today"],
        "types": {
            "member": "string", "period": "integer", "date": "string",
            "group_id": "string", "today": "string",
        },
        "outputPhases": ["checkin_list"],
        "agentAllowed": True,
        "example": {"operation": "find_checkin", "member": "谢飞桐", "date": "2026-08-05"},
    },
    "delete_checkin": {
        "description": (
            "删除一条【已落库】的打卡记录（软删，不出卡、不改动前端任何已完成的卡片）。"
            "只按 event_id 删除：先用 find_checkin 定位到目标记录的 event_id 再删。"
            "【何时可直接删】用户指令强硬清晰、明确指向唯一一条（如『删掉 cloe 8/4 那条 10 公里』）：find_checkin 命中唯一一条即可直接 delete_checkin。"
            "【何时先确认】指令模糊、或 find_checkin 命中多条：把候选列给用户，让其指明删哪条，不要擅自删。"
            "删除后回执含该成员当前期次最新有效累计（period_total / qualified / shortage_km），据此口头反馈『删完当期还剩多少 / 是否仍达标』。"
        ),
        "required": ["event_id"],
        "optional": ["reason", "group_id", "today"],
        "types": {
            "event_id": "string", "reason": "string",
            "group_id": "string", "today": "string",
        },
        "outputPhases": ["checkin_deleted"],
        "agentAllowed": True,
        "example": {"operation": "delete_checkin", "event_id": "谢飞桐_2026-08-04_01",
                    "reason": "用户要求删除"},
    },
}

FIELD_SUGGESTIONS = {
    "member_id": "member",
    "date": "today",
    "distance": "distance_raw",
}


def _default_today() -> str:
    """东八区当天日期；模型漏传 today 时兜底，避免 commit_checkin 因缺参失败后空口答应。"""
    from datetime import datetime, timedelta, timezone
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")


def normalize_operation_args(operation: str, args: dict[str, Any]) -> dict[str, Any]:
    """校验前归一化常见模型笔误（须在「未知字段」检查之前执行）。"""
    out = dict(args)
    # commit_checkin 漏 today：用东八区当天兜底
    if operation == "commit_checkin" and not out.get("today"):
        out["today"] = _default_today()
    # 卡片语义：distance_km 是 distance_raw 的常见别名笔误
    if operation in ("draft_checkin", "commit_checkin"):
        if out.get("distance_raw") in (None, "") and out.get("distance_km") not in (None, ""):
            out["distance_raw"] = out["distance_km"]
    return out


def describe_contract() -> dict[str, Any]:
    return {
        "app": "running_club_checkin_appskill",
        "invocation": "python3 /data/skills/running_club_checkin_appskill/scripts/_run.py ledger_api '<json>'",
        "describe": "python3 /data/skills/running_club_checkin_appskill/scripts/_run.py describe",
        "commonError": {
            "fields": {
                "operation": "string", "phase": "error",
                "code": "string", "message": "string",
            }
        },
        "scripts": [{
            "name": "ledger_api",
            "description": "跑团打卡台账 App 的唯一 Agent/App CLI。",
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
    字符串，如 distance_raw="2.01"。这里只做"确实是合法数字"的安全转换，转换失败
    （真正的非数字字符串、bool、list 等）原样返回，交给 _matches_type 正常判失败——
    不放过真正的类型错误，只兜底这一种常见的模型笔误，避免逼model走绕过 ledger_api
    的错误路径。"""
    if expected not in ("number", "integer") or not isinstance(value, str):
        return value
    try:
        coerced = float(value.strip())
    except (TypeError, ValueError):
        return value
    if expected == "integer":
        if not coerced.is_integer():
            return value
        return int(coerced)
    return coerced


# commit_checkin 一旦校验失败，模型历史上反复出现"放弃重试、转头直接调
# assets/tracker.py add_checkin 把账记上"的绕开行为——SKILL.md 里的规则是一段
# 埋在几万 token 上下文里的文字，抵不过报错那一刻的即时冲动。把警告直接写进报错
# 信息本身，让模型在刚失败、马上要决定下一步时就看到。落库只允许走卡片确认后的
# commit_checkin，任何情况下都不得直接调用 add_checkin/backfill 等写库命令。
_LEDGER_WRITE_OPS = {"commit_checkin"}
_BYPASS_WARNING = (
    "（这不是让你转去直接调用 assets/tracker.py add_checkin 把账记上的信号——"
    "确认失败时 skill 会取消旧卡并新出一张待确认卡。请让用户在新卡上补齐后再确认，"
    "绝不要绕过卡片直接写库，也不要对旧卡再 commit。）"
)


def _raise(operation: str, message: str) -> None:
    if operation in _LEDGER_WRITE_OPS:
        message = f"{message} {_BYPASS_WARNING}"
    raise ContractError(message)


def audit_operation_specs() -> list[str]:
    """开发/测试用：types 里声明的每个字段都必须在 required 或 optional 中。"""
    issues: list[str] = []
    for op, spec in OPERATIONS.items():
        allowed = set(spec.get("required") or []) | set(spec.get("optional") or [])
        for name in spec.get("types") or {}:
            if name not in allowed:
                issues.append(f"{op}: types 含 {name!r}，但未列入 required/optional")
    return issues


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
            suggestion = [known] if known in allowed else get_close_matches(name, sorted(allowed), n=1, cutoff=0.45)
            messages.append(f"{name} 是否应为 {suggestion[0]}" if suggestion else name)
        _raise(operation, f"不允许字段：{', '.join(messages)}")

    missing = [name for name in spec["required"] if args.get(name) in (None, "", [])]
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
