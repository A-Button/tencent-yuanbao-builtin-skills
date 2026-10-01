#!/usr/bin/env python3
"""Index-level weighted portfolio aggregation.

Combine N indices with given weights, compute portfolio daily returns,
report annualized return / vol / Sharpe / Calmar / MDD, and (optionally)
α/β vs a benchmark.

**Important**: This is for INDEX-level weighted portfolios (e.g. "30% 电子 +
40% 申万300 + 30% 银行"). For STOCK-level portfolios with share counts
(e.g. "1月5日买入招行 1000 股"), use stock-query skill's stock_portfolio.py.

Usage:
  sw_portfolio_agg.py --codes 801080,801300,801780 --names 电子,申万300,银行
                      --weights 0.3,0.4,0.3 [--days 250] [--benchmark 801003]
"""

from __future__ import annotations

import argparse
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
  # noqa: E402
    emit_artifact, emit_phase, emit_progress, emit_error,
    fetch_kline_one,
    fetch_kline_for_group,
    TRADING_DAYS_PER_YEAR,
    INDUSTRY_L1, STYLE_INDICES, MARKET_INDICES,
    get_index_display_name,

)
TEMPLATE = "SW_PORTFOLIO"

RISK_FREE_RATE = 0.02


def _kline_to_ret_map(kline: list) -> dict[str, float]:
    closes = []
    dates = []
    for b in kline:
        try:
            c = float(b.get("closeindex") or 0)
            if c > 0:
                closes.append(c)
                dates.append((b.get("bargaindate") or "")[:10])
        except (ValueError, TypeError):
            continue
    rets = {}
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            rets[dates[i]] = closes[i] / closes[i - 1] - 1
    return rets


def _annual_return(daily_rets: list[float]) -> float:
    if not daily_rets:
        return None
    # Compound returns
    cum = 1.0
    for r in daily_rets:
        cum *= (1 + r)
    years = len(daily_rets) / TRADING_DAYS_PER_YEAR
    if years <= 0:
        return None
    return round((cum ** (1 / years) - 1) * 100, 2)


def _cum_return(daily_rets: list[float]) -> float:
    if not daily_rets:
        return None
    cum = 1.0
    for r in daily_rets:
        cum *= (1 + r)
    return round((cum - 1) * 100, 2)


def _annual_vol(daily_rets: list[float]) -> float:
    n = len(daily_rets)
    if n < 30:
        return None
    mean = sum(daily_rets) / n
    var = sum((r - mean) ** 2 for r in daily_rets) / (n - 1)
    return round(math.sqrt(var) * math.sqrt(TRADING_DAYS_PER_YEAR) * 100, 2)


def _max_drawdown(daily_rets: list[float]) -> float:
    if not daily_rets:
        return None
    cum = 1.0
    peak = 1.0
    mdd = 0.0
    for r in daily_rets:
        cum *= (1 + r)
        if cum > peak:
            peak = cum
        dd = (cum - peak) / peak
        if dd < mdd:
            mdd = dd
    return round(mdd * 100, 2)


def _beta_alpha(port_rets: list[float], bench_rets: list[float]) -> tuple[float, float]:
    """(beta, alpha_annual_pct) via OLS."""
    n = min(len(port_rets), len(bench_rets))
    if n < 30:
        return None, None
    a = port_rets[:n]
    b = bench_rets[:n]
    mean_a = sum(a) / n
    mean_b = sum(b) / n
    cov = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(n)) / (n - 1)
    var_b = sum((b[i] - mean_b) ** 2 for i in range(n)) / (n - 1)
    if var_b <= 0:
        return None, None
    beta = cov / var_b
    # Annualized alpha
    alpha = (mean_a - beta * mean_b) * TRADING_DAYS_PER_YEAR
    return round(beta, 3), round(alpha * 100, 2)


def _fmt(v, suffix=""):
    return "—" if v is None else f"{v:.2f}{suffix}"


