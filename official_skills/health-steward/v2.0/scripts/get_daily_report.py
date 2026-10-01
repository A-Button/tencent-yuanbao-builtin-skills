#!/usr/bin/env python3
"""健康日报：四段式 HTML 产物（能量收支 → 摄入 → 消耗 → 明天怎么做）。

**日报不出卡，出的是 HTML 产物。** 报告主体是逐餐明细和两张图表，A2UI 画不出来，
所以落一份 HTML 到沙箱工作区，由平台当产物下发。回执里的 ``report_path`` 就是那份文件。

visibility 仅 model，给 22:00 的日报用。

模型只传 ``date``。餐次、训练、消耗和档案都由脚本从库里读出来再渲染，
不要传 ``report_data``。不传 ``date`` 就报错，不会退回旧版报告。只传旧的五项
摄入（kcal / 碳水 / 蛋白 / 脂肪 / 纤维）同样报错：那条兼容通道已经撤掉，少传字段
不会再静默出一份旧模板。

数据不全也出同一份完整四段模板，缺的数是 0，不走 no_data 或 partial。
"""

from __future__ import annotations

import _report_from_store
from _errors import ActionError
from _store import CrossStore, run


def get_daily_report(args: dict, store: CrossStore) -> dict:
    if args.get("date"):
        # 路径必须回给模型。藏起来之后它会编一个文件名交给 present_files，
        # 宿主按那个名字去取，真实文件还在，会话里却没有日报。
        return _report_from_store.build_daily_from_store(args, store)
    raise ActionError(
        "INVALID_ARGUMENT",
        "report_daily 需要 date。脚本自己读这一天的饮食和训练记录并生成报告，"
        "不要传 report_data。不传 date 不会退回旧版报告。",
    )


if __name__ == "__main__":
    raise SystemExit(run(get_daily_report))
