#!/usr/bin/env python3
"""Strict validation for the shared A2UI/HTML structuredContent payload."""

from __future__ import annotations

import math
import re
from datetime import datetime

from cli_contract import PERIODS, TABS
from nutrition import NUTRIENT_KEYS
from store import MEAL_TYPES

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}$")
MEAL_SOURCES = {"photo", "upload", "user"}

ITEM_KEYS = {
    "name", "portion", "emoji", "origin", "kcal", "protein_g", "fat_g",
    "carb_g", "sodium_mg", "story", "data_source", "assumptions",
}
ITEM_REQUIRED = {
    "name", "portion", "emoji", "origin", "kcal", "protein_g", "fat_g",
    "carb_g", "sodium_mg",
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
        for key in ("name", "portion", "emoji", "origin"):
            _string(item[key], f"{item_path}.{key}", nonempty=True)
        for key in NUTRIENT_KEYS:
            _number(item[key], f"{item_path}.{key}")
        for key in ("story", "data_source", "assumptions"):
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
        "meal_id", "user_id", "title", "scene_oneliner", "meal_type_display",
        "card_title", "foods_label", "photo_badge", "jump_url",
    ):
        _string(meal[key], f"{path}.{key}", nonempty=True)
    _iso_datetime(meal["eaten_at"], f"{path}.eaten_at")
    _enum(meal["eaten_at_source"], f"{path}.eaten_at_source", MEAL_SOURCES)
    _enum(meal["meal_type"], f"{path}.meal_type", MEAL_TYPES)
    _validate_items(meal["items"], f"{path}.items")
    _validate_totals(meal["totals"], f"{path}.totals")
    if "ai_price" in meal:
        _number(meal["ai_price"], f"{path}.ai_price")
    if "ai_price_display" in meal:
        _string(meal["ai_price_display"], f"{path}.ai_price_display", nonempty=True)
    _validate_narrative(meal["narrative"], f"{path}.narrative")
    if "nutrients" in meal:
        _strings(meal["nutrients"], f"{path}.nutrients")
    _nullable_string(meal["photo_url"], f"{path}.photo_url")
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
        item = _object(item_value, item_path, {"name"}, {"name"})
        _string(item["name"], f"{item_path}.name", nonempty=True)
    _validate_totals(meal["totals"], f"{path}.totals", kcal_only=True)
    _strings(meal["nutrients"], f"{path}.nutrients")
    _nullable_string(meal["photo_url"], f"{path}.photo_url")
    _nullable_string(meal["photo_key"], f"{path}.photo_key")


def _validate_today(value: object, path: str) -> None:
    today = _object(value, path, {"date", "meals_by_type", "totals"}, {"date", "meals_by_type", "totals"})
    date = _string(today["date"], f"{path}.date", nonempty=True)
    if not DATE_RE.fullmatch(date):
        _fail(f"{path}.date", "必须是 YYYY-MM-DD")
    grouped = _object(today["meals_by_type"], f"{path}.meals_by_type", set(MEAL_TYPES), set(MEAL_TYPES))
    for meal_type in MEAL_TYPES:
        for index, meal in enumerate(_array(grouped[meal_type], f"{path}.meals_by_type.{meal_type}")):
            _validate_summary_meal(meal, f"{path}.meals_by_type.{meal_type}[{index}]")
    _validate_totals(today["totals"], f"{path}.totals")


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


def validate_payload(payload: object) -> dict:
    """Return the payload unchanged after validating every dispatched field."""
    top_keys = {"current_meal", "today", "stats", "default_tab", "default_period"}
    result = _object(payload, "payload", top_keys, top_keys)
    current = result["current_meal"]
    if not isinstance(current, dict):
        _fail("payload.current_meal", "必须是对象")
    if current:
        _validate_meal(current, "payload.current_meal")
    _validate_today(result["today"], "payload.today")
    _validate_stats(result["stats"], "payload.stats")
    _enum(result["default_tab"], "payload.default_tab", TABS)
    _enum(result["default_period"], "payload.default_period", PERIODS)
    return result
