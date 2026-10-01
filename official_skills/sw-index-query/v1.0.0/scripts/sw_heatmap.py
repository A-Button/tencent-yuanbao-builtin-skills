#!/usr/bin/env python3
"""Sector heatmap: multi-timeframe returns for L1 industries + rotation quadrant.

Usage:
  python sw_heatmap.py                          # all 31 industries
  python sw_heatmap.py --scope consumer         # consumer industries only
  python sw_heatmap.py --codes 801030,801080    # specific industries by code
"""

from __future__ import annotations

import json
import argparse
import math
import sys
import os
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from datasource import ytd_return, IncompleteDataError
from sw_common import (  # noqa: E402
    attach_render,

    emit_artifact, emit_progress, emit_error, emit_phase,
    fetch_realtime_one, fetch_kline_one, fetch_snapshot_batch,
    parallel_fetch, parallel_fetch_kline,
    call_analysis_llm,
    resolve_scope, INDUSTRY_GROUPS, SCOPE_LABELS,
)
TEMPLATE = "SW_HEAT"
UNIVERSE_A_SHARE_L1 = "a-share-l1"
HEATMAP_KLINE_DAYS = 260


def _build_title(scope: str, codes: str | None, universe: str) -> str:
    if codes:
        return "自选行业热力图"
    return f"{SCOPE_LABELS.get(scope, '全行业')}热力图"


def _build_identifier(scope: str, codes: str | None, universe: str) -> str:
    prefix = "sw-heatmap"
    if codes:
        code_list = sorted(c.strip() for c in codes.split(",") if c.strip())
        return prefix + "-" + "-".join(code_list[:3])
    if scope != "all":
        return f"{prefix}-{scope}"
    return prefix


def _resolve_industries(universe: str, scope: str = "all", codes: str | None = None) -> dict:
    return resolve_scope(scope, codes)


def _bar_float(bar: dict, *keys: str, default: float | None = None) -> float | None:
    for key in keys:
        value = bar.get(key)
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return default


def _bar_date(bar: dict) -> str:
    for key in ("bargaindate", "trade_date", "date", "trading_date"):
        raw = bar.get(key)
        if raw in (None, ""):
            continue
        text = str(raw)
        normalized = text.replace("-", "")[:8]
        if len(normalized) == 8 and normalized.isdigit():
            return f"{normalized[:4]}-{normalized[4:6]}-{normalized[6:8]}"
        return text[:10]
    return ""


def _extract_series(bars: list[dict]) -> tuple[list[str], list[float]]:
    dates = []
    closes = []
    for bar in bars or []:
        close = _bar_float(bar, "closeIndex", "closeindex", "close", "l8")
        if close is None:
            continue
        dates.append(_bar_date(bar))
        closes.append(close)
    return dates, closes


def _row_from_kline(name: str, code: str, bars: list[dict]) -> dict:
    dates, closes = _extract_series(bars)
    today_pct = 0
    if len(closes) >= 2 and closes[-2]:
        today_pct = round((closes[-1] - closes[-2]) / closes[-2] * 100, 2)
    last_bar = bars[-1] if bars else {}
    amount = _bar_float(last_bar, "bargainsum", "turnovervalue", "amount", default=0) or 0
    rets = compute_returns(closes, dates)
    if any(k not in rets for k in ("d5", "d20", "d60", "ytd")):
        raise IncompleteDataError(f"{code}: 缺少多周期/YTD所需基准")
    return {
        "code": code, "name": name, "today": today_pct,
        "d5": rets.get("d5", 0), "d20": rets.get("d20", 0),
        "d60": rets.get("d60", 0), "ytd": rets.get("ytd", 0),
        "amount": amount,
    }


