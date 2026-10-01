#!/usr/bin/env python3
"""Historical percentile of a single-index metric.

Answers "XX 当前 PE 在 N 年历史处于什么分位"—— 常见估值分位数问题。

Methodology:
  1. Pull N 年 K 线（default 5 年）
  2. For pe/pb/dp: need full historical series which SWS API 不直接提供 —
     fallback 用 month-end snapshots (index_analysis_reports/?type=MONTH)
     按月点取样
  3. For close: 直接用 K 线
  4. 计算当前值在 N 年分布的百分位

Usage:
  python sw_quantile.py --code 801780 --name 银行 --metric pe --years 5
"""

from __future__ import annotations

import argparse
import json
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
    fetch_period_dates,
    fetch_period_snapshot,
    fetch_fundamentals_batch,

)
TEMPLATE = "SW_QUANTILE"

_INDEX_TYPES = ("一级行业", "市场表征", "二级行业", "风格指数")


def _percentile_rank(values: list[float], target: float) -> float:
    """What % of values are ≤ target. Returns 0-100."""
    if not values:
        return None
    n = len(values)
    count = sum(1 for v in values if v <= target)
    return round(count / n * 100, 2)


def _quantile(values: list[float], q: float) -> float:
    """q-th percentile (0 ≤ q ≤ 1)."""
    if not values:
        return None
    s = sorted(values)
    k = q * (len(s) - 1)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def _find_indextype(code: str) -> str | None:
    """Guess which indextype contains this code by trying each."""
    for t in _INDEX_TYPES:
        rows = fetch_fundamentals_batch(t)
        if any(r.get("code") == code for r in rows):
            return t
    return None


def _collect_monthly_series(code: str, metric: str, years: int,
                            index_type: str) -> list[tuple[str, float]]:
    """Collect (date, metric) pairs for the last N years of month-end snapshots.

    Only works for metrics available in index_analysis_reports/ — pe/pb/dp/turnover/close/change_pct.
    """
    dates = fetch_period_dates("MONTH")
    # Limit to last N years (≈ 12N months)
    wanted = dates[: max(12 * years, 12)]

    series = []
    for d in wanted:
        snap = fetch_period_snapshot("MONTH", d, index_type)
        row = next((r for r in snap if r.get("code") == code), None)
        if row and row.get(metric) is not None:
            series.append((d, float(row[metric])))
    return series


def _collect_close_from_kline(code: str, years: int) -> list[tuple[str, float]]:
    """For metric=close: use K-line directly, sample month-end points."""
    days = 250 * years
    kline = fetch_kline_one(code, "DAY", days)
    if not kline:
        return []
    # Group by YYYY-MM, keep last entry per month
    by_month: dict[str, tuple[str, float]] = {}
    for bar in kline:
        d = (bar.get("bargaindate") or "")[:10]
        ym = d[:7]
        if not ym:
            continue
        try:
            c = float(bar.get("closeindex") or 0)
        except (ValueError, TypeError):
            continue
        if c <= 0:
            continue
        by_month[ym] = (d, c)  # keep latest date per month (overwrite)
    months = sorted(by_month.keys())
    return [by_month[m] for m in months]


def _fmt(v):
    return "—" if v is None else f"{v:.2f}"


