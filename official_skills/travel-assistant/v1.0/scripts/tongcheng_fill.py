#!/usr/bin/env python3
"""按识别码去同程查一次，把票务 / 酒店卡要的字段精确填满。

模型只给能唯一定位这条记录的识别码（航班号 + 日期 + 出发到达城市，或店名 + 城市 + 入离店日期），
其余字段全部由这里从同程回包里取。不让模型手工挑字段，是因为回包里有几处必然挑错：

- 航班的预订链接不在航班那层，在 segments[0].wxurl；外层 metaData.wxurl 是列表页
- 航班 prices[] 有多档，ticketPrice 是 null，价格要取各档 saleTotalPrice 的最低值
- 火车顶层 price 恒为 "0"；最低价那档常常余票为 0，要取「有票座别」里的最低价
- airlineLogoUrl、机场简称恒为 null，要从航司二字码和机场全称推出来

查不到或没对上号时不抛错，交回 None，由调用方用模型给的字段兜底，并把缺什么报给模型。
"""

from __future__ import annotations

import datetime as dt
import re
import urllib.parse
from typing import Any

import provider_api

FLIGHT_ENDPOINT = "/flyRealTime"
TRAIN_ENDPOINT = "/trainRealTime"
HOTEL_ENDPOINT = "/main_bot/hotel_list_rt"
WEEKDAYS = "一二三四五六日"


