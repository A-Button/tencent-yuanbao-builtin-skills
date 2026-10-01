# WeStock Data - AI 深度参考指南 · 分册 02

[本手册索引](ai_usage_guide.md) · [技能入口](../../SKILL.md)

> 仅查当前需要的章节；示例和分析模板不增加用户条件。遵循入口的停止规则，默认文字回答，仅明确要求文件时创建文件。

### 机构评级（`westock rating`）

> 自 [Unreleased] 起重构为 **3 段精简结构**，A 股/港股/美股按市场自动分发，输出一致。

#### 段 1：目标价 & 当前评级摘要

输出表格列：`code | name | targetPriceAvg | targetPriceMax | targetPriceMin | upsideAvg | upsideMax | currentBuyCnt | currentIncCnt | currentHoldCnt | currentDecCnt | currentSellCnt | totalRatingCnt | forecastInstitutions`

- `targetPriceAvg/Max/Min`：目标价的平均/最高/最低值
- `upsideAvg/Max`：上涨空间百分比（基于当前价）
- `currentBuyCnt/IncCnt/...`：当前评级分布

#### 段 2：评级月度趋势统计（近 7 个月）

输出表格按月分布：`month | buyCnt | incCnt | holdCnt | decCnt | sellCnt`，反映买入/增持/中性/减持/卖出 5 档评级在最近 7 个月的变化趋势。

#### 段 3：价格 vs 目标价历史走势对比

输出表格列：`date | closePrice | targetPriceAvg`，逐日对比股价与机构目标价均值。

> **分析要点**：
> - 段 1 看共识强度（买入家数 vs 卖出家数）和上涨空间（upside）
> - 段 2 看评级动量（最近 1-2 个月评级是否上调/下调）
> - 段 3 看股价是否已 price-in 机构预期，或仍有低估空间

### 一致预期（`westock consensus`）

按代码前缀自动分发：A 股走 `queryCNConsensusForecast`，港股走 `queryHKConsensusForecast`，美股暂不支持。

#### A 股

输出表格，列含 `code | name | targetPrice`，以及 `forecasts` 数组中的 `year | revenue | netProfit | eps | pe | pb | ps | revenueYoy | netProfitYoy | institutionCnt`

#### 港股

按"时间维度"展示（行=季度，列=各指标）。顶层字段：`code | name | quarters`。

##### `quarters` 主表（按 `period` 升序）

| 字段 | 下游字段 | 说明 |
|------|---------|------|
| `period` | `ForecastPeriod` | 预测报告期（如 `2025Q4`、`2026Q1`） |
| `epsForecast` | `EPSForecast` | 每股收益-预测 |
| `revenueForecast` | `RevenueForecast` | 营业收入-预测（亿港币） |
| `netProfitForecast` | `NetProfitForecast` | 净利润-预测（亿港币） |
| `peRatioForecast` | `PERatioForecast` | 市盈率-预测 |
| `psRatioForecast` | `PSRatioForecast` | 市销率-预测 |
| `roeForecast` | `ROEForecast` | 净资产收益率-预测 |

> 列顺序固定为 EPS → 营收 → 净利润 → PE → PS → ROE（与微证券页面 tab 顺序一致）；某指标在该季度没有预测时该列为 `undefined`/缺省。

**分析要点**：目标价 vs 当前价（上涨空间）、EPS增速（盈利确定性）、PE走势（估值消化）、机构数（共识可信度）

---

### ESG 评级（`westock esg`）

查询中证 / 聚源两套 ESG 字母档评级。**与 `westock rating`（券商研报评级）和 `westock score`（量化评分）不同**；仅 A 股（`sh`/`sz`/`bj`）。

**命令用法**：

```bash
westock esg sh600519
westock esg sh600519,sz000651 --source csi

```

**输出格式**：
- 单股：按来源分行（中证 / 聚源），列含 `评级 | 发布日 | 截止日 | 变动`
- 批量：宽表 `中证评级 | 聚源评级 | …`

**字段（归一化后）**：

