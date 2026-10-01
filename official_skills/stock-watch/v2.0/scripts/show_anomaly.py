#!/usr/bin/env python3
"""异动命中后的那张卡。归因质量如实写进 grade，扶摇未接入前写不出 verified。"""

from __future__ import annotations

from _card import anomaly_note, base_card, note, run, with_actions


def show_anomaly(args: dict) -> dict:
    card = base_card(args)
    card["scene"] = "anomaly"
    card["title"] = f"{card['name']}触发异动监控"
    note(card, args, anomaly_note(args))
    return with_actions(card, "查看详情", "detail")


if __name__ == "__main__":
    raise SystemExit(run(show_anomaly))
