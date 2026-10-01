#!/usr/bin/env python3
"""Strict validation for the shared A2UI/HTML structuredContent payload."""

from __future__ import annotations

import math
import re
from datetime import datetime

from cli_contract import PERIODS, TABS
from nutrition import NUTRIENT_KEYS
from store import MEAL_TYPES, SKIP_SLOTS

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}$")
MEAL_SOURCES = {"photo", "upload", "user"}

ITEM_KEYS = {
    "name", "portion", "emoji", "origin", "kcal", "protein_g", "fat_g",
    "carb_g", "sodium_mg", "story", "data_source", "assumptions",
}
# emoji 由出卡前补上（XCard 食物行要画）；origin 不上卡。有就得是字符串。
ITEM_REQUIRED = {
    "name", "portion", "kcal", "protein_g", "fat_g", "carb_g", "sodium_mg",
}
MEAL_KEYS = {
    "meal_id", "user_id", "eaten_at", "eaten_at_source", "meal_type",
    "meal_type_display", "title", "scene_oneliner", "items", "totals",
    "narrative", "nutrients", "photo_url", "photo_key", "is_favorited",
    "created_at", "updated_at", "deleted_at",
    # XCard template bindings (same object, not a second payload)
    "card_title", "foods_label", "photo_badge", "jump_url",
    "ai_price", "ai_price_display",
}
MEAL_REQUIRED = {
    "meal_id", "user_id", "eaten_at", "eaten_at_source", "meal_type",
    "meal_type_display", "title", "scene_oneliner", "items", "totals",
    "narrative", "photo_url", "is_favorited", "created_at", "updated_at",
    "deleted_at", "card_title", "foods_label", "photo_badge", "jump_url",
}
NARRATIVE_KEYS = {"key_signals", "metabolism", "care", "followup"}
SUMMARY_MEAL_KEYS = {
    "meal_id", "title", "meal_type", "eaten_at", "items", "totals",
    "nutrients", "photo_url", "photo_key",
}
STAT_KEYS = {
    "range_days", "meal_count", "avg", "daily_kcal_trend", "trend_labels",
    "nutrition_composition", "regularity_score", "avg_meal_time",
}


CARD_STATE_KEYS = {
    "has_meal", "is_empty", "empty_text", "title", "jump_url",
    "brand", "headline",
    "show_roster", "show_stats",
    "selected",
    "breakfast", "lunch", "dinner",
}
CARD_SLOT_KEYS = {
    "name", "detail", "has_detail", "has_photo", "no_photo",
    "photo_url", "emoji", "status", "is_current", "not_current",
    "done", "not_done",
}
CARD_TODAY_KEYS = {"has_meals", "summary", "meals"}
CARD_TODAY_MEAL_KEYS = {
    "heading", "title", "foods", "kcal", "photo_url",
}
CARD_STATS_KEYS = {"period", "summary", "avg_kcal", "avg_macros", "regularity"}


class PayloadValidationError(ValueError):
    """Raised when data is unsafe to dispatch to either UI renderer."""


def _fail(path: str, message: str) -> None:
    raise PayloadValidationError(f"{path}: {message}")


def _object(value: object, path: str, required: set[str], allowed: set[str]) -> dict:
    if not isinstance(value, dict):
        _fail(path, "必须是对象")
    missing = sorted(required - value.keys())
    if missing:
        _fail(path, f"缺字段：{', '.join(missing)}")
    unknown = sorted(value.keys() - allowed)
    if unknown:
        _fail(path, f"有未知字段：{', '.join(unknown)}")
    return value


def _array(value: object, path: str) -> list:
    if not isinstance(value, list):
        _fail(path, "必须是数组")
    return value


def _string(value: object, path: str, *, nonempty: bool = False) -> str:
    if not isinstance(value, str):
        _fail(path, "必须是字符串")
    if nonempty and not value.strip():
        _fail(path, "不能为空")
    return value


def _nullable_string(value: object, path: str) -> None:
    if value is not None:
        _string(value, path)


