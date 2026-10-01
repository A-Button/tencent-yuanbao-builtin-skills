> 行情优先使用 westock；必要时通过网页检索补充并核实来源、日期与口径。执行与交付遵循 [DATA_SOURCE.md](DATA_SOURCE.md)；最终回复只表达结果与分析范围，不转述内部诊断。

# SW_TECH — 单指数技术面诊断

## 1. 概述

单一指数的全量技术指标分析：MACD / RSI / KDJ / BOLL / CCI / ATR / OBV / ADX 8 大指标 + 多空信号矩阵 + 综合评分 + 支撑压力位。回答"XX 技术面 / 技术分析 / 买卖信号"。

## 2. 输入

```
sw_tech.py --code CODE [--name NAME] [--period DAY|WEEK|MONTH] [--days N]
           [--event EVENT] [--forward-days N]
```

| 参数 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `--code` | 是 | — | 6 位申万指数代码（如 `801780`） |
| `--name` | 否 | 空 | 展示名（便于用户理解，如 `银行`） |
| `--period` | 否 | `DAY` | K 线周期：`DAY` / `WEEK` / `MONTH` |
| `--days` | 否 | `120` | 回溯 K 线根数；最小 60（脚本内部 `max(days, 60)`；传 `--event` 时自动提升至 ≥500 以检出足够历史事件） |
| `--event` | 否 | 无 | **追加历史事件后验**：`macd_golden` / `macd_dead` / `kdj_golden` / `kdj_dead` / `boll_break_high` / `boll_break_low` / `ma5_20_golden` / `ma5_20_dead` / `ma20_60_golden` / `ma20_60_dead` |
| `--forward-days` | 否 | `20` | 事件后观测 N 日收益率（仅 `--event` 生效） |

**事件后验说明**（`--event` 追加能力，原独立 `sw_event_stats.py` 已整合进本脚本）：在技术面诊断基础上，对指定技术事件做历史回测——检出窗口内全部事件、统计随后 N 日平均/中位数收益、胜率、最佳/最差、最近 3 次；HTML 渲染为"指标综合图 + 事件行情折线 + 收益分布直方图 + 统计表"。

**时间修饰转换**（agent 按 SKILL.md 日期解析规则处理）：
- "近一月" → `--days 22` / "近一季" → `--days 66` / "近半年" → `--days 125` / "近一年 / 今年以来" → `--days 250`

## 3. 输出

```json
{
  "status": "ok",
  "code": "801960", "name": "石油石化", "period": "DAY",
  "bars": 250, "range": "2025-04-08~2026-04-17",
  "latest_close": 2912.4,
  "score": 33, "bullish": 2, "bearish": 5, "neutral": 2,
  "support": [2903.78], "resistance": [3010.02, 3086.96],
  "summary_text": "指数: 石油石化(801960), 周期: DAY, 最新收盘: 2912.40, 技术信号: MA趋势=bearish(...); MACD=bearish(死叉放量); ...; 综合评分: 33/100, 支撑位: [...], 阻力位: [...]"
}
```

| 字段 | 含义 |
|------|------|
| `score` | 综合评分 0-100（越高越多头） |
| `bullish` / `bearish` / `neutral` | 多空中信号数（总和 = 8 或 9） |
| `support` / `resistance` | 关键支撑 / 压力位（最多各 2 个） |
| `summary_text` | 含每个技术指标的状态 + 评分 + 支撑压力 — **agent 必须引用** |

**颜色口径**：图表和正文信号摘要按 A 股配色，`bullish` / 多头 / 偏强用红色，`bearish` / 空头 / 偏弱用绿色，`neutral` / 中性用灰色。

## 4. 路由示例

| 用户说 | Agent 执行命令 |
|-------|--------------|
| "申万50 技术面" | `sw_tech.py --code 801001 --name 申万50` |
| "石油石化今年以来技术分析" | `sw_tech.py --code 801960 --name 石油石化 --days 250` |
| "银行周线技术诊断" | `sw_tech.py --code 801780 --name 银行 --period WEEK` |
| "医药生物近半年买卖信号" | `sw_tech.py --code 801150 --name 医药生物 --days 125` |
| "银行 MACD 金叉后 20 天表现" | `sw_tech.py --code 801780 --name 银行 --event macd_golden` |
| "电子 KDJ 死叉后 5 日胜率" | `sw_tech.py --code 801080 --name 电子 --event kdj_dead --forward-days 5` |

## 5. 已知坑 / 边界

- `--days` 最小 60（低于此脚本自动抬到 60），否则指标不稳定
- **严禁预测涨跌**（AGENTS.md 硬性规则 #5）。回复只陈述信号状态，不说"明天会跌"
- 用户没给具体指数（"某行业技术面"）→ 先触发澄清（`clarification-patterns.md` 模板 1）
- **事件后验**（`--event`）：事件检出依赖足够历史窗口，`--days` 过短时脚本自动提升取数；事件距今不足 `--forward-days` 日的不纳入统计（无法观测完整前向收益）
- 若要**深度综合报告**（技术+基本面+成分+风险）→ 走 `sw_deep.py`
- 与 `sw_chart.py --mode indicator` 区别：后者只画单个指标图（如 MACD），本脚本给 8 个指标 + 多空评分
