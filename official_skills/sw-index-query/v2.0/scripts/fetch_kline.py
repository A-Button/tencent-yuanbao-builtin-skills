#!/usr/bin/env python3
"""Fetch K-line (OHLCV) data for a Shenwan index with MA calculations."""

from __future__ import annotations

import json
import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from client import sw_get, sw_post  # noqa: E402
from sw_common import is_fund, is_style_broad, is_jc, get_index_display_name  # noqa: E402


def fetch_normal(code: str, period: str, days: int = 250) -> list:
    resp = sw_get(
        "/institute-sw/api/index_publish/trend/",
        params={"swindexcode": code, "period": period, "limit": days},
    )
    return resp["data"]


def fetch_fund(code: str, period: str) -> list:
    resp = sw_post(
        "/insWechatSw/fundIndex/getFundKChartData",
        body={"swIndexCode": code, "type": period},
    )
    return resp["data"]


def fetch_style_broad_or_jc(code: str, period: str, is_broad: bool) -> list:
    resp = sw_post(
        "/insWechatSw/dflgOrJcIndex/getDLFGKChartData",
        body={"swIndexCode": code, "indexType": 1 if is_broad else 2, "type": period},
    )
    return resp["data"]


def ma(series: list, n: int) -> list:
    result = [None] * min(n - 1, len(series))
    for i in range(n - 1, len(series)):
        result.append(round(sum(series[i - n + 1 : i + 1]) / n, 4))
    return result


def main():
    parser = argparse.ArgumentParser(description="Fetch Shenwan index K-line data")
    parser.add_argument("--code", required=True, help="6-digit Shenwan index code")
    parser.add_argument("--period", default="DAY", choices=["DAY", "WEEK", "MONTH"],
                        help="K-line period (default: DAY)")
    parser.add_argument("--days", type=int, default=90, help="Number of recent bars (default: 90)")
    parser.add_argument("--output", required=True, help="Output path for K-line JSON")
    args = parser.parse_args()

    try:
        code = args.code

        if is_style_broad(code) or is_jc(code):
            data = fetch_style_broad_or_jc(code, args.period, is_style_broad(code))
        elif is_fund(code):
            data = fetch_fund(code, args.period)
        else:
            data = fetch_normal(code, args.period, args.days)

        if not data:
            raise ValueError("API returned empty data")

        recent = data[-args.days:]
        closes = [float(r["closeindex"]) for r in recent]

        out = {
            "labels":  [r["bargaindate"][:10] for r in recent],
            "open":    [float(r["openindex"]) for r in recent],
            "high":    [float(r["maxindex"]) for r in recent],
            "low":     [float(r["minindex"]) for r in recent],
            "close":   closes,
            "ma5":     ma(closes, 5),
            "ma10":    ma(closes, 10),
            "ma20":    ma(closes, 20),
            "volumes": [round(float(r.get("bargainamount", 0)), 4) for r in recent],
            "amounts": [round(float(r.get("bargainsum", 0)), 4) for r in recent],
        }

        output_dir = os.path.dirname(os.path.abspath(args.output))
        os.makedirs(output_dir, exist_ok=True)

        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)

        api_name = recent[-1].get("swindexname") or recent[-1].get("l2") or code
        name = get_index_display_name(code, api_name)
        meta = {"name": name, "code": code, "period": args.period}
        meta_path = os.path.join(output_dir, "meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)

        print(json.dumps({
            "status": "ok",
            "output": args.output,
            "meta_file": meta_path,
            "bars": len(recent),
            "range": f"{out['labels'][0]}~{out['labels'][-1]}",
        }, ensure_ascii=False))

    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
