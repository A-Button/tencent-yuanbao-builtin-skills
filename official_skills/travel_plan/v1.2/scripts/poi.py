"""同程景点结果的消歧、归一化与字段状态报告。"""

from __future__ import annotations

import math
import os
import queue
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse

import card_links
from api import ApiError, query_hotel, query_spot


DETAIL_FIELDS = (
    "location", "title", "address", "images", "thumbnail", "businessHours",
    "openStatus", "ticketPrice", "rating", "level", "introduction",
    "ticketPurchaseData", "nearbyHotelsData",
)


def _positive_int_env(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _positive_float_env(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


NEARBY_HOTEL_DISTANCE = _positive_int_env("MY_TRAVEL_HOTEL_DISTANCE", 5000)
# 酒店接口只能逐景点查，是同程侧唯一按景点数线性增长的开销。景点批量查询是
# 一次请求，这里是 N 次，所以并发给得比批量查询宽。
_HOTEL_MAX_WORKERS = _positive_int_env("MY_TRAVEL_HOTEL_CONCURRENCY", 12)
# 「附近酒店」只是详情页的一个入口，缺了不影响行程本身。网关慢的时候，
# N 个请求各自重试 MAX_RETRIES+1 次，代价按景点数线性放大，能把一次渲染
# 拖到几分钟。所以这一段单独设墙钟预算，超了就放弃剩下的。
_HOTEL_BUDGET_SECONDS = _positive_float_env("MY_TRAVEL_HOTEL_BUDGET", 8.0)
# 单次景点批量查询的关键词上限。常见行程（一城 20 个景点以内）仍是一次请求。
_SPOT_BATCH_LIMIT = _positive_int_env("MY_TRAVEL_SPOT_BATCH", 20)
_SPOT_MAX_WORKERS = _positive_int_env("MY_TRAVEL_SPOT_CONCURRENCY", 6)
_TEMP_CLOSED_HINTS = ("暂停营业", "临时闭园", "临时关闭", "暂停开放", "停业整顿")
_CURRENTLY_CLOSED_HINTS = ("今日闭园", "今日关闭", "已闭园", "未开放")
_OPEN_HINTS = ("营业中", "开放中", "正常开放", "全年开放")
_X_PI = math.pi * 3000.0 / 180.0

# 卡片上「营业时间」只有一格的宽度，超出就被截成「2026-0…」，读的人什么也得不到。
# 所以这一格只接受时段本身，且限长到一格能放下的程度。
_HOURS_MAX_CHARS = 24
_HOURS_RANGE_RE = re.compile(r"(\d{1,2})[:：](\d{2})\s*[-–—~～至到]\s*(\d{1,2})[:：](\d{2})")
_ALL_DAY_HINTS = ("全天开放", "全天", "24小时", "24H", "24h")


def normalize_business_hours(value: object) -> str:
    """把各种"营业时间"原文收敛成时段，取不出时段就judge为没有。

    同程的 ``openTime`` 常常根本不是时段，而是"下次开门的时刻"（如
    ``2026-09-09 08:00``）；``businessStatus`` 则是整句话（如
    ``今日已闭园,明日日场8:30-14:30``）。两种直接塞进卡片都是错的：前者看着像
    个日期，后者会被截断。这里只认时段，认不出就返回空——宁可这一格显示"暂无"，
    让模型走官网补充，也好过摆一个看不懂的值。
    """
    text = re.sub(r"\s+", " ", _text(value))
    if not text:
        return ""
    ranges = []
    for start_hour, start_minute, end_hour, end_minute in _HOURS_RANGE_RE.findall(text):
        span = "%02d:%s-%02d:%s" % (int(start_hour), start_minute, int(end_hour), end_minute)
        if span not in ranges:
            ranges.append(span)
    if ranges:
        merged = "、".join(ranges)
        # 多个时段拼起来也可能超宽（旺季/淡季各一段），放不下就只留第一段。
        return merged if len(merged) <= _HOURS_MAX_CHARS else ranges[0]
    if any(hint in text for hint in _ALL_DAY_HINTS):
        return "全天开放"
    return ""


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _normalized_name(value: object) -> str:
    return re.sub(r"[\s·•・—_\-（）()【】\[\]《》“”\"'，,。.!！?？:：]", "", _text(value)).lower()


def _normalized_city(value: object) -> str:
    text = _text(value)
    for suffix in ("特别行政区", "自治区", "自治州", "地区", "市"):
        if text.endswith(suffix) and len(text) > len(suffix):
            text = text[:-len(suffix)]
            break
    return text


def _city_score(item: dict[str, Any], city: str) -> float:
    """城市只用于同名候选排序，绝不作为丢弃候选的门槛。"""
    wanted = _normalized_city(city)
    actuals = {
        value
        for value in (
            _normalized_city(item.get("city")),
            _normalized_city(item.get("district")),
        )
        if value
    }
    if not wanted or not actuals:
        return 0.25
    if wanted in actuals:
        return 1.0
    if any(wanted in actual or actual in wanted for actual in actuals):
        return 0.65
    return 0.0


def _name_score(keyword: str, candidate: str) -> float:
    wanted = _normalized_name(keyword)
    actual = _normalized_name(candidate)
    if not wanted or not actual:
        return 0.0
    if wanted == actual:
        return 1.0
    if wanted in actual or actual in wanted:
        shorter, longer = sorted((len(wanted), len(actual)))
        return 0.82 + 0.12 * (shorter / max(longer, 1))
    return SequenceMatcher(None, wanted, actual).ratio()


def rank_candidates(
    candidates: list[dict[str, Any]],
    keyword: str,
    city: str,
) -> list[dict[str, Any]]:
    """只排序候选，不按名称、城市或品类拒绝任何数据源结果。"""
    return sorted(
        (item for item in candidates if isinstance(item, dict)),
        key=lambda item: (
            _name_score(keyword, _text(item.get("name"))),
            _city_score(item, city),
        ),
        reverse=True,
    )


def _finite_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _location(item: dict[str, Any]) -> tuple[dict[str, float] | None, str]:
    coordinate = item.get("coordinate")
    if not isinstance(coordinate, dict):
        return None, ""
    lat = _finite_float(coordinate.get("lat"))
    lng = _finite_float(coordinate.get("lon") if "lon" in coordinate else coordinate.get("lng"))
    if lat is None or lng is None or not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None, ""
    coord_type = _text(coordinate.get("type")).upper()
    if coord_type in ("BD09", "BD-09", "BAIDU"):
        x = lng - 0.0065
        y = lat - 0.006
        z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * _X_PI)
        theta = math.atan2(y, x) - 0.000003 * math.cos(x * _X_PI)
        lat, lng = z * math.sin(theta), z * math.cos(theta)
        coord_type = "GCJ-02"
    elif coord_type not in ("GCJ02", "GCJ-02"):
        return None, coord_type
    return {"lat": round(lat, 6), "lng": round(lng, 6)}, "GCJ-02"


def _safe_url(value: object) -> str:
    text = _text(value)
    if text.startswith("http://"):
        text = "https://" + text[7:]
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        return ""
    return text


def _with_query_param(url: str, name: str, value: str) -> str:
    """为 URL 追加或替换一个单值查询参数。"""
    parsed = urlparse(url)
    query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if key != name
    ]
    query.append((name, value))
    return parsed._replace(query=urlencode(query)).geturl()


