#!/usr/bin/env python3
"""对话流信息面板：把这一轮要讲的结构化内容渲染成一张卡，而不是堆一段 markdown。

和 NOW 卡片是两条完全独立的通道，不要混：

  show_panel   对话流内，纯展示。用户这一轮就在看，不打扰信息流。
  show_widget  NOW 信息流，由 Trigger 到点投递。用于「到点了、有变化了」。

当前对话卡只放机票、火车票、打车时间和天气；缺少的块直接省略。
美食推荐由回复正文或适用的 NOW 卡呈现。

stdout 给模型，return 给卡片（assets/ui/card.json）。卡片只做绑定、不做判断，
所以「这块画不画」「状态用什么色」都在这里算成布尔值交出去。
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

import companion
import provider_api
import tongcheng_fill
from emit_card import CardError
from landing_links import (MAOYAN_MINI_ID, MEITUAN_MINI_ID, TENCENT_MAP_MINI_ID, TONGCHENG_MINI_ID,
                           _https, _list, _row, _text, keyword_mini_path)

# 卡片以 UI 为主，成段的说明不上卡——那些话写在回复正文里。
# 这里列的字段照收不报错，只是不渲染，并在回执里告诉模型改写进正文。
PROSE_FIELDS = {
    "panel": ("summary", "tips"),
    "panel.weather": ("tip",),
    "panel.route": ("note",),
    "panel.hotel": ("note",),
    "panel.restaurants": ("address",),
    "panel.steps": ("desc",),
    "panel.places": ("desc", "meta"),
}
# 留在卡上的都是短标签。超了直接报错：长句就是说明，该写进正文。
MAX_CHARS = {"title": 18, "eyebrow": 22, "notice": 28, "step": 16, "place": 16, "name": 18,
             "check": 16, "factLabel": 6, "factValue": 8, "action": 12, "spot": 10}

LIMITS = {"steps": 6, "places": 3, "facts": 3, "tips": 3, "actions": 2,
          "tickets": 2, "days": 4, "extras": 3, "restaurants": 3, "spots": 3,
          "checklist": 8, "chips": 4, "tags": 3, "shows": 3}

# 外部品牌露出：卡上每个跳外部小程序的按钮都带对方 logo + 名字。
# logo 取各家 App Store 官方图标（96px PNG）；上线前转存公司 CDN、并和对方确认品牌使用。
# 新接一家小程序先在这里登记，没登记的 gh_ 会被拒——卡上不允许出现不露品牌的外跳。
_APPSTORE = "https://is1-ssl.mzstatic.com/image/thumb/"
BRANDS = {
    TONGCHENG_MINI_ID: ("同程旅行", _APPSTORE + "Purple211/v4/37/ca/c3/37cac3c6-08d0-f993-466c-436df597ea43/"
                        "AppIcon-0-0-1x_U007emarketing-0-8-0-85-220.png/96x96bb.png"),
    TENCENT_MAP_MINI_ID: ("腾讯地图", _APPSTORE + "Purple221/v4/05/15/e9/0515e927-d996-104f-2c55-6f87c57b97f6/"
                          "AppIcon-0-0-1x_U007emarketing-0-11-0-85-220.png/96x96bb.png"),
    MEITUAN_MINI_ID: ("美团", _APPSTORE + "Purple211/v4/f9/7c/56/f97c56ea-ddcb-7fe0-66aa-97d5f481ef62/"
                      "AppIcon-0-0-1x_U007emarketing-0-0-0-7-0-0-sRGB-85-220.png/96x96bb.png"),
    MAOYAN_MINI_ID: ("猫眼", _APPSTORE + "Purple211/v4/18/93/5d/18935dff-1aad-50c3-8bfa-c2feba69c28e/"
                     "AppIcon-0-0-1x_U007epad-0-1-0-85-220.png/96x96bb.png"),
}
# 图标是公共 CDN 上的 PNG：xCard 内置 Icon 只有通用 UI 图标，没有天气和交通。
# 全部用 Fluent Emoji 3D（MIT）：自带阴影和颜色，放在灰底卡片上也看得清，一套风格到底。
# 上线前把前缀换成公司 CDN 的镜像地址即可，别处不用动。
FLUENT = "https://cdn.jsdelivr.net/gh/microsoft/fluentui-emoji@main/assets/"


def _fluent(name: str) -> str:
    return f"{FLUENT}{name.replace(' ', '%20')}/3D/{name.lower().replace(' ', '_')}_3d.png"


ICONS = {"flight": _fluent("Airplane"), "train": _fluent("High-speed train"),
         "hotel": _fluent("Hotel"), "place": _fluent("Round pushpin"),
         "notice": _fluent("Warning"), "tips": _fluent("Light bulb"),
         "restaurant": _fluent("Fork and knife with plate"), "spot": _fluent("Admission tickets"),
         "checklist": _fluent("Luggage"), "done": _fluent("Check mark button"),
         "show": _fluent("Clapper board")}
# check_route_eta 的 mode 取值；taxi 是给用户看的「打车」，路况按驾车算。
ROUTE_MODES = {"driving": ("驾车", "Automobile"), "taxi": ("打车", "Oncoming taxi"),
               "transit": ("公交地铁", "Metro"), "walking": ("步行", "Footprints"),
               "bicycling": ("骑行", "Bicycle")}
TRAFFIC_WORDS = {"smooth": "畅通", "slow": "缓行", "congested": "拥堵", "jam": "拥堵"}
# 同程航班接口有 airlineLogoUrl 字段但目前恒为 null，先按 IATA 二字码取公开 logo 兜底。
AIRLINE_LOGO = "https://pic.c-ctrip.com/AssetCatalog/airline/48/{code}.png"
TICKET_KINDS = {"flight": "航班", "train": "火车"}
# 顺序即优先级：「雷阵雨」先命中雷，「阵雨」先于「雨」。
WEATHER_ICONS = (("雷", "Cloud with lightning and rain"), ("雪", "Cloud with snow"),
                 ("阵雨", "Sun behind rain cloud"), ("雨", "Cloud with rain"), ("雾", "Fog"),
                 ("霾", "Fog"), ("阴", "Cloud"), ("多云", "Sun behind cloud"), ("晴", "Sun"))
# 状态文字命中这些词就标红，其余按正常色；宁可漏标也不把「已值机」标成异常。
WARN_WORDS = ("延误", "取消", "停运", "晚点", "备降", "返航", "变更", "停售")


# ── 场景骨架 ─────────────────────────────────────────────────────────────
# 有真实航班号时才出航班块；没有航班号不能用待定城市对补一张航班卡。
# 每个场景在这里规定必出哪些块，少了就不出卡，并在回执里说清楚缺什么、怎么补。
# 只管「不能少」，不管「不能多」——多出来的块由下面的体量预算兜。
VISUAL = ("tickets", "route", "weather")
TEXT_BLOCKS = ("notice", "facts", "steps", "checklist")
BLOCKS = VISUAL + TEXT_BLOCKS
SCENES = {
    "depart": {"what": "出发日、赶飞机赶火车", "need": (("tickets",),),
               "with": "route（去机场车站）、weather（目的地）、checklist"},
    "outing": {"what": "本地出门吃喝玩乐、夜里活动", "need": (("route", "restaurants", "shows", "spots", "places"),),
               "with": "weather、steps"},
    "cityday": {"what": "在一座城玩一整天", "need": (("weather",), ("steps",)), "with": "spots、restaurants"},
    "stay": {"what": "住宿安排", "need": (("hotel",),), "with": "route（去酒店）、weather"},
    "booking": {"what": "只查票、订票、订酒店", "need": (("tickets", "hotel"),), "only": ("tickets", "hotel"),
                "with": "不放别的块，查什么给什么"},
    # info 的「必出一块主内容」就是 _shape_check 那条底线，不在这里重复报一次错
    "info": {"what": "只回答一次查询：天气、路上多久、附近有什么",
             "need": (), "ban": ("steps", "checklist"), "with": "facts（算出来的结论）"},
}
# 一张对话卡的体量预算，单位是「行」（≈ 列表里一个单行条目的高度）。
# 超了客户端会折叠，用户得多点一次才看得全；凑齐所有块的卡就是这么来的。
BULK = {"cover": 3.5, "tickets": 3.5, "route": 2.6, "hotel": 2.6, "places": 3.0, "spots": 2.4,
        "restaurants": 2.2, "shows": 2.6, "steps": 0.9, "checklist": 0.8, "notice": 1.1,
        "facts": 1.3, "actions": 1.1}
BULK_MAX = 22.0    # 超过就不出卡
BULK_WARN = 14.0   # 超过在回执里提醒往正文挪
MAX_VISUAL = 4

_DROPPED: list[str] = []
_FILL: list[str] = []  # 票务 / 酒店 / 演出的填充情况，回执里报给模型
_NOTE: list[str] = []  # 出了卡但值得提醒模型的事，回执里报
_ERRORS: list[str] = []  # 字段错误攒一起报，见 _try


def _try(fn, *args):
    """收集字段错误而不是撞上第一个就停。

    实测：一张卡连撞 4 次校验（facts 超字数、places 超条数、places 多字段、places 图非 https），
    模型每次只能改一个再重发，光这一段就走了 4 轮、两分钟。错误互相独立，一次报完。
    """
    try:
        return fn(*args)
    except CardError as exc:
        _ERRORS.append(f"{exc.rule} {exc.message}")
        return None

# 这两样决定卡上有没有价格和「同程预订」按钮。缺了卡照出，但要让模型知道。
BOOKING_FIELDS = (("price", "价格"), ("wxPath", "同程预订按钮"))


def _degrade(fn, *args):
    """取数失败一律降级，不让一个上游异常打死整张卡。

    这些调用都有兜底路径（用模型给的字段，或整块不画），所以这里捕得宽；
    CardError 是模型入参写错，要让它冒出去，不能吞。
    """
    try:
        return fn(*args), ""
    except CardError:
        raise
    except Exception as exc:  # noqa: BLE001 - 上游是网络和第三方回包，异常类型不可穷举
        return None, f"{type(exc).__name__}: {getattr(exc, 'message', exc)}"[:80]
HINT_T = "补上 depCity、arrCity 和 YYYY-MM-DD 的 date，脚本会去同程查齐"


# 缺哪块时照这个告诉模型怎么补：给识别码就行，别自己手填。
NEED_HINT = {
    "tickets": "tickets 航班必须给真实 no、date、depCity、arrCity；火车给车次，"
               "未确定火车车次时可给 kind=train、date、depCity、arrCity、pending=true",
    "weather": "weather 天气：给 {city,date}，脚本自己查，别把气温写进 facts",
    "route": "route 怎么过去：给 {from,to,mode}，脚本自己算时长和路况",
    "hotel": "hotel 住哪：给 {name,city,checkIn,checkOut}，脚本去同程查齐",
    "steps": "steps 这一天的时间轴：每项 {time,title}",
    "spots": "spots 景点", "restaurants": "restaurants 吃的",
    "shows": "shows 电影演出", "places": "places 顺路可去的地方",
}


def _iso(value: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))


def _scene_check(scene: str, panel: dict) -> None:
    """出卡前按场景核一遍必出块。

    缺了必出块就不出卡：一张漏了机票的出发卡，比不出卡更容易让用户误以为没有这程。
    只管「不能少」，「不能多」交给 _shape_check 的体量预算。
    """
    if scene not in SCENES:
        raise CardError("SCENE_UNKNOWN", "scene 必填，取值：" + "；".join(
            f"{k}（{v['what']}）" for k, v in SCENES.items()))
    spec = SCENES[scene]
    given = {b for b in BLOCKS if panel.get(b) not in (None, "", [], {})}
    for group in spec["need"]:
        if given & set(group):
            continue
        want = "、".join(NEED_HINT.get(b, b) for b in group)
        raise CardError("SCENE_INCOMPLETE",
                        f"scene={scene} 是「{spec['what']}」的卡，这块不能少——{want}。"
                        f"真的没有这块内容就换一个 scene。")
    extra = given - set(spec["only"]) if spec.get("only") else given & set(spec.get("ban", ()))
    if extra:
        raise CardError("SCENE_EXTRA",
                        f"scene={scene}（{spec['what']}）的卡上不放 {'、'.join(sorted(extra))}：{spec['with']}。"
                        f"这些内容要么写进回复正文，要么换一个 scene。")


# ── 数据归位 ─────────────────────────────────────────────────────────────
# 每类数据只有一个归属块。放错了不是小事：天气挤进 facts 就变成一格 8 字的小字，
# 气温、图标、未来几天全丢了；城际线路挤进 facts 会被截成「深→京…」，票卡也就不出了。
TEMP_RE = re.compile(r"\d\s*(?:°|℃|度)")
WEATHER_RE = re.compile(r"晴|多云|阴天|阵雨|小雨|中雨|大雨|雷|雪|雾|霾|台风|降水")
FLIGHT_RE = re.compile(r"(?<![A-Z0-9])(?:[A-Z]{2}|[0-9][A-Z])\d{3,4}(?![0-9])")
TRAIN_RE = re.compile(r"(?<![A-Z0-9])[GDCZTKY]\d{2,4}(?![0-9])")
PAIR_RE = re.compile(r"[\u4e00-\u9fa5A-Za-z]{1,6}\s*(?:→|->|⇒|—>)\s*[\u4e00-\u9fa5A-Za-z]{1,6}")
COMMUTE_RE = re.compile(r"通勤|车程|打车|路上|到机场|到车站|去机场|去车站")
SPAN_RE = re.compile(r"\d+\s*(?:分钟|小时|min|h)")


def _misplaced(label: str, value: str) -> str:
    """这条数据本该进哪一块。返回空串表示放对了。"""
    if TEMP_RE.search(value) or WEATHER_RE.search(value):
        return "weather"
    if FLIGHT_RE.search(value) or TRAIN_RE.search(value) or PAIR_RE.search(value):
        return "tickets"
    if COMMUTE_RE.search(label) and SPAN_RE.search(value):
        return "route"
    return ""


def _placement_check(panel: dict) -> None:
    """挡住两类错：数据塞错块，以及有城际交通却不出票卡。

    检测只看模型自己写的文字——它把航班号写进了 facts，就说明它知道有这一程，
    那就没有理由不出票卡。
    """
    texts: list[tuple[str, str, str]] = []  # (出错字段, 标签, 值)
    for i, f in enumerate(panel.get("facts") or []):
        if isinstance(f, dict):
            texts.append((f"panel.facts[{i}]", _s(f.get("label")), _s(f.get("value"))))
    for key in ("notice", "title", "eyebrow"):
        texts.append((f"panel.{key}", "", _s(panel.get(key))))
    for i, s in enumerate(panel.get("steps") or []):
        if isinstance(s, dict):
            texts.append((f"panel.steps[{i}].title", "", _s(s.get("title"))))

    for field, label, value in texts:
        where = _misplaced(label, value)
        if not where or panel.get(where) not in (None, "", [], {}):
            continue  # 那一块已经给了，文字里再提一次不算放错
        if field.startswith(("panel.title", "panel.eyebrow", "panel.steps")) and where != "tickets":
            continue  # 标题和行程里顺嘴提天气不算错，只有漏掉整程交通才要拦
        raise CardError("MISPLACED_FIELD",
                        f"{field} 写的是「{value}」，这属于 {where}，不要塞进文字里——{NEED_HINT[where]}。"
                        f"卡上每类数据只有一个位置，放错就没有图标、按钮和展开信息。")


def _bulk(out: dict) -> float:
    """估这张卡有多高，单位是「行」。端上按高度折叠，不按块数。"""
    total = BULK["cover"] if out["hasCover"] else 0.0
    total += 1.0 if out["hasHeader"] else 0.0
    for key, per in BULK.items():
        value = out.get(key)
        if isinstance(value, list):
            total += per * len(value)
    total += sum(0.8 for t in out["tickets"] if t["hasExtras"])
    if out["hasWeather"]:
        wx = out["weather"]
        total += 2.0 + (1.4 if wx["hasDays"] else 0) + (1.0 if wx["hasChips"] else 0)
    for key in ("route", "hotel"):
        total += BULK[key] if out[f"has{key.title()}"] else 0.0
    return round(total, 1)


def _shape_check(out: dict) -> None:
    """两条跨场景的底线：不能是纯文字堆叠，也不能长到被端上折叠。"""
    visual = [k for k in VISUAL if out[f"has{k[0].upper()}{k[1:]}"]]
    if not visual:
        raise CardError("TEXT_ONLY_CARD",
                        "这张卡全是文字，没有一块能看的内容。卡片是用来看的，"
                        f"至少要有一块：{'；'.join(NEED_HINT[b] for b in ('tickets', 'weather', 'route'))}。"
                        "只有时间轴和清单要讲，就直接写进回复正文，不必出卡。")
    if len(visual) > MAX_VISUAL:
        raise CardError("CARD_TOO_LONG",
                        f"一张卡最多 {MAX_VISUAL} 块主内容，这张有 {len(visual)} 块"
                        f"（{'、'.join(visual)}）。挑这一轮最要紧的几块，其余写进正文。")
    bulk = _bulk(out)
    if bulk > BULK_MAX:
        raise CardError("CARD_TOO_LONG",
                        f"这张卡太长（约 {bulk} 行，上限 {BULK_MAX} 行），端上会折叠成「看完整内容」。"
                        "砍掉列表项或去掉一块，详细的写进回复正文。")
    if bulk > BULK_WARN:
        _NOTE.append(f"这张卡约 {bulk} 行，快到折叠线了，下次少放一块")


def _report_missing(label: str, fields: dict, how: str) -> None:
    missing = [name for key, name in BOOKING_FIELDS if not fields.get(key)]
    if missing:
        _FILL.append(f"{label} 没有{'、'.join(missing)}（{how}）")


def _pending_ticket(kind: str, date: str, dep: str, arr: str, t: dict) -> dict:
    """火车车次待定时画城市对和日期；航班没有真实航班号则不出卡。"""
    return {**t, "kind": kind, "no": "", "pending": True,
            "date": tongcheng_fill._short_date(date) if _iso(date) else date,
            "depTime": "--:--", "arrTime": "--:--", "depPlace": dep, "arrPlace": arr,
            "duration": "待定", "price": "", "wxPath": ""}


def _resolve_ticket(raw: object, i: int) -> dict | None:
    """航班必须有真实航班号；火车可按车次、挑选或待定展示：

      班次已知  给 no      → 按航班号 / 车次精确对号
      火车还在挑 给 pick    → 按线路挑一班（最早 / 最便宜 / 某时刻之后）
      火车只定了要走 给 pending → 不查，先画城市对和日期，等用户补车次

    航班查不到且缺完整字段时省略航班块；火车挑不到可退成待定。
    """
    if not isinstance(raw, dict):
        return raw  # 交给 _ticket 报类型错误
    t = dict(raw)
    no, date = _s(t.get("no")), _s(t.get("date"))
    dep, arr, kind = _s(t.pop("depCity", "")), _s(t.pop("arrCity", "")), _s(t.get("kind"))
    station = _s(t.pop("depStation", ""))
    pick, pending = _s(t.pop("pick", "")), bool(t.get("pending", False))
    label = no or f"{dep}→{arr}" if dep and arr else f"tickets[{i}]"
    how = f"没给识别码，{HINT_T}"
    routed = kind in TICKET_KINDS and dep and arr and _iso(date)

    if kind == "flight":
        if not re.fullmatch(r"[A-Z0-9]{2,3}\s*\d{1,4}[A-Z]?", no.upper()):
            _NOTE.append("航班块未展示：缺少真实航班号；取得航班号后再传 no")
            return None
        t["no"] = no = re.sub(r"\s+", "", no.upper())
        t.pop("pending", None)

    if routed and not no and (pick or pending):
        if pick:
            hit, err = _degrade(tongcheng_fill.pick_ticket, kind, date, dep, arr, pick)
            if err:
                _FILL.append(f"{label} 按 {pick} 挑班次失败（{err}）")
            if hit:
                _FILL.append(f"{label} 按 {pick} 挑的是 {hit['no']} {hit['depTime']}；"
                             "用户认准别的班次就改传 no")
                _report_missing(hit["no"], hit, "同程回包里就没有")
                return hit
            _FILL.append(f"{label} 同程 {date} 没有可挑的班次，先按待定画")
        _NOTE.append(f"{label} 的班次还没定，正文里问用户订的是哪一班，拿到后带 no 重发")
        return _pending_ticket(kind, date, dep, arr, t)

    if routed and no:
        hit, err = _degrade(tongcheng_fill.lookup_ticket, kind, no, date, dep, arr, station,
                            _s(t.get("depTime")))
        where = f"从{station}上车的 " if station else ""
        why = f"查同程失败：{err}" if err else f"同程 {date} {dep}→{arr} 没有{where}{no}"
        if hit:
            alts = hit.pop("_alts", None)
            if alts:
                _FILL.append(f"{label} 有 {len(alts)} 个上车点（{'、'.join(alts)}），画的是 {alts[0]}；"
                             "不对就加 depStation 重发")
            if _s(t.get("status")):
                hit["status"] = t["status"]  # 同程搜索不给实时状态，只有这一项听模型的
            _report_missing(label, hit, "同程回包里就没有")
            return hit
        _FILL.append(f"{label}：{why}，改用你给的字段")
        how = "同程没查到，只能用手填的"
    if date and _iso(date):
        t["date"] = tongcheng_fill._short_date(date)
    if not all(_s(t.get(k)) for k in ("depTime", "depPlace", "arrTime", "arrPlace")):
        start, end = dep or _s(t.get("depPlace")), arr or _s(t.get("arrPlace"))
        if start and end and kind == "train":  # 火车可只画待定城市对
            _NOTE.append(f"{label} 缺起止时间地点，按待定画了；补齐 no 再发一次就能出完整票卡")
            return _pending_ticket(kind, date, start, end, t)
        _FILL.append(f"{label} 缺起止时间或地点，卡上没画这张票")
        return None
    _report_missing(label, t, how)
    return t


def _resolve_weather(raw: object) -> object:
    """给了 city 就自己查天气，气温、温差、未来几天一次取齐。"""
    if not isinstance(raw, dict):
        return raw
    wx = dict(raw)
    city, when = _s(wx.pop("city", "")), _s(wx.pop("date", ""))
    if not city:
        return wx
    hit, why = _degrade(companion.panel_weather, city, when)
    if why:
        _FILL.append(f"{city}天气查不到（{why}），改用你给的字段")
        return wx
    if not hit:
        _FILL.append(f"{city} {when or '这一天'} 的天气取不到（超出预报射程，或接口没给这一天），"
                     "天气这块没画；不要手填一个气温上去")
        return None
    return {**wx, **{k: v for k, v in hit.items() if v not in ("", [], None)}}


def _resolve_route(raw: object) -> object:
    """给了 from + to 就自己算路线，时长、距离、路况、打车价一次取齐。"""
    if not isinstance(raw, dict):
        return raw
    r = dict(raw)
    origin, dest = _s(r.get("from")), _s(r.get("to"))
    if not (origin and dest):
        return r
    hit, why = _degrade(companion.panel_route, origin, dest, _s(r.get("mode")) or "driving",
                        _s(r.pop("city", "")))
    if why:
        _FILL.append(f"{origin}→{dest} 的路线算不出来（{why}），改用你给的字段")
        return r
    hit.pop("reserveMin", None)  # 出门时刻由模型按缓冲算，不在卡上直接给
    merged = {**r, **{k: v for k, v in hit.items() if v not in ("", None, False)}}
    if not _s(merged.get("duration")):
        _FILL.append(f"{origin}→{dest} 没算出时长，路线这块没画")
        return None
    return merged


def _resolve_hotel(raw: object) -> object:
    """给了 name + city 就去同程按店名查，只认名字完全一致的那家。"""
    if not isinstance(raw, dict):
        return raw
    h = dict(raw)
    name, city = _s(h.get("name")), _s(h.pop("city", ""))
    cin, cout = _s(h.get("checkIn")), _s(h.get("checkOut"))
    how = "没给识别码，补上 city 和 YYYY-MM-DD 的 checkIn / checkOut，脚本会去同程查齐"
    if name and city:
        hit, err = _degrade(tongcheng_fill.lookup_hotel, city, name,
                            cin if _iso(cin) else "", cout if _iso(cout) else "")
        why = f"查同程失败：{err}" if err else f"同程在{city}没有同名的「{name}」"
        if hit:
            if _s(h.get("image")):
                hit["image"] = h["image"]
            _report_missing(name, hit, "同程回包里就没有")
            return hit
        _FILL.append(f"{name}：{why}，改用你给的字段")
        how = "同程没查到，只能用手填的"
    for key in ("checkIn", "checkOut"):
        if _iso(_s(h.get(key))):
            h[key] = tongcheng_fill._short_date(h[key]).split(" ")[0]
    _report_missing(name or "hotel", h, how)
    return h


def _s(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _strip(raw: object, group: str, field: str) -> object:
    """把不上卡的描述字段摘掉，记下来好在回执里点名。非 dict 原样交给 _row 去报错。"""
    if not isinstance(raw, dict):
        return raw
    keys = PROSE_FIELDS.get(group, ())
    for k in keys:
        if raw.get(k) not in (None, "", []):
            _DROPPED.append(f"{field}.{k}")
    return {k: v for k, v in raw.items() if k not in keys}


def _short(text: str, kind: str, field: str) -> str:
    limit = MAX_CHARS[kind]
    if len(text) > limit:
        raise CardError("TEXT_TOO_LONG",
                        f"{field} 有 {len(text)} 字，卡上最多 {limit} 字。卡片只放短标签，"
                        f"解释和描述写进回复正文。")
    return text


def _opt(obj: dict, key: str, field: str) -> str:
    return _text(obj.get(key), f"{field}.{key}")


def _req(obj: dict, key: str, field: str) -> str:
    return _text(obj.get(key), f"{field}.{key}", required=True)


def _items(panel: dict, key: str) -> list:
    """超出条数不中断：记下来继续校验剩下的字段，最后一次把问题报全。"""
    rows = _list(panel.get(key), f"panel.{key}", None)
    if len(rows) > LIMITS[key]:
        _ERRORS.append(f"ITEM_COUNT panel.{key} 最多 {LIMITS[key]} 项，实际 {len(rows)} 项")
        rows = rows[:LIMITS[key]]
    return rows


def _each(panel: dict, key: str, build) -> list:
    """逐项构建，某一项报错只记下这一项，不影响其余项继续校验。"""
    return [row for row in (_try(build, raw, i) for i, raw in enumerate(_items(panel, key)))
            if row is not None]


def _wx_icon(text: str) -> str:
    return _fluent(next((icon for word, icon in WEATHER_ICONS if word in text), "Sun behind small cloud"))


def _mini_path(obj: dict, field: str) -> str:
    """同程接口回包里的 wxurl 原样传进来；自己拼的路径参数对不上会落到错误页面。"""
    path = _opt(obj, "wxPath", field)
    if path and not path.startswith("/"):
        raise CardError("INVALID_FIELD", f"{field}.wxPath 必须是同程回包里以 / 开头的 wxurl")
    return path


def _brand(gh: str, field: str) -> tuple[str, str]:
    if gh not in BRANDS:
        raise CardError("UNKNOWN_BRAND", f"{field} 跳的小程序 {gh} 没在 show_panel.BRANDS 登记品牌，"
                                         "卡上不允许不露品牌的外跳")
    return BRANDS[gh]


def _booking(obj: dict, field: str) -> dict[str, Any]:
    path, price = _mini_path(obj, field), _opt(obj, "price", field)
    name, logo = BRANDS[TONGCHENG_MINI_ID]
    return {"wxPath": path, "mini": TONGCHENG_MINI_ID, "canBook": bool(path),
            "price": price, "hasPrice": bool(price), "bookBrand": name, "bookLogo": logo}


def _tap(obj: dict, field: str) -> dict[str, Any]:
    """收 prepare_landing 回包里的 tap 原样传进来；卡片没有二级页，只认小程序跳转。"""
    tap = obj.get("tap")
    if tap is None:
        return {"tapMini": "", "tapPath": "", "canTap": False, "tapBrand": "", "tapLogo": ""}
    if not isinstance(tap, dict) or tap.get("type") != 3 or not isinstance(tap.get("mini_program"), dict):
        raise CardError("INVALID_FIELD", f"{field}.tap 只收小程序跳转（prepare_landing kind=map / scenery / "
                                         "hotel 回包里 type=3 的 tap），卡片不开 H5")
    mini = tap["mini_program"]
    name, path = _text(mini.get("name"), f"{field}.tap.mini_program.name", required=True), \
        _text(mini.get("path"), f"{field}.tap.mini_program.path")
    if not name.startswith("gh_"):
        raise CardError("MINI_PROGRAM_GH_ID", f"{field}.tap.mini_program.name 必须以 gh_ 开头")
    brand, logo = _brand(name, f"{field}.tap")
    return {"tapMini": name, "tapPath": path, "canTap": True, "tapBrand": brand, "tapLogo": logo}


def _tags(obj: dict, field: str) -> dict[str, Any]:
    tags = [{"text": _text(t, f"{field}.tags[{i}]", required=True)}
            for i, t in enumerate(_list(obj.get("tags"), f"{field}.tags", LIMITS["tags"]))]
    return {"tags": tags, "hasTags": bool(tags)}


def _meta(*parts: str) -> str:
    return " · ".join(p for p in parts if p)


def _route(raw: object) -> dict[str, Any]:
    field = "panel.route"
    r = _row(_strip(raw, field, field), field, {"mode", "from", "to", "duration", "distance",
                                                "traffic", "fare", "leaveBy", "restricted", "tap"})
    mode = _opt(r, "mode", field) or "driving"
    if mode not in ROUTE_MODES:
        raise CardError("INVALID_ENUM", f"{field}.mode 只能是 {'/'.join(ROUTE_MODES)}")
    label, icon = ROUTE_MODES[mode]
    traffic = _opt(r, "traffic", field)
    traffic = TRAFFIC_WORDS.get(traffic, traffic)
    restricted = r.get("restricted", False)
    if not isinstance(restricted, bool):
        raise CardError("INVALID_FIELD", f"{field}.restricted 必须是布尔值")
    fare = _opt(r, "fare", field)
    leave, origin = _opt(r, "leaveBy", field), _opt(r, "from", field)
    return {
        **_tap(r, field), "icon": _fluent(icon),
        "head": f"{label}前往 {_req(r, 'to', field)}",
        "duration": _req(r, "duration", field),
        "meta": _meta(_opt(r, "distance", field), fare and f"打车约 {fare}"),
        "origin": origin and f"从 {origin} 出发", "hasOrigin": bool(origin),
        "traffic": traffic, "trafficOk": traffic == "畅通",
        "trafficSlow": bool(traffic) and "缓" in traffic,
        "trafficJam": bool(traffic) and ("堵" in traffic),
        "leaveBy": leave and f"建议 {leave} 出门", "hasLeaveBy": bool(leave),
        "restricted": restricted,
    }


def _keyword_deal(kind: str, keyword: str, city: str) -> dict[str, Any]:
    """美团 / 猫眼按名字搜：深链开通就自动带按钮，没开通就不画，不需要模型额外传 tap。"""
    gh = MEITUAN_MINI_ID if kind == "food" else MAOYAN_MINI_ID
    path = keyword_mini_path(kind, keyword, city)
    brand, logo = BRANDS[gh]
    return {"dealMini": gh, "dealPath": path, "canDeal": bool(path), "dealBrand": brand, "dealLogo": logo}


def _restaurant(raw: object, i: int, city: str) -> dict[str, Any]:
    field = f"panel.restaurants[{i}]"
    r = _row(_strip(raw, "panel.restaurants", field), field,
             {"name", "image", "rating", "price", "category", "distance", "tags", "tap", "city"})
    image, rating = _image(r, field), _opt(r, "rating", field)
    name = _short(_req(r, "name", field), "name", f"{field}.name")
    meta = _meta(rating and f"{rating} 分", _opt(r, "price", field),
                 _opt(r, "category", field), _opt(r, "distance", field))
    return {
        **_tap(r, field), **_tags(r, field),
        **_keyword_deal("food", name, _opt(r, "city", field) or city),
        "name": name, "image": image, "hasImage": bool(image), "noImage": not image,
        "icon": ICONS["restaurant"], "rating": rating, "hasRating": bool(rating),
        "meta": meta, "hasMeta": bool(meta),
    }


def _spot(raw: object, i: int) -> dict[str, Any]:
    field = f"panel.spots[{i}]"
    s = _row(raw, field, {"name", "image", "open", "reserve", "price", "tags", "tap"})
    image, reserve, price = _image(s, field), _opt(s, "reserve", field), _opt(s, "price", field)
    return {
        **_tap(s, field), **_tags(s, field),
        "name": _short(_req(s, "name", field), "name", f"{field}.name"), "image": image,
        "hasImage": bool(image), "noImage": not image, "icon": ICONS["spot"], "open": _opt(s, "open", field),
        "reserve": reserve, "hasReserve": bool(reserve), "price": price, "hasPrice": bool(price),
    }


def _show(raw: object, i: int, city: str) -> dict[str, Any]:
    field = f"panel.shows[{i}]"
    s = _row(raw, field, {"name", "image", "venue", "time", "price", "tags", "city"})
    image, price = _image(s, field), _yuan(_opt(s, "price", field))
    name = _short(_req(s, "name", field), "name", f"{field}.name")
    time = _opt(s, "time", field)
    if not image:
        _FILL.append(f"{name} 没有海报：用 picture_search 搜「{name} 海报」取竖图再传 image")
    return {
        **_tags(s, field), **_keyword_deal("ticket", name, _opt(s, "city", field) or city),
        "name": name, "image": image, "hasImage": bool(image),
        "venue": _opt(s, "venue", field), "time": time, "hasTime": bool(time),
        "price": price, "hasPrice": bool(price),
    }


def _yuan(price: str) -> str:
    """「74 元」「74元起」「74」统一成「¥74」，卡上单位只留一个「起」。"""
    m = re.fullmatch(r"[¥￥]?\s*(\d+(?:\.\d+)?)\s*元?\s*起?", price)
    return f"¥{m.group(1)}" if m else price


def _image(obj: dict, field: str) -> str:
    return _https(obj["image"], f"{field}.image") if obj.get("image") not in (None, "") else ""


def _weather(raw: object) -> dict[str, Any]:
    wx = _row(_strip(raw, "panel.weather", "panel.weather"), "panel.weather",
              {"temp", "text", "range", "days", "chips"})
    out = {k: _opt(wx, k, "panel.weather") for k in ("temp", "text", "range")}
    if not (out["temp"] or out["text"]):
        raise CardError("DATA_SHAPE", "panel.weather 至少要有 temp 或 text")
    out["line"] = " · ".join(p for p in (out["text"], out["range"]) if p)
    days = []
    for i, d in enumerate(_list(wx.get("days"), "panel.weather.days", LIMITS["days"])):
        field = f"panel.weather.days[{i}]"
        d = _row(d, field, {"label", "text", "temp"})
        text = _opt(d, "text", field)
        days.append({"label": _req(d, "label", field), "icon": _wx_icon(text),
                     "temp": _opt(d, "temp", field) or text})
    chips = []
    for i, c in enumerate(_list(wx.get("chips"), "panel.weather.chips", LIMITS["chips"])):
        field = f"panel.weather.chips[{i}]"
        c = _row(c, field, {"label", "value"})
        chips.append({"label": _req(c, "label", field), "value": _req(c, "value", field)})
    out.update(days=days, hasDays=bool(days), chips=chips, hasChips=bool(chips),
               icon=_wx_icon(out["text"]), big=out["temp"] or out["text"],
               line=out["line"] if out["temp"] else out["range"])
    return out


def _ticket(raw: object, i: int) -> dict[str, Any]:
    field = f"panel.tickets[{i}]"
    t = _row(raw, field, {"kind", "no", "carrier", "airlineCode", "logo", "date", "depTime", "depPlace",
                          "arrTime", "arrPlace", "duration", "status", "extras", "price", "wxPath",
                          "pending"})
    kind = _req(t, "kind", field)
    if kind not in TICKET_KINDS:
        raise CardError("INVALID_ENUM", f"{field}.kind 只能是 flight 或 train")
    pending = bool(t.pop("pending", False)) and kind == "train"
    no = _opt(t, "no", field) if pending else _req(t, "no", field)
    head = [TICKET_KINDS[kind], no, _opt(t, "carrier", field), _opt(t, "date", field)]
    status = _opt(t, "status", field)
    warn = any(w in status for w in WARN_WORDS)
    extras = []
    for j, e in enumerate(_list(t.get("extras"), f"{field}.extras", LIMITS["extras"])):
        ef = f"{field}.extras[{j}]"
        e = _row(e, ef, {"label", "value"})
        extras.append({"label": _req(e, "label", ef), "value": _req(e, "value", ef)})
    icon = ICONS[kind]
    if t.get("logo") not in (None, ""):
        icon = _https(t["logo"], f"{field}.logo")
    elif kind == "flight" and _opt(t, "airlineCode", field):
        code = _opt(t, "airlineCode", field).upper()
        if not (len(code) == 2 and code.isalnum()):
            raise CardError("INVALID_FIELD", f"{field}.airlineCode 是航司二字码，如 CA、MU、3U")
        icon = AIRLINE_LOGO.format(code=code)
    return {
        **_booking(t, field), "pending": pending,
        "pendingText": "车次待定 · 告诉我车次" if pending else "",
        "icon": icon, "head": " · ".join(p for p in head if p),
        "status": status, "statusWarn": bool(status) and warn, "statusOk": bool(status) and not warn,
        "depTime": _req(t, "depTime", field), "depPlace": _req(t, "depPlace", field),
        "arrTime": _req(t, "arrTime", field), "arrPlace": _req(t, "arrPlace", field),
        "duration": _opt(t, "duration", field) or "直达",
        "extras": extras, "hasExtras": bool(extras),
    }


def _hotel(raw: object) -> dict[str, Any]:
    field = "panel.hotel"
    h = _row(_strip(raw, field, field), field, {"name", "checkIn", "checkOut", "nights", "address",
                                                "image", "price", "wxPath"})
    check_in, check_out, nights = (_opt(h, k, field) for k in ("checkIn", "checkOut", "nights"))
    stay = " · ".join(p for p in (check_in and f"{check_in} 入住", check_out and f"{check_out} 离店",
                                  nights) if p)
    address, image = _opt(h, "address", field), _image(h, field)
    name = _short(_req(h, "name", field), "name", f"{field}.name")
    return {**_booking(h, field), "name": name, "stay": stay, "hasStay": bool(stay),
            "image": image, "hasImage": bool(image), "noImage": not image, "icon": ICONS["hotel"],
            "address": address, "hasAddress": bool(address)}


def build_panel(value: object, scene: str = "") -> dict[str, Any]:
    """对话 XCard 仅渲染航班、火车、天气和打车时间。"""
    _DROPPED.clear()
    _FILL.clear()
    _NOTE.clear()
    _ERRORS.clear()
    panel = _row(_strip(value, "panel", "panel"), "panel",
                 {"scene", "title", "eyebrow", "cover", "notice", "facts", "tickets", "route", "weather",
                  "hotel", "spots", "restaurants", "shows", "steps", "places", "checklist", "actions", "city"})
    # 只约束 XCard 渲染，绝不改变景点、酒店、行程、围栏或 NOW 卡的业务工具。
    omitted = [key for key in panel if key not in {"scene", "tickets", "weather", "route", "city"}]
    panel = {key: panel[key] for key in ("tickets", "weather", "route", "city") if key in panel}
    if isinstance(panel.get("route"), dict) and panel["route"].get("mode") != "taxi":
        omitted.append("非打车路线")
        panel.pop("route")
    if omitted:
        _NOTE.append("XCard 未展示 " + "、".join(omitted) + "；相关业务结果请在会话正文或其他适合的通道呈现")
    out: dict[str, Any] = {}
    for key, kind in (("title", "title"), ("eyebrow", "eyebrow"), ("notice", "notice")):
        out[key] = _short(_opt(panel, key, "panel"), kind, f"panel.{key}")
    out["cover"] = _https(panel["cover"], "panel.cover") if panel.get("cover") not in (None, "") else ""

    def _fact(raw, i):
        field = f"panel.facts[{i}]"
        f = _row(raw, field, {"label", "value"})
        return {"label": _short(_req(f, "label", field), "factLabel", f"{field}.label"),
                "value": _short(_req(f, "value", field), "factValue", f"{field}.value")}

    facts = _each(panel, "facts", _fact)
    tickets = [t for t in (_try(_ticket, r, i) for i, r in
                           ((i, _resolve_ticket(t, i)) for i, t in enumerate(_items(panel, "tickets")))
                           if r is not None) if t]
    wx_raw = _resolve_weather(panel["weather"]) if panel.get("weather") is not None else None
    weather = (_try(_weather, wx_raw) or {}) if wx_raw is not None else {}
    hotel = (_try(_hotel, _resolve_hotel(panel["hotel"])) or {}) if panel.get("hotel") is not None else {}
    route_raw = _resolve_route(panel["route"]) if panel.get("route") is not None else None
    route = (_try(_route, route_raw) or {}) if route_raw is not None else {}
    city = _opt(panel, "city", "panel")
    restaurants = []  # 兼容模板数据形状；美食只在正文或适用的 NOW 卡呈现。
    shows = _each(panel, "shows", lambda x, i: _show(x, i, city))
    spots = _each(panel, "spots", _spot)

    def _check(raw, i):
        field = f"panel.checklist[{i}]"
        c = _row(raw, field, {"text", "done"})
        done = c.get("done", False)
        if not isinstance(done, bool):
            raise CardError("INVALID_FIELD", f"{field}.done 必须是布尔值")
        return {"text": _short(_req(c, "text", field), "check", f"{field}.text"),
                "done": done, "todo": not done, "icon": ICONS["done"]}

    def _step(raw, i):
        field = f"panel.steps[{i}]"
        s = _row(_strip(raw, "panel.steps", field), field, {"time", "title", "spot", "image"})
        image, spot = _image(s, field), _opt(s, "spot", field)
        return {"lead": _opt(s, "time", field) or f"{i + 1:02d}",
                "title": _short(_req(s, "title", field), "step", f"{field}.title"),
                "spot": _short(spot, "spot", f"{field}.spot"), "hasSpot": bool(spot),
                "image": image, "hasImage": bool(image), "hasNext": True}

    def _place(raw, i):
        field = f"panel.places[{i}]"
        p = _row(_strip(raw, "panel.places", field), field, {"name", "image"})
        image = _image(p, field)
        return {"title": _short(_req(p, "name", field), "place", f"{field}.name"),
                "image": image, "hasImage": bool(image), "noImage": not image, "icon": ICONS["place"]}

    def _action(raw, i):
        field = f"panel.actions[{i}]"
        a = _row(raw, field, {"label", "query"})
        return {"label": _short(_req(a, "label", field), "action", f"{field}.label"),
                "query": _req(a, "query", field)}

    checklist = _each(panel, "checklist", _check)
    steps = _each(panel, "steps", _step)
    if steps:
        steps[-1]["hasNext"] = False  # 最后一项下面不拖一截悬空的竖线
    places = _each(panel, "places", _place)
    actions = _each(panel, "actions", _action)

    out.update(
        icons={k: ICONS[k] for k in ("notice", "checklist", "spot", "restaurant", "show")},
        facts=facts, tickets=tickets, route=route, weather=weather, hotel=hotel,
        spots=spots, restaurants=restaurants, shows=shows, steps=steps, places=places,
        checklist=checklist, actions=actions,
        hasHeader=bool(out["title"] or out["eyebrow"]),
        hasTitle=bool(out["title"]), hasEyebrow=bool(out["eyebrow"]),
        hasCover=bool(out["cover"]),
        hasNotice=bool(out["notice"]), hasFacts=bool(facts), hasTickets=bool(tickets),
        hasWeather=bool(weather), hasHotel=bool(hotel), hasSteps=bool(steps),
        hasPlaces=bool(places), hasActions=bool(actions),
        hasRoute=bool(route), hasRestaurants=bool(restaurants), hasSpots=bool(spots),
        hasChecklist=bool(checklist), hasShows=bool(shows),
    )
    if _ERRORS:
        raise CardError("PANEL_REJECTED",
                        f"这张卡有 {len(_ERRORS)} 处要改，一次改完再发："
                        + "；".join(f"（{i}）{e}" for i, e in enumerate(_ERRORS, 1)))
    if not any(v for k, v in out.items() if k.startswith("has")):
        raise CardError("EMPTY_PANEL", "XCard 至少需要一块票务、天气或打车时间；其他内容请在会话正文呈现")
    _shape_check(out)
    return out


def show_panel(args: dict) -> dict | None:
    """stdout 给模型，return 给卡片——两者内容不同是有意的。

    模型只需要知道「面板已出、有哪几块」，不需要整份数据回灌进上下文。
    """
    try:
        result = build_panel(args.get("panel"), _s(args.get("scene")))
    except CardError as exc:
        print(json.dumps(
            {"phase": "error", "code": exc.rule, "message": exc.message, "retryable": False},
            ensure_ascii=False,
        ))
        return None

    blocks = [name for key, name in (
        ("hasTickets", "票务"), ("hasRoute", "路线"), ("hasWeather", "天气"), ("hasHotel", "住宿"),
        ("hasSpots", "景点"), ("hasShows", "演出"), ("hasNotice", "提醒"), ("hasFacts", "关键信息"),
        ("hasSteps", "行程"), ("hasPlaces", "地点"), ("hasChecklist", "清单"),
        ("hasActions", "追问按钮"),
    ) if result[key]]
    dropped = f"卡上不放说明文字，{'、'.join(_DROPPED)} 没有上卡，需要的话写进回复正文。" if _DROPPED else ""
    filled = f"卡片数据：{'；'.join(_FILL)}。" if _FILL else ""
    note = f"提醒：{'；'.join(_NOTE)}。" if _NOTE else ""
    print(f"面板已展示：{'、'.join(blocks) or result['title']}。{filled}{note}{dropped}"
          f"不要在回复里复述面板内容，接着说用户还需要知道的事。")
    return result


def main() -> int:
    try:
        args = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    except json.JSONDecodeError:
        print(json.dumps({"phase": "error", "code": "INVALID_FIELD",
                          "message": "入参必须是合法 JSON"}, ensure_ascii=False))
        return 1
    print(json.dumps({
        "phase": "error", "code": "CARD_CHANNEL_UNAVAILABLE",
        "message": "直接运行 show_panel.py 无法把返回值交给 XCard。请通过 app 的 show_panel 工具入口调用；"
                   "入口不可用时在会话正文说明，不能声称面板已展示。",
        "retryable": False,
    }, ensure_ascii=False))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
