#!/usr/bin/env python3
"""到点该不该发、以及完整的 show_widget 入参。

模型不要自己拼 Now 卡。调这个工具，``send`` 为 false 就停；为 true 就把
``show_widget`` 原样交给宿主的 show_widget，不要改字段、不要再搜图。

配图来自 ``assets/now_images.json`` 里的长期 HTTPS 地址。已记录餐次只有在档案里
存的就是公网 https 地址时才用那张，沙箱路径和短链不上卡。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from _errors import ActionError
from _store import CrossStore, run

CST = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
_IMAGES = json.loads((ROOT / "assets" / "now_images.json").read_text(encoding="utf-8"))
_SLOTS = ("breakfast", "lunch", "dinner")
_SLOT_TITLE = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐"}
_TODO = {
    "s1": "todo-s1-meals",
    "s2": "todo-s2-train",
    "s3": "todo-s3-daily",
    "s4": "todo-s4-weekly",
}


def _https(value: object) -> str | None:
    if isinstance(value, str) and value.startswith("https://"):
        return value
    return None


def _library(group: str, key: str) -> str | None:
    bucket = _IMAGES.get(group) or {}
    if not isinstance(bucket, dict):
        return None
    return _https(bucket.get(key) or bucket.get("default"))


def _day(args: dict):
    raw = args.get("date")
    if raw in (None, ""):
        return datetime.now(CST).date()
    try:
        return datetime.strptime(str(raw), "%Y-%m-%d").date()
    except ValueError as exc:
        raise ActionError("INVALID_ARGUMENT", f"date 不是合法日期：{raw}") from exc


def _slot(args: dict) -> str:
    slot = args.get("slot")
    if slot in _SLOTS:
        return slot
    if slot not in (None, ""):
        raise ActionError("INVALID_ARGUMENT", "slot 只能是 breakfast / lunch / dinner。")
    hour = datetime.now(CST).hour
    if hour < 10:
        return "breakfast"
    if hour < 15:
        return "lunch"
    return "dinner"


def _bind(args: dict, scene: str) -> dict:
    thing = str(args.get("thing_id") or "").strip()
    if not thing:
        return {}
    todo = str(args.get("todo_id") or _TODO[scene]).strip()
    return {"thingId": thing, "todoId": todo}


def _source() -> dict:
    return {"label": "健康记录"}


def _button(action_id: str, label: str, prompt: str) -> dict:
    return {
        "action_id": action_id,
        "label": label,
        "tap": {"type": 1, "agent_chat": {"send_prompt": prompt}},
    }


def _option(option_id: str, title: str, desc: str, image: str | None, done: bool) -> dict:
    row = {"option_id": option_id, "title": title, "desc": desc}
    if image:
        row["image"] = image
    if done:
        row["done"] = True
        row["selected"] = False
    else:
        row["selected"] = True
    return row


def _hold(scene: str, reason: str, **extra) -> dict:
    return {"send": False, "scene": scene, "reason": reason, **extra}


def _diet_day(day: str) -> tuple[dict[str, list], set[str]]:
    import store as diet

    grouped: dict[str, list] = {slot: [] for slot in _SLOTS}
    for meal in diet.load_meals_between(day, day):
        kind = meal.get("meal_type")
        if kind in grouped:
            grouped[kind].append(meal)
    return grouped, set(diet.skipped_slots(day))


def _foods(meals: list) -> str:
    names = []
    for meal in meals:
        for item in meal.get("items") or []:
            name = str(item.get("name") or "").strip() if isinstance(item, dict) else ""
            if name:
                names.append(name)
    return "+".join(names)


def _photo(meals: list, slot: str) -> str | None:
    for meal in meals:
        url = _https(meal.get("photo_url"))
        if url:
            return url
    return _library("meals", slot)


def _s1(args: dict, store: CrossStore) -> dict:
    del store
    day = _day(args)
    slot = _slot(args)
    grouped, skipped = _diet_day(day.isoformat())

    def settled(kind: str) -> bool:
        return bool(grouped[kind]) or kind in skipped

    if settled(slot):
        why = "已记录" if grouped[slot] else "已跳过"
        return _hold("s1", f"{_SLOT_TITLE[slot]}{why}，这次不发。")

    options = []
    for kind in _SLOTS:
        title = _SLOT_TITLE[kind]
        if grouped[kind]:
            kcal = 0
            for meal in grouped[kind]:
                totals = meal.get("totals") if isinstance(meal.get("totals"), dict) else {}
                kcal += float(totals.get("kcal") or 0)
            foods = _foods(grouped[kind]) or title
            desc = f"已吃 · {foods}，约{int(round(kcal))}kcal，已记下"
            options.append(_option(kind, title, desc, _photo(grouped[kind], kind), True))
        elif kind in skipped:
            options.append(_option(kind, title, "已跳过", _library("meals", kind), True))
        else:
            options.append(_option(kind, title, "待记录 · 拍一张我帮你算", _library("meals", kind), False))
    card = {
        "card_type": "todo_choice",
        "title": "今天的三餐，看看还差哪顿",
        "summary": f"{day.month}月{day.day}日 · 三餐打卡状态，可多选确认",
        "source": _source(),
        "actions": [
            _button("a_go_record", "去记录", "我要记"),
            _button("a_skip", "不吃了", "我要跳过"),
        ],
        "data": {"select_mode": 2, "options": options},
        **_bind(args, "s1"),
    }
    return {"send": True, "scene": "s1", "slot": slot, "show_widget": card}


def _s2(args: dict, store: CrossStore) -> dict:
    import _workout

    day = _day(args).isoformat()
    session = store.workout.session_on(day)
    if session is None:
        return _hold("s2", "今天没有排期，不发。")
    rows = [_workout._decorate_exercise(row) for row in store.workout.exercises_of(session["id"])]
    if not rows:
        return _hold("s2", "今天的排期里没有动作，不发。")
    pending = [row for row in rows if not row["done"]]
    finished = [row for row in rows if row["done"]]
    ordered = pending + finished
    shown = ordered[:3]
    options = []
    for row in shown:
        image = _library("exercises", row.get("exercise_key")) or _library("exercises", "default")
        options.append(_option(row["id"], row["name"], row["meta"], image, bool(row["done"])))
    rest = len(ordered) - len(shown)
    summary = f"{day[5:]} · {session.get('plan_name') or '今日训练'}"
    if rest:
        summary += f" · 还有 {rest} 个动作"
    card = {
        "card_type": "todo_choice",
        "title": "今天的训练",
        "summary": summary,
        "source": _source(),
        "actions": [
            _button("a_adjust", "改计划", "我想调整"),
            _button("a_done", "练了这些，帮我记上", "我练完了"),
        ],
        "data": {"select_mode": 2, "options": options},
        **_bind(args, "s2"),
    }
    return {"send": True, "scene": "s2", "show_widget": card}


def _report_card(scene: str, args: dict, report: dict, title: str, prompt: str, cover_key: str) -> dict:
    if not report.get("report_path"):
        return _hold(scene, "没有 report_path，不发。", report=report)
    intake = report.get("intake_kcal")
    burn = report.get("total_burn_kcal")
    balance = report.get("balance_kcal")
    if intake is not None and burn is not None and balance is not None:
        summary = f"摄入 {intake} kcal，消耗 {burn} kcal，能量差额 {int(balance):+d} kcal"
    else:
        summary = "记录还不完整，点开把缺的补上。"
    cover = _library("covers", cover_key)
    data = {"cover": {"url": cover}} if cover else {}
    card = {
        "card_type": "image_text",
        "title": title,
        "summary": summary,
        "source": _source(),
        "tap": {"type": 1, "agent_chat": {"send_prompt": prompt}},
        "actions": [_button("a_open_report", "看完整日报" if scene == "s3" else "看完整周报", prompt)],
        "data": data,
        **_bind(args, scene),
    }
    result = {
        "send": True,
        "scene": scene,
        "show_widget": card,
        "report_path": report.get("report_path"),
        "report_mode": report.get("report_mode"),
    }
    if report.get("questions"):
        result["questions"] = report["questions"]
    return result


def _s3(args: dict, store: CrossStore) -> dict:
    import _report_from_store

    payload = dict(args)
    if not payload.get("date"):
        payload["date"] = datetime.now(CST).date().isoformat()
    report = _report_from_store.build_daily_from_store(payload, store)
    return _report_card("s3", args, report, "今天的健康日报", "看看今天的日报", "daily")


def _s4(args: dict, store: CrossStore) -> dict:
    import _report_from_store

    payload = dict(args)
    if not payload.get("date") and not payload.get("week_start"):
        payload["date"] = datetime.now(CST).date().isoformat()
    report = _report_from_store.build_weekly_from_store(payload, store)
    return _report_card("s4", args, report, "本周健康周报", "看看本周的周报", "weekly")


_SCENES = {"s1": _s1, "s2": _s2, "s3": _s3, "s4": _s4}


def now_card(args: dict, store: CrossStore) -> dict:
    scene = str(args.get("scene") or "").strip()
    handler = _SCENES.get(scene)
    if handler is None:
        raise ActionError("INVALID_ARGUMENT", "scene 只能是 s1 / s2 / s3 / s4。")
    return handler(args, store)


if __name__ == "__main__":
    raise SystemExit(run(now_card))
