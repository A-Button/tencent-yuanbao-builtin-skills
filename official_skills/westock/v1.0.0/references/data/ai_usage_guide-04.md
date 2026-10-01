# WeStock Data - AI 深度参考指南 · 分册 04

[本手册索引](ai_usage_guide.md) · [技能入口](../../SKILL.md)

> 仅查当前需要的章节；示例和分析模板不增加用户条件。遵循入口的停止规则，默认文字回答，仅明确要求文件时创建文件。

### 宏观经济数据分析

**可用指标**（短名带 region 前缀，详见 [macro-fields.md](./macro-fields.md)）：

| 短名 | 名称 | 分组 | 查询方式 |
|----------|------|------|----------|
| `cn_gdp` | GDP数量指标 | GDP | `--year` |
| `cn_cpi_ppi` | GDP价格指标(CPI/PPI) | GDP | `--year` |
| `cn_pmi` | GDP供给指标(PMI) | GDP | `--year` / `--start --end` |
| `cn_profit` | GDP供给指标(工业企业利润) | GDP | `--year` |
| `cn_valueadded` | GDP供给指标(工业增加值) | GDP | `--year` |
| `cn_consumption` | GDP需求指标(消费) | GDP | `--year` |
| `cn_investment` | GDP需求指标(投资) | GDP | `--year` |
| `cn_prosperity` | GDP供给指标(企业景气指数) | GDP | `--year` |
| `cn_fiscal` | GDP财政指标 | GDP | `--year` |
| `cn_power_consumption` | GDP供给指标(用电量) | GDP | `--year` |
| `cn_disposable_income` | GDP需求指标(可支配收入) | GDP | `--year` |
| `cn_capacity_utilization` | GDP供给指标(产能利用率) | GDP | `--year` |
| `cn_product_output` | GDP供给指标(宏观产量) | GDP | `--year` |
| `cn_export_value` | GDP需求指标(出口交货值) | GDP | `--year` |
| `cn_export` | GDP需求指标(进出口) | GDP | `--year` |
| `cn_financing` | 货币需求指标(社融) | 货币 | `--year` |
| `cn_fundquantity` | 货币供给指标(数量) | 货币 | `--year` |
| `cn_fundcost` | 货币供给指标(利率) | 货币 | `--year` |
| `cn_yield_curve` | 货币供给指标(国债收益率曲线) | 货币 | `--year` |
| `cn_mlf` | 货币供给指标(公开市场操作/MLF) | 货币 | `--year` |
| `cn_term_spread` | 期限利差与曲线形态 | 估值 | `--date`（最新值） |
| `cn_premium_curve` | 溢价率曲线（红利/股债） | 估值 | `--date`（日频历史） |
| `cn_premium_value` | 溢价率水平（含10年分位） | 估值 | `--date`（最新值） |
| `cn_core` | 最新核心宏观指标（聚合短名，一键拉 p1+p2） | 综合 | `--date` |
| `cn_forecast` | 宏观预测 | 综合 | `--year` |
| `cn_employment` | 就业情况 | 综合 | `--date`（日频） |
| `cn_calendar_hist` | 宏观日历历史 | 综合 | `--year` |
| `cn_calendar_future` | 宏观日历未来 | 综合 | `--date` |
| `cn_lpr` | 贷款市场报价利率(LPR) | 中国专项 | `--date` |
| `cn_caixin_pmi` | 财新PMI | 中国专项 | `--date` |
| `cn_installed_capacity` | 发电装机容量 | 中国专项 | `--date` |
| `us_*` (29 个主题) | 美股宏观（就业/通胀/货币政策/景气/经济增长/财政/能源/地产/消费/工业生产/对外贸易/国债持有/美联储/VIX/美元指数/三大股指/债务规模/期限利差/收益率曲线/政策利率锚/SOFR/广义利率） | 主题 | `--date` |
| `hk_*` (4 个主题) | 港股宏观（经济增长/进出口外储/货币/其它） | 主题 | `--date` |
| `jp_*` (6 个主题) | 日本宏观（经济增长/通胀/就业/景气/货币/进出口外储） | 主题 | `--date` |
| `eu_*` (6 个主题) | 欧元区宏观（经济增长/通胀/货币/景气/进出口外储/就业） | 主题 | `--date` |
| `expect_<iso3>` (36 个地区) | 海外预期日历（按 iso3 地区代码） | global | `--year` 或 `--start --end` |

> **三种查询方式**：
> 1. **`--year` / `--start --end`**（标准年份型）：cn_gdp/cn_cpi_ppi/cn_pmi 等大多数中国指标
> 2. **`--date`**（按指定日期）：`cn_core`/`cn_premium_*`/`cn_term_spread`/`cn_calendar_future`/`cn_lpr` 等中国日频指标，以及**所有海外主题**（us_/hk_/jp_/eu_）
> 3. **`westock macro expect --area <iso3> --year`**：海外预期日历（36 个地区）独立子命令
>
> **聚合短名**：`cn_core` 一键拉 `cn_core_p1 + cn_core_p2`（同时返回 7 大核心指标）
> **拉某 region 多个主题**：`macro indicator` **无** `--region`（那是 `macro list` 的参数），须传短名、多个用**空格**分隔。**推荐**加 `--limit 5` 仅取最近 5 条/指标
> **mode 校验**：传错 `--year` 给 mode=date 指标会报错；agent 不确定时先用 `westock macro list --region <r>` 查 mode

