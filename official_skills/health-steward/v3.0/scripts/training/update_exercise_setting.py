#!/usr/bin/env python3
"""改某个动作的设置：改这次训练里某个动作的组数、次数或负重。

动作按 name / position（从 1 数）找，也认老调用的 session_id + exercise_id；
不给 session_id 就是今天那一场。只改传进来的字段。三项一个都没传时直接拒绝——
静默的空更新会让页面以为保存成功。
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
    MAX_REPS,
    MAX_SETS,
    ActionError,
    Store,
    pick_exercises,
    require_int,
    run,
    session_for,
    touch,
)

SETTING_FIELDS = ("sets", "reps", "load_text")


def update_exercise_setting(args: dict, store: Store) -> dict:
    session = session_for(store, args)
    [exercise] = pick_exercises(store, session, args, single=True)
    if not any(field in args for field in SETTING_FIELDS):
        raise ActionError(
            "EMPTY_UPDATE", f"至少要改一项：{'、'.join(SETTING_FIELDS)}。"
        )

    if "sets" in args:
        exercise["sets"] = require_int(args, "sets", 1, MAX_SETS)
    if "reps" in args:
        exercise["reps"] = require_int(args, "reps", 1, MAX_REPS)
    if "load_text" in args:
        # 传空字符串就是改成徒手，所以这里不做非空校验。
        exercise["load_text"] = str(args["load_text"] or "").strip()
    store.replace_exercise(touch(exercise))
    return {
        "date": session["date"],
        "session_id": session["id"],
        "exercise_id": exercise["id"],
        "name": exercise["name"],
    }


if __name__ == "__main__":
    raise SystemExit(run(update_exercise_setting))