def main():
    parser = argparse.ArgumentParser(description="Historical percentile of index metric")
    parser.add_argument("--code", required=True)
    parser.add_argument("--name", default="")
    parser.add_argument("--metric", default="pe",
                        choices=["pe", "pb", "dp", "turnover", "close"])
    parser.add_argument("--years", type=int, default=None, help="指定完整回溯年数；省略时展示供应商窗口百分位")
    parser.add_argument("--index-type", default=None,
                        choices=[None] + list(_INDEX_TYPES),
                        help="可选，省略时自动识别")
    args = parser.parse_args()

    from client import USE_WESTOCK
    if USE_WESTOCK:
        try:
            _run_westock(args)
        except Exception as exc:
            print(json.dumps({"status":"error","message":str(exc)}, ensure_ascii=False), file=sys.stderr)
            sys.exit(1)
        return
    args.years = args.years or 5
    name = args.name or args.code
    metric_label_map = {"pe":"PE", "pb":"PB", "dp":"股息率", "turnover":"换手率", "close":"收盘价"}
    metric_label_short = metric_label_map[args.metric]
    identifier = f"sw-quantile-{args.code}-{args.metric}-{args.years}y"
    title = f"{name} · {metric_label_short} 近 {args.years} 年分位"
    emit_artifact(TEMPLATE, identifier, title, {"loading": True})

    try:
        if args.years < 1:
            raise ValueError("--years 最小 1")

        emit_phase(TEMPLATE, identifier, title, "meta", {
            "code": args.code, "name": name,
            "metric": args.metric, "metric_label": metric_label_short,
            "years": args.years,
        }, meta={"title": title})

        # Resolve index type
        index_type = args.index_type
        if args.metric != "close" and not index_type:
            emit_progress(TEMPLATE, identifier, title, 1, 3, "识别指数类型")
            index_type = _find_indextype(args.code)
            if not index_type:
                raise ValueError(f"无法识别 {args.code} 属于哪类指数（市场表征/一级/二级/风格）")

        # Collect historical series
        emit_progress(TEMPLATE, identifier, title, 2, 3, f"采集近 {args.years} 年月度 {metric_label_short} 历史")
        if args.metric == "close":
            series = _collect_close_from_kline(args.code, args.years)
        else:
            series = _collect_monthly_series(args.code, args.metric, args.years, index_type)

        if len(series) < 12:
            raise ValueError(f"历史数据不足（样本 {len(series)} 个，需至少 12）")

        values = [v for _, v in series]
        current = values[0]  # 最新月（series 按日期降序）

        # Recompute current via fundamentals_batch for freshness (if not close)
        if args.metric != "close":
            emit_progress(TEMPLATE, identifier, title, 3, 3, "获取最新值")
            latest_rows = fetch_fundamentals_batch(index_type)
            row = next((r for r in latest_rows if r.get("code") == args.code), None)
            if row and row.get(args.metric) is not None:
                current = float(row[args.metric])

        historical = values  # include current
        percentile = _percentile_rank(historical, current)

        metric_label = {
            "pe": "PE", "pb": "PB",
            "dp": "股息率", "turnover": "换手率", "close": "收盘价",
        }[args.metric]

        # Percentile category
        if percentile is None:
            cat = "—"
        elif percentile <= 10:
            cat = "极低位（<10%）"
        elif percentile <= 25:
            cat = "低位（<25%）"
        elif percentile <= 50:
            cat = "中下位（<50%）"
        elif percentile <= 75:
            cat = "中上位（<75%）"
        elif percentile <= 90:
            cat = "高位（<90%）"
        else:
            cat = "极高位（≥90%）"

        suffix = "%" if args.metric in ("dp", "turnover") else ""

        summary_text = (
            f"{name}({args.code}) 当前 {metric_label} {_fmt(current)}{suffix}，"
            f"处于近 {args.years} 年 {_fmt(percentile)}% 分位（{cat}）\n"
            f"历史区间：{_fmt(min(historical))}~{_fmt(max(historical))}{suffix}  "
            f"中位数 {_fmt(_quantile(historical, 0.5))}{suffix}  "
            f"25分位 {_fmt(_quantile(historical, 0.25))}{suffix}  "
            f"75分位 {_fmt(_quantile(historical, 0.75))}{suffix}\n"
            f"（样本 {len(historical)} 个月点，范围 {series[-1][0]} ~ {series[0][0]}）"

        # Prepare time series for chart (ascending by date)
        )
        series_asc = sorted(series, key=lambda x: x[0])
        chart_dates = [s[0] for s in series_asc]
        chart_values = [round(s[1], 4) for s in series_asc]

        stats = {
            "current": round(current, 4),
            "percentile": percentile,
            "category": cat,
            "min": round(min(historical), 4),
            "max": round(max(historical), 4),
            "median": round(_quantile(historical, 0.5), 4),
            "p25": round(_quantile(historical, 0.25), 4),
            "p75": round(_quantile(historical, 0.75), 4),
        }

        data_payload = {
            "code": args.code, "name": name,
            "metric": args.metric, "metric_label": metric_label, "suffix": suffix,
            "years": args.years,
            "index_type": index_type,
            "stats": stats,
            "samples_count": len(historical),
            "range": f"{series[-1][0]} ~ {series[0][0]}",
            "dates": chart_dates,
            "values": chart_values,
            "summary_text": summary_text,
        }

        emit_phase(TEMPLATE, identifier, title, "data", data_payload,
                   meta={"title": title})
        emit_phase(TEMPLATE, identifier, title, "final", data_payload,
                   meta={"title": title}, analysis=summary_text)

        print(json.dumps(attach_render({
            "status": "ok",
            "mode": "quantile",
            "code": args.code, "name": name,
            "metric": args.metric, "years": args.years,
            "index_type": index_type,
            "current": stats["current"], "percentile": percentile,
            "category": stats.get("category"),
            "min": stats["min"], "max": stats["max"],
            "median": stats["median"], "p25": stats["p25"], "p75": stats["p75"],
            "samples_count": len(historical),
            "range": f"{series[-1][0]} ~ {series[0][0]}",
            "summary_text": summary_text,
        }), ensure_ascii=False))

    except Exception as e:
        emit_error(TEMPLATE, identifier, title, str(e))
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False),
              file=sys.stderr)
        sys.exit(1)



