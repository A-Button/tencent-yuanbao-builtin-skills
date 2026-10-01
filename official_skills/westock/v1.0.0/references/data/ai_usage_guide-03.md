# WeStock Data - AI 深度参考指南 · 分册 03

[本手册索引](ai_usage_guide.md) · [技能入口](../../SKILL.md)

> 仅查当前需要的章节；示例和分析模板不增加用户条件。遵循入口的停止规则，默认文字回答，仅明确要求文件时创建文件。

### ETF 档案（`westock etf profile`）

| 字段 | 说明 |
|------|------|
| `trackIndexCode/Name` | 跟踪指数（清单 `etf_track_index`） |
| `establishDate` | 成立日期 |
| `trusteeInstitution` | 托管人 |
| `purchaseStatus` / `redemptionStatus` | 申购/赎回状态 |
| `investScope` / `investStrategy` | 投资范围/策略 |
| `isTPlus0` | 是否支持 T+0 |
| `subscriptionFee` / `managementFee` / `custodyFee` / `serviceFee` | 认购/管理/托管/销售服务费率(%) |
| `managers` | 基金经理履历（snapshot `EtfManagerInfo`） |
| `classification` | 4 级分类（清单 `etf_classification`）：`primary`/`secondary`/`tertiary`/`quaternary`/`memo` |
| `managerHistory` | 经理历史（清单 `etf_manager`）：`current`/`first`/`longest`/`history` |
| `allocation` | 资产配置（snapshot `EtfAssetAllocation` + 清单规模） |

### ETF 运作概览（`westock etf overview`）

| 字段 | 说明 |
|------|------|
| `totalAsset` / `etfSize` | 总资产/规模及周月季年变化 |
| `chgPct` / `chgPct5D` / `chgPct20D` / `chgPct60D` / `chgPct52W` / `chgPctYtd` | 涨跌幅（多周期） |
| `etfDisc` / `etfDiscAvg*` | 溢折率及同指数均值 |
| `turnoverRate` / `turnoverValue` / `etfTurnover*` | 换手率/成交额 |
| `ytdMaxDrawdown` / `maxDrawdown1M/3M/6M/1Y/3Y` | 最大回撤（snapshot `EtfPerformance`） |
| `etfInFlow` / `etfInFlow*Avg` | 净申购及周月季年均值 |
| `peTtm` / `pb` / `psTtm` / `pcfTtm` / `peg` / `roe` / `divTtm` | 估值绝对值 |
| `peTtmPct` / `pbPct` / … | 估值历史百分位 |

### ETF 持仓（`westock etf holdings`）

| 字段 | 说明 |
|------|------|
| `holdings` | 申赎清单成分股（清单 `etf_prlist_{code}` 优先，snapshot 兜底） |
| `topStockChanges` | 重仓股涨跌：`code`/`name`/`ratio`/`rate`/`change` |

### ETF 净值时序（`westock etf nav`）

| 字段 | 说明 |
|------|------|
| `date` | 交易日 |
| `nav` | 单位净值（优先 `EtfNav`，缺失时回退 `ClosePrice`） |
| `closePrice` | 场内收盘价（可能与 nav 不同） |
| `navChange` | 净值涨跌额（相邻两日 `EtfNav` 差分；区间内首日不返回） |
| `navChangePct` | 净值涨跌幅(%)（同上） |

> ⚠️ `nav` 的涨跌由客户端按 `EtfNav` 差分计算，**不是** `ChangePrice`（收盘价涨跌）。查场内 OHLC 用 `westock kline`，不是 `westock etf nav`。

---

## 四点六、公司回购字段

### 回购数据（`westock buyback`）

**港股字段**：
| 字段 | 说明 |
|------|------|
| `BuybackShares` | 回购股份(股) |
| `BuybackMoney` | 回购金额(港元) |
| `BuybackPrice` | 回购均价(港元) |
| `BuybackCumMoney` | 本轮回购累计金额(港元) |

**A股字段**（BuybackAttach 数组）：
| 字段 | 说明 |
|------|------|
| `BuybackFunds` | 本次回购资金(元) |
| `BuybackSum` | 本次回购数量(股) |
| `BuybackPrice` | 本次回购均价(元) |

> 回购数据按日期降序排列，仅返回有回购记录的交易日。

---

### 风险事件（`westock risk`）

#### 特别处理（ST）

