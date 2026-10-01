"""Project verified chart fields onto the five-part, fixed-copy result page."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


PROFILE_PATH = Path(__file__).with_name("western_profiles.json")
ORDER = ("sun", "ascendant", "moon", "venus", "mercury")
SIGNS = ("白羊", "金牛", "双子", "巨蟹", "狮子", "处女", "天秤", "天蝎", "射手", "摩羯", "水瓶", "双鱼")
LABELS = {"sun": "太阳", "ascendant": "上升", "moon": "月亮", "venus": "金星", "mercury": "水星"}
THEMES = {"sun": "性格底色", "ascendant": "初见印象", "moon": "情绪需要", "venus": "喜欢的方式", "mercury": "思考与沟通"}


@lru_cache(maxsize=1)
def corpus() -> dict[str, Any]:
    data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    if data.get("schema_version") != "1.0.0":
        raise ValueError("星座文案版本无效。")
    profiles = data.get("profiles", {})
    if set(profiles) != set(ORDER):
        raise ValueError("星座文案必须覆盖指定的五项。")
    for component in ORDER:
        if set(profiles[component]) != set(SIGNS):
            raise ValueError(f"{component} 必须覆盖十二星座。")
        for entry in profiles[component].values():
            if set(entry) != {"tagline", "summary", "detail"} or any(
                not isinstance(value, str) or not value.strip() for value in entry.values()
            ):
                raise ValueError("星座文案字段不完整。")
    return data


def normalize_sign(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    sign = value.strip().removesuffix("座")
    return sign if sign in SIGNS else None


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def build_profile(payload: dict[str, Any]) -> dict[str, Any]:
    chart = _mapping(payload.get("chart"))
    source_input = _mapping(payload.get("input"))
    precision = _mapping(source_input.get("time_precision")).get("kind")
    time_range = chart.get("precision") == "time-range" and source_input.get("chart_precision") != "date-only" and precision in {None, "range", "shichen"}
    date_only = chart.get("precision") == "date-only" or source_input.get("chart_precision") == "date-only" or precision in {
        "approximate", "unknown", "withheld", "unspecified"
    } or (precision in {"range", "shichen"} and not time_range)
    planets = _mapping(chart.get("planets"))
    stable = _mapping(_mapping(chart.get("stable")).get("planet_signs"))
    possible = _mapping(_mapping(chart.get("possible")).get("planet_signs"))
    items = []
    for key in ORDER:
        item: dict[str, Any] = {
            "key": key, "label": LABELS[key], "theme": THEMES[key],
            "status": "unavailable", "sign": None, "sign_label": "暂未确定",
            "tagline": "等待可用结果", "summary": "当前盘面没有这一项的可用结果。",
            "detail": None, "source_path": None,
        }
        if key == "ascendant":
            value = None if date_only else _mapping(_mapping(chart.get("stable")).get("ascendant") if time_range else chart.get("ascendant")).get("sign")
            path = "chart.stable.ascendant.sign" if time_range else "chart.ascendant.sign"
            if date_only:
                item.update(tagline="需要准确出生时间", summary="缺少准确出生时间，上升暂未确定。")
            elif chart.get("ascendant_status") == "requires_coordinates":
                item.update(tagline="出生地点尚未定位", summary="出生地点尚未定位，上升暂未确定。")
            elif chart.get("ascendant_status") == "unsupported_latitude":
                item.update(tagline="地点超出计算范围", summary="出生地点超出当前上升计算范围，其他已确定结果仍然有效。")
            else:
                item.update(tagline="当前盘面未提供", summary="这份盘面尚未提供可用的上升结果。")
            candidates = _mapping(chart.get("possible")).get("ascendant", []) if time_range else []
            signs = list(dict.fromkeys(sign for raw in candidates if (sign := normalize_sign(raw)))) if isinstance(candidates, list) else []
            if len(signs) > 1:
                value = None
                item.update(status="variable", sign_label=" / ".join(f"{sign}座" for sign in signs),
                            tagline="所给时段内跨星座", summary="所给时段内上升经过星座交界，具体星座取决于出生时间。此项暂不作解读。",
                            source_path="chart.possible.ascendant")
        elif date_only or time_range:
            value = stable.get(key)
            path = f"chart.stable.planet_signs.{key}"
            candidates = possible.get(key, [])
            signs = list(dict.fromkeys(sign for raw in candidates if (sign := normalize_sign(raw)))) if isinstance(candidates, list) else []
            if time_range and len(signs) > 1:
                value = None
            if not normalize_sign(value) and signs:
                item.update(
                    status="variable", sign_label=" / ".join(f"{sign}座" for sign in signs),
                    tagline="所给时段内跨星座" if time_range else "具体星座仍待确定", summary=f"{'所给时段内' if time_range else '当天'}该天体经过星座交界，具体星座取决于出生时间。此项暂不作解读。",
                    source_path=f"chart.possible.planet_signs.{key}",
                )
        else:
            value = _mapping(planets.get(key)).get("sign")
            path = f"chart.planets.{key}.sign"
        sign = normalize_sign(value)
        if sign:
            item.update(corpus()["profiles"][key][sign])
            item.update(status="available", sign=sign, sign_label=f"{sign}座", source_path=path)
        items.append(item)
    return {"schema_version": "1.0.0", "precision": "date-only" if date_only else "time-range" if time_range else "exact", "items": items}