def _s(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _num(value: object) -> float | None:
    try:
        n = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _yuan(value: float | None) -> str:
    if value is None:
        return ""
    return f"¥{int(value)}" if value == int(value) else f"¥{value:.1f}"


def _duration(minutes: object) -> str:
    total = _num(minutes)
    if total is None:
        return ""
    h, m = divmod(int(total), 60)
    if not h:
        return f"{m}m"
    return f"{h}h" if not m else f"{h}h{m:02d}m"


def _short_date(value: str) -> str:
    try:
        d = dt.date.fromisoformat(value[:10])
    except ValueError:
        return value
    return f"{d.month}/{d.day} 周{WEEKDAYS[d.weekday()]}"


def _airport(full: str, city: str, terminal: str) -> str:
    """「深圳宝安国际机场」+ T3 → 「宝安 T3」。去不干净就保留全称，宁长勿错。"""
    name = full
    if city and name.startswith(city):
        name = name[len(city):]
    name = re.sub(r"(国际)?机场$", "", name) or full
    return f"{name} {terminal}".strip() if terminal else name


def _payload(data: dict[str, Any]) -> dict[str, Any]:
    """同程回包套了两层 data，第三层才是业务体（酒店还再多一层）。"""
    body = data.get("data") if isinstance(data.get("data"), dict) else data
    return body if isinstance(body, dict) else {}


# ── 航班 ─────────────────────────────────────────────────────────────────


def flight_fields(item: dict[str, Any]) -> dict[str, Any]:
    segs = [s for s in item.get("segments") or [] if isinstance(s, dict)]
    if not segs:
        return {}
    first, last = segs[0], segs[-1]
    prices = [p for p in item.get("prices") or [] if isinstance(p, dict)]
    priced = [(n, p) for p in prices if (n := _num(p.get("saleTotalPrice"))) is not None]
    cheapest = min(priced, key=lambda x: x[0]) if priced else None

    arr_time = _s(last.get("arrTime"))
    if _s(last.get("arrDate")) and _s(last.get("arrDate")) != _s(first.get("depDate")):
        arr_time += "+1"
    extras = []
    if len(segs) > 1:
        extras.append({"label": "中转", "value": "、".join(_s(s.get("arrCityName")) for s in segs[:-1])})
    aircraft = first.get("aircraft") if isinstance(first.get("aircraft"), dict) else {}
    if _s(aircraft.get("aircraftName")):
        extras.append({"label": "机型", "value": _s(aircraft["aircraftName"])})
    if cheapest and _s(cheapest[1].get("priceType")):
        extras.append({"label": "舱位", "value": _s(cheapest[1]["priceType"])})

    runtime = item.get("totalRunTime") if len(segs) > 1 else first.get("runTime")
    return {
        "kind": "flight",
        "no": _s(first.get("flightNo")),
        "carrier": _s(first.get("airlineShortName")) or _s(first.get("airlineName")),
        "airlineCode": _s(first.get("airlineCode")),
        "date": _short_date(_s(first.get("depDate"))),
        "depTime": _s(first.get("depTime")),
        "depPlace": _airport(_s(first.get("depAirportName")), _s(first.get("depCityName")),
                             _s(first.get("depAirportTerminal"))),
        "arrTime": arr_time,
        "arrPlace": _airport(_s(last.get("arrAirportName")), _s(last.get("arrCityName")),
                             _s(last.get("arrAirportTerminal"))),
        "duration": _duration(runtime),
        "extras": extras[:3],
        "price": _yuan(cheapest[0]) if cheapest else "",
        # 预订链接在航段上，不在航班那层
        "wxPath": _s(first.get("wxurl")),
    }


# ── 火车 ─────────────────────────────────────────────────────────────────


def train_fields(item: dict[str, Any]) -> dict[str, Any]:
    tickets = [t for t in item.get("ticketList") or [] if isinstance(t, dict)]

    def left(t: dict) -> int:
        try:
            return int(float(t.get("ticketLeft") or 0))
        except (TypeError, ValueError):
            return 0

    # 顶层 price 恒为 "0"，不能用；最低价那档常常没票，按「有票的最低价」算
    on_sale = [(n, t) for t in tickets if left(t) > 0 and (n := _num(t.get("ticketPrice"))) is not None]
    cheapest = min(on_sale, key=lambda x: x[0]) if on_sale else None
    extras = []
    # 有票的排前面：卡上标的价格来自有票座别，下面的座别列表得能对上
    for t in sorted(tickets, key=lambda t: (left(t) == 0, _num(t.get("ticketPrice")) or 0))[:3]:
        n = left(t)
        extras.append({"label": _s(t.get("ticketType")),
                       "value": f"{_yuan(_num(t.get('ticketPrice')))} · {f'{n} 张' if n else '无票'}"})

    arr_time = _s(item.get("arrTime"))
    if (_num(item.get("daySpan")) or 0) > 0:
        arr_time += f"+{int(_num(item.get('daySpan')))}"
    return {
        "kind": "train",
        "no": _s(item.get("trainCode")),
        "carrier": _s(item.get("trainType")),
        "date": _short_date(_s(item.get("depDate"))),
        "depTime": _s(item.get("depTime")),
        "depPlace": _s(item.get("depStationName")),
        "arrTime": arr_time,
        "arrPlace": _s(item.get("arrStationName")),
        "duration": _duration(item.get("runTime")),
        "extras": extras,
        "price": _yuan(cheapest[0]) if cheapest else "",
        "status": "" if cheapest or not tickets else "无票",
        "wxPath": _s(item.get("wxurl")),
    }


# ── 酒店 ─────────────────────────────────────────────────────────────────


def hotel_fields(item: dict[str, Any]) -> dict[str, Any]:
    wx = _s(item.get("wxurl"))
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(wx).query)) if wx else {}
    price = item.get("base_price")
    price = _num(price.get("price")) if isinstance(price, dict) else _num(price)
    loc = item.get("location") if isinstance(item.get("location"), dict) else {}
    out = {"name": _s(item.get("name")), "address": _s(loc.get("address")),
           "price": _yuan(price), "wxPath": wx}
    # 入离店日期以预订链接里的为准：卡上写的日期必须和点进去的一致
    if q.get("indate"):
        out["checkIn"] = _short_date(q["indate"]).split(" ")[0]
    if q.get("outdate"):
        out["checkOut"] = _short_date(q["outdate"]).split(" ")[0]
    if q.get("indate") and q.get("outdate"):
        try:
            nights = (dt.date.fromisoformat(q["outdate"]) - dt.date.fromisoformat(q["indate"])).days
            if nights > 0:
                out["nights"] = f"{nights} 晚"
        except ValueError:
            pass
    return out


# ── 查询与对号 ───────────────────────────────────────────────────────────


def _norm(value: object) -> str:
    return re.sub(r"\s+", "", _s(value)).upper()


