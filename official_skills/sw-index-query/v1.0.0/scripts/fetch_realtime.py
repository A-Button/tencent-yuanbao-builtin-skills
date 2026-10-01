#!/usr/bin/env python3
"""Fetch realtime intraday timeline data for a Shenwan index."""

from __future__ import annotations

import json
import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from client import USE_WESTOCK, sw_get  # noqa: E402


def fetch_timelines(code: str) -> dict:
    return sw_get(
        "/institute-sw/api/index_publish/details/timelines/",
        params={"swindexcode": code},
        timeout=30,
    )


def process(raw: dict) -> tuple:
    data = raw["data"]
    if not data:
        raise ValueError("API returned empty data list")

    last = data[-1]
    meta = {
        "prev_close": float(last["l3"]),
        "open":       float(last["l4"]),
        "high":       float(last["l6"]),
        "low":        float(last["l7"]),
        "latest":     float(last["l8"]),
        "amount_cum": round(float(last["l5"]) / 100, 4) if last["l5"] is not None else None,
        "vol_cum":    round(float(last["l11"]) / 100, 4),
        "time":       last["trading_time"],
        "date":       last["trading_date"],
        "name":       last.get("l2", ""),
        "code":       last.get("l1", ""),
        "point_interval": "1min" if USE_WESTOCK else "10s",
        "raw_count": len(data),
    }

    sampled = data
    times      = [r["trading_time"] for r in sampled]
    prices     = [float(r["l8"]) for r in sampled]
    amounts_cum = [round(float(r["l5"]) / 100, 4) if r["l5"] is not None else None for r in sampled]
    vol_cum     = [round(float(r["l11"]) / 100, 4) for r in sampled]

    vol_diff = [0.0]
    for i in range(1, len(vol_cum)):
        v = (vol_cum[i] - vol_cum[i - 1]) * 100000000
        vol_diff.append(round(max(0, v), 4))

    chart = {
        "times": times,
        "prices": prices,
        "volumes": vol_diff,
        "amounts_cum": amounts_cum,
    }
    return chart, meta


def main():
    parser = argparse.ArgumentParser(description="Fetch Shenwan index realtime data")
    parser.add_argument("--code", required=True, help="6-digit Shenwan index code")
    parser.add_argument("--output", required=True, help="Output path for chart JSON")
    args = parser.parse_args()

    try:
        raw = fetch_timelines(args.code)
        chart, meta = process(raw)

        output_dir = os.path.dirname(os.path.abspath(args.output))
        os.makedirs(output_dir, exist_ok=True)

        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(chart, f, ensure_ascii=False)

        meta_path = os.path.join(output_dir, "meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)

        print(json.dumps({
            "status": "ok",
            "chart_file": args.output,
            "meta_file": meta_path,
            "sampled_count": len(chart["times"]),
            "point_interval": meta["point_interval"],
            "range": f"{chart['times'][0]}~{chart['times'][-1]}",
        }, ensure_ascii=False))

    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