**PMI 分析要点**：
1. 制造业 PMI > 50 → 扩张，< 50 → 收缩
2. 关注新订单 vs 产成品库存差值 → 未来景气领先指标
3. 连续 3 个月趋势比单月数值更重要

**GDP 价格指标分析**：
1. CPI 同比 > 3% → 通胀压力，< 0 → 通缩风险
2. PPI vs CPI 剪刀差 → 上下游传导效率
3. 核心 CPI（剔除食品能源）→ 真实通胀水平

**货币指标分析**：
1. M2 增速 > 名义 GDP 增速 → 流动性宽裕
2. M1-M2 剪刀差收窄 → 企业活期存款增加（经营活跃）
3. 社融增量同比 → 实体经济融资需求
4. LPR/MLF 利率变动 → 央行政策信号

**国债收益率曲线分析**（`yield_curve`）：
1. 10Y-1Y 利差扩大 → 经济预期改善；倒挂 → 衰退预期
2. 长端利率（10Y/30Y）下行 → 风险偏好回落或宽松预期
3. 短端利率（1Y/2Y）跟随政策利率（MLF/逆回购）

**国债收益率曲线分析**（`cn_yield_curve`）：
1. 10Y-1Y 利差扩大 → 经济预期改善；倒挂 → 衰退预期
2. 长端利率（10Y/30Y）下行 → 风险偏好回落或宽松预期
3. 短端利率（1Y/2Y）跟随政策利率（MLF/逆回购）

**MLF 公开市场操作分析**（`cn_mlf`）：
1. 净投放（投放-到期）持续为正 → 央行主动宽松
2. 操作利率下调 → LPR 大概率跟随下调，宽松信号
3. 月末余额变化反映总量基调

**财政指标分析**（`cn_fiscal`）：
1. 财政赤字进度（`FISCAL_DEFICIT_PRG_YTD`）→ 全年赤字执行节奏
2. 税收/非税收占比 → 财政质量
3. 地方债发行（一般+专项）→ 基建发力强度
4. 民生支出占比（教育/医疗/社保）→ 财政结构

**就业指标分析**（`cn_employment`）：
1. 城镇调查失业率 → 整体就业景气
2. 16-24 岁青年失业率 → 结构性矛盾
3. 百度搜索指数（招聘/失业/找工作）→ 高频领先信号

**产能利用率分析**（`cn_capacity_utilization`）：
1. 制造业产能利用率 < 75% → 产能过剩；> 80% → 偏紧
2. 同比改善幅度大的行业 → 景气拐点

**进出口分析**（`cn_export`）：
1. 货物贸易差额 → 顺差/逆差对人民币汇率影响
2. 服务贸易差额（旅行/运输等）→ 跨境消费/物流变化
3. 外汇储备 + 黄金储备 → 央行储备资产配置

**宏观预测分析**（`cn_forecast`）：
1. 与官方公布值对比 → 市场一致预期偏离
2. PMI/CPI/M2 等核心指标的预测值 → 短期市场博弈基准
3. 多份预测值的中位数比单一来源更可靠

**溢价率分析**（`cn_premium_value` / `cn_premium_curve`）：
1. **股债溢价率（EquityPremium）= E/P - 10Y国债收益率**：衡量股票相对债券的吸引力
   - 数值越高 → 股票相对债券越便宜 → 股市性价比高
   - `EprPct10Y` 在 80%+ → 历史高位，股市偏便宜；< 20% → 历史低位，股市偏贵
2. **红利溢价率（DividendPremium）= 股息率 - 10Y国债收益率**：衡量高股息资产相对债券的吸引力
   - 高位 → 高股息策略胜率提升
3. **`cn_premium_curve`（约 2400 条历史日频）→ 长期分位上下轨**；`cn_premium_value`（1 条最新值 + 10 年分位）→ 当前快速判断

**期限利差分析**（`cn_term_spread`）：
1. **直读 `TermSpread`（bps）**：衡量长短端国债利差。仅做校核时，若 `Yield10Y`、`Yield2Y` 单位为 %，则 `(Yield10Y - Yield2Y) × 100` 才是 bps；不要混用百分数与基点。
   - 利差扩大（变陡） → 经济预期改善；倒挂 → 衰退预期信号
2. **`CurveForm*` 中文枚举**（牛陡/牛平/熊陡/熊平），多周期视角：
   - **牛陡**：短端下行更快 → 宽松预期/避险买短债
   - **牛平**：长端下行更快 → 衰退/通缩预期、避险买长债
   - **熊陡**：长端上行更快 → 通胀/经济过热预期
   - **熊平**：短端上行更快 → 央行紧缩预期