def _same_place(want: str, got: str) -> bool:
    w, g = _norm(want), _norm(got)
    return bool(w and g) and (w in g or g in w)


def lookup_ticket(kind: str, no: str, date: str, dep_city: str, arr_city: str,
                  dep_station: str = "", dep_time: str = "") -> dict[str, Any] | None:
    """按航班号 / 车次在当天同线路里找那一条。找不到返回 None，不猜最像的那一班。

    同一车次会按上车站分成几条（福田 06:48、深圳北 07:03）。dep_station 严格过滤；
    dep_time 只在多条里挑，对不上不排除。仍不止一条时取第一条，全部候选放进 `_alts`。
    """
    endpoint = FLIGHT_ENDPOINT if kind == "flight" else TRAIN_ENDPOINT
    payload = {"depCityName": dep_city, "arrCityName": arr_city, "depDate": date}
    body = _payload(_payload(provider_api._post_json(endpoint, payload)))
    items = body.get("flightList" if kind == "flight" else "trainList") or []
    want = _norm(no)
    hits = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if kind == "flight":
            segs = item.get("segments") or []
            if segs and isinstance(segs[0], dict) and _norm(segs[0].get("flightNo")) == want:
                hits.append(flight_fields(item))
        elif _norm(item.get("trainCode")) == want:
            hits.append(train_fields(item))
    if dep_station:
        hits = [h for h in hits if _same_place(dep_station, h["depPlace"])]
    timed = [h for h in hits if h["depTime"] == _s(dep_time)]
    if len(hits) > 1 and timed:  # 手抄的时刻可能差一分钟，只用来挑，不用来排除
        hits = timed
    if not hits:
        return None
    first = hits[0]
    if len(hits) > 1:
        first["_alts"] = [f"{h['depPlace']} {h['depTime']}" for h in hits]
    return first


def _amount(price: str) -> float:
    """把 flight_fields / train_fields 出的「¥1840」读回数字，用来排序。没价的排最后。"""
    m = re.fullmatch(r"¥(\d+(?:\.\d+)?)", _s(price))
    return float(m.group(1)) if m else float("inf")


def pick_ticket(kind: str, date: str, dep_city: str, arr_city: str,
                rule: str = "earliest") -> dict[str, Any] | None:
    """班次还没定时，按线路挑一班。

    rule：earliest 当天最早、cheapest 有票里最便宜、after:HH:MM 该时刻之后最早的一班。
    整条线路都查不到就返回 None，不编一班出来。
    """
    endpoint = FLIGHT_ENDPOINT if kind == "flight" else TRAIN_ENDPOINT
    body = _payload(_payload(provider_api._post_json(
        endpoint, {"depCityName": dep_city, "arrCityName": arr_city, "depDate": date})))
    fields = flight_fields if kind == "flight" else train_fields
    cand = [f for item in body.get("flightList" if kind == "flight" else "trainList") or []
            if isinstance(item, dict) and (f := fields(item)).get("depTime")]
    if not rule.startswith("after:") and rule not in ("earliest", "cheapest"):
        raise ValueError("pick 只能是 earliest、cheapest 或 after:HH:MM")
    if rule.startswith("after:"):
        floor = rule[len("after:"):].strip()
        cand = [c for c in cand if c["depTime"] >= floor]
    if not cand:
        return None
    if rule == "cheapest":
        # 没价的（火车全无票、航班停售）不算最便宜，_amount 已经把它们排到最后
        return min(cand, key=lambda c: (_amount(c["price"]), c["depTime"]))
    return min(cand, key=lambda c: c["depTime"])


def lookup_hotel(city: str, name: str, check_in: str = "", check_out: str = "") -> dict[str, Any] | None:
    """按店名查，只认名字完全一致的那家；排第一但名字对不上的不算。"""
    payload: dict[str, Any] = {"city": city, "keywords": name}
    if check_in:
        payload["checkin"] = check_in
    if check_out:
        payload["checkout"] = check_out
    body = _payload(_payload(_payload(provider_api._post_json(HOTEL_ENDPOINT, payload))))
    want = _norm(name)
    for item in body.get("siteList") or []:
        if isinstance(item, dict) and _norm(item.get("name")) == want:
            return hotel_fields(item)
    return None