def _number(value: object, path: str, *, minimum: float = 0) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(path, "必须是数字")
    if not math.isfinite(float(value)):
        _fail(path, "必须是有限数字")
    if value < minimum:
        _fail(path, f"不能小于 {minimum:g}")


def _integer(value: object, path: str, *, minimum: int = 0) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(path, "必须是整数")
    if value < minimum:
        _fail(path, f"不能小于 {minimum}")


def _enum(value: object, path: str, values: list[str] | set[str]) -> None:
    if value not in values:
        _fail(path, f"只能是 {', '.join(sorted(values))}")


def _iso_datetime(value: object, path: str, *, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    raw = _string(value, path, nonempty=True)
    try:
        datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        _fail(path, "必须是 ISO 8601 时间")  # noqa: B904


def _strings(value: object, path: str) -> None:
    for index, item in enumerate(_array(value, path)):
        _string(item, f"{path}[{index}]", nonempty=True)


def _validate_totals(value: object, path: str, *, kcal_only: bool = False) -> None:
    required = {"kcal"} if kcal_only else set(NUTRIENT_KEYS)
    allowed = required if kcal_only else required | {"ai_price"}
    totals = _object(value, path, required, allowed)
    for key in required:
        _number(totals[key], f"{path}.{key}")
    if not kcal_only and "ai_price" in totals:
        _number(totals["ai_price"], f"{path}.ai_price")


def _validate_items(value: object, path: str) -> None:
    for index, item_value in enumerate(_array(value, path)):
        item_path = f"{path}[{index}]"
        item = _object(item_value, item_path, ITEM_REQUIRED, ITEM_KEYS)
        for key in ("name", "portion"):
            _string(item[key], f"{item_path}.{key}", nonempty=True)
        for key in NUTRIENT_KEYS:
            _number(item[key], f"{item_path}.{key}")
        for key in ("emoji", "origin", "story", "data_source", "assumptions"):
            if key in item:
                _string(item[key], f"{item_path}.{key}")


def _validate_narrative(value: object, path: str) -> None:
    narrative = _object(value, path, set(), NARRATIVE_KEYS)
    if "key_signals" in narrative:
        _strings(narrative["key_signals"], f"{path}.key_signals")
    for key in ("metabolism", "care", "followup"):
        if key in narrative:
            _string(narrative[key], f"{path}.{key}")


def _validate_meal(value: object, path: str) -> None:
    meal = _object(value, path, MEAL_REQUIRED, MEAL_KEYS)
    for key in (
        "meal_id", "user_id", "title", "meal_type_display",
        "card_title", "foods_label", "photo_badge", "jump_url",
    ):
        _string(meal[key], f"{path}.{key}", nonempty=True)
    # 场景速写在详情页深色那一块。模型没传时脚本已经按食物名补过，这里只要求是字符串。
    _string(meal["scene_oneliner"], f"{path}.scene_oneliner")
    _iso_datetime(meal["eaten_at"], f"{path}.eaten_at")
    _enum(meal["eaten_at_source"], f"{path}.eaten_at_source", MEAL_SOURCES)
    _enum(meal["meal_type"], f"{path}.meal_type", MEAL_TYPES)
    _validate_items(meal["items"], f"{path}.items")
    for index, item in enumerate(meal["items"]):
        emoji = item.get("emoji") if isinstance(item, dict) else None
        if not isinstance(emoji, str) or not emoji.strip():
            _fail(f"{path}.items[{index}].emoji", "XCard 食物行要有 emoji")
    _validate_totals(meal["totals"], f"{path}.totals")
    if "ai_price" in meal:
        _number(meal["ai_price"], f"{path}.ai_price")
    if "ai_price_display" in meal:
        _string(meal["ai_price_display"], f"{path}.ai_price_display", nonempty=True)
    _validate_narrative(meal["narrative"], f"{path}.narrative")
    if "nutrients" in meal:
        _strings(meal["nutrients"], f"{path}.nutrients")
    _nullable_string(meal["photo_url"], f"{path}.photo_url")
    photo = meal["photo_url"]
    if not isinstance(photo, str) or not photo.startswith(("https://", "http://")):
        _fail(f"{path}.photo_url", "XCard 只认 http(s) 图片地址")
    _enum(meal["photo_badge"], f"{path}.photo_badge", {"实拍", "无图"})
    # 冻结之前落的记录没有这个字段，所以是可选的。
    if "photo_key" in meal:
        _nullable_string(meal["photo_key"], f"{path}.photo_key")
    if not isinstance(meal["is_favorited"], bool):
        _fail(f"{path}.is_favorited", "必须是布尔值")
    _iso_datetime(meal["created_at"], f"{path}.created_at")
    _iso_datetime(meal["updated_at"], f"{path}.updated_at")
    _iso_datetime(meal["deleted_at"], f"{path}.deleted_at", nullable=True)


def _validate_summary_meal(value: object, path: str) -> None:
    meal = _object(value, path, SUMMARY_MEAL_KEYS, SUMMARY_MEAL_KEYS)
    _string(meal["meal_id"], f"{path}.meal_id", nonempty=True)
    _string(meal["title"], f"{path}.title", nonempty=True)
    _enum(meal["meal_type"], f"{path}.meal_type", MEAL_TYPES)
    _iso_datetime(meal["eaten_at"], f"{path}.eaten_at")
    for index, item_value in enumerate(_array(meal["items"], f"{path}.items")):
        item_path = f"{path}.items[{index}]"
        item = _object(item_value, item_path, {"name", "portion"}, {"name", "portion"})
        _string(item["name"], f"{item_path}.name", nonempty=True)
        # 老记录里没有 portion，补成空串而不是必填——卡面那行会退成只列菜名。
        _string(item["portion"], f"{item_path}.portion")
    _validate_totals(meal["totals"], f"{path}.totals", kcal_only=True)
    _strings(meal["nutrients"], f"{path}.nutrients")
    _nullable_string(meal["photo_url"], f"{path}.photo_url")
    _nullable_string(meal["photo_key"], f"{path}.photo_key")


def _validate_today(value: object, path: str) -> None:
    today = _object(
        value, path,
        {"date", "meals_by_type", "totals", "skipped_slots"},
        {"date", "meals_by_type", "totals", "skipped_slots"},
    )
    date = _string(today["date"], f"{path}.date", nonempty=True)
    if not DATE_RE.fullmatch(date):
        _fail(f"{path}.date", "必须是 YYYY-MM-DD")
    grouped = _object(today["meals_by_type"], f"{path}.meals_by_type", set(MEAL_TYPES), set(MEAL_TYPES))
    for meal_type in MEAL_TYPES:
        for index, meal in enumerate(_array(grouped[meal_type], f"{path}.meals_by_type.{meal_type}")):
            _validate_summary_meal(meal, f"{path}.meals_by_type.{meal_type}[{index}]")
    _validate_totals(today["totals"], f"{path}.totals")
    skipped = _array(today["skipped_slots"], f"{path}.skipped_slots")
    seen: set[str] = set()
    for index, slot in enumerate(skipped):
        _enum(slot, f"{path}.skipped_slots[{index}]", SKIP_SLOTS)
        if slot in seen:
            _fail(f"{path}.skipped_slots", f"重复的餐次 {slot}")
        seen.add(slot)


def _validate_stat(value: object, path: str) -> None:
    stat = _object(value, path, STAT_KEYS, STAT_KEYS)
    _integer(stat["range_days"], f"{path}.range_days", minimum=1)
    _integer(stat["meal_count"], f"{path}.meal_count")
    avg = _object(
        stat["avg"], f"{path}.avg",
        {"kcal", "protein_g", "carb_g", "fat_g"},
        {"kcal", "protein_g", "carb_g", "fat_g"},
    )
    for key, number in avg.items():
        _number(number, f"{path}.avg.{key}")

    trend = _array(stat["daily_kcal_trend"], f"{path}.daily_kcal_trend")
    for index, number in enumerate(trend):
        _number(number, f"{path}.daily_kcal_trend[{index}]")
    labels = _array(stat["trend_labels"], f"{path}.trend_labels")
    for index, label in enumerate(labels):
        _string(label, f"{path}.trend_labels[{index}]")
    if len(trend) != len(labels):
        _fail(path, "daily_kcal_trend 与 trend_labels 长度必须一致")

    composition = _array(stat["nutrition_composition"], f"{path}.nutrition_composition")
    if len(composition) != len(trend):
        _fail(path, "nutrition_composition 与 daily_kcal_trend 长度必须一致")
    composition_keys = {"date", "protein_g", "carb_g", "fat_g"}
    for index, row_value in enumerate(composition):
        row_path = f"{path}.nutrition_composition[{index}]"
        row = _object(row_value, row_path, composition_keys, composition_keys)
        _string(row["date"], f"{row_path}.date")
        for key in composition_keys - {"date"}:
            _number(row[key], f"{row_path}.{key}")

    # 样本不够时由 nutrition.DEFAULT_REGULARITY 兜底，所以这里不再放行 null——
    # 卡片上那个圈没有空着的形态，漏一个 None 过去就是一张开天窗的卡。
    score = stat["regularity_score"]
    _integer(score, f"{path}.regularity_score")
    if score > 100:
        _fail(f"{path}.regularity_score", "不能大于 100")
    times = _object(
        stat["avg_meal_time"], f"{path}.avg_meal_time",
        set(), {"breakfast", "lunch", "dinner"},
    )
    for meal_type, value in times.items():
        raw = _string(value, f"{path}.avg_meal_time.{meal_type}", nonempty=True)
        if not TIME_RE.fullmatch(raw):
            _fail(f"{path}.avg_meal_time.{meal_type}", "必须是 HH:MM")


def _validate_stats(value: object, path: str) -> None:
    stats = _object(value, path, {"default_period", "day", "week"}, {"default_period", "day", "week"})
    _enum(stats["default_period"], f"{path}.default_period", PERIODS)
    _validate_stat(stats["day"], f"{path}.day")
    _validate_stat(stats["week"], f"{path}.week")


def _validate_card_state(value: object, path: str, *, has_meal: bool) -> None:
    """卡面开关位。两个布尔必须互斥，且要跟 current_meal 是否有值一致。

    不一致就是卡片会画错的前兆：``has_meal`` 为真而 ``current_meal`` 是空的，卡面会
    去画一块取不到任何路径的餐体；反过来则是有餐却显示「今天还没有记录」。这两种都
    不会报错，只会安静地画错，所以在这里拦。
    """
    state = _object(value, path, CARD_STATE_KEYS, CARD_STATE_KEYS)
    for key in ("has_meal", "is_empty", "show_roster", "show_stats"):
        if not isinstance(state[key], bool):
            _fail(f"{path}.{key}", "必须是布尔值")
    if state["has_meal"] == state["is_empty"]:
        _fail(path, "has_meal 与 is_empty 必须互斥")
    if state["has_meal"] != has_meal:
        _fail(path, f"has_meal={state['has_meal']} 与 current_meal 是否有值（{has_meal}）不一致")
    if state["show_roster"] == state["show_stats"]:
        _fail(path, "show_roster 与 show_stats 必须且只能有一个为 true")
    for key in (
        "empty_text", "title", "jump_url", "brand", "headline",
    ):
        if not isinstance(state[key], str):
            _fail(f"{path}.{key}", "必须是字符串")
        if not state[key].strip():
            _fail(f"{path}.{key}", "不能为空")
    for key in ("breakfast", "lunch", "dinner"):
        _validate_card_slot(state[key], f"{path}.{key}")
    if sum(state[key]["is_current"] for key in ("breakfast", "lunch", "dinner")) != 1:
        _fail(path, "早/午/晚三行里必须且只能有一行 is_current=true")
    selected = _array(state["selected"], f"{path}.selected")
    if selected:
        _fail(f"{path}.selected", "必须是空数组：勾选只发生在端上，预填会让点完按钮跳回第一行")


def _validate_card_slot(value: object, path: str) -> None:
    """花名册的一行。

    四对开关（``has_detail`` / ``has_photo`` / ``is_current`` / ``done`` 和它们的反位）是给
    ``Visibility`` 用的，正反不一致会让卡面同时画出两套文字或者一套都不画——两种都
    不报错，只会安静地画错，所以在这里拦。
    """
    slot = _object(value, path, CARD_SLOT_KEYS, CARD_SLOT_KEYS)
    for key in ("has_detail", "has_photo", "no_photo", "is_current", "not_current", "done", "not_done"):
        if not isinstance(slot[key], bool):
            _fail(f"{path}.{key}", "必须是布尔值")
    if slot["has_photo"] == slot["no_photo"]:
        _fail(path, "has_photo 与 no_photo 必须互斥")
    if slot["is_current"] == slot["not_current"]:
        _fail(path, "is_current 与 not_current 必须互斥")
    if slot["done"] == slot["not_done"]:
        _fail(path, "done 与 not_done 必须互斥")
    for key in ("name", "detail", "photo_url", "status"):
        if not isinstance(slot[key], str):
            _fail(f"{path}.{key}", "必须是字符串")
    _string(slot["name"], f"{path}.name", nonempty=True)
    _enum(slot["status"], f"{path}.status", {"✓", "○"})
    # detail / photo_url 允许为空串，但开关说有就必须真有。
    if slot["has_detail"] and not slot["detail"].strip():
        _fail(f"{path}.detail", "has_detail=true 时必须有文案")
    if slot["has_photo"] and not slot["photo_url"].strip():
        _fail(f"{path}.photo_url", "has_photo=true 时必须有图片地址")


def _validate_card_today(value: object, path: str) -> None:
    card = _object(value, path, CARD_TODAY_KEYS, CARD_TODAY_KEYS)
    if not isinstance(card["has_meals"], bool):
        _fail(f"{path}.has_meals", "必须是布尔值")
    _string(card["summary"], f"{path}.summary", nonempty=True)
    meals = _array(card["meals"], f"{path}.meals")
    if card["has_meals"] != bool(meals):
        _fail(f"{path}.has_meals", "必须与 meals 是否为空一致")
    for index, value in enumerate(meals):
        item_path = f"{path}.meals[{index}]"
        item = _object(value, item_path, CARD_TODAY_MEAL_KEYS, CARD_TODAY_MEAL_KEYS)
        for key in CARD_TODAY_MEAL_KEYS:
            _string(item[key], f"{item_path}.{key}", nonempty=True)


def _validate_card_stats(value: object, path: str) -> None:
    card = _object(value, path, CARD_STATS_KEYS, CARD_STATS_KEYS)
    for key in CARD_STATS_KEYS:
        _string(card[key], f"{path}.{key}", nonempty=True)


def validate_payload(payload: object) -> dict:
    """Return the payload unchanged after validating every dispatched field."""
    top_keys = {
        "current_meal", "today", "stats", "default_tab", "default_period",
        "card_state", "card_today", "card_stats",
    }
    result = _object(payload, "payload", top_keys, top_keys)
    current = result["current_meal"]
    if not isinstance(current, dict):
        _fail("payload.current_meal", "必须是对象")
    if current:
        _validate_meal(current, "payload.current_meal")
    _validate_card_state(result["card_state"], "payload.card_state", has_meal=bool(current))
    _validate_card_today(result["card_today"], "payload.card_today")
    _validate_card_stats(result["card_stats"], "payload.card_stats")
    _validate_today(result["today"], "payload.today")
    _validate_stats(result["stats"], "payload.stats")
    _enum(result["default_tab"], "payload.default_tab", TABS)
    _enum(result["default_period"], "payload.default_period", PERIODS)
    return result
