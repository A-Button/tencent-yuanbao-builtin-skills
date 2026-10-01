"""Now 动态卡的参数生成：把数据算成 ``show_widget`` 的完整入参，模型原样转发。

**为什么要有这一层。** Now 卡的字段散在规范的五个地方（署名、按钮、版式、字数、配色），
模型每次自己拼，就会拼串——2026-09-23 线上那张资讯卡用了盘面的署名和按钮、标题自己编、
`desc` 被「利好」顶掉了解读，而 `show_widget` 照样回 `now_id`，不报错。
把这些固定成常量放进代码，模型就只需要提供数据。

**这三个脚本不是 App tool，不要写进 ``app.yaml``。** 它们只在 stdout 打印一段 JSON，
不产出 ``__ONEAGENT_APP_RESULT__``、不渲染任何东西；直接 ``python3 scripts/now_*.py``
调用，把打印出来的对象原样作为 ``show_widget`` 的入参。走 ``_run.py`` 反而会被当成
A2UI 出卡。

配色、市场判定、自选股 URL、小数位都从 ``_card.py`` 取，不在这儿复制第二份——
那两套口径一旦漂移，主对话和 Now 就会对同一只票显示相反的颜色。
"""

from __future__ import annotations

import json
import sys
import unicodedata

from _card import (GREEN_MEANS_UP, STANCE_DIRECTION, _decimals, _fixed,
                   parse_symbol, zxg_detail_url)

# summary 只画一行，整句颜色口径会被截断，所以压成这两句固定文案。
SUMMARY_BOARD = "A股港股红涨绿跌，美股相反"
SUMMARY_NEWS = "利好利空颜色同盘面口径"

# 三个字段各只画一行，超出直接截断成「…」。协议没有行数或字号参数。
# 额度按**显示宽度**算，单位是一个汉字：`430.00 HKD` 占 5 个汉字宽而不是 10 个字。
# 按码点数会把「🔴 腾讯控股 430.00 HKD ▲2.63%」截成「…HKD ▲…」，涨跌幅整个没了。
LIMIT_SUMMARY, LIMIT_TITLE, LIMIT_DESC = 18, 20, 20


def _width(text: str) -> float:
    """半角算 0.5 个汉字宽，全角和 emoji 算 1 个。"""
    return sum(1.0 if unicodedata.east_asian_width(c) in "WF" or ord(c) > 0x2100
               else 0.5 for c in text)


def clip(text: str, limit: int) -> str:
    """按显示宽度截断，省略号自己也占宽。"""
    text = str(text).strip()
    if _width(text) <= limit:
        return text
    kept, used = [], 0.0
    for ch in text:
        w = _width(ch)
        if used + w > limit - 1:
            break
        kept.append(ch)
        used += w
    return "".join(kept).rstrip("，,；;。·、 ") + "…"

# 平台股票卡固定：2 上涨红 / 3 下跌绿 / 1 平盘灰 / 0 未指定灰。按实际涨跌填，
# 不要为美股对调——美股的绿涨红跌只在 recommend_list 用圆点表达。
TREND_UP, TREND_DOWN, TREND_FLAT = 2, 3, 1

DOT_UP, DOT_DOWN, DOT_FLAT = "🔴", "🟢", "⚪"
ARROW_UP, ARROW_DOWN = "▲", "▼"

# 按钮最多两个，多了 H5 会挤。prompt 以 label 开头再接标的，缺一不可：
# 只发 label 那几个字，主对话不带卡上下文，不知道指哪几只。
ACTION_BOARD = ("a_analyze", "帮我分析", "帮我分析{names}现在该怎么操作")
ACTION_NEWS = ("a_holdings", "聊聊对持仓的影响", "聊聊对持仓的影响：{names}今天这些资讯")
NAMES_IN_PROMPT = 3

# make-things 的 recommend_list 按 3–5 条组织。超出时截断而不是报错——
# 20:00 日结是无人值守跑的，报错等于当天没有卡。
# 少于 3 条不编造凑数：清单里就两只票时，编第三只比少一条更糟。条数上限以 make-things 为准。
MAX_ROWS = 5


