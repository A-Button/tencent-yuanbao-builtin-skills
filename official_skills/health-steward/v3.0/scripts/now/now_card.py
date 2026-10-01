#!/usr/bin/env python3
"""到点该不该发、以及完整的 show_widget 入参。

模型不要自己拼 Now 卡。调这个工具，``send`` 为 false 就停；为 true 就把
``show_widget`` 原样交给宿主的 show_widget，不要改字段、不要再搜图。

训练动作、三餐占位图和日报周报封面来自 ``assets/now_images.json`` 里的长期 HTTPS 地址。
三餐占位图只放在 Now 卡的 ``image`` 上。回执另给一句 ``chat_note``，模型只看那句回主对话，
不要把卡上的图写进正文、不要包 ``media_info``、不要调 ``image_generation``。
"""

from __future__ import annotations

import sys
from pathlib import Path
_scripts = Path(__file__).resolve().parents[1]
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))
import _boot
_boot.install()

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from _errors import ActionError
from _store import CrossStore, run

CST = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[2]
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


def _chat_tap(prompt: str | None = None) -> dict:
    """回到原会话；只有明确提交业务动作时才自动发送用户语言。"""
    agent_chat = {"send_prompt": prompt} if prompt else {}
    return {"type": 1, "agent_chat": agent_chat}


def _button(action_id: str, label: str, prompt: str | None = None) -> dict:
    return {
        "action_id": action_id,
        "label": label,
        "tap": _chat_tap(prompt),
    }


def _hold(scene: str, reason: str, **extra) -> dict:
    return {"send": False, "scene": scene, "reason": reason, **extra}


_CHAT_NOTE = (
    "只调 show_widget 发出这张卡。主对话不要再写一段提醒，"
    "不要贴卡上的图，不要写 media_info，不要调 image_generation。"
    "禁止把 show_widget 参数、回执或历史里的 image 地址抄进正文、media_info、present_files 或 photoUrl。"
    "这些图不是用户拍的，不是这一餐，也不是这次训练。"
    "photoUrl 只接受用户本轮刚上传的图。"
)

_REPORT_CHAT_NOTE = (
    "先把 show_widget 原样交给 show_widget，这张 Now 卡必须发出。"
    "再调一次 present_files，files 里只放回执 report_path 的原文，不要改文件名，"
    "不要再调 report_daily 或 report_weekly。"
    "终稿必须再写一条 media_info，type 为 file，path 与 files 里那条原文完全相同。"
    "本轮只交一份 HTML：present_files 只调一次，media_info 只写一条，指向同一个路径，不是两份文件。"
    "不要再调报告工具，不要再交第二次。"
    "只此一条，而且只能是这份 HTML。封面地址禁止写进正文、media_info 或 present_files。"
    "不要贴卡上的封面，不要调 image_generation，主对话不要再写一段提醒。"
)


def _diet_day(day: str) -> tuple[dict[str, list], set[str]]:
    import store as diet

    grouped: dict[str, list] = {slot: [] for slot in _SLOTS}
    for meal in diet.load_meals_between(day, day):
        kind = meal.get("meal_type")
        if kind in grouped:
            grouped[kind].append(meal)
    return grouped, set(diet.skipped_slots(day))


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

    title = _SLOT_TITLE[slot]
    # 推荐列表没有勾选框。todo_choice 一点按钮就会把餐次名再接到句子后面。
    # 占位图留在卡上。chat_note 告诉模型：这张图不是用户拍的，不要带进主对话。
    item = {"item_id": slot, "title": title, "desc": "待记录 · 拍一张我帮你算"}
    image = _library("meals", slot)
    if image:
        item["image"] = image
    card = {
        "card_type": "recommend_list",
        "title": f"今天的{title}",
        "summary": f"{day.month}月{day.day}日 · 还没记",
        "source": _source(),
        "actions": [
            _button("a_go_record", "去记录", f"这是我今天的{title}"),
            _button("a_skip", "不吃了", f"今天不吃{title}"),
        ],
        "data": {"items": [item]},
        **_bind(args, "s1"),
    }
    return {"send": True, "scene": "s1", "slot": slot, "chat_note": _CHAT_NOTE, "show_widget": card}


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
    if not pending:
        return _hold("s2", "今天的动作都完成了，不发。")
    # 推荐列表没有勾选框。todo_choice 一点按钮就会把勾中标题再接到句子后面。
    # 未完成的动作全部列上。三个是以前自己截的，协议没有「最多三行」，也没有卡内滑动。
    items = []
    for row in pending:
        item = {"item_id": str(row["id"]), "title": row["name"], "desc": row["meta"]}
        image = _library("exercises", row.get("exercise_key")) or _library("exercises", "default")
        if image:
            item["image"] = image
        items.append(item)
    done_count = len(rows) - len(pending)
    summary = f"{day[5:]} · {session.get('plan_name') or '今日训练'}"
    if done_count:
        summary += f" · 已完成 {done_count} 个"
    record_prompt = "我今天练了这些：" + "、".join(row["name"] for row in pending)
    card = {
        "card_type": "recommend_list",
        "title": "今天的训练",
        "summary": summary,
        "source": _source(),
        "actions": [
            _button("a_go_record", "去记录", record_prompt),
            _button("a_adjust", "改计划", "我想调整今天的训练计划"),
        ],
        "data": {"items": items},
        **_bind(args, "s2"),
    }
    return {"send": True, "scene": "s2", "chat_note": _CHAT_NOTE, "show_widget": card}


def _report_card(scene: str, args: dict, report: dict, title: str, cover_key: str) -> dict:
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
    if scene == "s3":
        label, prompt = "看完整日报", "我要看今天的健康日报"
    else:
        label, prompt = "看完整周报", "我要看本周的健康周报"
    card = {
        "card_type": "image_text",
        "title": title,
        "summary": summary,
        "source": _source(),
        "tap": _chat_tap(prompt),
        "actions": [_button("a_open_report", label, prompt)],
        "data": data,
        **_bind(args, scene),
    }
    result = {
        "send": True,
        "scene": scene,
        "chat_note": _REPORT_CHAT_NOTE,
        "show_widget": card,
        "report_mode": report.get("report_mode"),
        "report_path": report.get("report_path"),
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
    return _report_card("s3", args, report, "今天的健康日报", "daily")


def _created(args: dict, store: CrossStore) -> dict:
    """创建不再发 Now 卡。留下这个 scene，是为了拦住还在调用的旧路径。"""
    del args, store
    return _hold("created", "创建 Things 不发 Now 卡。")


def _s4(args: dict, store: CrossStore) -> dict:
    import _report_from_store

    payload = dict(args)
    if not payload.get("date") and not payload.get("week_start"):
        payload["date"] = datetime.now(CST).date().isoformat()
    report = _report_from_store.build_weekly_from_store(payload, store)
    return _report_card("s4", args, report, "本周健康周报", "weekly")


_SCENES = {"s1": _s1, "s2": _s2, "s3": _s3, "s4": _s4, "created": _created}


def now_card(args: dict, store: CrossStore) -> dict:
    scene = str(args.get("scene") or "").strip()
    handler = _SCENES.get(scene)
    if handler is None:
        raise ActionError("INVALID_ARGUMENT", "scene 只能是 s1 / s2 / s3 / s4 / created。")
    return handler(args, store)


if __name__ == "__main__":
    raise SystemExit(run(now_card))
