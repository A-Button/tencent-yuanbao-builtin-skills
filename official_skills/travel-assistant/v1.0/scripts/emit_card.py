#!/usr/bin/env python3
"""校验 show_widget 入参。线格式按 make-things 的扁平协议。"""

from __future__ import annotations

import json
import re
from typing import Any

# 两个发行包仅此配置不同，其余脚本保持一致：
#   legacy  —— show_widget 现行入参：字符串 card_type、扁平 data、camelCase thingId/todoId
#   nowcard —— 后台 NowCard 线格式：int card_type、具名正文子对象、snake_case 三个 id
CARD_FORMAT = "legacy"

CARD_TYPES = ("image_text", "recommend_list", "todo_remind", "todo_choice")
CARD_TYPE_CODES = {"image_text": 1, "recommend_list": 2, "todo_remind": 3, "todo_choice": 4}
CODE_TO_CARD_TYPE = {code: name for name, code in CARD_TYPE_CODES.items()}
LEGACY_ID_FIELDS = ("thingId", "todoId")
NOWCARD_ID_FIELDS = ("conversation_id", "thing_id", "todo_id")
MAX_CARD_BYTES = 64_000
ITEM_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,96}$")
CONFIRM_LABEL_RE = re.compile(r"确认|开始")
HTTPS_RE = re.compile(r"^https://", re.I)


class CardError(Exception):
    def __init__(self, rule: str, message: str) -> None:
        super().__init__(message)
        self.rule = rule
        self.message = message

    def as_dict(self) -> dict[str, Any]:
        return {"ok": False, "rule": self.rule, "message": self.message}


def _text(value: object, field: str, *, required: bool = False) -> str:
    if value is None or value == "":
        if required:
            raise CardError("REQUIRED_FIELD", f"缺少必填字段 {field}")
        return ""
    if not isinstance(value, str) or not value.strip():
        raise CardError("INVALID_FIELD", f"{field} 必须是非空字符串")
    return value.strip()


def _object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CardError("INVALID_FIELD", f"{field} 必须是对象")
    return value


def _int(value: object, field: str, allowed: set[int]) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CardError("INVALID_ENUM", f"{field} 必须是整数 {sorted(allowed)}")
    if value not in allowed:
        raise CardError("INVALID_ENUM", f"{field} 必须是 {sorted(allowed)} 之一")
    return value


def _https(value: object, field: str) -> str:
    url = _text(value, field, required=True)
    if not HTTPS_RE.match(url):
        raise CardError("HTTPS_URL", f"{field} 必须是可访问的 HTTPS 地址")
    return url


def _item_id(value: object, field: str) -> str:
    text = _text(value, field, required=True)
    if not ITEM_ID_RE.fullmatch(text):
        raise CardError("INVALID_ID", f"{field} 只能是 1–96 位字母、数字、下划线或连字符")
    return text


