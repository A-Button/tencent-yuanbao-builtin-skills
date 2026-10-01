#!/usr/bin/env python3
"""Fetch announcements, methodology, industry distribution, or risk/return for a Shenwan index."""

from __future__ import annotations

import json
import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from client import sw_get, sw_post  # noqa: E402


# ── announcement ──

def announcement_normal(code: str) -> dict:
    return sw_get(
        "/institute-sw/api/index_publish/details/index_announcements/",
        params={"swindexcode": code, "page": "1", "page_size": "10"},
    )


def announcement_fund(code: str) -> dict:
    return sw_post(
        "/insWechatSw/fundIndex/announcementPageList",
        body={"swIndexCode": code, "pageNo": 1, "pageSize": 10},
    )


def announcement_style(code: str) -> dict:
    return sw_post(
        "/insWechatSw/fundIndex/announcementPageList",
        body={"swIndexCode": code, "pageNo": 1, "pageSize": 10, "indexType": 1},
    )


def announcement_jc(code: str) -> dict:
    return sw_post(
        "/insWechatSw/fundIndex/announcementPageList",
        body={"swIndexCode": code, "pageNo": 1, "pageSize": 10, "indexType": 2},
    )


# ── methodology ──

def methodology_normal(code: str) -> dict:
    return sw_get(
        "/institute-sw/api/index_details/instruction_explain/",
        params={"swindexcode": code},
    )


def methodology_fund(code: str) -> dict:
    return sw_post(
        "/insWechatSw/fundIndex/methodology",
        body={"swIndexCode": code},
    )


def methodology_style(code: str) -> dict:
    return sw_post(
        "/insWechatSw/dflgOrJcIndex/methodology",
        body={"swIndexCode": code, "indexType": 1},
    )


def methodology_jc(code: str) -> dict:
    return sw_post(
        "/insWechatSw/dflgOrJcIndex/methodology",
        body={"swIndexCode": code, "indexType": 2},
    )


# ── industry distribution (getIndexIndustryDistribution) ──

def industry(code: str) -> dict:
    return sw_post(
        "/insWechatSw/swIndex/getIndexIndustryDistribution",
        body={"swIndexCode": code},
    )


# ── risk/return (getIndexRiskReturn) ──

def risk_return(code: str) -> dict:
    return sw_post(
        "/insWechatSw/swIndex/getIndexRiskReturn",
        body={"swIndexCode": code},
    )


DISPATCH = {
    ("announcement", "normal"): announcement_normal,
    ("announcement", "fund"):   announcement_fund,
    ("announcement", "style"):  announcement_style,
    ("announcement", "jc"):     announcement_jc,
    ("methodology", "normal"):  methodology_normal,
    ("methodology", "fund"):    methodology_fund,
    ("methodology", "style"):   methodology_style,
    ("methodology", "jc"):      methodology_jc,
}


def main():
    parser = argparse.ArgumentParser(description="Fetch Shenwan index announcements & info")
    parser.add_argument("--code", required=True, help="6-digit Shenwan index code")
    parser.add_argument("--action", required=True,
                        choices=["announcement", "methodology", "industry", "risk"],
                        help="Action type")
    parser.add_argument("--type", default="normal",
                        choices=["normal", "fund", "style", "jc"],
                        help="Index type (default: normal)")
    parser.add_argument("--output", required=True, help="Output path for JSON")
    args = parser.parse_args()

    try:
        if args.action == "industry":
            result = industry(args.code)
        elif args.action == "risk":
            result = risk_return(args.code)
        else:
            key = (args.action, args.type)
            fn = DISPATCH.get(key)
            if fn is None:
                raise ValueError(f"Unsupported action/type: {args.action}/{args.type}")
            result = fn(args.code)

        output_dir = os.path.dirname(os.path.abspath(args.output))
        os.makedirs(output_dir, exist_ok=True)

        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(json.dumps({
            "status": "ok",
            "output": args.output,
            "action": args.action,
            "type": args.type,
        }, ensure_ascii=False))

    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
