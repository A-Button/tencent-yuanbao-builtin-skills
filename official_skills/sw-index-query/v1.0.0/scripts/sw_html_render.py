#!/usr/bin/env python3
"""通用图表 HTML 渲染器：把分析结果渲染为可交互 HTML 网页（ECharts）。

纯标准库实现（仅依赖 json / os），无外部依赖。与 `sw_render.py` 的 SVG 渲染
一一对应，为同一份 payload 生成交互式 HTML 版本：

  - 折线图（多系列）        line_chart_html
  - 蜡烛图（K线+MA+量）     kline_chart_html
  - 热力图（行业多周期）     heatmap_chart_html
  - 横向条形图              bar_chart_h_html
  - 饼图                    pie_chart_html
  - 散点图（收益风险矩阵）  scatter_chart_html
  - 相关矩阵热力图          matrix_chart_html
  - 直方图                  histogram_chart_html
  - Markdown 表格 → HTML 表  md_table_html

设计要点：
  - A 股配色：红涨绿跌（#e03131 / #0ca678），浅底深字研报风
  - ECharts 5 CDN 渲染，全部图表支持 tooltip / dataZoom 缩放 / legend 切换
  - 每个图表函数返回 (div_html, script_js)；`build_page` 组装为完整 HTML 文档
  - 数据用 json.dumps 注入，避免手写嵌套结构

对外接口：
    build_page(title, subtitle, parts, source_note) -> str   # 完整 HTML
    各图表函数 -> {"div": str, "script": str}
"""

from __future__ import annotations

import json

ECHARTS_CDN = '<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>'

UP = "#e03131"
DOWN = "#0ca678"
ACCENT = "#2d3e63"
ACCENT2 = "#1971c2"
ACCENT3 = "#862e9c"
ACCENT4 = "#f59f00"
GRID = "#c6ccd9"
POOL = ["#378ADD", "#e03131", "#0ca678", "#f59f00", "#862e9c", "#12b886",
        "#e8590c", "#1971c2", "#f783ac", "#1098ad"]

_PAGE_CSS = """
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:"PingFang SC","Microsoft YaHei",sans-serif; background:#f5f6fa; color:#1f2430; padding:24px; }
  .wrap { max-width:1080px; margin:0 auto; }
  .header { background:linear-gradient(135deg,#1f2a44,#2d3e63); color:#fff; border-radius:12px; padding:20px 26px; margin-bottom:18px; }
  .header h1 { font-size:21px; margin-bottom:6px; }
  .header .sub { color:#b9c4dd; font-size:13px; }
  .card { background:#fff; border-radius:12px; padding:16px 20px; margin-bottom:16px; box-shadow:0 1px 4px rgba(20,30,60,.06); }
  .card h2 { font-size:15px; margin-bottom:10px; color:#1f2430; border-left:4px solid #2d3e63; padding-left:10px; }
  .chart { width:100%; height:360px; }
  .chart-sm { width:100%; height:280px; }
  .up { color:#e03131 !important; }
  .down { color:#0ca678 !important; }
  table { width:100%; border-collapse:collapse; font-size:13px; margin-top:6px; }
  th,td { padding:7px 9px; text-align:right; border-bottom:1px solid #eef0f5; }
  th { background:#f7f8fb; color:#5c6478; font-weight:600; text-align:right; }
  td:first-child, th:first-child { text-align:left; }
  .src { font-size:12px; color:#9aa3b8; margin-top:10px; line-height:1.7; }
  .note-box { background:#fffbea; border:1px solid #f5e6b8; border-radius:10px; padding:10px 14px; font-size:12.5px; color:#7a6a2f; margin-bottom:14px; }
  .scroll { max-height:460px; overflow:auto; }
"""


def _esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def default_source_note():
    from client import USE_WESTOCK
    from datasource import SOURCE_NOTE
    return SOURCE_NOTE if USE_WESTOCK else '申万指数资料'


