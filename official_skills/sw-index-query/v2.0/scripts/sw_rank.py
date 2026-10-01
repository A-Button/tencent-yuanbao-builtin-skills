#!/usr/bin/env python3
"""General-purpose index ranking: rank indices within a category by multiple metrics.

Supports all index types: L1 industries, fund indices, style indices, and custom lists.
Computes YTD return, Calmar ratio, max drawdown, Sharpe, volatility, and multi-period returns.

Usage:
  python sw_rank.py --category l1                    # All 31 L1 industries
  python sw_rank.py --category fund_theme            # Fund theme indices
  python sw_rank.py --category style                 # Style indices
  python sw_rank.py --codes 807141,807142,807143     # Custom list
  python sw_rank.py --category l1 --sort calmar      # Sort by Calmar ratio
  python sw_rank.py --category fund --days 250       # 1-year window
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from sw_common import (  # noqa: E402
    attach_render,

    emit_artifact, emit_progress, emit_error, emit_phase,
    fetch_risk_return_batch, fetch_kline_for_group,
    call_analysis_llm, resolve_category,
    CATEGORY_PRESETS, TRADING_DAYS_PER_YEAR,

)
TEMPLATE = "SW_RANK"


def _compute_derived_metrics(risk: dict, kline: list | None, days: int) -> dict:
    """Compute max_drawdown, Calmar, Sharpe, and YTD volatility from K-line data."""
    result = {
        "max_drawdown": None,
        "calmar": None,
        "sharpe": None,
        "ytd_vol": None,
    }

    if not kline or len(kline) < 2:
        return result

    closes = [float(r.get("closeindex", 0)) for r in kline]

    peak = closes[0]
    max_dd = 0.0
    for c in closes:
        if c > peak:
            peak = c
        dd = (c - peak) / peak if peak else 0
        if dd < max_dd:
            max_dd = dd
    result["max_drawdown"] = round(max_dd * 100, 2)

    daily_rets = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            daily_rets.append(closes[i] / closes[i - 1] - 1)

    if len(daily_rets) >= 10:
        mean_r = sum(daily_rets) / len(daily_rets)
        var_r = sum((r - mean_r) ** 2 for r in daily_rets) / (len(daily_rets) - 1)
        daily_vol = math.sqrt(var_r)
        ann_vol = round(daily_vol * math.sqrt(TRADING_DAYS_PER_YEAR) * 100, 2)
        result["ytd_vol"] = ann_vol

    ytd_return = risk.get("ytd_return")
    if result["max_drawdown"] and result["max_drawdown"] < -0.01:
        if ytd_return is not None:
            result["calmar"] = round(ytd_return / abs(result["max_drawdown"]), 2)

    y1_return = risk.get("y1_return")
    y1_vol = risk.get("y1_vol")
    if y1_return is not None and y1_vol and y1_vol > 0:
        result["sharpe"] = round((y1_return - 2.0) / y1_vol, 2)

    return result


SORT_KEYS = {
    "ytd": "ytd_return",
    "calmar": "calmar",
    "sharpe": "sharpe",
    "max_drawdown": "max_drawdown",
    "y1": "y1_return",
    "y3": "y3_return",
    "y5": "y5_return",
    "m1": "m1_return",
    "m3": "m3_return",
    "vol": "ytd_vol",
}


def _sort_val(item: dict, key: str) -> float:
    v = item.get(key)
    if v is None:
        return -99999
    if key == "max_drawdown":
        return v
    return v


def main():
    parser = argparse.ArgumentParser(description="Index category ranking")
    parser.add_argument("--category", default="l1",
                        choices=list(CATEGORY_PRESETS.keys()),
                        help="Preset category to rank")
    parser.add_argument("--codes", default=None,
                        help="Comma-separated index codes (overrides --category)")
    parser.add_argument("--days", type=int, default=250,
                        help="K-line lookback window for drawdown/volatility (default: 250)")
    parser.add_argument("--sort", default="ytd",
                        choices=list(SORT_KEYS.keys()),
                        help="Metric to sort by (default: ytd)")
    args = parser.parse_args()

    label, codes_dict = resolve_category(args.category, args.codes)
    sort_field = SORT_KEYS[args.sort]

    title = f"{label}指数排名"
    identifier = f"sw-rank-{args.category}" if not args.codes else "sw-rank-custom"

    emit_artifact(TEMPLATE, identifier, title, {"loading": True})
    emit_phase(TEMPLATE, identifier, title, "meta", {
        "category": args.category,
        "label": label,
        "sort": args.sort,
        "count": len(codes_dict),
    })

    try:
        # Phase 1: risk/return API data
        risk_data = fetch_risk_return_batch(
            codes_dict, TEMPLATE, identifier, title, "正在获取收益风险数据"
        )
        risk_by_code = {r["code"]: r for r in risk_data}

        # Phase 2: K-line data for drawdown / volatility
        kline_data = fetch_kline_for_group(codes_dict, "DAY", args.days)

        # Merge and compute derived metrics
        items = []
        for code, name in codes_dict.items():
            risk = risk_by_code.get(code, {})
            kline = kline_data.get(code)
            derived = _compute_derived_metrics(risk, kline, args.days)

            items.append({
                "code": code,
                "name": name,
                "ytd_return": risk.get("ytd_return"),
                "m1_return": risk.get("m1_return"),
                "m3_return": risk.get("m3_return"),
                "y1_return": risk.get("y1_return"),
                "y3_return": risk.get("y3_return"),
                "y5_return": risk.get("y5_return"),
                "y1_vol": risk.get("y1_vol"),
                "ytd_vol": derived["ytd_vol"],
                "max_drawdown": derived["max_drawdown"],
                "calmar": derived["calmar"],
                "sharpe": derived["sharpe"],
            })

        reverse = sort_field != "max_drawdown"
        items.sort(key=lambda x: _sort_val(x, sort_field), reverse=reverse)

        for rank, item in enumerate(items, 1):
            item["rank"] = rank

        data_payload = {
            "items": items,
            "sortField": sort_field,
            "sortLabel": args.sort,
            "category": args.category,
            "label": label,
        }
        meta_info = {"category": args.category, "label": label, "sort": args.sort, "count": len(items)}
        # Phase 3: LLM analysis
        emit_progress(TEMPLATE, identifier, title, len(codes_dict), len(codes_dict) + 1, "正在生成分析")
        emit_phase(TEMPLATE, identifier, title, "data", data_payload, meta=meta_info)

        valid = [x for x in items if x.get("ytd_return") is not None]
        top3 = valid[:3]
        bot3 = valid[-3:] if len(valid) >= 3 else valid

        lines = [
            f"{label}指数排名（按{args.sort}排序，共{len(valid)}个指数）",
        ]
        for i, t in enumerate(top3):
            parts = [f"YTD:{t['ytd_return']:+.2f}%" if t.get("ytd_return") is not None else ""]
            if t.get("calmar") is not None:
                parts.append(f"Calmar:{t['calmar']:.2f}")
            if t.get("max_drawdown") is not None:
                parts.append(f"最大回撤:{t['max_drawdown']:.2f}%")
            if t.get("sharpe") is not None:
                parts.append(f"Sharpe:{t['sharpe']:.2f}")
            lines.append(f"  Top{i+1}. {t['name']}({t['code']}): {', '.join(p for p in parts if p)}")
        for i, b in enumerate(bot3):
            parts = [f"YTD:{b['ytd_return']:+.2f}%" if b.get("ytd_return") is not None else ""]
            if b.get("calmar") is not None:
                parts.append(f"Calmar:{b['calmar']:.2f}")
            lines.append(f"  Bottom{i+1}. {b['name']}({b['code']}): {', '.join(p for p in parts if p)}")

        summary_text = "\n".join(lines)
        analysis = call_analysis_llm(summary_text, f"{label}排名")

        emit_phase(TEMPLATE, identifier, title, "final", data_payload, meta=meta_info, analysis=analysis)

        print(json.dumps(attach_render({
            "status": "ok",
            "category": args.category,
            "label": label,
            "sort": args.sort,
            "count": len(items),
            "top3": [{"name": x["name"], "code": x["code"],
                       "ytd_return": x["ytd_return"], "calmar": x["calmar"]} for x in top3],
            "summary_text": summary_text,
        }), ensure_ascii=False))

    except Exception as e:
        emit_error(TEMPLATE, identifier, title, str(e))
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
