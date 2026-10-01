#!/usr/bin/env python3
"""读身体档案。

没有体重字段。``bmr`` 只有在能读到最近体重时才有，否则 ``null`` +
``missing: ["weight"]``；档案本身不存在则 ``body_profile: null``、
``missing: ["body_profile"]``。
"""

from __future__ import annotations

import _energy
from _store import Store, run, today_iso


def get_body_profile(args: dict, store: Store) -> dict:
    profile = store.body_profile()
    if profile is None:
        return {"body_profile": None, "bmr": None, "missing": ["body_profile"]}
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
    raise SystemExit(run(get_body_profile))
