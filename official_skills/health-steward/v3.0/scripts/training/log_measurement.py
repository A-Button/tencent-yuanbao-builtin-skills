#!/usr/bin/env python3
"""记一次围度或体重。

一天一条，同一天再记就合并：只覆盖这次传进来的项，没传的保持原值——量了腹围
不该把上次记的臀围抹成空；记了体重也不该抹掉围度。

体重进 measurements，不进身体档案：档案是慢变量，体重是一天一条。

至少要有一项。这条 ``inputSchema`` 表达不了（CLI 的校验器不实现 anyOf），
所以由本脚本兜住。
"""

from __future__ import annotations

import sys
from pathlib import Path
_scripts = Path(__file__).resolve().parents[1]
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))
import _boot
_boot.install()

from _store import ActionError, Store, new_record, optional_date, optional_number, run, touch

# (part, column, low, high)。顺序即「记完之后趋势图停在哪一项」的优先级。
VALUE_FIELDS = (
    ("waist", "waist_cm", 20.0, 250.0),
    ("hip", "hip_cm", 20.0, 250.0),
    ("thigh", "thigh_cm", 20.0, 250.0),
    ("weight", "weight_kg", 20.0, 300.0),
)
BLANK_VALUES = {column: None for _, column, _, _ in VALUE_FIELDS}


def log_measurement(args: dict, store: Store) -> dict:
    day = optional_date(args)
    provided = {
        column: optional_number(args, column, low, high)
        for _, column, low, high in VALUE_FIELDS
        if column in args
    }
    values = {column: value for column, value in provided.items() if value is not None}
    if not values:
        raise ActionError(
            "NO_MEASUREMENT_VALUE",
            "至少要填一项：waist_cm（腹围）/ hip_cm（臀围）/ thigh_cm（大腿围）"
            " / weight_kg（体重）。",
        )

    existing = store.measurement_on(day)
    if existing is None:
        record = new_record(**{**BLANK_VALUES, "date": day, **values})
    else:
        record = touch({**existing, **values})
    store.save_measurement(record)

    focus = next(part for part, column, _, _ in VALUE_FIELDS if column in values)
    # 记完就把趋势图切到刚记的那一项，页面不用再要一次数据。
    return {"date": day, "measurement": record, "trend": {"part": focus}}


if __name__ == "__main__":
    raise SystemExit(run(log_measurement))
