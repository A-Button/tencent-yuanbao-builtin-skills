# WeStock Screener - AI 深度参考指南 · 分册 01

[本手册索引](ai_usage_guide.md) · [技能入口](../../SKILL.md)

> 仅查当前需要的章节；示例和分析模板不增加用户条件。遵循入口的停止规则，默认文字回答，仅明确要求文件时创建文件。

# WeStock Screener - AI 深度参考指南

> **定位**：本文档提供智能选股的详细返回数据格式、分析模板，以及完整的策略/标签代码列表。命令列表和基本用法请参见 [SKILL.md](../../SKILL.md)。
> 完整字段列表请参见 [fields-guide.md](./fields-guide.md)。

---

## 一、返回数据格式

### 格式化输出（默认）

输出 Markdown 表格，每行一只股票，列含股票代码、名称、收盘价、涨跌幅及表达式涉及的指标字段：

```
| code | name | ClosePrice | ChangePCT | PE_TTM | ROETTM |
| --- | --- | --- | --- | --- | --- |
| sh600519 | 贵州茅台 | 1690.00 | 1.25 | 28.50 | 32.15 |
| sz000001 | 平安银行 | 12.50 | -0.32 | 5.80 | 16.20 |
...
```


### 港股/美股字段差异

> 详见 [fields-guide.md](./fields-guide.md) 的逐市场字段表；查询返回字段与筛选表达式字段不要混用。

---

## 二、分析模板

### 3.1 价值选股

```bash
# 低PE（PE < 15）
westock screen condition --expression "intersect([PE_TTM > 0, PE_TTM < 15])" --date 2026-03-12 --limit 20 --orderby PE_TTM --asc

# 高股息（股息率 > 5%）
westock screen condition --expression "DividendRatioTTM > 5" --date 2026-03-12 --limit 20 --orderby DividendRatioTTM --desc

# PEG策略（PEG < 1，即 PE_TTM / 净利润增速 < 1）
westock screen condition --preset PEG --date 2026-03-12 --limit 20

# 低估值高ROE（PE < 15，ROE > 15%）
westock screen condition --expression "intersect([PE_TTM > 0, PE_TTM < 15, ROETTM > 15])" --date 2026-03-12 --limit 20 --orderby ROETTM --desc

# 破净股（PB < 1）
westock screen condition --expression "intersect([PB > 0, PB < 1])" --date 2026-03-12 --limit 20 --orderby PB --asc

```

**分析要点**：PE_TTM 分布（中位数/均值）、ROETTM 排名、结合市值和行业分类汇总

### 3.2 技术面选股

```bash
# 均线多头排列（MA5 > MA10 > MA20 > MA60）
westock screen condition --expression "intersect([MA_5 > MA_10, MA_10 > MA_20, MA_20 > MA_60])" --date 2026-03-12 --limit 20

# MACD看多状态（DIF > DEA，不等同于当日金叉）
westock screen condition --expression "DIF > DEA" --date 2026-03-12 --limit 20

# KDJ超卖（KDJ_J < 15）
westock screen condition --expression "KDJ_J < 15" --date 2026-03-12 --limit 20 --orderby KDJ_J --asc

# RSI超卖（RSI_6 < 25）
westock screen condition --expression "RSI_6 < 25" --date 2026-03-12 --limit 20 --orderby RSI_6 --asc

# 神奇九转绿9信号
westock screen condition --expression "NineTurn_9 = 1" --date 2026-03-12 --limit 20

# 布林带突破上轨（按字段表使用BOLL_UPPER；仍需当前服务支持）
westock screen condition --expression "ClosePrice > BOLL_UPPER" --date 2026-03-12 --limit 20

```

**分析要点**：均线间距（趋势强度）、配合换手率（TurnoverRate）验证、配合 MACD 交叉确认

### 3.3 资金面选股

