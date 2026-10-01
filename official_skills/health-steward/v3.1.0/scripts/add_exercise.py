#!/usr/bin/env python3
"""往某一天**已有的**那场训练里追加动作。

plan_session 在当天已有排期时也走同一条追加路径（见 ``_workout.append_exercises``），
模型加练直接调 workout_plan 即可；本工具保留给老调用和只想追加、不想误建一场的场合：
当天还没排过就报 SESSION_NOT_FOUND，不会替你新建。

**已完成的动作不受影响。** 这是追加路径存在的全部理由，改那里之前先想清楚这一条。
"""

from __future__ import annotations

from _store import ActionError, Store, append_exercises, optional_date, run


def add_exercise(args: dict, store: Store) -> dict:
    day = optional_date(args)
    session = store.session_on(day)
    if session is None:
        raise ActionError(
            "SESSION_NOT_FOUND",
            f"{day} 还没有安排训练，先用 workout_plan 排一场。",
        )

    raw = args.get("exercises")
    if not isinstance(raw, list) or not raw:
        raise ActionError("INVALID_ARGUMENT", "exercises 至少要有一个动作。")

    added = append_exercises(store, session, raw)
    return {
        "date": day,
        "session_id": session["id"],
        "added": [{"exercise_id": row["id"], "name": row["name"]} for row in added],
        "total_count": len(store.exercises_of(session["id"])),
    }


if __name__ == "__main__":
    raise SystemExit(run(add_exercise))