def _query_params(url: str) -> dict[str, str]:
    parsed = urlparse(url)
    raw = parsed.query
    if "?" in parsed.fragment:
        raw = parsed.fragment.split("?", 1)[1]
    params: dict[str, str] = {}
    for key, values in parse_qs(raw, keep_blank_values=False).items():
        if values and values[0]:
            params[key] = values[0]
    return params


def _nearby_hotels_data(payload: dict[str, Any], *, keyword: str = "") -> dict[str, str] | None:
    """提取同程酒店列表入口；移动端打开附近酒店列表，不跳某一家详情。"""
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    metadata = data.get("metaData") if isinstance(data.get("metaData"), dict) else {}
    link = _safe_url(metadata.get("redirectUrl")) or _safe_url(metadata.get("redirectPcUrl"))
    if not link:
        return None
    if keyword:
        link = _with_query_param(link, "keywords", keyword)
    result: dict[str, Any] = {"link": link, "label": "同程旅行"}
    params = _query_params(link)
    schema = card_links.hotel_list_schema(
        city=params.get("city") or params.get("cityid") or params.get("cityId") or "",
        keyword=(
            params.get("keywords")
            or params.get("keyword")
            or params.get("key")
            or params.get("center")
            or keyword
        ),
        indate=params.get("inDate") or params.get("indate") or "",
        outdate=params.get("outDate") or params.get("outdate") or "",
        lat=params.get("lat") or params.get("latitude") or "",
        lng=params.get("lng") or params.get("lon") or params.get("longitude") or "",
    )
    if schema:
        result["schema"] = schema
    icon = _safe_url(payload.get("iconUrl"))
    if icon:
        result["icon"] = icon
    return result


