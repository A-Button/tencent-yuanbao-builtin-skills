#!/usr/bin/env python3
"""资讯总结卡（`recommend_list`）的 show_widget 入参。

资讯 Todo 挂上之后，作为 20:00 日结的最后一张（排在股票卡和盘面总结之后）。没挂上不跑。只填和已推清单做差之后剩下的新条目；差集为空就不要调用本脚本。没有资讯事件来源，不要为盘中重大另调本脚本。当面问资讯不要再附一张 `stock`。

    python3 scripts/now_news.py '{"thing_id":"117…","source_label":"每晚资讯汇总","date":"09/22","items":[
      {"code":"hk00700","name":"腾讯控股","title":"暂无公司公告","stance":"中性",
       "takeaway":"反弹更像超跌修复","origin":"westock","url":"https://…"}]}'

`takeaway` 是这一条的一句话解读，**卡上最有价值的就是它**。方向已经由圆点表达过，
不要再把「利好」两个字写进 desc 去顶掉解读的位置（2026-09-23 线上发错过一张）。
`stance` 只接受 `利好` / `利空`，其余一律中性走 ⚪——标类型是陈述事实，标方向是下判断。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _card import STANCE_DIRECTION, parse_symbol  # noqa: E402
from _now import (clip, ACTION_NEWS, LIMIT_DESC, LIMIT_TITLE,  # noqa: E402
                  MAX_ROWS, SUMMARY_NEWS, action, dot, envelope, fail, h5,
                  name_of, run, source_label)


def build(args: dict, items: list[dict]) -> dict:
    rows = []
    # 已按重要度排过序，超出就砍尾部，不重排。
    for index, item in enumerate(items[:MAX_ROWS]):
        symbol = parse_symbol(item) if item.get("code") else {"market": "", "code": ""}
        way = STANCE_DIRECTION.get(str(item.get("stance") or "").strip(), "flat")
        headline = str(item.get("title") or "").strip()
        if not headline:
            fail(f"第 {index + 1} 条缺 title：资讯标题照取数返回值写，不要自己概括。")
        # 行业新闻这类没有归属标的，省掉 code/name 即可，不要硬塞一只票。
        name = name_of(item)
        name_part = f"{name} · " if name else ""
        row = {"item_id": symbol["code"] or f"news_{index + 1}",
               "title": clip(f"{dot(symbol['market'], way)} {name_part}{headline}",
                                   LIMIT_TITLE)}
        desc = " · ".join(p for p in (str(item.get("takeaway") or "").strip(),
                                      str(item.get("origin") or "").strip()) if p)
        if desc:
            row["desc"] = clip(desc, LIMIT_DESC)
        # 点进去是这条新闻的原文页。URL 只能用 westock 真返回的（`news article --raw`
        # 才有 url 列），不许拿 id 拼；取不到就这一条不可点，不要退回主对话。
        tap = h5(str(item.get("url") or "").strip())
        if tap:
            row["tap"] = tap
        rows.append(row)

    date = str(args.get("date") or "").strip()
    if not date:
        fail("date 必填：标题上的日期用资讯的当日日期，不要省略。")

    card = envelope("recommend_list", f"今日资讯总结 · {date}", SUMMARY_NEWS,
                    source_label(args), {"items": rows}, args.get("thing_id", ""))
    card["actions"] = [action(ACTION_NEWS, [i for i in items if i.get("code")] or items)]
    return card


if __name__ == "__main__":
    raise SystemExit(run(build))
