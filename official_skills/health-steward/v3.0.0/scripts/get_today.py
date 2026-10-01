#!/usr/bin/env python3
"""今日卡：当天的身体状态、训练安排与完成进度。

本体全在快照里（``today`` / ``card_*``），所以这里只负责把日期锚点定下来。
"""

from __future__ import annotations

from _store import Store, optional_date, run


def get_today(args: dict, store: Store) -> dict:
    return {"date": optional_date(args)}


if __name__ == "__main__":
    raise SystemExit(run(get_today))
