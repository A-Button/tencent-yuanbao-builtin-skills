#!/usr/bin/env python3
"""Unified chart script for SW index real-time, indicator, and compare views.

注意：单指数 K 线图模式（--mode kline）已移除——单指数日/周/月K线统一走
`sw_kline_report.py`（固定版式 HTML 研报，见 references/SW_KLINE_REPORT.md）。
本脚本保留 realtime / indicator / compare 三种模式（indicator 与 compare 内部
仍使用 K 线数据，但不再提供单指数 K 线图入口）。

Usage:
  python sw_chart.py --mode realtime --code 801001 --name "申万50"
  python sw_chart.py --mode indicator --code 801001 --name "申万50" --indicators macd,rsi --period DAY --days 120
  python sw_chart.py --mode compare --codes 801001,801003 --names 申万50,申万A指
"""

from __future__ import annotations

import json
import argparse
import datetime as _dt
import importlib.util
import sys
import os
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from client import USE_WESTOCK, sw_get, sw_post, APIOfflineError, APIError  # noqa: E402
from sw_common import (  # noqa: E402
    COLOR_POOL, call_analysis_llm, normalize_pct, emit_artifact, emit_progress, emit_phase,
    attach_render,
    FUND_CODES, STYLE_BROAD_CODES, JC_CODES,
    is_fund, is_style_broad, is_jc,
    get_index_display_name,
)


TEMPLATE_MAP = {
    "realtime": "SW_RT",
    "indicator": "SW_IND",
    "compare": "SW_CMP",
}

_EXTERNAL_INDEX_CLIENT = None


def _load_external_index_client():
    global _EXTERNAL_INDEX_CLIENT
    if _EXTERNAL_INDEX_CLIENT is not None:
        return _EXTERNAL_INDEX_CLIENT

    candidates = [
        os.path.join(SCRIPT_DIR, "external_indices.py"),
        "/agents/_shared/market_indices/client.py",  # 平台 fallback
        "/agents/_shared/tushare/client.py",  # 平台 fallback
    ]
    for path in candidates:
        if os.path.exists(path):
            spec = importlib.util.spec_from_file_location("pi_external_index_client", path)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                _EXTERNAL_INDEX_CLIENT = mod
                return mod
    raise RuntimeError("外部常用指数日K线查询暂不可用")


def _is_external_index(code: str) -> bool:
    try:
        return bool(_load_external_index_client().is_supported_index(code))
    except Exception:
        return False


def ma(series: list, n: int) -> list:
    result = [None] * (n - 1)
    for i in range(n - 1, len(series)):
        result.append(round(sum(series[i - n + 1 : i + 1]) / n, 4))
    return result


# ── Realtime ──

def fetch_realtime(code: str) -> tuple:
    raw = sw_get(
        "/institute-sw/api/index_publish/details/timelines/",
        params={"swindexcode": code},
        timeout=30,
    )
    data = raw["data"]
    if not data:
        raise ValueError("API returned empty data list")

    last = data[-1]
    meta = {
        "prev_close": float(last["l3"]),
        "open": float(last["l4"]),
        "high": float(last["l6"]),
        "low": float(last["l7"]),
        "latest": float(last["l8"]),
        "amount_cum": round(float(last["l5"]) / 100, 4) if last["l5"] is not None else None,
        "vol_cum": round(float(last["l11"]) / 100, 4),
        "time": last["trading_time"],
        "date": last["trading_date"],
        "name": last.get("l2", ""),
        "code": last.get("l1", ""),
        "point_interval": "1min" if USE_WESTOCK else "10s",
        "raw_count": len(data),
    }

    sampled = data
    times = [r["trading_time"] for r in sampled]
    prices = [float(r["l8"]) for r in sampled]
    amounts_cum = [round(float(r["l5"]) / 100, 4) if r["l5"] is not None else None for r in sampled]
    vol_cum = [round(float(r["l11"]) / 100, 4) for r in sampled]

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


# ── K-line ──

