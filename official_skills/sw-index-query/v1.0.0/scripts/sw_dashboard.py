#!/usr/bin/env python3
"""Market overview dashboard: fetch all L1 industries + market indices.

Usage:
  python sw_dashboard.py                         # realtime, all industries
  python sw_dashboard.py --date 20260317         # historical snapshot for Mar 17
  python sw_dashboard.py --scope consumer        # realtime, consumer industries only
  python sw_dashboard.py --date 20260317 --scope finance
"""

from __future__ import annotations

import json
import argparse
import sys
import os
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from sw_common import (  # noqa: E402
    attach_render,

    emit_artifact, emit_progress, emit_error, emit_phase,
    fetch_snapshot_batch, fetch_kline_batch, find_trading_day,
    call_analysis_llm, resolve_scope,
    INDUSTRY_L1, MARKET_INDICES, INDUSTRY_GROUPS,
    SCOPE_LABELS,

)
TEMPLATE = "SW_DASH"

WEEKDAY_CN = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"}


def _build_title(scope: str, date_str: str | None, actual_date: str | None) -> str:
    scope_label = SCOPE_LABELS.get(scope, "A股市场")
    if actual_date:
        from datetime import datetime
        try:
            dt = datetime.strptime(actual_date, "%Y%m%d")
            wd = WEEKDAY_CN.get(dt.weekday(), "")
            return f"{scope_label}全景 · {dt.month}月{dt.day}日({wd})"
        except ValueError:
            return f"{scope_label}全景 · {actual_date}"
    return f"{scope_label}全景 · 实时"


def _build_identifier(scope: str, date_str: str | None) -> str:
    parts = ["sw-dashboard"]
    if scope != "all":
        parts.append(scope)
    if date_str:
        parts.append(date_str)
    else:
        parts.append("rt")
    return "-".join(parts)


def main_realtime(scope: str, scope_industries: dict,
                  identifier: str, title: str):
    """Realtime path using /current/ batch snapshot API.

    Replaces the previous 35 × /timelines/ calls with 2 × /current/ calls
    (1 for 市场表征, 1 for 一级行业). Benefits:
      - ~20× faster
      - Immune to the dawn-maintenance window where /timelines/ returns empty
        (was the root cause of the 2026-04-17 bug)
      - No fallback needed — /current/ is available around the clock
    """
    emit_progress(TEMPLATE, identifier, title, 1, 3, "正在获取市场指数")
    market_data = fetch_snapshot_batch("市场表征")

    emit_progress(TEMPLATE, identifier, title, 2, 3, "正在获取行业数据")
    all_l1 = fetch_snapshot_batch("一级行业")

    # Scope filter client-side (current/ API does not accept scope param)
    if scope != "all" and scope in INDUSTRY_GROUPS:
        allowed_codes = set(INDUSTRY_GROUPS[scope].values())
        industry_data = [x for x in all_l1 if x["code"] in allowed_codes]
    else:
        industry_data = all_l1

    # Keep only the 4 market indices the UI expects
    wanted_market = set(MARKET_INDICES.keys())
    market_data = [x for x in market_data if x["code"] in wanted_market]

    if not industry_data:
        raise ValueError("未获取到任何行业数据（API 返空）")

    return market_data, industry_data


def main_historical(scope_industries: dict, target_date: str,
                    identifier: str, title: str) -> tuple:
    """Historical path: use K-line to reconstruct a past day's snapshot."""
    all_codes = {}
    for code, name in MARKET_INDICES.items():
        all_codes[name] = code
    for name, code in scope_industries.items():
        all_codes[name] = code

    kline_map = fetch_kline_batch(
        all_codes, TEMPLATE, identifier, title,
        period="DAY", days=30, msg="正在获取历史K线"
    )
    market_data = []
    industry_data = []
    actual_date = None

    for name, code in all_codes.items():
        bars = kline_map.get(code)
        if not bars:
            continue

        idx, ad = find_trading_day(bars, target_date)
        if actual_date is None:
            actual_date = ad

        bar_today = bars[idx]
        close_today = float(bar_today.get("closeindex", 0))
        amount = round(float(bar_today.get("bargainsum", 0)), 2)

        if idx > 0:
            close_prev = float(bars[idx - 1].get("closeindex", 0))
        else:
            close_prev = float(bar_today.get("openindex", close_today))

        change = round(close_today - close_prev, 2)
        change_pct = round(change / close_prev * 100, 2) if close_prev else 0

        item = {
            "code": code, "name": name, "latest": close_today,
            "prev_close": close_prev, "change": change,
            "change_pct": change_pct, "amount": amount,
            "date": ad, "time": "",
        }

        if code in MARKET_INDICES:
            market_data.append(item)
        else:
            industry_data.append(item)

    if not industry_data:
        raise ValueError(f"未获取到 {target_date} 附近的行业数据")

    return market_data, industry_data, actual_date


