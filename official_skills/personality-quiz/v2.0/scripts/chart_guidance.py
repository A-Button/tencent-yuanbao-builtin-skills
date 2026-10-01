#!/usr/bin/env python3
"""Legacy field guides for offline diagnostics, not the default result page."""

from __future__ import annotations

from typing import Any


GUIDANCE_VERSION = "1.0.0"
PERSONAL_PLANETS = ("sun", "moon", "mercury", "venus", "mars")
PLANET_ZH = {
    "sun": "太阳",
    "moon": "月亮",
    "mercury": "水星",
    "venus": "金星",
    "mars": "火星",
    "jupiter": "木星",
    "saturn": "土星",
    "uranus": "天王星",
    "neptune": "海王星",
    "pluto": "冥王星",
}
PLANET_TOPIC = {
    "sun": "核心表达",
    "moon": "情绪反应",
    "mercury": "思考沟通",
    "venus": "偏好与关系表达",
    "mars": "行动与边界",
}
ASPECT_ZH = {
    "conjunction": "合相",
    "sextile": "六合",
    "square": "刑相",
    "trine": "拱相",
    "opposition": "冲相",
}


def _item(
    label: str,
    title: str,
    body: str,
    *source_paths: str,
) -> dict[str, Any]:
    return {
        "label": label,
        "title": title,
        "body": body,
        "source_paths": list(source_paths),
    }


def _guide(system: str, precision: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": GUIDANCE_VERSION,
        "system": system,
        "precision": precision,
        "title": "盘面导读",
        "subtitle": "以下内容由固定规则读取盘面事实，帮你先看懂字段；它不是深度报告。",
        "items": items,
    }


def _degree(value: Any) -> str:
    try:
        return f"{float(value):.2f}°"
    except (TypeError, ValueError):
        return "—"


def _aspect_summary(aspects: Any) -> str:
    if not isinstance(aspects, list):
        return "当前没有可用的主要相位事实。"
    valid = [item for item in aspects if isinstance(item, dict)]
    valid.sort(
        key=lambda item: (
            float(item.get("orb_deg", 999))
            if isinstance(item.get("orb_deg"), (int, float))
            else 999
        )
    )
    parts = []
    for item in valid[:3]:
        first = PLANET_ZH.get(item.get("body_a"), str(item.get("body_a", "—")))
        second = PLANET_ZH.get(item.get("body_b"), str(item.get("body_b", "—")))
        aspect = ASPECT_ZH.get(item.get("aspect"), str(item.get("aspect", "—")))
        parts.append(f"{first}{aspect}{second}（容许度 {_degree(item.get('orb_deg'))}）")
    return "；".join(parts) if parts else "当前容许度内没有主要相位。"


def _western_exact(chart: dict[str, Any]) -> dict[str, Any]:
    planets = chart.get("planets", {})
    personal = []
    for key in PERSONAL_PLANETS:
        item = planets.get(key)
        if not isinstance(item, dict):
            continue
        personal.append(
            f"{PLANET_ZH[key]} {item.get('sign', '—')} {_degree(item.get('degree_in_sign'))}"
            f"（{PLANET_TOPIC[key]}）"
        )
    items = [
        _item(
            "阅读语法",
            "行星是主题 · 星座是表达方式 · 相位是几何联系",
            "先分清三层：行星说明正在观察哪类功能，星座提供该功能的象征表达方式，相位只记录两个功能之间的角度关系。",
            "chart.planets",
            "chart.aspects",
        ),
        _item(
            "个人行星",
            "先看太阳、月亮、水星、金星和火星",
            "；".join(personal) if personal else "当前没有可用的个人行星事实。",
            *(f"chart.planets.{key}" for key in PERSONAL_PLANETS),
        ),
        _item(
            "主要相位",
            "按容许度从小到大列出前三项",
            _aspect_summary(chart.get("aspects"))
            + "。更接近精确角度只是查看顺序，不自动等于更重要、更吉或更凶。",
            "chart.aspects",
        ),
        _item(
            "覆盖范围",
            "这是精确时刻基础星盘",
            (
                "当前包含十天体、热带黄道星座、度数、主要相位与上升点；不包含宫位、行运或未来事件。"
                if chart.get("ascendant") else
                "当前只覆盖十天体、热带黄道星座、度数和主要相位；不包含上升点、宫位、行运或未来事件。"
            ),
            "chart.coverage",
            "chart.houses",
            "chart.ascendant",
        ),
    ]
    return _guide("western", "exact", items)


def _western_date_only(chart: dict[str, Any]) -> dict[str, Any]:
    stable = chart.get("stable", {}).get("planet_signs", {})
    possible = chart.get("possible", {}).get("planet_signs", {})
    if not isinstance(stable, dict):
        stable = {}
    if not isinstance(possible, dict):
        possible = {}
    stable_parts = []
    variable_parts = []
    for key in PERSONAL_PLANETS:
        stable_sign = stable.get(key)
        possible_signs = possible.get(key)
        if stable_sign:
            stable_parts.append(f"{PLANET_ZH[key]} {stable_sign}（{PLANET_TOPIC[key]}）")
        elif isinstance(possible_signs, list) and possible_signs:
            sign_range = " / ".join(str(value) for value in possible_signs)
            variable_parts.append(f"{PLANET_ZH[key]} {sign_range}")
    stable_text = "；".join(stable_parts) or "五颗个人行星暂无整日稳定星座"
    variable_text = "；".join(variable_parts) or "五颗个人行星中没有跨星座项"
    items = [
        _item(
            "阅读语法",
            "行星是主题 · 星座是表达方式",
            "日期级初盘只把整日不变的行星星座作为确定信息；行星说明观察主题，星座提供象征表达方式。",
            "chart.stable.planet_signs",
        ),
        _item(
            "稳定事实",
            "整日稳定的个人行星",
            stable_text,
            "chart.stable.planet_signs",
        ),
        _item(
            "变化范围",
            "跨星座的个人行星",
            variable_text + "。这些值只保留为范围，不从中选一个作确定解读。",
            "chart.possible.planet_signs",
        ),
        _item(
            "精度边界",
            "没有使用猜测的出生时间",
            "精确度数、时间敏感相位、上升点和宫位本次不作判断；后续补充准确时间时应生成新版盘面。",
            "chart.unavailable",
        ),
    ]
    return _guide("western", "date-only", items)


def build_western_guidance(payload: dict[str, Any]) -> dict[str, Any]:
    chart = payload.get("chart", {})
    return (
        _western_date_only(chart)
        if chart.get("precision") == "date-only"
        else _western_exact(chart)
    )