def fetch_kline(code: str, period: str, days: int) -> tuple:
    if _is_external_index(code):
        return fetch_external_index_kline(code, period, days)

    if is_style_broad(code) or is_jc(code):
        resp = sw_post(
            "/insWechatSw/dflgOrJcIndex/getDLFGKChartData",
            body={"swIndexCode": code, "indexType": 1 if is_style_broad(code) else 2, "type": period},
        )
    elif is_fund(code):
        resp = sw_post(
            "/insWechatSw/fundIndex/getFundKChartData",
            body={"swIndexCode": code, "type": period},
        )
    else:
        resp = sw_get(
            "/institute-sw/api/index_publish/trend/",
            params={"swindexcode": code, "period": period, "limit": days},
        )

    data = resp["data"]
    if not data:
        raise ValueError("API returned empty data")

    recent = data[-days:]
    closes = [float(r["closeindex"]) for r in recent]
    chart = {
        "labels": [r["bargaindate"][:10] for r in recent],
        "open": [float(r["openindex"]) for r in recent],
        "high": [float(r["maxindex"]) for r in recent],
        "low": [float(r["minindex"]) for r in recent],
        "close": closes,
        "ma5": ma(closes, 5),
        "ma10": ma(closes, 10),
        "ma20": ma(closes, 20),
        "volumes": [round(float(r.get("bargainamount", 0)), 4) for r in recent],
        "amounts": [round(float(r.get("bargainsum", 0)), 4) for r in recent],
    }
    api_name = recent[-1].get("swindexname") or recent[-1].get("l2") or code
    if str(api_name) == str(code):
        api_name = None  # API 返回的是代码而非名称时忽略，交由内部注册表解析
    name = get_index_display_name(code, api_name)
    meta = {"name": name, "code": code, "period": period}
    return chart, meta


def fetch_external_index_kline(code: str, period: str, days: int) -> tuple:
    if period != "DAY":
        raise ValueError("外部常用指数目前仅支持 DAY 日K线对比")

    ts = _load_external_index_client()
    end_dt = _dt.date.today()
    lookback_days = max(120, days * 3)
    start_dt = end_dt - _dt.timedelta(days=lookback_days)
    raw = ts.index_daily(
        code,
        start_dt.strftime("%Y%m%d"),
        end_dt.strftime("%Y%m%d"),
    )
    bars = (raw.get("bars") or [])[-days:]
    if not bars:
        raise ValueError("外部常用指数日K线数据为空")

    closes = [float(r["close"]) for r in bars]
    chart = {
        "labels": [r["date"] for r in bars],
        "open": [float(r["open"]) for r in bars],
        "high": [float(r["high"]) for r in bars],
        "low": [float(r["low"]) for r in bars],
        "close": closes,
        "ma5": ma(closes, 5),
        "ma10": ma(closes, 10),
        "ma20": ma(closes, 20),
        "volumes": [round(float(r.get("volume", 0)), 4) for r in bars],
        "amounts": [round(float(r.get("amount", 0)), 4) for r in bars],
    }
    meta = {
        "name": raw.get("name") or code,
        "code": raw.get("code") or code,
        "period": period,
        "source": raw.get("source") or "external_index",
        "ts_code": raw.get("ts_code"),
    }
    return chart, meta


def fetch_compare_kline(code: str, period: str, days: int) -> tuple:
    return fetch_kline(code, period, days)


# ── Indicator (kline + technical indicators) ──

def fetch_indicator(code: str, period: str, days: int, indicators: list) -> tuple:
    chart, meta = fetch_kline(code, period, days)
    meta["indicators"] = indicators

    from indicators import compute  # noqa: E402
    ind_data = compute(chart, indicators)
    chart.update(ind_data)
    return chart, meta


# ── Compare ──