def main():
    parser = argparse.ArgumentParser(description="Market overview dashboard")
    parser.add_argument("--date", default=None, help="Target date YYYYMMDD for historical snapshot")
    parser.add_argument("--scope", default="all",
                        choices=["all"] + list(INDUSTRY_GROUPS.keys()),
                        help="Industry group filter")
    args = parser.parse_args()

    scope_industries = resolve_scope(args.scope)
    identifier = _build_identifier(args.scope, args.date)
    title = _build_title(args.scope, args.date, None)

    emit_artifact(TEMPLATE, identifier, title, {"loading": True})
    time.sleep(0.15)
    emit_phase(TEMPLATE, identifier, title, "meta", {
        "scope": args.scope,
        "date": args.date,
    })

    try:
        if args.date:
            market_data, industry_data, actual_date = main_historical(
                scope_industries, args.date, identifier, title
            )
            title = _build_title(args.scope, args.date, actual_date)
        else:
            market_data, industry_data = main_realtime(
                args.scope, scope_industries, identifier, title
            )
            actual_date = None

        industry_data.sort(key=lambda x: x.get("change_pct", 0), reverse=True)

        up_count = sum(1 for x in industry_data if x.get("change_pct", 0) > 0)
        down_count = sum(1 for x in industry_data if x.get("change_pct", 0) < 0)
        flat_count = len(industry_data) - up_count - down_count
        total_amount = sum(x.get("amount", 0) for x in industry_data)

        date_label = actual_date or (industry_data[0].get("date", "") if industry_data else "")

        meta = {
            "scope": args.scope,
            "date": date_label,
            "industries_count": len(industry_data),
        }

        total_steps = len(scope_industries) + len(MARKET_INDICES) + 1
        emit_progress(TEMPLATE, identifier, title, total_steps - 1, total_steps, "正在生成分析")

        data_dict = {
            "market": market_data,
            "industries": industry_data,
            "stats": {
                "up": up_count, "down": down_count, "flat": flat_count,
                "total_amount": round(total_amount, 2),
            },
        }
        time.sleep(0.15)
        emit_phase(TEMPLATE, identifier, title, "data", data_dict, meta=meta)

        top5 = [f"{x['name']} {x['change_pct']:+.2f}%" for x in industry_data[:5]]
        bot5 = [f"{x['name']} {x['change_pct']:+.2f}%" for x in industry_data[-5:]]
        summary_text = (
            f"日期: {date_label}\n"
            f"上涨行业: {up_count}, 下跌行业: {down_count}, 平盘: {flat_count}\n"
            f"全市场成交额: {total_amount:.0f}亿元\n"
            f"领涨: {', '.join(top5)}\n"
            f"领跌: {', '.join(bot5)}"
        )
        analysis = call_analysis_llm(summary_text, "市场全景")

        time.sleep(0.15)
        emit_phase(TEMPLATE, identifier, title, "final", {}, meta=meta, analysis=analysis)

        summary = {
            "status": "ok",
            "mode": "dashboard",
            "date": date_label,
            "industries_count": len(industry_data),
            "up": up_count,
            "down": down_count,
            "total_amount": round(total_amount, 2),
            "top3": [{"name": x["name"], "change_pct": x["change_pct"]} for x in industry_data[:3]],
            "bottom3": [{"name": x["name"], "change_pct": x["change_pct"]} for x in industry_data[-3:]],
            "summary_text": summary_text,
        }
        if args.date:
            summary["requested_date"] = args.date
            summary["actual_date"] = actual_date or args.date
        if args.scope != "all":
            summary["scope"] = args.scope

        print(json.dumps(attach_render(summary), ensure_ascii=False))

    except Exception as e:
        emit_error(TEMPLATE, identifier, title, str(e))
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
