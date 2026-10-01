#!/usr/bin/env python3
"""到价/止损提醒刚设好时的那张卡。"""

from __future__ import annotations

from _card import CardError, _decimals, _fixed, _number, alert_word, base_card
from _card import note, run, threshold_note, with_actions


def show_alert_set(args: dict) -> dict:
    card = base_card(args)
    direction = args.get("alert_direction")
    price = _number(args, "alert_price")
    if price is None:
        raise CardError("INVALID_ARGUMENT", "缺少参数：alert_price")

    card["scene"] = "alert_set"
    card["title"] = (
        f"已为{card['name']}设置 {_fixed(price, _decimals(price))} {alert_word(direction)}提醒"
    )
    # 提示行给的是标题没有的那半：现价离阈值还有多远。规则是否真的启用由 make-things
    # 那边决定，卡上只陈述条件本身，不写「监测已开启」——启用失败时那句话就是假的。
    note(card, args, threshold_note(card, direction, price))
    return with_actions(card, "查看详情", "detail")


if __name__ == "__main__":
    raise SystemExit(run(show_alert_set))
