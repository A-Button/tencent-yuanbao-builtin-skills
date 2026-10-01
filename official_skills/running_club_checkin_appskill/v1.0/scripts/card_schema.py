#!/usr/bin/env python3
"""打卡卡片的 card_data 构造与回读（schemaVersion 2）。

card_data 是**渲染契约**：客户端不认识"跑团打卡"这个业务，卡面上有几行、
每行什么 label、用什么控件、能不能编辑、配速依赖哪几个字段，全部由这里下发。
信封（structuredContent）只留服务端和模型要用的路由与状态——card_id /
operate_type / status / expire_at；改旧卡再加 update_seq_id。

两个方向都在这个模块里，保证下发与回读用的是同一套 fieldId：
  build_card_data   业务字段 -> schema 树（下行）
  field_raw         schema 树 -> 某个 fieldId 的原值（回读 app.env.ui_snapshot）

value 双写 raw + displayText 是有意的：编辑态要结构化值做双向绑定和校验，
展示态要成品文本。两者同源生成，客户端不做换算。
"""

from __future__ import annotations

import copy
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

SCHEMA_VERSION = 2
CARD_TYPE = "run_group_check_in"

# card_data.status 下发整数给渲染器；信封 structuredContent.status 仍是字符串，
# 服务端、模型和落库都读信封那一份。两份语义一致、表示不同。
# 技能下发三态：0 待确认 / 1 已确认 / 2 已取消。
# 待录入（recording=3）是端上点确认到模型回包的中间态，skill 不吐。
STATUS_CODES = {
    "pending": 0,      # 待确认
    "confirmed": 1,    # 已确认
    "cancelled": 2,    # 已取消
    "recording": 3,    # 待录入（端上中间态，skill 不吐）
}

FOOTER_TEXT = "元宝辅助识别，仅供参考"
ICON_TOKEN = "check_in"
CARD_NAME = "运动打卡"

# card_data 下面还有一层 cardPayload，是客户端那边的既有结构，逐字保留：
#   card_data = {cardId, cardType, cardName, cardPayload: {schemaVersion, presentation, sections}, status, actions}
# 卡面结构在内层，卡片身份与状态在外层。
INNER_KEY = "cardPayload"

# semanticCode 用内部 activity_type 取值，客户端拿它做归一化和统计；
# raw/displayText 给中文项目名，用户在编辑面板里改的就是这个自由文本。
ACTIVITY_LABELS = {
    "outdoor_run": "室外跑步",
    "treadmill": "跑步机",
    "indoor_run": "室内跑步",
    "swim": "游泳",
    "walk": "健走",
}

# 仅待确认有动作：编辑在右上角图标位，取消/确认在底部。
# 待录入 / 已确认 / 已取消一律空数组，Footer 不出。
PENDING_ACTIONS = [
    {
        "actionId": "edit",
        "text": "编辑",
        "placements": ["header_icon"],
        "style": "icon",
        "visible": True,
        "enabled": True,
    },
    {
        "actionId": "cancel",
        "text": "取消",
        "placements": ["footer_secondary"],
        "style": "secondary",
        "visible": True,
        "enabled": True,
    },
    {
        "actionId": "confirm",
        "text": "确认",
        "placements": ["footer_primary"],
        "style": "primary",
        "visible": True,
        "enabled": True,
    },
]

DISTANCE_UNITS = [{"id": "km", "label": "km"}, {"id": "m", "label": "m"}]

# 派生字段算不出来时的占位文案。服务端预填必须和客户端自算同源：客户端在
# 条件为假或输入缺失时回落到 resultConfig.emptyDisplayText，我们下发空串就会
# 出现「首次渲染是空、用户一编辑就变成 --」的跳变。两处共用这一个常量。
DERIVED_EMPTY_TEXT = "--"

# 派生结果的舍入位数，必须和各自 expression 里的 round.scale 一致：
# 配速取整到秒，折算跑步保留两位。预填值也按同样的位数和 half_up 舍入，
# 否则客户端一重算就跟服务端给的数对不上（例：1333m 泳，5.332 vs 5.33）。
PACE_SCALE = 0
SWIM_EQUIV_SCALE = 2

