#!/usr/bin/env python3
"""同程网关与腾讯地图的受控查询层。

业务凭证由 Sandbox NetworkPolicy 托管并注入；本模块只请求原始业务地址，
不读取、保存或发送 Token/Key。所有网络、HTTP、业务码、响应结构错误均转换为
结构化 ``ApiError``；只对超时、408、429 和 502/503/504 做有限退避重试。
"""

from __future__ import annotations

import json
import math
import os
import random
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


GW_BASE = os.environ.get(
    "MY_TRAVEL_API_BASE",
    "https://arsenalgw.ly.com/gwai/gw/ai_datasets/yuanbao",
).strip()
TONGCHENG_KEY = os.environ.get("MY_TRAVEL_API_KEY", "").strip()
TENCENT_MAP_API_BASE = os.environ.get(
    "TENCENT_MAP_API_BASE", "https://apis.map.qq.com"
).strip()

ENDPOINTS = {
    "spot": "/site_list_rt",
    "hotel": "/main_bot/hotel_list_rt",
    "train": "/trainRealTime",
    "flight": "/flyRealTime",
    "iflight": "/iflyRealTime",
}
RETRY_HTTP_CODES = {408, 429, 502, 503, 504}
ROUTE_MODES = {"driving", "walking", "bicycling", "transit"}
SUCCESS_CODES = {0, "0", 200, "200", "0000", "SUCCESS", "success", "OK", "ok"}
MAX_BODY_BYTES = 2 * 1024 * 1024


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except ValueError:
        value = default
    return min(max(value, minimum), maximum)


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        value = default
    return min(max(value, minimum), maximum)


TIMEOUT = _env_float("MY_TRAVEL_API_TIMEOUT", 15.0, 1.0, 60.0)
MAX_RETRIES = _env_int("MY_TRAVEL_API_RETRIES", 2, 0, 4)
# 单个逻辑请求（含重试）的墙钟上限。渲染要在一次工具调用里完成，任何一个
# 请求把重试次数乘满超时时间都会拖垮整轮。
REQUEST_BUDGET = _env_float("MY_TRAVEL_API_BUDGET", 20.0, 2.0, 120.0)
RETRY_BASE_SECONDS = _env_float("MY_TRAVEL_API_RETRY_BASE", 0.25, 0.05, 2.0)
MAP_MAX_CONCURRENCY = _env_int("MY_TRAVEL_MAP_CONCURRENCY", 12, 1, 32)
# 一次渲染的地图请求数是「景点数 + 接驳段数 × 4」，成百上千毫秒的单次延迟本身
# 不是瓶颈，发包速率才是：闸门定在 5/秒时，60 次算路的墙钟下限就是 12 秒，
# 并发上限根本用不上。这里放宽到 15，再由 _throttle_map_requests 按实际
# 限流回包自动降档，不必预先猜 Key 的配额。
MAP_REQUESTS_PER_SECOND = _env_float("MY_TRAVEL_MAP_QPS", 15.0, 0.2, 100.0)
MAP_MIN_REQUESTS_PER_SECOND = _env_float("MY_TRAVEL_MAP_QPS_FLOOR", 2.0, 0.2, 100.0)
MAP_RATE_LIMIT_COOLDOWN = _env_float("MY_TRAVEL_MAP_RATE_COOLDOWN", 1.0, 0.1, 10.0)


class ApiError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        provider: str = "",
        retryable: bool = False,
        status: int | None = None,
        attempts: int = 1,
        request_id: str = "",
    ):
        self.code = code
        self.message = message
        self.provider = provider
        self.retryable = retryable
        self.status = status
        self.attempts = attempts
        self.request_id = request_id
        super().__init__(f"{code}: {message}")

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "attempts": self.attempts,
        }
        if self.provider:
            result["provider"] = self.provider
        if self.status is not None:
            result["status"] = self.status
        if self.request_id:
            result["requestId"] = self.request_id
        return result


_MAP_CONCURRENCY_GATE = threading.BoundedSemaphore(MAP_MAX_CONCURRENCY)
_MAP_STATE_LOCK = threading.Lock()
_MAP_NEXT_REQUEST_AT = 0.0
_MAP_BLOCKED_UNTIL = 0.0
_MAP_CIRCUIT_ERROR: ApiError | None = None
_MAP_RATE = MAP_REQUESTS_PER_SECOND