3. **长短端变化对比**（`LongDif*` vs `ShortDif*`）→ 判断曲线驱动来自哪一端

**海外主题宏观分析（事件日历型）**（`us_*` / `hk_*` / `jp_*` / `eu_*`）：

统一 schema：`OccurDate` / `IndicatorName` / `ActualValue` / `ForecastValue` / `FormerValue` / `OccurTime`

1. **三栏对比识别预期差**：
   - `ActualValue` > `ForecastValue` → 数据超预期（鹰派事件 / 利好风险资产视情况）
   - `ActualValue` < `ForecastValue` → 不及预期（鸽派事件）
   - `ActualValue` 与 `FormerValue` 比较 → 边际变化方向
2. **常用筛查模式**：
   - 通胀：核心 PCE/CPI 月率/年率（美联储锚 = 2%）；PPI 月率（上游传导）；通胀预期（脱锚警讯）
   - 就业：非农 vs 预期（强 → 削弱降息）；失业率 vs 自然失业率；时薪同比（粘性通胀来源）
   - 货币：联邦基金利率上下限；FFR 当前年度/后面 1-3 年/长期（点阵图含义）
3. **降息/加息预期跟踪**：组合 `us_monetary --date` + `westock macro expect --area usa --year`
4. **板块映射规则**：
   - 鸽派偏移 → 利好成长股 / 长久期资产 / 黄金
   - 鹰派偏移 → 利好金融股（净息差扩大）/ 价值股
   - 通胀粘性高 → 价值股 / 能源 / 必选消费
   - 通胀回落 → 长久期成长股 / 利率敏感板块

**海外预期日历**（`expect_<iso3>` 共 36 个地区，`westock macro expect --area <iso3> --year`）：

比海外主题宏观多一列 `Importance`（1=低 / 2=中 / 3=高）。

1. 按 `Importance` 筛重要事件（FOMC / 非农 / CPI / PPI / GDP）
2. 公布前看 `ForecastValue`（市场一致预期），公布后看 `ActualValue` vs `ForecastValue` 预期差
3. 与主题型差异：主题型按 region 分主题切片（适合"看美国通胀近期"）；海外预期按地区分单地区全套日历（适合"看某地区某年所有重要事件"）

**中美对比 / 全球三央行对比 / 港股联系汇率制度**：
- 详见 [scenarios-guide.md 场景 72-76](./scenarios-guide.md)

### 板块成份股分析

> ⚠️ **概念股查询重点**：当用户问"XX概念有哪些股票"（如"华为概念股"、"AI概念股"、"新能源汽车概念"），必须使用统一 `westock search` 入口两步查询：
> 1. `westock search 华为 --type sector` — 搜索板块代码
> 2. `westock sector constituent <搜索到的代码>` — 查询成份股
>
> **不要用外部搜索工具**。

**板块代码格式**：

| 前缀 | 类型 | 示例 |
|------|------|------|
| `sw1_` | 申万一级行业 | `sw1_pt01801080`(电子) |
| `sw2_` | 申万二级行业 | `sw2_pt01801081`(半导体) |
| `sw3_` | 申万三级行业 | `sw3_pt01801081` |
| `area_` | 聚源地域概念 | `area_pt0001`(北京) |
| `style_` | 聚源产业概念 | `style_pt0001` |
| `indus_` | 聚源风格概念 | `indus_pt0001` |

> 指数成份股请使用 `westock index` 命令：`westock index constituent sh000300`（A 股）/ `westock index constituent hkHSI`（港股）

**返回字段（港股指数成份股）**：

| 字段 | 说明 |
|------|------|
| `code` | 成份股代码（如 hk00700） |
| `name` | 成份股名称（如 腾讯控股） |
| `chg` | 涨跌幅（%） |
| `turnover` | 成交额 |

**与 A 股指数成份股的差别**：

| 对比项 | A 股指数 | 港股指数 |
|--------|----------|----------|
| 返回字段 | code, name | code, name, chg, turnover |
| 成份数量 | 全量（如沪深300返回300只） | 仅返回当前涨幅/跌幅前20只 |

> **注意**：港股指数`BkComponentStocks`可能仅返回涨跌幅前20只成份，不能当完整名单。需要完整成份时核对权威发布方和目标日期；另一指数或ETF持仓只能是明确标注的替代样本，不能拼成目标指数完整成份。无法确认完整性时保留缺口。


---

## 六、格式化输出规范

- 金额超过亿元：使用"亿元"/"亿港元"/"亿美元"
- 成交量超过万手：使用"万手"
- 涨跌幅：保留2位小数，带 +/- 号
- 日期：YYYY-MM-DD 格式
- 数据为空时说明"暂无数据"，**不可伪造数据**
- 港股/美股财务数据必须标注货币单位
