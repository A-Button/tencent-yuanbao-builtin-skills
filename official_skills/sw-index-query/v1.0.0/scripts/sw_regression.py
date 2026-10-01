#!/usr/bin/env python3
"""Dual-index regression analysis: correlation, beta, alpha, tracking error.

Usage:
  python sw_regression.py --code 801010 --name "农林牧渔" [--benchmark 801003] [--bench-name "申万A指"] [--days 500]
"""

from __future__ import annotations

import json
import argparse
import sys
import os

import math
import statistics

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from sw_common import (  # noqa: E402
    attach_render,
  # noqa: E402
    emit_artifact, emit_progress, emit_phase,
    fetch_kline_for_group,
    call_analysis_llm,
    is_style_broad, is_jc,
    INDUSTRY_L1, STYLE_INDICES, MARKET_INDICES,
)


def _lookup_name(code: str) -> str:
    """Lookup index display name from code. Fallback to code itself."""
    for table in (INDUSTRY_L1, STYLE_INDICES, MARKET_INDICES):
        if code in table:
            return table[code]
    return code

TEMPLATE = "SW_REG"
TOTAL_STEPS = 5


def _align_klines(ka, kb):
    """Align two K-line lists by date, return (dates, closes_a, closes_b)."""
    da = {d['bargaindate']: float(d['closeindex']) for d in ka}
    db = {d['bargaindate']: float(d['closeindex']) for d in kb}
    common = sorted(set(da) & set(db))
    if len(common) < 30:
        return None, None, None
    return (
        common,
        [da[d] for d in common],
        [db[d] for d in common],
    )


def _beta_corr(ra, rb):
    if len(ra)!=len(rb) or len(ra)<2:
        return None,None
    ma,mb = statistics.mean(ra),statistics.mean(rb)
    cross=sum((a-ma)*(b-mb) for a,b in zip(ra,rb))
    va=sum((a-ma)**2 for a in ra); vb=sum((b-mb)**2 for b in rb)
    if va<=0 or vb<=0:
        return None,None
    return cross/vb,cross/math.sqrt(va*vb)


def _compute_regression(ca, cb):
    ra = [b/a-1 for a,b in zip(ca,ca[1:])]
    rb = [b/a-1 for a,b in zip(cb,cb[1:])]
    beta,corr = _beta_corr(ra,rb)
    if beta is None or corr is None:
        raise ValueError('目标或基准收益零方差，回归未定义')
    ma,mb = statistics.mean(ra),statistics.mean(rb)
    excess = [a-b for a,b in zip(ra,rb)]
    te = statistics.stdev(excess)*math.sqrt(250)
    cum_a,cum_b = (ca[-1]/ca[0]-1)*100,(cb[-1]/cb[0]-1)*100
    peak,mdd = ca[0],0
    for c in ca:
        peak=max(peak,c);mdd=max(mdd,(peak-c)/peak)
    return dict(correlation=round(corr,4),beta=round(beta,4),
                alpha_annual_pct=round((ma-beta*mb)*250*100,2),
                tracking_error_pct=round(te*100,2),
                info_ratio=round(statistics.mean(excess)*250/te,4) if te else None,
                cum_return_a=round(cum_a,2),cum_return_b=round(cum_b,2),excess_return=round(cum_a-cum_b,2),
                annual_return_a=round(((ca[-1]/ca[0])**(250/len(ra))-1)*100,2),
                annual_return_b=round(((cb[-1]/cb[0])**(250/len(rb))-1)*100,2),
                annual_vol_a=round(statistics.stdev(ra)*math.sqrt(250)*100,2),
                annual_vol_b=round(statistics.stdev(rb)*math.sqrt(250)*100,2),
                max_drawdown_a=round(mdd*100,2))


