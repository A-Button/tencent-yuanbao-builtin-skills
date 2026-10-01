#!/usr/bin/env python3
"""写入身体档案（性别 / 身高 / 年龄 / 活动量）。

档案是慢变量，**没有体重**——体重走 ``log_measurement`` 的一天一条。
回执里带算出的 ``bmr``，但只有能读到最近体重时才有；否则 ``bmr: null`` 并在
``missing`` 里标明缺 weight，不用默认体重去凑。
"""

from __future__ import annotations

import sys
from pathlib import Path
_scripts = Path(__file__).resolve().parents[1]
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))
import _boot
_boot.install()

import _energy
from _store import (
    ACTIVITY_LEVELS,
    SEXES,
    ActionError,
    Store,
    new_record,
    optional_number,
    require_int,
    require_text,
    run,
    today_iso,
    touch,
)


def set_body_profile(args: dict, store: Store) -> dict:
    sex = require_text(args, "sex")
    if sex not in SEXES:
        raise ActionError("INVALID_ARGUMENT", f"sex 只能是 {'/'.join(SEXES)}：{sex}")
    height = optional_number(args, "height_cm", 100.0, 250.0)
    if height is None:
        raise ActionError("INVALID_ARGUMENT", "缺少参数：height_cm")
    age = require_int(args, "age", 10, 120)
    activity = require_text(args, "activity_level")
    if activity not in ACTIVITY_LEVELS:
        raise ActionError(
            "INVALID_ARGUMENT",
            f"activity_level 只能是 {'/'.join(ACTIVITY_LEVELS)}：{activity}",
        )

    fields = {
        "sex": sex,
        "height_cm": height,
        "age": age,
        "activity_level": activity,
    }
    existing = store.body_profile()
    if existing is None:
        record = new_record(**fields)
    else:
        record = touch({**existing, **fields})
    store.save_body_profile(record)
    return _profile_receipt(store, record)


def _profile_receipt(store: Store, profile: dict) -> dict:
    """档案字段原样返回，再附 bmr；绝不把 weight 写进档案回执。"""
    public = {
        "sex": profile["sex"],
        "height_cm": profile["height_cm"],
        "age": profile["age"],
        "activity_level": profile["activity_level"],
        "updated_at": profile.get("updated_at"),
    }
    weight = store.latest_weight_on_or_before(today_iso())
    if weight is None:
        return {"body_profile": public, "bmr": None, "missing": ["weight"]}
    bmr = _energy.basal_metabolic_rate(
        profile["sex"], weight, profile["height_cm"], profile["age"]
    )
    return {"body_profile": public, "bmr": round(bmr), "missing": []}


if __name__ == "__main__":
    raise SystemExit(run(set_body_profile))
