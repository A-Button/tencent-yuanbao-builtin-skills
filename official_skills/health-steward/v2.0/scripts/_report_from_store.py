#!/usr/bin/env python3
"""从已经落库的饮食和训练记录组装 health-report-v1.0 的 report_data。

模型传 ``date`` 时走这里，把库里的饮食和训练收成渲染器要的结构。
取不到的字段填 None，不拿 0 或估出来的餐次顶上。膳食纤维饮食侧没有，日报模板
也不读它。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import _energy
import _health_report_v1
from _errors import ActionError

_WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
_MEAL_KEYS = ("breakfast", "lunch", "dinner")
_NUTRIENTS = ("kcal", "protein_g", "fat_g", "carb_g", "sodium_mg")


def _parse_day(raw: object, field: str) -> date:
    if not isinstance(raw, str):
        raise ActionError("INVALID_ARGUMENT", f"{field} 必须是 YYYY-MM-DD。")
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ActionError("INVALID_ARGUMENT", f"{field} 不是合法日期：{raw}") from exc


def _diet():
    import store as diet

    return diet


def _meals_between(start: str, end: str) -> list[dict]:
    return _diet().load_meals_between(start, end)


def _number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if value == value and abs(value) != float("inf") else None


def _normalized_meal_totals(meal: dict) -> dict:
    totals = meal.get("totals") if isinstance(meal.get("totals"), dict) else {}
    result = {key: _number(totals.get(key)) for key in _NUTRIENTS}
    for key in _NUTRIENTS:
        if result[key] is None:
            result[key] = _number(meal.get(key))
    for item in meal.get("items") or []:
        if not isinstance(item, dict):
            continue
        nutrients = item.get("nutrients") if isinstance(item.get("nutrients"), dict) else item
        for key in _NUTRIENTS:
            if result[key] is None:
                result[key] = 0.0
            result[key] += _number(nutrients.get(key)) or 0.0
    if result["kcal"] is None:
        macros = (result["protein_g"], result["fat_g"], result["carb_g"])
        if any(value is not None for value in macros):
            result["kcal"] = (result["protein_g"] or 0) * 4 + (result["fat_g"] or 0) * 9 + (result["carb_g"] or 0) * 4
    return {key: round(result[key] or 0.0, 1) for key in _NUTRIENTS}


def _meal_report(meal: dict) -> dict:
    diet = _diet()
    label = diet.MEAL_LABEL.get(meal.get("meal_type"), "")
    foods = []
    for item in meal.get("items") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name:
            foods.append({"name": name, "portion": str(item.get("portion") or "").strip()})
    totals = _normalized_meal_totals(meal)
    eaten = str(meal.get("eaten_at") or "")
    names = "、".join(item["name"] for item in foods) or str(meal.get("title") or label)
    kcal = totals.get("kcal")
    return {
        "meal_type": label or meal.get("meal_type"),
        "time": eaten[11:16] if len(eaten) >= 16 else "",
        "photo_url": None,
        "foods": foods,
        "totals": {key: totals.get(key, 0) for key in _NUTRIENTS},
        "scene": str(meal.get("title") or names),
        "signal": f"{label} {kcal} kcal" if kcal is not None else label,
        "source": "record",
        "confidence": "medium",
    }


def _slot_summary(meals: list[dict]) -> dict | None:
    if not meals:
        return None
    foods = []
    kcal = 0.0
    have_kcal = False
    for meal in meals:
        for item in meal.get("items") or []:
            name = str(item.get("name") or "").strip() if isinstance(item, dict) else ""
            if name:
                foods.append(name)
        totals = meal.get("totals") if isinstance(meal.get("totals"), dict) else {}
        if totals.get("kcal") is not None:
            kcal += float(totals["kcal"])
            have_kcal = True
    return {"summary": "、".join(foods), "kcal": int(round(kcal)) if have_kcal else None}


def _targets(store) -> dict:
    target = store.nutrition.nutrition_target()
    mid = {}
    for src, dst in (
        ("kcal", "target_kcal"),
        ("protein_g", "target_protein_g"),
        ("fat_g", "target_fat_g"),
        ("carb_g", "target_carb_g"),
    ):
        bounds = target.get(src) or {}
        low, high = bounds.get("min"), bounds.get("max")
        if isinstance(low, (int, float)) and isinstance(high, (int, float)):
            mid[dst] = int(round((float(low) + float(high)) / 2))
        else:
            mid[dst] = None
    return mid


def _profile(store, day: str) -> dict:
    profile = store.workout.body_profile() or {}
    weight = store.workout.latest_weight_on_or_before(day)
    payload = {
        "height_cm": profile.get("height_cm"),
        "weight_kg": weight,
        "age": profile.get("age"),
        "sex": profile.get("sex"),
        "goal": None,
    }
    payload.update(_targets(store))
    return payload


def _burn(store, day: str) -> dict:
    import _workout

    result = _energy.expenditure(
        _workout.body_profile_payload(store.workout),
        store.workout.latest_weight_on_or_before(day),
        *_workout.session_energy_inputs(store.workout, day),
    )
    source = "steps_estimate" if result.get("daily_activity_estimated") else "unknown"
    if result.get("daily_activity") is None:
        source = "unknown"
    return result, source


def _exercise_rows(store, day: str, weight) -> list[dict]:
    import _workout

    session = store.workout.session_on(day)
    if session is None:
        return []
    rows = []
    reference_weight = float(weight) if _number(weight) and float(weight) > 0 else 60.0
    for row in store.workout.exercises_of(session["id"]):
        if not row.get("done"):
            continue
        stamp = str(row.get("updated_at") or "")
        entry = _workout.library_entry(row.get("exercise_key")) or {}
        sets = int(_number(row.get("sets")) or 0)
        reps = int(_number(row.get("reps")) or 0)
        try:
            minutes = _energy.estimated_duration_minutes(
                [{
                    "sets": sets,
                    "reps": reps,
                    "rep_unit": _workout.rep_unit_of(row.get("exercise_key")),
                }]
            )
        except _energy.EnergyInputError:
            minutes = 0.0
        met = _number(entry.get("met")) or 3.5
        kcal = int(round(_energy.training_burn(met, reference_weight, minutes))) if minutes > 0 else 0
        rows.append({
            "name": row.get("name"),
            "time": stamp[11:16] if len(stamp) >= 16 else "",
            "duration_min": round(minutes, 1),
            "sets": sets,
            "reps": reps,
            "kcal": kcal,
            "source": "workout" if weight else "workout_reference_60kg",
        })
    return rows


def assemble_daily(args: dict, store) -> dict:
    day = _parse_day(args.get("date"), "date")
    iso = day.isoformat()
    meals = [_meal_report(meal) for meal in _meals_between(iso, iso)]
    burn, source = _burn(store, iso)
    weight = store.workout.latest_weight_on_or_before(iso)
    return {
        "report_type": "daily",
        "date": iso,
        "weekday": _WEEKDAYS[day.weekday()],
        "day_complete_confirmed": bool(args.get("day_complete_confirmed")),
        "profile": _profile(store, iso),
        "meals": meals,
        "exercises": _exercise_rows(store, iso, weight),
        "bmr_kcal": burn.get("bmr"),
        "daily_activity_kcal": burn.get("daily_activity"),
        "daily_activity_source": source,
    }


def _week_bounds(args: dict) -> tuple[date, date]:
    if args.get("week_start"):
        start = _parse_day(args.get("week_start"), "week_start")
        if start.weekday() != 0:
            raise ActionError("INVALID_ARGUMENT", "week_start 必须是周一。")
    else:
        day = _parse_day(args.get("date"), "date")
        start = day - timedelta(days=day.weekday())
    end = start + timedelta(days=6)
    return start, end


def assemble_weekly(args: dict, store) -> dict:
    start, end = _week_bounds(args)
    meals = _meals_between(start.isoformat(), end.isoformat())
    by_day: dict[str, list[dict]] = {}
    for meal in meals:
        by_day.setdefault(str(meal.get("eaten_at") or "")[:10], []).append(meal)
    days = []
    for offset in range(7):
        day = start + timedelta(days=offset)
        iso = day.isoformat()
        grouped = {key: [] for key in _MEAL_KEYS}
        for meal in by_day.get(iso, []):
            kind = meal.get("meal_type")
            if kind in grouped:
                grouped[kind].append(meal)
        slots = {key: _slot_summary(grouped[key]) for key in _MEAL_KEYS}
        nutrition = None
        if any(grouped.values()):
            nutrition = {"protein_g": 0.0, "fat_g": 0.0, "carb_g": 0.0}
            for meal in by_day.get(iso, []):
                totals = meal.get("totals") if isinstance(meal.get("totals"), dict) else {}
                for key in nutrition:
                    nutrition[key] += float(totals.get(key) or 0)
            nutrition = {key: int(round(value)) for key, value in nutrition.items()}
        burn, _source = _burn(store, iso)
        exercises = _exercise_rows(store, iso, store.workout.latest_weight_on_or_before(iso))
        exercise_slots = {"noon": None, "commute": None, "evening": None}
        if exercises:
            exercise_slots["evening"] = {
                "summary": "、".join(str(item.get("name") or "") for item in exercises),
                "kcal": sum(item["kcal"] for item in exercises if item.get("kcal") is not None) or None,
            }
        intake = None
        if any(slots.values()):
            parts = [slot["kcal"] for slot in slots.values() if slot and slot.get("kcal") is not None]
            intake = sum(parts) if parts else None
        days.append({
            "date": iso,
            "meals": slots,
            "nutrition": nutrition,
            "exercise_slots": exercise_slots,
            "intake_kcal": intake,
            "bmr_kcal": burn.get("bmr"),
            "daily_activity_kcal": burn.get("daily_activity"),
            "active_kcal": burn.get("training") if exercises else 0,
            "total_burn_kcal": burn.get("total"),
        })
    report = {
        "report_type": "weekly",
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "profile": _profile(store, end.isoformat()),
        "days": days,
    }
    return report


def build_daily_from_store(args: dict, store) -> dict:
    return _health_report_v1.build_daily(assemble_daily(args, store))


def build_weekly_from_store(args: dict, store) -> dict:
    return _health_report_v1.build_weekly(assemble_weekly(args, store))