# 配速的客户端自算规则：用户在卡上改了时长或距离，这一行不等下一轮模型回包就地重算。
# 表达式走 safe_ast（客户端只认这套白名单算子，不 eval），语义是
# round_half_up(duration[s] / distance[归一到 km])，结果按 5’13”/km 渲染。
# 距离声明 measurementType=length + normalizeToUnit=km，用户把单位切成 m 也算得对。
#
# 所有项目同一条公式，游泳也不例外：配速是「每公里游多久」，除的是真实游程。
# ×4 的代跑折算只属于下面 runningEquivalentDistance 那一行。
PACE_DERIVED = {
    "engine": "safe_ast",
    "astVersion": 1,
    "formulaId": "duration_seconds_div_distance_km_v1",
    "output": "pace_seconds_per_km",
    "inputFieldIds": ["duration", "distance"],
    "expression": {
        "op": "round",
        "mode": "half_up",
        "scale": 0,
        "value": {
            "op": "divide",
            "left": {
                "op": "field_number",
                "fieldId": "duration",
                "requiredUnit": "s",
            },
            "right": {
                "op": "field_number",
                "fieldId": "distance",
                "measurementType": "length",
                "normalizeToUnit": "km",
            },
        },
    },
    "resultConfig": {
        "unit": "s/km",
        "formatter": {"type": "minutes_seconds_per_km"},
        "emptyDisplayText": DERIVED_EMPTY_TEXT,
    },
}
PACE_DERIVED["expression"]["scale"] = PACE_SCALE

def _build_equiv_derived(factor: float, activity_type: str) -> dict[str, Any]:
    """代跑折算行的 derived AST；factor 来自 rules.equivalent_factor（与 effective_km 同源）。"""
    return {
        "engine": "safe_ast",
        "astVersion": 1,
        "formulaId": f"activity_distance_times_factor_{activity_type}_v1",
        "output": "equivalent_running_distance",
        "inputFieldIds": ["sportName", "distance"],
        "when": {
            "op": "equals",
            "left": {
                "op": "field_text",
                "fieldId": "sportName",
                "path": "value.semanticCode",
            },
            "right": {"op": "literal", "value": activity_type},
        },
        "expression": {
            "op": "round",
            "mode": "half_up",
            "scale": SWIM_EQUIV_SCALE,
            "value": {
                "op": "multiply",
                "left": {
                    "op": "field_number",
                    "fieldId": "distance",
                    "measurementType": "length",
                    "normalizeToUnit": "km",
                },
                "right": {"op": "literal", "value": factor},
            },
        },
        "resultConfig": {
            "unit": "km",
            "formatter": {
                "type": "decimal_with_unit",
                "unitLabel": "km",
                "maxFractionDigits": SWIM_EQUIV_SCALE,
                "trimTrailingZeros": True,
            },
            "emptyDisplayText": DERIVED_EMPTY_TEXT,
        },
    }


def _sport_label(activity_type: str) -> str:
    """项目中文名：优先读运行目录 rules.ACTIVITY_LABELS，fallback 包内默认表。"""
    try:
        import rules as _rules
        labels = getattr(_rules, "ACTIVITY_LABELS", None) or ACTIVITY_LABELS
    except ImportError:
        labels = ACTIVITY_LABELS
    return labels.get(activity_type, activity_type or "")


def _fmt_duration(seconds: int | None) -> str:
    """秒 -> h:mm:ss。小时位不补零（协议示例是 0:25:21，不是 00:25:21）。"""
    if not seconds or seconds <= 0:
        return ""
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}"


def round_half_up(value: float | None, scale: int) -> float | None:
    """按 half_up 舍到指定位数。

    Python 内置 round() 是银行家舍入（四舍六入五取偶），和协议要求的 half_up
    在正好 .5 时会差一档（4km/1250s 的配速 312.5：round() 给 312，客户端给 313）。
    """
    if value is None:
        return None
    q = Decimal(1).scaleb(-scale)
    result = Decimal(str(value)).quantize(q, rounding=ROUND_HALF_UP)
    return float(result)


def _fmt_distance(distance: float | None, unit: str) -> str:
    """4.86 -> '4.86 km'；末尾多余的零去掉（maxFractionDigits 是 2）。"""
    if distance is None:
        return ""
    text = f"{float(distance):.2f}".rstrip("0").rstrip(".")
    return f"{text} {unit}".strip()