| 字段 | 下游字段 | 说明 |
|------|---------|------|
| `grade` | `EsgGrade` | 当前评级（中证：AAA/BBB…；聚源：A/B/C…，**不可跨源比高低**） |
| `endDate` | `EndDate` | 数据截止日 |
| `publDate` | `InfoPublDate` | 评级发布日 |
| `prevGrade` | （chg 清单，字段名待首条非空样本确认） | 上次评级 |

> **数据说明**：中证覆盖约 900 只，聚源覆盖更广（约 5000+），单股可能仅有聚源数据。

---

### 脱水研报（`westock dehydrated`）

通过 `research_report_list_get` 获取脱水研报摘要列表，包含机构调研和行业风口两种类型。

**命令用法**：
```bash
westock dehydrated                         # 脱水研报列表（默认返回10条）
westock dehydrated --limit 20 --offset 20    # 自定义分页
westock dehydrated detail <研报ID>         # 研报详情

```

**输出格式**：
- 列表：Markdown 表格，含 `id | title | summary | pub_time | institution`
- 详情：Markdown 格式，含关联标的、投资要点、正文（HTML）

> 研报ID 从列表的 `id` 字段获取，用于查询详情。

---

### 技术指标（`westock technical`）

> **指标**：MA_5/10/20/60/120/250、MACD/DIF/DEA、KDJ_K/D/J、RSI_6/12/24、BOLL_UPPER/MID/LOWER。

#### 用法与输出

输出表格列：`code | date | period | closePrice | ma.MA_5 | ma.MA_10 | ... | macd.DIF | macd.DEA | macd.MACD | kdj.KDJ_K | ...`

嵌套对象（ma/macd/kdj/rsi/boll）的字段会展平为 `分组.字段名` 格式。`period` 字段标识 K 线周期（day/week/month 等）。不指定 `--start/--end` 时按默认返回最新一期全量指标；在截面模式（不传 `--date`/`--start`/`--end`）下附加 `--limit N` 表示"最近 N 期"（自动按区间拉取后取末尾 N 条）；指定 `--start/--end` 后按区间逐交易日返回，`--limit` 控制条数（默认 2000）。支持 A 股/港股/美股 个股及指数/ETF/板块（与 `kline` 同源；分钟 K 的标的限制同 `kline`：除美股指数外均支持）。

**典型用法**：
- `westock technical sh600000` — 日K最新一期指标
- `westock technical sh600000 --date 2026-03-01` — 指定日期
- `westock technical sh600000 --period week` — 周K技术指标
- `westock technical sh600000 --start 2026-02-01 --end 2026-03-01 --limit 30` — 日K区间
- `westock technical sh600000 --period month --start 2025-01-01 --end 2026-07-10` — 月K序列
- `westock technical sh600519,sz000001` — 多股对比

#### 解读要点

- **MA**：MA_5/10/20/60/120/250，短期均线在长期均线之上为多头排列
- **MACD**：DIF 上穿 DEA 为金叉（买入信号），下穿为死叉
- **KDJ**：K > 80 超买区，K < 20 超卖区
- **RSI**：RSI_6 > 70 超买，RSI_6 < 30 超卖
- **BOLL**：价格突破上轨/下轨为超买/超卖信号
- **周期差异**：周K/月K 技术指标反映中期/长期趋势；分钟K反映短期波动

### 筹码成本（`westock chip`）

#### 截面

输出表格列：`code | name | date | closePrice | chipProfitRate | chipAvgCost | chipConcentration90 | chipConcentration70`

#### 历史区间

输出表格，每行一个交易日，列名同上。

**解读**：盈利率>80%=获利盘占优；收盘价>平均成本=整体盈利；集中度越低=筹码越集中（主力控盘可能）

### 市场/指数/板块（`market`）

#### 截面（`MarketQuoteData`）关键字段

| 字段 | 说明 |
|------|------|
| `closePrice`/`changePct` | 收盘价/涨跌幅 |
| `chg5D`/`chg10D`/`chg20D`/`chg60D`/`chgYtd` | 多日涨跌幅(%) |
| `advancingCount`/`decliningCount` | 上涨/下跌家数 |
| `mainNetFlow`/`jumboNetFlow`/`blockNetFlow` | 主力/超大单/大单净流入（沪深，元）|
| `midNetFlow`/`smallNetFlow` | 中单/小单净流入（沪深，元）|
| `totalNetFlow`/`retailNetFlow` | 总/散户净流入（港股，港元）|