```bash
# 主力净流入 > 1亿
westock screen condition --expression "MainNetFlow > 100000000" --date 2026-03-12 --limit 20 --orderby MainNetFlow --desc

# 主力持续流入（5/10/20日均为正）
westock screen condition --expression "intersect([MainNetFlow5D > 0, MainNetFlow10D > 0, MainNetFlow20D > 0])" --date 2026-03-12 --limit 20

# 主力5日流入 > 5亿
westock screen condition --expression "MainNetFlow5D > 500000000" --date 2026-03-12 --limit 20 --orderby MainNetFlow5D --desc

# 高换手率（> 5%）
westock screen condition --expression "TurnoverRate > 5" --date 2026-03-12 --limit 20 --orderby TurnoverRate --desc

```

**分析要点**：资金流入持续性、配合涨跌幅判断是否拉升期、筛选"主力流入但涨幅不大"的潜力股

### 3.4 财务分析选股

```bash
# 高ROE（ROE > 20%）
westock screen condition --expression "ROETTM > 20" --date 2026-03-12 --limit 20 --orderby ROETTM --desc

# 高成长（营收增速 > 30%，净利润增速 > 40%）
westock screen condition --expression "intersect([TORGrowRate > 30, NPParentCompanyYOY > 40])" --date 2026-03-12 --limit 20 --orderby NPParentCompanyYOY --desc

# 低负债（资产负债率 < 40%）
westock screen condition --expression "DebtAssetsRatio < 40" --date 2026-03-12 --limit 20 --orderby DebtAssetsRatio --asc

# 正经营现金流
westock screen condition --preset PositiveCashFlow --date 2026-03-12 --limit 20

# 高ROE低负债（ROE > 15%，负债率 < 50%）
westock screen condition --expression "intersect([ROETTM > 15, DebtAssetsRatio < 50])" --date 2026-03-12 --limit 20 --orderby ROETTM --desc

```

### 3.5 组合策略选股

```bash
# 高股息+低估值（股息率 > 4%，PE < 12，PB < 1.5）
westock screen condition --expression "intersect([DividendRatioTTM > 4, PE_TTM > 0, PE_TTM < 12, PB > 0, PB < 1.5])" --date 2026-03-12 --limit 20 --orderby DividendRatioTTM --desc

# 白马成长（高ROE + 稳定增长）
westock screen condition --expression "intersect([ROETTM > 15, TORGrowRate > 15, NPParentCompanyYOY > 15])" --date 2026-03-12 --limit 20 --orderby ROETTM --desc

# 困境反转（近期跌幅大但开始反弹）
westock screen condition --expression "intersect([Chg20D < -20, Chg5D > 0, Chg5D < 10])" --date 2026-03-12 --limit 20 --orderby Chg5D --desc

# 小盘价值（市值20-100亿，PE < 20）
westock screen condition --expression "intersect([TotalMV > 2000000000, TotalMV < 10000000000, PE_TTM > 0, PE_TTM < 20])" --date 2026-03-12 --limit 20 --orderby PE_TTM --asc

# 技术面+基本面组合（均线多头 + 低PE + 高ROE）
westock screen condition --expression "intersect([MA_5 > MA_10, MA_10 > MA_20, PE_TTM > 0, PE_TTM < 25, ROETTM > 12])" --date 2026-03-12 --limit 20 --orderby ROETTM --desc

# 次新股高成长（近端次新股 + 成长能力排行）
westock screen ranking --type fin_growth --within-label listeddate_3mons --limit 20

```

### 3.6 机构评级选股（港股/美股）

```bash
# 港股高机构评级（买入评级 >= 8家）
westock screen condition --expression "RatingBuyCnt > 7" --date 2026-03-12 --limit 20 --orderby RatingBuyCnt --desc --market hk

# 港股目标价上行空间（> 30%）
westock screen condition --expression "TargetPriceAvg > ClosePrice * 1.3" --date 2026-03-12 --limit 20 --orderby TargetPriceAvg --desc --market hk

# 美股高机构评级
westock screen condition --expression "RatingBuyCnt > 7" --date 2026-03-12 --limit 20 --orderby RatingBuyCnt --desc --market us

# 港股低估值 + 高评级
westock screen condition --expression "intersect([PeTTM > 0, PeTTM < 15, RatingBuyCnt > 4])" --date 2026-03-12 --limit 20 --market hk

```