def _compute_dispersion(values: list[float]) -> dict:
    """Return dispersion stats: std / cv / range / iqr."""
    vals = [v for v in values if v is not None]
    n = len(vals)
    if n < 2:
        return {"std": None, "cv": None, "range": None, "iqr": None, "min": None, "max": None, "median": None}
    mean = sum(vals) / n
    var = sum((v - mean) ** 2 for v in vals) / (n - 1)
    std = math.sqrt(var)
    cv = abs(std / mean) if abs(mean) > 1e-9 else None
    vmin = min(vals)
    vmax = max(vals)
    vrange = vmax - vmin
    sv = sorted(vals)
    median = sv[n // 2] if n % 2 == 1 else (sv[n // 2 - 1] + sv[n // 2]) / 2
    q1_idx = max(0, int(n * 0.25) - (0 if n * 0.25 != int(n * 0.25) else 1))
    q3_idx = min(n - 1, int(n * 0.75))
    q1 = sv[q1_idx]
    q3 = sv[q3_idx]
    return {
        "std": round(std, 2), "cv": round(cv, 3) if cv is not None else None,
        "range": round(vrange, 2), "iqr": round(q3 - q1, 2),
        "min": round(vmin, 2), "max": round(vmax, 2),
        "median": round(median, 2),
    }


def _compute_ytd_return(closes: list[float], dates: list[str]) -> float | None:
    if not closes or not dates or len(closes) != len(dates):
        return None
    latest_year = dates[-1][:4]
    base_idx = None
    for idx in range(len(dates) - 1, -1, -1):
        if dates[idx] and dates[idx][:4] < latest_year:
            base_idx = idx
            break
    if base_idx is None or not closes[base_idx]:
        return None
    return round((closes[-1] - closes[base_idx]) / closes[base_idx] * 100, 2)


def compute_returns(closes, dates=None):
    if not closes or len(closes) < 2:
        return {}
    dates = dates or []
    last = closes[-1]
    r = {}
    if len(closes) >= 6 and closes[-6]:
        r["d5"] = round((last - closes[-6]) / closes[-6] * 100, 2)
    if len(closes) >= 21 and closes[-21]:
        r["d20"] = round((last - closes[-21]) / closes[-21] * 100, 2)
    if len(closes) >= 61 and closes[-61]:
        r["d60"] = round((last - closes[-61]) / closes[-61] * 100, 2)
    ytd = _compute_ytd_return(closes, dates)
    if ytd is not None:
        r["ytd"] = ytd
    return r


def main():
    parser = argparse.ArgumentParser(description="Sector heatmap")
    parser.add_argument("--universe", default=UNIVERSE_A_SHARE_L1,
                        choices=[UNIVERSE_A_SHARE_L1],
                        help="指数范围：a-share-l1=申万一级行业")
    parser.add_argument("--scope", default="all",
                        choices=["all"] + list(INDUSTRY_GROUPS.keys()))
    parser.add_argument("--codes", default=None, help="Comma-separated industry codes")
    parser.add_argument("--show-dispersion", action="store_true",
                        help="输出行业间离散度（std/cv/range/iqr），衡量板块内部分化")
    args = parser.parse_args()

    target_industries = _resolve_industries(args.universe, args.scope, args.codes)
    title = _build_title(args.scope, args.codes, args.universe)
    identifier = _build_identifier(args.scope, args.codes, args.universe)
    total_steps = len(target_industries) * 2 + 3

    emit_artifact(TEMPLATE, identifier, title, {"loading": True})
    emit_phase(TEMPLATE, identifier, title, "meta", {
        "scope": args.scope, "codes": args.codes,
        "universe": args.universe,
        "universe_label": "申万一级行业",
        "title": title,
        "industries_count": len(target_industries),
    })

    try:
        codes_dict = {v: k for k, v in target_industries.items()}
        meta = {
            "scope": args.scope,
            "codes": args.codes,
            "universe": args.universe,
            "universe_label": "申万一级行业",
            "title": title,
            "industries_count": len(codes_dict),
        }

        emit_progress(TEMPLATE, identifier, title, 1, 2, "并行获取行情及K线数据")

        if args.universe == UNIVERSE_A_SHARE_L1:
            # Use /current/ batch snapshot (1 call for all L1 industries) to keep
            # today's A-share heatmap consistent with the market dashboard.
            wanted_codes = set(codes_dict.keys())
            all_l1 = fetch_snapshot_batch("一级行业")
            rt_results = [x for x in all_l1 if x["code"] in wanted_codes]
            rt_map = {item["code"]: item for item in rt_results}

            industries_today = []
            for name, code in target_industries.items():
                rt = rt_map.get(code, {})
                industries_today.append({
                    "code": code, "name": name,
                    "today": rt.get("change_pct", 0),
                    "d5": 0, "d20": 0, "d60": 0, "ytd": 0,
                    "amount": rt.get("amount", 0),
                })
            industries_today.sort(key=lambda x: x["today"], reverse=True)
            emit_phase(TEMPLATE, identifier, title, "data",
                       {"industries": industries_today}, meta=meta)

            kline_map = parallel_fetch_kline(codes_dict, period="DAY", days=HEATMAP_KLINE_DAYS)
            industries = []
            for name, code in target_industries.items():
                row = _row_from_kline(name, code, kline_map.get(code, []))
                rt = rt_map.get(code, {})
                row["today"] = rt.get("change_pct", row["today"])
                row["amount"] = rt.get("amount", row["amount"])
                industries.append(row)
        else:
            kline_map = parallel_fetch_kline(codes_dict, period="DAY", days=HEATMAP_KLINE_DAYS)
            industries = [
                _row_from_kline(name, code, kline_map.get(code, []))
                for name, code in target_industries.items()
                if kline_map.get(code)
            ]
        if not industries:
            raise RuntimeError(f"未获取到{meta['universe_label']}行情数据")

        meta["as_of"] = next(iter(kline_map.values()))[-1]["bargaindate"]
        industries.sort(key=lambda x: x["today"], reverse=True)

        quadrants = {"leading": [], "weakening": [], "lagging": [], "improving": []}
        for ind in industries:
            pt = {"name": ind["name"], "x": ind["d20"], "y": ind["d5"]}
            if ind["d20"] >= 0 and ind["d5"] >= 0:
                quadrants["leading"].append(pt)
            elif ind["d20"] >= 0 and ind["d5"] < 0:
                quadrants["weakening"].append(pt)
            elif ind["d20"] < 0 and ind["d5"] < 0:
                quadrants["lagging"].append(pt)
            else:
                quadrants["improving"].append(pt)

        data_payload = {"industries": industries, "quadrants": quadrants}
        emit_phase(TEMPLATE, identifier, title, "data", data_payload, meta=meta)

        top5 = [f"{x['name']} 今日{x['today']:+.2f}% 5日{x['d5']:+.2f}% 20日{x['d20']:+.2f}%" for x in industries[:5]]
        bot5 = [f"{x['name']} 今日{x['today']:+.2f}% 5日{x['d5']:+.2f}% 20日{x['d20']:+.2f}%" for x in industries[-5:]]
        universe_label = meta["universe_label"]
        summary_text = (
            f"{universe_label}数量: {len(industries)}\n"
            f"领涨行业(今日):\n" + "\n".join(top5) + "\n"
            f"领跌行业(今日):\n" + "\n".join(bot5) + "\n"
            f"领涨象限(中期趋势好+短期动量强): {len(quadrants['leading'])}个行业\n"
            f"回落象限(中期趋势好+短期动量弱): {len(quadrants['weakening'])}个行业\n"
            f"落后象限(中期趋势弱+短期动量弱): {len(quadrants['lagging'])}个行业\n"
            f"改善象限(中期趋势弱+短期动量强): {len(quadrants['improving'])}个行业"
        )

        dispersion = None
        if args.show_dispersion:
            dispersion = {
                "today": _compute_dispersion([x["today"] for x in industries]),
                "d5": _compute_dispersion([x["d5"] for x in industries]),
                "d20": _compute_dispersion([x["d20"] for x in industries]),
                "d60": _compute_dispersion([x["d60"] for x in industries]),
                "ytd": _compute_dispersion([x["ytd"] for x in industries]),
            }
            disp_lines = ["\n板块内部分化（std / range / iqr）："]
            for key, label in [("today", "今日"), ("d5", "5日"), ("d20", "20日"),
                               ("d60", "60日"), ("ytd", "YTD")]:
                d = dispersion[key]
                if d["std"] is not None:
                    disp_lines.append(
                        f"  {label}: std={d['std']:.2f}% range=[{d['min']:+.2f}, {d['max']:+.2f}] "
                        f"iqr={d['iqr']:.2f}"
                    )
            summary_text += "\n" + "\n".join(disp_lines)

        analysis = call_analysis_llm(summary_text, f"{universe_label}轮动热力图")

        time.sleep(0.15)
        emit_phase(TEMPLATE, identifier, title, "final", {}, meta=meta, analysis=analysis)

        summary = {
            "status": "ok",
            "mode": "heatmap",
            "date": meta["as_of"],
            "industries": industries,
            "universe": args.universe,
            "universe_label": meta["universe_label"],
            "industries_count": len(industries),
            "quadrant_counts": {k: len(v) for k, v in quadrants.items()},
            "top3": [{"name": x["name"], "today": x["today"], "d5": x["d5"], "d20": x["d20"]} for x in industries[:3]],
            "bottom3": [{"name": x["name"], "today": x["today"], "d5": x["d5"], "d20": x["d20"]} for x in industries[-3:]],
            "summary_text": summary_text,
        }
        if args.scope != "all":
            summary["scope"] = args.scope
        if args.codes:
            summary["codes"] = args.codes
        if dispersion is not None:
            summary["dispersion"] = dispersion
        print(json.dumps(attach_render(summary), ensure_ascii=False))

    except Exception as e:
        emit_error(TEMPLATE, identifier, title, str(e))
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
