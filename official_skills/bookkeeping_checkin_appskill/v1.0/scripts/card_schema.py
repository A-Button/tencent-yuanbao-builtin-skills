#!/usr/bin/env python3
"""记账打卡卡片的 card_data 构造与回读（schemaVersion 2）。

card_data 是**渲染契约**：客户端不认识"记账"这个业务，卡面上有几行、每行什么
label、用什么控件、分类下拉里有哪些选项、哪些字段必填，全部由这里下发。信封
（structuredContent）只留服务端和模型要用的路由与状态——card_id /
operate_type / status / expire_at；改旧卡再加 update_seq_id。

与跑团打卡卡共用同一套协议外壳（app.resource / app.data / app.env、整数 status、
四态枚举 pending/recording/confirmed/cancelled、三个 action），只有 sections 里的字段树不同。差异集中在本文件。

两个方向都在这个模块里，保证下发与回读用的是同一套 fieldId：
  build_card_data   业务字段 -> schema 树（下行）
  field_raw         schema 树 -> 某个 fieldId 的原值（回读 app.env.ui_snapshot）

value 双写 raw + displayText 是有意的：编辑态要结构化值做双向绑定和校验，
展示态要成品文本（¥38.50 / 2026.08.09）。两者同源生成，客户端不做换算。

本模块只负责"把给定的值渲染成 schema 树"，不做业务兜底。分类默认「其他」、
日期默认当天这类规则在 ledger_api 里先算好再传进来——渲染层不猜业务语义。
"""

from __future__ import annotations

from typing import Any

import vocab

SCHEMA_VERSION = 2
CARD_TYPE = "bookkeeping_check_in"

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

CARD_TITLE = "记账打卡"
CARD_NAME = "记账打卡"
FOOTER_TEXT = "元宝辅助识别，仅供参考"
ICON_TOKEN = "bookkeeping"

# card_data 下面还有一层 cardPayload，是客户端那边的既有结构，逐字保留：
#   card_data = {cardId, cardType, cardName, cardPayload: {schemaVersion, presentation, sections}, status, actions}
# 卡面结构在内层，卡片身份与状态在外层。
INNER_KEY = "cardPayload"

# 单个 section：记账八个字段是一组平铺的行，没有跑团卡那种「基本信息 / 明细」分区。
SECTION_ID = "bookkeeping"

# 仅待确认有动作：编辑在右上角图标位，取消/确认在底部。
# 待录入 / 已确认 / 已取消一律空数组，Footer 不出。按钮最多三个（协议约束），这里正好用满。
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

# 必填三项，与 spec 一致：归属人、类型、金额。
# 日期有默认（当天）、分类和账户有兜底（其他）、商户和备注可为空，所以都不必填。
REQUIRED_FIELD_IDS = ("ownerName", "transactionType", "amount")


def _fmt_date(occurred_date: str) -> str:
    """2026-08-09 -> 2026.08.09；格式不认识就原样展示，不猜。"""
    text = str(occurred_date or "").strip()
    parts = text.split("-")
    if len(parts) == 3 and all(parts):
        return ".".join(parts)
    return text


def _fmt_amount(amount: float | None) -> str:
    """金额展示只带数字和两位小数，货币单位另有 currencyUnit 字段。"""
    if amount is None:
        return ""
    try:
        return f"{float(amount):.2f}"
    except (TypeError, ValueError):
        return ""


def _field(field_id: str, label_card: str, label_editor: str, control_type: str,
           value: dict[str, Any], *, required: bool, editable: bool,
           card_role: str = "row", control_config: dict[str, Any] | None = None,
           display_config: dict[str, Any] | None = None) -> dict[str, Any]:
    field: dict[str, Any] = {
        "fieldId": field_id,
        "labels": {"card": label_card, "editor": label_editor},
        "cardRole": card_role,
        "controlType": control_type,
        "required": required,
        "editable": editable,
        "value": value,
    }
    if control_config is not None:
        field["controlConfig"] = control_config
    if display_config is not None:
        field["displayConfig"] = display_config
    return field


def status_code(status: str) -> int:
    """状态字符串 -> card_data.status 的整数取值。未知状态直接报错，
    宁可让技能失败也不要把错的状态码渲染给用户。"""
    try:
        return STATUS_CODES[status]
    except KeyError:
        raise ValueError(f"unknown card status: {status!r}") from None


def _options(labels: dict[str, str]) -> list[dict[str, Any]]:
    """{id: label} -> [{id, label}]，保持声明顺序。"""
    return [{"id": oid, "label": label} for oid, label in labels.items()]


def _account_options() -> list[dict[str, Any]]:
    """账户选项额外带 aliases，供客户端在编辑面板里做模糊匹配。"""
    out: list[dict[str, Any]] = []
    for oid, label in vocab.ACCOUNTS.items():
        opt: dict[str, Any] = {"id": oid, "label": label}
        aliases = vocab.ACCOUNT_CLIENT_ALIASES.get(oid)
        if aliases:
            opt["aliases"] = list(aliases)
        out.append(opt)
    return out


def _category_option_groups() -> dict[str, list[dict[str, Any]]]:
    """分类按类型分组下发：客户端靠 dependsOnFieldId 在编辑面板里联动切换。"""
    return {tid: _options(labels) for tid, labels in vocab.CATEGORIES.items()}


def _enum_value(raw: str, label: str) -> dict[str, Any]:
    """枚举字段的 value：raw 是机器码，displayText 是中文，semanticCode 给客户端做统计。

    raw 为空（识别不出类型/分类）时不塞 semanticCode，也不编造 displayText——
    卡面上就是一个空行加 placeholder，等用户自己选。
    """
    if not raw:
        return {"raw": "", "displayText": ""}
    return {"raw": raw, "displayText": label or raw, "semanticCode": raw}