def _run_compare(args):
    codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    names = [n.strip() for n in args.names.split(",") if n.strip()]
    while len(names) < len(codes):
        names.append(codes[len(names)])
    names = [get_index_display_name(code, name) for code, name in zip(codes, names)]
    cmp_type = args.compare_type

    template = TEMPLATE_MAP["compare"]
    identifier = "sw-compare-" + "-".join(codes)
    title = " vs ".join(names) + " 对比分析"

    emit_artifact(template, identifier, title, {"loading": True})
    emit_phase(template, identifier, title, "meta", {"codes": codes, "names": names, "compareType": cmp_type})

    series = []
    total = len(codes)
    for i, (code, name) in enumerate(zip(codes, names)):
        emit_progress(template, identifier, title, i, total, "正在获取数据")
        color = COLOR_POOL[i % len(COLOR_POOL)]
        try:
            if cmp_type == "realtime":
                if _is_external_index(code):
                    raise ValueError("外部常用指数目前仅支持 K 线走势对比，请使用 --compare-type kline")
                chart, meta = fetch_realtime(code)
                pct = normalize_pct(chart["prices"], meta["prev_close"])
                chg = meta["latest"] - meta["prev_close"]
                series.append({
                    "name": name, "code": code, "color": color,
                    "times": chart["times"], "pctChanges": pct,
                    "latest": meta["latest"], "prevClose": meta["prev_close"],
                    "change": round(chg, 2),
                    "changePct": round(chg / meta["prev_close"] * 100, 2) if meta["prev_close"] else 0,
                })
            else:
                chart, meta = fetch_compare_kline(code, args.period, args.days)
                closes = chart["close"]
                base = closes[0] if closes else 1
                pct = normalize_pct(closes, base)
                latest = closes[-1] if closes else 0
                chg = round(latest - base, 2)
                series.append({
                    "name": name, "code": code, "color": color,
                    "labels": chart["labels"], "pctChanges": pct,
                    "latestClose": latest, "change": chg,
                    "changePct": round(chg / base * 100, 2) if base else 0,
                })
        except Exception as exc:
            if USE_WESTOCK:
                raise
            series.append({"name": name, "code": code, "color": color, "error": str(exc)})

    if USE_WESTOCK and len(codes) < 2:
        raise ValueError('指数对比至少需要两个代码')
    if cmp_type == 'kline' and all('error' not in item for item in series):
        common = sorted(set.intersection(*(set(item['labels']) for item in series)))
        if len(common) < 2:
            raise ValueError('指数对比共同交易日不足')
        if len({item['labels'][-1] for item in series}) > 1:
            raise ValueError('指数对比最新交易日不一致')
        for item in series:
            values = dict(zip(item['labels'],item['pctChanges']))
            base_ratio = 1+values[common[0]]/100
            item['pctChanges'] = [round(((1+values[d]/100)/base_ratio-1)*100,4) for d in common]
            item['labels'] = common
            base_price = item['latestClose']/(1+item['pctChanges'][-1]/100)
            item['change'] = round(item['latestClose']-base_price,2)
            item['changePct'] = item['pctChanges'][-1]

    valid = [s for s in series if "error" not in s]

    if not valid:
        error_msgs = [f"{s['name']}({s['code']}): {s['error']}" for s in series]
        error_text = "所有指数数据获取失败:\n" + "\n".join(error_msgs)
        emit_artifact(template, identifier, title, {
            "loading": False, "error": error_text,
        })
        print(json.dumps({
            "status": "error", "mode": "compare",
            "message": error_text,
            "summary_text": "\n".join(error_msgs),
        }, ensure_ascii=False))
        return

    lines = []
    for s in series:
        if "error" in s:
            lines.append(f"{s['name']}({s['code']}): 数据获取失败 - {s['error']}")
        elif cmp_type == "realtime":
            lines.append(
                f"{s['name']}({s['code']}): 最新{s['latest']}, "
                f"涨跌{s['change']:+.2f}, 涨跌幅{s['changePct']:+.2f}%"
            )
        else:
            lines.append(
                f"{s['name']}({s['code']}): 收盘{s['latestClose']}, "
                f"涨跌{s['change']:+.2f}, 涨跌幅{s['changePct']:+.2f}%"
            )
    analysis = call_analysis_llm("\n".join(lines), "指数对比")

    meta = {"codes": codes, "names": names, "compareType": cmp_type}
    data_payload = {"compareType": cmp_type, "series": series}
    time.sleep(0.15)
    emit_phase(template, identifier, title, "data", data_payload, meta=meta)
    time.sleep(0.15)
    emit_phase(template, identifier, title, "final", data_payload, meta=meta, analysis=analysis)

    print(json.dumps(attach_render({
        "status": "ok", "mode": "compare", "compareType": cmp_type,
        "count": len(valid),
        "series": [{"name": s["name"], "code": s["code"], "changePct": s.get("changePct")} for s in valid],
        "summary_text": "\n".join(lines),
    }), ensure_ascii=False))


# ── Main ──