def main():
    parser = argparse.ArgumentParser(description="Index-weighted portfolio aggregation")
    parser.add_argument("--codes", required=True, help="逗号分隔指数代码")
    parser.add_argument("--names", default=None, help="逗号分隔名称")
    parser.add_argument("--weights", required=True, help="逗号分隔权重（和应 ≈ 1）")
    parser.add_argument("--days", type=int, default=250)
    parser.add_argument("--benchmark", default=None, help="可选基准代码（默认不对比）")
    parser.add_argument("--bench-name", default=None)
    args = parser.parse_args()

    identifier = f"sw-portfolio-{args.codes.replace(',','-')[:40]}-{args.days}d"
    title = "指数级加权组合分析"
    emit_artifact(TEMPLATE, identifier, title, {"loading": True})

    try:
        codes = [c.strip() for c in args.codes.split(",") if c.strip()]
        weights = [float(w.strip()) for w in args.weights.split(",")]
        if len(codes) != len(weights):
            raise ValueError(f"codes({len(codes)}) 和 weights({len(weights)}) 数量不一致")
        if args.names:
            names = [n.strip() for n in args.names.split(",")]
            if len(names) != len(codes):
                raise ValueError("names 数量必须与 codes 一致")
            names = [get_index_display_name(c, n) for c, n in zip(codes, names)]
        else:
            all_names = {**INDUSTRY_L1, **STYLE_INDICES, **MARKET_INDICES}
            names = [get_index_display_name(c, all_names.get(c, c)) for c in codes]

        w_sum = sum(weights)
        if abs(w_sum - 1.0) > 0.05:
            # Allow user to pass percentages; normalize
            if abs(w_sum - 100) < 1:
                weights = [w / 100 for w in weights]
                w_sum = 1.0
            else:
                raise ValueError(f"权重和应 ≈ 1（或 100%），当前 {w_sum:.3f}")

        title = f"{len(codes)} 指数加权组合 · {args.days}日"
        emit_phase(TEMPLATE, identifier, title, "meta", {
            "codes": codes, "names": names, "weights": weights,
            "days": args.days,
            "benchmark": args.benchmark, "bench_name": args.bench_name,
        }, meta={"title": title})

        emit_progress(TEMPLATE, identifier, title, 1, 2, f"获取 {len(codes)} 指数 K 线")

        # Fetch K-lines
        codes_dict = dict(zip(codes, names))
        klines = fetch_kline_for_group(codes_dict, "DAY", args.days)

        ret_maps = {}
        for c in codes:
            k = klines.get(c)
            if not k:
                raise ValueError(f"获取 {c}({codes_dict[c]}) K 线失败")
            ret_maps[c] = _kline_to_ret_map(k)

        # Align common dates
        common_dates = None
        for rm in ret_maps.values():
            ds = set(rm.keys())
            common_dates = ds if common_dates is None else (common_dates & ds)
        common_dates = sorted(common_dates)
        if len(common_dates) < 30:
            raise ValueError(f"共同交易日不足（{len(common_dates)}）")

        # Build portfolio daily returns
        port_rets = []
        for d in common_dates:
            r = sum(ret_maps[c][d] * weights[i] for i, c in enumerate(codes))
            port_rets.append(r)

        # Compute components' individual stats over same window
        components = []
        for i, c in enumerate(codes):
            r_series = [ret_maps[c][d] for d in common_dates]
            components.append({
                "code": c, "name": names[i], "weight": weights[i],
                "cum_return": _cum_return(r_series),
                "annual_return": _annual_return(r_series),
                "annual_vol": _annual_vol(r_series),
            })

        # Portfolio stats
        port_cum = _cum_return(port_rets)
        port_annual = _annual_return(port_rets)
        port_vol = _annual_vol(port_rets)
        port_mdd = _max_drawdown(port_rets)
        port_sharpe = None
        if port_annual is not None and port_vol and port_vol > 0:
            port_sharpe = round((port_annual / 100 - RISK_FREE_RATE) / (port_vol / 100), 2)
        port_calmar = None
        if port_annual is not None and port_mdd and port_mdd < -0.01:
            port_calmar = round(port_annual / abs(port_mdd), 2)

        # Optional benchmark comparison
        vs_bench = None
        bench_aligned_rets = None
        if args.benchmark:
            emit_progress(TEMPLATE, identifier, title, 2, 2, f"获取基准 {args.bench_name or args.benchmark}")
            bench_kline = fetch_kline_one(args.benchmark, "DAY", args.days)
            if not bench_kline:
                raise ValueError(f"基准 {args.benchmark} K 线获取失败")
            bench_rets = _kline_to_ret_map(bench_kline)
            aligned_port = []
            aligned_bench = []
            for d in common_dates:
                if d in bench_rets:
                    aligned_port.append(ret_maps[codes[0]][d] * weights[0] + sum(
                        ret_maps[codes[i]][d] * weights[i] for i in range(1, len(codes))
                    ))
                    aligned_bench.append(bench_rets[d])
            if len(aligned_port) >= 30:
                beta, alpha = _beta_alpha(aligned_port, aligned_bench)
                b_cum = _cum_return(aligned_bench)
                p_cum = _cum_return(aligned_port)
                vs_bench = {
                    "benchmark": args.benchmark,
                    "bench_name": args.bench_name or args.benchmark,
                    "beta": beta,
                    "alpha_annual_pct": alpha,
                    "port_cum": p_cum, "bench_cum": b_cum,
                    "excess_return": round((p_cum or 0) - (b_cum or 0), 2),
                }
                bench_aligned_rets = aligned_bench

        # Build summary
        comp_str = ", ".join(f"{c['name']}({c['weight']*100:.0f}%)" for c in components)
        lines = [
            f"组合: {comp_str}",
            f"窗口: {common_dates[0]} ~ {common_dates[-1]}（{len(common_dates)} 日）",
            f"组合累计收益: {_fmt(port_cum, '%')}  |  年化 {_fmt(port_annual, '%')}  "
            f"|  年化波动 {_fmt(port_vol, '%')}",
            f"风调后: Sharpe {_fmt(port_sharpe)}（rf=2%）  |  Calmar {_fmt(port_calmar)}  "
            f"|  最大回撤 {_fmt(port_mdd, '%')}",
        ]
        if vs_bench:
            lines.append(
                f"vs {vs_bench['bench_name']}: Beta {_fmt(vs_bench['beta'])}  "
                f"|  年化α {_fmt(vs_bench['alpha_annual_pct'], '%')}  "
                f"|  累计超额 {_fmt(vs_bench['excess_return'], '%')}"
            )
        summary_text = "\n".join(lines)

        # Build cumulative curves for chart (down-sample to ~200 points)
        total = len(common_dates)
        step = max(1, total // 200)
        idxs = list(range(0, total, step))
        if idxs[-1] != total - 1: idxs.append(total - 1)

        # Portfolio cumulative index normalized to 100
        port_cum_curve = [100.0]
        cum = 1.0
        for r in port_rets:
            cum *= (1 + r)
            port_cum_curve.append(round(cum * 100, 2))
        # sample
        port_curve = [port_cum_curve[i] for i in idxs if i < len(port_cum_curve)]
        sampled_dates = [common_dates[i] for i in idxs]

        # Benchmark cum curve aligned to common_dates
        bench_curve = None
        if bench_aligned_rets is not None and len(bench_aligned_rets) >= 30:
            b_cum_curve = [100.0]
            cumb = 1.0
            for r in bench_aligned_rets:
                cumb *= (1 + r)
                b_cum_curve.append(round(cumb * 100, 2))
            # align by length
            bench_curve = [b_cum_curve[i] for i in idxs if i < len(b_cum_curve)]

        data_payload = {
            "components": components,
            "window": f"{common_dates[0]} ~ {common_dates[-1]}",
            "effective_days": len(common_dates),
            "stats": {
                "cum_return": port_cum,
                "annual_return": port_annual,
                "annual_vol": port_vol,
                "sharpe": port_sharpe, "calmar": port_calmar,
                "max_drawdown": port_mdd,
            },
            "vs_benchmark": vs_bench,
            "sampled_dates": sampled_dates,
            "port_curve": port_curve,
            "bench_curve": bench_curve,
            "summary_text": summary_text,
        }

        emit_phase(TEMPLATE, identifier, title, "data", data_payload, meta={"title": title})
        emit_phase(TEMPLATE, identifier, title, "final", data_payload,
                   meta={"title": title}, analysis=summary_text)

        print(json.dumps(attach_render({
            "status": "ok",
            "mode": "portfolio_agg",
            "components": components,
            "window": f"{common_dates[0]} ~ {common_dates[-1]}",
            "effective_days": len(common_dates),
            "cum_return": port_cum,
            "annual_return": port_annual,
            "annual_vol": port_vol,
            "sharpe": port_sharpe,
            "calmar": port_calmar,
            "max_drawdown": port_mdd,
            "vs_benchmark": vs_bench,
            "summary_text": summary_text,
        }), ensure_ascii=False))

    except Exception as e:
        emit_error(TEMPLATE, identifier, title, str(e))
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False),
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
