#!/usr/bin/env python3
"""N-index correlation matrix.

For ≥3 indices (use sw_regression.py for exactly 2), compute pairwise
Pearson correlation of daily returns over a window. Report matrix + max/min
pair + average correlation.

Usage:
  sw_corr_matrix.py --codes 801080,801750,801770,801760 --names 电子,计算机,通信,传媒 [--days 250]
  sw_corr_matrix.py --scope tmt [--days 250]
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
    fetch_kline_for_group,
    INDUSTRY_GROUPS,
    INDUSTRY_L1,
    STYLE_INDICES,
    MARKET_INDICES,

)
TEMPLATE = "SW_CORR"


def _kline_to_ret_map(kline: list) -> dict[str, float]:
    """Return {date: daily_return} map."""
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


def _pearson(a: list[float], b: list[float]) -> float:
    n = len(a)
    if n < 2:
        return None
    mean_a = sum(a) / n
    mean_b = sum(b) / n
    cov = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(n))
    var_a = sum((x - mean_a) ** 2 for x in a)
    var_b = sum((x - mean_b) ** 2 for x in b)
    denom = math.sqrt(var_a * var_b)
    if denom <= 0:
        return None
    return round(cov / denom, 4)


def _resolve_codes(args) -> dict:
    """Return {code: name} from --codes/--names or --scope."""
    if args.codes:
        codes = [c.strip() for c in args.codes.split(",") if c.strip()]
        if args.names:
            names = [n.strip() for n in args.names.split(",")]
            if len(names) != len(codes):
                raise ValueError("--names 数量必须与 --codes 一致")
        else:
            # Lookup names
            all_names = {**INDUSTRY_L1, **STYLE_INDICES, **MARKET_INDICES}
            names = [all_names.get(c, c) for c in codes]
        return dict(zip(codes, names))

    if args.scope:
        if args.scope == "l1":
            return dict(INDUSTRY_L1)
        if args.scope == "style":
            return dict(STYLE_INDICES)
        if args.scope == "market":
            return dict(MARKET_INDICES)
        if args.scope in INDUSTRY_GROUPS:
            return {code: name for name, code in INDUSTRY_GROUPS[args.scope].items()}
        raise ValueError(f"未知 scope: {args.scope}")

    raise ValueError("必须提供 --codes 或 --scope 其一")


def main():
    parser = argparse.ArgumentParser(description="N-index correlation matrix")
    parser.add_argument("--codes", default=None, help="逗号分隔指数代码（≥3 个）")
    parser.add_argument("--names", default=None, help="逗号分隔名称（与 codes 对齐）")
    parser.add_argument("--scope", default=None,
                        choices=[None, "l1", "style", "market"] + list(INDUSTRY_GROUPS.keys()),
                        help="替代 codes：l1 一级行业 / style 风格 / market 市场 / consumer/tmt/...")
    parser.add_argument("--days", type=int, default=250, help="回溯交易日")
    args = parser.parse_args()

    scope_label = args.scope or "custom"
    identifier = f"sw-corr-{scope_label}-{args.days}d"
    title = "N 指数相关性矩阵"

    emit_artifact(TEMPLATE, identifier, title, {"loading": True})

    try:
        codes_dict = _resolve_codes(args)
        if len(codes_dict) < 2:
            raise ValueError("至少需要 2 个指数")
        if len(codes_dict) == 2:
            raise ValueError("仅 2 个指数请用 sw_regression.py（含 alpha/beta/TE 更全）")
        if len(codes_dict) > 31:
            raise ValueError(f"相关矩阵不建议 >31 个（当前 {len(codes_dict)}），输出过大")

        title = f"{len(codes_dict)} 指数相关性矩阵 · {args.days}日"
        emit_phase(TEMPLATE, identifier, title, "meta", {
            "count_expected": len(codes_dict),
            "window_days": args.days,
            "scope": args.scope,
        }, meta={"title": title})

        emit_progress(TEMPLATE, identifier, title, 1, 2, f"并行获取 {len(codes_dict)} 指数 K 线")

        # Fetch K-lines in batch
        klines = fetch_kline_for_group(codes_dict, "DAY", args.days)

        # Build return maps aligned by date
        ret_maps: dict[str, dict[str, float]] = {}
        for code, kline in klines.items():
            if not kline:
                continue
            ret_maps[code] = _kline_to_ret_map(kline)

        if len(ret_maps) < 2:
            raise ValueError("成功获取 K 线的指数 < 2")

        # Intersect common dates
        common_dates = None
        for rm in ret_maps.values():
            ds = set(rm.keys())
            common_dates = ds if common_dates is None else (common_dates & ds)
        common_dates = sorted(common_dates)
        if len(common_dates) < 30:
            raise ValueError(f"共同交易日不足（{len(common_dates)}，需 ≥ 30）")

        # Build return series per index
        sorted_codes = [c for c in codes_dict.keys() if c in ret_maps]
        names = [codes_dict[c] for c in sorted_codes]
        ret_series = {c: [ret_maps[c][d] for d in common_dates] for c in sorted_codes}

        # Build correlation matrix
        n = len(sorted_codes)
        matrix = [[1.0] * n for _ in range(n)]
        corrs = []  # (i, j, corr)
        for i in range(n):
            for j in range(i + 1, n):
                r = _pearson(ret_series[sorted_codes[i]], ret_series[sorted_codes[j]])
                if r is None:
                    raise ValueError("存在零方差序列，相关系数未定义，不能填0")
                matrix[i][j] = r
                matrix[j][i] = r
                if r is not None:
                    corrs.append((i, j, r))

        if not corrs:
            raise ValueError("所有指数对相关性计算失败")

        # Stats
        avg_corr = round(sum(c[2] for c in corrs) / len(corrs), 4)
        max_pair = max(corrs, key=lambda x: x[2])
        min_pair = min(corrs, key=lambda x: x[2])

        summary_text = (
            f"{n} 个指数共同窗口 {args.days} 日（实际 {len(common_dates)} 日重叠）平均相关 {avg_corr:.3f}\n"
            f"最强: {names[max_pair[0]]}-{names[max_pair[1]]} = {max_pair[2]:.3f}\n"
            f"最弱: {names[min_pair[0]]}-{names[min_pair[1]]} = {min_pair[2]:.3f}"

        # Top-K pairs (both directions) for side panel
        )
        sorted_pairs = sorted(corrs, key=lambda x: x[2], reverse=True)
        top_pairs = [
            {"a": names[p[0]], "b": names[p[1]], "corr": round(p[2], 3)}
            for p in sorted_pairs[:5]
        ]
        bot_pairs = [
            {"a": names[p[0]], "b": names[p[1]], "corr": round(p[2], 3)}
            for p in sorted_pairs[-5:][::-1]
        ]

        data_payload = {
            "count": n,
            "window_days": args.days,
            "effective_days": len(common_dates),
            "codes": sorted_codes,
            "names": names,
            "matrix": [[round(x, 3) for x in row] for row in matrix],
            "avg_corr": avg_corr,
            "max_pair": {"a": names[max_pair[0]], "b": names[max_pair[1]], "corr": round(max_pair[2], 3)},
            "min_pair": {"a": names[min_pair[0]], "b": names[min_pair[1]], "corr": round(min_pair[2], 3)},
            "top_pairs": top_pairs,
            "bot_pairs": bot_pairs,
            "summary_text": summary_text,
        }

        emit_phase(TEMPLATE, identifier, title, "data", data_payload,
                   meta={"title": title})
        emit_phase(TEMPLATE, identifier, title, "final", data_payload,
                   meta={"title": title}, analysis=summary_text)

        print(json.dumps(attach_render({
            "status": "ok",
            "mode": "corr_matrix",
            "count": n,
            "window_days": args.days,
            "effective_days": len(common_dates),
            "codes": sorted_codes,
            "names": names,
            "avg_corr": avg_corr,
            "max_pair": {"a": names[max_pair[0]], "b": names[max_pair[1]], "corr": round(max_pair[2], 3)},
            "min_pair": {"a": names[min_pair[0]], "b": names[min_pair[1]], "corr": round(min_pair[2], 3)},
            "summary_text": summary_text,
        }), ensure_ascii=False))

    except Exception as e:
        emit_error(TEMPLATE, identifier, title, str(e))
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False),
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