def _clone_api_error(error: ApiError) -> ApiError:
    return ApiError(
        error.code,
        error.message,
        provider=error.provider,
        retryable=error.retryable,
        status=error.status,
        attempts=error.attempts,
        request_id=error.request_id,
    )


def _wait_for_map_request() -> None:
    """在进程内共享腾讯请求节奏，并在确定性配置错误后快速失败。"""
    global _MAP_NEXT_REQUEST_AT
    while True:
        with _MAP_STATE_LOCK:
            if _MAP_CIRCUIT_ERROR is not None:
                raise _clone_api_error(_MAP_CIRCUIT_ERROR)
            now = time.monotonic()
            ready_at = max(_MAP_NEXT_REQUEST_AT, _MAP_BLOCKED_UNTIL)
            if ready_at <= now:
                _MAP_NEXT_REQUEST_AT = now + 1.0 / _MAP_RATE
                return
            delay = ready_at - now
        time.sleep(delay)


def _pause_map_requests(seconds: float) -> None:
    global _MAP_BLOCKED_UNTIL
    with _MAP_STATE_LOCK:
        _MAP_BLOCKED_UNTIL = max(_MAP_BLOCKED_UNTIL, time.monotonic() + seconds)


def _throttle_map_requests() -> None:
    """撞到限流就把本进程的发包速率砍半，不要反复用 429 去试探 Key 的配额。"""
    global _MAP_RATE
    with _MAP_STATE_LOCK:
        _MAP_RATE = max(MAP_MIN_REQUESTS_PER_SECOND, _MAP_RATE / 2.0)


def _trip_map_circuit(error: ApiError) -> None:
    global _MAP_CIRCUIT_ERROR
    with _MAP_STATE_LOCK:
        if _MAP_CIRCUIT_ERROR is None:
            _MAP_CIRCUIT_ERROR = _clone_api_error(error)


def _retry_delay(attempt: int, retry_after: str = "") -> float:
    if retry_after:
        try:
            return min(max(float(retry_after), 0.0), 5.0)
        except ValueError:
            pass
    return RETRY_BASE_SECONDS * (2 ** attempt) + random.uniform(0, RETRY_BASE_SECONDS / 2)


def _read_json_response(resp: Any, provider: str) -> dict[str, Any]:
    raw = resp.read(MAX_BODY_BYTES + 1)
    if len(raw) > MAX_BODY_BYTES:
        raise ApiError("RESPONSE_TOO_LARGE", f"{provider} 响应超过大小限制", provider=provider)
    text = raw.decode("utf-8", "replace")
    try:
        data = json.loads(text) if text.strip() else {}
    except json.JSONDecodeError as exc:
        raise ApiError("BAD_RESPONSE", f"{provider} 返回的不是合法 JSON", provider=provider) from exc
    if not isinstance(data, dict):
        raise ApiError("BAD_RESPONSE", f"{provider} 响应根节点必须是对象", provider=provider)
    return data


def _request_json(req: urllib.request.Request, provider: str) -> dict[str, Any]:
    last: ApiError | None = None
    started = time.monotonic()

    def out_of_budget(delay: float) -> bool:
        """还够不够时间再试一次。

        重试对快速失败（5xx、429）很划算，一次几十毫秒；但对连接超时就是纯亏：
        15 秒没回包的网关，再等两轮也是 15 秒，一个请求就能烧掉 45 秒。所以按
        「下一次尝试的最坏耗时是否会越过截止线」来决定，而不是只数次数。
        """
        return time.monotonic() - started + delay + TIMEOUT > REQUEST_BUDGET

    for attempt in range(MAX_RETRIES + 1):
        if provider == "tencent":
            _wait_for_map_request()
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return _read_json_response(resp, provider)
        except urllib.error.HTTPError as exc:
            retryable = exc.code in RETRY_HTTP_CODES
            detail = ""
            try:
                detail = exc.read(500).decode("utf-8", "replace").strip()
            except OSError:
                pass
            message = f"{provider} 返回 HTTP {exc.code}"
            if detail:
                message += f"：{detail[:300]}"
            last = ApiError(
                "HTTP_RETRYABLE" if retryable else "HTTP_ERROR",
                message,
                provider=provider,
                retryable=retryable,
                status=exc.code,
                attempts=attempt + 1,
            )
            retry_after = exc.headers.get("Retry-After", "") if exc.headers else ""
            delay = _retry_delay(attempt, retry_after)
            if provider == "tencent" and exc.code == 429:
                _pause_map_requests(delay)
                _throttle_map_requests()
            if not retryable or attempt >= MAX_RETRIES or out_of_budget(delay):
                raise last from exc
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            last = ApiError(
                "NETWORK_ERROR",
                f"请求 {provider} 失败：{getattr(exc, 'reason', exc)}",
                provider=provider,
                retryable=True,
                attempts=attempt + 1,
            )
            delay = _retry_delay(attempt)
            if attempt >= MAX_RETRIES or out_of_budget(delay):
                raise last from exc
            time.sleep(delay)
    raise last or ApiError("NETWORK_ERROR", f"请求 {provider} 失败", provider=provider)


