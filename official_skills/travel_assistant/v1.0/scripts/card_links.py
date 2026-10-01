"""站点跳转与入口的生成规则。

这些字段全是机械派生的，**不进模型入参**：`navigationData` 由坐标 + 交通方式拼，
购票入口按同程景点 sid 拼微信明文 URL Scheme，附近酒店按城市 / 关键词拼同程
酒店列表页 Scheme，方案文案由 mode 映射。

PC / Web 的 `link` 仍走腾讯位置服务 Web URI
（https://lbs.qq.com/webApi/uriV1/uriGuide/uriWebRoute）。

移动端 `schema` 是一条微信明文 Scheme 字符串。

客户端打开的是微信小程序明文 Scheme
（https://developers.weixin.qq.com/miniprogram/dev/framework/open-ability/url-scheme.html）：
`weixin://dl/business/?appid=...&path=...&query=...`。参数必须走独立的 `query`
并整体编码：写成 `path=/a/b?x=1&y=2` 时，`&` 会被当成 Scheme 自己的分隔符，
小程序只能收到第一个参数，酒店列表就是这么跳空的。
"""

from __future__ import annotations

import datetime
import urllib.parse

# URI API 的 referer 使用稳定应用标识，不读取或复用托管的地图业务凭证。
MAP_REFERER = "yuanbao"

TONGCHENG_MINI_APPID = "gh_0a00573ff7cf"
TENCENT_MAP_MINI_APPID = "gh_ff25a9b4394d"
SCENERY_MINI_PATH = "/page/top/pages/scenery/detail/detail"
HOTEL_LIST_MINI_PATH = "/page/hotel/pages/sky/list/index"
MAP_POI_MINI_PATH = "/modules/poi/pages/index/index"
TONGCHENG_SCENERY_REFID = "2000411121"
TONGCHENG_HOTEL_REFID = "2000411784"
TONGCHENG_HOTEL_OF = "5148538"

_WEB_BASE = "https://apis.map.qq.com/uri/v1"

# mode → App 端 routeplan 的 type（仅 Web link 使用）
_ROUTE_TYPES = {
    "walk": "walk",
    "bike": "bike",
    "car": "drive",
    "taxi": "drive",
    "subway": "bus",
    "bus": "bus",
    "transit": "bus",
}
# Web/Wap 的 routeplan 只认 bus、drive、walk
_WEB_ROUTE_TYPES = {"bike": "walk"}
# 交通方案的展示文案，与端上的 mode → 文案映射保持一致
_MODE_LABELS = {
    "walk": "步行",
    "bike": "骑行",
    "car": "驾车",
    "taxi": "驾车",
    "subway": "公共交通",
    "bus": "公共交通",
    "transit": "公共交通",
}
_FALLBACK_MODE_LABEL = "出行"


def mode_label(mode: str) -> str:
    return _MODE_LABELS.get(mode, _FALLBACK_MODE_LABEL)


def _number(value: float) -> str:
    return ("%.6f" % float(value)).rstrip("0").rstrip(".")


def _coord(location: dict) -> str:
    return "%s,%s" % (_number(location["lat"]), _number(location["lng"]))


def _url(base: str, method: str, params: list[tuple[str, str]]) -> str:
    # 坐标的逗号与 marker 的 `coord:`、`;` 是腾讯的结构分隔符，不能被转义
    query = urllib.parse.urlencode(
        [(key, value) for key, value in params if value],
        quote_via=urllib.parse.quote,
        safe=",:;",
    )
    return "%s/%s?%s" % (base, method, query)


def _marker_link(location: dict, name: str) -> str:
    """标点页只要坐标就能打开，用来兜住拿不到终点名称的情况。"""
    marker = "coord:" + _coord(location)
    if name:
        marker += ";title:" + name
    return _url(_WEB_BASE, "marker", [("marker", marker), ("referer", MAP_REFERER)])


def weixin_scheme(appid: str, path: str, query: str = "") -> str:
    """明文 URL Scheme。参数走独立的 `query`，整体编码后 `&` 不会截断 path。"""
    scheme = "weixin://dl/business/?appid=%s&path=%s" % (appid, path)
    if query:
        scheme += "&query=%s" % urllib.parse.quote(query, safe="")
    return scheme