def _query_nearby_hotels(city: str, center: str, tripped: set[str]) -> dict[str, str] | None:
    """查询当前景点配置范围内的同程酒店。

    `tripped` 是同一批次共享的熔断标记。所有请求打的是同一个网关，第一个请求
    因超时或网络错误失败之后，剩下的几乎必然同样失败，再让它们各自重试只是
    把这批开销乘以景点数。
    """
    if tripped:
        return None
    try:
        payload = query_hotel(
            {"city": city, "center": center, "distance": NEARBY_HOTEL_DISTANCE}
        )
    except ApiError as exc:
        if exc.code in ("NETWORK_ERROR", "HTTP_RETRYABLE") or exc.status in (429, 503):
            tripped.add(exc.code)
        return None
    return _nearby_hotels_data(payload, keyword=center) if isinstance(payload, dict) else None


def _ticket_price(item: dict[str, Any]) -> str:
    raw = item.get("price")
    text = _text(str(raw)) if raw not in (None, "") else ""
    is_free = item.get("isFree") in (True, 1, "1", "true", "True", "是")
    if is_free or text in ("0", "0.0", "免费"):
        return "免费"
    if not text:
        return ""
    text = text.replace("￥", "¥").replace(" ", "").strip()
    numeric = re.fullmatch(r"¥?(\d+(?:\.\d+)?)(?:元)?(?:起)?", text)
    if numeric:
        if float(numeric.group(1)) == 0:
            return "免费"
        return f"¥{numeric.group(1)}起"
    price_range = re.fullmatch(r"¥?(\d+(?:\.\d+)?)[-~至](\d+(?:\.\d+)?)(?:元)?", text)
    if price_range:
        return f"¥{price_range.group(1)}-{price_range.group(2)}"
    return text


def _rating(item: dict[str, Any]) -> float | None:
    for key in ("commentScore", "score"):
        value = _finite_float(item.get(key))
        if value is not None and 0 < value <= 5:
            return round(value, 1)
    return None


def _level(item: dict[str, Any]) -> str:
    raw = _text(item.get("star")).upper().replace("景区", "").strip()
    if not raw or raw == "0":
        return ""
    if raw.isdigit() and 1 <= int(raw) <= 5:
        return f"{raw}A景区"
    if re.fullmatch(r"[1-5]A", raw):
        return f"{raw}景区"
    if re.fullmatch(r"A{1,5}", raw):
        return f"{len(raw)}A景区"
    return ""


def _open_status(item: dict[str, Any], hours: str) -> str:
    explicit = _text(item.get("businessStatus") or item.get("openStatus"))
    text = explicit or hours
    if any(hint in text for hint in _TEMP_CLOSED_HINTS):
        return "暂停营业"
    if any(hint in text for hint in _CURRENTLY_CLOSED_HINTS):
        return "已闭园"
    if any(hint in text for hint in _OPEN_HINTS):
        return "营业中"
    return ""


def _identifier_text(value: object) -> str:
    if isinstance(value, bool) or value is None:
        return ""
    if isinstance(value, (str, int, float)):
        return str(value).strip()
    return ""


def _provider_identity(item: dict[str, Any]) -> tuple[str, str]:
    for key in ("siteId", "sceneryId", "resId", "id"):
        value = _identifier_text(item.get(key))
        if value:
            return value, key
    return "", ""


def _provider_id(item: dict[str, Any]) -> str:
    """兼容内部旧调用；商品 ID 不作为景点实体 ID。"""
    return _provider_identity(item)[0]