def _compute_rolling(ca, cb, window=60):
    ra=[b/a-1 for a,b in zip(ca,ca[1:])]
    rb=[b/a-1 for a,b in zip(cb,cb[1:])]
    betas,corrs = [],[]
    for i in range(len(ra)):
        b,c = _beta_corr(ra[i-window+1:i+1],rb[i-window+1:i+1]) if i>=window-1 else (None,None)
        betas.append(round(b,4) if b is not None else None)
        corrs.append(round(c,4) if c is not None else None)
    return dict(rolling_beta=betas,rolling_corr=corrs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", required=True, help="目标指数代码")
    ap.add_argument("--name", default=None, help="目标指数名称 (省略则从代码查表推断)")
    ap.add_argument("--benchmark", default="801003", help="基准指数代码")
    ap.add_argument("--bench-name", default=None, help="基准指数名称 (省略则从代码查表推断)")
    ap.add_argument("--days", type=int, default=500, help="回溯交易日数")
    args = ap.parse_args()

    # 名字默认值：从代码表推断（避免 agent 每次必填）
    if args.name is None:
        args.name = _lookup_name(args.code)
    if args.bench_name is None:
        args.bench_name = _lookup_name(args.benchmark) if args.benchmark != "801003" else "申万A指"

    identifier = f"regression-{args.code}-{args.benchmark}"
    title = f"{args.name} vs {args.bench_name} 回归分析"

    # Step 1: emit loading skeleton
    emit_artifact(TEMPLATE, identifier, title, {"loading": True})
    emit_progress(TEMPLATE, identifier, title, 1, TOTAL_STEPS, "正在获取K线数据")

    # Step 2: fetch K-line data
    codes = {args.code: args.name, args.benchmark: args.bench_name}
    klines = fetch_kline_for_group(codes, "DAY", args.days)

    ka = klines.get(args.code)
    kb = klines.get(args.benchmark)
    if not ka or not kb:
        missing = []
        if not ka:
            missing.append(args.name)
        if not kb:
            missing.append(args.bench_name)
        emit_artifact(TEMPLATE, identifier, title, {
            "loading": False,
            "error": f"K线数据获取失败: {', '.join(missing)}"
        })
        print(json.dumps({"error": f"K线数据获取失败: {', '.join(missing)}"}, ensure_ascii=False))
        return

    emit_progress(TEMPLATE, identifier, title, 2, TOTAL_STEPS, "正在对齐日期")

    # Step 3: align dates and compute
    dates, ca, cb = _align_klines(ka, kb)
    if dates is None:
        emit_artifact(TEMPLATE, identifier, title, {
            "loading": False,
            "error": "重叠交易日不足30天，无法分析"
        })
        print(json.dumps({"error": "重叠交易日不足30天"}, ensure_ascii=False))
        return
    emit_progress(TEMPLATE, identifier, title, 3, TOTAL_STEPS, "正在计算回归指标")
    metrics = _compute_regression(ca, cb)
    rolling = _compute_rolling(ca, cb, window=min(60, len(ca) // 3))

    # Step 4: build chart data for template
    emit_progress(TEMPLATE, identifier, title, 4, TOTAL_STEPS, "正在生成分析结论")

    base_a = ca[0]
    base_b = cb[0]
    norm_a = [round((v / base_a - 1) * 100, 2) for v in ca]
    norm_b = [round((v / base_b - 1) * 100, 2) for v in cb]

    kline_data = {
        "labels": [r["bargaindate"][:10] for r in ka],
        "open": [float(r["openindex"]) for r in ka],
        "high": [float(r["maxindex"]) for r in ka],
        "low": [float(r["minindex"]) for r in ka],
        "close": [float(r["closeindex"]) for r in ka],
        "volumes": [round(float(r.get("bargainamount", 0)), 4) for r in ka],
    }

    chart_data = {
        "dates": dates,
        "norm_a": norm_a,
        "norm_b": norm_b,
        "name_a": args.name,
        "name_b": args.bench_name,
        "code_a": args.code,
        "code_b": args.benchmark,
        "metrics": metrics,
        "rolling_beta": rolling["rolling_beta"],
        "rolling_corr": rolling["rolling_corr"],
        "kline": kline_data,
    }

    # Step 5: LLM analysis
    data_summary = (
        f"双指数回归分析: {args.name}({args.code}) vs {args.bench_name}({args.benchmark})\n"
        f"分析区间: {dates[0]} 至 {dates[-1]}，共{len(dates)}个交易日\n"
        f"相关系数: {metrics['correlation']}\n"
        f"Beta: {metrics['beta']}\n"
        f"年化Alpha: {metrics['alpha_annual_pct']}%\n"
        f"年化追踪误差: {metrics['tracking_error_pct']}%\n"
        f"信息比率: {metrics['info_ratio']}\n"
        f"{args.name}累计收益: {metrics['cum_return_a']}%, 年化: {metrics['annual_return_a']}%, 年化波动率: {metrics['annual_vol_a']}%, 最大回撤: {metrics['max_drawdown_a']}%\n"
        f"{args.bench_name}累计收益: {metrics['cum_return_b']}%, 年化: {metrics['annual_return_b']}%, 年化波动率: {metrics['annual_vol_b']}%\n"
        f"累计超额收益: {metrics['excess_return']}%"
    )
    analysis = call_analysis_llm(data_summary, "双指数回归")

    # Emit final data
    emit_phase(TEMPLATE, identifier, title, "final", chart_data,
               meta={"type": "regression", "name": args.name, "code": args.code},
               analysis=analysis)

    # JSON summary for Agent
    summary_text = (
        f"{args.name}({args.code})与{args.bench_name}({args.benchmark})"
        f"近{len(dates)}个交易日({dates[0]}至{dates[-1]})回归分析:\n"
        f"- 相关系数: {metrics['correlation']}\n"
        f"- Beta: {metrics['beta']}\n"
        f"- 年化Alpha: {metrics['alpha_annual_pct']}%\n"
        f"- 年化追踪误差: {metrics['tracking_error_pct']}%\n"
        f"- 信息比率: {metrics['info_ratio']}\n"
        f"- {args.name}累计收益: {metrics['cum_return_a']}%  年化: {metrics['annual_return_a']}%  年化波动率: {metrics['annual_vol_a']}%  最大回撤: {metrics['max_drawdown_a']}%\n"
        f"- {args.bench_name}累计收益: {metrics['cum_return_b']}%  年化: {metrics['annual_return_b']}%  年化波动率: {metrics['annual_vol_b']}%\n"
        f"- 累计超额收益: {metrics['excess_return']}%"
    )

    result = {
        "status": "ok",
        "mode": "regression",
        "summary_text": summary_text,
        **metrics,
        "days": len(dates),
        "start_date": dates[0],
        "end_date": dates[-1],
    }
    print(json.dumps(attach_render(result), ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status":"error","message":str(exc)}, ensure_ascii=False),file=sys.stderr)
        sys.exit(1)
