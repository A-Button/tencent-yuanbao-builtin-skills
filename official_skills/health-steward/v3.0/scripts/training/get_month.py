#!/usr/bin/env python3
"""运动月历：某个月里哪些天有训练、各自完成到什么程度。

只换月历看的月份，今日卡的日期锚点仍是今天——翻月历不该把「今天」也翻走。
月份区间是左闭右开的 [当月 1 日, 次月 1 日)，12 月会正确进位到次年。
"""

from __future__ import annotations

import sys
from pathlib import Path
_scripts = Path(__file__).resolve().parents[1]
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))
import _boot
_boot.install()

from _store import Store, require_month, run, today_iso


def get_month(args: dict, store: Store) -> dict:
    return {"month": require_month(args), "date": today_iso()}


if __name__ == "__main__":
    raise SystemExit(run(get_month))
