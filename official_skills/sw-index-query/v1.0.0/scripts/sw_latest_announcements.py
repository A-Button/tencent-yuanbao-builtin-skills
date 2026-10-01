#!/usr/bin/env python3
"""Latest announcements across all SW indices.

Uses /insWechatSw/swIndex/fundORStockAnnouncementPageList — the batch
"whole-site announcements" endpoint (replaces per-index queries when the
analyst wants "any recent announcement").

Answers:
  - "最近一周 SWS 发布了哪些指数公告？"
  - "本周有哪些指数调整了成分股？"
  - "基金指数近期公告"

Usage:
  python sw_latest_announcements.py                    # 最近 7 天, 前 20 条
  python sw_latest_announcements.py --days 30          # 最近 30 天
  python sw_latest_announcements.py --limit 10         # 前 10 条
  python sw_latest_announcements.py --type 一级行业    # 过滤类型

Output:
  - Artifact: inline <pi-table> listing announcements
  - JSON summary to stdout
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from client import sw_post  # noqa: E402  (resolves to swsresearch/client.py)
from sw_common import (  # noqa: E402
    call_analysis_llm, attach_render, add_render_file, has_platform_artifact,
)


def _fmt_date(days_ago: int) -> str:
    d = datetime.date.today() - datetime.timedelta(days=days_ago)
    return d.strftime("%Y-%m-%d")


def main():
    parser = argparse.ArgumentParser(description="Latest SW index announcements")
    # SWS 发布节奏是**月末信息**为主，7 天窗口经常返 0 条。默认 90 天覆盖至少 3 次月末。
    parser.add_argument("--days", type=int, default=90,
                        help="时间窗口（最近 N 天，默认 90；SWS 以月末信息为主，窗口过小会返空）")
    parser.add_argument("--limit", type=int, default=20,
                        help="最多返回条数（默认 20）")
    # API 实际返回的 type 值（实测）: 一级行业 / 申万指数 / 申万50 / 特征指数 / 重要信息
    parser.add_argument("--type", default=None,
                        help="类型过滤（实际可选值：一级行业 / 申万指数 / 申万50 / 特征指数 / 重要信息）")
    args = parser.parse_args()

    start_date = _fmt_date(args.days)
    end_date = _fmt_date(0)

    try:
        # Fetch (API supports startDate / endDate)
        body = {"pageNo": 1, "pageSize": max(args.limit, 30),
                "startDate": start_date, "endDate": end_date}
        resp = sw_post(
            "/insWechatSw/swIndex/fundORStockAnnouncementPageList", body=body, timeout=20,
        )
        lst = (resp.get("data") or {}).get("list") or []

        if args.type:
            lst = [r for r in lst if r.get("type") == args.type]
        lst = lst[:args.limit]

        if not lst:
            raise ValueError(f"最近 {args.days} 天内未发现公告（类型过滤: {args.type or '全部'}）")

        # Build pi-table
        rows = []
        for r in lst:
            rows.append({
                "title": r.get("title", ""),
                "indexCode": r.get("swIndexCode", ""),
                "type": r.get("type", ""),
                "date": (r.get("delareDate") or "")[:10],
                "id": r.get("id", ""),
            })

        payload = {
            "title": f"最近 {args.days} 天指数公告",
            "description": f"共 {len(rows)} 条 · {start_date} → {end_date}"
                         + (f" · 类型: {args.type}" if args.type else ""),
            "columns": [
                {"key": "title", "title": "公告标题", "type": "text", "width": 360},
                {"key": "indexCode", "title": "指数代码", "type": "text", "width": 100},
                {"key": "type", "title": "类型", "type": "tag",
                 "colorMap": {
                     "一级行业": "blue", "申万指数": "gray",
                     "申万50": "green", "特征指数": "orange", "重要信息": "red",
                 }},
                {"key": "date", "title": "发布日期", "type": "text", "width": 110},
            ],
            "rows": rows,
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
                md_path = os.path.join(out_dir, "sw-announcements-table.md")
                add_render_file("sw-announcements-table", "md", md_path)
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(md)
            except Exception:
                pass
            print(md.rstrip("\n"))

        # Type distribution for summary
        type_count = {}
        for r in lst:
            t = r.get("type", "")
            type_count[t] = type_count.get(t, 0) + 1

        summary_text = (
            f"近 {args.days} 天指数公告聚合（{start_date} → {end_date}）\n"
            f"共 {len(lst)} 条"
            + (f"（过滤: {args.type}）\n" if args.type else "\n")
            + f"类型分布: {', '.join(f'{k}×{v}' for k, v in sorted(type_count.items(), key=lambda x: -x[1]))}\n"
            + "最新 3 条:\n"
            + "\n".join(f"  {r.get('title','')} [{r.get('type','')}, {(r.get('delareDate') or '')[:10]}]"
                       for r in lst[:3])

        )
        analysis = call_analysis_llm(summary_text, "指数公告聚合")

        print(json.dumps(attach_render({
            "status": "ok",
            "mode": "latest_announcements",
            "days": args.days,
            "startDate": start_date,
            "endDate": end_date,
            "type": args.type,
            "count": len(lst),
            "type_distribution": type_count,
            "items": [{"title": r.get("title", ""), "type": r.get("type", ""),
                       "indexCode": r.get("swIndexCode", ""),
                       "date": (r.get("delareDate") or "")[:10]} for r in lst],
            "summary_text": summary_text,
            "analysis": analysis,
        }), ensure_ascii=False))

    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False),
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
