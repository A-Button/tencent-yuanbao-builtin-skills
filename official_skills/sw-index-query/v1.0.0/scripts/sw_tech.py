#!/usr/bin/env python3
"""SW_TECH: Technical diagnosis for Shenwan indices.

Usage:
  python sw_tech.py --code 801030 --name "基础化工" --period DAY --days 120
"""

from __future__ import annotations

import json
import argparse
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from sw_common import (  # noqa: E402
    attach_render,
  # noqa: E402
    emit_artifact, emit_error, emit_phase, call_analysis_llm,
    RSI_OVERBOUGHT, RSI_OVERSOLD,
    KDJ_OVERBOUGHT, KDJ_OVERSOLD,
    CCI_STRONG, CCI_WEAK,
    get_index_display_name,
)
from sw_chart import fetch_kline  # noqa: E402
from indicators import macd, rsi, kdj, boll, cci, atr, obv, adx, ma  # noqa: E402


TEMPLATE = "SW_TECH"

# ── 事件后验（原 sw_event_stats 能力，整合进技术诊断）─────────────────────
EVENT_LABELS = {
    "macd_golden": "MACD 金叉",
    "macd_dead": "MACD 死叉",
    "kdj_golden": "KDJ 金叉",
    "kdj_dead": "KDJ 死叉",
    "boll_break_high": "突破 BOLL 上轨",
    "boll_break_low": "跌破 BOLL 下轨",
    "ma5_20_golden": "MA5↑MA20 金叉",
    "ma5_20_dead": "MA5↓MA20 死叉",
    "ma20_60_golden": "MA20↑MA60 金叉",
    "ma20_60_dead": "MA20↓MA60 死叉",
}


def _detect_cross(a: list, b: list, *, direction: str) -> list[int]:
    """Return indices where a crosses b (direction 'up' = a goes above b)."""
    idxs = []
    for i in range(1, len(a)):
        if a[i] is None or b[i] is None or a[i - 1] is None or b[i - 1] is None:
            continue
        if direction == "up":
            if a[i - 1] <= b[i - 1] and a[i] > b[i]:
                idxs.append(i)
        else:
            if a[i - 1] >= b[i - 1] and a[i] < b[i]:
                idxs.append(i)
    return idxs


def _detect_breach(series: list, ref: list, *, direction: str) -> list[int]:
    """Series breaches ref line (direction 'up' = series crosses above)."""
    idxs = []
    for i in range(1, len(series)):
        if series[i] is None or ref[i] is None or series[i - 1] is None or ref[i - 1] is None:
            continue
        if direction == "up":
            if series[i - 1] <= ref[i - 1] and series[i] > ref[i]:
                idxs.append(i)
        else:
            if series[i - 1] >= ref[i - 1] and series[i] < ref[i]:
                idxs.append(i)
    return idxs


def detect_events(event: str, closes: list, highs: list, lows: list) -> list[int]:
    """检出历史事件索引（复用与事件后验脚本一致的指标口径）。"""
    if event == "macd_golden":
        dif, dea, _ = macd(closes)
        return _detect_cross(dif, dea, direction="up")
    if event == "macd_dead":
        dif, dea, _ = macd(closes)
        return _detect_cross(dif, dea, direction="down")
    if event == "kdj_golden":
        k_arr, d_arr, _ = kdj(highs, lows, closes)
        return _detect_cross(k_arr, d_arr, direction="up")
    if event == "kdj_dead":
        k_arr, d_arr, _ = kdj(highs, lows, closes)
        return _detect_cross(k_arr, d_arr, direction="down")
    if event == "boll_break_high":
        _, upper, _ = boll(closes)
        return _detect_breach(closes, upper, direction="up")
    if event == "boll_break_low":
        _, _, lower = boll(closes)
        return _detect_breach(closes, lower, direction="down")
    if event in ("ma5_20_golden", "ma5_20_dead"):
        ma_fast, ma_slow = ma(closes, 5), ma(closes, 20)
        return _detect_cross(ma_fast, ma_slow,
                             direction="up" if event.endswith("golden") else "down")
    if event in ("ma20_60_golden", "ma20_60_dead"):
        ma_fast, ma_slow = ma(closes, 20), ma(closes, 60)
        return _detect_cross(ma_fast, ma_slow,
                             direction="up" if event.endswith("golden") else "down")
    raise ValueError(f"未知事件类型: {event}")


