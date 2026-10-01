#!/usr/bin/env python3
"""把早/午/晚某一餐标成跳过，不进热量合计，卡片刷新成已跳过。

薄入口：business logic 全在 diet_api.dispatch，这里只负责把本 tool 的 operation
带进去。operation 由文件名定死，不从入参读。
"""

from diet_api import run_operation

if __name__ == "__main__":
    raise SystemExit(run_operation("skip_meal"))
