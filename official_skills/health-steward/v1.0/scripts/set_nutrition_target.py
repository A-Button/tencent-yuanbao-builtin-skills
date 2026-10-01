#!/usr/bin/env python3
"""改推荐区间：五项各自可选，只改传进来的那几项。"""

from __future__ import annotations

from _errors import ActionError
from _nutrition import NUTRIENT_KEYS
from _store import Store, run


def set_nutrition_target(args: dict, store: Store) -> dict:
    target = store.nutrition_target()
    changed = []
    for key in NUTRIENT_KEYS:
        if key not in args:
            continue
        target[key] = _valid_range(key, args[key])
        changed.append(key)
    if not changed:
        raise ActionError("EMPTY_TARGET", "至少要传一项区间。")
    store.set_nutrition_target(target)
    return {}


def _valid_range(key: str, raw) -> dict:
    """min / max 的存在与非负由 inputSchema 兜住，这里只查它表达不了的 min < max。"""
    if not isinstance(raw, dict):
        raise ActionError("INVALID_ARGUMENT", f"{key} 需要 {{min, max}} 两个数值。")
    low, high = raw.get("min"), raw.get("max")
    for value in (low, high):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ActionError("INVALID_ARGUMENT", f"{key} 的 min / max 必须是数值。")
    if low >= high:
        raise ActionError("INVALID_RANGE", f"{key} 的 min 必须小于 max。")
    return {"min": low, "max": high}


if __name__ == "__main__":
    raise SystemExit(run(set_nutrition_target))