def _event_histogram(vals: list, bins: int = 12) -> dict:
    if not vals:
        return {"edges": [], "counts": []}
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        return {"edges": [lo, hi], "counts": [len(vals)]}
    edges = [lo + (hi - lo) * i / bins for i in range(bins + 1)]
    counts = [0] * bins
    for v in vals:
        idx = min(bins - 1, int((v - lo) / (hi - lo) * bins))
        counts[idx] += 1
    return {"edges": [round(e, 2) for e in edges], "counts": counts}


def compute_event_stats(event: str, chart: dict, forward_days: int = 20) -> dict:
    """计算单指数事件后验统计（MACD/KDJ/BOLL/MA 金叉死叉后 N 日前向收益）。

    chart 为 sw_chart.fetch_kline 返回的解析后 dict（labels/high/low/close）。
    Returns: dict（无事件时 stats=None）。含 stats / events / histogram /
    chart_dates / chart_closes / summary_text 片段。
    """
    closes = [float(v) for v in chart["close"]]
    highs = [float(v) for v in chart["high"]]
    lows = [float(v) for v in chart["low"]]
    dates = chart["labels"]
    if len(closes) < 120:
        return {"events_count": 0, "stats": None, "events": [], "event_markers": [],
                "chart_dates": [], "chart_closes": [], "histogram": {"edges": [], "counts": []},
                "summary_text": f"本次观察窗口为{len(closes)}根K线，事件回测需要至少120根完整样本；本页展示技术指标，不给出事件回测结论"}

    event_idxs = detect_events(event, closes, highs, lows)

    n_total = len(closes)
    sample_step = max(1, n_total // 250)
    price_idxs = list(range(0, n_total, sample_step))
    if price_idxs[-1] != n_total - 1:
        price_idxs.append(n_total - 1)
    chart_dates = [dates[i] for i in price_idxs]
    chart_closes = [round(closes[i], 2) for i in price_idxs]

    events = []
    for idx in event_idxs:
        if idx + forward_days >= n_total:
            continue
        entry = closes[idx]
        exit_ = closes[idx + forward_days]
        ret = round((exit_ - entry) / entry * 100, 2)
        events.append({
            "date": dates[idx],
            "entry_close": round(entry, 2),
            "exit_close": round(exit_, 2),
            "forward_return": ret,
        })

    n = len(events)
    if n == 0:
        return {
            "events_count": 0, "stats": None, "events": [], "event_markers": [],
            "chart_dates": chart_dates, "chart_closes": chart_closes,
            "histogram": {"edges": [], "counts": []},
            "summary_text": f"近窗口**无** {EVENT_LABELS[event]} 发生，或所有事件距今不足 {forward_days} 日无法回测",
        }

    rets = [e["forward_return"] for e in events]
    avg = round(sum(rets) / n, 2)
    sv = sorted(rets)
    median = sv[n // 2] if n % 2 == 1 else round((sv[n // 2 - 1] + sv[n // 2]) / 2, 2)
    wins = sum(1 for r in rets if r > 0)
    win_rate = round(wins / n, 3)
    best = max(events, key=lambda e: e["forward_return"])
    worst = min(events, key=lambda e: e["forward_return"])

    def _chart_idx(date):
        for i, d in enumerate(chart_dates):
            if d >= date:
                return i
        return len(chart_dates) - 1

    event_markers = [{
        "date": e["date"], "chart_idx": _chart_idx(e["date"]),
        "entry_close": e["entry_close"], "exit_close": e["exit_close"],
        "forward_return": e["forward_return"],
    } for e in events]

    recent_str = ", ".join(f"{e['date']}({e['forward_return']:+.2f}%)" for e in events[-3:])
    summary_text = (
        f"发生 {EVENT_LABELS[event]} {n} 次，随后 {forward_days} 日平均 {avg:+.2f}%，"
        f"中位数 {median:.2f}%，胜率 {win_rate*100:.1f}%；"
        f"最佳 {best['date']} {best['forward_return']:+.2f}%，"
        f"最差 {worst['date']} {worst['forward_return']:+.2f}%；"
        f"最近 3 次: {recent_str}"
    )

    return {
        "events_count": n,
        "stats": {
            "avg_forward_return": avg,
            "median_forward_return": median,
            "win_rate": win_rate,
            "best": {"date": best["date"], "return": best["forward_return"]},
            "worst": {"date": worst["date"], "return": worst["forward_return"]},
        },
        "events": events[-20:],
        "event_markers": event_markers,
        "chart_dates": chart_dates,
        "chart_closes": chart_closes,
        "histogram": _event_histogram(rets),
        "summary_text": summary_text,
    }


def _last(arr):
    for v in reversed(arr):
        if v is not None:
            return v
    return None


def _last_n(arr, n):
    vals = [v for v in arr if v is not None]
    return vals[-n:] if len(vals) >= n else vals


def build_signals(chart, ind):
    signals = []
    closes = chart["close"]
    last_close = closes[-1]
    ma5 = ind["ma5"]
    ma10 = ind["ma10"]
    ma20 = ind["ma20"]
    v_ma5 = _last(ma5)
    v_ma10 = _last(ma10)
    v_ma20 = _last(ma20)

    # MA趋势
    if v_ma5 and v_ma10 and v_ma20:
        if v_ma5 > v_ma10 > v_ma20:
            signals.append({"name": "MA趋势", "signal": "bullish",
                            "detail": f"MA5({v_ma5:.0f})>MA10({v_ma10:.0f})>MA20({v_ma20:.0f}) 多头排列"})
        elif v_ma5 < v_ma10 < v_ma20:
            signals.append({"name": "MA趋势", "signal": "bearish",
                            "detail": f"MA5({v_ma5:.0f})<MA10({v_ma10:.0f})<MA20({v_ma20:.0f}) 空头排列"})
        else:
            signals.append({"name": "MA趋势", "signal": "neutral",
                            "detail": f"MA5({v_ma5:.0f}) MA10({v_ma10:.0f}) MA20({v_ma20:.0f}) 均线交织"})

    # MACD
    dif_val = _last(ind["dif"])
    dea_val = _last(ind["dea"])
    hist_val = _last(ind["hist"])
    if dif_val is not None and dea_val is not None:
        if dif_val > dea_val and hist_val and hist_val > 0:
            signals.append({"name": "MACD", "signal": "bullish",
                            "detail": f"DIF({dif_val:.2f})>DEA({dea_val:.2f}) 金叉放量"})
        elif dif_val < dea_val and hist_val and hist_val < 0:
            signals.append({"name": "MACD", "signal": "bearish",
                            "detail": f"DIF({dif_val:.2f})<DEA({dea_val:.2f}) 死叉放量"})
        else:
            signals.append({"name": "MACD", "signal": "neutral",
                            "detail": f"DIF({dif_val:.2f}) DEA({dea_val:.2f}) 信号不明"})

    # RSI
    rsi_val = _last(ind["rsi"])
    if rsi_val is not None:
        if rsi_val >= RSI_OVERBOUGHT:
            signals.append({"name": "RSI", "signal": "bearish",
                            "detail": f"RSI={rsi_val:.1f} 超买区间(>{RSI_OVERBOUGHT})"})
        elif rsi_val <= RSI_OVERSOLD:
            signals.append({"name": "RSI", "signal": "bullish",
                            "detail": f"RSI={rsi_val:.1f} 超卖区间(<{RSI_OVERSOLD})"})
        else:
            signals.append({"name": "RSI", "signal": "neutral",
                            "detail": f"RSI={rsi_val:.1f} 中性区间"})

    # KDJ
    k_val = _last(ind["k"])
    d_val = _last(ind["d"])
    j_val = _last(ind["j"])
    if k_val is not None and d_val is not None:
        if k_val > d_val and j_val and j_val > KDJ_OVERBOUGHT:
            signals.append({"name": "KDJ", "signal": "bearish",
                            "detail": f"K({k_val:.1f}) D({d_val:.1f}) J({j_val:.1f}) 高位超买"})
        elif k_val > d_val and (j_val is None or j_val <= KDJ_OVERBOUGHT):
            signals.append({"name": "KDJ", "signal": "bullish",
                            "detail": f"K({k_val:.1f})>D({d_val:.1f}) 金叉"})
        elif k_val < d_val and j_val and j_val < KDJ_OVERSOLD:
            signals.append({"name": "KDJ", "signal": "bullish",
                            "detail": f"K({k_val:.1f}) D({d_val:.1f}) J({j_val:.1f}) 低位超卖"})
        elif k_val < d_val:
            signals.append({"name": "KDJ", "signal": "bearish",
                            "detail": f"K({k_val:.1f})<D({d_val:.1f}) 死叉"})
        else:
            signals.append({"name": "KDJ", "signal": "neutral",
                            "detail": f"K({k_val:.1f}) D({d_val:.1f}) J({j_val:.1f}) 震荡"})

    # BOLL
    boll_mid = _last(ind["boll_mid"])
    boll_up = _last(ind["boll_up"])
    boll_low = _last(ind["boll_low"])
    if boll_mid and boll_up and boll_low:
        if last_close > boll_up:
            signals.append({"name": "BOLL", "signal": "bearish",
                            "detail": f"价格({last_close:.0f})突破上轨({boll_up:.0f}) 超买"})
        elif last_close < boll_low:
            signals.append({"name": "BOLL", "signal": "bullish",
                            "detail": f"价格({last_close:.0f})跌破下轨({boll_low:.0f}) 超卖"})
        elif last_close > boll_mid:
            signals.append({"name": "BOLL", "signal": "bullish",
                            "detail": f"价格({last_close:.0f})位于中轨({boll_mid:.0f})上方"})
        else:
            signals.append({"name": "BOLL", "signal": "bearish",
                            "detail": f"价格({last_close:.0f})位于中轨({boll_mid:.0f})下方"})

    # CCI
    cci_val = _last(ind["cci"])
    if cci_val is not None:
        if cci_val > CCI_STRONG:
            signals.append({"name": "CCI", "signal": "bullish",
                            "detail": f"CCI={cci_val:.1f} 强势区间(>+{CCI_STRONG})"})
        elif cci_val < CCI_WEAK:
            signals.append({"name": "CCI", "signal": "bearish",
                            "detail": f"CCI={cci_val:.1f} 弱势区间(<{CCI_WEAK})"})
        else:
            signals.append({"name": "CCI", "signal": "neutral",
                            "detail": f"CCI={cci_val:.1f} 中性震荡"})

    # ATR volatility trend
    atr_vals = _last_n(ind["atr"], 10)
    if len(atr_vals) >= 5:
        recent_avg = sum(atr_vals[-3:]) / 3
        prev_avg = sum(atr_vals[:3]) / 3
        if recent_avg > prev_avg * 1.1:
            signals.append({"name": "ATR", "signal": "neutral",
                            "detail": f"ATR={atr_vals[-1]:.1f} 波动率上升 风险加大"})
        elif recent_avg < prev_avg * 0.9:
            signals.append({"name": "ATR", "signal": "neutral",
                            "detail": f"ATR={atr_vals[-1]:.1f} 波动率收窄 蓄势待变"})
        else:
            signals.append({"name": "ATR", "signal": "neutral",
                            "detail": f"ATR={atr_vals[-1]:.1f} 波动率平稳"})

    # OBV direction
    obv_vals = _last_n(ind["obv"], 10)
    if len(obv_vals) >= 5:
        if obv_vals[-1] > obv_vals[-5]:
            signals.append({"name": "OBV", "signal": "bullish",
                            "detail": f"OBV趋势向上 资金持续流入"})
        elif obv_vals[-1] < obv_vals[-5]:
            signals.append({"name": "OBV", "signal": "bearish",
                            "detail": f"OBV趋势向下 资金持续流出"})
        else:
            signals.append({"name": "OBV", "signal": "neutral",
                            "detail": f"OBV走平 资金观望"})

    # 量价关系
    volumes = chart["volumes"]
    if len(closes) >= 2 and len(volumes) >= 2:
        price_chg = closes[-1] - closes[-2]
        vol_chg = volumes[-1] - volumes[-2]
        if price_chg > 0 and vol_chg > 0:
            signals.append({"name": "量价关系", "signal": "bullish",
                            "detail": "价涨量增 多头确认"})
        elif price_chg > 0 and vol_chg < 0:
            signals.append({"name": "量价关系", "signal": "neutral",
                            "detail": "价涨量缩 上涨动力不足"})
        elif price_chg < 0 and vol_chg > 0:
            signals.append({"name": "量价关系", "signal": "bearish",
                            "detail": "价跌量增 空头放量"})
        elif price_chg < 0 and vol_chg < 0:
            signals.append({"name": "量价关系", "signal": "neutral",
                            "detail": "价跌量缩 抛压减轻"})
        else:
            signals.append({"name": "量价关系", "signal": "neutral",
                            "detail": "量价变化不明显"})

    return signals


def compute_score(signals):
    score_map = {"bullish": 10, "neutral": 5, "bearish": 0}
    total = sum(score_map.get(s["signal"], 5) for s in signals)
    n = len(signals) or 1
    return round(total / n / 10 * 100)


def compute_levels(chart, ind):
    closes = chart["close"]
    highs = chart["high"]
    lows = chart["low"]
    last_close = closes[-1]

    candidates_support = []
    candidates_resist = []

    boll_low = _last(ind["boll_low"])
    boll_up = _last(ind["boll_up"])
    boll_mid = _last(ind["boll_mid"])
    ma20_val = _last(ind["ma20"])

    if boll_low and boll_low < last_close:
        candidates_support.append(round(boll_low, 2))
    if ma20_val and ma20_val < last_close:
        candidates_support.append(round(ma20_val, 2))
    if boll_up and boll_up > last_close:
        candidates_resist.append(round(boll_up, 2))
    if boll_mid and boll_mid > last_close:
        candidates_resist.append(round(boll_mid, 2))

    n = min(20, len(lows))
    recent_low = min(lows[-n:])
    recent_high = max(highs[-n:])
    if recent_low < last_close:
        candidates_support.append(round(recent_low, 2))
    if recent_high > last_close:
        candidates_resist.append(round(recent_high, 2))

    support = sorted(set(candidates_support), reverse=True)[:2]
    resistance = sorted(set(candidates_resist))[:2]
    return support, resistance


def main():
    parser = argparse.ArgumentParser(description="SW_TECH: Technical diagnosis")
    parser.add_argument("--code", required=True, help="6-digit index code")
    parser.add_argument("--name", default="", help="Index display name")
    parser.add_argument("--period", default="DAY", choices=["DAY", "WEEK", "MONTH"])
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--event", default=None, choices=list(EVENT_LABELS.keys()),
                        help="追加历史事件后验（如 macd_golden = MACD 金叉后 N 日收益统计）")
    parser.add_argument("--forward-days", type=int, default=20,
                        help="事件后观测 N 日收益率（默认 20，仅 --event 时生效）")
    args = parser.parse_args()

    display_name = get_index_display_name(args.code, args.name or args.code)
    identifier = f"sw-tech-{args.code}"
    title = f"{display_name} 技术面诊断"
    if args.event:
        title += f" + {EVENT_LABELS[args.event]}后{args.forward_days}日回测"

    emit_artifact(TEMPLATE, identifier, title, {"loading": True})
    emit_phase(TEMPLATE, identifier, title, "meta", {},
               meta={"name": display_name, "code": args.code, "period": args.period})

    try:
        # 事件回测需要更长历史窗口（原 event_stats 默认 750 ≈ 3 年）
        fetch_days = max(args.days, 500) if args.event else args.days
        chart, meta = fetch_kline(args.code, args.period, fetch_days)
    except Exception as e:
        emit_error(TEMPLATE, identifier, title, f"获取K线数据失败: {e}")
        print(json.dumps({"status": "error", "message": str(e)}), ensure_ascii=False)
        sys.exit(1)

    closes = chart["close"]
    highs = chart["high"]
    lows = chart["low"]
    volumes = chart["volumes"]

    dif_arr, dea_arr, hist_arr = macd(closes)
    rsi_arr = rsi(closes, 14)
    k_arr, d_arr, j_arr = kdj(highs, lows, closes)
    boll_mid, boll_up, boll_low = boll(closes)
    cci_arr = cci(highs, lows, closes)
    atr_arr = atr(highs, lows, closes)
    obv_arr = obv(closes, volumes)
    di_p, di_m, adx_arr = adx(highs, lows, closes)
    ma5 = ma(closes, 5)
    ma10 = ma(closes, 10)
    ma20 = ma(closes, 20)

    ind = {
        "dif": dif_arr, "dea": dea_arr, "hist": hist_arr,
        "rsi": rsi_arr, "k": k_arr, "d": d_arr, "j": j_arr,
        "boll_mid": boll_mid, "boll_up": boll_up, "boll_low": boll_low,
        "cci": cci_arr, "atr": atr_arr, "obv": obv_arr,
        "di_plus": di_p, "di_minus": di_m, "adx": adx_arr,
        "ma5": ma5, "ma10": ma10, "ma20": ma20,
    }

    signals = build_signals(chart, ind)
    score = compute_score(signals)
    support, resistance = compute_levels(chart, ind)

    meta["name"] = get_index_display_name(args.code, meta.get("name") or display_name)
    meta["code"] = args.code
    meta["period"] = args.period
    meta["date"] = chart["labels"][-1] if chart["labels"] else ""

    data_dict = {
        "kline": {
            "labels": chart["labels"],
            "open": chart["open"],
            "high": highs,
            "low": lows,
            "close": closes,
            "volumes": volumes,
            "ma5": ma5,
            "ma10": ma10,
            "ma20": ma20,
        },
        "boll": {"mid": boll_mid, "upper": boll_up, "lower": boll_low},
        "macd": {"dif": dif_arr, "dea": dea_arr, "hist": hist_arr},
        "rsi": rsi_arr,
        "kdj": {"k": k_arr, "d": d_arr, "j": j_arr},
        "cci": cci_arr,
        "atr": atr_arr,
        "obv": obv_arr,
        "adx": {"di_plus": di_p, "di_minus": di_m, "adx": adx_arr},
        "signals": signals,
        "score": score,
        "support": support,
        "resistance": resistance,
    }

    # ── 事件后验（--event 时追加）──
    event_block = {}
    if args.event:
        event_block = compute_event_stats(args.event, chart, args.forward_days)
        event_block["event"] = args.event
        event_block["event_label"] = EVENT_LABELS[args.event]
        event_block["forward_days"] = args.forward_days
        data_dict.update(event_block)

    emit_phase(TEMPLATE, identifier, title, "data", data_dict, meta=meta)

    # LLM analysis
    sig_parts = "; ".join(
        f"{s['name']}={s['signal']}({s['detail']})" for s in signals
    )
    summary_text = (
        f"指数: {meta['name']}({args.code}), 周期: {args.period}, "
        f"最新收盘: {closes[-1]:.2f}, "
        f"技术信号: {sig_parts}, 综合评分: {score}/100, "
        "颜色口径: 多头/偏强用红色, 空头/偏弱用绿色, 中性用灰色, "
        f"支撑位: {support}, 阻力位: {resistance}"
    )
    if event_block:
        summary_text += "\n" + event_block.get("summary_text", "")
    analysis = call_analysis_llm(summary_text, "技术面诊断")

    emit_phase(TEMPLATE, identifier, title, "final", data_dict, meta=meta,
               analysis=analysis)

    out = {
        "status": "ok",
        "code": args.code,
        "name": meta["name"],
        "period": args.period,
        "bars": len(closes),
        "range": f"{chart['labels'][0]}~{chart['labels'][-1]}",
        "latest_close": closes[-1],
        "score": score,
        "bullish": sum(1 for s in signals if s["signal"] == "bullish"),
        "bearish": sum(1 for s in signals if s["signal"] == "bearish"),
        "neutral": sum(1 for s in signals if s["signal"] == "neutral"),
        "support": support,
        "resistance": resistance,
        "summary_text": summary_text,
    }
    if event_block:
        out["event"] = event_block.get("event")
        out["event_label"] = event_block.get("event_label")
        out["events_count"] = event_block.get("events_count", 0)
        out["event_stats"] = event_block.get("stats")
        out["event_summary"] = event_block.get("summary_text", "")
    print(json.dumps(attach_render(out), ensure_ascii=False))


if __name__ == "__main__":
    main()
