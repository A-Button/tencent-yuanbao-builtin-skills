#!/usr/bin/env python3
"""Fetch component stocks/funds for a Shenwan index."""

from __future__ import annotations

import json
import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
from client import sw_post  # noqa: E402


def fetch_normal(code: str) -> dict:
    page_size = 1000
    return sw_post(
        "/insWechatSw/swIndex/componentStockPageList",
        body={"indexCode": code, "pageNo": 1, "pageSize": page_size},
        timeout=10,
    )["data"]


def fetch_fund(code: str) -> dict:
    return sw_post(
        "/insWechatSw/fundIndex/componentFundPageList",
        body={"swIndexCode": code, "pageNo": 1, "pageSize": 1000},
        timeout=10,
    )["data"]


def fetch_style_or_jc(code: str, idx_type: str) -> dict:
    return sw_post(
        "/insWechatSw/dflgOrJcIndex/componentDLFGPageList",
        body={
            "swIndexCode": code,
            "pageNo": 1,
            "pageSize": 1000,
            "indexType": 1 if idx_type == "style" else 2,
        },
        timeout=10,
    )["data"]


def extract_components(data) -> list:
    records = data if isinstance(data, list) else data.get("records", data.get("list", []))
    result = []
    for r in records:
        result.append({
            "stockCode":     r.get("stockCode", r.get("securityCode", r.get("fundCode", ""))),
            "stockName":     r.get("stockName", r.get("securityName", r.get("fundName", ""))),
            "newWeight":     r.get("newWeight", ""),
            "beginningdate": r.get("beginningDate", r.get("beginningdate", r.get("beginDate", ""))),
        })
    return result


def main():
    parser = argparse.ArgumentParser(description="Fetch Shenwan index components")
    parser.add_argument("--code", required=True, help="6-digit Shenwan index code")
    parser.add_argument("--type", required=True, choices=["normal", "fund", "style", "jc"],
                        help="Index type: normal, fund, style, jc")
    parser.add_argument("--output", required=True, help="Output path for components JSON")
    args = parser.parse_args()

    try:
        idx_type = args.type

        if idx_type in ("style", "jc"):
            raw = fetch_style_or_jc(args.code, idx_type)
        elif idx_type == "normal":
            raw = fetch_normal(args.code)
        elif idx_type == "fund":
            raw = fetch_fund(args.code)
        else:
            raise ValueError(f"Unknown type: {idx_type}")

        components = extract_components(raw)

        out = {
            "components": components,
            "total": len(components),
        }

        output_dir = os.path.dirname(os.path.abspath(args.output))
        os.makedirs(output_dir, exist_ok=True)

        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)

        print(json.dumps({
            "status": "ok",
            "output": args.output,
            "total": len(components),
        }, ensure_ascii=False))

    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
