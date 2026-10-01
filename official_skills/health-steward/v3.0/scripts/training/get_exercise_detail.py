#!/usr/bin/env python3
"""动作详情：随包静态资料（主要肌群 / 呼吸方法 / 难度 / 常见错误 / 演示地址）
加上它在今天这场训练里的当前设置。

动作可以用 exercise_key、position（今天第几个，从 1 数）或 name 指：卡片「查要领」
递进来的是「看「第1个动作」的动作要领」，直接按 position 查，不用先 get_today。
name 先在今天的清单里找，找不到再按动作资料里的名字找。

资料来自 ``assets/exercise_library.json``，不是用户数据；设置来自
``session_exercises``。没排今天的训练时 ``setting`` 为 null，资料照常返回。
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
    Store,
    exercise_library,
    match_by_name,
    ordinal_of,
    require_library_entry,
    run,
    today_iso,
)


def _resolve_key(args: dict, rows: list[dict]) -> tuple[str, int | None]:
    key = args.get("exercise_key")
    if isinstance(key, str) and key.strip():
        return key.strip(), None

    name = args.get("name")
    position = args.get("position")
    if position is None and name is not None:
        position = ordinal_of(name)
    if position is not None:
        if isinstance(position, bool) or not isinstance(position, int):
            raise ActionError("INVALID_ARGUMENT", "position 必须是整数，从 1 数。")
        if not 1 <= position <= len(rows):
            raise ActionError(
                "NOT_FOUND", f"今天的清单里没有第 {position} 个动作（共 {len(rows)} 个）。"
            )
        return rows[position - 1]["exercise_key"], position

    if isinstance(name, str) and name.strip():
        row, _ = match_by_name(rows, name)
        if row is not None:
            return row["exercise_key"], rows.index(row) + 1
        entry, problem = match_by_name(exercise_library(), name)
        if entry is None:
            raise ActionError("NOT_FOUND", f"{problem}，今天的清单和动作资料里都没找到。")
        return entry["key"], None

    raise ActionError("INVALID_ARGUMENT", "要指明是哪个动作：position（第几个）、name 或 exercise_key。")


def get_exercise_detail(args: dict, store: Store) -> dict:
    day = today_iso()
    session = store.session_on(day)
    rows = store.exercises_of(session["id"]) if session is not None else []
    key, position = _resolve_key(args, rows)
    entry = require_library_entry(key)
    setting = None
    if session is not None:
        setting = next(
            (
                {
                    "session_id": session["id"],
                    "exercise_id": row["id"],
                    "sets": row["sets"],
                    "reps": row["reps"],
                    "load_text": row["load_text"],
                    "done": bool(row["done"]),
                }
                for row in rows
                if row["exercise_key"] == entry["key"]
            ),
            None,
        )
    result = {"date": day, "exercise_detail": {**entry, "setting": setting}}
    if position is not None:
        result["position"] = position
    return result


if __name__ == "__main__":
    raise SystemExit(run(get_exercise_detail))
