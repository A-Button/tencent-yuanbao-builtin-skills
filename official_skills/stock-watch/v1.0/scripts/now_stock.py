#!/usr/bin/env python3
"""股票卡（`stock`）的 show_widget 入参：到价命中、异动命中、当面问盘面、新建盯盘。

    python3 scripts/now_stock.py '{"thing_id":"117…","todo_id":"todo-…",
      "title":"已为宁德时代设置 8.00 止损提醒","items":[
      {"code":"hk03750","name":"宁德时代","time":"09/18 16:07:58",
       "price":9.006,"prev_close":8.86}]}'

三条平台硬约束，写死在这儿省得每次记：

- **配不了按钮。** make-things 三处写死「纯展示，无图表、无按钮，不配置 actions」，
  配了不报 40001、工具照回 now_id、按钮直接不画——比报错更难查。要按钮用 recommend_list。
- **整卡 tap 只在放一只时配。** 放两只以上指向谁都不对，所以多标的盘面卡是纯展示卡。
- **不要传 `data.hint`。** proto 没这个字段，传了就是 40001 unknown field "hint"。
  提示写进 title，或放到日结那张总结卡的 summary。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _card import _decimals, _fixed, parse_symbol, zxg_detail_url  # noqa: E402
from _now import (SOURCE_BOARD, TREND_DOWN, TREND_FLAT, TREND_UP,  # noqa: E402
                  direction, envelope, fail, h5, name_of, run)

MAX_ITEMS = 3
TREND = {"up": TREND_UP, "down": TREND_DOWN, "flat": TREND_FLAT}


def build(args: dict, items: list[dict]) -> dict:
    if len(items) > MAX_ITEMS:
        fail(f"一张 stock 卡最多放 {MAX_ITEMS} 只，其余的写进 20:00 那张日结总结。")

    rows = []
    for index, item in enumerate(items):
        symbol = parse_symbol(item)
        price, prev = item.get("price"), item.get("prev_close")
        if price is None:
            fail(f"第 {index + 1} 只缺 price。")
        if not item.get("time"):
            # 数据时刻走「数据时刻怎么取」那道梯子，禁止拿系统时间冒充行情时刻。
            fail(f"第 {index + 1} 只缺 time：行情时刻不能用当前系统时间。")
        decimals = _decimals(price)
        pct = item.get("change_pct")
        if pct is None and prev:
            pct = (price - prev) / prev * 100
        row = {"time": str(item["time"]), "name": name_of(item),
               "code": symbol["code_text"], "current_price": _fixed(price, decimals),
               "trend": TREND[direction(pct)]}
        if prev is not None:
            row["prev_close_price"] = _fixed(prev, decimals)
        if pct is not None:
            row["change"] = f"{pct:+.2f}%"
        rows.append(row)

    title = str(args.get("title") or "").strip()
    if not title:
        fail("title 必填：写这次通知本身，如「已为宁德时代设置 8.00 止损提醒」。")

    card = envelope("stock", title, "", SOURCE_BOARD, {"items": rows},
                    args.get("thing_id", ""))
    card.pop("summary")          # stock 卡不画 summary，留空字段只是噪音
    if args.get("todo_id"):
        card["todoId"] = str(args["todo_id"])
    if len(items) == 1:
        tap = h5(zxg_detail_url(parse_symbol(items[0])))
        if tap:
            card["tap"] = tap
    return card


if __name__ == "__main__":
    raise SystemExit(run(build))