### 3.7 按板块筛选

`--universe`的范围ID按当前`condition`帮助与服务契约核对；不要把搜索返回板块代码自动去掉`pt`就认定可用。以下是历史语法示例，只有范围ID已核验与目标板块一致时使用；不能将它们套用到`ranking`的范围参数。

```bash
# 在华为概念板块中筛选低PE股票
westock screen condition --expression "intersect([PE_TTM > 0, PE_TTM < 25])" --date 2026-03-12 --limit 20 --orderby PE_TTM --asc --universe 02021291

# 在人工智能板块中筛选高ROE股票
westock screen condition --expression "ROETTM > 15" --date 2026-03-12 --limit 20 --orderby ROETTM --desc --universe 02003800

```

**常见板块代码**（可通过 westock 搜索获取最新代码）：

| 板块名称 | 代码 | 板块名称 | 代码 |
|---------|------|---------|------|
| 华为概念 | 02021291 | 人工智能 | 02003800 |
| 华为昇腾 | 02GN2032 | 人形机器人 | 02GN2238 |
| 华为鸿蒙 | 02101423 | 低空经济 | 02GN2294 |
| 华为算力 | 02GN2266 | 半导体 | 02003010 |
| AI大模型 | 02GN2228 | 数据要素 | 02GN2200 |
| AI算力芯片 | 02GN2222 | 算力租赁 | 02GN2234 |

### 3.8 港股低估值高股息

```bash
# 港股高股息低估值（股息率 > 6%，PE < 8，PB < 0.8）
westock screen condition --expression "intersect([PeTTM > 0, PeTTM < 8, DivTTM > 6, PbLF > 0, PbLF < 0.8])" --date 2026-03-12 --limit 20 --orderby DivTTM --desc --market hk

# 港股低估值蓝筹（PE < 10，市值 > 500亿）
westock screen condition --expression "intersect([PeTTM > 0, PeTTM < 10, TotalMV > 500])" --date 2026-03-12 --limit 20 --orderby TotalMV --desc --market hk

# 美股低估值高股息
westock screen condition --expression "intersect([PeTTM > 0, PeTTM < 15, DivTTM > 3])" --date 2026-03-12 --limit 20 --orderby DivTTM --desc --market us

```

### 3.9 标签选股

标签选股适用于快速按分类获取股票列表，无需手写表达式。常见场景：

```bash
# 查看央企公司
westock screen label --type shareholder_central_state --date 2026-04-10

# 查看国企 + 央企（多标签）
westock screen label --type shareholder_central_state,shareholder_local_state --date 2026-04-10 --limit 50

# 查看大基金持仓
westock screen label --type shareholder_nicf_phase1,shareholder_nicf_phase2,shareholder_nicf_phase3 --date 2026-04-10

# 查看破净股
westock screen label --type valuation_lowpb --date 2026-04-10

# 查看高ROE股票
westock screen label --type fin_high_roettm --date 2026-04-10 --limit 50

# 查看业绩预增股
westock screen label --type fin_forecast_inc --date 2026-04-10

# 查看千元股
westock screen label --type price_up1000 --date 2026-04-10

# 查看超大盘股
westock screen label --type marketcap_super_big --date 2026-04-10

# 查看近期次新股
westock screen label --type listeddate_3mons --date 2026-04-10

# 查看 ST 股票（风险提示）
westock screen label --type risk_st --date 2026-04-10

```

**分析要点**：
- 标签选股返回的是符合该分类的股票列表，适合快速了解某类股票的整体情况
- 多标签并查不自动保证交集；按返回的各组语义解释，交集需明确计算且标注样本范围
- 候选可继续在本技能内用 `westock quote` / `westock finance` 批量精查，见 [数据命令](../data/commands.md)
- 此处股票标签模式支持沪深 A 股；ETF 使用下节的独立资产模式

