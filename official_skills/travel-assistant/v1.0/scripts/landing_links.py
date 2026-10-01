#!/usr/bin/env python3
"""构造 NOW 卡片的小程序、地图和主对话落地目标。"""

from __future__ import annotations

import datetime as dt
import urllib.parse
from typing import Any

import provider_api
from emit_card import CardError


# 小程序原始 ID。必须是 gh_ 开头的原始 id，填 AppID 会 bad_param。
TONGCHENG_MINI_ID = "gh_0a00573ff7cf"
TENCENT_MAP_MINI_ID = "gh_ff25a9b4394d"
MEITUAN_MINI_ID = "gh_870576f3c6f9"
MAOYAN_MINI_ID = "gh_d9004ba7511f"

# 美团 / 猫眼按关键词进搜索结果页。三样拿到后填这里就同时生效：
# prepare_landing kind=food / ticket 出 tap，show_panel 的餐厅、演出卡自动带上品牌按钮。
# PATH 留空 = 未开通，一律不给跳转（落首页比没有跳转更伤）。
MEITUAN_PATH = ""
MEITUAN_PARAMS = {"keyword": "keyword", "city": "city"}  # 我方字段 → 对方参数名
MEITUAN_EXTRA: dict[str, str] = {}                       # 来源 / 渠道参数，按对方规范填
MAOYAN_PATH = "/pages/search/result"
MAOYAN_PARAMS = {"keyword": "search_keyword"}  # 猫眼搜索页不收城市
MAOYAN_EXTRA = {"activeTab": "0"}              # 0 = 落在「全部」tab
SCENERY_PATH = "/page/top/pages/scenery/detail/detail"
HOTEL_PATH = "/page/hotel/pages/sky/list/index"
MAP_POI_PATH = "/modules/poi/pages/index/index"
SCENERY_REFID = "2000411121"
HOTEL_REFID = "2000411784"
HOTEL_OF = "5148538"
MAP_REFERER = "yuanbao"


def _text(value: object, field: str, *, required: bool = False) -> str:
    if value is None or value == "":
        if required:
            raise CardError("REQUIRED_FIELD", f"缺少必填字段 {field}")
        return ""
    if not isinstance(value, str) or not value.strip():
        raise CardError("INVALID_FIELD", f"{field} 必须是非空字符串")
    return value.strip()


def _https(value: object, field: str) -> str:
    url = _text(value, field, required=True)
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise CardError("HTTPS_URL", f"{field} 必须是完整 HTTPS 地址")
    return url


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CardError("INVALID_FIELD", f"{field} 必须是数字")
    return float(value)


def _mini_tap(name: str, path: str) -> dict[str, Any]:
    return {
        "type": 3,
        "mini_program": {"name": name, "path": path, "mp_type": 0},
    }


def _h5_tap(url: str) -> dict[str, Any]:
    return {"type": 2, "h5": {"url": url}}