def _to_detail(item: dict[str, Any], icon: str) -> tuple[dict[str, Any], dict[str, Any]]:
    detail: dict[str, Any] = {}
    location, coordinate_system = _location(item)
    if location:
        detail["location"] = location
    title = _text(item.get("name"))
    if title:
        detail["title"] = title
    address = _text(item.get("address"))
    if address:
        detail["address"] = address

    raw_images = item.get("pic")
    if isinstance(raw_images, str):
        raw_images = [raw_images]
    images = []
    if isinstance(raw_images, list):
        for value in raw_images:
            url = _safe_url(value)
            if url and url not in images:
                images.append(url)
            if len(images) >= 8:
                break
    if images:
        detail["images"] = images
        detail["thumbnail"] = images[0]

    raw_hours = _text(item.get("openTime"))
    business_status = _text(item.get("businessStatus"))
    # 两个字段都可能带时段，也都可能带别的东西，一起交给归一化挑时段。
    hours = normalize_business_hours(raw_hours) or normalize_business_hours(business_status)
    if hours:
        detail["businessHours"] = hours
    # 营业状态仍看原文：闭园与否的线索在被丢掉的那部分话里。
    status = _open_status(item, raw_hours or business_status)
    if status:
        detail["openStatus"] = status
    price = _ticket_price(item)
    if price:
        detail["ticketPrice"] = price
    rating = _rating(item)
    if rating is not None:
        detail["rating"] = rating
    level = _level(item)
    if level:
        detail["level"] = level
    introduction = _text(item.get("summary") or item.get("introduction"))
    if introduction:
        detail["introduction"] = introduction

    web_link = _safe_url(item.get("redirectUrl"))
    params = _query_params(web_link)
    sid = params.get("sid") or _provider_id(item)
    wxrefid = params.get("wxrefid") or params.get("refid")
    schema = card_links.scenery_schema(sid, wxrefid)
    if web_link and schema and price != "免费":
        purchase: dict[str, Any] = {
            "link": web_link,
            "schema": schema,
            "label": "同程旅行",
        }
        safe_icon = _safe_url(icon)
        if safe_icon:
            purchase["icon"] = safe_icon
        detail["ticketPurchaseData"] = purchase

    provider_id, provider_id_kind = _provider_identity(item)
    meta = {
        "provider": "tongcheng",
        "providerId": provider_id,
        "providerIdKind": provider_id_kind,
        "productId": _identifier_text(item.get("productId")),
        "city": _text(item.get("city")),
        "district": _text(item.get("district")),
        "adcode": _text(item.get("adcode")),
        "rawCategory": _text(item.get("category")),
        "coordinateSystem": coordinate_system,
    }
    return detail, meta


def _candidate_record(item: dict[str, Any]) -> dict[str, Any]:
    location, _ = _location(item)
    provider_id, _ = _provider_identity(item)
    return {
        "provider": "tongcheng",
        "providerId": provider_id,
        "name": _text(item.get("name")),
        "city": _text(item.get("city")),
        "district": _text(item.get("district")),
        "address": _text(item.get("address")),
        "location": location,
        "category": _text(item.get("category")),
    }


def _selection_required(keyword: str, candidates: list[dict[str, Any]]) -> bool:
    """唯一同名实体可自动确认；其他情况交由模型查看候选纠偏。"""
    wanted = _normalized_name(keyword)
    exact_entities = {
        _provider_identity(item)[0]
        or "|".join(
            (
                _normalized_name(item.get("name")),
                _text(item.get("address")),
                _text(item.get("city")),
            )
        )
        for item in candidates
        if _normalized_name(item.get("name")) == wanted
    }
    return len(exact_entities) != 1


def _groups_for_keyword(groups: dict[str, Any], city: str, keyword: str) -> list[dict[str, Any]]:
    direct = groups.get(f"{city}_{keyword}")
    if isinstance(direct, list):
        return [item for item in direct if isinstance(item, dict)]
    wanted_city = _normalized_city(city)
    wanted_keyword = _normalized_name(keyword)
    for key, value in groups.items():
        if not isinstance(key, str) or not isinstance(value, list):
            continue
        prefix, separator, suffix = key.rpartition("_")
        if separator and _normalized_city(prefix) == wanted_city and _normalized_name(suffix) == wanted_keyword:
            return [item for item in value if isinstance(item, dict)]
    return []


def _query_spots(city: str, keywords: list[str]) -> dict[str, Any]:
    """一个城市的景点查询，超过批量上限就拆成并发的几批再合回一份回包。

    批量查询的好处是一次往返，坏处是关键词一多这一次往返就成了整轮渲染里最长的
    串行段，而且它挡在算路前面。上限之内（常见行程都在）保持单请求，行为不变；
    超过了才拆，用几个并发请求换回墙钟。
    """
    if len(keywords) <= _SPOT_BATCH_LIMIT:
        return query_spot({"cityName": city, "keywords": keywords})
    chunks = [
        keywords[index:index + _SPOT_BATCH_LIMIT]
        for index in range(0, len(keywords), _SPOT_BATCH_LIMIT)
    ]
    merged: dict[str, Any] = {"data": {}}
    failure: ApiError | None = None
    with ThreadPoolExecutor(max_workers=min(_SPOT_MAX_WORKERS, len(chunks))) as pool:
        for payload in pool.map(
            lambda chunk: _query_spots_chunk(city, chunk), chunks
        ):
            if isinstance(payload, ApiError):
                failure = failure or payload
                continue
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
                continue
            merged["data"].update(payload["data"])
            if not merged.get("iconUrl"):
                icon = _text(payload.get("iconUrl"))
                if icon:
                    merged["iconUrl"] = icon
    # 全批都失败才算整体不可用；部分成功照常返回，缺的关键词自然落到 no_result。
    if not merged["data"] and failure is not None:
        raise failure
    return merged