def build_page(title: str, subtitle: str, parts: list, source_note: str = "") -> str:
    """组装完整 HTML 文档。

    Args:
        title: 页面标题（h1）
        subtitle: 副标题（header sub）
        parts: list，每项为 {"div": ..., "script": ...}（图表块）或
               {"html": ...}（纯 HTML 块，如表格）
        source_note: 数据来源说明（页脚）
    """
    divs = []
    scripts = []
    for p in parts:
        if "div" in p:
            divs.append(p["div"])
        if "script" in p:
            scripts.append(p["script"])
        if "html" in p:
            divs.append(p["html"])
    script_block = "\n".join(scripts)
    body = "\n".join(divs)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(title)}</title>
{ECHARTS_CDN}
<style>{_PAGE_CSS}</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <h1>{_esc(title)}</h1>
    <div class="sub">{_esc(subtitle)}</div>
  </div>
  <div class="note-box">
    <b>免责声明：</b>以上内容基于公开数据和技术分析，仅供参考，不构成投资建议。市场有风险，投资需谨慎。任何投资决策应结合个人风险承受能力、资金状况和投资目标独立判断，必要时咨询持牌专业机构。过往表现不预示未来收益。
  </div>
  {body}
  <div class="src">
    {_esc(source_note) if source_note else "数据来源：腾讯自选股（申万行业板块口径），行情可能有延迟，以交易所披露为准"}
  </div>
