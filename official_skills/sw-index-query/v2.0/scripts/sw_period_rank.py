#!/usr/bin/env python3
"""Week / Month period ranking: cross-section of all indices at a week-end
or month-end boundary.

Uses:
  - /index_analysis/week_month_datetime/ — available period-end dates
  - /index_analysis/index_analysis_reports/ — per-period snapshot

Answers analyst questions like:
  - "本月哪个行业涨最多？"
  - "上个月 PE 最低的行业"
  - "近三个月换手率持续上升的行业" (with --windows 3)

Usage:
  python sw_period_rank.py                                # 本月一级行业涨跌幅排名
  python sw_period_rank.py --period WEEK                  # 本周
  python sw_period_rank.py --metric pe --order asc        # PE 升序
  python sw_period_rank.py --metric dp --order desc       # 股息率降序
  python sw_period_rank.py --period MONTH --offset 1      # 上月
  python sw_period_rank.py --index-type 市场表征 --period WEEK
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
    attach_render, add_render_file, has_platform_artifact,
    call_analysis_llm,
    fetch_period_dates,
    fetch_period_snapshot,
    INDUSTRY_GROUPS,
    SCOPE_LABELS,
)
METRIC_LABELS = {
    "change_pct": ("涨跌幅(%)", "区间涨跌"),
    "pe": ("PE", "估值"),
    "pb": ("PB", "估值"),
    "dp": ("股息率(%)", "股息"),
    "turnover": ("换手率(%)", "交投活跃度"),
    "volume": ("成交量(亿股)", ""),
    "close": ("收盘指数", ""),
    "circ_mcap": ("流通市值(亿)", ""),
}

_PERIOD_LABELS = {"WEEK": "周", "MONTH": "月"}


def _default_order(metric: str) -> str:
    return "asc" if metric in ("pe", "pb") else "desc"


def _fmt(v, d=2):
    return "—" if v is None else f"{v:.{d}f}"


def _emit_table(rows, metric, period, bargaindate, scope_label):
    period_cn = _PERIOD_LABELS[period]
    metric_label, _ = METRIC_LABELS.get(metric, (metric, ""))

    columns = [
        {"key": "name", "title": "指数", "type": "text", "width": 120},
        {"key": "code", "title": "代码", "type": "text", "width": 80},
        {"key": "close", "title": "收盘", "type": "number", "decimals": 2},
        {"key": "change_pct", "title": f"{period_cn}涨跌幅", "type": "percent"},
        {"key": "pe", "title": "PE", "type": "number", "decimals": 2},
        {"key": "pb", "title": "PB", "type": "number", "decimals": 2},
        {"key": "dp", "title": "股息率%", "type": "number", "decimals": 2},
        {"key": "turnover", "title": "换手%", "type": "number", "decimals": 2},
    ]

    payload = {
        "title": f"{scope_label} {period_cn}度排行 · {bargaindate}",
        "description": f"按 {metric_label} 排序",
        "columns": columns,
        "rows": [
            {
                "name": r["name"], "code": r["code"],
                "close": r.get("close"),
                "change_pct": r.get("change_pct"),
                "pe": r.get("pe"), "pb": r.get("pb"),
                "dp": r.get("dp"), "turnover": r.get("turnover"),
            }
            for r in rows
        ],
    }

    if has_platform_artifact():
        import uuid
        block_id = uuid.uuid4().hex[:8]
        print(f'<pi-table id="{block_id}">')
        print(json.dumps(payload, ensure_ascii=False))
        print("</pi-table>")
    else:
        # 无平台：输出 Markdown 表格并写入渲染文件
        from sw_render import md_table_from_payload
        md = md_table_from_payload(payload)
        try:
            from sw_common import get_render_dir
            out_dir = get_render_dir()
            os.makedirs(out_dir, exist_ok=True)
            md_path = os.path.join(out_dir, "sw-period-rank-table.md")
            add_render_file("sw-period-rank-table", "md", md_path)
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(md)
        except Exception:
            pass
        print(md.rstrip("\n"))


def main():
    parser = argparse.ArgumentParser(description="Week/Month period ranking")
    parser.add_argument("--period", default="MONTH", choices=["WEEK", "MONTH"])
    parser.add_argument("--offset", type=int, default=0,
                        help="0=最近一个周/月末, 1=上一个, 2=上上一个, ...")
    parser.add_argument("--compare-offset", type=int, default=None,
                        help="可选对比基准 offset。传入后额外输出 reversals 反转榜")
    parser.add_argument("--index-type", default="一级行业",
                        choices=["市场表征", "一级行业", "二级行业", "风格指数"])
    parser.add_argument("--scope", default="all",
                        choices=["all"] + list(INDUSTRY_GROUPS.keys()))
    parser.add_argument("--metric", default="change_pct",
                        choices=list(METRIC_LABELS.keys()))
    parser.add_argument("--order", default=None, choices=["asc", "desc"])
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    order = args.order or _default_order(args.metric)

    try:
        from client import USE_WESTOCK
        if USE_WESTOCK and args.metric != "change_pct":
            raise ValueError("westock 周/月排行仅支持涨跌幅；历史估值横截面未验证")
        if args.offset < 0 or (args.compare_offset is not None and args.compare_offset < 0):
            raise ValueError("offset 必须非负")
        # 1) Fetch date list and pick the target bargaindate
        dates = fetch_period_dates(args.period)
        if not dates:
            raise ValueError(f"未获取到 {args.period} 级日期列表")
        if args.offset >= len(dates):
            raise ValueError(f"--offset {args.offset} 超出可用范围（共 {len(dates)} 个日期）")
        bargaindate = dates[args.offset]

        # 2) Fetch snapshot for that date
        scope_codes = INDUSTRY_GROUPS[args.scope].values() if args.index_type == "一级行业" and args.scope != "all" else None
        rows = fetch_period_snapshot(args.period, bargaindate, args.index_type, codes=scope_codes)
        if not rows:
            raise ValueError(f"未获取到 {bargaindate} 的 {args.index_type} 截面数据")

        # 3) Scope filter
        if args.index_type == "一级行业" and args.scope != "all":
            allowed = set(INDUSTRY_GROUPS[args.scope].values())
            rows = [r for r in rows if r["code"] in allowed]

        # 4) Remove rows missing the target metric, sort, truncate
        rows = [r for r in rows if r.get(args.metric) is not None]
        if not rows:
            raise ValueError(f"无有效 {args.metric} 数据")
        rows.sort(key=lambda r: r.get(args.metric) or 0, reverse=(order == "desc"))
        rows = rows[:args.limit]

        period_cn = _PERIOD_LABELS[args.period]
        metric_label, _ = METRIC_LABELS.get(args.metric, (args.metric, ""))
        scope_label = (SCOPE_LABELS.get(args.scope, "A股市场")
                       if args.index_type == "一级行业" else args.index_type)

        _emit_table(rows, args.metric, args.period, bargaindate, scope_label)

        # 5) Summary
        n = len(rows)
        vals = [r[args.metric] for r in rows]
        median = sorted(vals)[n // 2] if n else None
        top5 = rows[:5]
        bot5 = rows[-5:] if n >= 10 else []

        top5_str = ", ".join(f"{r['name']}({_fmt(r.get(args.metric))})" for r in top5)
        bot5_str = ", ".join(f"{r['name']}({_fmt(r.get(args.metric))})" for r in bot5)

        summary_text = (
            f"{scope_label} {period_cn}度 {metric_label} 排行（{bargaindate}）\n"
            f"样本 {n} 条, 中位数 {_fmt(median)}\n"
            f"{'高' if order == 'desc' else '低'}5: {top5_str}"
        )
        if bot5:
            summary_text += f"\n{'低' if order == 'desc' else '高'}5: {bot5_str}"

        # 6) Compare mode: rank reversal vs another offset
        reversals = None
        compare_bargaindate = None
        if args.compare_offset is not None and args.compare_offset != args.offset:
            if args.compare_offset >= len(dates):
                raise ValueError(
                    f"--compare-offset {args.compare_offset} 超出范围（共 {len(dates)} 个日期）"
                )
            compare_bargaindate = dates[args.compare_offset]
            compare_rows = fetch_period_snapshot(
                args.period, compare_bargaindate, args.index_type, codes=scope_codes
            )
            if args.index_type == "一级行业" and args.scope != "all":
                allowed = set(INDUSTRY_GROUPS[args.scope].values())
                compare_rows = [r for r in compare_rows if r["code"] in allowed]
            compare_rows = [
                r for r in compare_rows if r.get(args.metric) is not None
            ]
            # Sort compare rows same direction, build rank map
            compare_rows.sort(
                key=lambda r: r.get(args.metric) or 0, reverse=(order == "desc")
            )
            rank_prev = {r["code"]: i + 1 for i, r in enumerate(compare_rows)}
            rank_now = {r["code"]: i + 1 for i, r in enumerate(rows)}

            # Only include codes present in both snapshots
            reversals_all = []
            for code, rn in rank_now.items():
                rp = rank_prev.get(code)
                if rp is None:
                    continue
                change = rp - rn  # positive = rank improved (e.g. 15→1 => +14)
                name = next((r["name"] for r in rows if r["code"] == code), code)
                reversals_all.append({
                    "code": code, "name": name,
                    "rank_now": rn, "rank_prev": rp, "change": change,
                })
            # Filter |change| >= 10, sort by |change| desc
            reversals = [r for r in reversals_all if abs(r["change"]) >= 10]
            reversals.sort(key=lambda r: abs(r["change"]), reverse=True)

            if reversals:
                summary_text += f"\n\n排名反转 TOP（vs {compare_bargaindate}）："
                for r in reversals[:5]:
                    arrow = "↑" if r["change"] > 0 else "↓"
                    summary_text += (
                        f"\n  {r['name']}({r['code']}): 第{r['rank_prev']}→第{r['rank_now']}"
                        f" ({arrow}{abs(r['change'])}位)"
                    )
        analysis = call_analysis_llm(summary_text, f"{period_cn}度{metric_label}排行")

        output = {
            "status": "ok",
            "mode": "period_rank",
            "period": args.period,
            "offset": args.offset,
            "bargaindate": bargaindate,
            "index_type": args.index_type,
            "scope": args.scope,
            "metric": args.metric,
            "order": order,
            "count": n,
            "top5": [{"name": r["name"], "code": r["code"], args.metric: r.get(args.metric)} for r in top5],
            "bottom5": [{"name": r["name"], "code": r["code"], args.metric: r.get(args.metric)} for r in bot5],
            "summary_text": summary_text,
            "analysis": analysis,
        }
        if reversals is not None:
            output["compare_offset"] = args.compare_offset
            output["compare_bargaindate"] = compare_bargaindate
            output["reversals"] = reversals
        print(json.dumps(attach_render(output), ensure_ascii=False))

    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False),
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
