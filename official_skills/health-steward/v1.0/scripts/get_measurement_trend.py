#!/usr/bin/env python3
"""围度趋势：某一项最近若干个记录点，外加与上一次的差值。

``weeks`` 是「返回最近多少个有效记录点」。按周记录时它就是周数；两次记录隔得
更久也只算一个点，这里不对日期做重采样。
"""

from __future__ import annotations

from _store import (
    DEFAULT_TREND_WEEKS,
    MAX_TREND_WEEKS,
    MEASUREMENT_PARTS,
    MIN_TREND_WEEKS,
    ActionError,
    Store,
    require_int,
    run,
)


def get_measurement_trend(args: dict, store: Store) -> dict:
    part = args.get("part")
    if part not in MEASUREMENT_PARTS:
        raise ActionError(
            "INVALID_ARGUMENT", f"part 只能取 {'/'.join(MEASUREMENT_PARTS)}：{part}"
        )
    weeks = DEFAULT_TREND_WEEKS
    if "weeks" in args:
        weeks = require_int(args, "weeks", MIN_TREND_WEEKS, MAX_TREND_WEEKS)
    # 点位与差值由快照统一算，这里只把查询条件递过去。
    return {"trend": {"part": part, "weeks": weeks}}


if __name__ == "__main__":
    raise SystemExit(run(get_measurement_trend))