**标签筛选 → 排行或精查**：

需要标签池内低估值排行时，使用 `westock screen ranking --type fin_valuation --within-label shareholder_central_state --limit 20`。需要其它数值条件时先核对该命令支持的字段和阈值，不能宣称未执行的条件已经满足。

已确定候选后，批量 `westock quote` / `westock finance` 用于核验详情；不要把行情查询包装成服务端条件选股。

### 3.9.1 ETF 选基（label --asset etf）

通过 `--asset etf` 切换 label 命令到 ETF 维度（40+ 个 KYP 主题池）。与默认的股票标签选股职责并列：

```bash
# 列出全部 ETF 主题池
westock screen label --asset etf --list
westock screen label --asset etf --list 行情表现             # 按分组筛选

# 单池查询
westock screen label --type high_dividend --asset etf               # 高股息 ETF
westock screen label --type size_1000 --asset etf                   # 千亿规模 ETF
westock screen label --type size_100 --asset etf --limit 50         # 百亿基金（分页）
westock screen label --type issue_in_3m --asset etf                 # 近 3 月新发 ETF

# 多池并查（每个池分别返回，非交集）
westock screen label --type low_valuation,high_roe --asset etf
westock screen label --type commodity,bond,currency --asset etf     # 商品/债券/货币型

```

**主题池分类速查**：

| 分类 | 代表性池 |
|------|----------|
| 上市时间 | `issue_new`(最新发行)、`issue_in_3m/in_1y/over_5y` |
| 规模 | `size_1000`(千亿)、`size_500`、`size_100`(百亿) |
| 行情表现 | `high_dividend`(高股息)、`low_valuation`(低估值) |
| 财务 | `high_roe`、`high_roa`、`high_npttm` |
| 经理 | `manager_long_tenure`(老将)、`manager_high_perf` |
| 类型/策略 | `commodity`(商品型)、`bond`(债券型)、`currency`(货币型)、`strategy_div`(红利) |

> ⚠️ **数据职责边界**：
> - 用户带"标签/主题"（如"高股息 / 千亿基金 / 科创板占比高"）→ 走 `westock screen label --asset etf`（横截面筛选）
> - 用户给具体 ETF 代码（如"沪深300ETF详情"）→ 走 `westock etf profile` / `westock etf overview` 等子命令
>
> ⚠️ **限制**：ETF 选基仅支持单日查询（不支持 `--start/--end` 区间）。

### 3.10 事件选股

事件选股适用于查询发生特定事件的股票列表，事件代码已自带时间窗口（如 `past_30`、`next_90`）：

```bash
# 预计解禁三月内
westock screen event --type shareunlock_next_90 

# 实际解禁公告后
westock screen event --type shareunlock_incoming 

# 董监高变动
westock screen event --type manager_change 

# 董监高增减持
westock screen event --type manager_sharechg 

# 计划减持未实施
westock screen event --type manager_shareplan_sell_incoming 

# 回购一月内
westock screen event --type buyback 

# 大宗交易一月内
westock screen event --type block_past_30 

# 龙虎榜上榜统计两周内
westock screen event --type longhu_statis_past_15 

# 将加入重要指数
westock screen event --type index_add_incoming 

# 重大资产重组
westock screen event --type regroup_unclosed 

# 分红预案公告后一月
westock screen event --type dividend_plan 

# 业绩预约一月内披露
westock screen event --type earnings_schedule 

```

**分析要点**：
- 事件代码已包含时间窗口（如 `past_30` 表示过去30天，`next_90` 表示未来90天）
- 事件选股仅支持 A 股

**事件筛选 → 数据精查**：

先查询 `westock screen event --type shareunlock_next_90 --limit 20`，再提取真实代码，以逗号批量调用 `westock quote` / `westock finance` 核验详情。

需要事件池内排名时使用 `screen ranking --within-event shareunlock_next_90` 及其支持的排序、阈值参数。行情精查不等于条件筛选；不要把截断候选的核验结果称为全市场筛选。

