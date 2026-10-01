#!/usr/bin/env python3
"""记录当天的身体状态，并**由本脚本**算出训练建议。

一天一条：同一天重复提交覆盖原记录，不会堆出两行。``advice`` 永远由
``_store.advice_for`` 现算，入参里没有这个字段——结论不接受模型或页面传进来。
"""

from __future__ import annotations

import json

from _store import (
    Store,
    advice_for,
    new_record,
    normalize_soreness,
    optional_date,
    require_int,
    run,
    touch,
)


def log_readiness(args: dict, store: Store) -> dict:
    day = optional_date(args)
    fatigue = require_int(args, "fatigue", 1, 5)
    soreness = normalize_soreness(args.get("soreness"))
    advice = advice_for(fatigue, soreness)

    fields = {
        "date": day,
        "fatigue": fatigue,
        # 库里存 JSON 文本，出参给解析好的数组，转换只在存储边界上发生一次。
        "soreness": json.dumps(soreness, ensure_ascii=False),
        "advice": advice,
    }
    existing = store.readiness_on(day)
    if existing is None:
        record = new_record(**fields)
    else:
        record = touch({**existing, **fields})
    store.save_readiness(record)
    return {"date": day, "advice": advice}


if __name__ == "__main__":
    raise SystemExit(run(log_readiness))
