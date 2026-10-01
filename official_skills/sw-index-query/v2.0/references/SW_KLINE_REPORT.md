> 行情优先使用 westock；必要时通过网页检索补充并核实来源、日期与口径。执行与交付遵循 [DATA_SOURCE.md](DATA_SOURCE.md)；最终回复只表达结果与分析范围，不转述内部诊断。

# SW_KLINE_REPORT —— 单指数日K线技术面研报（HTML）

> **何时读取**：用户问"XX指数日K线 / XX的K线研报 / 电子指数日K线 / 帮我看看XX的日K走势"等，要求**单指数日K线 + 技术面速览**时读取本文件，按指导执行 `sw_kline_report.py`。区别于 `SW_CHART.md`（图表为主）与 `SW_TECH.md`（全量技术指标诊断）：本场景是**固定版式的 HTML 研报**（K线图+核心指标+形态信号+关键交易数据表），专为快速产出统一格式研报设计。

## 脚本

`scripts/sw_kline_report.py`

```bash
python <skill根目录>/scripts/sw_kline_report.py --code 801080
python <skill根目录>/scripts/sw_kline_report.py --code 801080 --days 250
python <skill根目录>/scripts/sw_kline_report.py --code 000300 --days 120   # 外部常用指数
python <skill根目录>/scripts/sw_kline_report.py --code 801080 --name 电子  # 显式给名
python <skill根目录>/scripts/sw_kline_report.py --code 801080 --output <目录>
```

## 参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `--code` | 是 | 指数代码：申万指数（6位，如 801080 电子 / 801003 申万A指）或外部常用指数（000300 / 000905 / 399006 等，见 `external_indices.py` 支持表） |
| `--name` | 否 | 显示名，默认从 API 自动解析 |
| `--days` | 否 | K线根数（默认 120，推荐 120~250） |
| `--period` | 否 | K线周期：`DAY` / `WEEK` / `MONTH`（默认 `DAY` 日K线；外部常用指数仅支持 `DAY`） |
| `--output` | 否 | 输出目录（默认 `<工作目录>`） |

## 路由示例

| 用户表达 | 命令 |
|---------|------|
| "电子指数日K线" | `--code 801080` |
| "申万50近半年日K线" | `--code 801001 --days 125` |
| "沪深300日K研报" | `--code 000300 --days 120` |
| "创业板指K线走势分析" | `--code 399006 --days 120` |
| "电子周K线" | `--code 801080 --period WEEK` |
| "银行月K线" | `--code 801780 --period MONTH` |

## 输出

stdout 最后一行 JSON 摘要：

```json
{
  "status": "ok", "mode": "kline_report",
  "code": "801080", "name": "电子", "bars": 120,
  "range": "2026-02-13~2026-08-14",
  "last_close": 9022.47, "period_chg_pct": 26.98,
  "candle_signals_count": 45,
  "render_files": {"kline-report": {"html": "<绝对路径>/电子801080_日K线研报.html"}}
}
```

**交付规范（必须）**：用 present_files 推送 `render_files["kline-report"]["html"]`，并在回复中给出核心结论（最新收盘、区间涨幅、MA 状态、最近形态信号、量能提示）。

## 已知坑

- **形态信号是启发式判定**（吞噬/锤子/晨星/三白兵等，纯标准库实现，无 pandas 依赖），信号只反映历史形态，不构成预测；数量多属正常（日线噪音）。
- 外部指数和申万行业行情优先使用 westock；以实际 `range` 为准，不自行假设最新数据日期等于查询日。网页补充须核实同一品种、日期和口径。
- 外部常用指数仅支持日K线（`--period DAY`），周/月K线传 `--period WEEK/MONTH` 会报错。
- 本脚本是单指数K线的**唯一入口**（原 `sw_chart.py --mode kline` 已移除）；需要技术指标子图/多指数对比走 `sw_chart.py` 的 indicator/compare 模式。
- 生成的 HTML 使用 ECharts CDN（需联网渲染图表）；交付前如环境允许，可对 HTML 内联 JS 做一次语法自检（`node --check`）。