def _query_spots_chunk(city: str, chunk: list[str]) -> Any:
    try:
        return query_spot({"cityName": city, "keywords": chunk})
    except ApiError as exc:
        return exc


def _start_nearby_hotels(
    city: str,
    resolved: dict[str, dict[str, Any]],
    reports: dict[str, Any],
) -> Any:
    """立刻发出酒店请求，返回一个收口函数；结果在收口时写回 resolved/reports。

    这里用守护线程而不是 ThreadPoolExecutor：线程池会在解释器退出时 join 掉
    所有工作线程，超预算放弃的请求仍会把进程按在原地，省下的时间又还回去了。
    """
    tripped: set[str] = set()
    pending: queue.Queue = queue.Queue()
    for keyword in resolved:
        pending.put(keyword)
    found: dict[str, dict[str, str]] = {}
    lock = threading.Lock()
    drained = threading.Event()
    left = {"count": pending.qsize()}

    def worker() -> None:
        while True:
            try:
                keyword = pending.get_nowait()
            except queue.Empty:
                return
            nearby = _query_nearby_hotels(city, keyword, tripped)
            with lock:
                if nearby:
                    found[keyword] = nearby
                left["count"] -= 1
                if left["count"] <= 0:
                    drained.set()

    for _ in range(min(_HOTEL_MAX_WORKERS, left["count"])):
        threading.Thread(target=worker, daemon=True).start()
    deadline = time.monotonic() + _HOTEL_BUDGET_SECONDS

    def finish() -> None:
        drained.wait(max(deadline - time.monotonic(), 0.0))
        # 预算用尽时，已经回来的照常写入，没回来的这轮就不要了。
        with lock:
            for keyword, nearby in found.items():
                resolved[keyword]["nearbyHotelsData"] = nearby
                fields = reports[keyword].get("fields")
                if isinstance(fields, dict):
                    fields["nearbyHotelsData"] = "present"

    return finish


def resolve_with_status(
    city: str,
    names: list[str],
    *,
    defer_hotels: bool = False,
) -> dict[str, Any]:
    keywords = [name for name in dict.fromkeys(_text(value) for value in names) if name]
    reports: dict[str, Any] = {}
    if not city or not keywords:
        return {"items": {}, "reports": reports}
    try:
        payload = _query_spots(city, keywords)
    except ApiError as exc:
        for keyword in keywords:
            reports[keyword] = {"status": "provider_unavailable", "error": exc.as_dict()}
        return {"items": {}, "reports": reports}
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        error = {"code": "BAD_RESPONSE", "provider": "tongcheng", "retryable": False}
        for keyword in keywords:
            reports[keyword] = {"status": "provider_unavailable", "error": error}
        return {"items": {}, "reports": reports}

    groups = payload["data"]
    icon = _text(payload.get("iconUrl"))
    resolved: dict[str, dict[str, Any]] = {}
    for keyword in keywords:
        candidates = rank_candidates(_groups_for_keyword(groups, city, keyword), keyword, city)
        report: dict[str, Any] = {"status": "present" if candidates else "no_result"}
        if candidates:
            best = candidates[0]
            detail, meta = _to_detail(best, icon)
            resolved[keyword] = detail
            report["meta"] = meta
            report["candidates"] = [_candidate_record(item) for item in candidates[:5]]
            report["selectionRequired"] = _selection_required(keyword, candidates)
            report["fields"] = {
                field: ("present" if detail.get(field) not in (None, "", [], {}) else "not_returned")
                for field in DETAIL_FIELDS
            }
        reports[keyword] = report

    # 整批关键词全空更像数据源或配置异常，标注出来交由调用方缩短负缓存并上报。
    if not resolved:
        for report in reports.values():
            report["batchEmpty"] = True

    response: dict[str, Any] = {"items": resolved, "reports": reports}
    # 酒店接口需要逐景点查询；失败只隐藏「附近酒店」，不影响景点详情。
    if resolved:
        finish = _start_nearby_hotels(city, resolved, reports)
        if defer_hotels:
            # 这批数据只喂详情页的「附近酒店」入口，与坐标和算路无关，交由
            # 调用方在算路之后收口，把这段网络时间藏进算路的等待里。
            response["finishHotels"] = finish
        else:
            finish()
    return response


def resolve(city: str, names: list[str]) -> dict[str, dict[str, Any]]:
    """兼容旧调用，只返回成功匹配的字段。"""
    return resolve_with_status(city, names)["items"]
