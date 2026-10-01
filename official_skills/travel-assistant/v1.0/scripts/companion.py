#!/usr/bin/env python3
"""获取天气、路况和周边数据，并以结构化结果表示失败。"""

from __future__ import annotations

import json
import math
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

_COORD_RE = re.compile(r"\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)\s*")
_OUTDOOR_BAD = ("雨", "雪", "雹", "台风", "暴", "雷电")
_KIND_KEYWORDS = {
    "dining": "餐厅",
    "souvenir": "纪念品",
    "convenience": "便利店",
}


def _tencent_scripts() -> Path | None:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "tencent-map" / "scripts",
        Path(os.environ.get("ONEAGENT_SKILLS_ROOT") or "") / "tencent-map" / "scripts",
    ]
    for path in candidates:
        if (path / "map_query.py").is_file():
            return path
    return None


def _load_map_query():
    """优先使用 tencent-map；未部署时回退到内置实现。"""
    scripts = _tencent_scripts()
    if scripts is not None:
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        import map_query  # type: ignore

        return map_query

    import map_fallback  # type: ignore

    return map_fallback


def _coord_pair(value: object, field: str) -> str:
    if not isinstance(value, str) or not _COORD_RE.fullmatch(value):
        raise ValueError(f"{field} 必须是纬度,经度")
    match = _COORD_RE.fullmatch(value)
    assert match is not None
    lat, lng = float(match.group(1)), float(match.group(2))
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValueError(f"{field} 坐标超出范围")
    return f"{lat:.6f},{lng:.6f}"


def _parse_date(value: object) -> date | None:
    text = value.strip() if isinstance(value, str) else ""
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _outdoor(weather: str) -> bool:
    return not any(token in weather for token in _OUTDOOR_BAD)


