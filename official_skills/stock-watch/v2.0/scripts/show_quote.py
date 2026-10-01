#!/usr/bin/env python3
"""没有盯盘事件时的普通行情快照卡。"""

from __future__ import annotations

from _card import base_card, note, run, with_actions


def show_quote(args: dict) -> dict:
    card = base_card(args)
    card["scene"] = "quote"
    card["title"] = f"{card['name']}当前行情"
    # 没有盯盘事件就没有可算的条件，提示行只在 Agent 主动传 note 时才出。
    # 不要为了填满版面塞一句「暂无异常」——那是一句没人核过的结论。
    note(card, args, "")
    return with_actions(card, "查看详情", "detail")


if __name__ == "__main__":
    raise SystemExit(run(show_quote))