| 字段 | 说明 |
|------|------|
| `type` | 特别处理类型（ST/\*ST/SST/撤销ST） |
| `explain` | 事项描述 |
| `date` | 信息发布日期 |
| `riskLevel` | 风险等级：high（高风险）、medium（中风险）、low（低风险） |

#### 股权质押

| 字段 | 说明 |
|------|------|
| `date` | 股权质押披露截止日期 |
| `floatPledgedVolume` | 无限售股份质押数量（万股） |
| `nonFloatPledgedVolume` | 有限售股份质押数量（万股） |
| `pledgeNum` | 质押笔数 |
| `pledgeRatio` | 质押比例 |
| `totalPledge` | 质押数量（万股） |
| `riskLevel` | 风险等级：high（质押比例≥50%）、medium（30%-50%）、low（<30%） |

#### 解禁信息

| 字段 | 说明 |
|------|------|
| `initialInfoPublDate` | 解禁信息首次发布日期 |
| `infoPublDate` | 解禁信息最新发布日期 |
| `estimateActual` | 解禁日期类型 |
| `shareHolderName` | 解禁股东名 |
| `changeReason` | 解禁原因 |
| `restrictedCondition` | 限售条件说明 |
| `newAFloatListed` | 新增可售A股 |
| `actualFloatListedShares` | 实际上市流通数量 |
| `riskLevel` | 风险等级：high、medium、low |

#### 诉讼仲裁

| 字段 | 说明 |
|------|------|
| `date` | 诉讼仲裁最新公告日期 |
| `actionDesc` | 行为描述 |
| `subjectMatterStat` | 案由简称 |
| `latestSuitSum` | 涉诉金额（元） |
| `eventSubject` | 事件主体 |
| `eventSubjectRole` | 事件主体在诉讼中的角色 |
| `plaintiff` | 诉讼仲裁原告 |
| `defendant` | 诉讼仲裁被告 |
| `plaintiffAssociation` | 原告与上市公司关联关系 |
| `defendantAssociation` | 被告与上市公司关联关系 |
| `caseStatus` | 仲裁状态 |
| `firstInstanceStatus` | 一审状态 |
| `secondInstanceStatus` | 二审状态 |
| `sppStatus` | 最高院监督状态 |
| `adjudgementStatus` | 判决执行状态 |
| `riskLevel` | 风险等级：high（涉诉金额>1亿或作为被告）、medium（>1000万）、low |

#### 增发信息

| 字段 | 说明 |
|------|------|
| `issueType` | 增发类别 |
| `eventProcedure` | 事件进程 |
| `advanceDate` | 预案公告日期 |
| `smDeciPublDate` | 决案公告日期 |
| `intentLetterPublDate` | 意向书发布日期 |
| `prospectusPublDate` | 新股说明书发布日期 |
| `sacApprovalPublDate` | 国资委通过日期 |
| `csrcApprovalPublDate` | 证监会批准日期 |
| `advanceValidStartDate` | 预案有效期起始日期 |
| `advanceValidEndDate` | 预案有效期截止日期 |
| `newSharesListDate` | 增发新股上市日期 |
| `stockType` | 增发A股类型 |
| `issuePurpose` | 增发目的 |
| `issueObject` | 发行对象 |
| `issuePriceCeiling` | 发行价上限（元） |
| `issuePriceFloor` | 发行价下限（元） |
| `issuePrice` | 每股发行价（元） |
| `issueVol` | 发行量（万股） |
| `seoProceeds` | 增发新股募集资金总额（元） |
| `seoNetProceeds` | 增发新股募集资金净额（元） |

#### 高管变动（LeaderChange）

| 字段 | 说明 |
|------|------|
| `leaderName` | 高管姓名 |
| `leaderPosition` | 职位（如 副总裁/董事/总经理） |
| `leaderPositionType` | 职位类型（如 经营层/董事会） |
| `leaderStartDate` | 任职起始日期（已规范化为 YYYY-MM-DD） |
| `leaderChangeReason` | 变动原因（如 退休/辞职/换届） |

> **接入说明**：通过 `stock_quote_snapshot` 截面查询，`LeaderChange` 字段是嵌套 JSON 数组字符串。结果按任职起始日期倒序。

#### 高管增减持（ExecutiveTransferPlans）