def _validate_tap(tap: object, field: str, *, choice_confirm: bool = False) -> None:
    if tap is None:
        return
    data = _object(tap, field)
    tap_type = data.get("type")
    if tap_type == "image_preview" or tap_type == 4:
        raise CardError("IMAGE_PREVIEW_FORBIDDEN", "一期不要下发 image_preview")
    if tap_type == 1:
        chat = _object(data.get("agent_chat"), f"{field}.agent_chat")
        # 空对象只打开原会话；选择确认按钮仍在下方强制要求 send_prompt。
        if "send_prompt" in chat:
            _text(chat["send_prompt"], f"{field}.agent_chat.send_prompt", required=True)
        # 协议 §2.2：将关联 ID 放在卡片根节点。
        chat_extra = set(chat) - {"send_prompt"}
        if chat_extra:
            raise CardError(
                "TAP_MIXED",
                f"{field}.agent_chat 只能有 send_prompt，多了 {sorted(chat_extra)}；"
                "请将会话 ID 放在卡片根节点，不要放入 tap",
            )
        extra = set(data) - {"type", "agent_chat"}
        if extra:
            raise CardError("TAP_MIXED", f"{field} type=1 只能带 agent_chat，多了 {sorted(extra)}")
    elif tap_type == 2:
        page = _object(data.get("h5"), f"{field}.h5")
        _https(page.get("url"), f"{field}.h5.url")
        extra = set(data) - {"type", "h5"}
        if extra:
            raise CardError("TAP_MIXED", f"{field} type=2 只能带 h5，多了 {sorted(extra)}")
    elif tap_type == 3:
        mini_program = _object(data.get("mini_program"), f"{field}.mini_program")
        name = _text(
            mini_program.get("name"),
            f"{field}.mini_program.name",
            required=True,
        )
        if not name.startswith("gh_"):
            raise CardError(
                "MINI_PROGRAM_GH_ID",
                f"{field}.mini_program.name 必须是 gh_ 原始 id，不能填 AppID",
            )
        if mini_program.get("path") not in (None, ""):
            _text(mini_program.get("path"), f"{field}.mini_program.path")
        _int(
            mini_program.get("mp_type", 0),
            f"{field}.mini_program.mp_type",
            {0, 1, 2},
        )
        extra = set(data) - {"type", "mini_program"}
        if extra:
            raise CardError("TAP_MIXED", f"{field} type=3 只能带 mini_program，多了 {sorted(extra)}")
    else:
        raise CardError(
            "UNKNOWN_TAP",
            f"{field}.type 只能是 1（agent_chat）、2（h5）或 3（mini_program）",
        )
    if choice_confirm:
        if tap_type != 1:
            raise CardError(
                "CHOICE_CONFIRM_TARGET",
                f"{field} 是选择确认按钮，必须用 type=1 把选择结果发回会话",
            )
        prompt = _text(
            (_object(data.get("agent_chat"), f"{field}.agent_chat")).get("send_prompt"),
            f"{field}.agent_chat.send_prompt",
            required=True,
        )
        if not prompt.endswith(("：", ":")):
            raise CardError(
                "CHOICE_PROMPT_PREFIX",
                f"{field}.agent_chat.send_prompt 必须是以冒号收尾的前缀",
            )


def _validate_actions(actions: object, *, card_type: str) -> None:
    if actions is None:
        return
    if not isinstance(actions, list) or not actions:
        raise CardError("INVALID_FIELD", "actions 必须是非空数组")
    if len(actions) > 2:
        raise CardError("ITEM_COUNT", f"actions 最多 2 个，实际 {len(actions)} 个")
    seen: set[str] = set()
    for index, item in enumerate(actions):
        prefix = f"actions[{index}]"
        row = _object(item, prefix)
        action_id = _text(row.get("action_id"), f"{prefix}.action_id", required=True)
        if action_id in seen:
            raise CardError("DUPLICATE_ID", f"actions.action_id 重复：{action_id}")
        seen.add(action_id)
        label = _text(row.get("label"), f"{prefix}.label", required=True)
        confirm = card_type == "todo_choice" and bool(CONFIRM_LABEL_RE.search(label))
        if row.get("tap") is None:
            raise CardError("REQUIRED_FIELD", f"{prefix}.tap 必填")
        _validate_tap(row.get("tap"), f"{prefix}.tap", choice_confirm=confirm)


def _validate_items(
    items: object,
    *,
    field: str,
    min_n: int,
    max_n: int,
    id_key: str,
    allowed: set[str],
) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        raise CardError("REQUIRED_FIELD", f"{field} 必须是数组")
    if not (min_n <= len(items) <= max_n):
        raise CardError("ITEM_COUNT", f"{field} 需要 {min_n}–{max_n} 条，实际 {len(items)} 条")
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        prefix = f"{field}[{index}]"
        row = _object(item, prefix)
        item_id = _item_id(row.get(id_key), f"{prefix}.{id_key}")
        if item_id in seen:
            raise CardError("DUPLICATE_ID", f"{field} 的 {id_key} 重复：{item_id}")
        seen.add(item_id)
        _text(row.get("title"), f"{prefix}.title", required=True)
        # 拒绝端上会忽略的额外字段；todo_remind 的 item 不支持单独点击（§2.1）。
        extra = set(row) - allowed
        if extra:
            raise CardError("DATA_SHAPE", f"{prefix} 不支持 {sorted(extra)}；可用字段：{sorted(allowed)}")
        rows.append(row)
    return rows


