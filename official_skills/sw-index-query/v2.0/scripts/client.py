#!/usr/bin/env python3
"""申万查询兼容入口：默认 westock CLI，显式 official 模式保留原 API。

这是原平台共享库 `swsresearch/client.py` 的可移植替代实现，仅依赖 Python
标准库（urllib / ssl / json），使整个 skill 在 Python 3.9+ 环境使用；默认模式需要已授权 westock CLI。

对外接口与原始 client 完全一致：
    sw_get(path, params=None, timeout=15)      -> dict（解析后的 JSON）
    sw_post(path, body=None, timeout=15)       -> dict（解析后的 JSON）
    class APIError(Exception)
    class APIOfflineError(APIError)

API 端点定义见 ../references/api-specs.md。
可通过环境变量覆盖：
    SW_BASE_URL   基础域名（默认 https://www.swsresearch.com）
"""

from __future__ import annotations

import json
from datasource import DataSourceError, UnsupportedCapabilityError
import os
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = os.environ.get("SW_BASE_URL", "https://www.swsresearch.com").rstrip("/")

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 公共行情 API 可能存在证书/代理问题；创建宽松上下文保证可达性。
# urllib 默认不发 ALPN。沙箱 ZeroProxy/Pingora 对无 ALPN 的 ClientHello 直接掐连接。
# 只宣告 http/1.1：urllib 不会 HTTP/2，带 h2 时网关会选 h2，应用层对不上。
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE
_SSL_CTX.set_alpn_protocols(["http/1.1"])


class APIError(Exception):
    """API 返回无效数据或响应无法解析时抛出。"""


class APIOfflineError(APIError):
    """网络不可达 / 超时等离线类错误。"""


def _build_url(path: str, params: dict | None) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        url = path
    else:
        url = BASE_URL + (path if path.startswith("/") else "/" + path)
    if params:
        qs = urllib.parse.urlencode(params)
        url += ("&" if "?" in url else "?") + qs
    return url


def _official_request(method: str, path: str, params=None, body=None, timeout=15):
    url = _build_url(path, params)
    headers = dict(_DEFAULT_HEADERS)
    data = None
    if method in ("POST", "PUT", "PATCH"):
        headers["Content-Type"] = "application/json"
        payload = body if body is not None else {}
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX)
        raw = resp.read().decode("utf-8", "replace")
    except (urllib.error.URLError, socket.timeout, TimeoutError,
            ConnectionError, OSError) as exc:
        raise APIOfflineError(
            f"申万 API 不可达 ({method} {path}): {exc}"
        ) from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise APIError(f"申万 API 返回非 JSON ({method} {path}): {raw[:200]!r}") from exc


def sw_get(path: str, params=None, timeout: int = 15, **kwargs) -> dict:
    """GET 请求。kwargs 兼容原始 client 的额外参数（忽略）。"""
    return _request("GET", path, params=params, timeout=timeout)


def sw_post(path: str, body=None, timeout: int = 15, json=None, **kwargs) -> dict:
    """POST 请求。`body` 与原始 client 一致；`json` 作为别名保留兼容。"""
    payload = body if body is not None else json
    return _request("POST", path, body=payload, timeout=timeout)


DATASOURCE = os.environ.get("SW_DATASOURCE", "westock").lower()
if DATASOURCE not in ("westock", "official"):
    raise ValueError("SW_DATASOURCE 必须为 westock 或 official")
USE_WESTOCK = DATASOURCE == "westock"


def _request(method, path, params=None, body=None, timeout=15):
    if not USE_WESTOCK:
        return _official_request(method, path, params, body, timeout)
    from datasource import get_kline, get_minute, get_component, get_risk_return
    args = params or body or {}
    code = args.get("swindexcode") or args.get("swIndexCode") or args.get("indexCode")
    if path.endswith("/trend/") or path.endswith("KChartData"):
        return {"data": get_kline(code, args.get("period", args.get("type", "DAY")), int(args.get("limit", 250)))}
    if path.endswith("/timelines/"):
        return {"data": get_minute(code), "point_interval": "1min"}
    if "component" in path:
        rows = get_component(code)
        return {"data": {"list": rows, "total": len(rows)}}
    if path.endswith("getIndexRiskReturn"):
        r = get_risk_return(code)
        aliases = {"m1_return":"m1_interval_return_rate", "m3_return":"m3_interval_return_rate",
                   "ytd_return":"ytd_interval_return_rate"}
        for y in (1,3,5):
            aliases[f"y{y}_return"] = f"y{y}_annual_return_rate"
            aliases[f"y{y}_vol"] = f"y{y}_annual_volatility"
        return {"data": {v:r.get(k) for k,v in aliases.items()}}
    raise UnsupportedCapabilityError(f"westock 未提供等价端点: {path}；公告原文/编制说明/官方行业权重不可替代。可显式设置 SW_DATASOURCE=official 访问原接口")