def check_weather(
    args: dict[str, Any],
    query: Callable[..., dict[str, Any]] | None = None,
    geocode: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    maps = None if query and (geocode or args.get("location")) else _load_map_query()
    weather_fn = query or maps.weather
    query_type = str(args.get("type") or "now")
    if query_type not in {"now", "future"}:
        raise ValueError("type 只能是 now 或 future")
    payload: dict[str, Any] = {"type": query_type}
    if args.get("location"):
        payload["location"] = _coord_pair(args["location"], "location")
    elif args.get("city"):
        geocode_fn = geocode or maps.geocode
        geo = geocode_fn({"address": args["city"], "region": args["city"]})
        location = geo.get("location") if isinstance(geo, dict) else None
        if not isinstance(location, dict):
            raise RuntimeError("无法把城市解析成坐标")
        payload["location"] = f"{location['lat']},{location['lng']}"
    else:
        raise ValueError("需要 location 或 city")

    target = _parse_date(args.get("date"))
    today = date.today()
    if target and target > today + timedelta(days=3):
        return {
            "ok": True,
            "horizonExceeded": True,
            "outdoorSuitable": "unknown",
            "date": target.isoformat(),
            "message": "天气预报只覆盖当天加未来 3 天，这一天不做户外判断。",
        }

    raw = weather_fn(payload)
    if query_type == "now":
        weather = str(raw.get("weather") or "")
        suitable = _outdoor(weather) if weather else None
        return {
            "ok": True,
            "horizonExceeded": False,
            "kind": "now",
            "city": raw.get("city"),
            "district": raw.get("district"),
            "weather": weather,
            "temperature": raw.get("temperature"),
            "outdoorSuitable": "yes" if suitable else ("no" if suitable is False else "unknown"),
            "date": (target or today).isoformat(),
        }

    days = raw.get("days") if isinstance(raw.get("days"), list) else []
    picked = None
    if target:
        for item in days:
            if str(item.get("date") or "").startswith(target.isoformat()):
                picked = item
                break
    if picked is None and days:
        picked = days[0]
    if not isinstance(picked, dict):
        return {
            "ok": True,
            "horizonExceeded": True,
            "outdoorSuitable": "unknown",
            "message": "没有对应日期的预报。",
        }
    day_weather = str(picked.get("day_weather") or "")
    night_weather = str(picked.get("night_weather") or "")
    suitable = _outdoor(day_weather + night_weather) if (day_weather or night_weather) else None
    return {
        "ok": True,
        "horizonExceeded": False,
        "kind": "future",
        "city": raw.get("city"),
        "date": picked.get("date"),
        "dayWeather": day_weather,
        "nightWeather": night_weather,
        "maxDegree": picked.get("max_degree"),
        "minDegree": picked.get("min_degree"),
        "outdoorSuitable": "yes" if suitable else ("no" if suitable is False else "unknown"),
    }


def check_route_eta(args: dict[str, Any], query: Callable[..., dict[str, Any]] | None = None) -> dict[str, Any]:
    request_fn = query or _load_map_query().request
    mode = str(args.get("mode") or "driving")
    origin = _coord_pair(args.get("from"), "from")
    destination = _coord_pair(args.get("to"), "to")
    if mode not in {"driving", "walking", "transit"}:
        raise ValueError("mode 只能是 driving、walking 或 transit")

    if query is not None and not hasattr(query, "__self__"):
        # tests inject a complete route-like function
        raw = query({"from": origin, "to": destination, "mode": mode})
        return _route_from_normalized(raw, origin, destination, mode)

    path = {
        "driving": "/ws/direction/v1/driving/",
        "walking": "/ws/direction/v1/walking/",
        "transit": "/ws/direction/v1/transit/",
    }[mode]
    params = {"from": origin, "to": destination}
    if mode == "driving":
        params["policy"] = "REAL_TRAFFIC"
    result = request_fn(path, params).get("result") or {}
    routes = result.get("routes") or []
    if not routes:
        raise RuntimeError("未返回可用路线")
    best = routes[0]
    distance_m = _finite(best.get("distance"))
    duration_min = _finite(best.get("duration"))
    speed = None
    hint = "unknown"
    if distance_m and duration_min and duration_min > 0:
        speed = round((distance_m / 1000.0) / (duration_min / 60.0), 1)
        if mode == "driving":
            if speed < 15:
                hint = "congested"
            elif speed < 25:
                hint = "slow"
            else:
                hint = "smooth"
        else:
            hint = "smooth"
    taxi = best.get("taxi_fare") if isinstance(best.get("taxi_fare"), dict) else {}
    restriction = best.get("restriction") if isinstance(best.get("restriction"), dict) else {}
    reserve_min = None
    if duration_min is not None:
        reserve_min = int(math.ceil(duration_min * 1.3 + 15))
    return {
        "ok": True,
        "mode": mode,
        "from": origin,
        "to": destination,
        "distanceKm": round(distance_m / 1000.0, 1) if distance_m is not None else None,
        "durationMin": duration_min,
        "avgSpeedKmh": speed,
        "trafficHint": hint,
        "reserveMin": reserve_min,
        "taxiFare": taxi.get("fare"),
        "restricted": restriction.get("status") == 1,
        "trafficLightCount": best.get("traffic_light_count"),
    }


# ── 给卡片用的成品字段 ───────────────────────────────────────────────────
# 模型只报「哪个城市、哪天」「从哪到哪」，取数和排版都在这里做完。
# 让模型自己把回包字段挑进卡片，结果就是气温被抄成一格 8 字的 facts，
# 图标、未来几天、路况和打车价全丢了。

_WEEKDAYS = "一二三四五六日"
_PANEL_DAYS = 4


def _day_label(day: date, today: date) -> str:
    if day == today:
        return "今天"
    if day == today + timedelta(days=1):
        return "明天"
    return f"周{_WEEKDAYS[day.weekday()]}"


def _degrees(low: object, high: object) -> str:
    lo, hi = str(low or "").strip(), str(high or "").strip()
    return f"{lo}–{hi}°" if lo and hi else (f"{hi or lo}°" if (hi or lo) else "")


def panel_weather(city: str, when: str = "", maps=None) -> dict[str, Any]:
    """天气卡要的全部字段：当下气温、天气、温差、未来几天、湿度风力。

    超出预报射程（当天 + 3 天）时返回空 dict，由调用方不画这一块。
    """
    maps = maps or _load_map_query()
    geo = maps.geocode({"address": city, "region": city})
    location = geo.get("location") if isinstance(geo, dict) else None
    if not isinstance(location, dict):
        raise RuntimeError(f"无法把「{city}」解析成坐标")
    point = f"{location['lat']},{location['lng']}"

    today = date.today()
    target = _parse_date(when) or today
    if not today <= target <= today + timedelta(days=3):
        return {}

    forecast = maps.weather({"type": "future", "location": point})
    days = [d for d in (forecast.get("days") or []) if isinstance(d, dict)]
    picked = next((d for d in days if str(d.get("date") or "").startswith(target.isoformat())), None)

    out: dict[str, Any] = {"range": _degrees(picked and picked.get("min_degree"),
                                             picked and picked.get("max_degree"))}
    out["temp"] = out["text"] = ""
    if target == today:
        now = maps.weather({"type": "now", "location": point})
        degree = str(now.get("temperature") or "").strip()
        out["temp"] = f"{degree}°" if degree else ""
        out["text"] = str(now.get("weather") or "").strip()
        chips = [("湿度", str(now.get("humidity") or "").strip() and f"{now['humidity']}%"),
                 ("风力", str(now.get("wind_power") or "").strip() and f"{now['wind_power']} 级")]
        out["chips"] = [{"label": k, "value": v} for k, v in chips if v]
    if not (out["temp"] or out["text"]):
        # 实况拿不到（接口没给实时那一段）就退到当天的预报，别把整块天气丢掉：
        # 预报只有白天 / 夜间两种天气、没有实时气温，大字位让给天气本身
        out["temp"] = ""
        out["text"] = str((picked or {}).get("day_weather") or "").strip()

    strip = []
    for d in days:
        parsed = _parse_date(d.get("date"))
        if parsed is None or not today <= parsed <= today + timedelta(days=6):
            continue
        strip.append({"label": _day_label(parsed, today),
                      "text": str(d.get("day_weather") or "").strip(),
                      "temp": _degrees(d.get("min_degree"), d.get("max_degree"))})
    out["days"] = strip[:_PANEL_DAYS]
    return out if (out["temp"] or out["text"]) else {}


def panel_route(origin: str, destination: str, mode: str = "driving", city: str = "", maps=None) -> dict[str, Any]:
    """路线卡要的全部字段。origin / destination 是地名，坐标在这里查。

    taxi 是给用户看的说法，路况按驾车算——地图接口没有单独的打车路线。
    """
    maps = maps or _load_map_query()

    def locate(name: str) -> str:
        # region 只收城市名，塞地名进去地图侧直接判参数错误
        geo = maps.geocode({"address": name, **({"region": city} if city else {})})
        loc = geo.get("location") if isinstance(geo, dict) else None
        if not isinstance(loc, dict):
            raise RuntimeError(f"无法把「{name}」解析成坐标")
        return f"{loc['lat']},{loc['lng']}"

    ask = "driving" if mode in ("driving", "taxi", "bicycling") else mode
    eta = check_route_eta({"from": locate(origin), "to": locate(destination), "mode": ask})
    minutes, km, fare = eta.get("durationMin"), eta.get("distanceKm"), eta.get("taxiFare")
    return {
        "mode": mode, "from": origin, "to": destination,
        "duration": f"{int(minutes)} 分钟" if minutes else "",
        "distance": f"{km} km" if km else "",
        "traffic": eta.get("trafficHint") or "",
        "fare": f"¥{int(fare)}" if fare else "",
        "restricted": bool(eta.get("restricted")),
        "reserveMin": eta.get("reserveMin"),
    }


def _finite(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _route_from_normalized(raw: dict[str, Any], origin: str, destination: str, mode: str) -> dict[str, Any]:
    distance_m = _finite(raw.get("distance_m") or raw.get("distanceM"))
    duration_min = _finite(raw.get("duration_min") or raw.get("durationMin"))
    speed = None
    hint = str(raw.get("trafficHint") or "unknown")
    if distance_m and duration_min and duration_min > 0:
        speed = round((distance_m / 1000.0) / (duration_min / 60.0), 1)
        if hint == "unknown" and mode == "driving":
            hint = "congested" if speed < 15 else ("slow" if speed < 25 else "smooth")
    reserve_min = int(math.ceil(duration_min * 1.3 + 15)) if duration_min is not None else None
    return {
        "ok": True,
        "mode": mode,
        "from": origin,
        "to": destination,
        "distanceKm": round(distance_m / 1000.0, 1) if distance_m is not None else None,
        "durationMin": duration_min,
        "avgSpeedKmh": speed,
        "trafficHint": hint,
        "reserveMin": reserve_min,
        "taxiFare": raw.get("taxiFare"),
        "restricted": bool(raw.get("restricted")),
        "trafficLightCount": raw.get("trafficLightCount"),
    }


def find_nearby(args: dict[str, Any], query: Callable[..., dict[str, Any]] | None = None) -> dict[str, Any]:
    place_fn = query or _load_map_query().place
    kind = str(args.get("kind") or "")
    if kind not in _KIND_KEYWORDS:
        raise ValueError("kind 只能是 dining、souvenir 或 convenience")
    near = _coord_pair(args.get("near"), "near")
    keyword = str(args.get("keyword") or "").strip() or _KIND_KEYWORDS[kind]
    radius = int(args.get("radius") or 1000)
    limit = int(args.get("limit") or 5)
    raw = place_fn({
        "keyword": keyword,
        "near": near,
        "radius": radius,
        "limit": limit,
    })
    items = []
    for item in (raw.get("items") or [])[:limit]:
        if not isinstance(item, dict):
            continue
        location = item.get("location") if isinstance(item.get("location"), dict) else {}
        entry = {
            "title": item.get("title"),
            "address": item.get("address"),
            "category": item.get("category"),
            "location": location,
        }
        if item.get("distance_m") is not None:
            entry["distanceKm"] = round(float(item["distance_m"]) / 1000.0, 2)
        items.append(entry)
    return {
        "ok": True,
        "kind": kind,
        "anchor": near,
        "keyword": keyword,
        "phrase": "附近",
        "items": items,
        "note": "锚点是调用方传入的坐标。只有确认它来自本轮实时定位，才能表述为“您附近”或“距您 X 米”；行程站点坐标只能表述为“站点附近”。",
    }


def wrap(fn: Callable[[dict[str, Any]], dict[str, Any]], args: dict[str, Any]) -> dict[str, Any]:
    try:
        return fn(args)
    except ValueError as exc:
        return {"ok": False, "phase": "error", "code": "INVALID_ARGUMENT", "message": str(exc), "retryable": False}
    except Exception as exc:
        return {
            "ok": False,
            "phase": "error",
            "code": "PROVIDER_ERROR",
            "message": str(exc) or "查询失败",
            "retryable": True,
        }