def _trim_chart_by_date(chart: dict, start: str, end: str) -> dict:
    """Trim a chart dict (with 'labels' key as YYYY-MM-DD) to [start, end] range."""
    labels = chart.get("labels", [])
    start_cmp = f"{start[:4]}-{start[4:6]}-{start[6:8]}" if len(start) == 8 else start
    end_cmp = f"{end[:4]}-{end[4:6]}-{end[6:8]}" if len(end) == 8 else end

    indices = [i for i, d in enumerate(labels) if start_cmp <= d <= end_cmp]
    if not indices:
        raise ValueError(f"在 {start}~{end} 范围内未找到K线数据")

    lo, hi = indices[0], indices[-1] + 1
    trimmed = {}
    for k, v in chart.items():
        if isinstance(v, list) and len(v) == len(labels):
            trimmed[k] = v[lo:hi]
        else:
            trimmed[k] = v

    return trimmed


def main():
    parser = argparse.ArgumentParser(description="SW index chart with template artifact output")
    parser.add_argument("--mode", required=True, choices=["realtime", "indicator", "compare"])
    parser.add_argument("--code", default="", help="6-digit Shenwan index code")
    parser.add_argument("--name", default="", help="Index display name")
    parser.add_argument("--period", default="DAY", choices=["DAY", "WEEK", "MONTH"])
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--start", default=None, help="Start date YYYYMMDD (mutually exclusive with --days)")
    parser.add_argument("--end", default=None, help="End date YYYYMMDD (mutually exclusive with --days)")
    parser.add_argument("--indicators", default="macd,kdj,rsi,boll,cci,atr,obv,adx",
                        help="Comma-separated indicators for indicator mode（默认全量 8 个：macd,kdj,rsi,boll,cci,atr,obv,adx）")
    parser.add_argument("--codes", default="", help="Comma-separated codes for compare mode")
    parser.add_argument("--names", default="", help="Comma-separated names for compare mode")
    parser.add_argument("--compare-type", default="realtime", choices=["realtime", "kline"], help="Compare data type")
    parser.add_argument("--anchor-date", default=None,
                        help="锚点日期 YYYYMMDD。配合 --before-days/--after-days 展示锚点前后窗口（仅 indicator）")
    parser.add_argument("--before-days", type=int, default=30,
                        help="锚点之前的日历日数（仅 --anchor-date 生效，默认 30）")
    parser.add_argument("--after-days", type=int, default=30,
                        help="锚点之后的日历日数（仅 --anchor-date 生效，默认 30）")
    args = parser.parse_args()

    # Anchor date → convert to --start/--end
    if args.anchor_date:
        if args.mode != "indicator":
            print(json.dumps({
                "status": "error",
                "message": "--anchor-date 仅支持 indicator 模式",
            }, ensure_ascii=False), file=sys.stderr)
            sys.exit(1)
        if args.start or args.end:
            print(json.dumps({
                "status": "error",
                "message": "--anchor-date 与 --start/--end 互斥",
            }, ensure_ascii=False), file=sys.stderr)
            sys.exit(1)
        try:
            import datetime as _dt
            anchor_dt = _dt.datetime.strptime(args.anchor_date, "%Y%m%d").date()
        except ValueError:
            print(json.dumps({
                "status": "error",
                "message": f"--anchor-date {args.anchor_date} 格式错误，需 YYYYMMDD",
            }, ensure_ascii=False), file=sys.stderr)
            sys.exit(1)
        start_dt = anchor_dt - _dt.timedelta(days=args.before_days)
        end_dt = anchor_dt + _dt.timedelta(days=args.after_days)
        args.start = start_dt.strftime("%Y%m%d")
        args.end = end_dt.strftime("%Y%m%d")

    use_date_range = args.start is not None and args.end is not None

    if args.mode == "compare":
        try:
            _run_compare(args)
        except Exception as e:
            t = TEMPLATE_MAP["compare"]
            ident = "sw-compare"
            emit_artifact(t, ident, "对比分析", {"loading": False, "error": str(e)})
            print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False), file=sys.stderr)
            sys.exit(1)
        return

    template = TEMPLATE_MAP[args.mode]
    display_name = get_index_display_name(args.code, args.name or args.code)

    if args.mode == "realtime":
        identifier = f"sw-realtime-{args.code}"
        title = f"{display_name} 实时分时图"
    elif use_date_range:
        identifier = f"sw-{args.mode}-{args.code}-{args.start}-{args.end}"
        title = f"{display_name} 技术指标图 · {args.start}~{args.end}"
    else:
        identifier = f"sw-{args.mode}-{args.code}-{args.days}d"
        title = f"{display_name} 技术指标图"
        if args.days != 90:
            title += f" · {args.days}日"

    emit_artifact(template, identifier, title, {"loading": True})
    emit_phase(template, identifier, title, "meta", {"code": args.code, "name": display_name})

    try:
        if args.mode == "realtime":
            chart, meta = fetch_realtime(args.code)
        else:
            effective_days = 9999 if use_date_range else max(args.days, 60)
            ind_list = [s.strip() for s in args.indicators.split(",") if s.strip()]
            chart, meta = fetch_indicator(args.code, args.period, effective_days, ind_list)
            if use_date_range:
                chart = _trim_chart_by_date(chart, args.start, args.end)

        emit_phase(template, identifier, title, "data", chart, meta=meta)

        summary = {
            "status": "ok",
            "mode": args.mode,
            "code": args.code,
            "name": meta.get("name") or display_name,
        }
        if args.mode == "realtime":
            summary["latest"] = meta["latest"]
            summary["prev_close"] = meta["prev_close"]
            summary["date"] = meta["date"]
            summary["time"] = meta["time"]
            summary["sampled_count"] = len(chart["times"])
            summary["point_interval"] = meta.get("point_interval", "10s")
            summary["raw_count"] = meta.get("raw_count", len(chart["times"]))
            chg = meta["latest"] - meta["prev_close"]
            chg_pct = chg / meta["prev_close"] * 100 if meta["prev_close"] else 0
            summary["change"] = round(chg, 2)
            summary["change_pct"] = round(chg_pct, 2)
        elif args.mode == "indicator":
            summary["bars"] = len(chart["labels"])
            summary["period"] = args.period
            summary["range"] = f"{chart['labels'][0]}~{chart['labels'][-1]}"
            latest_close = chart["close"][-1]
            summary["latest_close"] = latest_close
            summary["latest_open"] = chart["open"][-1]
            summary["latest_high"] = chart["high"][-1]
            summary["latest_low"] = chart["low"][-1]
            summary["latest_date"] = chart["labels"][-1]
            summary["latest_volume"] = chart["volumes"][-1]
            summary["latest_amount"] = chart["amounts"][-1]
            if len(chart["close"]) >= 2:
                prev = chart["close"][-2]
                summary["prev_close"] = prev
                chg = latest_close - prev
                summary["change"] = round(chg, 2)
                summary["change_pct"] = round(chg / prev * 100, 2) if prev else 0
            summary["indicators"] = args.indicators

        if summary.get("mode") == "indicator" and "summary_text" not in summary:
            _name = summary.get("name", summary.get("code", ""))
            _close = summary.get("latest_close", "")
            _chg = summary.get("change_pct")
            _period = summary.get("period", "")
            _rng = summary.get("range", "")
            _chg_str = f"，涨跌幅 {_chg:+.2f}%" if _chg is not None else ""
            summary["summary_text"] = f"{_name} {_period}线最新收盘 {_close}{_chg_str}，区间 {_rng}"
        elif summary.get("mode") == "realtime" and "summary_text" not in summary:
            _name = summary.get("name", summary.get("code", ""))
            _latest = summary.get("latest", "")
            _chg = summary.get("change_pct")
            _chg_str = f"，涨跌幅 {_chg:+.2f}%" if _chg is not None else ""
            summary["summary_text"] = f"{_name} 最新价 {_latest}{_chg_str}"

        print(json.dumps(attach_render(summary), ensure_ascii=False))

    except APIOfflineError as e:
        emit_artifact(template, identifier, title, {
            "loading": False, "error": str(e),
        })
        print(json.dumps({
            "status": "offline", "offline": True, "message": str(e),
        }, ensure_ascii=False))

    except Exception as e:
        emit_artifact(template, identifier, title, {
            "loading": False, "error": str(e),
        })
        print(json.dumps({
            "status": "error", "message": str(e),
        }, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
