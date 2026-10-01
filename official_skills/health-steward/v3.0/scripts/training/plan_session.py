#!/usr/bin/env python3
"""给某一天排训练。没有它就不会有「今日训练」。

一天一场。当天还没有排期就新建一场；已经有了，这次给的动作接在末尾——跟
add_exercise 同一条追加路径，已经勾掉的动作一个字段都不动。以前第二次调用直接报
SESSION_EXISTS，模型想加练时撞上这个错，还会退回去重排一整场，所以改成追加。
追加时 plan_name / cycle_* 不改原来那场，只在回执里说明。改组数次数走
update_exercise_setting。

``exercise_key`` 必须在 ``assets/exercise_library.json`` 里出现过，这样「动作详情」
永远有资料可显示。要加新动作，先往那份随包资料里加一条。
"""

from __future__ import annotations

import sys
from pathlib import Path
_scripts = Path(__file__).resolve().parents[1]
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))
import _boot
_boot.install()

from _store import (
    ActionError,
    MAX_PER_SESSION,
    Store,
    append_exercises,
    check_exercise_keys,
    exercise_row,
    new_record,
    optional_date,
    require_int,
    require_text,
    run,
)


def plan_session(args: dict, store: Store) -> dict:
    day = optional_date(args)
    raw = args.get("exercises")
    if not isinstance(raw, list) or not raw:
        raise ActionError("INVALID_ARGUMENT", "exercises 至少要有一个动作。")

    existing = store.session_on(day)
    if existing is not None:
        added = append_exercises(store, existing, raw)
        return {
            "date": day,
            "session_id": existing["id"],
            "appended": True,
            "added": [row["name"] for row in added],
            "total_count": len(store.exercises_of(existing["id"])),
            "note": f"{day} 已经排过「{existing['plan_name']}」，这次的动作接在末尾，已完成的不动。",
        }

    plan_name = require_text(args, "plan_name")
    cycle_index = require_int(args, "cycle_index", 1, 99)
    cycle_size = require_int(args, "cycle_size", 1, 99)
    if cycle_index > cycle_size:
        raise ActionError(
            "INVALID_ARGUMENT", f"cycle_index 不能大于 cycle_size：{cycle_index} > {cycle_size}"
        )
    if len(raw) > MAX_PER_SESSION:
        raise ActionError("TOO_MANY_EXERCISES", f"一场最多 {MAX_PER_SESSION} 个动作。")
    check_exercise_keys(raw)

    session = new_record(
        date=day,
        plan_name=plan_name,
        cycle_index=cycle_index,
        cycle_size=cycle_size,
        status="pending",
    )
    rows = [exercise_row(item, session["id"], position) for position, item in enumerate(raw)]
    store.insert_session(session)
    for row in rows:
        store.insert_exercise(row)
    return {"date": day, "session_id": session["id"]}


if __name__ == "__main__":
    raise SystemExit(run(plan_session))
