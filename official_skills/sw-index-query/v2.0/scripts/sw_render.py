#!/usr/bin/env python3
"""HTML render adapter: converts emit payloads into interactive HTML pages.

纯标准库实现（无任何外部依赖）。当平台 artifact client 缺失（纯 CLI /
WorkBuddy 等本地环境）时，sw_common 的 emit_* 不再静默 no-op，而是把
data/final 阶段的 payload 交给本模块渲染为交互式 HTML 图表页面
（ECharts CDN，红涨绿跌），写入 <工作目录>/.swi/render/。

图表渲染全部委托 `sw_html_render.py`（line/kline/heatmap/bar/pie/scatter/
matrix/histogram/indicator/md_table 的 HTML 版本）；本模块只负责按
template + payload 结构做分发、组装 build_page，并保留 Markdown 表格
（md_table / md_table_from_payload）供 valuation / period_rank /
latest_announcements 等纯表格脚本使用。

SVG 渲染已完全移除（2026-08-19）：所有图表统一输出交互式 HTML，
Agent 用 present_files 推送 render_files.*.html 即可。
"""

from __future__ import annotations

import json
import os
import re
import uuid

# ── 调色板（中国习惯：涨=红 #E24B4A，跌=绿 #1D9E75）────────────────────────
UP = "#E24B4A"          # 涨/红
DOWN = "#1D9E75"        # 跌/绿
FLAT = "#888780"
TEXT = "#2C2C2A"
MUTED = "#5F5E5A"
GRID = "#D3D1C7"
BG = "#FFFFFF"
ACCENT = "#378ADD"      # 基准线/折线
ACCENT2 = "#534AB7"
ACCENT3 = "#BA7517"
POOL = ["#378ADD", "#E24B4A", "#1D9E75", "#BA7517", "#534AB7", "#1ABC9C"]


def _num(v, digits=2) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.{digits}f}"
    except (TypeError, ValueError):
        return str(v)


def _sign(v, digits=2) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):+.{digits}f}"
    except (TypeError, ValueError):
        return str(v)


def _write_file(out_dir: str, identifier: str, ext: str, content: str) -> str:
    """把内容写入 out_dir/identifier.ext，返回绝对路径。"""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{identifier}.{ext}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return os.path.abspath(path)


# ── Markdown 表格（纯表格脚本保留使用）──────────────────────────────────────

def md_table(title: str, headers: list, rows: list, *, aligns: list | None = None,
             description: str = "") -> str:
    """headers: [col...]；rows: [[cell...], ...]。返回 Markdown 表格字符串。"""
    if not headers:
        return ""
    out = []
    if title:
        out.append(f"**{title}**")
    if description:
        out.append(f"> {description}")
    out.append("")
    out.append("| " + " | ".join(str(h) for h in headers) + " |")
    out.append("|" + "|".join("---" for _ in headers) + "|")
    for row in rows:
        cells = [str(c) if c is not None else "—" for c in row]
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"


def md_table_from_payload(payload: dict) -> str:
    """把 pi-table 格式 payload {title, description, columns, rows} 转为 Markdown。"""
    title = payload.get("title", "")
    description = payload.get("description", "")
    cols = payload.get("columns") or []
    rows = payload.get("rows") or []
    headers = [c.get("title", c.get("key", "")) for c in cols]
    keys = [c.get("key", "") for c in cols]
    body = []
    for r in rows:
        body.append([r.get(k) for k in keys])
    return md_table(title, headers, body, description=description)


# ── 统一分发：根据 template + payload 结构渲染为交互式 HTML ─────────────────

_RENDER_DIR_HINT = None


def set_render_dir(path: str):
    """设置渲染输出目录（供 sw_common 调用）。"""
    global _RENDER_DIR_HINT
    _RENDER_DIR_HINT = path