def build_card_data(*, card_id: str, owner_name: str, owner_id: str | None,
                    occurred_date: str, transaction_type: str,
                    amount: float | None, currency: str,
                    category: str, account: str, merchant_name: str, note: str,
                    status: str) -> dict[str, Any]:
    """业务字段 -> 完整 card_data。整份下发，不做增量。

    传进来的 transaction_type / category / account 必须已经是 vocab 里的机器码
    （由 ledger_api 归一并兜底）。这里只渲染，认不出的取值会原样下发成 raw，
    在 missing 清单里暴露出来，而不是被静默改掉。
    """
    currency = vocab.normalize_currency(currency)

    fields = [
        # 归属人是群成员，不是自由文本：控件用 member_input，raw 是 {text, memberId}
        # 结构体（与跑团打卡的「对象」字段同款），客户端据此在卡面上关联群成员。
        # memberId 为空表示这个人还没建档——落库会被拒，模型该先建档。
        _field(
            "ownerName", "归属人", "归属人", "member_input",
            {"raw": {"text": owner_name, "memberId": owner_id},
             "displayText": owner_name},
            required=True, editable=True,
            control_config={"placeholder": "请输入归属人",
                            "allowMemberAssociation": True},
        ),
        _field(
            "date", "日期", "日期", "date_picker",
            {"raw": occurred_date, "displayText": _fmt_date(occurred_date)},
            required=False, editable=True,
            control_config={
                "placeholder": "输入日期",
                "displayFormat": "yyyy.MM.dd",
                "defaultToToday": True,
            },
        ),
        _field(
            "transactionType", "类型", "类型", "single_select",
            _enum_value(transaction_type, vocab.type_label(transaction_type)),
            required=True, editable=True,
            control_config={
                "placeholder": "请选择类型",
                "options": _options(vocab.TRANSACTION_TYPES),
            },
        ),
        _field(
            "amount", "金额", "金额", "money_input",
            {"raw": amount, "displayText": _fmt_amount(amount)},
            required=True, editable=True,
            control_config={
                "placeholder": "请输入金额",
                "keyboard": "decimal",
                "maxFractionDigits": 2,
            },
        ),
        _field(
            "currencyUnit", "货币单位", "货币单位", "text_input",
            {"raw": currency, "displayText": currency},
            required=False, editable=True,
            control_config={"placeholder": "人民币"},
        ),
        _field(
            "category", "分类", "分类", "category_picker",
            _enum_value(category, vocab.category_label(transaction_type, category)),
            required=False, editable=True,
            control_config={
                "dependsOnFieldId": "transactionType",
                "fallbackOptionId": vocab.FALLBACK_CATEGORY,
                "optionGroups": _category_option_groups(),
            },
        ),
        _field(
            "account", "账户", "账户", "account_picker",
            _enum_value(account, vocab.account_label(account)),
            required=False, editable=True,
            control_config={
                "fallbackOptionId": vocab.FALLBACK_ACCOUNT,
                "options": _account_options(),
            },
        ),
        _field(
            "merchantName", "商户", "商户", "name_input",
            {"raw": merchant_name, "displayText": merchant_name},
            required=False, editable=True,
            control_config={"placeholder": "请输入商户"},
        ),
        _field(
            "note", "备注", "备注", "text_input",
            {"raw": note, "displayText": note},
            required=False, editable=True,
            control_config={"placeholder": "请输入备注"},
        ),
    ]

    return {
        "cardId": card_id,
        "cardType": CARD_TYPE,
        "cardName": CARD_NAME,
        INNER_KEY: {
            "schemaVersion": SCHEMA_VERSION,
            "presentation": {
                "cardTitle": CARD_TITLE,
                "iconToken": ICON_TOKEN,
                "footerText": FOOTER_TEXT,
                "editor": {
                    "title": "编辑记账",
                    "unsavedPrompt": "内容尚未保存，退出后将无法恢复。",
                },
            },
            "sections": [{"sectionId": SECTION_ID, "fields": fields}],
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

    落库只认 raw（枚举字段等价地认 semanticCode），displayText 一律忽略——
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


def field_unit(card_data: dict[str, Any], field_id: str) -> str:
    field = find_field(card_data, field_id)
    if not field:
        return ""
    return str((field.get("value") or {}).get("unit") or "")


def currency_of(card_data: dict[str, Any]) -> str:
    """货币单位：新卡读 currencyUnit，旧卡回落到 amount.value.unit。

    词表内归一成中文名；用户自填的表外币种原样返回。
    """
    raw = field_raw(card_data, "currencyUnit")
    if raw:
        return vocab.normalize_currency(raw)
    code = field_semantic_code(card_data, "currencyUnit")
    if code:
        return vocab.normalize_currency(code)
    unit = field_unit(card_data, "amount")
    if unit:
        return vocab.normalize_currency(unit)
    return vocab.DEFAULT_CURRENCY


def owner_name_of(card_data: dict[str, Any]) -> str:
    """ownerName 的 raw 是 {text, memberId}，取 text。

    客户端在编辑面板里改归属人时可能只填了文本没关联到成员（memberId 为空），
    所以这两个值要分开读，不能假设同时存在。
    """
    raw = field_raw(card_data, "ownerName")
    if isinstance(raw, dict):
        return str(raw.get("text") or "")
    return str(raw or "")


def owner_id_of(card_data: dict[str, Any]) -> str:
    """ownerName 的 raw.memberId；未关联到已建档成员时为空串。"""
    raw = field_raw(card_data, "ownerName")
    if isinstance(raw, dict):
        return str(raw.get("memberId") or "")
    return ""
