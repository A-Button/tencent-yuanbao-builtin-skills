#!/usr/bin/env python3
"""单指数日K线技术面研报：拉取申万指数日K线 → 计算统计指标 → 形态识别
→ 按固定模板产出 HTML 研报（sw_html_report.py 模板 1）。

Usage:
  python sw_kline_report.py --code 801080                 # 申万电子 120 日
  python sw_kline_report.py --code 801080 --days 250      # 250 日
  python sw_kline_report.py --code 000300 --days 120      # 外部常用指数
  python sw_kline_report.py --code 801080 --name 电子     # 显式给名
  python sw_kline_report.py --code 801080 --output dir    # 指定输出目录

输出：
  - stdout 最后一行 JSON 摘要（含 render_files.html 路径）
  - HTML 研报文件（默认 <工作目录>/<名称><代码>_日K线研报.html）
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

from client import USE_WESTOCK, sw_get  # noqa: E402
from sw_common import (  # noqa: E402
    is_fund, is_style_broad, is_jc,
    get_index_display_name, get_workspace_dir, attach_render,
    fetch_kline_one,
)
from external_indices import index_daily, is_supported_index  # noqa: E402
from sw_html_report import render_kline_report  # noqa: E402


# ── 轻量 K 线形态识别（纯标准库，无 pandas 依赖）────────────────────────
# 输入：closes / opens / highs / lows（同长度列表，时间升序）
# 输出：list[{"date","signal"}]，signal: 1=看涨 / -1=看跌（仅报告非零信号）


def _body(o, c):
    return c - o


def _range(h, l):
    return h - l


def _upper_shadow(o, c, h):
    return h - max(o, c)


def _lower_shadow(o, c, l):
    return min(o, c) - l


def detect_candle_patterns(dates, opens, highs, lows, closes):
    """识别常见 K 线形态，返回非零信号列表（仅最近 120 根内）。"""
    n = len(closes)
    signals = []
    for i in range(2, n):
        if i < 2:
            continue
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]
        o1, h1, l1, c1 = opens[i-1], highs[i-1], lows[i-1], closes[i-1]
        o2, h2, l2, c2 = opens[i-2], highs[i-2], lows[i-2], closes[i-2]

        rng = _range(h, l)
        if rng <= 0:
            continue
        body = abs(_body(o, c))
        body_ratio = body / rng
        upper = _upper_shadow(o, c, h)
        lower = _lower_shadow(o, c, l)
        sig = 0

        # ── 单根形态 ──
        # 锤子线（看涨反转）：下影 ≥ 2×实体，上影短，出现在下跌后
        if lower >= 2 * body and upper <= body and body > 0 and c1 < o1:
            sig = 1
        # 射击之星（看跌反转）：上影 ≥ 2×实体，下影短，出现在上涨后
        elif upper >= 2 * body and lower <= body and body > 0 and c1 > o1:
            sig = -1
        # 十字星（多空分歧）：实体 ≤ 10% 振幅
        elif body_ratio <= 0.1:
            # 结合前一根方向：前跌后十字 → 潜在看涨；前涨后十字 → 潜在看跌
            sig = 1 if c1 < o1 else (-1 if c1 > o1 else 0)
        # 纺锤线（实体小，影线长，趋势犹豫）—— 不单独给信号，避免噪音

        # ── 双根形态 ──
        # 看涨吞没：前阴后阳，阳实体完全包裹阴实体
        if c1 < o1 and c > o and c >= o1 and o <= c1:
            sig = 1
        # 看跌吞没：前阳后阴，阴实体完全包裹阳实体
        elif c1 > o1 and c < o and o >= c1 and c <= o1:
            sig = -1
        # 看涨孕线：前阳后阴（小实体），被前实体包裹
        elif c1 > o1 and c < o and o <= c1 and c >= o1 and body < abs(_body(o1, c1)):
            sig = 0  # 孕线弱信号，不单独报
        # 看跌孕线：前阴后阳（小实体）
        elif c1 < o1 and c > o and o >= c1 and c <= o1 and body < abs(_body(o1, c1)):
            sig = 0

        # ── 三根形态（晨星 / 暮星 / 三白兵 / 三黑乌鸦）──
        # 晨星：大阴 → 小实体/十字 → 大阳，收在首根中点之上
        if c2 < o2 and abs(_body(o2, c2)) > 0 and \
           c > o and c >= (o2 + c2) / 2 and \
           abs(_body(o1, c1)) <= _range(h1, l1) * 0.3:
            sig = 1
        # 暮星：大阳 → 小实体/十字 → 大阴，收在首根中点之下
        elif c2 > o2 and abs(_body(o2, c2)) > 0 and \
             c < o and c <= (o2 + c2) / 2 and \
             abs(_body(o1, c1)) <= _range(h1, l1) * 0.3:
            sig = -1
        # 三白兵：连续三根阳线，收盘逐级抬高
        elif c2 > o2 and c1 > o1 and c > o and \
             c > c1 > c2 and o >= o1 - 1e-9 and o1 >= o2 - 1e-9:
            sig = 1
        # 三黑乌鸦：连续三根阴线，收盘逐级走低
        elif c2 < o2 and c1 < o1 and c < o and \
             c < c1 < c2 and o <= o1 + 1e-9 and o1 <= o2 + 1e-9:
            sig = -1

        if sig != 0:
            signals.append({"date": dates[i], "signal": sig})
    return signals


# ── 统计指标 ──────────────────────────────────────────────────────────


def compute_stats(dates, opens, highs, lows, closes, volumes, ma5, ma10, ma20):
    close = closes
    n = len(close)
    last = close[-1]
    s = {}

    s["start_date"] = dates[0]
    s["end_date"] = dates[-1]
    s["first_close"] = round(close[0], 2)
    s["last_close"] = round(last, 2)
    s["period_chg_pct"] = round((last / close[0] - 1) * 100, 2)

    for days, key in [(5, "chg_5d"), (10, "chg_10d"), (20, "chg_20d"), (60, "chg_60d")]:
        if n > days and close[-1 - days]:
            s[key] = round((last / close[-1 - days] - 1) * 100, 2)

    s["period_high"] = round(max(highs), 2)
    s["period_low"] = round(min(lows), 2)
    s["high_date"] = dates[highs.index(max(highs))]
    s["low_date"] = dates[lows.index(min(lows))]

    high = max(highs)
    s["drawdown_from_high_pct"] = round((last / high - 1) * 100, 2)

    s["ma5"] = round(ma5[-1], 2) if ma5[-1] is not None else None
    s["ma10"] = round(ma10[-1], 2) if ma10[-1] is not None else None
    s["ma20"] = round(ma20[-1], 2) if ma20[-1] is not None else None
    s["above_ma5"] = bool(last > s["ma5"]) if s["ma5"] else False
    s["above_ma10"] = bool(last > s["ma10"]) if s["ma10"] else False
    s["above_ma20"] = bool(last > s["ma20"]) if s["ma20"] else False

    rets = [close[i] / close[i-1] - 1 for i in range(1, n) if close[i-1]]
    if len(rets) >= 20:
        import statistics
        vol20 = statistics.stdev(rets[-20:]) * math.sqrt(252) * 100
        s["vol_20d_annual_pct"] = round(vol20, 2)

    s["avg_vol_20d"] = round(sum(volumes[-20:]) / 20, 2)
    s["last_vol"] = round(volumes[-1], 2)
    s["vol_ratio_vs_20d"] = round(volumes[-1] / (sum(volumes[-20:]) / 20), 2) if volumes[-1] else 0

    up_days = sum(1 for i in range(1, n) if close[i] > close[i-1])
    s["up_days"] = up_days
    s["down_days"] = n - 1 - up_days

    daily = [close[i] / close[i-1] * 100 - 100 for i in range(1, n) if close[i-1]]
    if daily:
        s["max_up_day_pct"] = round(max(daily), 2)
        s["max_down_day_pct"] = round(min(daily), 2)
    return s


# ── 取数 ──────────────────────────────────────────────────────────────


def fetch_bars(code: str, days: int, period: str = "DAY"):
    """拉取K线（日/周/月），支持申万指数与外部常用指数（外部仅日线）。
    返回 (labels, o,h,l,c,volumes)。"""
    if is_supported_index(code):
        import datetime
        if period != "DAY":
            raise RuntimeError("外部常用指数目前仅支持日K线（DAY）")
        end = datetime.date.today()
        # 多取 1.6 倍日历日，保证交易日数量足够
        cal_days = int(days * 1.6) + 20
        start = end - datetime.timedelta(days=cal_days)
        data = index_daily(code, start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
        bars = data.get("bars") or []
        if not bars:
            raise RuntimeError(f"外部指数 {code} 无数据")
        labels = [str(b["date"])[:10].replace("-", "") for b in bars]
        labels = [f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 and d.isdigit() else d
                  for d in labels]
        opens = [float(b["open"]) for b in bars]
        highs = [float(b["high"]) for b in bars]
        lows = [float(b["low"]) for b in bars]
        closes = [float(b["close"]) for b in bars]
        volumes = [float(b.get("volume") or 0) for b in bars]
        name = data.get("name") or code
        return labels, opens, highs, lows, closes, volumes, [b.get("amount") for b in bars], name, "westock CLI 外部指数行情，可能有延迟，以交易所官方为准"

    # 申万指数
    if is_style_broad(code) or is_jc(code):
        resp = sw_post(
            "/insWechatSw/dflgOrJcIndex/getDLFGKChartData",
            body={"swIndexCode": code, "indexType": 1 if is_style_broad(code) else 2,
                  "type": period},
        )
        data = resp["data"]
    elif is_fund(code):
        resp = sw_post(
            "/insWechatSw/fundIndex/getFundKChartData",
            body={"swIndexCode": code, "type": period},
        )
        data = resp["data"]
    else:
        resp = sw_get(
            "/institute-sw/api/index_publish/trend/",
            params={"swindexcode": code, "period": period, "limit": days},
        )
        data = resp["data"]

    if not data:
        raise RuntimeError(f"申万指数 {code} 无K线数据")

    recent = data[-days:]
    labels = [r["bargaindate"][:10] for r in recent]
    opens = [float(r["openindex"]) for r in recent]
    highs = [float(r["maxindex"]) for r in recent]
    lows = [float(r["minindex"]) for r in recent]
    closes = [float(r["closeindex"]) for r in recent]
    volumes = [round(float(r.get("bargainamount", 0)), 4) for r in recent]

    api_name = recent[-1].get("swindexname") or recent[-1].get("l2") or None
    name = get_index_display_name(code, api_name)
    amounts = [r.get("bargainsum") for r in recent]
    return labels, opens, highs, lows, closes, volumes, amounts, name, ("腾讯自选股（申万行业板块口径），行情可能有延迟，以交易所披露为准" if USE_WESTOCK else "申万指数资料")


def ma_series(series, n):
    out = [None] * min(n - 1, len(series))
    for i in range(n - 1, len(series)):
        out.append(round(sum(series[i - n + 1:i + 1]) / n, 4))
    return out


def main():
    parser = argparse.ArgumentParser(description="单指数日K线技术面研报（HTML）")
    parser.add_argument("--code", required=True, help="指数代码（申万 801080 / 外部 000300）")
    parser.add_argument("--name", default=None, help="指数显示名（可选，默认自动解析）")
    parser.add_argument("--days", type=int, default=120, help="K线根数（默认120）")
    parser.add_argument("--period", default="DAY", choices=["DAY", "WEEK", "MONTH"],
                        help="K线周期（默认DAY日K线；外部常用指数仅支持DAY）")
    parser.add_argument("--output", default=None, help="输出目录（默认 <工作目录>）")
    args = parser.parse_args()

    try:
        labels, opens, highs, lows, closes, volumes, amounts, name, source = fetch_bars(
            args.code, args.days, args.period)
        if args.name:
            name = args.name

        ma5 = ma_series(closes, 5)
        ma10 = ma_series(closes, 10)
        ma20 = ma_series(closes, 20)
        stats = compute_stats(labels, opens, highs, lows, closes, volumes, ma5, ma10, ma20)

        # 形态识别（仅用最近 120 根）
        start = max(0, len(closes) - 120)
        signals = detect_candle_patterns(
            labels[start:], opens[start:], highs[start:], lows[start:], closes[start:]
        )

        bars = {
            "labels": labels, "open": opens, "high": highs, "low": lows,
            "close": closes, "ma5": ma5, "ma10": ma10, "ma20": ma20,
            "volumes": volumes, "amounts": amounts,
        }
        meta = {"name": name, "code": args.code, "period": args.period}

        out_dir = args.output or get_workspace_dir()
        html_path = render_kline_report(
            out_dir, meta, bars, stats, signals[-8:], source,
        )

        period_label = {"DAY": "日", "WEEK": "周", "MONTH": "月"}.get(args.period, "日")
        summary = {
            "status": "ok",
            "mode": "kline_report",
            "code": args.code,
            "name": name,
            "period": args.period,
            "bars": len(labels),
            "data_source": "westock" if USE_WESTOCK else "swsresearch",
            "data_note": source,
            "range": f"{labels[0]}~{labels[-1]}",
            "last_close": stats["last_close"],
            "period_chg_pct": stats["period_chg_pct"],
            "candle_signals_count": len(signals),
            "render_files": {"kline-report": {"html": html_path}},
        }
        print(json.dumps(summary, ensure_ascii=False))

    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False),
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