</div>
<script>
{script_block}
</script>
</body>
</html>
"""
    return html


def _chart(title: str, option_obj: dict, height_cls: str = "chart",
           height_px: int | None = None, subtitle: str = "",
           formatters: dict | None = None) -> dict:
    """把一个 ECharts option 对象渲染为 (div, script)。option 数据用 json 注入。

    Args:
        height_px: 若指定，用内联 style 覆盖容器高度（用于按行数动态撑高，
                   解决热力图/横向条形图行距过窄问题）。
        formatters: {占位符名: JS 函数源码字符串}。option 中用 `"__FMT_<名>__"`
                    占位的值会在最终 script 中替换为**真正的 JS 函数字面量**
                    （不带引号），使 ECharts 收到函数对象而非字符串——这是
                    tooltip/label 自定义 formatter 的唯一正确方式。
    """
    import uuid
    cid = "c" + uuid.uuid4().hex[:8]
    style = f' style="height:{int(height_px)}px"' if height_px else ""
    div = (f'<div class="card"><h2>{_esc(title)}</h2>'
           f'<div id="{cid}" class="{height_cls}"{style}></div></div>')
    opt_json = json.dumps(option_obj, ensure_ascii=False)
    # 把占位符替换为真正的 JS 函数（去掉引号，使其成为函数字面量）
    for key, fn_src in (formatters or {}).items():
        opt_json = opt_json.replace(f'"__FMT_{key}__"', fn_src)
    script = (
        f"var chart_{cid} = echarts.init(document.getElementById('{cid}'));\n"
        f"chart_{cid}.setOption({opt_json});\n"
        f"window.addEventListener('resize', function(){{ chart_{cid}.resize(); }});\n"
    )
    return {"div": div, "script": script}


def _color_for(v, up_color=UP, down_color=DOWN):
    try:
        return up_color if float(v) >= 0 else down_color
    except (TypeError, ValueError):
        return GRID


def _axis_base_style():
    return {
        "axisLine": {"lineStyle": {"color": "#c6ccd9"}},
        "axisLabel": {"color": "#5c6478"},
        "splitLine": {"lineStyle": {"color": "#eef0f5"}},
    }


# ── 折线图（多系列）───────────────────────────────────────────────────


def line_chart_html(title, labels, series, *, y_label="", height_cls="chart",
                    unit="", colors=None):
    """series: [{name, values, color}] → (div, script)"""
    data = []
    for s in series:
        vals = s.get("values") or []
        data.append({
            "name": s.get("name", ""),
            "type": "line",
            "smooth": True,
            "showSymbol": False,
            "data": [None if v is None else round(float(v), 4) for v in vals],
            "lineStyle": {"width": 2, "color": s.get("color") or (colors or POOL)[0]},
            "itemStyle": {"color": s.get("color") or (colors or POOL)[0]},
        })
    option = {
        "animation": False,
        "tooltip": {"trigger": "axis", "backgroundColor": "rgba(255,255,255,.96)",
                    "borderColor": "#d5dae5", "textStyle": {"color": "#1f2430"}},
        "legend": {"data": [s["name"] for s in series], "top": 0, "textStyle": {"color": "#5c6478"}},
        "grid": {"left": 60, "right": 24, "top": 34, "bottom": 60},
        "xAxis": {"type": "category", "data": labels, **_axis_base_style()},
        "yAxis": {"type": "value", "name": y_label, "nameTextStyle": {"color": "#5c6478"},
                  "scale": True,
                  "axisLabel": {"color": "#5c6478"}, "splitLine": {"lineStyle": {"color": "#eef0f5"}}},
        "dataZoom": [
            {"type": "inside", "start": 0, "end": 100},
            {"type": "slider", "start": 0, "end": 100, "bottom": 8, "height": 16},
        ],
        "series": data,
    }
    return _chart(title, option, height_cls=height_cls)


# ── 蜡烛图（K线 + MA + 成交量）────────────────────────────────────────


def kline_chart_html(title, labels, opens, highs, lows, closes, *,
                     ma5=None, ma10=None, ma20=None, volumes=None,
                     height_cls="chart"):
    ohlc = []
    for i in range(len(labels)):
        ohlc.append([round(float(opens[i]), 2), round(float(closes[i]), 2),
                     round(float(lows[i]), 2), round(float(highs[i]), 2)])
    series = [{
        "name": "K线", "type": "candlestick",
        "data": ohlc,
        "itemStyle": {"color": UP, "color0": DOWN, "borderColor": UP, "borderColor0": DOWN},
    }]
    legend = ["K线"]
    ma_defs = [("MA5", ma5, "#f59f00"), ("MA10", ma10, "#1971c2"), ("MA20", ma20, "#862e9c")]
    for name, vals, color in ma_defs:
        if vals:
            legend.append(name)
            series.append({
                "name": name, "type": "line", "smooth": True, "showSymbol": False,
                "data": [None if v is None else round(float(v), 2) for v in vals],
                "lineStyle": {"width": 1.2, "color": color},
            })
    has_vol = bool(volumes)
    if has_vol:
        legend.append("成交量")
    option = {
        "animation": False,
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "cross"},
                    "backgroundColor": "rgba(255,255,255,.96)", "borderColor": "#d5dae5",
                    "textStyle": {"color": "#1f2430"}},
        "legend": {"data": legend, "top": 0, "textStyle": {"color": "#5c6478"}},
        "grid": [
            {"left": 60, "right": 24, "top": 34, "height": "58%" if has_vol else "78%"},
            {"left": 60, "right": 24, "top": "76%" if has_vol else None, "height": "16%"},
        ] if has_vol else [{"left": 60, "right": 24, "top": 34, "height": "78%"}],
        "xAxis": [
            {"type": "category", "data": labels, "boundaryGap": True, **_axis_base_style()},
            {"type": "category", "gridIndex": 1, "data": labels, "boundaryGap": True,
             "axisLabel": {"show": False}, "axisLine": {"show": False}},
        ] if has_vol else [{"type": "category", "data": labels, "boundaryGap": True, **_axis_base_style()}],
        "yAxis": [
            {"scale": True, **_axis_base_style()},
            {"scale": True, "gridIndex": 1, "splitLine": {"show": False},
             "axisLabel": {"show": False}},
        ] if has_vol else [{"scale": True, **_axis_base_style()}],
        "dataZoom": [
            {"type": "inside", "xAxisIndex": [0, 1] if has_vol else [0], "start": 0, "end": 100},
            {"type": "slider", "xAxisIndex": [0, 1] if has_vol else [0],
             "start": 0, "end": 100, "bottom": 8, "height": 16},
        ],
        "series": series + ([{
            "name": "成交量", "type": "bar", "xAxisIndex": 1, "yAxisIndex": 1,
            "data": [round(float(v), 2) for v in volumes],
            "itemStyle": {"color": "#adb5bd"},
        }] if has_vol else []),
    }
    return _chart(title, option, height_cls=height_cls)


# ── 指标图（主图 K线+MA+BOLL，下方多指标子图）─────────────────────────


def indicator_chart_html(title, labels, opens, highs, lows, closes, *,
                         ma5=None, ma10=None, ma20=None, volumes=None,
                         indicators=None, height_cls="chart"):
    """技术指标综合图：主图 K线+MA+布林带，下方按指标类型分多个子图。

    indicators: 由 indicators.compute 返回的 dict（含 dif/dea/macd、k/d/j、
                 rsi、cci、atr、obv、adx、di_plus/di_minus、boll_mid/up/low 等）。
    自动按可用数据分组建子图：
      - MACD 子图: DIF/DEA 折线 + MACD 柱
      - KDJ 子图: K/D/J 三线
      - RSI / CCI / ATR 子图: 单线
      - ADX 子图: ADX/+DI/-DI 三线
      - OBV 子图: 量能折线
    """
    ind = indicators or {}
    ohlc = []
    for i in range(len(labels)):
        ohlc.append([round(float(opens[i]), 2), round(float(closes[i]), 2),
                     round(float(lows[i]), 2), round(float(highs[i]), 2)])

    # ── 主图 series：K线 + MA + BOLL ──
    main_series = [{
        "name": "K线", "type": "candlestick",
        "data": ohlc,
        "itemStyle": {"color": UP, "color0": DOWN, "borderColor": UP, "borderColor0": DOWN},
    }]
    legend = ["K线"]
    for name, vals, color in [("MA5", ma5, "#f59f00"), ("MA10", ma10, "#1971c2"),
                              ("MA20", ma20, "#862e9c")]:
        if vals:
            legend.append(name)
            main_series.append({
                "name": name, "type": "line", "smooth": True, "showSymbol": False,
                "data": [None if v is None else round(float(v), 2) for v in vals],
                "lineStyle": {"width": 1.2, "color": color},
            })
    # BOLL 上/中/下轨（若有）
    for name, key, color in [("BOLL上轨", "boll_up", "#e8590c"),
                             ("BOLL中轨", "boll_mid", "#12b886"),
                             ("BOLL下轨", "boll_low", "#1971c2")]:
        if key in ind and ind[key]:
            legend.append(name)
            main_series.append({
                "name": name, "type": "line", "smooth": True, "showSymbol": False,
                "data": [None if v is None else round(float(v), 2) for v in ind[key]],
                "lineStyle": {"width": 1, "color": color, "type": "dashed"},
            })

    # ── 子图规划：每个 (标题, 高度占比, 构建series函数) ──
    subplots = []

    if ind.get("macd"):
        subplots.append(("MACD", 0.18, lambda ind=ind: [
            {"name": "DIF", "type": "line", "data": [round(float(v), 3) if v is not None else None for v in ind.get("dif", [])],
             "lineStyle": {"width": 1.2, "color": "#f59f00"}, "showSymbol": False},
            {"name": "DEA", "type": "line", "data": [round(float(v), 3) if v is not None else None for v in ind.get("dea", [])],
             "lineStyle": {"width": 1.2, "color": "#1971c2"}, "showSymbol": False},
            {"name": "MACD", "type": "bar",
             "data": [round(float(v), 3) if v is not None else None for v in ind.get("macd", [])],
             "itemStyle": {"color": None}},
        ]))
    if ind.get("k") and ind.get("d"):
        subplots.append(("KDJ", 0.18, lambda ind=ind: [
            {"name": "K", "type": "line", "data": [round(float(v), 2) if v is not None else None for v in ind["k"]],
             "lineStyle": {"width": 1, "color": "#f59f00"}, "showSymbol": False},
            {"name": "D", "type": "line", "data": [round(float(v), 2) if v is not None else None for v in ind["d"]],
             "lineStyle": {"width": 1, "color": "#1971c2"}, "showSymbol": False},
            {"name": "J", "type": "line", "data": [round(float(v), 2) if v is not None else None for v in ind["j"]],
             "lineStyle": {"width": 1, "color": "#862e9c"}, "showSymbol": False},
        ]))
    if ind.get("rsi"):
        subplots.append(("RSI", 0.16, lambda ind=ind: [
            {"name": "RSI", "type": "line",
             "data": [round(float(v), 2) if v is not None else None for v in ind["rsi"]],
             "lineStyle": {"width": 1.2, "color": "#e8590c"}, "showSymbol": False},
        ]))
    if ind.get("cci"):
        subplots.append(("CCI", 0.16, lambda ind=ind: [
            {"name": "CCI", "type": "line",
             "data": [round(float(v), 2) if v is not None else None for v in ind["cci"]],
             "lineStyle": {"width": 1.2, "color": "#12b886"}, "showSymbol": False},
        ]))
    if ind.get("adx"):
        subplots.append(("ADX", 0.16, lambda ind=ind: [
            {"name": "ADX", "type": "line", "data": [round(float(v), 2) if v is not None else None for v in ind["adx"]],
             "lineStyle": {"width": 1.2, "color": "#862e9c"}, "showSymbol": False},
            {"name": "+DI", "type": "line", "data": [round(float(v), 2) if v is not None else None for v in ind.get("di_plus", [])],
             "lineStyle": {"width": 1, "color": "#e03131"}, "showSymbol": False},
            {"name": "-DI", "type": "line", "data": [round(float(v), 2) if v is not None else None for v in ind.get("di_minus", [])],
             "lineStyle": {"width": 1, "color": "#0ca678"}, "showSymbol": False},
        ]))
    if ind.get("atr"):
        subplots.append(("ATR", 0.14, lambda ind=ind: [
            {"name": "ATR", "type": "line",
             "data": [round(float(v), 2) if v is not None else None for v in ind["atr"]],
             "lineStyle": {"width": 1.2, "color": "#f59f00"}, "showSymbol": False},
        ]))
    if ind.get("obv"):
        subplots.append(("OBV", 0.16, lambda ind=ind: [
            {"name": "OBV", "type": "line",
             "data": [round(float(v), 2) if v is not None else None for v in ind["obv"]],
             "lineStyle": {"width": 1.2, "color": "#1971c2"}, "showSymbol": False},
        ]))

    # Each pane has its own grid. One shared date axis sits below the final pane.
    n_plots = 1 + len(subplots)
    grids, x_axes, y_axes, all_series = [], [], [], []
    MAIN_H, SUB_H, GAP, TOP0 = 300, 130, 28, 48
    grids.append({"left": 62, "right": 30, "top": TOP0, "height": MAIN_H})
    cursor = TOP0 + MAIN_H
    for _ in subplots:
        cursor += GAP
        grids.append({"left": 62, "right": 30, "top": cursor, "height": SUB_H})
        cursor += SUB_H
    # Reserve independent bands for final date labels and the zoom slider.
    total_h = cursor + 72
    for i in range(n_plots):
        show_dates = i == n_plots - 1
        x_axes.append({
            "type": "category", "gridIndex": i, "data": labels, "boundaryGap": True,
            "axisLine": {"show": show_dates, "lineStyle": {"color": "#c6ccd9"}},
            "axisTick": {"show": show_dates, "alignWithLabel": True},
            "axisLabel": {"show": show_dates, "color": "#5c6478", "fontSize": 10,
                          "margin": 12, "hideOverlap": True, "showMinLabel": False,
                          "showMaxLabel": False},
            "axisPointer": {"label": {"show": show_dates}},
        })

    y_axes.append({"scale": True, "splitLine": {"lineStyle": {"color": "#eef0f5"}},
                   "axisLabel": {"color": "#5c6478"}})
    for i in range(len(subplots)):
        y_axes.append({"scale": True, "gridIndex": i + 1,
                       "splitLine": {"lineStyle": {"color": "#eef0f5"}},
                       "axisLabel": {"color": "#5c6478", "fontSize": 10}})

    all_series.extend(main_series)
    for i, (sname, sheight, builder) in enumerate(subplots):
        gidx = i + 1
        for s in builder():
            s["xAxisIndex"] = gidx
            s["yAxisIndex"] = gidx
            if s["type"] == "bar":
                # MACD 柱按正负着色
                s["itemStyle"] = {"color": None}
                s["data"] = [{"value": v, "itemStyle": {"color": UP if (v or 0) >= 0 else DOWN}}
                             if v is not None else None for v in s["data"]]
            all_series.append(s)

    datazoom_xidx = list(range(n_plots))
    option = {
        "animation": False,
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "cross"},
                    "backgroundColor": "rgba(255,255,255,.96)", "borderColor": "#d5dae5",
                    "textStyle": {"color": "#1f2430"}},
        "legend": {"type": "scroll", "data": legend + [s[0] for s in subplots], "top": 0, "left": 0, "right": 0,
                   "textStyle": {"color": "#5c6478"}},
        "grid": grids,
        "xAxis": x_axes,
        "yAxis": y_axes,
        "dataZoom": [
            {"type": "inside", "xAxisIndex": datazoom_xidx, "start": 0, "end": 100},
            {"type": "slider", "xAxisIndex": datazoom_xidx, "start": 0, "end": 100,
             "bottom": 6, "height": 14},
        ],
        "axisPointer": {"link": [{"xAxisIndex": "all"}]},
        "series": all_series,
    }
    return _chart(title, option, height_cls="chart", height_px=total_h)


# ── 热力图（行业多周期）───────────────────────────────────────────────


def heatmap_chart_html(title, industries, fields, field_labels=None, height_cls="chart"):
    flabels = field_labels or {f: f for f in fields}
    names = [x.get("name", "") for x in industries]
    data = []
    for i, x in enumerate(industries):
        for j, f in enumerate(fields):
            v = x.get(f, 0)
            try:
                v = float(v)
            except (TypeError, ValueError):
                v = 0
            data.append([j, i, round(v, 2)])
    # 行距问题：按行业数量动态撑高容器（每行至少 26px），保证标签可读
    n_rows = len(names)
    height_px = max(320, n_rows * 28 + 110)
    flabel_arr = json.dumps(list(flabels.values()), ensure_ascii=False)
    tooltip_fn = (
        "function(p){return " + json.dumps(names, ensure_ascii=False) + "[p.value[1]]+' · '+"
        + flabel_arr + "[p.value[0]]+' : <b>'+p.value[2]+'%</b>';}"
    )
    option = {
        "animation": False,
        "tooltip": {"position": "top", "formatter": "__FMT_HEAT_TOOLTIP__"},
        "grid": {"left": 86, "right": 30, "top": 30, "bottom": 70},
        "xAxis": {"type": "category", "data": [flabels.get(f, f) for f in fields],
                  "splitArea": {"show": True}, **_axis_base_style()},
        "yAxis": {"type": "category", "data": names, "splitArea": {"show": True},
                  "axisLabel": {"color": "#5c6478", "fontSize": 11}},
        "visualMap": {
            "min": -6, "max": 6, "calculable": True, "orient": "horizontal",
            "left": "center", "bottom": 8, "textStyle": {"color": "#5c6478"},
            "inRange": {"color": ["#0ca678", "#f5f6fa", "#e03131"]},
        },
        "series": [{
            "type": "heatmap", "data": data, "label": {"show": True, "fontSize": 10,
            "color": "#1f2430"},
            "emphasis": {"itemStyle": {"shadowBlur": 10, "shadowColor": "rgba(0,0,0,.3)"}},
        }],
    }
    return _chart(title, option, height_cls=height_cls, height_px=height_px,
                  formatters={"HEAT_TOOLTIP": tooltip_fn})


# ── 横向条形图 ────────────────────────────────────────────────────────


def bar_chart_h_html(title, items, *, value_label="pct", color_by_sign=True,
                     height_cls="chart", max_items=None):
    items = items if max_items is None else items[:max_items]
    names = [x.get("name", "") for x in items]
    vals = []
    for x in items:
        try:
            vals.append(round(float(x.get("value", 0)), 2))
        except (TypeError, ValueError):
            vals.append(0)
    colors = [_color_for(v) if color_by_sign else ACCENT for v in vals]
    formatter = "{c}%" if value_label == "pct" else "{c}"
    # 行距问题：按条目数量动态撑高容器（每行至少 26px），避免行距过窄
    n_rows = len(names)
    height_px = max(320, n_rows * 26 + 90)
    option = {
        "animation": False,
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"},
                    "backgroundColor": "rgba(255,255,255,.96)", "borderColor": "#d5dae5",
                    "textStyle": {"color": "#1f2430"}},
        "grid": {"left": 86, "right": 48, "top": 10, "bottom": 30},
        "xAxis": {"type": "value",
                  "axisLabel": {"color": "#5c6478", "formatter": formatter},
                  "splitLine": {"lineStyle": {"color": "#eef0f5"}}},
        "yAxis": {"type": "category", "data": names, "axisLabel": {"color": "#5c6478", "fontSize": 11}},
        "series": [{
            "type": "bar", "data": [{"value": v, "itemStyle": {"color": c}}
                                    for v, c in zip(vals, colors)],
            "label": {"show": True, "position": "right", "fontSize": 10,
                      "formatter": formatter, "color": "#1f2430"},
            "barMaxWidth": 22,
        }],
    }
    return _chart(title, option, height_cls=height_cls, height_px=height_px)


# ── 饼图 ──────────────────────────────────────────────────────────────


def pie_chart_html(title, pie_data, height_cls="chart-sm", donut=True):
    data = []
    for i, x in enumerate(pie_data):
        name = x.get("name", "") if isinstance(x, dict) else str(x)
        value = x.get("value", 0) if isinstance(x, dict) else 0
        data.append({"name": name, "value": value,
                     "itemStyle": {"color": POOL[i % len(POOL)]}})
    option = {
        "animation": False,
        "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)",
                    "backgroundColor": "rgba(255,255,255,.96)", "borderColor": "#d5dae5",
                    "textStyle": {"color": "#1f2430"}},
        "legend": {"orient": "vertical", "right": 8, "top": "middle",
                   "textStyle": {"color": "#5c6478", "fontSize": 11}},
        "series": [{
            "type": "pie", "radius": ["42%", "72%"] if donut else "72%",
            "center": ["38%", "50%"],
            "data": data,
            "label": {"show": True, "formatter": "{b} {d}%", "fontSize": 10},
        }],
    }
    return _chart(title, option, height_cls=height_cls)


# ── 散点图（收益风险矩阵）─────────────────────────────────────────────


def scatter_chart_html(title, points, *, x_key="x", y_key="y", name_key="name",
                       x_label="", y_label="", height_cls="chart",
                       color_key=None, color_label="",
                       mark_lines=None, tooltip_extra=None):
    """散点图（支持按第三维着色 + 均值分割线 + 扩展 tooltip）。

    Args:
        points: [{x_key, y_key, name_key, ...}]
        color_key: 若指定，取每个 point 的该字段值作为第三维（visualMap 连续
                   着色，红=高，绿=低）；例如收益风险比 ratio
        color_label: 色带图例名称（如"收益风险比"）
        mark_lines: 分割线列表，如 [{"x": 20, "label": "均值波动"},
                                   {"y": 15, "label": "均值收益"}]
        tooltip_extra: 每点的额外 tooltip 行，list of {"label", "key"}
    """
    data = []
    cvals = []
    for p in points:
        try:
            x = float(p.get(x_key, 0))
            y = float(p.get(y_key, 0))
        except (TypeError, ValueError):
            continue
        entry = {"name": p.get(name_key, "")}
        if color_key:
            try:
                cv = float(p.get(color_key) or 0)
            except (TypeError, ValueError):
                cv = 0
            cvals.append(round(cv, 3))
            entry["value"] = [round(x, 2), round(y, 2), round(cv, 3)]
        else:
            entry["value"] = [round(x, 2), round(y, 2)]
        if tooltip_extra:
            entry["extra"] = {t["key"]: p.get(t["key"]) for t in tooltip_extra}
        data.append(entry)

    # tooltip formatter：ECharts 用 new Function() 解析字符串；用反引号+三元表达式
    extra_parts = []
    if tooltip_extra:
        for t in tooltip_extra:
            label = _esc(t["label"])
            key = t["key"]
            extra_parts.append(
                "((p.data.extra && p.data.extra['" + key + "']!=null) ? "
                "'" + label + "：'+p.data.extra['" + key + "']+'<br/>' : '')"
            )
    extra_js = " + ".join(extra_parts) if extra_parts else "''"
    x_part = _esc(x_label)
    y_part = _esc(y_label)
    tip_fmt = (
        "function(p){return "
        "`<b>${p.data.name}</b><br/>"
        + x_part + ": ${p.value[0]}%<br/>"
        + y_part + ": ${p.value[1]}%<br/>` + ("
        + extra_js + ");}"
    )

    mark_line_data = []
    for ml in mark_lines or []:
        if "x" in ml:
            mark_line_data.append({
                "xAxis": float(ml["x"]),
                "label": {"formatter": ml.get("label", ""), "position": "insideEndTop",
                          "color": "#868e96", "fontSize": 10},
                "lineStyle": {"type": "dashed", "color": "#868e96", "width": 1},
            })
        if "y" in ml:
            mark_line_data.append({
                "yAxis": float(ml["y"]),
                "label": {"formatter": ml.get("label", ""), "position": "insideEndTop",
                          "color": "#868e96", "fontSize": 10},
                "lineStyle": {"type": "dashed", "color": "#868e96", "width": 1},
            })

    series = {
        "type": "scatter", "data": data, "symbolSize": 14,
        "itemStyle": {"opacity": 0.8},
        "label": {"show": True, "formatter": "__FMT_SCATTER_LABEL__",
                  "position": "top", "fontSize": 9, "color": "#5c6478"},
        "markLine": {"silent": True, "symbol": "none", "data": mark_line_data},
    }

    option = {
        "animation": False,
        "tooltip": {"formatter": "__FMT_SCATTER_TOOLTIP__",
                    "backgroundColor": "rgba(255,255,255,.96)", "borderColor": "#d5dae5",
                    "textStyle": {"color": "#1f2430"}},
        "grid": {"left": 60, "right": 30, "top": 20, "bottom": 50},
        "xAxis": {"type": "value", "name": x_label, "scale": True,
                  "nameTextStyle": {"color": "#5c6478"}, **_axis_base_style()},
        "yAxis": {"type": "value", "name": y_label, "scale": True,
                  "nameTextStyle": {"color": "#5c6478"}, **_axis_base_style()},
        "dataZoom": [
            {"type": "inside", "start": 0, "end": 100},
            {"type": "slider", "start": 0, "end": 100, "bottom": 8, "height": 16},
        ],
    }

    if color_key and cvals:
        option["visualMap"] = {
            "min": min(cvals), "max": max(cvals),
            "dimension": 2, "seriesIndex": 0, "calculable": True,
            "orient": "horizontal", "left": "center", "bottom": 8,
            "text": [color_label, ""], "textStyle": {"color": "#5c6478", "fontSize": 10},
            "inRange": {"color": ["#0ca678", "#f5f6fa", "#e03131"]},
        }
        series["encode"] = {"x": 0, "y": 1}

    option["series"] = [series]
    return _chart(
        title, option, height_cls=height_cls,
        formatters={
            "SCATTER_TOOLTIP": tip_fmt,
            "SCATTER_LABEL": "function(p){return p.data.name;}",
        },
    )


# ── 相关矩阵热力图 ────────────────────────────────────────────────────


def matrix_chart_html(title, names, matrix, height_cls="chart"):
    data = []
    for i, row in enumerate(matrix):
        for j, v in enumerate(row):
            try:
                v = round(float(v), 2)
            except (TypeError, ValueError):
                v = 0
            data.append([j, i, v])
    names_arr = json.dumps(list(names), ensure_ascii=False)
    tooltip_fn = (
        "function(p){return "
        + names_arr + "[p.value[1]]+' × '"
        + names_arr + "[p.value[0]]+' : <b>'+p.value[2]+'</b>';}"
    )
    option = {
        "animation": False,
        "tooltip": {"position": "top", "formatter": "__FMT_MATRIX_TOOLTIP__"},
        "grid": {"left": 60, "right": 30, "top": 30, "bottom": 60},
        "xAxis": {"type": "category", "data": list(names),
                  "splitArea": {"show": True}, "axisLabel": {"rotate": 45, "fontSize": 10, "color": "#5c6478"}},
        "yAxis": {"type": "category", "data": list(names), "splitArea": {"show": True},
                  "axisLabel": {"fontSize": 10, "color": "#5c6478"}},
        "visualMap": {
            "min": -1, "max": 1, "calculable": True, "orient": "horizontal",
            "left": "center", "bottom": 8, "textStyle": {"color": "#5c6478"},
            "inRange": {"color": ["#0ca678", "#f5f6fa", "#e03131"]},
        },
        "series": [{
            "type": "heatmap", "data": data,
            "label": {"show": True, "fontSize": 9, "color": "#1f2430"},
        }],
    }
    return _chart(title, option, height_cls=height_cls,
                  formatters={"MATRIX_TOOLTIP": tooltip_fn})


# ── 直方图 ────────────────────────────────────────────────────────────


def histogram_chart_html(title, edges, counts, height_cls="chart-sm"):
    labels = []
    for i in range(len(edges) - 1):
        labels.append(f"{edges[i]:.1f}~{edges[i+1]:.1f}")
    option = {
        "animation": False,
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"},
                    "backgroundColor": "rgba(255,255,255,.96)", "borderColor": "#d5dae5",
                    "textStyle": {"color": "#1f2430"}},
        "grid": {"left": 50, "right": 24, "top": 20, "bottom": 50},
        "xAxis": {"type": "category", "data": labels, "axisLabel": {"rotate": 35, "fontSize": 10, "color": "#5c6478"}},
        "yAxis": {"type": "value", "axisLabel": {"color": "#5c6478"}, "splitLine": {"lineStyle": {"color": "#eef0f5"}}},
        "series": [{
            "type": "bar", "data": list(counts), "barMaxWidth": 24,
            "itemStyle": {"color": ACCENT},
        }],
    }
    return _chart(title, option, height_cls=height_cls)


# ── Markdown 表格 → HTML 表格块 ───────────────────────────────────────


def md_table_html(title: str, headers: list, rows: list, *, description: str = "") -> dict:
    """把表格数据渲染为 HTML 表格卡片（可配说明行）。"""
    head = "<tr>" + "".join(f"<th>{_esc(h)}</th>" for h in headers) + "</tr>"
    body_rows = []
    for row in rows:
        cells = []
        for c in row:
            txt = str(c) if c is not None else "—"
            if txt.endswith("%"):
                try:
                    v = float(txt.rstrip("%"))
                    cls = "up" if v > 0 else ("down" if v < 0 else "")
                except ValueError:
                    cls = ""
            else:
                cls = ""
            cells.append(f'<td class="{cls}">{_esc(txt)}</td>')
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    desc = f'<div class="src">{_esc(description)}</div>' if description else ""
    div = (
        f'<div class="card"><h2>{_esc(title)}</h2>{desc}'
        f'<div class="scroll"><table>{head}{"".join(body_rows)}</table></div></div>'
    )
    return {"html": div}