| 字段 | 说明 |
|------|------|
| `managerName` | 高管姓名 |
| `managerSharesChange` | 股份变动数量（**负数表示减持，正数表示增持**） |
| `managerDealPrice` | 成交均价（元） |
| `managerHoldChangeDeclareDate` | 公告日期（已规范化为 YYYY-MM-DD） |

> **接入说明**：`stock_quote_history` 取近 1 年序列 + `stock_quote_snapshot` 兜底最新一条，按 (公告日期, 姓名, 变动数) 三元组去重，结果按公告日期倒序。

#### 评级信息（BondRatingInfo）

| 字段 | 说明 |
|------|------|
| `rating` | 评级（如 AAA/AA+/AA） |
| `ratingOutlook` | 评级展望（如 稳定/正面/负面） |
| `ratingChgDirection` | 变动方向（如 维持/上调/下调） |
| `ratingStandard` | 评级标准 |
| `ratingOrg` | 评级机构（如 中诚信国际/联合资信） |

> **注意**：风险事件只提供客观数据展示，不进行主观评分或风险等级判定。用户需根据实际情况自行判断风险程度。无效代码或无风险事件的股票会输出"暂无风险事件"，AI 应如实反馈不要编造风险信息。

---

### 事件总览（`westock events`，42 类标签）

> **与 risk 的差别**：`westock risk` 是 8 类风险事件**细查**（按个股取明细字段），`westock events` 是 42 类事件标签**速览**（按 `stock_event` 全市场清单一次拉取后客户端过滤）。`westock events` 仅展示挂在股票身上的事件 ID + 中文描述，覆盖中性+利好+风险全场景，不含明细字段。

**返回字段**：

| 字段 | 说明 |
|------|------|
| `date` | 查询日期（YYYY-MM-DD） |
| `stocks[].code` | 股票代码（如 sh600519） |
| `stocks[].name` | 股票名称（清单未返回时通过 `stock_quote_snapshot` 兜底补全） |
| `stocks[].tagIds` | 命中的事件 ID 数组（按 `--types` 过滤后） |
| `stocks[].tagDescs` | 事件 ID 对应中文描述（与 tagIds 顺序一致） |

**42 类事件 ID 映射（按大类分组）**：

| 大类 | 事件 ID | 说明 |
|------|---------|------|
| 交易异动 | 1 | 过去1个月内的大宗交易 |
| 交易异动 | 21 | 过去2周内的龙虎榜上榜详情 |
| 交易异动 | 22 | 过去2周内的龙虎榜上榜统计 |
| 股本变动 | 2 | 过去1个月内发生了回购披露的 |
| 股本变动 | 5 | 在过去1个月内发布了实施公告但尚未除权除息(含权期) |
| 股本变动 | 6 | 在过去3天内已经除权除息(正在填权观察窗口期) |
| 股本变动 | 7 | 在过去1个月内发布了分红预案(已过董事会) |
| 股本变动 | 8 | 在过去1个月内发布了分红决案(已过股东大会) |
| 股本变动 | 17 | 定增上市后一月 |
| 股本变动 | 18 | 定增上市后三月 |
| 股本变动 | 19 | 定增上市前一月 |
| 股本变动 | 20 | 定增上市前一周 |
| 业绩披露 | 9 | 过去1个月新增发布业绩快报 |
| 业绩披露 | 10 | 过去1个月新增发布业绩预告 |
| 业绩披露 | 11 | 过去7天新增发布财报 |
| 业绩披露 | 12 | 已经披露了将在未来1个月内发布新财报 |
| 指数变动 | 13 | 刚加入重要指数成分股一周内 |
| 指数变动 | 14 | 已披露即将加入重要指数成分股 |
| 指数变动 | 15 | 刚被踢出重要指数成分股一周内 |
| 指数变动 | 16 | 已披露即将踢出重要指数成分股 |
| 董监高 | 23 | 过去1个月内有董监高变动 |
| 董监高 | 24 | 过去1个月内发生了董监高增减持的披露 |
| 董监高 | 25 | 披露了计划增持且正在计划实施中的 |
| 董监高 | 26 | 已经披露计划增持但尚未进入实施 |
| 董监高 | 27 | 披露了计划减持且正在计划实施中的 |
| 董监高 | 28 | 已经披露计划减持但尚未进入实施 |
| 股权事件 | 29 | 将在1个月内召开股东大会 |
| 股权事件 | 30 | 尚未否决或结束的吸收合并 |
| 股权事件 | 31 | 尚未否决或结束的资产重组 |
| 股权事件 | 32 | 已公告即将更名，尚未生效 |
| 股权事件 | 33 | 过去3个月内刚更名的观察期 |
| 股权事件 | 38 | 尚未否决或结束的要约收购 |
| 限售解禁 | 34 | 已经发布了实际解禁公告将在不远的近期发生实际解禁 |
| 限售解禁 | 35 | 实际解禁份额已上市的2周观察期内 |
| 限售解禁 | 36 | 预计将在未来3个月内解禁 |
| 法律处罚 | 3 | 已经披露被处罚但尚未生效 |
| 法律处罚 | 4 | 已经生效的重大违规处罚一月内 |
| 法律处罚 | 37 | 过去一个月内披露涉诉 |
| 停复牌 | 39 | 预计将在未来3天内复牌 |
| 停复牌 | 40 | 过去1周内已复牌的 |
| 停复牌 | 41 | 处在停牌中的股票 |
| 停复牌 | 42 | 停牌已超过30天的股票 |