def _validate_data(card_type: str, data: dict[str, Any], body_key: str = "data") -> None:
    if card_type == "image_text":
        extra = set(data) - {"cover"}
        if extra:
            raise CardError("DATA_SHAPE", f"{body_key} 只能有 cover，多了 {sorted(extra)}")
        cover = data.get("cover")
        if cover is not None:
            cover_obj = _object(cover, f"{body_key}.cover")
            _https(cover_obj.get("url"), f"{body_key}.cover.url")
            if set(cover_obj) - {"url"}:
                raise CardError("DATA_SHAPE", f"{body_key}.cover 只传 url，不要传 width/height")
        return

    if card_type == "recommend_list":
        items = _validate_items(data.get("items"), field=f"{body_key}.items", min_n=3, max_n=5,
                                id_key="item_id", allowed={"item_id", "title", "desc", "image", "tap"})
        extra = set(data) - {"items"}
        if extra:
            raise CardError("DATA_SHAPE", f"{body_key} 只能有 items，多了 {sorted(extra)}")
        for index, item in enumerate(items):
            if item.get("image") not in (None, ""):
                _https(item.get("image"), f"{body_key}.items[{index}].image")
            _validate_tap(item.get("tap"), f"{body_key}.items[{index}].tap")
        return

    if card_type == "todo_remind":
        items = _validate_items(data.get("items"), field=f"{body_key}.items", min_n=1, max_n=20,
                                id_key="item_id", allowed={"item_id", "title", "desc", "badge"})
        extra = set(data) - {"items", "footnote"}
        if extra:
            raise CardError("DATA_SHAPE", f"{body_key} 只能有 items/footnote，多了 {sorted(extra)}")
        if data.get("footnote") not in (None, ""):
            _text(data.get("footnote"), f"{body_key}.footnote")
        for index, item in enumerate(items):
            badge = item.get("badge")
            if badge is None:
                continue
            badge_obj = _object(badge, f"{body_key}.items[{index}].badge")
            _text(badge_obj.get("text"), f"{body_key}.items[{index}].badge.text", required=True)
            # 协议文档列出 1 蓝 / 2 橙；线上也接受 tone=0，并按未指定样式渲染。
            _int(badge_obj.get("tone"), f"{body_key}.items[{index}].badge.tone", {0, 1, 2})
        return

    extra = set(data) - {"select_mode", "options"}
    if extra:
        raise CardError("DATA_SHAPE", f"{body_key} 只能有 select_mode/options，多了 {sorted(extra)}")
    mode = _int(data.get("select_mode"), f"{body_key}.select_mode", {1, 2})
    options = _validate_items(data.get("options"), field=f"{body_key}.options", min_n=1, max_n=20,
                              id_key="option_id",
                              allowed={"option_id", "title", "desc", "image", "selected", "done"})
    selected = [row for row in options if row.get("selected") and not row.get("done")]
    if mode == 1 and len(selected) > 1:
        raise CardError("SELECT_MODE", "select_mode=1 最多预选一项未完成选项")
    for index, row in enumerate(options):
        if row.get("done") and row.get("selected"):
            raise CardError("SELECT_MODE", f"{body_key}.options[{index}] 已完成项不能同时 selected")
        if row.get("image") not in (None, ""):
            _https(row.get("image"), f"{body_key}.options[{index}].image")


def _resolve_card_type(data: dict[str, Any]) -> str:
    """将两种线格式的 card_type 归一化为内部名称。"""
    raw = data.get("card_type")
    if CARD_FORMAT == "nowcard":
        if raw == 5:
            raise CardError("UNKNOWN_CARD_TYPE", "出行助手不支持 stock（card_type=5）")
        code = _int(raw, "card_type", set(CODE_TO_CARD_TYPE))
        return CODE_TO_CARD_TYPE[code]
    if raw == "stock":
        raise CardError("UNKNOWN_CARD_TYPE", "出行助手不支持 stock")
    card_type = _text(raw, "card_type", required=True)
    if card_type not in CARD_TYPES:
        raise CardError("UNKNOWN_CARD_TYPE", f"card_type 只能是 {', '.join(CARD_TYPES)}")
    return card_type


