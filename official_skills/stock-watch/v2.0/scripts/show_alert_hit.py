#!/usr/bin/env python3
"""到价/止损条件命中、且复查后仍成立时的那张卡。"""

from __future__ import annotations

from _card import CardError, _decimals, _fixed, _number, alert_word, base_card, cross_word
from _card import note, run, threshold_note, with_actions


def show_alert_hit(args: dict) -> dict:
    card = base_card(args)
    direction = args.get("alert_direction")
    price = _number(args, "alert_price")
    if price is None:
        raise CardError("INVALID_ARGUMENT", "缺少参数：alert_price")

    threshold = _fixed(price, _decimals(price))
    card["scene"] = "alert_hit"
    card["title"] = f"{card['name']}{cross_word(direction)} {threshold}，触发{alert_word(direction)}提醒"
    note(card, args, threshold_note(card, direction, price))
    return with_actions(card, "改提醒", "edit_alert")


if __name__ == "__main__":
    raise SystemExit(run(show_alert_hit))
