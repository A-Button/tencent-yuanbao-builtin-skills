#!/usr/bin/env python3
"""市场风格分析研报：风格指数 + 一级行业 + 外部宽基指数 → 固定模板
HTML 研报（sw_html_report.py 模板 2）。

Usage:
  python sw_style_report.py --breadth-json b.json          # 标准用法（见下）
  python sw_style_report.py --breadth-json b.json --output dir

市场广度与情绪数据（涨跌家数 / 涨停跌停 / 成交额 / 两融余额）**必须**通过
WorkBuddy 环境的数据源获取后传入：
  - 大盘市场宽度统计（neodata）：沪深两市涨跌家数、涨停/跌停家数、成交额
  - 两融统计（neodata）：全市场融资融券余额、占流通市值比等
脚本不自取个股级广度数据，也不做行业级兜底——缺少广度数据时相关区块显示
"待补充"，并在 stderr 提示获取方式。

输出：
  - stdout 最后一行 JSON 摘要（含 render_files.html 路径）
  - HTML 研报文件（默认 <工作目录>/今日市场风格分析.html）
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

from sw_common import (  # noqa: E402
    fetch_snapshot_batch, get_workspace_dir, resolve_market_reference,
)
from external_indices import index_daily, is_supported_index  # noqa: E402
from sw_html_report import render_style_report  # noqa: E402

# 宽基指数（外部）：代码, 显示名, 解读
BROAD_INDICES = [
    ("000001", "上证指数", "权重护盘，最抗跌"),
    (*resolve_market_reference("801001"), "跨行业龙头市场参照"),
    ("000016", "上证50", "大盘蓝筹，防御属性"),
    ("000300", "沪深300", "核心资产"),
    ("000905", "中证500", "中盘"),
    ("000852", "中证1000", "小盘，昨日大涨后回吐"),
    ("399001", "深证成指", "成长含量高"),
    ("399006", "创业板指", "成长领跌"),
]

# 市场参照直接使用中证A50或上证50的实际代码，不查询801001，
# 不在外部宽基失败后退回申万50；补充路由由Agent执行。

# 风格指数代码 → 展示名
STYLE_CODES = {
    "801811": "大盘", "801812": "中盘", "801813": "小盘",
    "801821": "高市盈率", "801822": "中市盈率", "801823": "低市盈率",
    "801831": "高市净率", "801832": "中市净率", "801833": "低市净率",
    "801841": "高价股", "801842": "中价股", "801843": "低价股",
    "801851": "亏损股", "801852": "微利股", "801853": "绩优股",
}


def _pct_str(v):
    try:
        return f"{float(v):+.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _safe_int(v):
    """将 JSON 中的数值（可能是 int/float/字符串/千分位字符串）转为 int，失败返回 0。"""
    if v is None:
        return 0
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return int(v)
    try:
        return int(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0


def _fetch_broad_indices():
    """拉外部宽基指数（腾讯行情），返回 list[(name, chg, c20, ytd, px, note)]。
    仅返回已核实的宽基数据；补充由Agent使用westock skill/websearch。"""
    results = []
    used_fallback = False
    try:
        today = datetime.date.today()
        start = (today - datetime.timedelta(days=400)).strftime("%Y%m%d")
        end = today.strftime("%Y%m%d")
        for code, name, note in BROAD_INDICES:
            try:
                if not is_supported_index(code):
                    continue
                data = index_daily(code, start, end)
                bars = data.get("bars") or []
                if len(bars) < 2:
                    continue
                # 最后一条为最新（盘中为实时 bar）
                last = bars[-1]
                prev = bars[-2]
                chg = (float(last["close"]) / float(prev["close"]) - 1) * 100
                # 近20日：找 20 个交易日前的收盘
                c20_base = bars[-21]["close"] if len(bars) > 21 else bars[0]["close"]
                c20 = (float(last["close"]) / float(c20_base) - 1) * 100
                # YTD uses the last observation before the current year.
                cutoff=str(int(last['date'][:4])-1)+'1231'
                ytd_base=next((float(b['close']) for b in reversed(bars) if b['date'].replace('-','')[:8]<=cutoff),None)
                ytd=(float(last['close'])/ytd_base-1)*100 if ytd_base else None
                results.append((name, round(chg, 2), round(c20, 2), round(ytd, 2)
                                if ytd is not None else None,
                                float(last["close"]), note, last["date"]))
            except Exception as e:
                print(f"[sw_style_report] {name} 抓取失败: {e}", file=sys.stderr)
                continue
    except Exception as e:
        print(f"[sw_style_report] 外部宽基指数不可达: {e}", file=sys.stderr)

    if len(results) >= 3:
        return results, used_fallback

    # Partial coverage stays in the actual external-index names and dates.
    used_fallback = True
    return results, used_fallback


def _fetch_styles():
    """拉申万风格指数，返回 list[(name, chg, label)]（按涨跌排序）。"""
    snap = fetch_snapshot_batch("风格指数")
    found = {r["code"]: r["change_pct"] for r in snap}
    styles = []
    for code, name in STYLE_CODES.items():
        if code in found:
            label = ""
            if code.startswith("80182"):
                label = "成长" if code == "801821" else ("价值" if code == "801823" else "")
            elif code.startswith("80183"):
                label = "价值" if code == "801833" else ""
            styles.append((name, found[code], label))
    return styles


def _fetch_sectors():
    """拉申万一级行业，返回 list[(name, chg)] + (up, down, total_amount_亿)。"""
    snap = fetch_snapshot_batch("一级行业")
    sectors = [(r["name"], r["change_pct"]) for r in snap if r.get("name")]
    up = sum(1 for _, c in sectors if c > 0)
    down = sum(1 for _, c in sectors if c < 0)
    total_amount = round(sum(r.get("amount") or 0 for r in snap), 1)
    return sectors, up, down, total_amount


def _determine_dominance(styles):
    """市值/估值风格判断（原 sw_style.py 的判定逻辑迁入，阈值不变）。"""
    big = mid = small = None
    high_pe = low_pe = None
    for name, chg, _ in styles:
        if name == "大盘":
            big = chg
        elif name == "中盘":
            mid = chg
        elif name == "小盘":
            small = chg
        elif name == "高市盈率":
            high_pe = chg
        elif name == "低市盈率":
            low_pe = chg
    big_pct = big or 0
    small_pct = small or 0
    mid_pct = mid or 0
    if big_pct > small_pct and big_pct > mid_pct:
        size = "大盘占优"
    elif small_pct > big_pct and small_pct > mid_pct:
        size = "小盘活跃"
    elif mid_pct > big_pct:
        size = "中小盘活跃"
    else:
        size = "风格均衡"
    high_pe_pct = high_pe or 0
    low_pe_pct = low_pe or 0
    if high_pe_pct > low_pe_pct + 0.3:
        val = "成长风格占优"
    elif low_pe_pct > high_pe_pct + 0.3:
        val = "价值风格占优"
    else:
        val = "成长价值均衡"
    return size, val


def main():
    parser = argparse.ArgumentParser(description="今日市场风格分析研报（HTML）")
    parser.add_argument("--output", default=None, help="输出目录（默认 <工作目录>）")
    parser.add_argument("--breadth-json", default=None,
                        help="市场广度数据 JSON（neodata 大盘市场宽度统计/两融统计，必填）")
    args = parser.parse_args()

    try:
        today = datetime.date.today()
        date_label = today.strftime("%Y-%m-%d")

        # 1) 风格指数
        styles = _fetch_styles()
        if not styles:
            raise RuntimeError("未获取到风格指数数据")
        size_style, val_style = _determine_dominance(styles)

        # 2) 一级行业
        sectors, s_up, s_down, s_amount = _fetch_sectors()

        # 3) 外部宽基指数
        broad, used_fallback = _fetch_broad_indices()

        # 4) 广度与情绪：必须来自 neodata 数据（大盘市场宽度统计/两融统计），
        #    经 --breadth-json 传入；脚本不自取、不做行业级兜底。
        breadth = {}
        if not args.breadth_json or not os.path.exists(args.breadth_json):
            print(json.dumps({
                "status": "error",
                "message": "缺少市场广度数据：请先通过 WorkBuddy 数据源获取 neodata「大盘市场宽度统计」"
                           "（沪深涨跌家数、涨停/跌停、成交额）与「两融统计」（两融余额），"
                           "按 SW_STYLE_REPORT.md 的 JSON 结构写入文件后，用 --breadth-json 传入。"
            }, ensure_ascii=False), file=sys.stderr)
            sys.exit(1)

        with open(args.breadth_json, encoding="utf-8") as f:
            ext = json.load(f)
        breadth = {
            "up_down": f"{ext.get('up','—')} / {ext.get('down','—')}",
            "up_down_note": ext.get("up_down_note", "沪深两市个股（全市场口径）"),
            "limit": f"{ext.get('limit_up','—')} / {ext.get('limit_down','—')}",
            "limit_note": ext.get("limit_note", ""),
            "amount": ext.get("amount", "—"),
            "amount_note": ext.get("amount_note", ""),
            "margin": ext.get("margin", "—"),
            "margin_note": ext.get("margin_note", ""),
            "sentiment": ext.get("sentiment", "—"),
            "sentiment_note": ext.get("sentiment_note", ""),
        }
        breadth_scope = "全市场个股口径（neodata 大盘市场宽度统计 / 两融统计）"
        breadth["size_style"] = size_style
        breadth["size_note"] = (
            f"大盘{_pct_str(dict((n,c) for n,c,_ in styles).get('大盘',0))}% / "
            f"中盘{_pct_str(dict((n,c) for n,c,_ in styles).get('中盘',0))}% / "
            f"小盘{_pct_str(dict((n,c) for n,c,_ in styles).get('小盘',0))}%"
        )
        breadth["val_style"] = val_style
        breadth["val_note"] = (
            f"低PE{_pct_str(dict((n,c) for n,c,_ in styles).get('低市盈率',0))}% vs "
            f"高PE{_pct_str(dict((n,c) for n,c,_ in styles).get('高市盈率',0))}%"
        )
        breadth["overall_style"] = val_style if "价值" in val_style or "均衡" in val_style else "成长风格"
        breadth["overall_note"] = "低估值防御方向相对抗跌" if "价值" in val_style else "风格切换观察中"

        # 个股广度（来自 neodata 数据）
        b_up = _safe_int(ext.get("up"))
        b_down = _safe_int(ext.get("down"))
        b_total = b_up + b_down
        b_up_ratio = b_up / b_total if b_total else None
        breadth_weak = (b_up_ratio is not None and b_up_ratio < 0.4)

        # 5) 判定表
        verdict_rows = [
            ("市场档位", "震荡切换档", "指数震荡、热点轮动加快，存量博弈"),
            ("市值风格", size_style, f"大盘{_pct_str(dict((n,c) for n,c,_ in styles).get('大盘',0))}% / 小盘{_pct_str(dict((n,c) for n,c,_ in styles).get('小盘',0))}%"),
            ("估值风格", val_style, "低PE/低PB 相对占优，防御属性资金主导"),
            ("行业结构", "资源防御走强" if s_up < s_down else "普涨格局",
             f"行业 {s_up}涨/{s_down}跌，领涨方向见上方轮动图"),
            ("广度质量", "偏弱" if breadth_weak else "偏强",
             f"个股上涨 {b_up} 家 / 下跌 {b_down} 家（全市场口径），"
             f"赚钱效应{'弱' if breadth_weak else '强'}"),
            ("操作含义", "控制仓位、做短不做长",
             "精选低位顺周期/资源；高位硬科技以波段思维，勿追高"),
        ]
        verdict_note = (
            "切换前置信号（后续观察）：① 资源周期放量滞涨→补涨或一日游；"
            "② 高位科技缩量企稳→超跌反弹可期；"
            "③ 个股上涨家数占比连续回升至 50% 以上→情绪修复确认；"
            "④ 两融余额快速放大或维持担保比例跌破 270%→杠杆风险上升。"
        )
        verdict = {"rows": verdict_rows, "note": verdict_note}

        # 6) 文字摘要
        top3 = sorted(sectors, key=lambda x: x[1], reverse=True)[:3]
        bot3 = sorted(sectors, key=lambda x: x[1])[:3]
        top_str = "、".join(f"{n} {_pct_str(c)}%" for n, c in top3)
        bot_str = "、".join(f"{n} {_pct_str(c)}%" for n, c in bot3)

        # 宽基指数摘要
        if broad:
            b_up_idx = sum(1 for _, c, _, _, _, _, _ in broad if c >= 0)
            b_down_idx = len(broad) - b_up_idx
            idx_summary = f"宽基指数 {b_up_idx} 涨 {b_down_idx} 跌"
        else:
            idx_summary = "本次风格判断聚焦已核实的行业表现"

        breadth_phrase = "偏弱" if breadth_weak else "偏强"
        tldr = (
            f"今日 A 股{idx_summary}，风格层面<b>{val_style}</b>（低PE/低PB 相对抗跌），"
            f"市值上<b>{size_style}</b>。行业层面 {s_up} 涨 {s_down} 跌，"
            f"领涨：{top_str}；领跌：{bot_str}。市场广度{breadth_phrase}"
            f"（个股上涨 {b_up} 家 / 下跌 {b_down} 家，上涨占比 {b_up_ratio*100:.0f}%），"
            f"成交额 {ext.get('amount','—')}——整体呈{'存量切换、高位兑现' if breadth_weak else '相对健康'}特征。"
        )
        sector_note = (
            f"领涨方向（{s_up} 个行业）：{top_str}。领跌方向：{bot_str}。"
            "（具体驱动因素可结合当日新闻、政策与隔夜外盘判断）"
        )
        breadth_note = (
            f"广度诊断：个股上涨 {b_up} 家 / 下跌 {b_down} 家（上涨占比 {b_up_ratio*100:.0f}%），"
            f"{'广度偏弱，赚钱效应差，属聚焦过度的脆弱结构' if breadth_weak else '广度较好，普涨格局'}。"
            f"数据口径：{breadth_scope}。"
        )

        source_note = {
            "idx": "数据来源：腾讯行情（外部宽基指数，最新交易日收盘/盘中）"
                   + ("；市场参照范围以本页实际展示的宽基指数为准" if used_fallback else ""),
            "style": "数据来源：腾讯自选股（申万行业板块口径），行情可能有延迟，以交易所披露为准",
            "sector": "数据来源：腾讯自选股（申万行业板块口径），行情可能有延迟，以交易所披露为准",
            "breadth": f"数据来源：neodata 大盘市场宽度统计 / 两融统计（{date_label}）",
            "all": "腾讯自选股（申万行业板块口径），行情可能有延迟，以交易所披露为准、腾讯行情（外部宽基指数）、"
                   "neodata 大盘市场宽度统计 / 两融统计（市场广度与情绪）"
                   + f"。行情数据为 {date_label} 快照，收盘数据以交易所披露为准。",
        }

        out_dir = args.output or get_workspace_dir()
        html_path = render_style_report(
            out_dir,
            indices=[(n, c, f"{c20:+.2f}", f"{ytd:+.2f}" if ytd is not None else "—",
                      px, note) for n, c, c20, ytd, px, note, _ in broad],
            styles=styles,
            industries=sectors,
            breadth=breadth,
            verdict=verdict,
            source_note=source_note,
            date_label=date_label,
            tldr=tldr,
            sector_note=sector_note,
            breadth_note=breadth_note,
            style_headline=f"{val_style}，{size_style}",
            sector_headline="资源防御走强" if s_up < s_down else "行业普涨",
            breadth_headline=f"广度{'偏弱' if breadth_weak else '偏强'}（全市场个股口径）",
        )

        summary = {
            "status": "ok",
            "mode": "style_report",
            "date": date_label,
            "dominance": {"size": size_style, "valuation": val_style},
            "sectors": {"up": s_up, "down": s_down, "total_amount_yi": s_amount},
            "breadth": {"up": b_up, "down": b_down,
                        "limit_up": ext.get("limit_up"), "limit_down": ext.get("limit_down"),
                        "amount": ext.get("amount"), "margin": ext.get("margin"),
                        "sentiment": ext.get("sentiment")},
            "top3": [{"name": n, "chg": c} for n, c in top3],
            "bottom3": [{"name": n, "chg": c} for n, c in bot3],
            "broad_indices": [{"name": n, "chg": c} for n, c, _, _, _, _, _ in broad],
            "breadth_scope": breadth_scope,
            "render_files": {"style-report": {"html": html_path}},
        }
        print(json.dumps(summary, ensure_ascii=False))

    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False),
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
