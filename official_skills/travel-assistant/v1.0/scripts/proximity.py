#!/usr/bin/env python3
"""把「我在哪」和「下一程在哪」换算成可判定的距离。

地理围栏触发的算术部分放在这里，判断留给规则的指令。分工的理由：
阈值命中与否必须可复现、可测试，不能靠模型心算经纬度差。

位置本身不在这里取——它来自 `geo-location` Connector 的 `get_geo_location`，
本模块只接收已经拿到的 lat/lng。
"""

from __future__ import annotations

import math
from typing import Any

from emit_card import CardError
from trip_context import load_trip_context

# 默认围栏半径。出行场景里 3 公里大约是「快到了，该准备下车/找入口」的距离，
# 5 公里是「该出发去下一程了」。用户明确给了就用用户的。
DEFAULT_RADIUS_KM = 3.0
MAX_RADIUS_KM = 50.0
MAX_TARGETS = 20
EARTH_RADIUS_KM = 6371.0088


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CardError("INVALID_FIELD", f"{field} 必须是数字")
    return float(value)


def _coord(lat: object, lng: object, field: str) -> tuple[float, float]:
    lat_v = _number(lat, f"{field}.lat")
    lng_v = _number(lng, f"{field}.lng")
    if not -90.0 <= lat_v <= 90.0:
        raise CardError("INVALID_FIELD", f"{field}.lat 超出 -90~90")
    if not -180.0 <= lng_v <= 180.0:
        raise CardError("INVALID_FIELD", f"{field}.lng 超出 -180~180")
    return lat_v, lng_v


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """大圆距离。坐标系必须一致——腾讯与同程都是 gcj02，别和 wgs84 混算。"""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def _bearing(lat1: float, lng1: float, lat2: float, lng2: float) -> str:
    """粗略方位，只用来让卡片文案说人话（「在你东北方 2.1 公里」）。"""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lng2 - lng1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    deg = (math.degrees(math.atan2(y, x)) + 360) % 360
    names = ("正北", "东北", "正东", "东南", "正南", "西南", "正西", "西北")
    return names[int((deg + 22.5) % 360 // 45)]


def _round_km(value: float) -> float:
    # 1 公里以内精确到 10 米，再远没必要——定位本身没那么准。
    return round(value, 2) if value < 1 else round(value, 1)


def _targets_from_trip() -> list[dict[str, Any]]:
    """从 travel_plan 的行程里取带坐标的站点，按天与顺序编号。

    没有坐标的站点直接跳过：算不了距离的目标放进结果只会让模型以为它很远。
    """
    trip = load_trip_context()
    if not trip.get("found"):
        return []
    targets: list[dict[str, Any]] = []
    for day in trip.get("days") or []:
        for index, stop in enumerate(day.get("stops") or []):
            location = stop.get("location")
            if not isinstance(location, dict):
                continue
            targets.append({
                "name": stop.get("name") or "",
                "lat": location.get("lat"),
                "lng": location.get("lng"),
                "dayId": day.get("dayId"),
                "stopId": stop.get("stopId"),
                "order": index,
            })
    return targets


def _radius(args: dict[str, Any]) -> float:
    radius_km = _number(args.get("radius_km", DEFAULT_RADIUS_KM), "radius_km")
    if not 0 < radius_km <= MAX_RADIUS_KM:
        raise CardError("INVALID_FIELD", f"radius_km 必须在 0~{MAX_RADIUS_KM} 之间")
    return radius_km


def _targets(args: dict[str, Any], radius_km: float) -> tuple[str, list[dict[str, Any]]]:
    """目标来源二选一：显式传 `targets`，或不传而自动读 travel_plan 的行程站点。"""
    raw_targets = args.get("targets")
    source = "explicit"
    if raw_targets is None:
        raw_targets = _targets_from_trip()
        source = "trip"
        if not raw_targets:
            raise CardError(
                "NO_TARGETS",
                "行程里没有带坐标的站点。显式传 targets（name + lat + lng），"
                "或先让 travel_plan 把行程排出来。",
            )
    if not isinstance(raw_targets, list):
        raise CardError("INVALID_FIELD", "targets 必须是数组")
    if not raw_targets:
        raise CardError("NO_TARGETS", "targets 为空")
    if len(raw_targets) > MAX_TARGETS:
        raise CardError("ITEM_COUNT", f"targets 最多 {MAX_TARGETS} 个，实际 {len(raw_targets)} 个")

    parsed: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_targets):
        if not isinstance(raw, dict):
            raise CardError("INVALID_FIELD", f"targets[{index}] 必须是对象")
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise CardError("REQUIRED_FIELD", f"targets[{index}].name 必填")
        t_lat, t_lng = _coord(raw.get("lat"), raw.get("lng"), f"targets[{index}]")
        # 每个目标可以有自己的半径：机场想 5 公里就开始提醒，餐厅 1 公里才有意义。
        own = raw.get("radius_km")
        own_km = _number(own, f"targets[{index}].radius_km") if own is not None else radius_km
        if not 0 < own_km <= MAX_RADIUS_KM:
            raise CardError("INVALID_FIELD", f"targets[{index}].radius_km 必须在 0~{MAX_RADIUS_KM} 之间")
        entry: dict[str, Any] = {"name": name.strip(), "radiusKm": own_km, "lat": t_lat, "lng": t_lng}
        for key in ("dayId", "stopId", "order"):
            if raw.get(key) not in (None, ""):
                entry[key] = raw[key]
        parsed.append(entry)
    return source, parsed


def check_proximity(args: dict[str, Any]) -> dict[str, Any]:
    """算当前位置到每个目标的距离，并标出哪些进了围栏。"""
    lat, lng = _coord(args.get("lat"), args.get("lng"), "当前位置")
    radius_km = _radius(args)
    source, parsed = _targets(args, radius_km)

    results: list[dict[str, Any]] = []
    for t in parsed:
        distance = haversine_km(lat, lng, t["lat"], t["lng"])
        results.append({**t, "distanceKm": _round_km(distance), "within": distance <= t["radiusKm"],
                        "bearing": _bearing(lat, lng, t["lat"], t["lng"])})

    results.sort(key=lambda item: item["distanceKm"])
    inside = [item for item in results if item["within"]]

    result: dict[str, Any] = {
        "ok": True,
        "source": source,
        "radiusKm": radius_km,
        "targets": results,
        "within": inside,
        "hit": bool(inside),
        "nearest": results[0],
    }
    if inside:
        result["note"] = (
            f"命中 {len(inside)} 个围栏，最近的是「{inside[0]['name']}」"
            f"{inside[0]['distanceKm']} 公里。命中不等于要发卡——"
            "先看这一程是不是已经提醒过（读进展行），再过发卡五条。"
        )
    else:
        result["note"] = (
            f"都没进围栏，最近的「{results[0]['name']}」还有 {results[0]['distanceKm']} 公里。"
            "本轮保持静默，只更新进展行的检查时间。"
        )
    return result


MAX_FENCES = 5  # 整条规则 2048 字节，条件和 prompt 要一起装下
KM_PER_LAT_DEG = 111.32


def _box(lat: float, lng: float, radius_km: float) -> dict[str, float]:
    """半径圆的外接经纬度框。角上会多出最多 √2 倍半径，命中后要用 check_proximity 复核。"""
    dlat = radius_km / KM_PER_LAT_DEG
    dlng = radius_km / (KM_PER_LAT_DEG * max(math.cos(math.radians(lat)), 0.01))
    return {"latMin": round(lat - dlat, 4), "latMax": round(lat + dlat, 4),
            "lngMin": round(lng - dlng, 4), "lngMax": round(lng + dlng, 4)}


def plan_geofence(args: dict[str, Any]) -> dict[str, Any]:
    """把围栏写成 judge.condition 能直接比的经纬度区间。

    judge 只能调一次取数（get_geo_location），判断方也不该心算球面距离；
    换成「纬度在 a~b 且经度在 c~d」这种纯数字比较，就能在后台判、未命中不投递 prompt。
    `exclude` 放已经提醒过的站点名，重新生成的条件里就没有它们。
    """
    radius_km = _radius(args)
    source, parsed = _targets(args, radius_km)
    exclude = args.get("exclude") or []
    if not isinstance(exclude, list) or not all(isinstance(x, str) for x in exclude):
        raise CardError("INVALID_FIELD", "exclude 必须是站点名数组")
    skip = {x.strip() for x in exclude}
    fences = [{"name": t["name"], "radiusKm": t["radiusKm"], "box": _box(t["lat"], t["lng"], t["radiusKm"])}
              for t in parsed if t["name"] not in skip]
    if not fences:
        return {"ok": True, "source": source, "fences": [], "condition": "",
                "note": "所有站点都已提醒过，停用这条围栏规则。"}
    if len(fences) > MAX_FENCES:
        raise CardError("ITEM_COUNT", f"一条围栏规则最多 {MAX_FENCES} 个站点，实际 {len(fences)} 个；"
                        "只放接下来要去的几站，走完再用 exclude 重新生成")
    parts = [f"{i}. {f['name']} 纬度{f['box']['latMin']}~{f['box']['latMax']} "
             f"经度{f['box']['lngMin']}~{f['box']['lngMax']}" for i, f in enumerate(fences, 1)]
    condition = ("定位结果的纬度和经度同时落在任一区间内即命中：\n" + "\n".join(parts)
                 + "\n没有坐标、失败或超时都算未命中。")
    return {
        "ok": True, "source": source, "fences": fences, "condition": condition,
        "conditionBytes": len(condition.encode("utf-8")),
        "note": "把 condition 原样填进 judge.condition，tool_call 用 get_geo_location。"
                "命中后在 prompt 里先用 check_proximity 复核（区间角上会多出一点），"
                "再把命中站点加进 exclude 重新生成条件、用 update_trigger 换掉 judge。",
    }
