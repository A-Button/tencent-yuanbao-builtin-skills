> 行情优先使用 westock；必要时通过网页检索补充并核实来源、日期与口径。执行与交付遵循 [DATA_SOURCE.md](DATA_SOURCE.md)；最终回复只表达结果与分析范围，不转述内部诊断。

# SW_CHART — 实时 / 指标 / 对比 三合一

> **更新（2026-08-18）**：原 `kline` 模式（单指数K线图）已移除——单指数日/周/月K线统一走 **`SW_KLINE_REPORT.md`（sw_kline_report.py 固定版式研报）**。本脚本保留 `realtime` / `indicator` / `compare` 三种模式。

## 1. 概述

统一图表脚本 3 种模式：`realtime` 实时分时、`indicator` K 线 + 技术指标子图、`compare` 多指数对比。回答"XX 实时行情 / MACD / 两个指数谁涨多"。**单指数 K 线（走势 / 日K / 周K / 月K）→ 路由到 `sw_kline_report.py`**（见 `SW_KLINE_REPORT.md`）。

## 2. 输入

```
sw_chart.py --mode MODE [--code C] [--name N] [--period P] [--days N | --start S --end E]
            [--indicators I] [--codes C1,C2] [--names N1,N2] [--compare-type T]
            [--anchor-date D --before-days X --after-days Y]
```

**通用参数**：

| 参数 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `--mode` | 是 | — | `realtime` / `indicator` / `compare`（**无 kline**） |
| `--code` | realtime/indicator 必填 | — | 申万代码；外部常用指数仅用于 compare 的 `--compare-type kline` |
| `--name` | 否 | 空 | 展示名 |
| `--period` | 否 | `DAY` | K 线周期：`DAY` / `WEEK` / `MONTH`（indicator 内部取数用） |
| `--days` | 否 | `90` | K 线回溯根数（与 `--start/--end` 互斥；indicator 模式最小 60） |

**日期区间（可选，与 `--days` 互斥；仅 indicator 模式）**：

| 参数 | 说明 |
|------|------|
| `--start YYYYMMDD` + `--end YYYYMMDD` | 精确区间。两者相同时改用 `--days` 或 `--anchor-date` 展示近期走势 |
| `--anchor-date YYYYMMDD` + `--before-days N` + `--after-days M` | 围绕锚点日期取前后窗口（如"春节前后 30 天"的指标走势；**仅 indicator 模式**） |

**indicator 模式**：`--indicators macd,kdj,rsi,boll,cci,atr,obv,adx`（逗号分隔，**默认全量 8 个指标**）。交互式 HTML 渲染为**综合指标图**：主图 K线+MA5/10/20+BOLL 三轨，下方按类型分 MACD / KDJ / RSI / CCI / ADX / ATR / OBV 子图（十字光标联动）。若只想看单个指标，可传 `--indicators macd` 等子集。

**compare 模式**：

| 参数 | 说明 |
|------|------|
| `--codes a,b,c` | 2-3 个指数代码 |
| `--names A,B,C` | 对应展示名（顺序对齐） |
| `--compare-type` | `realtime` 当日分时对比 / `kline` 历史归一化对比（默认 `realtime`） |

`compare-type=kline` 支持外部常用指数（见 `index-codes.md`）。传参仍使用 `--code` / `--codes`，脚本内部自动完成取数与对齐。

**外部常用指数参数值（`kline` / `compare-type=kline`；同一代码表也用于成分股和模式识别）**：

| `--code`/`--codes` 值 | 名称 |
|------|------|
| `000001` | 上证指数 |
| `000016` | 上证50 |
| `000010` | 上证180 |
| `000300` | 沪深300 |
| `000905` | 中证500 |
| `000852` | 中证1000 |
| `932000` | 中证2000 |
| `000510` | 中证A500 |
| `930050` | 中证A50 |
| `399001` | 深证成指 |
| `399106` | 深证综指 |
| `399006` | 创业板指 |
| `399102` | 创业板综 |
| `399005` | 中小100 |
| `399330` | 深证100 |
| `000688` | 科创50 |
| `000698` | 科创100 |
| `000699` | 科创200 |
| `899050` | 北证50 |
| `000985` | 中证全指 |
| `HSI` | 恒生指数 |

