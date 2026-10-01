#!/usr/bin/env python3
"""HTML 研报渲染器：把分析结果渲染为固定模板的 HTML 研报文件。

纯标准库实现（仅依赖 json / os），无外部依赖。已固化两类固定模板：

  1. kline_report  —— 单指数日K线研报（K线图+MA+成交量、核心指标速览、
                      K线形态信号、关键交易数据表）
  2. style_report  —— 今日市场风格分析（TL;DR 结论卡、宽基指数、风格维度、
                      行业轮动、市场广度与情绪、风格判断与仓位含义）

设计要点：
  - 占位符 + replace 注入数据（不用 f-string 内嵌 JS，规避花括号转义问题）
  - A 股配色：红涨绿跌（#e03131 / #0ca678），浅底深字研报风
  - ECharts 5 CDN 渲染图表；关键数据区块做"图 / 表可切换"
  - 所有行情数据以注入参数为准，渲染器不做任何数据编造

对外接口：
    render_kline_report(out_dir, meta, bars, stats, candle_signals, source_note)
    render_style_report(out_dir, indices, styles, industries, breadth, verdict, source_note)
    二者均返回输出文件绝对路径。
"""

from __future__ import annotations

import json
import os

UP = "#e03131"      # 涨/红
DOWN = "#0ca678"    # 跌/绿
ACCENT = "#2d3e63"

ECHARTS_CDN = '<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>'


def _esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _pct(v, digits=2, sign=True):
    try:
        fv = float(v)
        return f"{fv:+.{digits}f}" if sign else f"{fv:.{digits}f}"
    except (TypeError, ValueError):
        return str(v)


def _cls(v):
    try:
        return "up" if float(v) >= 0 else "down"
    except (TypeError, ValueError):
        return ""


