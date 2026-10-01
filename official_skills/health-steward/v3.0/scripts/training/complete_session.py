#!/usr/bin/env python3
"""完成今日整场训练，并把该场全部动作标记为已完成。

不给 session_id 就是今天那一场。操作是幂等的：重复点击不会切回未完成状态。
"""

from __future__ import annotations

import sys
from pathlib import Path
_scripts = Path(__file__).resolve().parents[1]
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))
import _boot
_boot.install()

from _store import Store, run, session_for, touch


def complete_session(args: dict, store: Store) -> dict:
    session = session_for(store, args)
    rows = store.exercises_of(session["id"])

    for exercise in rows:
        if not exercise["done"]:
            exercise["done"] = 1
            store.replace_exercise(touch(exercise))

    if session["status"] != "done":
        session["status"] = "done"
        store.replace_session(touch(session))

    completed = [row["name"] for row in rows]
    return {
        "date": session["date"],
        "session_id": session["id"],
        "completed": completed,
        "done_count": len(rows),
        "total_count": len(rows),
        "session_done": True,
    }


if __name__ == "__main__":
    raise SystemExit(run(complete_session))