## 3. 输出

运行 `sw_chart.py` 时按路由示例直接执行。平台环境自动渲染模板；本地/CLI 环境由 `sw_render.py` + `sw_html_render.py` 把图表数据渲染为**交互式 HTML 页面**（分时折线 / 指标综合图 / 对比折线），路径通过 JSON 摘要的 `render_files` 字段返回。**Agent 必须用 present_files 推送 HTML 文件给用户展示**，同时基于最后一行 JSON 摘要撰写文字回复。

**realtime**:
```json
{"status":"ok","mode":"realtime","code":"801001","name":"申万50",
 "latest":3939.7,"prev_close":3930.46,"date":"20260417","time":"14:59:50",
 "sampled_count":1440,"point_interval":"10s","raw_count":1440,"summary_text":"..."}
```
`date` / `time` 直接来自 API 的最新可得分时点。实时分时图保留 API 返回的 10 秒原始点，不做分钟降采样。Agent 只按该日期和时间表述。

**indicator**：K线字段 + `"indicators":"macd"`，模式为 `indicator`

**compare**:
```json
{"status":"ok","mode":"compare","compareType":"kline","count":2,
 "series":[{"name":"基础化工","code":"801030","changePct":16.69},
           {"name":"电子","code":"801080","changePct":19.44}],
 "summary_text":"..."}
```

## 4. 路由示例

| 用户说 | Agent 执行命令 |
|-------|--------------|
| "申万50 今天行情" / "实时行情" | `sw_chart.py --mode realtime --code 801001 --name 申万50` |
| "申万50 的 MACD" | `sw_chart.py --mode indicator --code 801001 --name 申万50 --indicators macd` |
| "基础化工和电子哪个涨幅高" | `sw_chart.py --mode compare --codes 801030,801080 --names 基础化工,电子 --compare-type kline --days 90` |
| "沪深300和申万300比较" | `sw_chart.py --mode compare --codes 000300,801300 --names 沪深300,申万300 --compare-type kline --days 125` |
| "中证1000和申万300比较" | `sw_chart.py --mode compare --codes 000852,801300 --names 中证1000,申万300 --compare-type kline --days 125` |
| "申万300 日K线" / "电子周K线" / "沪深300 近半年走势" | **单指数K线 → 路由到 `SW_KLINE_REPORT.md`，执行 `sw_kline_report.py`**（`--code 801300 --days 90` / `--code 801080 --period WEEK` / `--code 000300 --days 125`） |

## 5. 已知坑 / 边界

- **单指数K线图（`--mode kline`）已移除**，统一走 `sw_kline_report.py` 固定版式研报；本脚本只保留 realtime / indicator / compare
- indicator 模式 `--days` 低于 60 会被拉高到 60（指标需足够样本）
- compare 模式 `--codes` 建议 2-3 个；4+ 请走 `sw_heatmap --codes` 或 `sw_corr_matrix`
- 外部常用指数支持 `--compare-type kline` 的日 K 线走势对比；成分股走 `sw_comp.py` + 共享 `market_indices` adapter；实时分时、公告、估值排行仍只覆盖申万指数体系
- realtime 模式只引用脚本/API 返回的数据日期、时间和值；分时点保留 10 秒原始数据；成交量为 0 时也按返回值照实表述
- 用户问"某个指数 K 线"但没给代码 → 先触发澄清（`clarification-patterns.md` 模板 2）
- 要看**完整技术面**（8 个指标 + 评分 + 支撑压力）→ 走 `sw_tech.py`，不是 indicator 模式
- 要画**历史分位数曲线** → 走 `sw_quantile.py`
