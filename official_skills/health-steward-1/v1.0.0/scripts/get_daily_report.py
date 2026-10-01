#!/usr/bin/env python3
"""健康日报：四段式 HTML 产物（能量收支 → 摄入 → 消耗 → 明天怎么做）。

**日报不出卡，出的是 HTML 产物。** 报告主体是逐餐明细和两张图表，A2UI 画不出来，
所以落一份 HTML 到沙箱工作区，由平台当产物下发。回执里的 ``report_path`` 就是那份文件。

visibility 仅 model，给 22:00 的日报用。

传 ``date`` 时脚本自己读饮食和训练记录来组装；传 ``report_data`` 时仍按调用方
给的结构渲染（过渡期两种都收，同时给时以 ``report_data`` 为准）。两个都不传
才报错，不会退回旧版报告。只传旧的五项摄入（kcal / 碳水 / 蛋白 / 脂肪 / 纤维）
同样报错：那条兼容通道已经撤掉，少传字段不会再静默出一份旧模板。

数据不全不算失败，由 ``_health_report_v1`` 自己分档：没有任何记录回 ``no_data`` 加一句
邀请，记了但不完整回 ``partial`` 降级页加追问。**这两档都不该靠补造数据凑成完整版。**
"""

from __future__ import annotations

import _health_report_v1
import _report_from_store
from _errors import ActionError
from _store import CrossStore, run


def get_daily_report(args: dict, store: CrossStore) -> dict:
    report_data = args.get("report_data")
    if isinstance(report_data, dict):
        return _health_report_v1.build_daily(report_data)
    if args.get("date"):
        return _report_from_store.build_daily_from_store(args, store)
    raise ActionError(
        "INVALID_ARGUMENT",
        "report_daily 需要 date 或 report_data。传 date 由脚本自己读饮食和训练记录；"
        "传 report_data 则按 references/health-report-v1.0/api_reference.md 渲染。"
        "两个都不传不会退回旧版报告。",
    )


if __name__ == "__main__":
    raise SystemExit(run(get_daily_report))
