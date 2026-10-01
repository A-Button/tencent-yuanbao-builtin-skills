#!/usr/bin/env python3
"""Risk-Return Matrix: scatter plot of L1 industries by annualized return vs volatility.

Usage:
  python sw_risk_matrix.py                      # all 31 industries
  python sw_risk_matrix.py --scope tmt          # TMT industries only
  python sw_risk_matrix.py --codes 801030,801080  # specific industries
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
    fetch_risk_return_one, parallel_fetch,
    call_analysis_llm,
    resolve_scope, INDUSTRY_GROUPS, SCOPE_LABELS,

)
TEMPLATE = "SW_RISK"


def _build_title(scope: str, codes: str | None) -> str:
    if codes:
        return "自选行业收益风险矩阵"
    return f"{SCOPE_LABELS.get(scope, '全行业')}收益风险矩阵"


def _build_identifier(scope: str, codes: str | None) -> str:
    if codes:
        code_list = sorted(c.strip() for c in codes.split(",") if c.strip())
        return "sw-risk-" + "-".join(code_list[:3])
    if scope != "all":
        return f"sw-risk-{scope}"
    return "sw-risk-matrix"


def main():
    parser = argparse.ArgumentParser(description="Risk-return matrix")
    parser.add_argument("--scope", default="all",
                        choices=["all"] + list(INDUSTRY_GROUPS.keys()))
    parser.add_argument("--codes", default=None, help="Comma-separated industry codes")
    args = parser.parse_args()

    target_industries = resolve_scope(args.scope, args.codes)
    title = _build_title(args.scope, args.codes)
    identifier = _build_identifier(args.scope, args.codes)

    emit_artifact(TEMPLATE, identifier, title, {"loading": True})
    emit_phase(TEMPLATE, identifier, title, "meta", {
        "scope": args.scope, "codes": args.codes,
    })

    try:
        codes_for_fetch = {v: k for k, v in target_industries.items()}

        emit_progress(TEMPLATE, identifier, title, 1, 3, "并行获取收益风险数据")
        risk_data = parallel_fetch(fetch_risk_return_one, codes_for_fetch)

        if not risk_data:
            emit_error(TEMPLATE, identifier, title, "未获取到任何行业收益风险数据")
            print(json.dumps({"status": "error", "message": "no data"}, ensure_ascii=False), file=sys.stderr)
            sys.exit(1)

        industries = []
        for item in risk_data:
            y1_ret = item.get("y1_return")
            y1_vol = item.get("y1_vol")
            if y1_ret is not None and y1_vol is not None and y1_vol != 0:
                ratio = round(y1_ret / y1_vol, 4)
            else:
                ratio = None
            industries.append({
                "code": item["code"], "name": item["name"],
                "y1_return": y1_ret, "y1_vol": y1_vol, "ratio": ratio,
                "m1_return": item.get("m1_return"),
                "m3_return": item.get("m3_return"),
                "ytd_return": item.get("ytd_return"),
            })

        industries.sort(key=lambda x: x["ratio"] if x["ratio"] is not None else -9999, reverse=True)

        meta = {"scope": args.scope, "codes": args.codes, "industries_count": len(industries)}

        emit_progress(TEMPLATE, identifier, title, 2, 3, "正在生成分析")
        data_payload = {"industries": industries}
        emit_phase(TEMPLATE, identifier, title, "data", data_payload, meta=meta)

        valid = [x for x in industries if x["ratio"] is not None]
        top5 = [f"{x['name']}(收益/风险={x['ratio']:.2f})" for x in valid[:5]]
        bot5 = [f"{x['name']}(收益/风险={x['ratio']:.2f})" for x in valid[-5:]]
        summary_text = (
            f"共{len(valid)}个行业的年化收益/风险数据\n"
            f"收益风险比最高: {', '.join(top5)}\n"
            f"收益风险比最低: {', '.join(bot5)}\n"
            f"均值收益率: {sum(x['y1_return'] for x in valid if x['y1_return'] is not None) / max(len(valid), 1):.2f}%\n"
            f"均值波动率: {sum(x['y1_vol'] for x in valid if x['y1_vol'] is not None) / max(len(valid), 1):.2f}%"
        )
        analysis = call_analysis_llm(summary_text, "行业收益风险矩阵")

        time.sleep(0.15)
        emit_phase(TEMPLATE, identifier, title, "final", {}, meta=meta, analysis=analysis)

        summary = {
            "status": "ok",
            "mode": "risk_matrix",
            "industries_count": len(industries),
            "top3": [{"name": x["name"], "ratio": x["ratio"]} for x in valid[:3]],
            "bottom3": [{"name": x["name"], "ratio": x["ratio"]} for x in valid[-3:]],
            "summary_text": summary_text,
        }
        if args.scope != "all":
            summary["scope"] = args.scope
        if args.codes:
            summary["codes"] = args.codes
        print(json.dumps(attach_render(summary), ensure_ascii=False))

    except Exception as e:
        emit_error(TEMPLATE, identifier, title, str(e))
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