> ⚠️ 美股不支持资金流向字段，仅支持 `westock fund short`（卖空数据）

#### 历史区间

输出表格，每行一个交易日，含 `date | closePrice | changePct | mainNetFlow | ...`

### 行业经营数据（`westock sector oper`）

查询各行业经营指标的历史序列数据，覆盖29个申万一级行业。数据包括价格、产量、销量、收入等经营指标。

**输出格式**：
- 按行业分组输出
- 每个行业输出一个 Markdown 表格，列含 `指标代码 | 指标名称 | 数据点 | 最新日期 | 最新值`

**返回字段说明**：

| 字段 | 说明 |
|------|------|
| `指标代码` | 经营指标的唯一代码（如 `F_COAL_INV_COAL_QHD_D`） |
| `指标名称` | 经营指标的中文名称（如"库存:煤炭:秦皇岛港:日"） |
| `数据点` | 该指标可用的历史数据点数量 |
| `最新日期` | 最新数据点的日期（格式：`YYYYMMDD`） |
| `最新值` | 最新数据点的数值 |

**使用示例**：

```bash
westock sector oper 煤炭                  # 查询煤炭行业经营数据
westock sector oper 煤炭 --date 2026-06-15  # 指定日期
westock sector oper --list                # 列出所有支持经营数据的行业

```

**支持行业**（共29个）：
传媒、电力设备、电子、房地产、纺织服饰、非银金融、钢铁、公用事业、国防军工、环保、机械设备、基础化工、计算机、家用电器、建筑材料、建筑装饰、交通运输、煤炭、美容护理、农林牧渔、汽车、商贸零售、社会服务、石油石化、食品饮料、通信、医药生物、银行、有色金属

**参数说明**：
- `<行业>`：支持中文名称（如"煤炭"）或标识（如 `coal`），**不要**传板块代码（如 `pt02021291`）
- `--list`：列出所有支持经营数据的行业
- `--date`：查询日期 YYYY-MM-DD（默认今天）

---

### 板块估值（`westock sector valuation`）

查询单个或多个板块的 PE/PB/PS/PCF/DIV 及**历史百分位**（相对自身历史区间）。**与 `westock market-overview --type valuation`（中证全指大盘估值）不同**；与 `westock sector forecast`（未来一致预期估值）互补。

**命令用法**：

```bash
westock sector valuation pt01801080
westock sector valuation pt01801080,pt01801081
westock sector valuation pt01801080 --date 2026-06-25

```

**输出格式**：
- 截面：Markdown 表，每行一个板块；支持多板块逗号批量对比
- 历史（`--start` + `--end`）：按 `EndDate` 升序的时间序列；**每次仅支持单板块**

**核心字段**（下游原始字段名，CLI 直接输出）：

| 字段 | 说明 |
|------|------|
| `code` / `name` | 板块代码 / 名称 |
| `EndDate` | 数据截止日（`YYYYMMDD`） |
| `PeTTM` / `PeTTMPct` | 市盈率 TTM / 历史百分位（**%**，越高表示相对历史越贵） |
| `PbLF` / `PbLFPct` | 市净率 LF / 历史百分位 |
| `PsTTM` / `PsTTMPct` | 市销率 TTM / 历史百分位 |
| `PcfTTM` / `PcfTTMPct` | 市现率 TTM / 历史百分位 |
| `DivTTM` / `DivTTMPct` | 股息率 TTM / 历史百分位 |
| `*PrevM/Q/W/Y` | 各指标相对上月/上季/上周/去年的变动 |

> **参数**：传**板块代码**（`pt*`）。支持申万行业及聚源概念/地域/产业。先用 `westock search --type sector` 获取代码。

**分析要点**：
- `PeTTMPct` / `PbLFPct` 等百分位：判断行业相对自身历史估值高低
- 与 `westock sector forecast` 的 `pe`/`peg` 对照：当前估值 vs 预期盈利增速是否匹配
- 与 `westock sector finance` 的 `roeTTM` 对照：盈利质量能否支撑估值