def _flatten_tech_indicators(data: dict) -> dict:
    """把 sw_tech 嵌套的指标结构展开为 indicator_chart_html 期望的平铺字段。

    sw_tech 的 payload 中 boll/macd/kdj/adx 各为 dict（如 {"mid","upper","lower"}、
    {"dif","dea","hist"}、{"k","d","j"}、{"di_plus","di_minus","adx"}），
    其余指标（rsi/cci/atr/obv）本身平铺。此处统一展开为平铺键。
    """
    ind: dict = {}
    boll = data.get("boll") or {}
    if isinstance(boll, dict):
        ind["boll_mid"] = boll.get("mid")
        ind["boll_up"] = boll.get("upper")
        ind["boll_low"] = boll.get("lower")
    macd = data.get("macd") or {}
    if isinstance(macd, dict):
        ind["dif"] = macd.get("dif")
        ind["dea"] = macd.get("dea")
        ind["macd"] = macd.get("hist")  # MACD 柱（hist）
    kdj = data.get("kdj") or {}
    if isinstance(kdj, dict):
        ind["k"] = kdj.get("k")
        ind["d"] = kdj.get("d")
        ind["j"] = kdj.get("j")
    adx = data.get("adx") or {}
    if isinstance(adx, dict):
        ind["adx"] = adx.get("adx")
        ind["di_plus"] = adx.get("di_plus")
        ind["di_minus"] = adx.get("di_minus")
    for key in ("rsi", "cci", "atr", "obv"):
        if data.get(key):
            ind[key] = data[key]
    return ind


