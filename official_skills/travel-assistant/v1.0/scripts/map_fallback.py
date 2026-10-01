#!/usr/bin/env python3
"""在 tencent-map 未部署时提供腾讯位置服务的内置实现。

仅实现 companion.py 与 provider_api.py 使用的四个入口：request、place、weather 和
geocode。保持输出结构与 map_query 一致。

请求只包含业务参数，由 Sandbox NetworkPolicy 为腾讯地图接口注入凭证。
"""

from __future__ import annotations

import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BASE_URL = os.environ.get("TENCENT_MAP_API_BASE", "https://apis.map.qq.com").rstrip("/")

_RETRYABLE_STATUSES = {120, 500, 510, 520, 530}
_MIN_INTERVAL = float(os.environ.get("TENCENT_MAP_MIN_INTERVAL", "0.25"))
_TIMEOUT = 15
_MAX_RETRY = 3
_COORD_RE = re.compile(r"\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)\s*")

_last_request_at = 0.0


class MapError(Exception):
    """与 tencent-map 的 MapError 同名同形，便于两份实现互换。"""

    def __init__(self, code: str, message: str, status: int | None = None, hint: str = ""):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.hint = hint

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"ok": False, "code": self.code, "message": self.message}
        if self.status is not None:
            payload["status"] = self.status
        if self.hint:
            payload["hint"] = self.hint
        return payload


def _fail(message: str, hint: str = "") -> None:
    raise MapError("INVALID_ARGUMENT", message, hint=hint)


def _throttle() -> None:
    global _last_request_at
    wait = _MIN_INTERVAL - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


def _url(path: str, params: dict[str, Any]) -> str:
    cleaned = {k: str(v) for k, v in params.items() if v not in (None, "")}
    return f"{BASE_URL}{path}?{urllib.parse.urlencode(cleaned)}"


def _fetch(url: str) -> dict[str, Any]:
    last: MapError | None = None
    for attempt in range(_MAX_RETRY):
        _throttle()
        try:
            with urllib.request.urlopen(url, timeout=_TIMEOUT) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last = MapError("HTTP_ERROR", f"HTTP {exc.code}", hint="检查网络或稍后重试")
        except (urllib.error.URLError, TimeoutError) as exc:
            last = MapError("NETWORK_ERROR", str(getattr(exc, "reason", exc)))
        except ValueError:
            last = MapError("BAD_RESPONSE", "响应不是合法 JSON")
        else:
            if not isinstance(payload, dict):
                raise MapError("BAD_RESPONSE", "响应根节点必须是对象")
            status = payload.get("status")
            if status == 0:
                return payload
            message = str(payload.get("message") or "接口返回失败")
            code = "RETRYABLE" if status in _RETRYABLE_STATUSES else "REQUEST_REJECTED"
            error = MapError(code, message, status=status if isinstance(status, int) else None)
            if code != "RETRYABLE":
                raise error
            last = error
        if attempt < _MAX_RETRY - 1:
            time.sleep(0.6 * (2 ** attempt))
    raise last or MapError("UNKNOWN", "请求失败")


def request(path: str, params: dict[str, Any]) -> dict[str, Any]:
    """发起一次 GET，返回 status=0 的原始响应；失败抛 MapError。"""
    return _fetch(_url(path, params))


def _coord(value: object, field: str) -> str:
    if not isinstance(value, str):
        _fail(f"{field} 必须是 '纬度,经度' 字符串")
    match = _COORD_RE.fullmatch(value)  # type: ignore[arg-type]
    if not match:
        _fail(f"{field} 格式应为 '纬度,经度'，收到 {value!r}")
    lat, lng = float(match.group(1)), float(match.group(2))
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        _fail(f"{field} 坐标超出范围")
    return f"{lat:.6f},{lng:.6f}"


def _location(raw: object) -> dict[str, float] | None:
    if not isinstance(raw, dict):
        return None
    try:
        lat, lng = float(raw.get("lat")), float(raw.get("lng"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lng)):
        return None
    return {"lat": round(lat, 6), "lng": round(lng, 6)}


def place(args: dict[str, Any]) -> dict[str, Any]:
    keyword = str(args.get("keyword") or "").strip()
    if not keyword:
        _fail("缺少必填参数 keyword")
    limit = max(1, min(int(args.get("limit", 10)), 20))
    if args.get("near"):
        radius = max(1, min(int(args.get("radius", 1000)), 50000))
        boundary = f"nearby({_coord(args['near'], 'near')},{radius})"
    else:
        city = str(args.get("city") or "").strip()
        if not city:
            _fail("缺少必填参数 city")
        boundary = f"region({city},{1 if args.get('auto_extend', True) else 0})"
    params: dict[str, Any] = {"keyword": keyword, "boundary": boundary, "page_size": limit}
    if args.get("order_by"):
        params["orderby"] = args["order_by"]
    data = request("/ws/place/v1/search", params)
    items = []
    for item in (data.get("data") or [])[:limit]:
        if not isinstance(item, dict):
            continue
        entry: dict[str, Any] = {
            "title": item.get("title"),
            "address": item.get("address"),
            "location": _location(item.get("location")),
            "category": item.get("category"),
        }
        if item.get("tel"):
            entry["phone"] = item["tel"]
        if isinstance(item.get("_distance"), (int, float)):
            entry["distance_m"] = round(float(item["_distance"]))
        items.append(entry)
    return {"count": data.get("count"), "items": items}


def weather(args: dict[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = {"type": args.get("type", "now")}
    if args.get("location"):
        params["location"] = _coord(args["location"], "location")
    elif args.get("adcode"):
        params["adcode"] = args["adcode"]
    else:
        _fail("需要 location 或 adcode")
    if args.get("added_fields"):
        params["added_fields"] = args["added_fields"]
    result = request("/ws/weather/v1/", params).get("result") or {}
    if params["type"] == "now":
        realtime = (result.get("realtime") or [{}])[0]
        info = realtime.get("infos") or {}
        return {
            "city": realtime.get("city"),
            "district": realtime.get("district"),
            "weather": info.get("weather"),
            "temperature": info.get("temperature"),
            "humidity": info.get("humidity"),
            "wind_direction": info.get("wind_direction"),
            "wind_power": info.get("wind_power"),
            "update_time": realtime.get("update_time"),
        }
    forecast = (result.get("forecast") or [{}])[0]
    return {
        "city": forecast.get("city"),
        # 接口实际给的是 date / day.weather / night.weather，不是 time / day_weather；
        # 读错字段整份预报会变成一串 None，而且不报错。老字段名一并兼容。
        "days": [
            {
                "date": day.get("date") or day.get("time"),
                "day_weather": (day.get("day") or {}).get("weather") or day.get("day_weather"),
                "night_weather": (day.get("night") or {}).get("weather") or day.get("night_weather"),
                "max_degree": (day.get("day") or {}).get("temperature") or day.get("max_degree"),
                "min_degree": (day.get("night") or {}).get("temperature") or day.get("min_degree"),
            }
            for day in (forecast.get("infos") or [])[:7]
        ],
    }


def geocode(args: dict[str, Any]) -> dict[str, Any]:
    address = str(args.get("address") or "").strip()
    if not address:
        _fail("缺少必填参数 address")
    params = {"address": address, "region": args.get("region") or args.get("city")}
    result = request("/ws/geocoder/v1/", params).get("result") or {}
    return {
        "location": _location(result.get("location")),
        "title": result.get("title"),
        "level": result.get("level"),
        "reliability": result.get("reliability"),
        "address_components": result.get("address_components"),
    }