def _row(value: object, field: str, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CardError("INVALID_FIELD", f"{field} 必须是对象")
    extra = set(value) - allowed
    if extra:
        raise CardError("DATA_SHAPE", f"{field} 不支持 {sorted(extra)}，只能有 {sorted(allowed)}")
    return value


def _list(value: object, field: str, limit: int | None) -> list:
    """limit=None 表示不在这里卡条数，由调用方自己决定是报错还是截断。"""
    if value is None:
        return []
    if not isinstance(value, list):
        raise CardError("INVALID_FIELD", f"{field} 必须是数组")
    if limit is not None and len(value) > limit:
        raise CardError("ITEM_COUNT", f"{field} 最多 {limit} 项，实际 {len(value)} 项")
    return value


def _legacy_page(args: dict[str, Any]) -> dict[str, Any]:
    """Keep saved triggers working without producing an unavailable detail link."""
    return {
        "ok": True,
        "kind": "page",
        "tap": {"type": 1, "agent_chat": {}},
        "note": "旧版详情页入口已改为返回原会话；卡片需直接写清关键信息。",
    }


KEYWORD_MINIS = {
    "food": {"brand": "美团", "gh": MEITUAN_MINI_ID},
    "ticket": {"brand": "猫眼", "gh": MAOYAN_MINI_ID},
}


def _keyword_config(kind: str) -> tuple[str, dict[str, str], dict[str, str]]:
    # 读模块全局而不是闭包，测试和配置改动能即时生效。
    prefix = "MEITUAN" if kind == "food" else "MAOYAN"
    g = globals()
    return g[f"{prefix}_PATH"], g[f"{prefix}_PARAMS"], g[f"{prefix}_EXTRA"]


def keyword_mini_path(kind: str, keyword: str, city: str = "") -> str:
    """拼美团 / 猫眼搜索页路径；未开通返回空串，调用方据此不画按钮。"""
    path, names, extra = _keyword_config(kind)
    if not path or not keyword:
        return ""
    params = [(names["keyword"], keyword)]
    if city and names.get("city"):
        params.append((names["city"], city))
    params.extend(extra.items())
    joiner = "&" if "?" in path else "?"
    return f"{path}{joiner}{urllib.parse.urlencode(params, quote_via=urllib.parse.quote)}"


def _keyword_mini(args: dict[str, Any], *, kind: str) -> dict[str, Any]:
    """美团 / 猫眼这类按关键词进小程序的落地。

    **没有深链 path 时直接拒绝，不落首页。**

    卡上写着「海岸城」，点进去是美团首页还得自己再搜一遍——这比没有跳转更伤：
    没跳转用户知道要自己找，给了跳转却落错地方，他会认为这个功能坏了。
    深链拿到之前，这类地点走 `kind=map`（腾讯地图能定位到具体 POI），
    或者干脆不配 tap，把关键词写进卡片文案。
    """
    keyword = _text(args.get("keyword") or args.get("name"), "keyword", required=True)
    city = _text(args.get("city"), "city")
    brand, gh_id = KEYWORD_MINIS[kind]["brand"], KEYWORD_MINIS[kind]["gh"]
    full_path = keyword_mini_path(kind, keyword, city)
    if not full_path:
        raise CardError(
            "DEEPLINK_MISSING",
            f"{brand}的深链路径还没配，只能落小程序首页，用户进去还得自己搜「{keyword}」。"
            f"改用 kind=map 定位到具体地点，或不配 tap、把「{keyword}」写进卡片文案。"
            f"拿到深链后填 scripts/landing_links.py 顶部的路径常量即可开启。",
        )
    return {
        "ok": True,
        "kind": kind,
        "tap": _mini_tap(gh_id, full_path),
        "keyword": keyword,
        "deepLinked": True,
        "note": f"直达{brand}的「{keyword}」。",
    }


def _food_landing(args: dict[str, Any]) -> dict[str, Any]:
    return _keyword_mini(args, kind="food")


def _ticket_landing(args: dict[str, Any]) -> dict[str, Any]:
    return _keyword_mini(args, kind="ticket")


# 各家地图自己托管的唤端页。全是 HTTPS，直接当 h5.url 用，不需要我们部署任何东西。
# 在手机上打开会引导装了对应 app 的用户跳过去，没装的就留在网页版。
#
# 坐标一律是 gcj02（腾讯地图返回的就是）。腾讯与高德原生 gcj02 直接用；
# 百度默认按 bd09 解释，必须显式带 coord_type=gcj02，否则整体偏移几百米。
NAVI_PROVIDERS = {
    "qqmap": {
        "label": "腾讯地图",
        "url": ("https://apis.map.qq.com/uri/v1/routeplan?type=drive"
                "&to={name}&tocoord={lat},{lng}&referer=" + MAP_REFERER),
    },
    "amap": {
        "label": "高德地图",
        "url": ("https://uri.amap.com/navigation?to={lng},{lat},{name}"
                "&mode=car&coordinate=gaode&src=yuanbao"),
    },
    "baidu": {
        "label": "百度地图",
        "url": ("https://api.map.baidu.com/direction?destination=latlng:{lat},{lng}|name:{name}"
                "&mode=driving&coord_type=gcj02&output=html&src=yuanbao"),
    },
    "apple": {
        "label": "Apple 地图",
        "url": "https://maps.apple.com/?daddr={lat},{lng}&q={name}&dirflg=d",
    },
}
DEFAULT_NAVI_PROVIDER = "qqmap"


def _navigate_landing(args: dict[str, Any]) -> dict[str, Any]:
    """导航落地：跳各家地图自己的唤端页。

    协议只有三种 tap，`geo:` / `iosamap://` 这类 scheme 没法直接下发——不是 HTTPS，
    容器也只会把 h5.url 丢进 WebView。但各家地图都有自建的 HTTPS 唤端页，
    用它们就不必自己托管页面。

    一个 tap 只能落一家。要让用户在几家之间挑，用 `recommend_list`，
    每行一家，各自挂自己的 tap——选择权在卡片上，不在页面里。
    """
    provider = _text(args.get("provider"), "provider") or DEFAULT_NAVI_PROVIDER
    if provider not in NAVI_PROVIDERS:
        raise CardError("INVALID_ENUM", f"provider 只能是 {'/'.join(NAVI_PROVIDERS)}")

    name = _text(args.get("name"), "name", required=True)
    lat, lng = args.get("lat"), args.get("lng")
    if lat is None or lng is None:
        city = _text(args.get("city"), "city")
        if not city:
            raise CardError("REQUIRED_FIELD", "navigate 需要 lat/lng，或提供 city 加 name 由工具查坐标")
        resolved = provider_api.resolve_poi(city, name)
        lat, lng = resolved.get("lat"), resolved.get("lng")
    if lat is None or lng is None:
        raise CardError("LOCATION_UNRESOLVED", f"查不到「{name}」的坐标，改用 kind=map")

    spec = NAVI_PROVIDERS[provider]
    url = spec["url"].format(
        name=urllib.parse.quote(name, safe=""),
        lat=f"{_number(lat, 'lat'):.6f}",
        lng=f"{_number(lng, 'lng'):.6f}",
    )
    return {
        "ok": True,
        "kind": "navigate",
        "provider": provider,
        "label": spec["label"],
        "tap": _h5_tap(url),
        "coordType": "gcj02",
        "alternatives": {k: v["label"] for k, v in NAVI_PROVIDERS.items() if k != provider},
        "note": (
            f"落到{spec['label']}的唤端页，装了 app 的会跳过去，没装的留在网页版。"
            "要让用户在几家之间挑，就发一张 recommend_list，每行一家、各挂各的 tap。"
        ),
    }


def _map_landing(args: dict[str, Any]) -> dict[str, Any]:
    name = _text(args.get("name"), "name", required=True)
    poi_id = _text(args.get("poi_id"), "poi_id")
    city = _text(args.get("city"), "city")
    lat = args.get("lat")
    lng = args.get("lng")
    resolved: dict[str, Any] | None = None

    # 未提供 poiId 时查询腾讯地图；无结果时仍可打开关键词页。
    if not poi_id and city:
        try:
            resolved = provider_api.resolve_poi(city, name)
        except provider_api.ProviderError as exc:
            resolved = {"error": exc.code, "message": exc.message}
        else:
            poi_id = resolved["poiId"]
            if lat is None and lng is None and "lat" in resolved:
                lat, lng = resolved["lat"], resolved["lng"]

    params = [("poiId", poi_id)] if poi_id else []
    params.extend([("keyword", name), ("fromSource", "yuanbao")])
    query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    result: dict[str, Any] = {
        "ok": True,
        "kind": "map",
        "tap": _mini_tap(TENCENT_MAP_MINI_ID, f"{MAP_POI_PATH}?{query}"),
        "resolvedPoi": bool(poi_id),
    }
    if resolved is not None:
        result["lookup"] = resolved

    if (lat is None) != (lng is None):
        raise CardError("COORD_PAIR", "lat 与 lng 必须成对提供")
    if lat is not None:
        lat_value = _number(lat, "lat")
        lng_value = _number(lng, "lng")
        marker = f"coord:{lat_value:.6f},{lng_value:.6f};title:{name}"
        web_query = urllib.parse.urlencode(
            {"marker": marker, "referer": MAP_REFERER},
            quote_via=urllib.parse.quote,
            safe=",:;",
        )
        result["h5FallbackTap"] = _h5_tap(
            f"https://apis.map.qq.com/uri/v1/marker?{web_query}"
        )
    return result


def _scenery_landing(args: dict[str, Any]) -> dict[str, Any]:
    sid = _text(args.get("sid"), "sid")
    refid = _text(args.get("wxrefid"), "wxrefid")
    lookup: dict[str, Any] | None = None

    # 未提供 sid 时按城市和名称查询同程；无结果时失败，以避免跳转到错误景点。
    if not sid:
        city = _text(args.get("city"), "city")
        name = _text(args.get("name"), "name")
        if not city or not name:
            raise CardError("REQUIRED_FIELD", "scenery 需要 sid，或者提供 city 加 name 由工具查同程")
        try:
            lookup = provider_api.resolve_scenery(city, name)
        except provider_api.ProviderError as exc:
            raise CardError(exc.code, exc.message) from exc
        sid = lookup["sid"]
        refid = refid or lookup.get("wxrefid", "")

    query = urllib.parse.urlencode({"sid": sid, "wxrefid": refid or SCENERY_REFID})
    result: dict[str, Any] = {
        "ok": True,
        "kind": "scenery",
        "tap": _mini_tap(TONGCHENG_MINI_ID, f"{SCENERY_PATH}?{query}"),
    }
    if lookup is not None:
        result["lookup"] = lookup
    return result


def _hotel_landing(args: dict[str, Any]) -> dict[str, Any]:
    city = _text(args.get("city"), "city")
    keyword = _text(args.get("keyword"), "keyword")
    if not city and not keyword:
        raise CardError("REQUIRED_FIELD", "city 与 keyword 至少提供一个")
    today = dt.date.today()
    indate = _text(args.get("indate"), "indate") or today.isoformat()
    outdate = _text(args.get("outdate"), "outdate") or (today + dt.timedelta(days=1)).isoformat()
    params: list[tuple[str, str]] = []
    if city:
        params.append(("city", city))
    if keyword:
        params.append(("keywords", keyword))
    if args.get("lat") is not None:
        if args.get("lng") is None:
            raise CardError("COORD_PAIR", "lat 与 lng 必须成对提供")
        params.extend([
            ("lat", str(_number(args.get("lat"), "lat"))),
            ("lng", str(_number(args.get("lng"), "lng"))),
        ])
    elif args.get("lng") is not None:
        raise CardError("COORD_PAIR", "lat 与 lng 必须成对提供")
    params.extend([
        ("isOutLand", "0"),
        ("indate", indate),
        ("outdate", outdate),
        ("timeZone", "8"),
        ("refid", HOTEL_REFID),
        ("of", HOTEL_OF),
    ])
    return {
        "ok": True,
        "kind": "hotel",
        "tap": _mini_tap(
            TONGCHENG_MINI_ID,
            f"{HOTEL_PATH}?{urllib.parse.urlencode(params, quote_via=urllib.parse.quote)}",
        ),
    }


KINDS = {
    "page": _legacy_page,
    "map": _map_landing,
    "scenery": _scenery_landing,
    "hotel": _hotel_landing,
    "food": _food_landing,
    "ticket": _ticket_landing,
    "navigate": _navigate_landing,
}


def prepare_landing(args: dict[str, Any]) -> dict[str, Any]:
    kind = _text(args.get("kind"), "kind", required=True)
    handler = KINDS.get(kind)
    if handler is None:
        raise CardError("INVALID_ENUM", f"kind 只能是 {'/'.join(KINDS)}")
    return handler(args)