def scenery_schema(sid: str, wxrefid: str = "") -> str:
    sid = str(sid or "").strip()
    if not sid:
        return ""
    refid = str(wxrefid or "").strip() or TONGCHENG_SCENERY_REFID
    path = "%s?sid=%s&wxrefid=%s" % (SCENERY_MINI_PATH, sid, refid)
    return weixin_scheme(TONGCHENG_MINI_APPID, path)


def _hotel_stay_dates(indate: str = "", outdate: str = "") -> tuple[str, str]:
    checkin = str(indate or "").strip()
    checkout = str(outdate or "").strip()
    if not checkin or not checkout:
        today = datetime.date.today()
        checkin = checkin or today.isoformat()
        checkout = checkout or (today + datetime.timedelta(days=1)).isoformat()
    return checkin, checkout


def hotel_list_schema(
    *,
    city: str = "",
    keyword: str = "",
    indate: str = "",
    outdate: str = "",
    lat: str = "",
    lng: str = "",
) -> str:
    city = str(city or "").strip()
    keyword = str(keyword or "").strip()
    if not city and not keyword:
        return ""
    checkin, checkout = _hotel_stay_dates(indate, outdate)
    parts = []
    if city:
        parts.append("city=%s" % city)
    if keyword:
        parts.append("keywords=%s" % keyword)
    lat = str(lat or "").strip()
    lng = str(lng or "").strip()
    if lat:
        parts.append("lat=%s" % lat)
    if lng:
        parts.append("lng=%s" % lng)
    # 渠道参数与端上酒店 demo 对齐；不带 hotelid，避免落到某家详情。
    parts.extend(
        [
            "isOutLand=0",
            "indate=%s" % checkin,
            "outdate=%s" % checkout,
            "timeZone=8",
            "refid=%s" % TONGCHENG_HOTEL_REFID,
            "of=%s" % TONGCHENG_HOTEL_OF,
        ]
    )
    return weixin_scheme(TONGCHENG_MINI_APPID, HOTEL_LIST_MINI_PATH, "&".join(parts))


def map_schema(name: str, poi_id: str) -> str:
    poi_id = str(poi_id or "").strip()
    name = str(name or "").strip()
    if not poi_id and not name:
        return ""
    # 端上 demo 顺序：poiId、keyword、fromSource
    parts = []
    if poi_id:
        parts.append("poiId=%s" % poi_id)
    if name:
        parts.append("keyword=%s" % urllib.parse.quote(name, safe=""))
    parts.append("fromSource=yuanbao")
    path = "%s?%s" % (MAP_POI_MINI_PATH, "&".join(parts))
    return weixin_scheme(TENCENT_MAP_MINI_APPID, path)


def stop_navigation(location: dict, *, name: str = "", poi_id: str = "") -> dict:
    """站点详情里的「导航」按钮：Web 走路网规划，移动端开腾讯地图小程序。"""
    coord = _coord(location)
    web = [
        ("type", "drive"),
        ("to", name),
        ("tocoord", coord),
        ("coord_type", "2"),
        ("referer", MAP_REFERER),
    ]
    result = {
        "link": _url(_WEB_BASE, "routeplan", web) if name else _marker_link(location, name),
    }
    schema = map_schema(name, poi_id)
    if schema:
        result["schema"] = schema
    return result


def route_navigation(
    mode: str,
    location: dict,
    *,
    to_name: str = "",
    from_name: str = "",
    from_location: dict | None = None,
    poi_id: str = "",
) -> dict | None:
    """交通信息面板里某条方案的导航：按该方案的 mode 从本站到下一站。"""
    route_type = _ROUTE_TYPES.get(mode)
    if not route_type:
        return None  # 认不出的 mode 不猜，端上该端不画按钮
    coord = _coord(location)
    from_coord = _coord(from_location) if from_location else ""
    web = [
        ("type", _WEB_ROUTE_TYPES.get(route_type, route_type)),
        ("from", from_name),
        ("fromcoord", from_coord),
        ("to", to_name),
        ("tocoord", coord),
        ("coord_type", "2"),
        ("referer", MAP_REFERER),
    ]
    result = {
        "link": _url(_WEB_BASE, "routeplan", web) if to_name else _marker_link(location, to_name),
    }
    schema = map_schema(to_name or from_name, poi_id)
    if schema:
        result["schema"] = schema
    return result


def ticket_purchase(stop: dict) -> dict | None:
    """不生成搜索型伪购票入口；调用方只透传同程 sid 拼出的小程序 Scheme。"""
    return None
