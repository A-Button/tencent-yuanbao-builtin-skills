#!/usr/bin/env python3
"""Deep analysis report for a single SW index.

Usage:
  python sw_deep.py --code 801001 --name "申万50"
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
    emit_artifact, emit_progress, emit_error, emit_phase,
    fetch_realtime_one, fetch_kline_one, fetch_risk_return_one,
    fetch_fundamentals_batch,
    fetch_component_stocks, fetch_industry_distribution,
    call_analysis_llm, _float,
    is_style_broad, is_jc, get_index_display_name,
    RSI_OVERBOUGHT, RSI_OVERSOLD,
    KDJ_OVERBOUGHT, KDJ_OVERSOLD,
    CCI_STRONG, CCI_WEAK,
    ATR_EXPAND_RATIO, ATR_SHRINK_RATIO,
)
from indicators import compute  # noqa: E402

TEMPLATE = "SW_DEEP"
TOTAL_STEPS = 8


def _lookup_fundamentals(code: str) -> dict:
    """Find PE/PB/股息率/换手率/流通市值 for a single index.

    Uses /day_week_month_report/ batch endpoint (1 request returns all
    indices of the category), scans for the target code client-side.
    Returns empty dict if not found / API failure (non-fatal).
    """
    # Determine category — try 一级行业 first (covers 801010–801980 range),
    # fall back to 市场表征 / 风格指数 / 二级行业.
    for indextype in ("一级行业", "市场表征", "二级行业", "风格指数"):
        rows = fetch_fundamentals_batch(indextype)
        for r in rows:
            if r.get("code") == code:
                return r
    return {}


def _last_valid(arr):
    """Return last non-None value from a list."""
    for v in reversed(arr or []):
        if v is not None:
            return v
    return None


def _avg_valid(arr, tail=20):
    """Average of last *tail* non-None values."""
    vals = [v for v in (arr or [])[-tail:] if v is not None]
    return sum(vals) / len(vals) if vals else None


def compute_signals(ind, closes, volumes):
    """Derive directional signals from indicator data."""
    signals = []

    # --- MA trend ---
    ma5 = _last_valid(ind.get("ma5"))
    ma10 = _last_valid(ind.get("ma10"))
    ma20 = _last_valid(ind.get("ma20"))
    if ma5 is not None and ma10 is not None and ma20 is not None:
        if ma5 > ma10 > ma20:
            signals.append({"name": "均线排列", "signal": "bullish", "detail": "MA5>MA10>MA20 多头排列"})
        elif ma5 < ma10 < ma20:
            signals.append({"name": "均线排列", "signal": "bearish", "detail": "MA5<MA10<MA20 空头排列"})
        else:
            signals.append({"name": "均线排列", "signal": "neutral", "detail": "均线交织，方向不明"})

    # --- MACD ---
    dif = _last_valid(ind.get("dif"))
    dea = _last_valid(ind.get("dea"))
    if dif is not None and dea is not None:
        if dif > dea:
            signals.append({"name": "MACD", "signal": "bullish", "detail": f"DIF({dif:.2f})>DEA({dea:.2f}) 金叉状态"})
        else:
            signals.append({"name": "MACD", "signal": "bearish", "detail": f"DIF({dif:.2f})<DEA({dea:.2f}) 死叉状态"})

    # --- RSI ---
    rsi_val = _last_valid(ind.get("rsi"))
    if rsi_val is not None:
        if rsi_val > RSI_OVERBOUGHT:
            signals.append({"name": "RSI", "signal": "bearish", "detail": f"RSI={rsi_val:.1f} 超买区间"})
        elif rsi_val < RSI_OVERSOLD:
            signals.append({"name": "RSI", "signal": "bullish", "detail": f"RSI={rsi_val:.1f} 超卖区间"})
        else:
            signals.append({"name": "RSI", "signal": "neutral", "detail": f"RSI={rsi_val:.1f} 中性区间"})

    # --- KDJ ---
    k_val = _last_valid(ind.get("k"))
    d_val = _last_valid(ind.get("d"))
    if k_val is not None and d_val is not None:
        if k_val > KDJ_OVERBOUGHT:
            signals.append({"name": "KDJ", "signal": "bearish", "detail": f"K={k_val:.1f} 超买区间"})
        elif k_val < KDJ_OVERSOLD:
            signals.append({"name": "KDJ", "signal": "bullish", "detail": f"K={k_val:.1f} 超卖区间"})
        elif k_val > d_val:
            signals.append({"name": "KDJ", "signal": "bullish", "detail": f"K({k_val:.1f})>D({d_val:.1f}) 金叉"})
        else:
            signals.append({"name": "KDJ", "signal": "bearish", "detail": f"K({k_val:.1f})<D({d_val:.1f}) 死叉"})

    # --- BOLL ---
    boll_up = _last_valid(ind.get("boll_up"))
    boll_mid = _last_valid(ind.get("boll_mid"))
    boll_low = _last_valid(ind.get("boll_low"))
    price = closes[-1] if closes else None
    if price is not None and boll_up is not None and boll_mid is not None and boll_low is not None:
        if price > boll_up:
            signals.append({"name": "BOLL", "signal": "bearish", "detail": f"价格({price:.2f})突破上轨({boll_up:.2f})，超买"})
        elif price < boll_low:
            signals.append({"name": "BOLL", "signal": "bullish", "detail": f"价格({price:.2f})跌破下轨({boll_low:.2f})，超卖"})
        elif price > boll_mid:
            signals.append({"name": "BOLL", "signal": "bullish", "detail": f"价格在中轨上方，偏强势"})
        else:
            signals.append({"name": "BOLL", "signal": "bearish", "detail": f"价格在中轨下方，偏弱势"})

    # --- CCI ---
    cci_val = _last_valid(ind.get("cci"))
    if cci_val is not None:
        if cci_val > CCI_STRONG:
            signals.append({"name": "CCI", "signal": "bullish", "detail": f"CCI={cci_val:.1f} 强势区间"})
        elif cci_val < CCI_WEAK:
            signals.append({"name": "CCI", "signal": "bearish", "detail": f"CCI={cci_val:.1f} 弱势区间"})
        else:
            signals.append({"name": "CCI", "signal": "neutral", "detail": f"CCI={cci_val:.1f} 震荡区间"})

    # --- ATR ---
    atr_val = _last_valid(ind.get("atr"))
    atr_avg = _avg_valid(ind.get("atr"))
    if atr_val is not None and atr_avg is not None:
        if atr_val > atr_avg * ATR_EXPAND_RATIO:
            signals.append({"name": "ATR", "signal": "neutral", "detail": f"ATR={atr_val:.2f} 波动放大，高于均值"})
        elif atr_val < atr_avg * ATR_SHRINK_RATIO:
            signals.append({"name": "ATR", "signal": "neutral", "detail": f"ATR={atr_val:.2f} 波动收窄，低于均值"})
        else:
            signals.append({"name": "ATR", "signal": "neutral", "detail": f"ATR={atr_val:.2f} 波动平稳"})

    # --- OBV ---
    obv_arr = ind.get("obv") or []
    obv_recent = [v for v in obv_arr[-10:] if v is not None]
    if len(obv_recent) >= 5:
        if obv_recent[-1] > obv_recent[0]:
            signals.append({"name": "OBV", "signal": "bullish", "detail": "OBV趋势上升，资金持续流入"})
        else:
            signals.append({"name": "OBV", "signal": "bearish", "detail": "OBV趋势下降，资金持续流出"})

    # --- Volume-Price ---
    if len(closes) >= 2 and volumes and len(volumes) >= 2:
        p_chg = closes[-1] - closes[-2]
        v_last = volumes[-1] if volumes[-1] is not None else 0
        v_prev = volumes[-2] if volumes[-2] is not None else 0
        v_chg = v_last - v_prev
        if p_chg > 0 and v_chg > 0:
            signals.append({"name": "量价", "signal": "bullish", "detail": "价涨量增，走势健康"})
        elif p_chg > 0 and v_chg <= 0:
            signals.append({"name": "量价", "signal": "neutral", "detail": "价涨量缩，上攻乏力"})
        elif p_chg < 0 and v_chg > 0:
            signals.append({"name": "量价", "signal": "bearish", "detail": "价跌量增，抛压较大"})
        else:
            signals.append({"name": "量价", "signal": "neutral", "detail": "价跌量缩，下跌动能减弱"})

    # Score
    score_map = {"bullish": 2, "neutral": 1, "bearish": 0}
    total = sum(score_map.get(s["signal"], 1) for s in signals)
    max_score = len(signals) * 2 if signals else 1
    score = round(total / max_score * 100)

    return signals, score


def compute_support_resistance(ind, closes):
    """Derive support/resistance from BOLL and recent highs/lows."""
    support = []
    resistance = []

    boll_low = _last_valid(ind.get("boll_low"))
    boll_up = _last_valid(ind.get("boll_up"))
    if boll_low is not None:
        support.append(round(boll_low, 2))
    if boll_up is not None:
        resistance.append(round(boll_up, 2))

    recent = closes[-20:] if len(closes) >= 20 else closes
    if recent:
        support.append(round(min(recent), 2))
        resistance.append(round(max(recent), 2))

    support.sort()
    resistance.sort()
    return support[:2], resistance[:2]


def main():
    parser = argparse.ArgumentParser(description="SW index deep analysis report")
    parser.add_argument("--code", required=True, help="6-digit Shenwan index code")
    parser.add_argument("--name", default="", help="Index display name")
    parser.add_argument("--days", type=int, default=120, help="K-line lookback days (default 120, min 60)")
    args = parser.parse_args()

    code = args.code
    name = get_index_display_name(code, args.name or code)
    days = max(args.days, 60)
    identifier = f"sw-deep-{code}-{days}d" if days != 120 else f"sw-deep-{code}"
    title = f"{name} 深度分析报告" + (f" · {days}日" if days != 120 else "")

    emit_artifact(TEMPLATE, identifier, title, {"loading": True})
    emit_phase(TEMPLATE, identifier, title, "meta", {},
               meta={"name": name, "code": code})

    try:
        no_realtime_api = is_style_broad(code) or is_jc(code)
        if no_realtime_api:
            emit_progress(TEMPLATE, identifier, title, 1, TOTAL_STEPS, "正在准备行情快照")
            realtime = {}
        else:
            emit_progress(TEMPLATE, identifier, title, 1, TOTAL_STEPS, "正在获取实时行情")
            realtime = fetch_realtime_one(code)
            if not realtime:
                raise ValueError("无法获取实时行情数据")

        # Step 2: K-line
        emit_progress(TEMPLATE, identifier, title, 2, TOTAL_STEPS, "正在获取K线数据")
        kline_raw = fetch_kline_one(code, "DAY", days)
        if not kline_raw:
            raise ValueError("无法获取K线数据")

        labels = [r["bargaindate"][:10] for r in kline_raw]
        opens = [float(r["openindex"]) for r in kline_raw]
        highs = [float(r["maxindex"]) for r in kline_raw]
        lows = [float(r["minindex"]) for r in kline_raw]
        closes = [float(r["closeindex"]) for r in kline_raw]
        volumes = [round(float(r.get("bargainamount", 0)), 4) for r in kline_raw]

        if not realtime:
            prev_close = closes[-2] if len(closes) >= 2 else closes[-1]
            latest = closes[-1]
            chg = latest - prev_close
            realtime = {
                "code": code, "name": name,
                "latest": latest, "prev_close": prev_close,
                "change": round(chg, 2),
                "change_pct": round(chg / prev_close * 100, 2) if prev_close else 0,
                "open": opens[-1], "high": highs[-1], "low": lows[-1],
                "amount": 0, "volume": 0,
                "time": "", "date": labels[-1],
            }

        from indicators import ma  # noqa: E402
        ma5 = ma(closes, 5)
        ma10 = ma(closes, 10)
        ma20 = ma(closes, 20)

        kline_data = {
            "labels": labels, "open": opens, "high": highs,
            "low": lows, "close": closes, "volumes": volumes,
            "ma5": ma5, "ma10": ma10, "ma20": ma20,
        }

        # Step 3: Risk/Return
        emit_progress(TEMPLATE, identifier, title, 3, TOTAL_STEPS, "正在获取收益风险数据")
        risk_return = fetch_risk_return_one(code) or {}

        # Step 4: Component stocks
        emit_progress(TEMPLATE, identifier, title, 4, TOTAL_STEPS, "正在获取成分股数据")
        all_components = fetch_component_stocks(code)
        sorted_comp = sorted(all_components, key=lambda x: float(x.get("newWeight", 0)), reverse=True)
        top10 = [
            {"stockName": c.get("stockName", ""), "stockCode": c.get("stockCode", ""), "newWeight": _float(c.get("newWeight"))}
            for c in sorted_comp[:10]
        ]

        # Step 5: Industry distribution
        emit_progress(TEMPLATE, identifier, title, 5, TOTAL_STEPS, "正在获取行业分布数据")
        industry_dist = fetch_industry_distribution(code)
        industry_data = [
            {"industryTypeName": d.get("industryName", "") or d.get("industryTypeName", ""), "newWeight": _float(d.get("newWeight"))}
            for d in industry_dist
        ]

        # Step 6: Fundamental metrics (PE/PB/股息率/换手率/流通市值)
        emit_progress(TEMPLATE, identifier, title, 6, TOTAL_STEPS, "正在获取估值数据")
        fundamentals = _lookup_fundamentals(code)

        # Step 7: Technical indicators
        emit_progress(TEMPLATE, identifier, title, 7, TOTAL_STEPS, "正在计算技术指标")
        ind_input = {"close": closes, "high": highs, "low": lows, "open": opens, "volumes": volumes}
        ind_result = compute(ind_input, ["macd", "rsi", "kdj", "boll", "cci", "atr", "obv"])
        ind_result["ma5"] = ma5
        ind_result["ma10"] = ma10
        ind_result["ma20"] = ma20

        signals, score = compute_signals(ind_result, closes, volumes)
        support, resistance = compute_support_resistance(ind_result, closes)

        # Step 8: LLM analysis
        emit_progress(TEMPLATE, identifier, title, 8, TOTAL_STEPS, "正在生成深度分析")
        bull_count = sum(1 for s in signals if s["signal"] == "bullish")
        neut_count = sum(1 for s in signals if s["signal"] == "neutral")
        bear_count = sum(1 for s in signals if s["signal"] == "bearish")
        signal_summary = f"{bull_count}多/{neut_count}中/{bear_count}空"

        data_dict = {
            "realtime": realtime,
            "kline": kline_data,
            "riskReturn": risk_return,
            "fundamentals": fundamentals,
            "components": top10,
            "componentCount": len(all_components),
            "industryDist": industry_data,
            "signals": signals,
            "score": score,
            "support": support,
            "resistance": resistance,
        }
        meta_dict = {"name": name, "code": code, "date": realtime.get("date", "")}

        emit_phase(TEMPLATE, identifier, title, "data", data_dict, meta=meta_dict)

        valuation_line = ""
        if fundamentals:
            pe_s = f"{fundamentals.get('pe'):.2f}" if fundamentals.get("pe") is not None else "—"
            pb_s = f"{fundamentals.get('pb'):.2f}" if fundamentals.get("pb") is not None else "—"
            dp_s = f"{fundamentals.get('dp'):.2f}%" if fundamentals.get("dp") is not None else "—"
            to_s = f"{fundamentals.get('turnover'):.2f}%" if fundamentals.get("turnover") is not None else "—"
            mc_s = f"{fundamentals.get('circ_mcap'):.0f}亿元" if fundamentals.get("circ_mcap") is not None else "—"
            valuation_line = (
                f"估值: PE {pe_s}, PB {pb_s}, 股息率 {dp_s}, "
                f"换手率 {to_s}, 流通市值 {mc_s}\n"
            )

        llm_input = (
            f"指数: {name}({code})\n"
            f"最新价: {realtime['latest']}, 涨跌幅: {realtime['change_pct']}%\n"
            f"{valuation_line}"
            f"技术信号综合评分: {score}/100 ({signal_summary})\n"
            f"信号详情: {'; '.join(s['name']+'='+s['signal']+': '+s['detail'] for s in signals)}\n"
            f"支撑位: {support}, 压力位: {resistance}\n"
            f"1月收益: {risk_return.get('m1_return')}%, 3月收益: {risk_return.get('m3_return')}%, "
            f"年初至今: {risk_return.get('ytd_return')}%, 1年收益: {risk_return.get('y1_return')}%\n"
            f"1年波动率: {risk_return.get('y1_vol')}%, 3年波动率: {risk_return.get('y3_vol')}%\n"
            f"成分股数量: {len(all_components)}, 前三大权重: "
            f"{', '.join(c['stockName']+'('+str(c['newWeight'])+'%)' for c in top10[:3])}\n"
            f"行业分布前三: {', '.join(d['industryTypeName']+'('+str(d['newWeight'])+'%)' for d in industry_data[:3])}"
        )
        analysis = call_analysis_llm(llm_input, "指数深度分析")

        emit_phase(TEMPLATE, identifier, title, "final", data_dict, meta=meta_dict,
                   analysis=analysis)

        # JSON summary for agent
        print(json.dumps(attach_render({
            "status": "ok",
            "mode": "deep",
            "code": code,
            "name": name,
            "latest": realtime["latest"],
            "change_pct": realtime["change_pct"],
            "score": score,
            "signal_summary": signal_summary,
            "y1_return": risk_return.get("y1_return"),
            "y1_vol": risk_return.get("y1_vol"),
            "pe": fundamentals.get("pe"),
            "pb": fundamentals.get("pb"),
            "dp": fundamentals.get("dp"),
            "turnover": fundamentals.get("turnover"),
            "circ_mcap": fundamentals.get("circ_mcap"),
            "summary_text": llm_input,
        }), ensure_ascii=False))

    except Exception as e:
        emit_error(TEMPLATE, identifier, title, str(e))
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
