#!/usr/bin/env python3
"""Compute technical indicators from K-line data."""

from __future__ import annotations

import json
import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)


# ── Trend Indicators ──

def ma(series: list, n: int) -> list:
    result = [None] * (n - 1)
    for i in range(n - 1, len(series)):
        result.append(round(sum(series[i - n + 1 : i + 1]) / n, 4))
    return result


def ema(series: list, n: int) -> list:
    k = 2.0 / (n + 1)
    result = [None] * (n - 1)
    result.append(sum(series[:n]) / n)
    for i in range(n, len(series)):
        result.append(round(series[i] * k + result[-1] * (1 - k), 4))
    return result


def macd(prices: list, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple:
    e_fast = ema(prices, fast)
    e_slow = ema(prices, slow)
    dif = [
        round(a - b, 4) if a is not None and b is not None else None
        for a, b in zip(e_fast, e_slow)
    ]
    first = next(i for i, v in enumerate(dif) if v is not None)
    k = 2.0 / (signal + 1)
    dea = [None] * len(dif)
    dea[first + signal - 1] = round(sum(dif[first : first + signal]) / signal, 4)
    for i in range(first + signal, len(dif)):
        dea[i] = round(dif[i] * k + dea[i - 1] * (1 - k), 4)
    hist = [
        round(2 * (dif[i] - dea[i]), 4) if dif[i] is not None and dea[i] is not None else None
        for i in range(len(dif))
    ]
    return dif, dea, hist


def adx(highs: list, lows: list, closes: list, period: int = 14) -> tuple:
    tr_list, dm_plus, dm_minus = [], [], []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        up = highs[i] - highs[i - 1]
        dn = lows[i - 1] - lows[i]
        dm_p = max(up, 0) if up > dn else 0
        dm_m = max(dn, 0) if dn > up else 0
        tr_list.append(tr)
        dm_plus.append(dm_p)
        dm_minus.append(dm_m)

    di_plus = ema([a / b * 100 if b != 0 else 0 for a, b in zip(dm_plus, tr_list)], period)
    di_minus = ema([a / b * 100 if b != 0 else 0 for a, b in zip(dm_minus, tr_list)], period)
    dx = [
        round(abs(a - b) / (a + b) * 100, 4) if a is not None and b is not None and (a + b) != 0 else 0
        for a, b in zip(di_plus, di_minus)
    ]
    adx_val = ema(dx, period * 2)
    return di_plus, di_minus, adx_val


# ── Momentum Indicators ──

def kdj(highs: list, lows: list, closes: list, period: int = 9) -> tuple:
    n = len(closes)
    k_arr = [None] * n
    d_arr = [None] * n
    for i in range(period - 1, n):
        hh = max(highs[i - period + 1 : i + 1])
        ll = min(lows[i - period + 1 : i + 1])
        rsv = (closes[i] - ll) / (hh - ll) * 100 if hh != ll else 50
        k_val = 50 if i == period - 1 else k_arr[i - 1] * 2 / 3 + rsv * 1 / 3
        d_val = 50 if i == period - 1 else d_arr[i - 1] * 2 / 3 + k_val * 1 / 3
        k_arr[i] = round(k_val, 4)
        d_arr[i] = round(d_val, 4)
    j_arr = [
        round(3 * k_arr[i] - 2 * d_arr[i], 4) if k_arr[i] is not None and d_arr[i] is not None else None
        for i in range(n)
    ]
    return k_arr, d_arr, j_arr


def rsi(prices: list, period: int = 14) -> list:
    gains = []
    losses = []
    for i in range(1, len(prices)):
        d = prices[i] - prices[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))

    if len(gains) < period:
        return [None] * len(prices)

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    result = [None] * period
    rs = avg_gain / avg_loss if avg_loss != 0 else 100
    result.append(round(100 - 100 / (1 + rs), 4))

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rs = avg_gain / avg_loss if avg_loss != 0 else 100
        result.append(round(100 - 100 / (1 + rs), 4))
    return result


def cci(highs: list, lows: list, closes: list, period: int = 14) -> list:
    tp = [(h + l + c) / 3 for h, l, c in zip(highs, lows, closes)]
    result = []
    for i in range(period - 1, len(tp)):
        sma_val = sum(tp[i - period + 1 : i + 1]) / period
        mad = sum(abs(t - sma_val) for t in tp[i - period + 1 : i + 1]) / period
        result.append(round((tp[i] - sma_val) / (0.015 * mad), 4) if mad != 0 else 0)
    return [None] * (period - 1) + result


# ── Volatility Indicators ──

