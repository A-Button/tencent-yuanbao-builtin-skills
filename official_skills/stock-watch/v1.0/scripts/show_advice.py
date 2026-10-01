#!/usr/bin/env python3
"""咨询建议卡：几只票各给一个操作标签和一行理由。

跟其余三张不同，这张是**多标的**的，所以没有单标的那套现价大数字和到价条件。
"""

from __future__ import annotations

from _card import COLOUR_HINT, GREEN_MEANS_UP, _text, advice_row, require_items, run

MAX_ROWS = 6


def show_advice(args: dict) -> dict:
    rows = [advice_row(item, index) for index, item in enumerate(require_items(args, MAX_ROWS))]

    # 只要列表里有美股且真染了色，就把口径标出来。多标的卡最容易读错颜色：
    # 同一屏里 A 股的红和美股的红含义相反。
    mixed = {row["_market"] for row in rows}
    needs_hint = bool(mixed & GREEN_MEANS_UP) and any(
        row["is_red"] or row["is_green"] for row in rows
    )
    footer = (args.get("footer") or "").strip()

    return {
        "scene": "advice",
        "kicker": _text(args, "basis"),
        "title": (args.get("title") or "").strip() or "个股操作建议",
        "rows": [{key: value for key, value in row.items() if not key.startswith("_")}
                 for row in rows],
        "has_footer": bool(footer),
        "footer_text": footer,
        "has_colour_hint": needs_hint,
        "colour_hint_text": COLOUR_HINT if needs_hint else "",
    }


if __name__ == "__main__":
    raise SystemExit(run(show_advice))
