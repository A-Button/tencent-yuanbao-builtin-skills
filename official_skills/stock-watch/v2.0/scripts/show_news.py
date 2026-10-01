#!/usr/bin/env python3
"""资讯汇总卡：一次几只票的公告 / 研报 / 事件 / 新闻合成一张，每条同时带类型和情绪两个标签。

归属标的逐条给，不是整张卡一个——一次汇总里既有某只票的公告，也有没有归属的
行业新闻。
"""

from __future__ import annotations

from _card import COLOUR_HINT, GREEN_MEANS_UP, _text, news_row, require_items, run

MAX_ROWS = 6


def show_news(args: dict) -> dict:
    rows = [news_row(item, index) for index, item in enumerate(require_items(args, MAX_ROWS))]

    # 列表里混进美股，就得说清楚这张卡上的红绿不是同一套口径。
    markets = {row.pop("_market") for row in rows}
    coloured = any(row["stance_red"] or row["stance_green"] for row in rows)
    needs_hint = bool(markets & GREEN_MEANS_UP) and coloured

    return {
        "scene": "news",
        "kicker": _text(args, "source_line"),
        "title": (args.get("title") or "").strip() or f"今日 {len(rows)} 条重点资讯",
        "has_summary": bool((args.get("summary") or "").strip()),
        "summary_text": (args.get("summary") or "").strip(),
        "rows": rows,
        "has_colour_hint": needs_hint,
        "colour_hint_text": COLOUR_HINT if needs_hint else "",
        "primary_label": "帮我解读",
        "primary_prompt": "解读这批资讯对我的持仓可能有什么影响",
        "secondary_label": "换一批",
        "secondary_prompt": "换一批资讯看看",
    }


if __name__ == "__main__":
    raise SystemExit(run(show_news))