---

### 行业未来盈利预测（`westock sector forecast`）

查询申万一级/二级行业的机构一致预期盈利路径（未来 3 年）。**与 `westock consensus`（个股一致预期）不同**：无目标价/EPS，数值为**行业聚合**口径。

**命令用法**：

```bash
westock sector forecast pt01801780              # 申万一级银行
westock sector forecast pt01801081          # 申万二级半导体
westock sector forecast pt01801780 --date 2026-06-25

```

**输出格式**：
- 按行业分组，每组一个 Markdown 表（行=预测年度，按 `year` 升序）
- 顶层含行业名、`code`（pt 代码）、`swLevel`、`forecastDate`

**`forecasts` 主表字段**（列顺序：营收/利润 → 增速 → 估值）：

| 字段 | 下游字段 | 说明 |
|------|---------|------|
| `year` | `ConYear` | 一致预期年度 |
| `revenue` | `ConOr` | 一致预期营业收入（**万元**，行业加总） |
| `netProfit` | `ConNp` | 一致预期归母净利润（**万元**，行业加总） |
| `netAssets` | `ConNa` | 一致预期归母净资产（**万元**，行业加总） |
| `revenueYoy` | `ConOrYoy` | 营业收入同比增速（**%**） |
| `netProfitYoy` | `ConNpYoy` | 归母净利润同比增速（**%**） |
| `netProfitCagr2Y` | `ConNpYoy2Y` | 归母净利润两年复合增长率（**%**） |
| `pe` | `ConPe` | 一致预期市盈率（倍） |
| `pb` | `ConPb` | 一致预期市净率（倍） |
| `ps` | `ConPs` | 一致预期市销率（倍） |
| `roe` | `ConRoe` | 一致预期 ROE（**%**） |
| `peg` | `ConPeg` | 一致预期 PEG（**%**，清单口径，非常见 PEG 倍数） |

> **参数**：仅支持申万一级/二级板块代码（`pt*`）。**不支持**申万三级、聚源地域/产业/风格概念（如 `pt03001176` 海南地域概念会明确报错）。先用 `westock search --type sector` 获取申万行业代码。

**分析要点**：
- `netProfitYoy` / `netProfitCagr2Y`：盈利增速路径与确定性
- `pe` + `peg`：估值水平与成长性匹配（注意 `peg` 为 % 口径）
- `roe`：行业整体盈利能力
- 与 `westock sector valuation`（当前估值百分位）对照：预期利润增速能否消化估值

---

### 申万行业财务指标（`westock sector finance`）

查询申万行业成份股聚合的财报 TTM 指标。**与个股 `westock finance`（三大表）不同**；与 `westock sector forecast`（未来一致预期）互补。

**命令用法**：

```bash
westock sector finance pt01801780
westock sector finance pt01801780,pt01801080
westock sector finance pt01801780 --date 2026-03-31

```

**输出格式**：
- 默认：多行业合并为一张截面表（含 `name | code | swLevel`）
- `--date`：指定查询日期（**不支持** `--start`/`--end` 区间）

**核心字段（归一化后）**：

| 字段 | 下游字段 | 说明 |
|------|---------|------|
| `endDate` | `EndDate` | 财报期（`YYYYMMDD`） |
| `revenueTTM` | `RevenueTTM` | 营业收入 TTM（**万元**，行业加总） |
| `netProfitTTM` | `NetProfitTTM` | 归母净利润 TTM（**万元**） |
| `netProfitYoY` | `NetProfitYoY` | 净利同比增速（**%**） |
| `roeTTM` | `RoeTTM` | ROE TTM（**%**） |
| `debtRatio` | `DebtRatio` | 资产负债率（**%**） |
| `grossProfitRatioTTM` | `GrossProfitRatioTTM` | 毛利率 TTM（%） |
| `netProfitRatioTTM` | `NetProftRatioTTM` | 净利率 TTM（%，下游字段有拼写 typo） |

> **参数**：支持 sw1/sw2/sw3；聚源概念/地域会明确报错。历史查询需同时指定 `--start` 与 `--end`（与 `westock sector valuation` 一致）。