def _fmt_pace(pace_seconds: int | None) -> str:
    """313 -> 5’13”/km。用印刷体引号，与客户端设计稿一致。"""
    if not pace_seconds or pace_seconds <= 0:
        return ""
    return f"{pace_seconds // 60}’{pace_seconds % 60:02d}”/km"


def _fmt_date(occurred_date: str) -> str:
    """2026-08-09 -> 2026.08.09；格式不认识就原样展示，不猜。"""
    text = str(occurred_date or "").strip()
    parts = text.split("-")
    if len(parts) == 3 and all(parts):
        return ".".join(parts)
    return text


def _field(field_id: str, label_card: str, label_editor: str, control_type: str,
           value: dict[str, Any], *, required: bool, editable: bool,
           card_role: str = "row", control_config: dict[str, Any] | None = None,
           display_config: dict[str, Any] | None = None,
           derived: dict[str, Any] | None = None,
           editor_visible: bool | None = None) -> dict[str, Any]:
    field: dict[str, Any] = {
        "fieldId": field_id,
        "labels": {"card": label_card, "editor": label_editor},
        "cardRole": card_role,
        "controlType": control_type,
        "required": required,
        "editable": editable,
        "value": value,
    }
    # editorVisible 只在要显式隐藏时下发；不带就是编辑面板里也出这一行（默认行为）。
    if editor_visible is not None:
        field["editorVisible"] = editor_visible
    if control_config is not None:
        field["controlConfig"] = control_config
    if display_config is not None:
        field["displayConfig"] = display_config
    if derived is not None:
        field["derived"] = derived
    return field


def status_code(status: str) -> int:
    """状态字符串 -> card_data.status 的整数取值。未知状态直接报错，
    宁可让技能失败也不要把错的状态码渲染给用户。"""
    try:
        return STATUS_CODES[status]
    except KeyError:
        raise ValueError(f"unknown card status: {status!r}") from None


