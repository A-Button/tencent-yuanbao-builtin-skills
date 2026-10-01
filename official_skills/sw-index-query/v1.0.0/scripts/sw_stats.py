#!/usr/bin/env python3
"""Single-index all-metrics snapshot.

Reports all key performance / risk / win-rate metrics for ONE index in a single
ranked table. Use case:
  "算一下申万银行指数的年化收益率、年化波动率、Sharpe、Calmar、最大回撤、日胜率"

Usage:
  python sw_stats.py --code 801780 --name 银行 [--days 1250] [--benchmark 801003]
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
    fetch_risk_return_one,
    fetch_fundamentals_batch,
    TRADING_DAYS_PER_YEAR,

)
TEMPLATE = "SW_STATS"

RISK_FREE_RATE = 0.02  # 2% 无风险利率


def _annual_return(closes: list[float]) -> float:
    """Annualized return from first to last close."""
    if len(closes) < 2 or closes[0] <= 0:
        return None
    total = closes[-1] / closes[0] - 1
    years = (len(closes)-1) / TRADING_DAYS_PER_YEAR
    if years <= 0:
        return None
    return round(((1 + total) ** (1 / years) - 1) * 100, 2)


def _annual_vol(daily_rets: list[float]) -> float:
    """Annualized volatility from daily returns."""
    n = len(daily_rets)
    if n < 30:
        return None
    mean = sum(daily_rets) / n
    var = sum((r - mean) ** 2 for r in daily_rets) / (n - 1)
    return round(math.sqrt(var) * math.sqrt(TRADING_DAYS_PER_YEAR) * 100, 2)


def _max_drawdown(closes: list[float]) -> float:
    """Max drawdown (negative percentage)."""
    if not closes:
        return None
    peak = closes[0]
    mdd = 0.0
    for c in closes:
        if c > peak:
            peak = c
        if peak > 0:
            dd = (c - peak) / peak
            if dd < mdd:
                mdd = dd
    return round(mdd * 100, 2)


def _win_rate_daily(daily_rets: list[float]) -> float:
    """% of days with positive return."""
    n = len(daily_rets)
    if n == 0:
        return None
    wins = sum(1 for r in daily_rets if r > 0)
    return round(wins / n * 100, 2)


def _win_rate_monthly(closes: list[float], dates: list[str]) -> float:
    """% of calendar months with positive return."""
    if len(closes) != len(dates) or len(closes) < 2:
        return None
    month_opens: dict[str, float] = {}
    month_closes: dict[str, float] = {}
    for c, d in zip(closes, dates):
        ym = (d or "")[:7]  # YYYY-MM
        if not ym:
            continue
        if ym not in month_opens:
            month_opens[ym] = c
        month_closes[ym] = c

    months = sorted(month_opens.keys())
    if len(months) < 2:
        return None
    wins = 0
    for m in months:
        if month_closes[m] > month_opens[m]:
            wins += 1
    return round(wins / len(months) * 100, 2)


def _win_rate_yearly(closes: list[float], dates: list[str]) -> float:
    """% of calendar years with positive return."""
    if len(closes) != len(dates) or len(closes) < 2:
        return None
    year_opens: dict[int, float] = {}
    year_closes: dict[int, float] = {}
    for c, d in zip(closes, dates):
        try:
            y = int((d or "")[:4])
        except ValueError:
            continue
        if y not in year_opens:
            year_opens[y] = c
        year_closes[y] = c

    years = sorted(year_opens.keys())
    if len(years) < 2:
        return None
    wins = sum(1 for y in years if year_closes[y] > year_opens[y])
    return round(wins / len(years) * 100, 2)


def _lookup_fundamentals(code: str) -> dict:
    """Look up PE/PB/dp/turnover for a single index across all index types."""
    from client import USE_WESTOCK
    if USE_WESTOCK:
        from datasource import get_valuation
        return get_valuation(code)[-1]
    for indextype in ("一级行业", "市场表征", "二级行业", "风格指数"):
        rows = fetch_fundamentals_batch(indextype)
        for r in rows:
            if r.get("code") == code:
                return r
    return {}


def _fmt(v, suffix=""):
    return "—" if v is None else f"{v:.2f}{suffix}"


def main():
    parser = argparse.ArgumentParser(description="Single-index all-metrics snapshot")
    parser.add_argument("--code", required=True)
    parser.add_argument("--name", default="")
    parser.add_argument("--days", type=int, default=1250, help="默认 5 年")
    parser.add_argument("--benchmark", default=None, help="可选基准代码")
    args = parser.parse_args()

    name = args.name or args.code
    identifier = f"sw-stats-{args.code}-{args.days}d"
    title = f"{name} · 全指标快照（{args.days} 日）"
    emit_artifact(TEMPLATE, identifier, title, {"loading": True})

    try:
        emit_phase(TEMPLATE, identifier, title, "meta", {
            "code": args.code, "name": name,
            "days": args.days,
            "benchmark": args.benchmark,
        }, meta={"title": title})

        emit_progress(TEMPLATE, identifier, title, 1, 3, "获取 K 线")
        # 1. Fetch K-line
        kline = fetch_kline_one(args.code, "DAY", args.days)
        if not kline or len(kline) < 30:
            raise ValueError(f"K 线数据不足（{len(kline) if kline else 0} 根），需至少 30 根")

        dates = [(b.get("bargaindate") or "")[:10] for b in kline]
        closes = [float(b.get("closeindex") or 0) for b in kline if b.get("closeindex")]
        dates = dates[:len(closes)]

        # 2. Compute daily returns
        daily_rets = []
        for i in range(1, len(closes)):
            if closes[i - 1] > 0:
                daily_rets.append(closes[i] / closes[i - 1] - 1)

        # 3. Core metrics
        annual_return = _annual_return(closes)
        annual_vol = _annual_vol(daily_rets)
        mdd = _max_drawdown(closes)
        wr_day = _win_rate_daily(daily_rets)
        wr_month = _win_rate_monthly(closes, dates)
        wr_year = _win_rate_yearly(closes, dates)

        sharpe = None
        if annual_return is not None and annual_vol and annual_vol > 0:
            sharpe = round((annual_return / 100 - RISK_FREE_RATE) / (annual_vol / 100), 2)

        calmar = None
        if annual_return is not None and mdd is not None and mdd < -0.01:
            calmar = round(annual_return / abs(mdd), 2)

        emit_progress(TEMPLATE, identifier, title, 2, 3, "获取区间收益风险")
        # 4. Risk/return API (1y/3y/5y + volatility)
        rr = fetch_risk_return_one(args.code) or {}

        emit_progress(TEMPLATE, identifier, title, 3, 3, "获取基本面")
        # 5. Fundamentals (PE/PB/dp/turnover)
        fund = _lookup_fundamentals(args.code)
        valuation_date = fund.get("date")

        # 6. Build output
        first_date = dates[0] if dates else ""
        last_date = dates[-1] if dates else ""

        stats = {
            "window_days": len(closes),
            "range": f"{first_date}~{last_date}",
            "annual_return": annual_return,
            "annual_vol": annual_vol,
            "sharpe": sharpe,
            "calmar": calmar,
            "max_drawdown": mdd,
            "win_rate_day": wr_day,
            "win_rate_month": wr_month,
            "win_rate_year": wr_year,
            # From API
            "m1_return": rr.get("m1_return"),
            "m3_return": rr.get("m3_return"),
            "ytd_return": rr.get("ytd_return"),
            "y1_return": rr.get("y1_return"),
            "y3_return": rr.get("y3_return"),
            "y5_return": rr.get("y5_return"),
            "y1_vol": rr.get("y1_vol"),
            "y3_vol": rr.get("y3_vol"),
            "y5_vol": rr.get("y5_vol"),
            # Fundamentals
            "valuation_date": valuation_date,
            "pe": fund.get("pe"),
            "pb": fund.get("pb"),
            "dp": fund.get("dp"),
            "turnover": fund.get("turnover"),
            "circ_mcap": fund.get("circ_mcap"),
        }

        summary_text = (
            f"指数: {name}({args.code}) | 窗口: {first_date} ~ {last_date}（{len(closes)}根K线）\n"
            f"收益：年化 {_fmt(annual_return, '%')}  |  近1年 {_fmt(rr.get('y1_return'), '%')}  "
            f"|  近3年 {_fmt(rr.get('y3_return'), '%')}  |  近5年 {_fmt(rr.get('y5_return'), '%')}  "
            f"|  YTD {_fmt(rr.get('ytd_return'), '%')}\n"
            f"风险：年化波动 {_fmt(annual_vol, '%')}  |  最大回撤 {_fmt(mdd, '%')}\n"
            f"风调后：Sharpe {_fmt(sharpe)}（rf=2%）  |  Calmar {_fmt(calmar)}\n"
            f"胜率：日 {_fmt(wr_day, '%')}  |  月 {_fmt(wr_month, '%')}  |  年 {_fmt(wr_year, '%')}\n"
            f"估值：PE {_fmt(fund.get('pe'))}  |  PB {_fmt(fund.get('pb'))}  "
            f"|  股息率 {_fmt(fund.get('dp'), '%')}  |  换手率 {_fmt(fund.get('turnover'), '%')}  "
            f"|  流通市值 {_fmt(fund.get('circ_mcap'))}亿"

        # Sample cumulative return curve (for template sparkline)
        )
        n_total = len(closes)
        step = max(1, n_total // 150)
        idxs = list(range(0, n_total, step))
        if idxs[-1] != n_total - 1: idxs.append(n_total - 1)
        sampled_dates = [dates[i] for i in idxs]
        sampled_closes = [round(closes[i], 2) for i in idxs]

        data_payload = {
            "code": args.code, "name": name,
            "stats": stats,
            "sampled_dates": sampled_dates,
            "sampled_closes": sampled_closes,
            "summary_text": summary_text,
        }

        emit_phase(TEMPLATE, identifier, title, "data", data_payload, meta={"title": title})
        emit_phase(TEMPLATE, identifier, title, "final", data_payload,
                   meta={"title": title}, analysis=summary_text)

        print(json.dumps(attach_render({
            "status": "ok",
            "mode": "stats",
            "code": args.code, "name": name,
            "stats": stats,
            "summary_text": summary_text,
        }), ensure_ascii=False))

    except Exception as e:
        emit_error(TEMPLATE, identifier, title, str(e))
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False),
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