def _run_westock(args):
    from datasource import get_valuation, get_kline, IncompleteDataError, UnsupportedCapabilityError
    from sw_common import add_render_file, get_render_dir, INDUSTRY_NAME_BY_CODE
    from sw_render import md_table_from_payload
    from datetime import date, timedelta
    name = args.name or INDUSTRY_NAME_BY_CODE.get(args.code, args.code)
    if args.years is not None and args.years < 1:
        raise ValueError('--years 最小1')
    if args.years is None and args.metric in ('pe','pb'):
        row = get_valuation(args.code)[-1]
        value, pct = row.get(args.metric), row.get(args.metric+'_percentile')
        if value is None or pct is None:
            raise IncompleteDataError('估值或供应商历史百分位缺失')
        summary = dict(status='ok',mode='quantile',code=args.code,name=name,metric=args.metric,
                       current=value,percentile=pct,date=row['date'],percentile_window=row['percentile_window'],
                       summary_text=f"{name} {row['date']} {args.metric.upper()} {value:.4f}，供应商历史窗口百分位 {pct:.2f}%；窗口年数未说明。")
    else:
        years = args.years or 1
        end = date.today()
        start = end.replace(year=end.year-years) if not (end.month==2 and end.day==29) else end.replace(year=end.year-years,day=28)
        if args.metric == 'close':
            rows = get_kline(args.code,limit=250*years+30)
            series = [(r['bargaindate'],r['closeindex']) for r in rows]
        elif args.metric in ('pe','pb','dp'):
            rows = get_valuation(args.code,start.isoformat(),end.isoformat())
            series = [(r['date'],r[args.metric]) for r in rows if r.get(args.metric) is not None]
        else:
            raise UnsupportedCapabilityError('当前源无历史换手率估值序列')
        series = sorted(set(series))
        if len(series)<12 or date.fromisoformat(series[0][0])>start+timedelta(days=7):
            coverage=f'{series[0][0]}~{series[-1][0]}' if series else '空'
            raise IncompleteDataError(f'请求{years}年历史，实际覆盖{coverage}，不足以给出指定年数分位。PE/PB可省略 --years 查询供应商窗口百分位。')
        actual_end = date.fromisoformat(series[-1][0])
        # Anchor lookback to the actual latest observation, not a later query date.
        actual_start = actual_end.replace(year=actual_end.year-years) if not (actual_end.month==2 and actual_end.day==29) else actual_end.replace(year=actual_end.year-years,day=28)
        series = [(d,v) for d,v in series if d>=actual_start.isoformat()]
        value=series[-1][1]; pct=_percentile_rank([v for _,v in series],value)
        summary=dict(status='ok',mode='quantile',code=args.code,name=name,metric=args.metric,years=years,
                     current=value,percentile=pct,date=series[-1][0],samples_count=len(series),range=f'{series[0][0]}~{series[-1][0]}',
                     summary_text=f'{name} {args.metric} 当前{value:.4f}，近{years}年日样本分位{pct:.2f}%；实际覆盖{series[0][0]}~{series[-1][0]}，{len(series)}样本。')
    payload={'title':name+' 历史分位', 'description':summary['summary_text'],
             'columns':[{'key':'metric','title':'指标'},{'key':'current','title':'当前值'},{'key':'percentile','title':'百分位%'},{'key':'date','title':'截至日期'}],
             'rows':[summary]}
    path=os.path.join(get_render_dir(),f"quantile-{args.code}-{args.metric}.md")
    os.makedirs(os.path.dirname(path),exist_ok=True)
    with open(path,'w',encoding='utf-8') as f:
        f.write(md_table_from_payload(payload))
    add_render_file('quantile','md',path)
    print(json.dumps(attach_render(summary),ensure_ascii=False))

if __name__ == "__main__":
    main()