def validate_card(payload: object) -> dict[str, Any]:
    data = _object(payload, "card")
    card_type = _resolve_card_type(data)
    _text(data.get("title"), "title", required=True)
    # legacy 正文位于扁平 data 中；nowcard 正文位于与 card_type 同名的子对象中。
    body_key = "data" if CARD_FORMAT == "legacy" else card_type
    body = _object(data.get(body_key), body_key)
    if data.get("source") is not None:
        source = _object(data.get("source"), "source")
        _text(source.get("label"), "source.label", required=True)
        # 协议 §2.2：来源行仅包含文案；端上固定绘制会话图标，不下发 icon。
        source_extra = set(source) - {"label"}
        if source_extra:
            raise CardError("DATA_SHAPE", f"source 只能有 label，多了 {sorted(source_extra)}")
    if data.get("summary") not in (None, ""):
        _text(data.get("summary"), "summary")
    _validate_tap(data.get("tap"), "tap")
    _validate_actions(data.get("actions"), card_type=card_type)
    id_fields = LEGACY_ID_FIELDS if CARD_FORMAT == "legacy" else NOWCARD_ID_FIELDS
    values = {}
    for field in id_fields:
        values[field] = _text(data.get(field), field) if data.get(field) not in (None, "") else ""
    thing_field, todo_field = id_fields[-2], id_fields[-1]
    if values[todo_field] and not values[thing_field]:
        raise CardError("THING_TODO_PAIR", f"传 {todo_field} 时必须同时传真实 {thing_field}")

    extra = set(data) - {"card_type", "title", body_key, "source", "summary", "actions", "tap", *id_fields}
    if extra:
        raise CardError("DATA_SHAPE", f"卡片顶层不要传 {sorted(extra)}；公共字段不要放进正文")
    _validate_data(card_type, body, body_key)
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_CARD_BYTES:
        raise CardError("CARD_TOO_LARGE", f"卡片 {len(encoded)} 字节，超过 {MAX_CARD_BYTES} 上限")
    return data


def _tap_warnings(card_type: str, data: dict[str, Any], body: dict[str, Any]) -> list[str]:
    """整卡和推荐项同时可点时，仅提示点击目标不一致的组合。"""
    if card_type != "recommend_list" or data.get("tap") is None:
        return []
    items = body.get("items")
    if not isinstance(items, list):
        return []
    item_taps = [row.get("tap") for row in items if isinstance(row, dict) and row.get("tap") is not None]
    tapped = len(item_taps)
    if tapped == 0:
        return []
    if all(item_tap == data["tap"] for item_tap in item_taps):
        return []
    return [
        f"recommend_list 有 {tapped}/{len(items)} 行各自可点，却又配了整卡 tap："
        "点留白会落到和点行不同的地方。把整卡落地改成 actions 里一个带文案的按钮"
        "（如「看完整安排」），并删掉顶层 tap。"
    ]


def emit_card(card: object) -> dict[str, Any]:
    payload = validate_card(card)
    card_type = _resolve_card_type(payload)
    body_key = "data" if CARD_FORMAT == "legacy" else card_type
    result = {
        "ok": True,
        "card": payload,
        "nextAction": "show_widget",
        "note": "校验通过。用 make-things 的 show_widget 原样提交 card，只有返回 now_id 才算发布成功。",
    }
    warnings = _tap_warnings(card_type, payload, payload.get(body_key) or {})
    if warnings:
        result["warnings"] = warnings
    return result


def main() -> int:
    raw = __import__("sys").argv[1] if len(__import__("sys").argv) > 1 else "{}"
    try:
        payload = json.loads(raw)
        card = payload.get("card") if isinstance(payload, dict) and "card" in payload else payload
        print(json.dumps(emit_card(card), ensure_ascii=False, separators=(",", ":")))
        return 0
    except json.JSONDecodeError:
        print(json.dumps(
            {"ok": False, "rule": "INVALID_JSON", "message": "参数不是合法 JSON"},
            ensure_ascii=False,
            separators=(",", ":"),
        ))
        return 0
    except CardError as exc:
        print(json.dumps(exc.as_dict(), ensure_ascii=False, separators=(",", ":")))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
