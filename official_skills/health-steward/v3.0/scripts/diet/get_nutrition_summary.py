#!/usr/bin/env python3
"""把今日实际摄入比到推荐区间上，给出三态判定、整体评价和一句建议。

五项都传了就按入参打分（旧调用）。一项都不传就按当天饮食记录合计，
膳食纤维饮食侧没有，标成未知，不当成 0。
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
from _nutrition import NUTRIENT_KEYS, evaluate_nutrition, require_number, resolve_date
from _store import Store, run


def _from_meals(day: str) -> dict | None:
    import store as diet

    meals = diet.load_meals_between(day, day)
    if not meals:
        return None
    intake = {key: 0.0 for key in ("kcal", "carb_g", "protein_g", "fat_g")}
    for meal in meals:
        totals = meal.get("totals") if isinstance(meal.get("totals"), dict) else {}
        for key in intake:
            intake[key] += float(totals.get(key) or 0)
    intake["fiber_g"] = None
    return intake


def get_nutrition_summary(args: dict, store: Store) -> dict:
    day = resolve_date(args.get("date"))
    provided = [key for key in NUTRIENT_KEYS if key in args]
    if provided and len(provided) != len(NUTRIENT_KEYS):
        missing = [key for key in NUTRIENT_KEYS if key not in args]
        raise ActionError("INVALID_ARGUMENT", f"摄入要嘛五项都传，要嘛一项都不传改由记录计算。缺：{', '.join(missing)}")
    if provided:
        intake = {key: require_number(args, key) for key in NUTRIENT_KEYS}
    else:
        intake = _from_meals(day)
        if intake is None:
            return {"date": day, "nutrition": None, "missing": ["meals"]}
    return {"nutrition": evaluate_nutrition(intake, store.nutrition_target(), day)}


if __name__ == "__main__":
    raise SystemExit(run(get_nutrition_summary))
