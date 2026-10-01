#!/usr/bin/env python3
"""整套提醒时，算出每条线的本地时刻和到点要执行的 prompt。

不在这里创建 Thing。字段名、schedule、是否 bind_and_enable 以刚加载的
make-things 为准，本回执不能原样当成 create_thing / create_trigger 的参数。
"""

from __future__ import annotations

import sys
from pathlib import Path
_scripts = Path(__file__).resolve().parents[1]
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))
import _boot
_boot.install()

from _errors import ActionError
from _store import CrossStore, run

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


def _prompt(scene: str, slot: str = "") -> str:
    extra = f"，slot={slot}" if slot else ""
    lines = [
        "加载 health-steward，重读当前 Thing，执行本次到点工作。",
        f"调用 now_card，scene={scene}{extra}，thing_id 和 todo_id 用本规则上的真实值。",
        "send 为 false 就不要调 show_widget；为 true 就把回执里的 show_widget 原样传给 show_widget。",
    ]
    if scene in ("s3", "s4"):
        lines.append(
            "send 为 true 时，调一次 present_files，files 里只放回执 report_path 的原文，不要改文件名，不要再调报告工具。"
            "终稿必须再写一条 media_info，type 为 file，path 与 files 里那条原文完全相同。"
            "本轮只交一份 HTML：present_files 只调一次，media_info 只写一条，指向同一个路径，不是两份文件。"
            "不要再调报告工具，不要再交第二次。"
            "只此一条，而且只能是这份 HTML。封面地址禁止写进正文、media_info 或 present_files。"
            "不要贴卡上的封面，不要调 image_generation，主对话不要再写一段提醒。"
        )
    else:
        lines.append(
            "主对话只看回执里的 chat_note：不要再写一段提醒，不要贴卡上的图，不要写 media_info，不要调 image_generation。"
            "禁止把 image 地址抄进正文、media_info、present_files 或 photoUrl。这些图不是用户上传的。"
        )
    if scene == "s2":
        lines.append("只提醒并展示已经排好的当天训练，不要根据前一天饮食或训练记录生成新计划。")
    return "".join(lines)


def _line(scene: str, todo_id: str, title: str, repeat: str, times: list[dict], prompt: str) -> dict:
    return {
        "scene": scene,
        "preferred_todo_id": todo_id,
        "title": title,
        "repeat": repeat,
        "times": times,
        "prompt": prompt,
    }


def _after_enable(existing_thing_id: str) -> dict:
    """创建不再发 Now 卡。新建、补规则、改时刻都一样。"""
    del existing_thing_id
    return {
        "send": False,
        "reason": "创建 Things 不发 Now 卡。启用成功后直接回复用户，不要调 show_widget，也不要跑 now_card scene=created。",
    }


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

    lines = []
    if "s1" in scenes:
        slots = [
            {"slot": "breakfast", "label": "早餐提醒", "time": times["breakfast"]},
            {"slot": "lunch", "label": "午餐提醒", "time": times["lunch"]},
            {"slot": "dinner", "label": "晚餐提醒", "time": times["dinner"]},
        ]
        lines.append(_line(
            "s1", "todo-s1-meals", "三餐拍照提醒", "每天", slots,
            _prompt("s1", "<本餐 breakfast|lunch|dinner>"),
        ))
    if "s2" in scenes:
        lines.append(_line(
            "s2", "todo-s2-train", "今日训练", "每天",
            [{"label": "今日训练", "time": times["train"]}],
            _prompt("s2"),
        ))
    if "s3" in scenes:
        lines.append(_line(
            "s3", "todo-s3-daily", "健康日报", "每天",
            [{"label": "健康日报", "time": times["daily"]}],
            _prompt("s3"),
        ))
    if "s4" in scenes:
        lines.append(_line(
            "s4", "todo-s4-weekly", "健康周报", "每周日",
            [{"label": "健康周报", "time": times["weekly"]}],
            _prompt("s4"),
        ))

    goal_parts = []
    if "s1" in scenes:
        goal_parts.append(f"三餐 {times['breakfast']} / {times['lunch']} / {times['dinner']}")
    if "s2" in scenes:
        goal_parts.append(f"训练 {times['train']}")
    if "s3" in scenes:
        goal_parts.append(f"日报每天 {times['daily']}")
    if "s4" in scenes:
        goal_parts.append(f"周报周日 {times['weekly']}")
    existing = str(args.get("thing_id") or "").strip()
    body = {
        "app_id": "health-steward",
        "goal": "；".join(goal_parts),
        "lines": lines,
        "after_enable": _after_enable(existing),
        "note": (
            "这是健康提醒的意图，不是 create_thing / create_trigger 的参数。"
            "字段名、时间怎么填、要不要 bind_and_enable，以刚加载的 make-things 为准。"
            "创建不发 Now 卡：after_enable.send 为 false，不要把 show_widget 交给宿主，也不要跑 now_card scene=created。"
            "没有这份回执不要创建，也不要自己写触发 prompt。"
            "schema 接受预设任务标识时用 preferred_todo_id，否则用工具回包里的 id，并把 scene 留在 prompt 里。"
            "schema 有 mcp_app_ids 时只填 health-steward。"
        ),
    }
    if existing:
        body["existing_thing_id"] = existing
    return body


if __name__ == "__main__":
    raise SystemExit(run(now_setup))
