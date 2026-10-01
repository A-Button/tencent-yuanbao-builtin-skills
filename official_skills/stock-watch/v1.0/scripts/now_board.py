#!/usr/bin/env python3
"""盘面总结卡（`recommend_list`）的 show_widget 入参。

**只在每晚 20:00 的收盘日结里发**，覆盖盯盘清单的全部标的。当面问盘面、到价命中、
异动命中都不发它，那些场景只发一张 `stock`（见 now_stock.py）。

    python3 scripts/now_board.py '{"thing_id":"117…","as_of":"09/22 收盘","items":[
      {"code":"hk00700","name":"腾讯控股","price":430,"change_pct":2.63,
       "currency":"HKD","note":"主力净流入 13 亿，MA20 仍压制"}]}'

`note` 是那一行的解读，挑一条最能解释今天这根 K 的（均线 / 量比 / 资金 / 触媒），
超 20 字会被截断；判断依据写进主对话正文，别指望卡面能展开。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _card import parse_symbol, zxg_detail_url  # noqa: E402
from _now import (clip, ACTION_BOARD, LIMIT_DESC, SOURCE_BOARD, SUMMARY_BOARD,  # noqa: E402
                  MAX_ROWS, action, envelope, h5, quote_line, run)


def build(args: dict, items: list[dict]) -> dict:
    # 超过 5 只按今日涨跌幅绝对值取前几名——动得最多的才是这张日结要说的事。
    # 按钮 prompt 里的「等 N 只」用的仍是全量，用户知道自己盯了几只。
    shown = sorted(items, key=lambda i: abs(i.get("change_pct") or 0),
                   reverse=True)[:MAX_ROWS] if len(items) > MAX_ROWS else items
    rows = []
    for item in shown:
        symbol = parse_symbol(item)
        row = {"item_id": symbol["code"], "title": quote_line(item)}
        if item.get("note"):
            row["desc"] = clip(str(item["note"]), LIMIT_DESC)
        # 逐只跳自选股个股页；拼不出该市场的链接就整条不配 tap，不猜一个把人点到别的票上。
        tap = h5(zxg_detail_url(symbol))
        if tap:
            row["tap"] = tap
        rows.append(row)

    as_of = str(args.get("as_of") or "").strip()
    if not as_of:
        # 数据时刻来自行情，禁止墙上时钟；缺了宁可不发也不编一个。
        from _now import fail
        fail("as_of 必填：标题上的数据时刻要来自行情，不能用当前系统时间。")

    card = envelope("recommend_list", f"今日盯盘总结 · {as_of}", SUMMARY_BOARD,
                    SOURCE_BOARD, {"items": rows}, args.get("thing_id", ""))
    card["actions"] = [action(ACTION_BOARD, items)]
    return card


if __name__ == "__main__":
    raise SystemExit(run(build))
