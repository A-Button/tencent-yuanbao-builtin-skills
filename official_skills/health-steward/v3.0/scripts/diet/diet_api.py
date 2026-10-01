#!/usr/bin/env python3
"""饮食助手唯一业务门面。

用法：
    python3 diet_api.py '<json>'          # {"operation": "...", ...}

输出就是三 tab 的 render_payload 本身，外加一个 `_model` 键——那是给模型看的精简回执，
由 _run.py 摘出来单独打印，不进卡片。这样 Agent 走 _run.py、iframe 直连 app.yaml 声明的
handler，两条路拿到的是同一种形状。

不管哪个 operation，payload 里都是完整的 current_meal + today + stats，只有 default_tab
不同：宿主每次 tool-result 会整体替换 iframe 的数据，缺哪一段那一段就空了。
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import PurePosixPath

import nutrition
import store
from a2ui import default_scene, enrich_display_fields
from cli_contract import CONTRACT, ContractError, validate
from payload_schema import PayloadValidationError, validate_payload



def _card_meals(date_str: str) -> list[dict]:
    """卡片和统计只用最近 7 天。更早的日子按需要再打开，不把整本档案读上来。"""
    anchor = store.parse_time(date_str + "T12:00:00+08:00")
    start = (anchor - timedelta(days=nutrition.REGULARITY_DAYS - 1)).strftime("%Y-%m-%d")
    return store.load_meals_between(start, date_str)


def build_payload(default_tab: str, current_meal: dict | None, date_str: str, period: str = "week") -> dict:
    meals = _card_meals(date_str)
    todays = [m for m in meals if str(m.get("eaten_at", ""))[:10] == date_str]
    anchor = store.parse_time(date_str + "T12:00:00+08:00")
    # 日视图/统计/删除这几个 operation 本身没有「本餐」，但卡片的第一个 tab 还在。
    # 拿当天最后一餐兜底，让用户切过去时看到的是最近这顿而不是空白。
    if current_meal is None and todays:
        current_meal = todays[-1]
    payload = {
        "current_meal": current_meal or {},
        "today": {
            "date": date_str,
            "meals_by_type": nutrition.group_by_meal_type(todays),
            "totals": nutrition.day_totals(todays),
            "skipped_slots": store.skipped_slots(date_str),
        },
        "stats": {
            "default_period": period,
            "day": nutrition.stats_for_day(meals, date_str),
            "week": nutrition.stats_for_week(meals, anchor),
        },
        "default_tab": default_tab,
        "default_period": period,
    }
    # A2UI / XCard 与 HTML 共用这一份 structuredContent。
    # 展示字段写在 current_meal 上，模板按 /current_meal/* 绑定。
    return enrich_display_fields(payload)


def _day_has_meals(payload: dict) -> bool:
    grouped = (payload.get("today") or {}).get("meals_by_type") or {}
    return any(grouped.values())


def _day_has_skips(payload: dict) -> bool:
    return bool((payload.get("today") or {}).get("skipped_slots"))


def _nothing_to_render(payload: dict, operation: str) -> bool:
    """该不该把这份载荷当成「空天」。

    get_day / delete_meal 只看**被查询的那一天**：当天一条记录、一次跳过都没有
    才算空。只标了「不吃了」也要出卡，花名册那一行得改成已跳过。

    get_stats 仍看统计窗口：日/周都是零条才跳过。今天没吃、近 7 天还有记录时，
    统计洞察那个 tab 有东西，卡片照发。
    """
    if payload.get("current_meal") or _day_has_meals(payload) or _day_has_skips(payload):
        return False
    if operation in ("get_day", "delete_meal"):
        return True
    stats = payload.get("stats") or {}
    return not any((stats.get(p) or {}).get("meal_count") for p in ("day", "week"))


def _skip_reason(operation: str) -> str:
    if operation in ("get_day", "delete_meal"):
        return "empty_day"
    return "empty_archive"


def _recompute(meal: dict) -> dict:
    """按 items 重算 totals 并跑交叉核验。ai_price 是模型估的，原样保留。"""
    totals = nutrition.sum_items(meal.get("items") or [])
    price = (meal.get("totals") or {}).get("ai_price")
    if price is not None:
        totals["ai_price"] = price
    meal["totals"] = totals
    return nutrition.cross_check(totals)


# 拉远端图的超时与体积上限。照片是附属信息，记录本身比它重要：拉不下来当没图，
# 不阻断落库，也不让一个卡住的下游把整次 record_meal 拖到脚本超时。
_PHOTO_FETCH_TIMEOUT_SEC = 8
_PHOTO_MAX_BYTES = 20 * 1024 * 1024


def _freeze_photo(meal_id: str, photo_url: str | None) -> str | None:
    """把模型给的图片引用冻结成档案自己的对象，返回 photo_key；拿不到返回 None。

    模型能给的两种引用都活不过这次会话：沙箱路径指向按会话挂载的 inputs，短链有
    自己的有效期。而卡片每次都从档案重新推导，所以落库这一刻是唯一还拿得到字节的
    时机——错过了就只剩兜底图。
    """
    raw = (photo_url or "").strip()
    if not raw:
        return None
    if raw.startswith(("http://", "https://")):
        return _freeze_remote_photo(meal_id, raw)
    src = store.inputs_photo(raw)
    if src is None:
        return None
    try:
        return store.freeze_photo(meal_id, src.read_bytes(), src.suffix)
    except OSError:
        return None


class _PhotoUnreachable(Exception):
    """http(s) 这一下没拉到字节。跟「拉到了但太大不收」分开，后者地址本身还能显示。"""


# 拉不开的地址如果留在 photo_url 上，出卡会把它当成实拍。回执让模型换本轮真图再改。
_UNREACHABLE_PHOTO_NOTE = (
    "这个地址打不开，用本轮 [user_image_url] 原文再 diet_update。"
    "不要沿用刚才这条地址，也不要自己编一条短链。"
)


def _freeze_remote_photo(meal_id: str, url: str) -> str | None:
    """把短链指向的图拉下来存进档案。只在落库这一刻拉，之后短链失效也不影响。

    网络失败或空响应抛 _PhotoUnreachable。超限返回 None：字节已经到了，只是不往卷上写。
    """
    try:
        with urllib.request.urlopen(url, timeout=_PHOTO_FETCH_TIMEOUT_SEC) as resp:
            # 多读一个字节用来判超限：读满上限说明后面还有，这张不收。
            blob = resp.read(_PHOTO_MAX_BYTES + 1)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise _PhotoUnreachable from exc
    if not blob:
        raise _PhotoUnreachable
    if len(blob) > _PHOTO_MAX_BYTES:
        return None
    suffix = PurePosixPath(urllib.parse.urlparse(url).path).suffix
    try:
        return store.freeze_photo(meal_id, blob, suffix)
    except OSError:
        return None


def _apply_photo(meal: dict) -> str | None:
    """冻结 meal 上的 photo_url。拉不开时原地址留在档案里，出卡没有冻结文件就仍用这条地址。"""
    try:
        meal["photo_key"] = _freeze_photo(meal["meal_id"], meal.get("photo_url"))
    except _PhotoUnreachable:
        meal["photo_key"] = None
        return _UNREACHABLE_PHOTO_NOTE
    return None


def _duplicate_photo_warning(photo_url: str | None, date_str: str, meal_id: str) -> str | None:
    """同一天另一条记录already用了这张图，多半是短链抄串了。

    模型手里同时躺着历史几轮的短链，补记第二餐时很容易把上一餐那条抄下来——
    卡片就配上一张别的东西的照片，而落库、校验、出卡全都正常，没有任何地方会报错。
    「同一天两条记录共用一张图」是个纯机械信号，不需要看图也不需要猜意图。

    只告警不拦截：一张合影里拍到两餐、分两条记下来是合法的，虽然少见。
    拦下去会把这种用户逼进反复重试，而告警至少让模型有机会自己发现抄错了。
    """
    if not photo_url:
        return None
    for other in store.load_meals_between(date_str, date_str):
        if other.get("meal_id") == meal_id:
            continue
        if other.get("photo_url") == photo_url:
            return (
                f"这张图 {date_str} 已经挂在另一条记录「{other.get('title')}」上了。"
                "多半是短链抄串了——历史消息里还躺着前几轮的图片链接。"
                "回去核对用户这一轮那条消息旁边的短链，是这张就忽略本条提醒，"
                f"不是就用 diet_update 把 {meal_id} 的 photo_url 改过来。"
            )
    return None


def _cross_check_warning(check: dict) -> str:
    return (
        f"交叉核验偏差 {check.get('delta_pct')}% 超过 5%，"
        "正文里要说明并重估这几项的 kcal/蛋白/脂肪/碳水。"
    )


def _food_names(items: list[dict]) -> list[str]:
    names = [str(item.get("name") or "").strip() for item in items]
    return [name for name in names if name]


def _default_title(items: list[dict]) -> str:
    """没给标题时按食物名补一个，只用来在「看今天吃了什么」里认出是哪一条。"""
    names = _food_names(items)
    if not names:
        return "一餐"
    shown = "、".join(names[:2])
    title = shown if len(names) <= 2 else f"{shown}等{len(names)}样"
    return title[:40]


def _model_receipt(meal: dict, check: dict, extra: dict) -> dict:
    """给模型的回执。只回数字和状态，不要把本回执原样贴进正文。"""
    totals = meal.get("totals") or {}
    receipt = {
        "meal_id": meal.get("meal_id"),
        "meal_type": meal.get("meal_type"),
        "meal_label": store.MEAL_LABEL.get(meal.get("meal_type"), ""),
        "eaten_at": meal.get("eaten_at"),
        "eaten_at_source": meal.get("eaten_at_source"),
        "totals": totals,
        "cross_check": check.get("cross_check"),
        "delta_pct": check.get("delta_pct"),
        "cross_check_passed": check.get("passed"),
    }
    if not check.get("passed"):
        receipt["warning"] = _cross_check_warning(check)
    receipt.update(extra)
    return receipt


_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# 允许的时钟误差。超过这个的「未来用餐时间」按上传时刻收，不让模型把封面写成今晚七点。
_FUTURE_SLACK = timedelta(minutes=2)


def _raw_clock(raw: object) -> datetime | None:
    """用户/模型给的完整时间。只给日期的不算，那种钟点本来就要借此刻。"""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or _DATE_ONLY.fullmatch(text):
        return None
    return store.parse_time(text)


def resolve_eaten_at(raw: object) -> datetime:
    """定这一餐吃在什么时候：没给就是此刻，给了就听给的。

    多出来的一档是「只给了日期」。模型把「昨天」翻成 2026-09-03 是常事，
    直接解析会落到 00:00，餐次被判成夜宵，卡片上也显示成凌晨十二点。
    这种情况日期照用户说的，钟点补成当前时刻。

    再多一档：完整时间落在未来。模型常把英式早餐写成「今晚 19:30 晚餐」，
    封面既不是拍摄时间也不是上传时间。未来钟点一律收成此刻。
    """
    now = store.now()
    if not raw:
        return now
    text = str(raw).strip()
    if not text:
        return now
    when = store.parse_time(text)
    if _DATE_ONLY.fullmatch(text):
        when = when.replace(hour=now.hour, minute=now.minute, second=now.second)
    if when > now + _FUTURE_SLACK:
        return now
    return when


def op_record_meal(args: dict) -> tuple[dict, dict]:
    raw_eaten = args.get("eatenAt")
    eaten_at = resolve_eaten_at(raw_eaten)
    source = args.get("eatenAtSource") or "upload"
    requested = _raw_clock(raw_eaten)
    if requested is not None and requested > store.now() + _FUTURE_SLACK:
        source = "upload"
    date_str = eaten_at.strftime("%Y-%m-%d")
    meal_type = args.get("mealType") or store.derive_meal_type(
        eaten_at, beverage_only=bool(args.get("beverageOnly"))
    )
    now_iso = store.now_iso()

    # 同槽多卡：同一天同一 mealType 再记一次就新建一条，不合并。
    # 午餐先记盖浇饭、后补水果，日视图午餐槽下应并排两张独立卡（各有图、标题、营养）。
    meal = {
        "meal_id": store.new_meal_id(date_str, meal_type),
        "user_id": args.get("userId") or "u_local",
        "eaten_at": eaten_at.replace(microsecond=0).isoformat(),
        "eaten_at_source": source,
        "meal_type": meal_type,
        "title": args.get("title") or _default_title(args["items"]),
        "scene_oneliner": (args.get("sceneOneliner") or "").strip() or default_scene(args["items"]),
        "items": list(args["items"]),
        "totals": {"ai_price": args["aiPrice"]} if args.get("aiPrice") is not None else {},
        "narrative": args.get("narrative") or {},
        "nutrients": args.get("nutrients") or [],
        "photo_url": args.get("photoUrl"),
        "is_favorited": False,
        "created_at": now_iso,
        "updated_at": now_iso,
        "deleted_at": None,
    }
    # 冻结要在落库之前：photo_key 得跟着记录一起落下去，出卡时才有东西可解。
    # 拉不开的 http(s) 会在这里被清掉，后面的出卡和档案都看不到这条地址。
    unreachable = _apply_photo(meal)
    check = _recompute(meal)
    # 落库前查：append 之后自己也会成为「另一条记录」，就永远告警自己了。
    # 比的是模型给的原始引用而不是 photo_key——后者每条记录都不一样，比不出抄串。
    photo_warning = unreachable or _duplicate_photo_warning(meal["photo_url"], date_str, meal["meal_id"])
    store.append_meal(meal)

    payload = build_payload("meal", meal, date_str)
    extra = {
        "saved": True,
        "today_totals": payload["today"]["totals"],
    }
    if photo_warning:
        extra["photo_warning"] = photo_warning
    receipt = _model_receipt(meal, check, extra)
    return receipt, payload


def op_estimate_meal(args: dict) -> tuple[dict, dict]:
    """只算不存，但照样出卡。

    合计和交叉核验跟 record_meal 同一套算法。不调 store 的写接口：测算结果只放在
    这次 payload 的 current_meal 上，今日食书和统计仍读档案，不会被这笔测算污染。
    """
    totals = nutrition.sum_items(args["items"])
    if args.get("aiPrice") is not None:
        totals["ai_price"] = args["aiPrice"]
    check = nutrition.cross_check(totals)
    eaten_at = store.now().replace(microsecond=0)
    date_str = eaten_at.strftime("%Y-%m-%d")
    meal = {
        "meal_id": "m_estimate",
        "user_id": "u_local",
        "eaten_at": eaten_at.isoformat(),
        "eaten_at_source": "upload",
        "meal_type": store.derive_meal_type(eaten_at),
        "title": args.get("title") or _default_title(args["items"]),
        "scene_oneliner": (args.get("sceneOneliner") or "").strip() or default_scene(args["items"]),
        "items": list(args["items"]),
        "totals": totals,
        "narrative": args.get("narrative") or {},
        "nutrients": [],
        "photo_url": args.get("photoUrl"),
        "is_favorited": False,
        "created_at": store.now_iso(),
        "updated_at": store.now_iso(),
        "deleted_at": None,
    }
    payload = build_payload("meal", meal, date_str)
    receipt = {
        "totals": totals,
        "cross_check": check.get("cross_check"),
        "delta_pct": check.get("delta_pct"),
        "cross_check_passed": check.get("passed"),
        "saved": False,
    }
    if not check.get("passed"):
        receipt["warning"] = _cross_check_warning(check)
    return receipt, payload


def op_get_meal(args: dict) -> tuple[dict, dict]:
    meal = store.find_meal(args["mealId"])
    if meal is None:
        raise ContractError("NOT_FOUND", f"没找到 {args['mealId']}，可能已被删除")
    date_str = str(meal.get("eaten_at", ""))[:10]
    payload = build_payload("meal", meal, date_str)
    return _model_receipt(meal, nutrition.cross_check(meal.get("totals") or {}), {}), payload


def _foods_of(meal: dict) -> str:
    parts = []
    for item in meal.get("items") or []:
        name = str(item.get("name") or "").strip()
        portion = str(item.get("portion") or "").strip()
        if name:
            parts.append(f"{name} {portion}" if portion else name)
    return "、".join(parts)


def _day_row(meal: dict) -> dict:
    """当天一餐给模型的样子：每餐自带宏量和食物，日报取数不用再逐餐 get_meal。"""
    totals = meal.get("totals") or {}
    row = {
        "meal_id": meal.get("meal_id"),
        "meal_type": meal.get("meal_type"),
        "label": store.MEAL_LABEL.get(meal.get("meal_type"), ""),
        "time": str(meal.get("eaten_at") or "")[11:16],
        "title": meal.get("title"),
        "foods": _foods_of(meal),
        "has_photo": bool(meal.get("photo_key") or meal.get("photo_url")),
    }
    row.update({key: totals.get(key, 0) for key in nutrition.NUTRIENT_KEYS})
    return row


def op_get_day(args: dict) -> tuple[dict, dict]:
    date_str = args.get("date") or store.now().strftime("%Y-%m-%d")
    payload = build_payload("today", None, date_str)
    today = payload["today"]
    return {
        "date": date_str,
        "totals": today["totals"],
        "skipped_slots": today["skipped_slots"],
        "meals": [_day_row(meal) for meal in store.load_meals_between(date_str, date_str)],
    }, payload


def op_skip_meal(args: dict) -> tuple[dict, dict]:
    """把早/午/晚某一餐标成跳过。不造零热量记录，不进合计。"""
    date_str = args.get("date") or store.now().strftime("%Y-%m-%d")
    meal_type = args["mealType"]
    recorded = [
        meal for meal in store.load_meals_between(date_str, date_str)
        if meal.get("meal_type") == meal_type
    ]
    if recorded:
        raise ContractError(
            "SLOT_RECORDED",
            f"{store.MEAL_LABEL[meal_type]}已经记过，不能标成跳过。要改记录用 diet_update。",
        )
    slots = store.mark_skip(date_str, meal_type)
    payload = build_payload("today", None, date_str)
    return {
        "date": date_str,
        "meal_type": meal_type,
        "skipped": True,
        "skipped_slots": slots,
    }, payload


def op_get_stats(args: dict) -> tuple[dict, dict]:
    date_str = args.get("date") or store.now().strftime("%Y-%m-%d")
    period = args["period"]
    payload = build_payload("stats", None, date_str, period=period)
    return {"period": period, **payload["stats"][period]}, payload


def op_update_meal(args: dict) -> tuple[dict, dict]:
    meal = store.find_meal(args["mealId"])
    if meal is None:
        raise ContractError("NOT_FOUND", f"没找到 {args['mealId']}，可能已被删除")

    patch = args["patch"]
    unknown = [k for k in patch if k not in meal]
    if unknown:
        raise ContractError("INVALID_ARGUMENT", f"patch 里有档案上没有的字段：{', '.join(unknown)}")
    previous_url = meal.get("photo_url")
    previous_key = meal.get("photo_key")
    meal.update(patch)
    unreachable = None
    if "photo_url" in patch:
        # 换图等于换引用，旧 photo_key 指的还是上一张，得重新冻结。
        # 新地址拉不开就留着上一张，不要把打不开的地址放到卡上。
        unreachable = _apply_photo(meal)
        if unreachable:
            meal["photo_url"] = previous_url
            meal["photo_key"] = previous_key
    meal["updated_at"] = store.now_iso()
    # items 改了就必须重算 totals，不能只改一边
    check = _recompute(meal) if "items" in patch else nutrition.cross_check(meal.get("totals") or {})
    store.replace_meal(meal["meal_id"], meal)

    date_str = str(meal.get("eaten_at", ""))[:10]
    payload = build_payload("meal", meal, date_str)
    extra = {
        "changed_fields": sorted(patch),
        "today_totals": payload["today"]["totals"],
    }
    if unreachable:
        extra["photo_warning"] = unreachable
    return _model_receipt(meal, check, extra), payload


def op_delete_meal(args: dict) -> tuple[dict, dict]:
    meal = store.find_meal(args["mealId"])
    if meal is None:
        raise ContractError("NOT_FOUND", f"没找到 {args['mealId']}，可能已经删过了")
    meal["deleted_at"] = store.now_iso()
    meal["updated_at"] = meal["deleted_at"]
    store.replace_meal(meal["meal_id"], meal)

    date_str = str(meal.get("eaten_at", ""))[:10]
    payload = build_payload("today", None, date_str)
    return {
        "meal_id": meal["meal_id"],
        "deleted_at": meal["deleted_at"],
        "deleted": True,
        "today_totals": payload["today"]["totals"],
    }, payload


HANDLERS = {
    "record_meal": op_record_meal,
    "estimate_meal": op_estimate_meal,
    "get_meal": op_get_meal,
    "get_day": op_get_day,
    "skip_meal": op_skip_meal,
    "get_stats": op_get_stats,
    "update_meal": op_update_meal,
    "delete_meal": op_delete_meal,
}


MODEL_VIEW_KEY = "_model"

# 换个调用也不会有不同结果的错误。其余（参数不对、没找到、这餐已记过）改对了再调就行。
_NOT_RETRYABLE = frozenset(("INVALID_PAYLOAD", "INTERNAL_ERROR", "UNKNOWN_TOOL"))


def _error_envelope(code: str, message: str, errors: list[str] | None = None) -> dict:
    """跟训练侧同一个形状：phase / code / message / retryable，多条问题再带 errors。"""
    envelope = {
        "phase": "error",
        "code": code,
        "message": message,
        "retryable": code not in _NOT_RETRYABLE,
    }
    if errors and len(errors) > 1:
        envelope["errors"] = list(errors)
    return envelope


def dispatch(args: dict) -> dict:
    operation = args.get("operation") or ""
    args = validate(operation, args)
    receipt, payload = HANDLERS[operation](args)
    payload["default_tab"] = args.get("tab") or CONTRACT[operation]["defaultTab"]
    # Only a fully valid shared payload may reach either the A2UI or HTML resource.
    # Validate after all derived fields/defaults are applied, before adding model-only metadata.
    validate_payload(payload)
    model_view = {"phase": operation, "ok": True, **receipt}
    # 没东西可显示时**照样下发这份完整载荷**，让卡片走 card_state 的空态分支。
    #
    # 以前这里直接返回只剩 _model 的壳，靠 _run.py「没有业务字段就不发 sentinel」
    # 做到「干脆不出卡」。那个手段在 CLI 这条路上失效了：只要 handler 跑成功，CLI 就
    # 一定按 _meta.ui.resourceUri 追加 sentinel，拦不住。宿主于是收到一份挂着卡片资源、
    # 却没有 current_meal 的数据——卡面所有绑定静默取不到，剩个空壳，还会因为
    # dataMode: keep_latest 把上一张好卡替换掉。
    #
    # 与其让两条路各画一种空白，不如让「没有记录」在卡面上变成一句明确的话。
    # 模型这边照旧收到信号，正文按 SKILL §2.3 写。
    if _nothing_to_render(payload, operation):
        model_view["card_empty"] = _skip_reason(operation)
    payload[MODEL_VIEW_KEY] = model_view
    return payload


def run_operation(operation: str | None = None) -> int:
    """tool 入口。

    ``operation`` 给了就用它——一个 tool 一个 operation，由 tool 名定死，模型既传不进来
    （schema 里没这个字段，additionalProperties: false）也改不掉。八个薄 handler
    脚本各自带着自己的 operation 调这里，业务逻辑仍只有 dispatch 那一份。

    为 None 时从入参里读，直接跑 ``diet_api.py '<json>'`` 调试时走这条。
    """
    raw = sys.argv[1] if len(sys.argv) > 1 else "{}"
    try:
        args = json.loads(raw)
        if not isinstance(args, dict):
            raise ContractError("invalid_argument", "参数必须是 JSON 对象")
        if operation is not None:
            args = {**args, "operation": operation}
        result = dispatch(args)
        # 库在本地盘上跑，这一步把它推回挂载卷。只在本次真写过时才传。
        store.publish()
        code = 0
    except ContractError as exc:
        error = _error_envelope(exc.code, str(exc), exc.errors)
        result, code = {**error, MODEL_VIEW_KEY: error}, 2
    except PayloadValidationError as exc:
        error = _error_envelope("INVALID_PAYLOAD", str(exc))
        result, code = {**error, MODEL_VIEW_KEY: error}, 3
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        error = _error_envelope("INTERNAL_ERROR", str(exc))
        result, code = {**error, MODEL_VIEW_KEY: error}, 1
    print(json.dumps(result, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(run_operation())
