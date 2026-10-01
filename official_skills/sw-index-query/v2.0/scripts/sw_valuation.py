#!/usr/bin/env python3
"""Index valuation ranking: PE / PB / 股息率 / 换手率 / 流通市值 cross-section.

Uses /institute-sw/api/index_analysis/day_week_month_report/ — the batch
fundamental metrics endpoint. Returns a ranked list answering "哪些行业
当前估值低 / 股息率高 / 换手率高".

Usage:
  python sw_valuation.py                              # 一级行业, 按 PE 升序
  python sw_valuation.py --metric pb                  # 按 PB 升序
  python sw_valuation.py --metric dp --order desc     # 股息率从高到低
  python sw_valuation.py --metric turnover --order desc  # 换手率从高到低
  python sw_valuation.py --scope tmt --metric pe      # TMT 板块 PE 排序
  python sw_valuation.py --index-type 市场表征 --metric pe

Output:
  - Artifact: inline pi-table with sortable columns
  - JSON summary to stdout for the Agent to reference
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
    fetch_fundamentals_batch,
    INDUSTRY_GROUPS,
    SCOPE_LABELS,
)
METRIC_LABELS = {
    "pe": ("PE", "低估值优先"),
    "pb": ("PB", "低估值优先"),
    "dp": ("股息率(%)", "高股息优先"),
    "turnover": ("换手率(%)", "高换手优先"),
    "change_pct": ("涨跌幅(%)", ""),
    "circ_mcap": ("流通市值(亿)", ""),
}


def _default_order(metric: str) -> str:
    """PE/PB default asc (cheap first); dp/turnover default desc (high first)."""
    return "asc" if metric in ("pe", "pb") else "desc"


def _fmt(v: float | None, decimals: int = 2) -> str:
    if v is None:
        return "—"
    return f"{v:.{decimals}f}"


def _emit_table(rows: list[dict], metric: str, title: str, description: str):
    """Render a table result: pi-table on platform, Markdown table locally."""
    metric_label, _ = METRIC_LABELS.get(metric, (metric, ""))

    columns = [
        {"key": "name", "title": "指数", "type": "text", "width": 120},
        {"key": "code", "title": "代码", "type": "text", "width": 80},
        {"key": "date", "title": "估值日期", "type": "text"},
        {"key": "quote_date", "title": "行情日期", "type": "text"},
        {"key": "latest", "title": "行情价", "type": "number", "decimals": 2},
        {"key": "change_pct", "title": "涨跌幅", "type": "percent"},
        {"key": "pe", "title": "PE", "type": "number", "decimals": 2},
        {"key": "pe_percentile", "title": "PE历史分位%", "type": "number"},
        {"key": "pb_percentile", "title": "PB历史分位%", "type": "number"},
        {"key": "pb", "title": "PB", "type": "number", "decimals": 2},
        {"key": "dp", "title": "股息率%", "type": "number", "decimals": 2},
        {"key": "turnover", "title": "换手%", "type": "number", "decimals": 2},
        {"key": "circ_mcap", "title": "流通市值(亿)", "type": "number", "decimals": 0},
    ]

    table_rows = []
    for r in rows:
        table_rows.append({
            "date": r.get("date"),
            "quote_date": r.get("quote_date"),
            "name": r["name"],
            "code": r["code"],
            "latest": r.get("close"),
            "change_pct": r.get("change_pct"),
            "pe": r.get("pe"),
            "pb": r.get("pb"),
            "pe_percentile": r.get("pe_percentile"),
            "pb_percentile": r.get("pb_percentile"),
            "dp": r.get("dp"),
            "turnover": r.get("turnover"),
            "circ_mcap": r.get("circ_mcap"),
        })

    payload = {
        "title": f"{title} · 按 {metric_label} 排序",
        "description": description,
        "columns": columns,
        "rows": table_rows,
    }

    if has_platform_artifact():
        # 平台环境：pi-table 内联块（同 build_inline_block.py 格式）
        import uuid
        block_id = uuid.uuid4().hex[:8]
        print(f'<pi-table id="{block_id}">')
        print(json.dumps(payload, ensure_ascii=False))
        print("</pi-table>")
    else:
        # 无平台：输出 Markdown 表格，并写入 .md 渲染文件供 Agent 展示
        from sw_render import md_table_from_payload
        md = md_table_from_payload(payload)
        try:
            from sw_common import get_render_dir
            out_dir = get_render_dir()
            add_render_file("sw-valuation-table", "md",
                            os.path.join(out_dir, "sw-valuation-table.md"))
            os.makedirs(out_dir, exist_ok=True)
            with open(os.path.join(out_dir, "sw-valuation-table.md"), "w", encoding="utf-8") as f:
                f.write(md)
        except Exception:
            pass
        print(md.rstrip("\n"))


def main():
    parser = argparse.ArgumentParser(description="Index valuation ranking")
    parser.add_argument("--index-type", default="一级行业",
                        choices=["市场表征", "一级行业", "二级行业", "风格指数"],
                        help="分类")
    parser.add_argument("--scope", default="all",
                        choices=["all"] + list(INDUSTRY_GROUPS.keys()),
                        help="板块过滤（仅对 一级行业 有效）")
    parser.add_argument("--metric", default="pe",
                        choices=list(METRIC_LABELS.keys()),
                        help="排序指标（pe/pb/dp/turnover/change_pct/circ_mcap）")
    parser.add_argument("--order", default=None, choices=["asc", "desc"],
                        help="排序方向（默认 PE/PB asc，dp/turnover desc）")
    parser.add_argument("--limit", type=int, default=50,
                        help="输出行数上限（默认 50）")
    args = parser.parse_args()

    order = args.order or _default_order(args.metric)

    try:
        rows = fetch_fundamentals_batch(args.index_type, codes=INDUSTRY_GROUPS[args.scope].values() if args.index_type == "一级行业" and args.scope != "all" else None)
        if not rows:
            raise ValueError(f"未获取到 {args.index_type} 的估值数据")

        # Scope filter — 仅对 一级行业 分类有意义
        if args.index_type == "一级行业" and args.scope != "all":
            allowed = set(INDUSTRY_GROUPS[args.scope].values())
            rows = [r for r in rows if r["code"] in allowed]

        # Filter out rows where target metric is missing
        rows = [r for r in rows if r.get(args.metric) is not None]
        if not rows:
            raise ValueError(f"在 {args.index_type} / {args.scope} 范围内未找到 {args.metric} 数据")

        reverse = order == "desc"
        rows.sort(key=lambda r: r.get(args.metric) or 0, reverse=reverse)
        rows = rows[:args.limit]

        # Summary statistics
        vals = [r[args.metric] for r in rows if r.get(args.metric) is not None]
        n = len(vals)
        median = sorted(vals)[n // 2] if n else None
        mn = min(vals) if vals else None
        mx = max(vals) if vals else None

        metric_label, _ = METRIC_LABELS.get(args.metric, (args.metric, ""))
        scope_label = SCOPE_LABELS.get(args.scope, "A股市场") if args.index_type == "一级行业" else args.index_type
        title = f"{scope_label} 估值排行"
        bargaindate = rows[0].get("date", "") if rows else ""
        description = f"数据日期 {bargaindate} · 共 {n} 条 · {metric_label} 中位数 {_fmt(median)} · 区间 {_fmt(mn)}—{_fmt(mx)}"

        _emit_table(rows, args.metric, title, description)

        # Build summary text for the Agent
        top5_items = rows[:5]
        bot5_items = rows[-5:] if len(rows) >= 10 else []
        top5 = ", ".join(f"{r['name']}({_fmt(r.get(args.metric))})" for r in top5_items)
        bot5 = ", ".join(f"{r['name']}({_fmt(r.get(args.metric))})" for r in bot5_items)

        summary_text = (
            f"{title} - {metric_label} {'降序' if reverse else '升序'}\n"
            f"数据日期: {bargaindate} | 样本数: {n}\n"
            f"{metric_label} 中位数 {_fmt(median)}, 最小 {_fmt(mn)}, 最大 {_fmt(mx)}\n"
            f"前5: {top5}"
        )
        if bot5_items:
            summary_text += f"\n后5: {bot5}"

        # LLM analysis (same pattern as sw_rank)
        analysis = call_analysis_llm(summary_text, "指数估值排名")

        print(json.dumps(attach_render({
            "status": "ok",
            "mode": "valuation",
            "index_type": args.index_type,
            "scope": args.scope,
            "metric": args.metric,
            "order": order,
            "count": n,
            "bargaindate": bargaindate,
            "top5": [{"name": r["name"], "code": r["code"], args.metric: r.get(args.metric)}
                     for r in rows[:5]],
            "bottom5": [{"name": r["name"], "code": r["code"], args.metric: r.get(args.metric)}
                        for r in rows[-5:]],
            "summary_text": summary_text,
            "analysis": analysis,
        }), ensure_ascii=False))

    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False),
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
