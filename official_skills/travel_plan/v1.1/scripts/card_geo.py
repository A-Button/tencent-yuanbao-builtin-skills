"""腾讯 POI 与真实路网查询层。失败时返回状态，不制造坐标或直线。"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from typing import Any

import api


MAX_WORKERS = api.MAP_MAX_CONCURRENCY
VALID_MODES = {"walk", "bike", "car", "taxi", "subway", "bus", "transit"}
_ROUTE_MODES = {
    "walk": "walking",
    "bike": "bicycling",
    "car": "driving",
    "taxi": "driving",
    "subway": "transit",
    "bus": "transit",
    "transit": "transit",
}
_CATEGORY_KEYWORDS = (
    ("景点", ("景点", "风景", "名胜", "公园", "博物馆", "展览", "寺", "古镇", "遗址", "故居", "街区")),
    ("美食", ("美食", "餐饮", "餐厅", "小吃", "快餐", "咖啡", "茶")),
    ("住宿", ("酒店", "住宿", "宾馆", "旅馆", "民宿")),
    ("购物", ("购物", "商场", "商店", "超市", "步行街")),
    ("娱乐", ("娱乐", "休闲", "酒吧", "剧院", "影院", "乐园")),
    ("交通", ("交通", "地铁", "车站", "机场", "码头", "索道", "停车")),
)
_PUNCTUATION = str.maketrans("", "", " \t\r\n·•・—_-（）()【】[]《》“”\"'，,。.!！?？:：")


def available() -> bool:
    return bool(api.TENCENT_MAP_API_BASE)


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _finite(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _valid_location(value: object) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    lat, lng = _finite(value.get("lat")), _finite(value.get("lng"))
    if lat is None or lng is None or not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    return {"lat": lat, "lng": lng}


def format_distance(meters: float) -> str:
    # 一律用公里：同一列里混着「米」和「公里」，读的人得在心里换算才能比较两段的远近。
    # 0.1 是一位小数能表示的最小非零值；再短也不写 0.0公里，那看着像没算出来。
    return "%.1f公里" % max(0.1, meters / 1000)


def display_category(raw: str) -> str:
    text = _text(raw)
    if not text:
        return ""
    for label, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return label
    head = text.split(":")[0].strip()
    return head if 0 < len(head) <= 6 else ""


def straight_distance(origin: dict[str, float], destination: dict[str, float]) -> float:
    radius = 6_371_000.0
    lat1, lat2 = math.radians(origin["lat"]), math.radians(destination["lat"])
    d_lat = lat2 - lat1
    d_lng = math.radians(destination["lng"] - origin["lng"])
    h = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lng / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(h)))


def _normalized(value: object) -> str:
    return _text(value).translate(_PUNCTUATION).lower()


def _normalized_city(value: object) -> str:
    text = _text(value)
    for suffix in ("特别行政区", "自治区", "自治州", "地区", "市"):
        if text.endswith(suffix) and len(text) > len(suffix):
            return text[:-len(suffix)]
    return text


def _name_score(wanted: str, actual: str) -> float:
    left, right = _normalized(wanted), _normalized(actual)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if left in right or right in left:
        short, long = sorted((len(left), len(right)))
        return 0.82 + 0.12 * short / max(long, 1)
    return SequenceMatcher(None, left, right).ratio()


def _city_score(place: dict[str, Any], city: str) -> float:
    expected_city = _normalized_city(city)
    actuals = {
        value
        for value in (
            _normalized_city(place.get("city")),
            _normalized_city(place.get("district")),
        )
        if value
    }
    if not expected_city or not actuals:
        return 0.25
    if expected_city in actuals:
        return 1.0
    if any(expected_city in actual or actual in expected_city for actual in actuals):
        return 0.65
    return 0.0


def rank_places(
    places: list[dict[str, Any]],
    name: str,
    city: str,
) -> list[dict[str, Any]]:
    """只排序地点候选，不按名称、城市、品类或 type 丢弃结果。"""
    return sorted(
        (place for place in places if isinstance(place, dict)),
        key=lambda place: (
            _name_score(name, _text(place.get("name"))),
            _city_score(place, city),
        ),
        reverse=True,
    )


def _build_place(place: dict[str, Any], requested_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    location = _valid_location(place.get("location"))
    if not location:
        return {}, {}
    resolved: dict[str, Any] = {"location": location}
    for key in ("address", "phone"):
        text = _text(place.get(key))
        if text:
            resolved[key] = text
    category = display_category(_text(place.get("rawCategory") or place.get("category")))
    if category:
        resolved["category"] = category
    official = _text(place.get("name"))
    if official and official != requested_name:
        resolved["title"] = official
    meta = {
        "provider": "tencent",
        "providerId": _text(place.get("providerId")),
        "province": _text(place.get("province")),
        "city": _text(place.get("city")),
        "district": _text(place.get("district")),
        "adcode": _text(place.get("adcode")),
        "rawCategory": _text(place.get("rawCategory") or place.get("category")),
        "coordinateSystem": _text(place.get("coordinateSystem")) or "GCJ-02",
    }
    for key in ("category_code", "type"):
        value = place.get(key)
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            meta[key] = value
    request_id = _text(place.get("requestId"))
    if request_id:
        meta["requestId"] = request_id
    return resolved, meta


def _candidate_record(place: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": "tencent",
        "providerId": _text(place.get("providerId")),
        "name": _text(place.get("name")),
        "city": _text(place.get("city")),
        "district": _text(place.get("district")),
        "address": _text(place.get("address")),
        "location": _valid_location(place.get("location")),
        "category": _text(place.get("rawCategory") or place.get("category")),
    }


def _selection_required(name: str, places: list[dict[str, Any]]) -> bool:
    wanted = _normalized(name)
    exact_entities = {
        _text(place.get("providerId"))
        or "|".join(
            (
                _normalized(place.get("name")),
                _text(place.get("address")),
                _text(place.get("city")),
            )
        )
        for place in places
        if _normalized(place.get("name")) == wanted
    }
    return len(exact_entities) != 1


def resolve_place_with_status(name: str, city: str) -> dict[str, Any]:
    if not name or not city:
        return {"status": "invalid_argument", "error": {"code": "CITY_OR_NAME_MISSING", "retryable": False}}
    if not available():
        return {"status": "provider_unavailable", "error": {"code": "CONFIG_MISSING", "provider": "tencent", "retryable": False}}
    try:
        response = api.query_place(
            {"keyword": name, "city": city, "limit": 20, "autoExtend": True}
        )
    except api.ApiError as exc:
        return {"status": "provider_unavailable", "error": exc.as_dict()}
    places = response.get("places")
    if not isinstance(places, list):
        return {"status": "provider_unavailable", "error": {"code": "BAD_RESPONSE", "provider": "tencent", "retryable": False}}
    request_id = _text(response.get("requestId"))
    if request_id:
        places = [
            ({**place, "requestId": place.get("requestId") or request_id} if isinstance(place, dict) else place)
            for place in places
        ]
    ranked = rank_places(
        [place for place in places if isinstance(place, dict)], name, city
    )
    result: dict[str, Any] = {"status": "present" if ranked else "no_result"}
    if ranked:
        best = ranked[0]
        values, meta = _build_place(best, name)
        if not values:
            result["status"] = "provider_unavailable"
            result["error"] = {"code": "BAD_COORDINATE", "provider": "tencent", "retryable": False}
        else:
            result["values"] = values
            result["meta"] = meta
            result["candidates"] = [_candidate_record(place) for place in ranked[:5]]
            result["selectionRequired"] = _selection_required(name, ranked)
            result["fields"] = {
                key: ("present" if values.get(key) not in (None, "", [], {}) else "not_returned")
                for key in ("location", "address", "phone", "category", "title")
            }
    return result


def resolve_place(name: str, city: str = "") -> dict[str, Any] | None:
    report = resolve_place_with_status(name, city)
    return report.get("values") if report.get("status") == "present" else None


def resolve_places_with_status(names: list[str], city: str) -> dict[str, Any]:
    unique = [name for name in dict.fromkeys(_text(value) for value in names) if name]
    if not unique:
        return {"items": {}, "reports": {}}
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(unique))) as pool:
        pairs = pool.map(lambda name: (name, resolve_place_with_status(name, city)), unique)
    reports = dict(pairs)
    items = {
        name: report["values"]
        for name, report in reports.items()
        if report.get("status") == "present" and isinstance(report.get("values"), dict)
    }
    # 整批关键词全空更像数据源或配置异常，标注出来交由调用方缩短负缓存并上报。
    if not items:
        for report in reports.values():
            report["batchEmpty"] = True
    return {"items": items, "reports": reports}


def resolve_places(names: list[str], city: str = "") -> dict[str, dict[str, Any]]:
    return resolve_places_with_status(names, city)["items"]


def resolve_location_by_address(name: str, city: str) -> dict[str, Any]:
    if not name or not city:
        return {
            "status": "invalid_argument",
            "error": {"code": "CITY_OR_NAME_MISSING", "retryable": False},
        }
    if not available():
        return {
            "status": "provider_unavailable",
            "error": {
                "code": "CONFIG_MISSING",
                "provider": "tencent",
                "retryable": False,
            },
        }
    try:
        result = api.query_geocode({"address": f"{city}{name}"})
    except api.ApiError as exc:
        return {"status": "provider_unavailable", "error": exc.as_dict()}
    location = _valid_location(result.get("location"))
    if not location:
        return {
            "status": "no_result",
            "fields": {"location": "not_returned"},
        }
    values = {"location": location}
    return {
        "status": "present",
        "values": values,
        "fields": {"location": "present"},
        "meta": {
            "provider": "tencent-geocode",
            "province": _text(result.get("province")),
            "city": _text(result.get("city")),
            "district": _text(result.get("district")),
            "adcode": _text(result.get("adcode")),
            "address": _text(result.get("address")),
            "coordinateSystem": "GCJ-02",
            "requestId": _text(result.get("requestId")),
        },
    }


def _polyline_from(data: dict[str, Any]) -> list[dict[str, float]]:
    points = []
    for point in data.get("coords") or []:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            return []
        location = _valid_location({"lat": point[0], "lng": point[1]})
        if not location:
            return []
        if not points or location != points[-1]:
            points.append(location)
    return points if len(points) >= 2 else []


def _route_request(
    origin: dict[str, float],
    destination: dict[str, float],
    route_type: str,
    *,
    with_steps: bool = True,
) -> dict[str, Any]:
    return api.query_route({
        "from": f"{origin['lat']},{origin['lng']}",
        "to": f"{destination['lat']},{destination['lng']}",
        "mode": route_type,
        "noStep": not with_steps,
    })


def resolve_route_with_status(
    origin: dict,
    destination: dict,
    mode: str,
    *,
    needs_geometry: bool = True,
) -> dict[str, Any]:
    if mode not in VALID_MODES:
        return {"status": "invalid_mode", "error": {"code": "INVALID_MODE", "retryable": False}}
    start, end = _valid_location(origin), _valid_location(destination)
    if not start or not end:
        return {"status": "invalid_argument", "error": {"code": "BAD_COORDINATE", "retryable": False}}
    if not available():
        return {"status": "provider_unavailable", "error": {"code": "CONFIG_MISSING", "provider": "tencent", "retryable": False}}
    route_type = _ROUTE_MODES[mode]
    route_types = (
        ("driving", "walking", "bicycling")
        if route_type == "driving"
        else (route_type,)
    )
    data: dict[str, Any] = {}
    values: dict[str, Any] = {}
    geometry_mode = route_type
    for candidate_type in route_types:
        try:
            candidate = _route_request(
                start, end, candidate_type, with_steps=needs_geometry
            )
        except api.ApiError as exc:
            if candidate_type == route_type:
                return {"status": "provider_unavailable", "error": exc.as_dict()}
            continue
        candidate_values: dict[str, Any] = {}
        distance = _finite(candidate.get("distance"))
        duration = _finite(candidate.get("duration"))
        if distance is not None and distance > 0:
            candidate_values["distance"] = format_distance(distance)
        if duration is not None and duration > 0:
            candidate_values["duration"] = f"{max(1, round(duration))}分钟"
        polyline = _polyline_from(candidate)
        if polyline:
            candidate_values["polyline"] = polyline
        data, values, geometry_mode = candidate, candidate_values, candidate_type
        if values:
            break

    fields = {
        key: ("present" if values.get(key) not in (None, "", [], {}) else "not_returned")
        for key in ("distance", "duration", "polyline")
    }
    status = "present" if all(value == "present" for value in fields.values()) else "partial"
    result: dict[str, Any] = {
        "status": status,
        "values": values,
        "fields": fields,
        "meta": {
            "provider": "tencent",
            "mode": route_type,
            "geometryMode": geometry_mode,
            "coordinateSystem": "GCJ-02",
        },
    }
    request_id = _text(data.get("requestId"))
    if request_id:
        result["meta"]["requestId"] = request_id
    return result


def resolve_route(origin: dict, destination: dict, mode: str) -> dict[str, Any] | None:
    report = resolve_route_with_status(origin, destination, mode)
    return report.get("values") if report.get("status") in ("present", "partial") else None


def resolve_routes_with_status(segments: list[tuple]) -> dict[str, Any]:
    """段落元组是 `(key, origin, destination, mode[, needs_geometry])`。

    全部逐段调 direction。曾经把只要距离时长的段落合批走距离矩阵，但腾讯的每秒配额
    是按「起点数 × 终点数」的格子扣的，而合批只用得上对角线：k 段要扣 k² 格却只取 k 个。
    direction 每段只扣 1 格，还顺带给了折线，比矩阵既便宜又完整。
    needs_geometry 为假的段落不需要折线，用 no_step 砍掉回包里的路线引导。
    """
    if not segments:
        return {"items": {}, "reports": {}}

    def resolve(segment: tuple) -> tuple[Any, dict[str, Any]]:
        key, origin, destination, mode = segment[:4]
        needs_geometry = segment[4] if len(segment) > 4 else True
        return key, resolve_route_with_status(
            origin, destination, mode, needs_geometry=needs_geometry
        )

    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(segments))) as pool:
        reports: dict[Any, dict[str, Any]] = dict(pool.map(resolve, segments))
    return {
        "items": {
            key: report["values"]
            for key, report in reports.items()
            if report.get("status") in ("present", "partial") and isinstance(report.get("values"), dict)
        },
        "reports": reports,
    }


def resolve_routes(segments: list[tuple]) -> dict:
    return resolve_routes_with_status(segments)["items"]
