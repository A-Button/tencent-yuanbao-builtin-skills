#!/usr/bin/env python3
"""股票卡（`stock`）的 show_widget 入参：每晚 20:00 日结的第一张、到价命中、异动命中、第一次说盯盘/看看盘面/看看股票、已经在盯盘里再问盘面。

日结这张放今天值得盯的，最多 3 只，其余写进紧跟着的盘面总结。

本会话已经发过股票 Now 卡时，创建盯盘不要再调这个脚本。说了盯盘仍要先把 make-things 的 Thing 建上，没拿到真实 ID 不能写已创建。

    python3 scripts/now_stock.py '{"thing_id":"117…","todo_id":"todo-…","source_label":"宁德时代到价提醒",
      "title":"已为宁德时代设置 8.00 止损提醒","items":[
      {"code":"hk03750","name":"宁德时代","time":"09/18 16:07:58",
       "price":9.006,"prev_close":8.86}]}'

本脚本不写 `actions`、不写 `data.hint`。按钮和字段以 make-things 的 show-widget.md 为准。
整卡 tap 只在放一只时配，放两只以上指向谁都不对。
`source_label` 必填：本次 Todo 的真实 title，没有 Todo 就用 Thing 名称。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _card import _decimals, _fixed, parse_symbol, zxg_detail_url  # noqa: E402
from _now import (TREND_DOWN, TREND_FLAT, TREND_UP,  # noqa: E402
                  direction, envelope, fail, h5, name_of, run, source_label)

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
    # 2026-09-27 许继电气那张：标题写成「资讯 · 5条重点」，身子仍是行情块。
    # 股票卡只能画报价，画不出资讯列表。资讯必须改走 now_news.py。
    if any(word in title for word in ("资讯", "新闻", "公告", "研报")):
        fail("标题像资讯汇总。股票卡只能画行情，资讯改跑 now_news.py（recommend_list），不要用本脚本。")

    card = envelope("stock", title, "", source_label(args), {"items": rows},
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