def _write(out_dir: str, filename: str, html: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


# ═══════════════════════════════════════════════════════════════════════
# 模板 1：单指数日K线研报
# ═══════════════════════════════════════════════════════════════════════

_TEMPLATE_KLINE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__TITLE__</title>
__ECHARTS__
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:"PingFang SC","Microsoft YaHei",sans-serif; background:#f5f6fa; color:#1f2430; padding:24px; }
  .wrap { max-width:1080px; margin:0 auto; }
  .header { background:linear-gradient(135deg,#1f2a44,#2d3e63); color:#fff; border-radius:12px; padding:22px 26px; margin-bottom:18px; }
  .header h1 { font-size:22px; margin-bottom:6px; }
  .header .sub { color:#b9c4dd; font-size:13px; }
  .header .price { font-size:34px; font-weight:700; margin-top:10px; }
  .header .delta { font-size:15px; margin-left:10px; }
  .up { color:#e03131 !important; }
  .down { color:#0ca678 !important; }
  .card { background:#fff; border-radius:12px; padding:18px 22px; margin-bottom:16px; box-shadow:0 1px 4px rgba(20,30,60,.06); }
  .card h2 { font-size:16px; margin-bottom:12px; color:#1f2430; border-left:4px solid #2d3e63; padding-left:10px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; }
  .kpi { background:#fafbfd; border:1px solid #e8ebf2; border-radius:10px; padding:12px 14px; }
  .kpi .label { font-size:12px; color:#7b8498; }
  .kpi .value { font-size:19px; font-weight:700; margin-top:4px; }
  .kpi .note { font-size:11px; color:#9aa3b8; margin-top:2px; }
  .chips { display:flex; flex-wrap:wrap; gap:8px; }
  .chip { padding:4px 10px; border-radius:14px; font-size:12px; font-weight:600; }
  .chip.up { background:#fde8e8; color:#c92a2a; }
  .chip.down { background:#e6faf3; color:#087f5b; }
  .muted { color:#9aa3b8; font-size:13px; }
  .chart { width:100%; height:520px; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th,td { padding:8px 10px; text-align:right; border-bottom:1px solid #eef0f5; }
  th { background:#f7f8fb; color:#5c6478; font-weight:600; text-align:right; }
  td:first-child, th:first-child { text-align:left; }
  .tabs { display:flex; gap:8px; margin-bottom:10px; }
  .tab { padding:6px 16px; border-radius:16px; background:#f0f2f7; color:#5c6478; font-size:13px; cursor:pointer; border:none; }
  .tab.active { background:#2d3e63; color:#fff; }
  .view { display:none; }
  .view.active { display:block; }
  .src { font-size:12px; color:#9aa3b8; margin-top:12px; line-height:1.7; }
  .note-box { background:#fffbea; border:1px solid #f5e6b8; border-radius:10px; padding:12px 16px; font-size:13px; color:#7a6a2f; margin-bottom:16px; }
</style>
</head>
<body>
<div class="wrap">

  <div class="header">
    <h1>__NAME__ · __PERIOD_CN__K线技术面研报</h1>
    <div class="sub">指数代码 __CODE__ · 数据区间 __START__ ~ __END__ · 共 __BARS__ 根__PERIOD_CN__K</div>
    <div class="price">__LAST_PRICE__ <span class="delta __PERIOD_CLS__">区间 __PERIOD_CHG__</span></div>
    <div class="sub" style="margin-top:6px;">区间最高 __HIGH__（__HIGH_DATE__） · 区间最低 __LOW__（__LOW_DATE__）</div>
  </div>

  <div class="note-box">
    <b>免责声明：</b>以上内容基于公开数据和技术分析，仅供参考，不构成投资建议。市场有风险，投资需谨慎。任何投资决策应结合个人风险承受能力、资金状况和投资目标独立判断，必要时咨询持牌专业机构。过往表现不预示未来收益。
  </div>

  <div class="card">
    <h2>核心指标速览</h2>
    <div class="grid">
      <div class="kpi"><div class="label">近5日涨跌</div><div class="value __C5C__">__CHG5__</div></div>
      <div class="kpi"><div class="label">近10日涨跌</div><div class="value __C10C__">__CHG10__</div></div>
      <div class="kpi"><div class="label">近20日涨跌</div><div class="value __C20C__">__CHG20__</div></div>
      <div class="kpi"><div class="label">近60日涨跌</div><div class="value __C60C__">__CHG60__</div></div>
      <div class="kpi"><div class="label">距区间高点回撤</div><div class="value __CDDC__">__DD__</div></div>
      <div class="kpi"><div class="label">MA5 / MA10 / MA20</div><div class="value" style="font-size:15px;">__MA5__ / __MA10__ / __MA20__</div><div class="note">收盘__MA_NOTE__MA20</div></div>
      <div class="kpi"><div class="label">近20日年化波动</div><div class="value">__VOL20__</div></div>
      <div class="kpi"><div class="label">区间涨跌天数</div><div class="value">__UPDAYS__涨 / __DOWNDAYS__跌</div></div>
    </div>
  </div>

  <div class="card">
    <h2>__PERIOD_CN__K线走势（含 MA5 / MA10 / MA20 与成交量）</h2>
    <div class="tabs">
      <button class="tab active" onclick="switchView('chartView')">图</button>
      <button class="tab" onclick="switchView('tableView')">表</button>
    </div>
    <div id="chartView" class="view active"><div id="klineChart" class="chart"></div></div>
    <div id="tableView" class="view"><div style="max-height:440px;overflow:auto;"><table id="dataTable"></table></div></div>
  </div>

  <div class="card">
    <h2>近期K线形态信号</h2>
    <div class="chips">__CANDLE_CHIPS__</div>
    <div class="src">信号由 K 线形态识别引擎（锤子/吞噬/晨星/三白兵等经典形态）基于日K数据自动判定，仅反映历史价格形态，不构成预测。</div>
  </div>

  <div class="card">
    <h2>关键交易数据（最近 __RECENT_N__ 个交易日）</h2>
    <table>
      <tr><th>日期</th><th>开</th><th>高</th><th>低</th><th>收</th><th>涨跌%</th><th>成交额(亿)</th></tr>
      <tbody id="recentRows"></tbody>
    </table>
  </div>

  <div class="src">
    数据来源：__SOURCE_NOTE__ · 数据截至 __END__ 收盘 · 指数点位为收盘点位<br>
    技术分析信号基于历史价格形态，仅供参考，不构成投资建议。
  </div>
</div>

<script>
var dates = __DATES__;
var ohlc = __OHLC__;
var vols = __VOLS__;
var amounts = __AMOUNTS__;
var ma5 = __MA5_ARR__;
var ma10 = __MA10_ARR__;
var ma20 = __MA20_ARR__;

var kc = echarts.init(document.getElementById('klineChart'));
kc.setOption({
  animation:false,
  tooltip: { trigger:'axis', axisPointer:{ type:'cross' }, backgroundColor:'rgba(255,255,255,.96)', borderColor:'#d5dae5', textStyle:{ color:'#1f2430' } },
  legend: { data:['日K','MA5','MA10','MA20','成交量'], top:0 },
  grid: [
    { left:60, right:20, top:34, height:'58%' },
    { left:60, right:20, top:'76%', height:'16%' }
  ],
  xAxis: [
    { type:'category', data:dates, boundaryGap:true, axisLine:{ lineStyle:{ color:'#c6ccd9' } }, axisLabel:{ color:'#5c6478' } },
    { type:'category', gridIndex:1, data:dates, boundaryGap:true, axisLabel:{ show:false }, axisLine:{ show:false } }
  ],
  yAxis: [
    { scale:true, splitLine:{ lineStyle:{ color:'#eef0f5' } }, axisLabel:{ color:'#5c6478' } },
    { scale:true, gridIndex:1, splitLine:{ show:false }, axisLabel:{ show:false } }
  ],
  dataZoom: [
    { type:'inside', xAxisIndex:[0,1], start:0, end:100 },
    { type:'slider', xAxisIndex:[0,1], start:0, end:100, bottom:2, height:16 }
  ],
  series: [
    { name:'日K', type:'candlestick', data:ohlc, itemStyle:{ color:'#e03131', color0:'#0ca678', borderColor:'#e03131', borderColor0:'#0ca678' } },
    { name:'MA5', type:'line', data:ma5, smooth:true, showSymbol:false, lineStyle:{ width:1, color:'#f59f00' } },
    { name:'MA10', type:'line', data:ma10, smooth:true, showSymbol:false, lineStyle:{ width:1, color:'#1971c2' } },
    { name:'MA20', type:'line', data:ma20, smooth:true, showSymbol:false, lineStyle:{ width:1, color:'#862e9c' } },
    { name:'成交量', type:'bar', xAxisIndex:1, yAxisIndex:1, data:vols, itemStyle:{ color:'#adb5bd' } }
  ]
});

function renderTable() {
  var tb = document.getElementById('dataTable');
  var head = '<tr><th>日期</th><th>开</th><th>高</th><th>低</th><th>收</th><th>涨跌%</th><th>成交额(亿)</th></tr>';
  var rows = '';
  var prev = null;
  for (var i = dates.length - 1; i >= 0; i--) {
    var o = ohlc[i][0], c = ohlc[i][1], l = ohlc[i][2], h = ohlc[i][3];
    var chg = prev === null ? '' : ((c / prev - 1) * 100).toFixed(2) + '%';
    var cls = (c >= o) ? 'up' : 'down';
    rows += '<tr><td>' + dates[i] + '</td><td>' + o.toFixed(2) + '</td><td>' + h.toFixed(2) + '</td><td>' + l.toFixed(2) + '</td><td class="' + cls + '">' + c.toFixed(2) + '</td><td class="' + (chg.indexOf('-') === 0 ? 'down' : 'up') + '">' + chg + '</td><td>' + vols[i].toFixed(2) + '</td></tr>';
    prev = c;
  }
  tb.innerHTML = head + rows;
}
renderTable();

var recentRows = '';
var rprev = null;
for (var j = dates.length - __RECENT_N__; j < dates.length; j++) {
  var o2 = ohlc[j][0], c2 = ohlc[j][1], l2 = ohlc[j][2], h2 = ohlc[j][3];
  var rc = (rprev === null) ? '' : ((c2 / rprev - 1) * 100).toFixed(2) + '%';
  var cls2 = (c2 >= o2) ? 'up' : 'down';
  recentRows += '<tr><td>' + dates[j] + '</td><td>' + o2.toFixed(2) + '</td><td>' + h2.toFixed(2) + '</td><td>' + l2.toFixed(2) + '</td><td class="' + cls2 + '">' + c2.toFixed(2) + '</td><td class="' + (rc.indexOf('-') === 0 ? 'down' : 'up') + '">' + rc + '</td><td>' + (amounts[j] == null ? '—' : amounts[j].toFixed(2)) + '</td></tr>';
  rprev = c2;
}
document.getElementById('recentRows').innerHTML = recentRows;

function switchView(view) {
  var tabs = document.querySelectorAll('.tab');
  for (var t = 0; t < tabs.length; t++) tabs[t].classList.remove('active');
  event.target.classList.add('active');
  document.getElementById('chartView').classList.toggle('active', view === 'chartView');
  document.getElementById('tableView').classList.toggle('active', view === 'tableView');
  if (view === 'chartView') kc.resize();
}

window.addEventListener('resize', function() { kc.resize(); });
</script>
</body>
</html>
"""


def render_kline_report(out_dir, meta, bars, stats, candle_signals, source_note,
                        filename=None):
    """渲染单指数日K线研报。

    Args:
        out_dir: 输出目录（自动创建）。
        meta: dict{name, code, period}
        bars: dict{labels, open, high, low, close, ma5, ma10, ma20, volumes}
        stats: dict（与 build 阶段一致：period_chg_pct, chg_5d... 等）
        candle_signals: list[{"date","signal"}]（最近若干非零形态信号）
        source_note: 数据来源说明（如"腾讯自选股（申万行业板块口径），行情可能有延迟，以交易所披露为准"）
    """
    name = meta["name"]
    code = meta["code"]
    period_cn = {"DAY": "日", "WEEK": "周", "MONTH": "月"}.get(meta.get("period", "DAY"), "日")
    labels = bars["labels"]
    n = len(labels)
    ohlc = [[bars["open"][i], bars["close"][i], bars["low"][i], bars["high"][i]]
            for i in range(n)]

    # 形态 chips
    if candle_signals:
        chips = []
        for it in candle_signals[-8:]:
            tag = "看涨" if it["signal"] == 1 else "看跌"
            chips.append(f'<span class="chip {"up" if it["signal"]==1 else "down"}">{it["date"]} · {tag}</span>')
        candle_html = '<div class="chips">' + "".join(chips) + "</div>"
    else:
        candle_html = '<p class="muted">近120日未检测到经典K线形态信号</p>'

    # 最近 10 日
    recent_n = min(10, n)

    title = f"{name}（{code}）{period_cn}K线研报"
    html = _TEMPLATE_KLINE
    html = html.replace("__TITLE__", _esc(title))
    html = html.replace("__ECHARTS__", ECHARTS_CDN)
    html = html.replace("__PERIOD_CN__", _esc(period_cn))
    html = html.replace("__NAME__", _esc(name))
    html = html.replace("__CODE__", _esc(code))
    html = html.replace("__START__", _esc(labels[0]))
    html = html.replace("__END__", _esc(labels[-1]))
    html = html.replace("__BARS__", str(n))
    html = html.replace("__LAST_PRICE__", f"{stats['last_close']:,.2f}")
    html = html.replace("__PERIOD_CHG__", _pct(stats["period_chg_pct"]))
    html = html.replace("__PERIOD_CLS__", _cls(stats["period_chg_pct"]))
    html = html.replace("__HIGH__", f"{stats['period_high']:,.2f}")
    html = html.replace("__HIGH_DATE__", _esc(stats["high_date"]))
    html = html.replace("__LOW__", f"{stats['period_low']:,.2f}")
    html = html.replace("__LOW_DATE__", _esc(stats["low_date"]))

    def kpi_pair(key, placeholder_cls, placeholder_val):
        return html  # no-op, replaced below via closures

    html = html.replace("__CHG5__", _pct(stats.get("chg_5d")))
    html = html.replace("__C5C__", _cls(stats.get("chg_5d")))
    html = html.replace("__CHG10__", _pct(stats.get("chg_10d")))
    html = html.replace("__C10C__", _cls(stats.get("chg_10d")))
    html = html.replace("__CHG20__", _pct(stats.get("chg_20d")))
    html = html.replace("__C20C__", _cls(stats.get("chg_20d")))
    html = html.replace("__CHG60__", _pct(stats.get("chg_60d")))
    html = html.replace("__C60C__", _cls(stats.get("chg_60d")))
    html = html.replace("__DD__", _pct(stats.get("drawdown_from_high_pct")))
    html = html.replace("__CDDC__", _cls(stats.get("drawdown_from_high_pct")))
    html = html.replace("__MA5__", f"{stats['ma5']:,.0f}")
    html = html.replace("__MA10__", f"{stats['ma10']:,.0f}")
    html = html.replace("__MA20__", f"{stats['ma20']:,.0f}")
    html = html.replace("__MA_NOTE__", "站上" if stats.get("above_ma20") else "跌破")
    html = html.replace("__VOL20__", f"{stats['vol_20d_annual_pct']:.1f}%")
    html = html.replace("__UPDAYS__", str(stats.get("up_days", 0)))
    html = html.replace("__DOWNDAYS__", str(stats.get("down_days", 0)))

    html = html.replace("__CANDLE_CHIPS__", candle_html)
    html = html.replace("__RECENT_N__", str(recent_n))
    html = html.replace("__SOURCE_NOTE__", _esc(source_note))

    html = html.replace("__DATES__", json.dumps(labels))
    html = html.replace("__OHLC__", json.dumps(ohlc))
    html = html.replace("__VOLS__", json.dumps(bars["volumes"]))
    html = html.replace("__AMOUNTS__", json.dumps(bars.get("amounts", [None]*len(labels))))
    html = html.replace("__MA5_ARR__", json.dumps(bars["ma5"]))
    html = html.replace("__MA10_ARR__", json.dumps(bars["ma10"]))
    html = html.replace("__MA20_ARR__", json.dumps(bars["ma20"]))

    if not filename:
        filename = f"{name}{code}_{period_cn}K线研报.html"
    return _write(out_dir, filename, html)


# ═══════════════════════════════════════════════════════════════════════
# 模板 2：今日市场风格分析
# ═══════════════════════════════════════════════════════════════════════

_TEMPLATE_STYLE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__TITLE__</title>
__ECHARTS__
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:"PingFang SC","Microsoft YaHei",sans-serif; background:#f5f6fa; color:#1f2430; padding:24px; }
  .wrap { max-width:1080px; margin:0 auto; }
  .header { background:linear-gradient(135deg,#1f2a44,#2d3e63); color:#fff; border-radius:12px; padding:22px 26px; margin-bottom:18px; }
  .header h1 { font-size:22px; margin-bottom:6px; }
  .header .sub { color:#b9c4dd; font-size:13px; }
  .tldr { background:#fffbea; border:1px solid #f0e3b8; border-radius:12px; padding:16px 20px; margin-bottom:16px; }
  .tldr h2 { font-size:15px; color:#7a6a2f; margin-bottom:8px; }
  .tldr p { font-size:13.5px; line-height:1.8; color:#5c5326; }
  .card { background:#fff; border-radius:12px; padding:18px 22px; margin-bottom:16px; box-shadow:0 1px 4px rgba(20,30,60,.06); }
  .card h2 { font-size:16px; margin-bottom:12px; border-left:4px solid #2d3e63; padding-left:10px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; }
  .kpi { background:#fafbfd; border:1px solid #e8ebf2; border-radius:10px; padding:12px 14px; }
  .kpi .label { font-size:12px; color:#7b8498; }
  .kpi .value { font-size:18px; font-weight:700; margin-top:4px; }
  .kpi .note { font-size:11px; color:#9aa3b8; margin-top:2px; }
  .up { color:#e03131 !important; }
  .down { color:#0ca678 !important; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th,td { padding:8px 10px; text-align:right; border-bottom:1px solid #eef0f5; }
  th { background:#f7f8fb; color:#5c6478; font-weight:600; text-align:right; }
  td:first-child, th:first-child { text-align:left; }
  .chart { width:100%; height:400px; }
  .chart-sm { width:100%; height:360px; }
  .src { font-size:12px; color:#9aa3b8; margin-top:12px; line-height:1.7; }
  .bq { font-size:13px; color:#5c6478; border-left:3px solid #c6ccd9; padding-left:12px; margin:10px 0; line-height:1.7; }
</style>
</head>
<body>
<div class="wrap">

  <div class="header">
    <h1>__TITLE_H1__</h1>
    <div class="sub">__DATE_LABEL__ · A股 · __DATA_NOTE__</div>
  </div>

  <div class="tldr">
    <h2>TL;DR · 结论先行</h2>
    <p>__TLDR__</p>
  </div>

  <div class="card">
    <h2>一、宽基指数：全面回调，跌幅随市值递减扩大</h2>
    <div id="chartIdx" class="chart"></div>
    <table style="margin-top:10px;">
      <tr><th>指数</th><th>点位</th><th>今日</th><th>近20日</th><th>YTD</th><th>解读</th></tr>
      __IDX_ROWS__
    </table>
    <div class="src">__SRC_IDX__</div>
  </div>

  <div class="card">
    <h2>二、风格维度：__STYLE_HEADLINE__</h2>
    <div class="grid">
      __STYLE_KPIS__
    </div>
    <div id="chartStyle" class="chart-sm" style="margin-top:14px;"></div>
    <div class="src">__SRC_STYLE__</div>
  </div>

  <div class="card">
    <h2>三、行业轮动：__SECTOR_HEADLINE__</h2>
    <div id="chartInd" class="chart"></div>
    <div class="bq">__SECTOR_NOTE__</div>
    <div class="src">__SRC_SECTOR__</div>
  </div>

  <div class="card">
    <h2>四、市场广度与情绪：__BREADTH_HEADLINE__</h2>
    <div class="grid">
      __BREADTH_KPIS__
    </div>
    <div class="bq">__BREADTH_NOTE__</div>
    <div class="src">__SRC_BREADTH__</div>
  </div>

  <div class="card">
    <h2>五、风格判断与仓位含义</h2>
    <table>
      <tr><th>维度</th><th>当前状态</th><th>风格含义</th></tr>
      __VERDICT_ROWS__
    </table>
    <div class="bq">__VERDICT_NOTE__</div>
  </div>

  <div class="src" style="margin-bottom:40px;">
    <b>免责声明：</b>以上内容基于公开数据和技术分析，仅供参考，不构成投资建议。市场有风险，投资需谨慎。任何投资决策应结合个人风险承受能力、资金状况和投资目标独立判断，必要时咨询持牌专业机构。过往表现不预示未来收益。<br><br>
    数据来源：__SOURCE_NOTE__
  </div>
</div>

<script>
var idxNames = __IDX_NAMES__;
var idxChg = __IDX_CHG__;

echarts.init(document.getElementById('chartIdx')).setOption({
  tooltip: { trigger:'axis', axisPointer:{type:'shadow'} },
  grid: { left:50, right:20, top:20, bottom:30 },
  xAxis: { type:'value', axisLabel:{ formatter:'{value}%' }, splitLine:{lineStyle:{color:'#eef0f5'}} },
  yAxis: { type:'category', data: idxNames.slice().reverse() },
  series: [{ type:'bar', data: idxChg.slice().reverse().map(function(v){ return { value:v, itemStyle:{ color: v>=0 ? '#e03131' : '#0ca678' } }; }) }]
});

var styleNames = __STYLE_NAMES__;
var styleVals = __STYLE_VALS__;
echarts.init(document.getElementById('chartStyle')).setOption({
  tooltip: { trigger:'axis', axisPointer:{type:'shadow'} },
  grid: { left:60, right:30, top:20, bottom:30 },
  xAxis: { type:'category', data: styleNames, axisLabel:{rotate:35, fontSize:11} },
  yAxis: { type:'value', axisLabel:{ formatter:'{value}%' } },
  series: [{ type:'bar', barWidth:'55%', data: styleVals.map(function(v){ return { value:v, itemStyle:{ color: v>=0 ? '#e03131' : '#0ca678' } }; }) }]
});

var indNames = __IND_NAMES__;
var indVals = __IND_VALS__;
echarts.init(document.getElementById('chartInd')).setOption({
  tooltip: { trigger:'axis', axisPointer:{type:'shadow'} },
  grid: { left:50, right:30, top:20, bottom:40 },
  xAxis: { type:'category', data: indNames, axisLabel:{rotate:55, fontSize:11} },
  yAxis: { type:'value', axisLabel:{ formatter:'{value}%' } },
  dataZoom: [{ type:'inside', start:0, end:100 }],
  series: [{ type:'bar', barWidth:'60%', data: indVals.map(function(v){ return { value:v, itemStyle:{ color: v>=0 ? '#e03131' : '#0ca678' } }; }) }]
});
</script>
</body>
</html>
"""


def render_style_report(out_dir, indices, styles, industries, breadth, verdict,
                        source_note, filename=None, date_label="2026-08-18",
                        tldr="", sector_note="", breadth_note="",
                        style_headline="价值风格占优", sector_headline="资源防御走强",
                        breadth_headline="广度恶化，情绪偏低"):
    """渲染今日市场风格分析研报。

    Args:
        out_dir: 输出目录。
        indices: list[(name, chg_pct, chg20_str, ytd_str, latest, note)]
        styles:  list[(name, chg_pct, label)]
        industries: list[(name, chg_pct)]（按涨跌排序，或自动排序）
        breadth: dict{up, down, limit_up, limit_down, amount_wan_yi, note_kpis:list[(label,value,note)]}
        verdict: dict{rows:list[(dim,state,meaning)], note}
        source_note: 数据来源说明。
    """
    # 宽基指数表格行
    idx_rows = []
    for name, chg, c20, ytd, px, note in indices:
        idx_rows.append(
            f"<tr><td>{_esc(name)}</td><td>{px:,.2f}</td>"
            f'<td class="{_cls(chg)}">{_pct(chg)}%</td>'
            f'<td class="{_cls(float(str(c20).replace("%","")) if str(c20).replace("%","").replace("+","").replace("-","").isdigit() else 0)}">{_esc(c20)}%</td>'
            f'<td class="{_cls(float(str(ytd).replace("%","")) if str(ytd).replace("%","").replace("+","").replace("-","").isdigit() else 0)}">{_esc(ytd)}%</td>'
            f"<td>{_esc(note)}</td></tr>"
        )

    # 风格 KPI
    style_kpis = []
    style_kpis.append(f'<div class="kpi"><div class="label">市值风格</div><div class="value">{_esc(breadth.get("size_style",""))}</div><div class="note">{_esc(breadth.get("size_note",""))}</div></div>')
    style_kpis.append(f'<div class="kpi"><div class="label">估值风格</div><div class="value">{_esc(breadth.get("val_style",""))}</div><div class="note">{_esc(breadth.get("val_note",""))}</div></div>')
    style_kpis.append(f'<div class="kpi"><div class="label">综合判断</div><div class="value" style="color:#1c7ed6;">{_esc(breadth.get("overall_style","价值风格占优"))}</div><div class="note">{_esc(breadth.get("overall_note",""))}</div></div>')
    # 补充任意自定义 kpi（市场广度卡）
    for item in breadth.get("extra_kpis", []):
        style_kpis.append(
            f'<div class="kpi"><div class="label">{_esc(item[0])}</div><div class="value">{_esc(item[1])}</div><div class="note">{_esc(item[2])}</div></div>'
        )

    # 广度 KPI
    breadth_kpis = []
    b_defs = [
        ("上涨/下跌家数", breadth.get("up_down", "—"), breadth.get("up_down_note", "")),
        ("涨停 / 跌停", breadth.get("limit", "—"), breadth.get("limit_note", "")),
        ("两市成交额", breadth.get("amount", "—"), breadth.get("amount_note", "")),
        ("两融余额", breadth.get("margin", "—"), breadth.get("margin_note", "")),
        ("市场情绪", breadth.get("sentiment", "—"), breadth.get("sentiment_note", "")),
    ]
    for label, value, note in b_defs:
        if value is not None:
            breadth_kpis.append(
                f'<div class="kpi"><div class="label">{_esc(label)}</div><div class="value">{_esc(value)}</div><div class="note">{_esc(note)}</div></div>'
            )
    for item in breadth.get("extra_breadth_kpis", []):
        breadth_kpis.append(
            f'<div class="kpi"><div class="label">{_esc(item[0])}</div><div class="value">{_esc(item[1])}</div><div class="note">{_esc(item[2])}</div></div>'
        )

    # 判定表行
    verdict_rows = []
    for dim, state, meaning in verdict.get("rows", []):
        verdict_rows.append(
            f"<tr><td>{_esc(dim)}</td><td><b>{_esc(state)}</b></td><td>{_esc(meaning)}</td></tr>"
        )

    # 行业排序
    ind_sorted = sorted(industries, key=lambda x: x[1], reverse=True)
    ind_names = [x[0] for x in ind_sorted]
    ind_vals = [x[1] for x in ind_sorted]

    # 风格排序（chart 用，按涨跌排序便于看图）
    style_sorted = sorted(styles, key=lambda x: x[1], reverse=True)
    style_names = [x[0] for x in style_sorted]
    style_vals = [x[1] for x in style_sorted]

    idx_names = [x[0] for x in indices]
    idx_chg = [x[1] for x in indices]

    title = "今日市场风格分析"
    html = _TEMPLATE_STYLE
    html = html.replace("__TITLE__", _esc(title))
    html = html.replace("__ECHARTS__", ECHARTS_CDN)
    html = html.replace("__TITLE_H1__", _esc(title))
    html = html.replace("__DATE_LABEL__", _esc(date_label))
    html = html.replace("__DATA_NOTE__", _esc("数据截至盘中/收盘 · 数据来源见文末"))
    html = html.replace("__TLDR__", tldr or "<b>今日 A 股整体回调</b>，价值/低估值相对占优，行业层面资源防御走强、高位科技兑现，市场广度偏弱。")
    html = html.replace("__IDX_ROWS__", "\n".join(idx_rows))
    html = html.replace("__SRC_IDX__", _esc(source_note.get("idx", "")))
    html = html.replace("__STYLE_HEADLINE__", _esc(style_headline))
    html = html.replace("__STYLE_KPIS__", "\n".join(style_kpis))
    html = html.replace("__SRC_STYLE__", _esc(source_note.get("style", "")))
    html = html.replace("__SECTOR_HEADLINE__", _esc(sector_headline))
    html = html.replace("__SECTOR_NOTE__", sector_note or "")
    html = html.replace("__SRC_SECTOR__", _esc(source_note.get("sector", "")))
    html = html.replace("__BREADTH_HEADLINE__", _esc(breadth_headline))
    html = html.replace("__BREADTH_KPIS__", "\n".join(breadth_kpis))
    html = html.replace("__BREADTH_NOTE__", breadth_note or "")
    html = html.replace("__SRC_BREADTH__", _esc(source_note.get("breadth", "")))
    html = html.replace("__VERDICT_ROWS__", "\n".join(verdict_rows))
    html = html.replace("__VERDICT_NOTE__", _esc(verdict.get("note", "")))
    html = html.replace("__SOURCE_NOTE__", _esc(source_note.get("all", "")))

    html = html.replace("__IDX_NAMES__", json.dumps(idx_names))
    html = html.replace("__IDX_CHG__", json.dumps(idx_chg))
    html = html.replace("__STYLE_NAMES__", json.dumps(style_names))
    html = html.replace("__STYLE_VALS__", json.dumps(style_vals))
    html = html.replace("__IND_NAMES__", json.dumps(ind_names))
    html = html.replace("__IND_VALS__", json.dumps(ind_vals))

    if not filename:
        filename = "今日市场风格分析.html"
    return _write(out_dir, filename, html)


if __name__ == "__main__":
    import sys
    print(json.dumps({"status": "ok", "module": "sw_html_report",
                      "templates": ["kline_report", "style_report"]},
                     ensure_ascii=False))