**分析要点**：`netProfitYoY`+`roeTTM` 看盈利质量；`debtRatio` 看杠杆；配合 `westock sector valuation` / `westock sector forecast` 构成基本面→估值→预期链。

---

### 市场总览（`westock market-overview`，A 股大盘画像）

8 个子类（type）归并到单一入口，提供 A 股大盘"宏观体检"。来源是 8 个 `market_statis_*` 后端清单。

| type | 中文 | 说明 |
|------|------|------|
| `summary` | 画像总评（默认） | 14 维度得分 + 状态文案（估值/情绪/技术/趋势/风格轮动/股市规模/宏观情绪/北向资金/两融情绪/PMI 等） |
| `trade` | 三大指数收盘统计 | 上证/深证/创业板 + 成交额多周期均值（5D/20D/60D） |
| `interval` | 三大指数多周期涨跌 | 5D/20D/60D/250D 涨跌 + 52 周高低 |
| `westock technical` | 大盘技术面 | MACD / KDJ / RSI / BOLL / MA |
| `updown` | A 股涨跌停 / 红绿盘 | 涨停/跌停家数 + 红绿盘比 + 创新高/新低家数 |
| `margin` | 两融余额变动 | 两融余额 + 多周期变动 |
| `valuation` | 估值百分位 | 中证全指 PE/PB/PS + 历史百分位 |
| `rotation` | 风格轮动 | 沪深300 / 中证1000 / 成长 / 价值 板块轮动 |

**用法**：
```
westock market-overview                    # 默认 summary（最常用，给 LLM 做"今日市场点评"）
westock market-overview --type trade       # 单 type
westock market-overview --type technical,updown   # 多 type 一次拉
westock market-overview --type all         # 全量 8 个
westock market-overview list               # 列出所有 type
```

**summary 14 维度** 每个维度含：`name`（维度名）、`westock score`（0~100 得分）、`status`（状态文案，如"估值偏高"、"情绪乐观"）。**这是给 AI 做今日市场点评最直接的入口** —— 一次调用即可得到"估值/情绪/技术/趋势/风格"5 大类共 14 个维度的状态画像。

### 排行数据（`rank`）

输出 Markdown 表格，列头为字段中文标签（来自 `list_data_schema`），如"市盈率TTM(倍)"、"股息率TTM(%)"等。

**返回信息**：
- 清单名称、查询日期、总条数
- 排序字段（中文标签）和方向（升序/降序）
- 分页信息（offset/limit/hasMore）
- 每行含股票代码、名称及各指标字段

**参数说明**：

| 参数 | 说明 | 可选值 |
|------|------|--------|
| 清单代码 | 排行清单代码，如 `fin_valuation` | 见 SKILL.md 排行清单表 |
| --limit | 每页条数，默认20，最大50 | 数字 |
| --offset | 偏移量，默认0 | 数字 |
| --desc | 排序方向，默认true（降序） | `true`/`false` |

> 字段中文标签由 API 的 `list_data_schema` 自动解析，无需手动映射

---

### 分红数据（`westock dividend/calendar`）

输出表格，字段因市场不同：

- **A股**：`reportEndDate | dividendFlag | procedure | dividendType | proposalSn | rightRegDate | exDiviDate | bonusShareRatio | tranAddShareRatio | cashDiviRMB | totalCashDiviComRMB | dividendPlan`
- **港股**：`reportEndDate | exDiviDate | cashPayDate | cashDivPerShare | specialDivPerShare | totalCashDivi | dividendPlan`
- **美股**：`exDivDate | regDate | payDate | dividendCurrency | dividend | dividendPlan`

> 美股可能额外包含 `splitInfo`（拆合股信息）

**参数说明**：
- 默认查询最近分红数据
- `--years N`：查询近N年分红历史（如 `--years 5`、`--years 10`）
- `--all`：返回所有记录（含未实施分红方案），默认只返回已实施分红的记录
- 返回记录按报告期/除权日降序排列（最新的在前）

### 财报披露日历（`westock disclosure`）

输出表格，字段因市场不同：

