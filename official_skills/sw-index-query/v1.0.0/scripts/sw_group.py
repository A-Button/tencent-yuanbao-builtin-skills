#!/usr/bin/env python3
"""Group comparison: dashboard + matrix view for themed index groups.

Usage:
  python sw_group.py --preset style_broad          # 6 style broad indices
  python sw_group.py --preset jc                   # 4 JC indices
  python sw_group.py --preset style_broad --days 125  # half-year lookback
  python sw_group.py --codes 801271,801273,801275 --names "周期,消费,TMT"
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
    fetch_kline_for_group, fetch_risk_return_one, fetch_component_stocks_auto,
    call_analysis_llm, normalize_pct, _float,
    GROUP_PRESETS, GROUP_LABELS, COLOR_POOL,
    INDUSTRY_NAME_BY_CODE,
)

TEMPLATE = "SW_GRP"
TOTAL_STEPS = 6


def _resolve_group(preset: str | None, codes: str | None,
                    names: str | None) -> dict:
    """Return {code: short_name} for the group."""
    if preset and preset in GROUP_PRESETS:
        return GROUP_PRESETS[preset]
    if codes:
        code_list = [c.strip() for c in codes.split(",") if c.strip()]
        if names:
            name_list = [n.strip() for n in names.split(",")]
        else:
            name_list = [INDUSTRY_NAME_BY_CODE.get(c, c) for c in code_list]
        while len(name_list) < len(code_list):
            name_list.append(code_list[len(name_list)])
        return dict(zip(code_list, name_list))
    raise ValueError("必须指定 --preset 或 --codes")


def _compute_period_return(closes: list, n: int) -> float | None:
    """Return % change over last n bars, or None if insufficient data."""
    if len(closes) < n + 1:
        return None
    base = closes[-(n + 1)]
    if not base:
        return None
    return round((closes[-1] - base) / base * 100, 2)


def _compute_ytd_return(closes: list, labels: list) -> float | None:
    """Return % change from first trading day of current year."""
    if not closes or not labels:
        return None
    current_year = labels[-1][:4]
    for i, lbl in enumerate(labels):
        if lbl[:4] == current_year:
            base = closes[i]
            if base:
                return round((closes[-1] - base) / base * 100, 2)
            break
    return None


def main():
    parser = argparse.ArgumentParser(description="Group index comparison")
    parser.add_argument("--preset", default=None,
                        choices=list(GROUP_PRESETS.keys()),
                        help="Predefined group: style_broad or jc")
    parser.add_argument("--codes", default=None,
                        help="Comma-separated index codes")
    parser.add_argument("--names", default=None,
                        help="Comma-separated display names (with --codes)")
    parser.add_argument("--days", type=int, default=90,
                        help="K-line lookback days (default 90, min 60)")
    args = parser.parse_args()

    try:
        group = _resolve_group(args.preset, args.codes, args.names)
    except ValueError as e:
        print(json.dumps({"status": "error", "message": str(e)},
                         ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    days = max(args.days, 60)
    preset_label = GROUP_LABELS.get(args.preset, "指数群组对比")
    title = preset_label + (f" · {days}日" if days != 90 else "")
    identifier = f"sw-grp-{args.preset or 'custom'}"

    emit_artifact(TEMPLATE, identifier, title, {"loading": True})
    emit_phase(TEMPLATE, identifier, title, "meta", {},
               meta={"title": title, "preset": args.preset or "custom",
                     "count": len(group)})

    try:
        # Step 1: Fetch K-line for all indices
        emit_progress(TEMPLATE, identifier, title, 1, TOTAL_STEPS,
                      "正在获取K线数据")
        kline_map = fetch_kline_for_group(group, "DAY", days)
        if not kline_map:
            raise ValueError("无法获取任何指数的K线数据")

        # Step 2: Parse K-line + compute multi-period returns + normalization
        emit_progress(TEMPLATE, identifier, title, 2, TOTAL_STEPS,
                      "正在计算收益指标")

        common_dates = None
        parsed = {}
        for code in group:
            bars = kline_map.get(code)
            if not bars:
                continue
            labels = [r["bargaindate"][:10] for r in bars]
            closes = [float(r["closeindex"]) for r in bars]
            date_set = set(labels)
            if common_dates is None:
                common_dates = date_set
            else:
                common_dates &= date_set
            parsed[code] = {"labels": labels, "closes": closes, "bars": bars}

        if not common_dates or not parsed:
            raise ValueError("指数K线数据日期无交集")

        common_sorted = sorted(common_dates)
        base_date = common_sorted[0]

        indices_data = []
        for code, name in group.items():
            p = parsed.get(code)
            if not p:
                continue
            lbl_map = dict(zip(p["labels"], p["closes"]))
            aligned = [lbl_map[d] for d in common_sorted if d in lbl_map]
            if not aligned:
                continue

            base_price = aligned[0]
            normed = normalize_pct(aligned, base_price)

            all_closes = p["closes"]
            all_labels = p["labels"]
            latest = all_closes[-1]
            prev = all_closes[-2] if len(all_closes) >= 2 else latest
            chg = latest - prev
            chg_pct = round(chg / prev * 100, 2) if prev else 0

            returns = {
                "5d": _compute_period_return(all_closes, 5),
                "20d": _compute_period_return(all_closes, 20),
                "60d": _compute_period_return(all_closes, 60),
                "ytd": _compute_ytd_return(all_closes, all_labels),
            }

            indices_data.append({
                "code": code, "name": name,
                "latest": round(latest, 2),
                "change_pct": chg_pct,
                "returns": returns,
                "normalized": normed,
            })

        # Step 3: Fetch risk/return
        emit_progress(TEMPLATE, identifier, title, 3, TOTAL_STEPS,
                      "正在获取收益风险数据")
        for item in indices_data:
            rr = fetch_risk_return_one(item["code"])
            item["risk"] = rr or {}

        # Step 4: Fetch component stocks top3
        emit_progress(TEMPLATE, identifier, title, 4, TOTAL_STEPS,
                      "正在获取成分股数据")
        for item in indices_data:
            comps = fetch_component_stocks_auto(item["code"])
            sorted_c = sorted(comps,
                              key=lambda x: float(x.get("newWeight", 0)),
                              reverse=True)
            item["top3"] = [
                {"stockName": c.get("stockName", ""),
                 "newWeight": _float(c.get("newWeight"))}
                for c in sorted_c[:3]
            ]
            item["componentCount"] = len(comps)

        # Compute rankings per period
        periods = ["5d", "20d", "60d", "ytd"]
        rankings = {}
        for p in periods:
            ranked = sorted(
                [d for d in indices_data if d["returns"].get(p) is not None],
                key=lambda x: x["returns"][p], reverse=True)
            rankings[p] = [d["code"] for d in ranked]

        data_payload = {
            "indices": indices_data,
            "labels": common_sorted,
            "rankings": rankings,
            "colors": COLOR_POOL[:len(indices_data)],
        }
        meta_payload = {
            "title": title, "preset": args.preset or "custom",
            "count": len(indices_data),
            "date": common_sorted[-1] if common_sorted else "",
        }

        # Step 5: Emit data phase
        emit_progress(TEMPLATE, identifier, title, 5, TOTAL_STEPS,
                      "正在组装数据")
        emit_progress(TEMPLATE, identifier, title, 6, TOTAL_STEPS,
                      "正在生成轮动分析")
        emit_phase(TEMPLATE, identifier, title, "data", data_payload,
                   meta=meta_payload)

        perf_lines = []
        for d in indices_data:
            r = d["returns"]
            risk = d.get("risk", {})
            perf_lines.append(
                f"{d['name']}({d['code']}): 最新{d['latest']}, "
                f"日涨跌{d['change_pct']}%, "
                f"5日{r.get('5d','N/A')}%, 20日{r.get('20d','N/A')}%, "
                f"60日{r.get('60d','N/A')}%, YTD{r.get('ytd','N/A')}%, "
                f"年化收益{risk.get('y1_return','N/A')}%, "
                f"年化波动{risk.get('y1_vol','N/A')}%, "
                f"成分股{d['componentCount']}只"
            )
        rank_lines = []
        for p in periods:
            codes = rankings.get(p, [])
            names = [next((d["name"] for d in indices_data if d["code"] == c), c)
                     for c in codes]
            rank_lines.append(f"{p}排名: {' > '.join(names)}")

        llm_input = (
            f"指数群组: {preset_label}\n"
            f"数据日期: {common_sorted[-1] if common_sorted else 'N/A'}\n"
            + "\n".join(perf_lines) + "\n"
            + "\n".join(rank_lines)
        )
        analysis = call_analysis_llm(llm_input, "板块轮动")

        emit_phase(TEMPLATE, identifier, title, "final", data_payload,
                   meta=meta_payload, analysis=analysis)

        summary_text = llm_input
        print(json.dumps(attach_render({
            "status": "ok",
            "mode": "group",
            "preset": args.preset or "custom",
            "count": len(indices_data),
            "summary_text": summary_text,
        }), ensure_ascii=False))

    except Exception as e:
        emit_error(TEMPLATE, identifier, title, str(e))
        print(json.dumps({"status": "error", "message": str(e)},
                         ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
