#!/usr/bin/env python3
"""勾掉动作，一次可以勾好几个。

按动作名（names）或第几个（positions，从 1 数，跟卡面顺序一致）找，也认老调用的
session_id + exercise_id。不给 session_id 就是今天那一场。「我练完了臀桥、硬拉」
一次调用就够，不用先查 id。

置为已完成而不是反复切换：同一个动作被点两次应该还是已完成，重试才安全。
全部勾完时整场自动标成已完成，月历上才看得出这天练完了；之后再加练会重新打开。
"""

from __future__ import annotations

from _store import Store, pick_exercises, run, session_for, touch


def complete_exercise(args: dict, store: Store) -> dict:
    session = session_for(store, args)
    picked = pick_exercises(store, session, args)
    for exercise in picked:
        exercise["done"] = 1
        store.replace_exercise(touch(exercise))

    rows = store.exercises_of(session["id"])
    done = sum(1 for row in rows if row["done"])
    result = {
        "date": session["date"],
        "session_id": session["id"],
        "completed": [row["name"] for row in picked],
        "done_count": done,
        "total_count": len(rows),
    }
    if len(picked) == 1:
        result["exercise_id"] = picked[0]["id"]
    if rows and done == len(rows) and session["status"] != "done":
        session["status"] = "done"
        store.replace_session(touch(session))
        result["session_done"] = True
    return result


if __name__ == "__main__":
    raise SystemExit(run(complete_exercise))
