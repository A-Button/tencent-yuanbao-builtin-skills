#!/usr/bin/env python3
"""首次建提醒：把 Thing / Todo / Trigger 的参数算好，模型照抄去调 make-things。

不在这里创建。那些工具不在本进程里。``enabled`` 一律 false，启用是创建顺序的
最后一步，而且要等 write_todos 把真实 trigger_id 写进 rule_ids 之后。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from _errors import ActionError
from _store import CrossStore, run

CST = timezone(timedelta(hours=8))

_DEFAULT_TIMES = {
    "breakfast": "08:30",
    "lunch": "11:30",
    "dinner": "17:30",
    "train": "08:00",
    "daily": "22:00",
    "weekly": "22:00",
}
_SCENES = ("s1", "s2", "s3", "s4")


def _clock(value: object, name: str) -> str:
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        raise ActionError("INVALID_ARGUMENT", f"{name} 必须是 HH:MM。")
    hour, minute = value.split(":")
    if not (hour.isdigit() and minute.isdigit() and 0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
        raise ActionError("INVALID_ARGUMENT", f"{name} 不是合法时刻：{value}")
    return value


def _dtstart(hhmm: str) -> str:
    hour, minute = (int(part) for part in hhmm.split(":"))
    now = datetime.now(CST)
    moment = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if moment <= now:
        moment += timedelta(days=1)
    return moment.strftime("%Y%m%dT%H%M%S")


def _trigger(title: str, todo_id: str, rrule: str, hhmm: str, instruction: str) -> dict:
    return {
        "title": title,
        "todo_id": todo_id,
        "trigger_kind": "rrule",
        "rrule": rrule,
        "run_at": "",
        "enabled": False,
        "timezone": "Asia/Shanghai",
        "dtstart": _dtstart(hhmm),
        "instruction": instruction,
    }


def _todo(todo_id: str, title: str, hhmm: str, cycle: str) -> dict:
    return {
        "todo_id": todo_id,
        "title": title,
        "schedule_info": {"kind": "TIME", "time": {"cycle": cycle, "time_of_day": hhmm}},
        "rule_ids": [],
    }


def _instruction(scene: str, slot: str = "") -> str:
    extra = f"，slot={slot}" if slot else ""
    return (
        "加载 health-steward，重读当前 Thing，执行本次到点工作。"
        f"调用 now_card，scene={scene}{extra}，thing_id 和 todo_id 用本规则上的真实值。"
        "send 为 false 就不要调 show_widget；为 true 就把回执里的 show_widget 原样传给 show_widget。"
    )


def now_setup(args: dict, store: CrossStore) -> dict:
    del store
    requested = args.get("scenes") or list(_SCENES)
    if not isinstance(requested, list) or not requested:
        raise ActionError("INVALID_ARGUMENT", "scenes 必须是 s1 / s2 / s3 / s4 组成的非空数组。")
    scenes = []
    for scene in requested:
        if scene not in _SCENES:
            raise ActionError("INVALID_ARGUMENT", f"不认识的场景：{scene}")
        if scene not in scenes:
            scenes.append(scene)
    overrides = args.get("times") or {}
    if not isinstance(overrides, dict):
        raise ActionError("INVALID_ARGUMENT", "times 必须是对象。")
    times = dict(_DEFAULT_TIMES)
    for key, value in overrides.items():
        if key not in times:
            raise ActionError("INVALID_ARGUMENT", f"times 不认识 {key}")
        times[key] = _clock(value, key)

    triggers = []
    todos = []
    items = []
    if "s1" in scenes:
        todos.append(_todo("todo-s1-meals", "三餐拍照提醒", times["breakfast"], "DAILY"))
        for slot, title in (("breakfast", "早餐提醒"), ("lunch", "午餐提醒"), ("dinner", "晚餐提醒")):
            triggers.append(_trigger(
                title, "todo-s1-meals", "FREQ=DAILY;INTERVAL=1", times[slot], _instruction("s1", slot),
            ))
            items.append({"item_id": slot, "title": _SLOT_LABEL[slot], "desc": times[slot]})
    if "s2" in scenes:
        todos.append(_todo("todo-s2-train", "今日训练", times["train"], "DAILY"))
        triggers.append(_trigger(
            "今日训练", "todo-s2-train", "FREQ=DAILY;INTERVAL=1", times["train"], _instruction("s2"),
        ))
        items.append({"item_id": "train", "title": "今日训练", "desc": times["train"]})
    if "s3" in scenes:
        todos.append(_todo("todo-s3-daily", "健康日报", times["daily"], "DAILY"))
        triggers.append(_trigger(
            "健康日报", "todo-s3-daily", "FREQ=DAILY;INTERVAL=1", times["daily"], _instruction("s3"),
        ))
        items.append({"item_id": "daily", "title": "健康日报", "desc": f"每天 {times['daily']}"})
    if "s4" in scenes:
        todos.append(_todo("todo-s4-weekly", "健康周报", times["weekly"], "WEEKLY"))
        triggers.append(_trigger(
            "健康周报", "todo-s4-weekly", "FREQ=WEEKLY;BYDAY=SU", times["weekly"], _instruction("s4"),
        ))
        items.append({"item_id": "weekly", "title": "健康周报", "desc": f"周日 {times['weekly']}"})

    thing_id = str(args.get("thing_id") or "").strip()
    initial = {
        "card_type": "todo_remind",
        "title": "健康提醒已安排",
        "summary": "规则启用后才会到点运行",
        "source": {"label": "健康记录"},
        "data": {"items": items, "footnote": "还没启用的规则不要说已经开启。"},
    }
    if thing_id:
        initial["thingId"] = thing_id
        initial["todoId"] = todos[0]["todo_id"]
    goal_parts = []
    if "s1" in scenes:
        goal_parts.append(f"三餐 {times['breakfast']} / {times['lunch']} / {times['dinner']}")
    if "s2" in scenes:
        goal_parts.append(f"训练 {times['train']}")
    if "s3" in scenes:
        goal_parts.append(f"日报每天 {times['daily']}")
    if "s4" in scenes:
        goal_parts.append(f"周报周日 {times['weekly']}")
    return {
        "thing": {"mcp_app_ids": ["health-steward"], "goal": "；".join(goal_parts)},
        "todos": todos,
        "triggers": triggers,
        "initial_widget": initial,
        "order": [
            "get_thing，没有再 create_thing，mcp_app_ids 只用 health-steward",
            "trigger/create_trigger 逐条，enabled=false",
            "write_todos，rule_ids 填上一步返回的 trigger_id，schedule_info 用 todos 里那份",
            "重读确认后 trigger/update_trigger {\"enabled\": true}",
            "show_widget 用 initial_widget；回包有 now_id 才算发出",
        ],
    }


_SLOT_LABEL = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐"}


if __name__ == "__main__":
    raise SystemExit(run(now_setup))