> 完整中文描述与最新分组见上表（与代码同源）。

**典型用法**：

```bash
westock events sh600519                  # 个股事件标签速览
westock events sh600519,sz000001         # 批量

```

**与 risk 的选择**：
- 想知道**有没有**某类事件 → `westock events`（轻量速览，1 次接口拉清单）
- 想拿到**明细字段**（如解禁数量、质押比例、诉讼金额、高管姓名） → `westock risk`

> **数据特性**：`westock events` 命中规则由 `stock_event` 清单维护方决定（如"过去 1 个月内"、"未来 3 天内"等窗口）；某些 ID（如停复牌系列）只在事件发生窗口内才会被打标。当某只股票 `westock events` 返回为空时，应明确告知用户"当前无事件命中"，**不应编造事件**。

---

## 五、分析模板

### 成交量分析

1. `westock kline <CODE> --period day --limit 20` → 从表格中提取 `volume` 列
2. 计算：平均值、最大/最小值、前10日均值 vs 后10日均值
3. 识别：放量日（>均值×1.5）、缩量日（<均值×0.5）

### 资金流向分析

**A股**：`westock fund flow <CODE>` → 提取 `MainNetFlow`/`JumboNetFlow`/`BlockNetFlow` → 转换单位（元→亿元）→ 统计净流入/流出天数

**港股资金**：`westock fund flow <CODE>` → 提取 `TotalNetFlow`/`MainNetFlow` → 分析主力趋势

**港股卖空**：`westock fund short <CODE>` → 提取 `ShortShares`/`ShortAmount`/`ShortRatio` → 卖空比率>15%需关注

**美股卖空**：`westock fund short <CODE>` → 提取 `ShortRatio`/`ShortShares`/`ShortRecoverDays` → `ShortRatio`>10%或`ShortRecoverDays`>5天需关注

**指数/板块**：按 [数据命令](./commands.md) 核对 `westock fund flow` 对目标代码的支持范围，再读取实际返回的资金字段与单位；不使用旧的 `market <CODE>` 入口，不假定所有指数均支持。

### 技术指标分析

**MACD**：DIF与DEA交叉（金叉=买信号/死叉=卖信号）、MACD柱正负变化、DIF/DEA相对0轴位置

**KDJ**：K与D交叉、J值>80超买/<20超卖

**RSI**：RSI_6>70超买/<30超卖，RSI_6与RSI_12背离

**均线**：多头排列（MA5>MA10>MA20>MA60）、MA60/120/250作为支撑/压力位

### 筹码趋势分析（历史区间）

- 盈利率上升 = 获利盘增加（股价上涨）
- 平均成本抬升 = 筹码成本中枢上移（主力可能建仓）
- 集中度下降 = 筹码趋于集中（主力吸筹控盘）
- 集中度上升 = 筹码趋于分散（可能派发）

### 机构评级分析（港股/美股）

1. 评级共识度：`(ratingBuyCnt + ratingIncCnt) / ratingCnt`
2. 目标均价 vs 当前价 → 上涨/下跌空间
3. 港股：`earningsForecast` EPS × 目标PE → 合理估值区间

### A股一致预期分析

1. 目标价 vs 当前价 → 上涨空间
2. 多年度EPS增速 → 盈利增长确定性
3. PE走势 → 估值是否逐年降低（估值消化）
4. `institutionCnt` → 共识覆盖度

