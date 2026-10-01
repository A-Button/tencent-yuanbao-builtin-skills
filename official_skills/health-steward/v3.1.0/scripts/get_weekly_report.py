#!/usr/bin/env python3
"""健康周报：四段式 HTML 产物，含三张横向滑动的周历。

同日报：不出卡，落一份 HTML 到沙箱工作区，回执里的 ``report_path`` 是那份文件。
visibility 仅 model。

传 ``date``（这一周里的任意一天）或 ``week_start``（必须是周一）时，脚本自己读
记录组装七天。传 ``report_data`` 时仍按调用方给的结构渲染。两个都不传才报错。

旧的「不传 report_data 就出体重均值 + 近 6 周折线」兼容通道已撤掉，理由同
``get_daily_report``：它会在调用方漏传字段时静默产出一份旧模板报告，退出码还是 0。

有效日不足 3 天时 ``_health_report_v1`` 回 ``sparse``、不出 HTML，这是刻意的——
七日趋势和执行表在两三天数据上画出来只会是噪声。
"""

from __future__ import annotations

import _health_report_v1
import _report_from_store
from _errors import ActionError
from _store import CrossStore, run


def get_weekly_report(args: dict, store: CrossStore) -> dict:
    report_data = args.get("report_data")
    if isinstance(report_data, dict):
        return _health_report_v1.build_weekly(report_data)
    if args.get("date") or args.get("week_start"):
        return _report_from_store.build_weekly_from_store(args, store)
    raise ActionError(
        "INVALID_ARGUMENT",
        "report_weekly 需要 date、week_start 或 report_data。"
        "传 date 由脚本自己读这一周的记录；传 report_data 则按 api_reference 渲染。"
        "都不传不会退回旧版报告。",
    )


if __name__ == "__main__":
    raise SystemExit(run(get_weekly_report))
