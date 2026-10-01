#!/usr/bin/env python3
"""算某一天的能量消耗（基础代谢 + 日常活动 + 训练）。

给日报用，页面不必调。本 tool **不算摄入**，所以 ``energy_balance`` 固定为
``null``——余额由 ``get_daily_report`` 拿摄入减去本 tool 的 ``total`` 来算，
不要在这里跨沙箱调 diet-assistant-in-health-steward。

缺档案或缺体重时，``_energy.expenditure`` 会把对应项标进 ``missing``，
``total`` 为 ``null`` 而不是 0。今天没练则 ``training`` 为 0（不是 missing）。
"""

from __future__ import annotations

import _energy
from _store import Store, body_profile_payload, optional_date, run, session_energy_inputs


def get_expenditure(args: dict, store: Store) -> dict:
    day = optional_date(args)
    result = _energy.expenditure(
        body_profile_payload(store),
        store.latest_weight_on_or_before(day),
        *session_energy_inputs(store, day),
    )
    # 余额由 get_daily_report 拿摄入减去本 tool 的 total；这里不读饮食、不算余额。
    result["energy_balance"] = None
    result["date"] = day
    return result


if __name__ == "__main__":
    raise SystemExit(run(get_expenditure))
