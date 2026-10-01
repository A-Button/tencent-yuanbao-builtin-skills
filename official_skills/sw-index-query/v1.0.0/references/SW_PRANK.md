> 行情优先使用 westock；必要时通过网页检索补充并核实来源、日期与口径。执行与交付遵循 [DATA_SOURCE.md](DATA_SOURCE.md)；最终回复只表达结果与分析范围，不转述内部诊断。

# SW_PRANK — 周 / 月级截面排名

## 1. 概述

指定周末或月末日期的指数截面排名（涨跌 / PE / 股息率 / 换手率等），支持 `--offset` 选取历史周/月末。**C3 新增 `--compare-offset` 跨期反转对比**。回答"本月哪个行业涨最多 / 上月 PE 最低 / 本周换手率前 5 / 上月 vs 这月反转"。

## 2. 输入

```
sw_period_rank.py [--period P] [--offset N] [--compare-offset M]
                  [--metric M] [--order O] [--index-type T] [--scope S] [--limit L]
```

| 参数 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `--period` | 否 | `MONTH` | `WEEK` / `MONTH` |
| `--offset` | 否 | `0` | `0`=最近周/月末；`1`=上一个；`2`=上上一个 |
| `--compare-offset` | 否 | — | 对比基准 offset（如 `--offset 0 --compare-offset 1` = 本月 vs 上月） |
| `--metric` | 否 | `change_pct` | 排序指标：`change_pct` / `pe` / `pb` / `dp` / `turnover` / `volume` / `close` / `circ_mcap` |
| `--order` | 否 | 自动 | `asc` / `desc`。PE/PB 默认 asc；其他默认 desc |
| `--index-type` | 否 | `一级行业` | `市场表征` / `一级行业` / `二级行业` / `风格指数` |
| `--scope` | 否 | `all` | 仅 `一级行业` 生效：`consumer` / `tmt` / ... |
| `--limit` | 否 | `50` | 行数上限 |

## 3. 输出

**基本模式**（单期）:
```json
{
  "status": "ok",
  "period": "MONTH", "offset": 0,
  "bargaindate": "2026-03-31",
  "count": 10,
  "top5":    [{"name":"银行","code":"801780","change_pct":3.93}, ...],
  "bottom5": [{"name":"交通运输","code":"801170","change_pct":-5.54}, ...],
  "summary_text": "A股市场 月度 涨跌幅(%) 排行（2026-03-31）..."
}
```

**对比模式**（`--compare-offset N` 时额外字段）：
```json
{
  ...,
  "current_bargaindate": "2026-03-31",
  "compare_bargaindate": "2026-02-28",
  "reversals": [
    {"code":"801780","name":"银行","rank_now":1,"rank_prev":15,"change":14},
    ...
  ],
  "summary_text": "... 排名反转 TOP：银行从第15→第1（+14位），..."
}
```

## 4. 路由示例

| 用户说 | Agent 执行命令 |
|-------|--------------|
| "本月哪个行业涨最多" | `sw_period_rank.py --period MONTH --limit 10` |
| "上月 PE 最低" | `sw_period_rank.py --period MONTH --offset 1 --metric pe` |
| "本周换手率前 5" | `sw_period_rank.py --period WEEK --metric turnover --limit 5` |
| "上周 TMT 涨幅" | `sw_period_rank.py --period WEEK --offset 1 --scope tmt` |
| "本月 vs 上月 哪些行业反转" | `sw_period_rank.py --period MONTH --offset 0 --compare-offset 1` |
| "近 3 月月度 YTD 排名" | `sw_period_rank.py --period MONTH --offset 0 --metric change_pct` |

## 5. 已知坑 / 边界

- `bargaindate` 是 API 返回的**已收盘**周/月末日期；查询日是 4 月 18 → 月末最新是 3 月 31
- `--offset` 超过可用日期数会报错（如请求 10 年前的月末）
- `change_pct` 在月度是**该月区间收益**（非日涨跌）；周度类似
- 对比模式（`--compare-offset`）限定 rank 变化 ≥ 10 位才出现在 `reversals` 里
- 与 `sw_rank.py` 区别：RANK 是"整体时段"（YTD/Calmar/Sharpe），本脚本是"**明确锚定某周/月末**"
- 决策树：
  - 关键词 "本周/本月/上周/上月" → 本脚本
  - 关键词 "今天/最新" → `sw_valuation.py` 或 `sw_dashboard.py`
  - 关键词 "YTD/年化/Sharpe" → `sw_rank.py`