def _request(method: str, url: str, provider: str, payload: dict | None = None) -> dict[str, Any]:
    body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("User-Agent", "curl/8.4.0")
    req.add_header("Accept", "application/json")
    if payload is not None:
        req.add_header("Content-Type", "application/json; charset=UTF-8")
    return _request_json(req, provider)


def _validate_tongcheng_response(data: dict[str, Any]) -> dict[str, Any]:
    if "success" in data and data["success"] is False:
        raise ApiError(
            "PROVIDER_ERROR",
            f"同程业务请求失败：{data.get('message') or data.get('msg') or 'unknown'}",
            provider="tongcheng",
        )
    for key in ("code", "errorCode"):
        if key in data and data[key] not in SUCCESS_CODES and data[key] not in (None, ""):
            raise ApiError(
                "PROVIDER_ERROR",
                f"同程业务码 {data[key]}：{data.get('message') or data.get('msg') or '请求失败'}",
                provider="tongcheng",
            )
    return data


def _post_json(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not GW_BASE:
        raise ApiError(
            "CONFIG_MISSING",
            "缺少 MY_TRAVEL_API_BASE",
            provider="tongcheng",
        )
    url = GW_BASE.rstrip("/") + "/" + path.lstrip("/")
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json; charset=UTF-8")
    req.add_header("User-Agent", "curl/8.4.0")
    req.add_header("Accept", "application/json")
    # 同程网关按 Authorization 鉴权，值是裸 key，不加 Bearer 前缀。
    # 沙箱内由平台注入；开发机不设就是「业务码 401：无权限」。
    if TONGCHENG_KEY:
        req.add_header("Authorization", TONGCHENG_KEY)
    return _validate_tongcheng_response(_request_json(req, "tongcheng"))


def _get_json(url: str) -> dict[str, Any]:
    with _MAP_CONCURRENCY_GATE:
        return _request("GET", url, "tencent")


def query_spot(args: dict[str, Any]) -> dict[str, Any]:
    city = str(args.get("cityName") or args.get("city") or "").strip()
    if not city:
        raise ApiError("INVALID_ARGUMENT", "spot 查询需要 cityName")
    raw = args.get("keywords")
    if raw is None:
        raw = [args.get("keyword")]
    if not isinstance(raw, list):
        raise ApiError("INVALID_ARGUMENT", "keywords 必须是字符串数组")
    keywords: list[str] = []
    for value in raw:
        if value is None:
            continue
        if not isinstance(value, str):
            raise ApiError("INVALID_ARGUMENT", "keywords 必须是字符串数组")
        text = value.strip()
        if text and text not in keywords:
            keywords.append(text)
    if not keywords:
        raise ApiError("INVALID_ARGUMENT", "spot 查询至少需要一个 keyword")
    return _post_json(
        ENDPOINTS["spot"],
        {"qryDetail": [{"keyword": keyword, "cityName": city} for keyword in keywords]},
    )


def query_hotel(args: dict[str, Any]) -> dict[str, Any]:
    city = str(args.get("city") or args.get("cityName") or "").strip()
    if not city:
        raise ApiError("INVALID_ARGUMENT", "hotel 查询需要 city")
    payload: dict[str, Any] = {"city": city}
    for key in (
        "brand", "keywords", "center", "distance", "facilities", "grade",
        "province", "impressionTags", "sortType", "sortDirection", "star",
        "type", "pageIndex", "pageSize", "intents", "cost", "checkin",
        "checkout", "coordinate",
    ):
        value = args.get(key)
        if value not in (None, "", [], {}):
            payload[key] = value
    return _post_json(ENDPOINTS["hotel"], payload)


def _route_payload(args: dict[str, Any], endpoint_key: str) -> dict[str, Any]:
    dep = str(args.get("depCityName") or args.get("depCity") or "").strip()
    arr = str(args.get("arrCityName") or args.get("arrCity") or "").strip()
    date = str(args.get("depDate") or args.get("date") or "").strip()
    if not dep or not arr:
        raise ApiError("INVALID_ARGUMENT", f"{endpoint_key} 查询需要出发与到达城市")
    payload = {"depCityName": dep, "arrCityName": arr}
    if date:
        payload["depDate"] = date
    return _post_json(ENDPOINTS[endpoint_key], payload)


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _coord_pair(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ApiError("INVALID_ARGUMENT", f"{name} 必须是 lat,lng")
    match = re.fullmatch(r"\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)\s*", value)
    if not match:
        raise ApiError("INVALID_ARGUMENT", f"{name} 必须是 lat,lng")
    lat, lng = float(match.group(1)), float(match.group(2))
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ApiError("INVALID_ARGUMENT", f"{name} 坐标超出范围")
    return f"{lat:.7f},{lng:.7f}"


def _decode_polyline(coors: object) -> list[list[float]]:
    if not isinstance(coors, list) or len(coors) < 4 or len(coors) % 2:
        return []
    values: list[float] = []
    for value in coors:
        number = _finite_number(value)
        if number is None:
            return []
        values.append(number)
    for index in range(2, len(values)):
        values[index] = values[index - 2] + values[index] / 1_000_000.0
    points = []
    for index in range(0, len(values), 2):
        lat, lng = values[index], values[index + 1]
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            return []
        points.append([lat, lng])
    return points


def _route_coords(route: dict[str, Any]) -> list[list[float]]:
    """方向接口顶层 polyline 就是所请求交通方式的真实路网几何。"""
    return _decode_polyline(route.get("polyline"))


def _map_status_number(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if str(value).strip() == str(number) else None


def _validate_map_response(data: dict[str, Any], action: str) -> dict[str, Any]:
    raw_status = data.get("status")
    status = _map_status_number(raw_status)
    if status == 0:
        return data
    message = str(data.get("message") or raw_status or "unknown")
    request_id = str(data.get("request_id") or data.get("requestId") or "").strip()
    lowered = message.lower()
    auth_statuses = {110, 111, 112, 113, 160, 161, 190, 199}
    if status == 120:
        code, retryable = "MAP_RATE_LIMIT", True
    elif status == 121:
        code, retryable = "MAP_DAILY_QUOTA", False
    elif status in auth_statuses:
        code, retryable = "MAP_AUTH", False
    elif status in {500, 510, 520, 530, 531, 600}:
        code, retryable = "MAP_SERVICE_ERROR", True
    elif any(word in lowered for word in ("签名", "鉴权", "未授权", "无效的key", "invalid key")):
        code, retryable = "MAP_AUTH", False
    elif any(word in lowered for word in ("每日", "daily quota", "日配额")):
        code, retryable = "MAP_DAILY_QUOTA", False
    elif any(word in lowered for word in ("每秒", "qps", "rate limit", "频率")):
        code, retryable = "MAP_RATE_LIMIT", True
    else:
        code, retryable = "MAP_ERROR", False
    error = ApiError(
        code,
        f"{action}失败：{message}",
        provider="tencent",
        retryable=retryable,
        status=status,
        request_id=request_id,
    )
    if code == "MAP_RATE_LIMIT":
        _pause_map_requests(MAP_RATE_LIMIT_COOLDOWN)
        _throttle_map_requests()
    elif code in ("MAP_DAILY_QUOTA", "MAP_AUTH"):
        _trip_map_circuit(error)
    raise error


def query_route(args: dict[str, Any]) -> dict[str, Any]:
    if not TENCENT_MAP_API_BASE:
        raise ApiError("CONFIG_MISSING", "缺少 TENCENT_MAP_API_BASE", provider="tencent")
    origin = _coord_pair(args.get("from"), "from")
    destination = _coord_pair(args.get("to"), "to")
    mode = str(args.get("mode") or "driving").strip()
    if mode not in ROUTE_MODES:
        raise ApiError("INVALID_ARGUMENT", "mode 必须是 driving/walking/bicycling/transit")
    params: dict[str, Any] = {
        "from": origin,
        "to": destination,
    }
    if args.get("noStep"):
        # 备选交通方式只展示距离和时长，路线引导是纯浪费的回包体积。
        params["no_step"] = 1
    waypoints = args.get("waypoints")
    if waypoints not in (None, []):
        if not isinstance(waypoints, list):
            raise ApiError("INVALID_ARGUMENT", "waypoints 必须是坐标数组")
        params["waypoints"] = ";".join(
            _coord_pair(value, "waypoints") for value in waypoints
        )
    url = TENCENT_MAP_API_BASE.rstrip("/") + "/ws/direction/v1/" + mode + "?" + urllib.parse.urlencode(params)
    data = _validate_map_response(_get_json(url), "算路")
    result = data.get("result")
    if not isinstance(result, dict):
        raise ApiError("BAD_RESPONSE", "地图算路缺少 result", provider="tencent")
    routes = result.get("routes")
    if not isinstance(routes, list):
        raise ApiError("BAD_RESPONSE", "地图算路 routes 格式错误", provider="tencent")
    if not routes:
        response: dict[str, Any] = {"coords": [], "distance": None, "duration": None}
        request_id = str(data.get("request_id") or data.get("requestId") or "").strip()
        if request_id:
            response["requestId"] = request_id
        return response
    first = routes[0]
    if not isinstance(first, dict):
        raise ApiError("BAD_RESPONSE", "地图算路 route 格式错误", provider="tencent")
    response = {
        "coords": _route_coords(first),
        "distance": _finite_number(first.get("distance")),
        "duration": _finite_number(first.get("duration")),
    }
    request_id = str(data.get("request_id") or data.get("requestId") or "").strip()
    if request_id:
        response["requestId"] = request_id
    return response


def query_place(args: dict[str, Any]) -> dict[str, Any]:
    if not TENCENT_MAP_API_BASE:
        raise ApiError("CONFIG_MISSING", "缺少 TENCENT_MAP_API_BASE", provider="tencent")
    keyword = str(args.get("keyword") or args.get("name") or "").strip()
    city = str(args.get("city") or args.get("cityName") or "").strip()
    if not keyword:
        raise ApiError("INVALID_ARGUMENT", "place 查询需要 keyword")
    if not city:
        raise ApiError("INVALID_ARGUMENT", "place 查询需要 city，禁止无城市全局匹配")
    limit = args.get("limit")
    page_size = limit if isinstance(limit, int) and not isinstance(limit, bool) and 1 <= limit <= 20 else 20
    auto_extend = args.get("autoExtend") is True

    def search(region_auto_extend: int) -> tuple[dict[str, Any], list[Any]]:
        params = {
            "keyword": keyword,
            "boundary": f"region({city},{region_auto_extend})",
            "page_size": page_size,
            "added_fields": "category_code",
        }
        url = (
            TENCENT_MAP_API_BASE.rstrip("/")
            + "/ws/place/v1/search?"
            + urllib.parse.urlencode(params)
        )
        payload = _validate_map_response(_get_json(url), "地点搜索")
        raw = payload.get("data")
        if not isinstance(raw, list):
            raise ApiError(
                "BAD_RESPONSE",
                "地点搜索 data 格式错误",
                provider="tencent",
            )
        return payload, raw

    def normalize(
        payload: dict[str, Any],
        raw_places: list[Any],
    ) -> tuple[list[dict[str, Any]], str]:
        request_id = str(
            payload.get("request_id") or payload.get("requestId") or ""
        ).strip()
        places: list[dict[str, Any]] = []
        for item in raw_places:
            if not isinstance(item, dict):
                continue
            location = item.get("location")
            if not isinstance(location, dict):
                continue
            lat = _finite_number(location.get("lat"))
            lng = _finite_number(location.get("lng"))
            if (
                lat is None
                or lng is None
                or not (-90 <= lat <= 90 and -180 <= lng <= 180)
            ):
                continue
            ad_info = item.get("ad_info") if isinstance(item.get("ad_info"), dict) else {}
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            raw_category = str(item.get("category") or "").strip()
            place: dict[str, Any] = {
                "providerId": str(item.get("id") or ""),
                "name": title,
                "location": {"lat": lat, "lng": lng},
                "coordinateSystem": "GCJ-02",
                "address": str(item.get("address") or "").strip(),
                "phone": str(item.get("tel") or "").strip(),
                "category": raw_category,
                "rawCategory": raw_category,
                "province": str(
                    ad_info.get("province") or item.get("province") or ""
                ).strip(),
                "city": str(ad_info.get("city") or item.get("city") or "").strip(),
                "district": str(
                    ad_info.get("district") or item.get("district") or ""
                ).strip(),
                "adcode": str(
                    ad_info.get("adcode") or item.get("adcode") or ""
                ).strip(),
            }
            for key in ("category_code", "type"):
                value = item.get(key)
                if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                    place[key] = value
            if request_id:
                place["requestId"] = request_id
            places.append(place)
        return places, request_id

    data, raw_places = search(0)
    places, request_id = normalize(data, raw_places)
    if not places and auto_extend:
        data, raw_places = search(1)
        places, request_id = normalize(data, raw_places)
    response = {"places": places}
    if request_id:
        response["requestId"] = request_id
    return response


def query_geocode(args: dict[str, Any]) -> dict[str, Any]:
    if not TENCENT_MAP_API_BASE:
        raise ApiError("CONFIG_MISSING", "缺少 TENCENT_MAP_API_BASE", provider="tencent")
    address = str(args.get("address") or "").strip()
    if not address:
        raise ApiError("INVALID_ARGUMENT", "geocode 查询需要 address")
    params = {"address": address}
    url = (
        TENCENT_MAP_API_BASE.rstrip("/")
        + "/ws/geocoder/v1/?"
        + urllib.parse.urlencode(params)
    )
    data = _validate_map_response(_get_json(url), "地址解析")
    result = data.get("result")
    if not isinstance(result, dict):
        raise ApiError("BAD_RESPONSE", "地址解析缺少 result", provider="tencent")
    raw_location = result.get("location")
    if not isinstance(raw_location, dict):
        return {"location": None}
    lat = _finite_number(raw_location.get("lat"))
    lng = _finite_number(raw_location.get("lng"))
    if lat is None or lng is None or not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return {"location": None}
    components = (
        result.get("address_components")
        if isinstance(result.get("address_components"), dict)
        else {}
    )
    ad_info = result.get("ad_info") if isinstance(result.get("ad_info"), dict) else {}
    response: dict[str, Any] = {
        "location": {"lat": lat, "lng": lng},
        "address": str(result.get("address") or address).strip(),
        "province": str(components.get("province") or "").strip(),
        "city": str(components.get("city") or "").strip(),
        "district": str(components.get("district") or "").strip(),
        "adcode": str(ad_info.get("adcode") or "").strip(),
    }
    request_id = str(data.get("request_id") or data.get("requestId") or "").strip()
    if request_id:
        response["requestId"] = request_id
    return response


def query_train(args: dict[str, Any]) -> dict[str, Any]:
    return _route_payload(args, "train")


def query_flight(args: dict[str, Any]) -> dict[str, Any]:
    return _route_payload(args, "flight")


def query_iflight(args: dict[str, Any]) -> dict[str, Any]:
    return _route_payload(args, "iflight")


HANDLERS = {
    "spot": query_spot,
    "hotel": query_hotel,
    "train": query_train,
    "flight": query_flight,
    "iflight": query_iflight,
    "route": query_route,
    "place": query_place,
    "geocode": query_geocode,
}


def run(args: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(args, dict):
        raise ApiError("INVALID_ARGUMENT", "参数必须是对象")
    qtype = str(args.get("type") or "").strip()
    handler = HANDLERS.get(qtype)
    if not handler:
        raise ApiError(
            "UNKNOWN_TYPE",
            f"不支持的查询类型：{qtype or '(空)'}；可用：{', '.join(sorted(HANDLERS))}",
        )
    return {"type": qtype, "data": handler({key: value for key, value in args.items() if key != "type"})}


def main() -> int:
    raw = sys.argv[1] if len(sys.argv) > 1 else "{}"
    try:
        args = json.loads(raw)
        result = run(args)
    except json.JSONDecodeError:
        result = {"phase": "error", "code": "INVALID_JSON", "message": "请求参数不是合法 JSON", "retryable": False}
    except ApiError as exc:
        result = {"phase": "error", **exc.as_dict()}
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