def fail(message: str) -> None:
    print(json.dumps({"phase": "error", "message": message}, ensure_ascii=False))
    raise SystemExit(1)


def direction(change_pct: float | None) -> str:
    """缺失或 0 都算平盘——不猜方向，平盘走灰色不染红绿。"""
    if change_pct is None or change_pct == 0:
        return "flat"
    return "up" if change_pct > 0 else "down"


def dot(market: str, way: str) -> str:
    """圆点按市场惯例翻转：沪深京港涨红跌绿，美股绿涨红跌。箭头两边一样。"""
    if way == "flat":
        return DOT_FLAT
    if market in GREEN_MEANS_UP:
        return DOT_UP if way == "down" else DOT_DOWN
    return DOT_UP if way == "up" else DOT_DOWN


def name_of(item: dict) -> str:
    """名称由入参给，`parse_symbol` 只负责代码归一，不认名称。"""
    return str(item.get("name") or "").strip()


def quote_line(item: dict) -> str:
    """一行「圆点 + 名称 + 现价 + 币种 + ▲▼涨跌幅」，超 20 字截断。"""
    symbol = parse_symbol(item)
    pct = item.get("change_pct")
    way = direction(pct)
    arrow = "" if way == "flat" else (ARROW_UP if way == "up" else ARROW_DOWN)
    price = item.get("price")
    decimals = _decimals(price) if price is not None else 2
    parts = [dot(symbol["market"], way), name_of(item)]
    if price is not None:
        parts.append(_fixed(price, decimals))
    if item.get("currency"):
        parts.append(str(item["currency"]))
    if pct is not None:
        parts.append(f"{arrow}{abs(pct):.2f}%")
    return clip(" ".join(p for p in parts if p), LIMIT_TITLE)


def names_of(items: list[dict], limit: int = NAMES_IN_PROMPT) -> str:
    names = [n for n in (name_of(i) for i in items) if n]
    if len(names) <= limit:
        return "、".join(names)
    return "、".join(names[:limit]) + f"等 {len(names)} 只"


def action(spec: tuple[str, str, str], items: list[dict]) -> dict:
    action_id, label, template = spec
    return {"action_id": action_id, "label": label,
            "tap": {"type": 1,
                    "agent_chat": {"send_prompt": template.format(names=names_of(items))}}}


def source_label(args: dict) -> str:
    """署名不在本技能里规定。按 make-things 用本次 Todo 的真实 title。"""
    label = str(args.get("source_label") or "").strip()
    if not label:
        fail("source_label 必填：按 make-things，填本次 Todo 的真实 title；没有 Todo 就填 Thing 名称。")
    return label


def h5(url: str) -> dict | None:
    """开 H5。tap 有哪些 type 以 make-things 为准，本脚本只发 type 2。"""
    return {"type": 2, "h5": {"url": url}} if url else None


def envelope(card_type: str, title: str, summary: str, source: str,
             data: dict, thing_id: str) -> dict:
    """顶层骨架。关联事项用 camelCase `thingId`，不是 IDL 的 thing_id。"""
    if not thing_id:
        fail("thing_id 必填：Now 卡要挂在真实 Thing 上，不能发游离动态。")
    return {"card_type": card_type, "title": title,
            "summary": clip(summary, LIMIT_SUMMARY),
            "source": {"label": source}, "thingId": str(thing_id), "data": data}


def emit(payload: dict) -> int:
    """打印一行紧凑 JSON，原样作为 show_widget 的入参。"""
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0


def run(build) -> int:
    raw = sys.argv[1] if len(sys.argv) > 1 else "{}"
    try:
        args = json.loads(raw)
    except json.JSONDecodeError:
        fail("请求参数必须是 JSON 对象。")
    if not isinstance(args, dict):
        fail("请求参数必须是 JSON 对象。")
    items = args.get("items")
    if not isinstance(items, list) or not items:
        fail("items 必填，且至少一条。")
    return emit(build(args, items))