def render_payload(template: str, identifier: str, title: str,
                   data: dict, meta: dict | None = None,
                   out_dir: str | None = None) -> dict:
    """把 emit 的 data payload 渲染为交互式 HTML 页面（+ Markdown 表格）。

    Returns: {"svg": None, "md": path|None, "html": path|None}
    svg 恒为 None（SVG 渲染已移除），html 为 ECharts 交互页。
    """
    if not isinstance(data, dict) or not data:
        return {"svg": None, "md": None, "html": None}

    out_dir = out_dir or _RENDER_DIR_HINT or "workspace/.swi/render"
    ident = re.sub(r"[^A-Za-z0-9_.-]", "-", identifier or uuid.uuid4().hex[:8])

    # 交互式 HTML 渲染器（惰性导入，避免循环依赖）
    try:
        from sw_html_render import (
            build_page, line_chart_html, kline_chart_html, heatmap_chart_html,
            bar_chart_h_html, pie_chart_html, scatter_chart_html,
            matrix_chart_html, histogram_chart_html, md_table_html,
            indicator_chart_html,
        )
    except ImportError:
        build_page = line_chart_html = kline_chart_html = indicator_chart_html = None

    md_path = html_path = None
    html_parts = []
    from sw_html_render import default_source_note
    html_source = (meta or {}).get("data_note") or default_source_note()

    # ── 分时图 SW_RT ──
    if template == "SW_RT" and data.get("times") and data.get("prices"):
        m = meta or {}
        pc = m.get("prev_close")
        series = [{"name": "价格", "values": data["prices"], "color": ACCENT}]
        if pc:
            series.append({"name": "昨收", "values": [pc] * len(data["times"]), "color": GRID})
        if line_chart_html:
            html_parts.append(line_chart_html(title, data["times"], series, y_label="价格"))

    # ── K线 SW_KL / SW_IND / 深度 SW_DEEP / 技术 SW_TECH 共用蜡烛图 ──
    #    SW_IND / SW_TECH 额外渲染指标综合图（BOLL + 下方指标子图）
    elif (template in ("SW_KL", "SW_IND", "SW_DEEP", "SW_TECH")
          and ((data.get("labels") and data.get("close"))
               or (isinstance(data.get("kline"), dict)
                   and data["kline"].get("labels") and data["kline"].get("close")))):
        kline = data.get("kline") if isinstance(data.get("kline"), dict) else data
        labels = data.get("labels") or kline.get("labels", [])
        opens = data.get("open") or kline.get("open", [])
        highs = data.get("high") or kline.get("high", [])
        lows = data.get("low") or kline.get("low", [])
        closes = data.get("close") or kline.get("close", [])
        ma5 = data.get("ma5") or kline.get("ma5")
        ma10 = data.get("ma10") or kline.get("ma10")
        ma20 = data.get("ma20") or kline.get("ma20")
        volumes = data.get("volumes") or kline.get("volumes")
        if template == "SW_IND" and indicator_chart_html:
            # 指标综合图：主图 K线+MA+BOLL，下方 MACD/KDJ/RSI/CCI/ATR/ADX/OBV 子图
            html_parts.append(indicator_chart_html(
                title, labels, opens, highs, lows, closes,
                ma5=ma5, ma10=ma10, ma20=ma20, volumes=volumes, indicators=data,
            ))
        elif template == "SW_TECH" and indicator_chart_html:
            # sw_tech 指标数据为嵌套结构，展开为平铺后渲染全指标子图
            html_parts.append(indicator_chart_html(
                title, labels, opens, highs, lows, closes,
                ma5=ma5, ma10=ma10, ma20=ma20, volumes=volumes,
                indicators=_flatten_tech_indicators(data),
            ))
            # sw_tech --event 追加的事件后验区块（行情折线 + 收益分布 + 统计表）
            if data.get("chart_closes") and data.get("event_label"):
                e_dates = data.get("chart_dates") or []
                e_series = [{"name": "收盘", "values": data["chart_closes"], "color": ACCENT}]
                if line_chart_html:
                    html_parts.append(line_chart_html(
                        f"{data['event_label']} 行情", e_dates, e_series, y_label="收盘价"))
                h = data.get("histogram")
                if h and h.get("edges") and histogram_chart_html:
                    html_parts.append(histogram_chart_html(
                        f"{data['event_label']} 后{data.get('forward_days', 20)}日收益分布",
                        h["edges"], h["counts"]))
                if data.get("stats") and md_table_html:
                    s = data["stats"]
                    rows = [
                        ["事件次数", str(data.get("events_count", 0))],
                        ["平均前向收益", _sign(s.get("avg_forward_return")) + "%"],
                        ["中位数前向收益", _sign(s.get("median_forward_return")) + "%"],
                        ["胜率", _num(s.get("win_rate") * 100, 1) + "%"],
                        ["最佳 / 最差",
                         f"{_sign(s.get('best', {}).get('return'))}% ({s.get('best', {}).get('date', '—')}) / "
                         f"{_sign(s.get('worst', {}).get('return'))}% ({s.get('worst', {}).get('date', '—')})"],
                    ]
                    html_parts.append(md_table_html(
                        f"{data['event_label']} 后{data.get('forward_days', 20)}日统计",
                        ["指标", "数值"], rows))
        elif kline_chart_html:
            html_parts.append(kline_chart_html(
                title, labels, opens, highs, lows, closes,
                ma5=ma5, ma10=ma10, ma20=ma20, volumes=volumes,
            ))

    # ── 对比 SW_CMP：多指数归一化折线 ──
    elif template == "SW_CMP" and data.get("series"):
        series = []
        cmp_labels = []
        for s in data["series"]:
            if "error" in s:
                continue
            vals = s.get("pctChanges") or []
            slabels = s.get("labels") or s.get("times") or []
            if not cmp_labels:
                cmp_labels = slabels
            series.append({"name": s.get("name", s.get("code", "")), "values": vals,
                           "color": s.get("color", ACCENT)})
        if series and line_chart_html:
            html_parts.append(line_chart_html(title, cmp_labels, series, y_label="涨跌幅%"))

    # ── 市场全景 SW_DASH：行业涨跌条形图 ──
    elif template == "SW_DASH" and data.get("industries"):
        inds = data["industries"]
        items = [{"name": x.get("name", ""), "value": x.get("change_pct", 0)} for x in inds]
        if bar_chart_h_html:
            html_parts.append(bar_chart_h_html(title, items, value_label="pct", color_by_sign=True))

    # ── 热力图 SW_HEAT ──
    elif template == "SW_HEAT" and data.get("industries"):
        fields = ["today", "d5", "d20", "d60", "ytd"]
        flabels = {"today": "今日", "d5": "5日", "d20": "20日", "d60": "60日", "ytd": "YTD"}
        if heatmap_chart_html:
            html_parts.append(heatmap_chart_html(title, data["industries"], fields, field_labels=flabels))
        if data.get('quadrants') and scatter_chart_html:
            points = [dict(name=x['name'],x=x['d20'],y=x['d5']) for x in data['industries']]
            html_parts.append(scatter_chart_html('行业轮动四象限（右上领涨、左上改善、左下落后、右下回落）',
                points,x_label='20日收益%',y_label='5日收益%',mark_lines=[{'x':0,'label':'趋势零线'},{'y':0,'label':'动量零线'}]))
        if bar_chart_h_html:
            html_parts.append(bar_chart_h_html('今日行业涨跌排序',
                [{'name':x['name'],'value':x['today']} for x in data['industries']],value_label='pct',color_by_sign=True))

    # ── 群组 SW_GRP：归一化折线 ──
    elif template == "SW_GRP" and data.get("indices"):
        labels = data.get("labels") or []
        series = []
        colors = data.get("colors") or POOL
        for i, d in enumerate(data["indices"]):
            series.append({"name": d.get("name", ""), "values": d.get("normalized", []),
                           "color": colors[i % len(colors)]})
        if series and line_chart_html:
            html_parts.append(line_chart_html(title, labels, series, y_label="涨跌幅%"))

    # ── 回归 SW_REG（template 笔误为 SW_DEEP，靠 data.metrics 识别）──
    elif (template in ("SW_DEEP", "SW_REG") and data.get("metrics")
          and data.get("norm_a") is not None):
        labels = data.get("dates") or []
        series = [
            {"name": data.get("name_a", "A"), "values": data.get("norm_a", []), "color": UP},
            {"name": data.get("name_b", "B"), "values": data.get("norm_b", []), "color": ACCENT},
        ]
        if line_chart_html:
            html_parts.append(line_chart_html(title, labels, series, y_label="归一化%"))
        m = data.get("metrics", {})
        headers = ["指标", "数值"]
        rows = [
            ["相关系数", _num(m.get("correlation"), 4)],
            ["Beta", _num(m.get("beta"), 4)],
            ["年化 Alpha", _sign(m.get("alpha_annual_pct")) + "%"],
            ["年化追踪误差", _num(m.get("tracking_error_pct")) + "%"],
            ["信息比率", _num(m.get("info_ratio"), 2)],
            ["累计收益 A / B", f"{_sign(m.get('cum_return_a'))}% / {_sign(m.get('cum_return_b'))}%"],
            ["累计超额收益", _sign(m.get("excess_return")) + "%"],
            ["最大回撤 A", _num(m.get("max_drawdown_a")) + "%"],
        ]
        md_path = _write_file(out_dir, ident + "-metrics", "md", md_table(title, headers, rows))
        if md_table_html:
            html_parts.append(md_table_html(title + " 指标", headers, rows))

    # ── 收益风险矩阵 SW_RISK：散点图（均值分割线 + 收益风险比着色 + 说明）──
    elif template == "SW_RISK" and data.get("industries"):
        inds = data["industries"]
        pts = [{"name": x.get("name"), "x": x.get("y1_vol"), "y": x.get("y1_return"),
                "ratio": x.get("ratio"), "ytd": x.get("ytd_return"),
                "m1": x.get("m1_return"), "m3": x.get("m3_return")}
               for x in inds]
        if scatter_chart_html:
            vol_vals = [x.get("y1_vol") for x in inds if x.get("y1_vol") is not None]
            ret_vals = [x.get("y1_return") for x in inds if x.get("y1_return") is not None]
            mark_lines = []
            if vol_vals:
                mark_lines.append({"x": round(sum(vol_vals) / len(vol_vals), 2),
                                   "label": "均值波动"})
            if ret_vals:
                mark_lines.append({"y": round(sum(ret_vals) / len(ret_vals), 2),
                                   "label": "均值收益"})
            html_parts.append(scatter_chart_html(
                title, pts, x_key="x", y_key="y", name_key="name",
                x_label="年化波动率%", y_label="年化收益%",
                color_key="ratio", color_label="收益风险比",
                mark_lines=mark_lines,
                tooltip_extra=[
                    {"label": "收益风险比", "key": "ratio"},
                    {"label": "YTD", "key": "ytd"},
                    {"label": "近1月", "key": "m1"},
                    {"label": "近3月", "key": "m3"},
                ]))

    # ── 排名 SW_RANK：Markdown 表格 ──
    elif template == "SW_RANK" and data.get("items"):
        rows = []
        headers = ["排名", "指数", "代码", "YTD%", "1月%", "3月%", "1年%", "年化波动%", "最大回撤%", "Calmar", "Sharpe"]
        for it in data["items"]:
            rows.append([
                it.get("rank", ""), it.get("name", ""), it.get("code", ""),
                _num(it.get("ytd_return")), _num(it.get("m1_return")),
                _num(it.get("m3_return")), _num(it.get("y1_return")),
                _num(it.get("ytd_vol")), _num(it.get("max_drawdown")),
                _num(it.get("calmar")), _num(it.get("sharpe")),
            ])
        desc = f"按 {data.get('sortLabel', '')} 排序 · 共 {len(rows)} 个指数"
        md_path = _write_file(out_dir, ident + "-rank", "md", md_table(title, headers, rows, description=desc))
        if md_table_html:
            html_parts.append(md_table_html(title, headers, rows, description=desc))

    # ── 成分股 SW_COMP：饼图 + 表格 ──
    elif template == "SW_COMP":
        if data.get("pieData") and pie_chart_html:
            html_parts.append(pie_chart_html(title, data["pieData"]))
        if data.get("items"):
            rows = [[it.get("rank"), it.get("name"), it.get("code"),
                     _num(it.get("weight")) + "%", it.get("beginDate", "")[:10]]
                    for it in data["items"][:50]]
            headers = ["排名", "名称", "代码", "权重%", "纳入日期"]
            desc = f"共 {data.get('totalItemCount', len(rows))} 只成分"
            md_path = _write_file(out_dir, ident + "-comp", "md", md_table(title + " 成分", headers, rows, description=desc))
            if md_table_html:
                html_parts.append(md_table_html(title + " 成分", headers, rows, description=desc))

    # ── 历史分位 SW_QUANTILE：折线 + 表格 ──
    elif template == "SW_QUANTILE" and data.get("values"):
        labels = data.get("dates") or []
        vals = data.get("values", [])
        series = [{"name": data.get("metric_label", ""), "values": vals, "color": ACCENT}]
        if line_chart_html:
            html_parts.append(line_chart_html(title, labels, series, y_label=data.get("metric_label", "")))
        s = data.get("stats", {})
        suffix = data.get("suffix", "")
        rows = [
            ["当前值", f"{_num(s.get('current'))}{suffix}"],
            ["历史分位", f"{_num(s.get('percentile'), 1)}%"],
            ["区间判断", s.get("category", "—")],
            ["历史最低 / 最高", f"{_num(s.get('min'))}{suffix} / {_num(s.get('max'))}{suffix}"],
            ["中位数 / P25 / P75", f"{_num(s.get('median'))} / {_num(s.get('p25'))} / {_num(s.get('p75'))}"],
            ["样本数", str(data.get("samples_count", ""))],
        ]
        headers = ["指标", "数值"]
        md_path = _write_file(out_dir, ident + "-q", "md", md_table(title + " 分位", headers, rows, description=data.get("range", "")))
        if md_table_html:
            html_parts.append(md_table_html(title + " 分位", headers, rows, description=data.get("range", "")))

    # ── 全指标快照 SW_STATS：净值折线 + 表格 ──
    elif template == "SW_STATS" and data.get("sampled_closes"):
        labels = data.get("sampled_dates") or []
        series = [{"name": "累计净值", "values": data["sampled_closes"], "color": ACCENT}]
        if line_chart_html:
            html_parts.append(line_chart_html(title + " 净值", labels, series, y_label="收盘价"))
        s = data.get("stats", {})
        rows = [
            ["区间", s.get("range", "—")],
            ["年化收益", _sign(s.get("annual_return")) + "%"],
            ["年化波动", _num(s.get("annual_vol")) + "%"],
            ["Sharpe", _num(s.get("sharpe"))],
            ["Calmar", _num(s.get("calmar"))],
            ["最大回撤", _num(s.get("max_drawdown")) + "%"],
            ["日胜率 / 月胜率", f"{_num(s.get('win_rate_day'))}% / {_num(s.get('win_rate_month'))}%"],
            ["PE / PB", f"{_num(s.get('pe'))} / {_num(s.get('pb'))}"],
            ["股息率 / 换手", f"{_num(s.get('dp'))}% / {_num(s.get('turnover'))}%"],
        ]
        headers = ["指标", "数值"]
        md_path = _write_file(out_dir, ident + "-stats", "md", md_table(title + " 指标", headers, rows))
        if md_table_html:
            html_parts.append(md_table_html(title + " 指标", headers, rows))

    # ── 相关性矩阵 SW_CORR ──
    elif template == "SW_CORR" and data.get("matrix"):
        if matrix_chart_html:
            html_parts.append(matrix_chart_html(title, data.get("names", []), data["matrix"]))

    # ── 指数组合 SW_PORTFOLIO：净值折线 ──
    elif template == "SW_PORTFOLIO" and data.get("port_curve"):
        labels = data.get("sampled_dates") or []
        series = [{"name": "组合", "values": data["port_curve"], "color": UP}]
        if data.get("bench_curve"):
            series.append({"name": "基准", "values": data["bench_curve"], "color": GRID})
        if line_chart_html:
            html_parts.append(line_chart_html(title, labels, series, y_label="累计净值"))

    # ── 组装交互式 HTML 页面 ──
    if build_page is not None and html_parts:
        try:
            subtitle = title + (" · 数据截至 " + meta["as_of"] if meta and meta.get("as_of") else "")
            html_doc = build_page(title, subtitle, html_parts, html_source)
            html_path = _write_file(out_dir, ident + "-html", "html", html_doc)
        except Exception as e:
            print(f"[sw_render] {ident} HTML 渲染失败: {e}", file=sys.stderr)
            html_path = None

    return {"svg": None, "md": md_path, "html": html_path}