def boll(closes: list, period: int = 20, k: int = 2) -> tuple:
    mid, upper, lower = [], [], []
    for i in range(len(closes)):
        if i < period - 1:
            mid.append(None)
            upper.append(None)
            lower.append(None)
        else:
            seg = closes[i - period + 1 : i + 1]
            sma_val = sum(seg) / period
            std = (sum((x - sma_val) ** 2 for x in seg) / period) ** 0.5
            mid.append(round(sma_val, 4))
            upper.append(round(sma_val + k * std, 4))
            lower.append(round(sma_val - k * std, 4))
    return mid, upper, lower


def atr(highs: list, lows: list, closes: list, period: int = 14) -> list:
    tr = [
        max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        for i in range(1, len(closes))
    ]
    result = [None]
    if len(tr) >= period:
        result.append(round(sum(tr[:period]) / period, 4))
        for i in range(period, len(tr)):
            result.append(round((result[-1] * (period - 1) + tr[i]) / period, 4))
    return result


# ── Volume Indicators ──

def obv(closes: list, volumes: list) -> list:
    result = [0.0]
    for i in range(1, len(closes)):
        val = result[-1] + (volumes[i] if closes[i] >= closes[i - 1] else -volumes[i])
        result.append(round(val, 4))
    return result


# ── Dispatcher ──

SUPPORTED = {
    "ma5", "ma10", "ma20", "ma60",
    "ema12", "ema26",
    "macd", "kdj", "rsi", "cci",
    "boll", "atr", "obv", "adx",
}


def compute(data: dict, indicators: list) -> dict:
    closes  = data["close"]
    highs   = data.get("high", closes)
    lows    = data.get("low", closes)
    opens   = data.get("open", closes)
    volumes = data.get("volumes", [0] * len(closes))

    out = {}
    for ind in indicators:
        ind = ind.strip().lower()
        if ind not in SUPPORTED:
            out[ind] = f"unsupported indicator: {ind}"
            continue

        if ind == "ma5":
            out["ma5"] = ma(closes, 5)
        elif ind == "ma10":
            out["ma10"] = ma(closes, 10)
        elif ind == "ma20":
            out["ma20"] = ma(closes, 20)
        elif ind == "ma60":
            out["ma60"] = ma(closes, 60)
        elif ind == "ema12":
            out["ema12"] = ema(closes, 12)
        elif ind == "ema26":
            out["ema26"] = ema(closes, 26)
        elif ind == "macd":
            dif, dea, hist = macd(closes)
            out["dif"] = dif
            out["dea"] = dea
            out["macd"] = hist
        elif ind == "kdj":
            k_arr, d_arr, j_arr = kdj(highs, lows, closes)
            out["k"] = k_arr
            out["d"] = d_arr
            out["j"] = j_arr
        elif ind == "rsi":
            out["rsi"] = rsi(closes)
        elif ind == "cci":
            out["cci"] = cci(highs, lows, closes)
        elif ind == "boll":
            m, u, l = boll(closes)
            out["boll_mid"] = m
            out["boll_up"] = u
            out["boll_low"] = l
        elif ind == "atr":
            out["atr"] = atr(highs, lows, closes)
        elif ind == "obv":
            out["obv"] = obv(closes, volumes)
        elif ind == "adx":
            di_p, di_m, adx_val = adx(highs, lows, closes)
            out["di_plus"] = di_p
            out["di_minus"] = di_m
            out["adx"] = adx_val

    return out


def main():
    parser = argparse.ArgumentParser(description="Compute technical indicators from K-line data")
    parser.add_argument("--input", required=True, help="Path to K-line JSON")
    parser.add_argument("--indicators", required=True,
                        help="Comma-separated list of indicators (e.g. macd,rsi,boll)")
    parser.add_argument("--output", required=True, help="Output path for indicator JSON")
    args = parser.parse_args()

    try:
        with open(args.input, "r", encoding="utf-8") as f:
            data = json.load(f)

        ind_list = [s.strip() for s in args.indicators.split(",") if s.strip()]
        unknown = [s for s in ind_list if s.lower() not in SUPPORTED]
        if unknown:
            print(json.dumps({
                "status": "warning",
                "message": f"Unsupported indicators will be skipped: {unknown}",
                "supported": sorted(SUPPORTED),
            }, ensure_ascii=False), file=sys.stderr)

        result = compute(data, ind_list)

        output_dir = os.path.dirname(os.path.abspath(args.output))
        os.makedirs(output_dir, exist_ok=True)

        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)

        print(json.dumps({
            "status": "ok",
            "output": args.output,
            "computed": [k for k in result if not isinstance(result[k], str)],
        }, ensure_ascii=False))

    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