- **A股**：`reportEndDate | disclosureEndDate | disclosureDate | disclosureDesc`
- **港股**：`reportEndDate | disclosureDesc`
- **美股**：`reportEndDate | disclosureDate | disclosureDesc`

### 命令参数详细说明

#### notice list（公告列表）

| 参数位置 | 说明 | 可选值 |
|---------|------|--------|
| 代码 | 股票代码，支持逗号分隔批量 | - |
| 类型 | 公告类型 | `0`=全部（默认），`1`=财务，`2`=配股，`3`=增发，`4`=股权变动，`5`=重大事项，`6`=风险，`7`=其他 |

#### report list（研报列表）

| 参数位置 | 说明 | 可选值 |
|---------|------|--------|
| 代码 | 标的代码：个股（如 sh600000）或行业/板块（如 pt01801080），支持逗号分隔批量 | - |
| 页码 | 页码，默认1 | 数字，从1开始 |
| 每页数量 | 每页返回条数，默认20 | 数字 |
| 类型 | 研报类型 | `0`=全部（默认），`1`=研报，`2`=业绩会 |

#### calendar（投资日历 — 个股事件日历）

查询指定日期有哪些股票发生分红/财报/IPO/停复牌/会议/解禁/增发事件，按事件类型分组输出。
宏观经济日历请使用 `westock macro indicator cn_calendar_future|cn_calendar_hist`。

| 参数 | 说明 | 可选值 |
|---------|------|--------|
| `--date` | 查询日期 | `YYYY-MM-DD`，默认今天 |
| `--event` | 事件类型过滤 | `financial_report`/`dividend`/`ipo`/`trading_halt`/`meeting`/`lockup_release`/`rights_issue`/`all`，支持逗号分隔多类型，默认 `all` |
| `--market` | 市场 | `hs`（沪深）/ `hk`（港股）/ `us`（美股），默认 `hs` |
| `--limit` | 返回条数 | 数字，默认 10 |
| `--offset` | 偏移量 | 数字，默认 0 |

#### index constituent（指数成份股）

| 参数 | 说明 |
|------|------|
| 代码 | 指数代码，支持逗号分隔批量。A 股（如 sh000300）、港股（如 hkHSI）自动路由 |
| --list | 查询指数清单 |
| --search 关键词 | 搜索指数 |

#### connect（沪深港通成份股 / 北向 · 陆股通）

> 沪深港通成份股名单（标的池），不是资金流量数据；如需资金买卖方向请用 `westock fund flow` / `westock fund margin` / `westock fund block`。

| 参数 | 说明 | 可选值 |
|---------|------|--------|
| `--exchange` | 交易所（必填） | `sh`=沪股通，`sz`=深股通 |
| `--limit` | 每页条数，默认 50，最多 100 | 数字 |
| `--offset` | 偏移量（用于翻页） | 数字 |

---

## 三、货币单位处理

> **重要**：逐端点读取币种和数量级。港股财报可能采用港元、美元或人民币；不得仅按上市市场指定报表币种。

**港股**：检查 `CurrencyType`（"港币"/"美元"/"人民币"）和 `CurrencyUnit` 字段
- ✅ 正确：`营业收入：832.3亿港元`
- ❌ 错误：`营业收入：¥832.3亿`

**跨期对比注意**：同比/环比增长率可能受汇率换算影响，展示时建议添加说明：`"注：同比数据可能受汇率波动影响"`

---

## 四、单位换算

仅在返回字段明确采用下列单位时使用对应换算；不要把本表当成所有端点的默认单位。筛选排行、财报与行情的数量级可能不同。

| 已确认的原始单位 | 换算 |
|---|---|
| 手 | ÷10000=万手 |
| 元/港元/美元 | ÷100000000=相应币种的亿 |
| 万元/万港元/万美元 | ÷10000=相应币种的亿 |
| 百万元/百万港元/百万美元 | ÷100=相应币种的亿 |
| 股 | ÷1000000=百万股 |

---

## 四点五、ETF 数据字段

> **子命令**（必填）：`westock etf profile` 档案+资产配置；`westock etf overview` 运作概览；`westock etf holdings` 申赎清单+重仓涨跌；`westock etf nav` 净值时序。

