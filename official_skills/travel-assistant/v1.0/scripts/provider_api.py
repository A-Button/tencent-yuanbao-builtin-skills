#!/usr/bin/env python3
"""通过同程网关与腾讯地图解析落地页所需的真实业务 ID。

与 travel_plan/scripts/api.py 同源：业务凭证由 Sandbox NetworkPolicy 托管注入，
本模块只请求脚本内固定的原始业务地址，不读取、保存或传递 Token/Key。

同程走 MY_TRAVEL_API_BASE；腾讯复用 tencent-map 的 map_client（它已处理 key 解析、
SN 签名与发包节流），避免在这里重造一份鉴权逻辑。
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

GW_BASE = os.environ.get(
    "MY_TRAVEL_API_BASE",
    "https://arsenalgw.ly.com/gwai/gw/ai_datasets/yuanbao",
).strip()
SPOT_ENDPOINT = "/site_list_rt"
# 同程网关按 Authorization 鉴权，值是裸 key，**不加 Bearer 前缀**——加了照样 401。
# 沙箱里由 NetworkPolicy 注入，开发机需要自己给，否则所有同程调用都是「业务码 401：无权限」。
TONGCHENG_KEY = os.environ.get("MY_TRAVEL_API_KEY", "").strip()
SUCCESS_CODES = {0, "0", 200, "200", "0000", "SUCCESS", "success", "OK", "ok"}
RETRY_HTTP_CODES = {408, 429, 502, 503, 504}
MAX_BODY_BYTES = 2 * 1024 * 1024
# 落地页解析仅占卡片组装的一步，因此使用比 travel_plan 更短的超时预算。
TIMEOUT = 8.0
MAX_RETRIES = 1


class ProviderError(RuntimeError):
    def __init__(self, code: str, message: str, *, provider: str, retryable: bool = False):
        self.code = code
        self.message = message
        self.provider = provider
        self.retryable = retryable
        super().__init__(f"{code}: {message}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": False,
            "rule": self.code,
            "message": self.message,
            "provider": self.provider,
            "retryable": self.retryable,
        }


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _post_json(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not GW_BASE:
        raise ProviderError("CONFIG_MISSING", "缺少 MY_TRAVEL_API_BASE", provider="tongcheng")
    url = GW_BASE.rstrip("/") + "/" + path.lstrip("/")
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    last: ProviderError | None = None
    for attempt in range(MAX_RETRIES + 1):
        request = urllib.request.Request(url, data=body, method="POST")
        request.add_header("Content-Type", "application/json; charset=UTF-8")
        request.add_header("User-Agent", "curl/8.4.0")
        request.add_header("Accept", "application/json")
        if TONGCHENG_KEY:
            request.add_header("Authorization", TONGCHENG_KEY)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                raw = response.read(MAX_BODY_BYTES + 1)
            if len(raw) > MAX_BODY_BYTES:
                raise ProviderError("RESPONSE_TOO_LARGE", "同程响应超过大小限制", provider="tongcheng")
            text = raw.decode("utf-8", "replace")
            data = json.loads(text) if text.strip() else {}
            if not isinstance(data, dict):
                raise ProviderError("BAD_RESPONSE", "同程响应根节点必须是对象", provider="tongcheng")
            return _validate(data)
        except urllib.error.HTTPError as exc:
            retryable = exc.code in RETRY_HTTP_CODES
            last = ProviderError(
                "HTTP_RETRYABLE" if retryable else "HTTP_ERROR",
                f"同程返回 HTTP {exc.code}",
                provider="tongcheng",
                retryable=retryable,
            )
            if not retryable or attempt >= MAX_RETRIES:
                raise last from exc
        except json.JSONDecodeError as exc:
            raise ProviderError("BAD_RESPONSE", "同程返回的不是合法 JSON", provider="tongcheng") from exc
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            last = ProviderError(
                "NETWORK_ERROR",
                f"请求同程失败：{getattr(exc, 'reason', exc)}",
                provider="tongcheng",
                retryable=True,
            )
            if attempt >= MAX_RETRIES:
                raise last from exc
        time.sleep(0.25 * (2 ** attempt))
    raise last or ProviderError("NETWORK_ERROR", "请求同程失败", provider="tongcheng")


def _validate(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("success") is False:
        raise ProviderError(
            "PROVIDER_ERROR",
            f"同程业务请求失败：{data.get('message') or data.get('msg') or 'unknown'}",
            provider="tongcheng",
        )
    for key in ("code", "errorCode"):
        value = data.get(key)
        if key in data and value not in SUCCESS_CODES and value not in (None, ""):
            raise ProviderError(
                "PROVIDER_ERROR",
                _code_message(value, data),
                provider="tongcheng",
            )
    return data


def _code_message(value: object, data: dict[str, Any]) -> str:
    detail = data.get("message") or data.get("msg") or "请求失败"
    if str(value) == "401":
        # 这个 401 反复被当成代码坏了排查，直接把原因和出口写进报错。
        missing = "未配置 MY_TRAVEL_API_KEY" if not TONGCHENG_KEY else "当前 key 无权限"
        return (
            f"同程网关鉴权失败（{missing}）。key 走 Authorization 头、裸值不加 Bearer；"
            "沙箱内由平台注入，开发机需自行设置 MY_TRAVEL_API_KEY。"
            "取不到就按 data-sources.md 降级，不要改用 web_search 顶替字段。"
        )
    return f"同程业务码 {value}：{detail}"


def _query_params(url: str) -> dict[str, str]:
    if not url:
        return {}
    try:
        query = urllib.parse.urlsplit(url).query
    except ValueError:
        return {}
    return {key: value for key, value in urllib.parse.parse_qsl(query) if value}


def _normalized(value: object) -> str:
    return "".join(_text(value).split()).lower()


def _image_url(value: object) -> str:
    """将同程 CDN 图片地址规范化为卡片支持的 HTTPS 地址。"""
    url = _text(value)
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("http://"):
        url = "https://" + url[len("http://"):]
    if not url.startswith("https://"):
        return ""
    if " " in url or len(url) > 1024:
        return ""
    return url


def _images(item: dict[str, Any], limit: int = 5) -> list[str]:
    raw = item.get("pic")
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    found: list[str] = []
    for value in raw:
        url = _image_url(value)
        if url and url not in found:
            found.append(url)
        if len(found) >= limit:
            break
    return found


def _spot_candidates(payload: dict[str, Any], city: str, keyword: str) -> list[dict[str, Any]]:
    """按规范化后的 `<城市>_<关键词>` 匹配分组结果。"""
    groups = payload.get("data")
    if not isinstance(groups, dict):
        return []
    direct = groups.get(f"{city}_{keyword}")
    if isinstance(direct, list):
        return [item for item in direct if isinstance(item, dict)]
    for key, value in groups.items():
        if not isinstance(key, str) or not isinstance(value, list):
            continue
        prefix, separator, suffix = key.rpartition("_")
        if separator and _normalized(prefix) == _normalized(city) and _normalized(suffix) == _normalized(keyword):
            return [item for item in value if isinstance(item, dict)]
    return []


def _query_spots(city: str, names: list[str]) -> dict[str, Any]:
    """在单次同程请求中批量查询多个景点关键词。"""
    return _post_json(
        SPOT_ENDPOINT,
        {"qryDetail": [{"keyword": name, "cityName": city} for name in names]},
    )


def _best_candidate(candidates: list[dict[str, Any]], name: str) -> tuple[dict[str, Any], bool]:
    wanted = _normalized(name)
    exact = [item for item in candidates if _normalized(item.get("name")) == wanted]
    return (exact or candidates)[0], bool(exact)


def resolve_place_media(city: str, names: list[str]) -> dict[str, Any]:
    """批量获取同程收录的真实图片，用作 image_text 主图或列表项缩略图。

    将没有图片的名称放入 `missing`，由调用方改用 picture_search 或省略图片。
    """
    city = _text(city)
    if not city:
        raise ProviderError("INVALID_ARGUMENT", "取配图需要 city", provider="tongcheng")
    cleaned: list[str] = []
    for value in names or []:
        text = _text(value)
        if text and text not in cleaned:
            cleaned.append(text)
    if not cleaned:
        raise ProviderError("INVALID_ARGUMENT", "取配图需要至少一个 name", provider="tongcheng")
    if len(cleaned) > 8:
        raise ProviderError("INVALID_ARGUMENT", "一次最多查 8 个名称", provider="tongcheng")

    payload = _query_spots(city, cleaned)
    places: list[dict[str, Any]] = []
    missing: list[str] = []
    for name in cleaned:
        candidates = _spot_candidates(payload, city, name)
        if not candidates:
            missing.append(name)
            continue
        item, matched = _best_candidate(candidates, name)
        images = _images(item)
        if not images:
            missing.append(name)
            continue
        entry: dict[str, Any] = {
            "name": name,
            "resolvedName": _text(item.get("name")) or name,
            "matched": matched,
            "thumbnail": images[0],
            "images": images,
        }
        address = _text(item.get("address"))
        if address:
            entry["address"] = address
        places.append(entry)
    return {"ok": True, "city": city, "places": places, "missing": missing}


def resolve_scenery(city: str, name: str) -> dict[str, Any]:
    """查询同程景点并提取购票小程序所需的 sid 与 wxrefid。

    优先从 redirectUrl 查询参数读取 sid，再回退到实体 ID 字段。两者均不存在时返回无结果。
    """
    city = _text(city)
    name = _text(name)
    if not city or not name:
        raise ProviderError("INVALID_ARGUMENT", "查同程景点需要 city 和 name", provider="tongcheng")
    payload = _query_spots(city, [name])
    candidates = _spot_candidates(payload, city, name)
    if not candidates:
        raise ProviderError("PROVIDER_NO_RESULT", f"同程没有收录「{name}」", provider="tongcheng")

    item, matched = _best_candidate(candidates, name)
    params = _query_params(_text(item.get("redirectUrl")))
    sid = params.get("sid") or ""
    if not sid:
        for key in ("siteId", "sceneryId", "resId", "id"):
            value = item.get(key)
            if value not in (None, ""):
                sid = str(value).strip()
                break
    if not sid:
        raise ProviderError("PROVIDER_NO_RESULT", f"同程未给出「{name}」的景点 ID", provider="tongcheng")

    result: dict[str, Any] = {
        "sid": sid,
        "name": _text(item.get("name")) or name,
        "matched": matched,
        "candidateCount": len(candidates),
    }
    wxrefid = params.get("wxrefid") or params.get("refid")
    if wxrefid:
        result["wxrefid"] = wxrefid
    address = _text(item.get("address"))
    if address:
        result["address"] = address
    # 复用同一回包中的图片，避免重复查询。
    images = _images(item)
    if images:
        result["thumbnail"] = images[0]
        result["images"] = images
    return result


def _load_map_client():
    """优先使用 tencent-map；未部署时回退到同样暴露 request 的内置实现。"""
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "tencent-map" / "scripts",
        Path(os.environ.get("ONEAGENT_SKILLS_ROOT") or "") / "tencent-map" / "scripts",
    ]
    for path in candidates:
        if (path / "map_client.py").is_file():
            if str(path) not in sys.path:
                sys.path.insert(0, str(path))
            import map_client  # type: ignore

            return map_client

    import map_fallback  # type: ignore

    return map_fallback


def resolve_poi(city: str, name: str) -> dict[str, Any]:
    """查询腾讯 POI 并提取地图小程序所需的 poiId。

    直接调用地点搜索接口，以保留 `map_query.place` 未返回的 `id`。
    """
    city = _text(city)
    name = _text(name)
    if not name:
        raise ProviderError("INVALID_ARGUMENT", "查腾讯 POI 需要 name", provider="tencent")
    if not city:
        raise ProviderError("INVALID_ARGUMENT", "查腾讯 POI 需要 city，禁止无城市全局匹配", provider="tencent")
    client = _load_map_client()
    try:
        data = client.request("/ws/place/v1/search", {
            "keyword": name,
            "boundary": f"region({city},1)",
            "page_size": 5,
        })
    except Exception as exc:  # map_client 自带结构化异常，这里统一成 ProviderError
        raise ProviderError("MAP_ERROR", f"腾讯地点搜索失败：{exc}", provider="tencent") from exc

    items = [item for item in (data.get("data") or []) if isinstance(item, dict)]
    if not items:
        raise ProviderError("PROVIDER_NO_RESULT", f"腾讯地图没有搜到「{name}」", provider="tencent")

    wanted = _normalized(name)
    exact = [item for item in items if _normalized(item.get("title")) == wanted]
    item = (exact or items)[0]
    poi_id = _text(item.get("id"))
    if not poi_id:
        raise ProviderError("PROVIDER_NO_RESULT", f"腾讯地图未给出「{name}」的 POI ID", provider="tencent")

    result: dict[str, Any] = {
        "poiId": poi_id,
        "name": _text(item.get("title")) or name,
        "matched": bool(exact),
        "candidateCount": len(items),
    }
    address = _text(item.get("address"))
    if address:
        result["address"] = address
    location = item.get("location")
    if isinstance(location, dict):
        try:
            result["lat"] = float(location["lat"])
            result["lng"] = float(location["lng"])
        except (KeyError, TypeError, ValueError):
            pass
    return result