def build_card_data(*, card_id: str, member_name: str,
                    member_id: str | None, occurred_date: str, activity_type: str,
                    duration_seconds: int | None, distance: float | None,
                    distance_unit: str, pace_seconds: int | None,
                    location: str, status: str,
                    equivalent_km: float | None = None,
                    equivalent_factor: float | None = None,
                    age_exempt: bool = False) -> dict[str, Any]:
    """业务字段 -> 完整 card_data。整份下发，不做增量。"""
    sport_name = _sport_label(activity_type)
    duration_required = not age_exempt
    pace_required = not age_exempt

    basic = [
        _field(
            "memberName", "对象", "打卡对象", "member_input",
            {"raw": {"text": member_name, "memberId": member_id},
             "displayText": member_name},
            required=True, editable=True,
            control_config={"placeholder": "*输入对象", "allowMemberAssociation": True},
        ),
        _field(
            "date", "日期", "日期", "date_picker",
            {"raw": occurred_date, "displayText": _fmt_date(occurred_date)},
            required=True, editable=True,
            control_config={
                "placeholder": "输入日期",
                "displayFormat": "yyyy.MM.dd",
                "defaultToToday": True,
            },
        ),
    ]

    sport_value: dict[str, Any] = {"raw": sport_name, "displayText": sport_name}
    if activity_type:
        sport_value["semanticCode"] = activity_type
    details = [
        _field(
            "sportName", "项目", "项目", "text_input", sport_value,
            required=False, editable=True,
            control_config={"placeholder": "输入项目"},
        ),
        _field(
            "duration", "时长", "时长", "duration_picker",
            {"raw": duration_seconds, "unit": "s",
             "displayText": _fmt_duration(duration_seconds)},
            required=duration_required, editable=True,
        ),
        _field(
            "distance", "距离", "距离", "decimal_unit_input",
            {"raw": distance, "unit": distance_unit,
             "displayText": _fmt_distance(distance, distance_unit)},
            required=True, editable=True,
            control_config={
                "placeholder": "*输入距离",
                "keyboard": "decimal",
                "measurementType": "length",
                "maxFractionDigits": 2,
                "units": DISTANCE_UNITS,
            },
        ),
    ]
    # 配速只读且由 duration/distance 派生。算不出来也要把这行下发（raw=null、
    # displayText 空）：card_data 是完整渲染契约，字段一律不省。
    # showWhenEmpty 只给地点用，这里不带。
    pace_rounded = round_half_up(pace_seconds, PACE_SCALE) if pace_seconds else None
    pace_raw = int(pace_rounded) if pace_rounded else None
    details.append(_field(
        "pace", "配速", "配速（自动计算）", "derived_text",
        {"raw": pace_raw, "unit": "s/km",
         "displayText": _fmt_pace(pace_raw) if pace_raw else DERIVED_EMPTY_TEXT},
        required=pace_required, editable=False,
        display_config={"hint": "自动计算"},
        derived=copy.deepcopy(PACE_DERIVED),
    ))
    # 有代跑折算的项目才出「折算跑步」行（系数由 rules.effective_km 决定，见 equivalent_factor）。
    # 编辑面板里不出（editorVisible=false），它纯派生、用户改不了。
    if equivalent_factor is not None and activity_type:
        equiv_raw = round_half_up(equivalent_km, SWIM_EQUIV_SCALE) if equivalent_km else None
        details.append(_field(
            "runningEquivalentDistance", "折算跑步", "折算跑步（自动计算）", "derived_text",
            {"raw": equiv_raw, "unit": "km",
             "displayText": _fmt_distance(equiv_raw, "km") if equiv_raw else DERIVED_EMPTY_TEXT},
            required=False, editable=False, editor_visible=False,
            display_config={"hint": "自动计算", "showWhenEmpty": True},
            derived=copy.deepcopy(_build_equiv_derived(equivalent_factor, activity_type)),
        ))
    loc = (location or "").strip()
    details.append(_field(
        "location", "位置", "位置", "text_input",
        {"raw": location, "displayText": location},
        required=False, editable=True,
        editor_visible=True if loc else None,
        control_config={"placeholder": "输入位置"},
        display_config={"showWhenEmpty": False},
    ))

    return {
        "cardId": card_id,
        "cardType": CARD_TYPE,
        "cardName": CARD_NAME,
        INNER_KEY: {
            "schemaVersion": SCHEMA_VERSION,
            "presentation": {
                "iconToken": ICON_TOKEN,
                "footerText": FOOTER_TEXT,
                "editor": {
                    "title": "编辑打卡",
                    "initialFocusFieldId": "memberName",
                    "unsavedPrompt": "内容尚未保存，退出后将无法恢复。",
                },
            },
            "sections": [
                {"sectionId": "basic", "fields": basic},
                {"sectionId": "details", "fields": details},
            ],
        },
        "status": status_code(status),
        "actions": [dict(a) for a in PENDING_ACTIONS] if status == "pending" else [],
    }


def _inner(card_data: dict[str, Any]) -> dict[str, Any]:
    """取卡面结构那一层。

    回读时既可能拿到完整的 card_data（下行那份、以及客户端经 app.env 原样回传的
    那份），也可能有人直接把内层递进来，两种都认。
    """
    inner = card_data.get(INNER_KEY)
    if isinstance(inner, dict):
        return inner
    return card_data


def iter_fields(card_data: dict[str, Any]):
    """按 sections 顺序遍历所有 field。"""
    for section in _inner(card_data).get("sections") or []:
        if not isinstance(section, dict):
            continue
        for field in section.get("fields") or []:
            if isinstance(field, dict):
                yield field


def find_field(card_data: dict[str, Any], field_id: str) -> dict[str, Any] | None:
    for field in iter_fields(card_data):
        if field.get("fieldId") == field_id:
            return field
    return None


def field_raw(card_data: dict[str, Any], field_id: str) -> Any:
    """回读某个 fieldId 的原值。

    落库只认 raw（和 sportName 的 semanticCode），displayText 一律忽略——
    它是服务端渲的展示文本，客户端改完不保证同步更新。
    """
    field = find_field(card_data, field_id)
    if not field:
        return None
    return (field.get("value") or {}).get("raw")


def field_semantic_code(card_data: dict[str, Any], field_id: str) -> str:
    field = find_field(card_data, field_id)
    if not field:
        return ""
    return str((field.get("value") or {}).get("semanticCode") or "")


def member_name_of(card_data: dict[str, Any]) -> str:
    """memberName 的 raw 是 {text, memberId}，取 text。"""
    raw = field_raw(card_data, "memberName")
    if isinstance(raw, dict):
        return str(raw.get("text") or "")
    return str(raw or "")
