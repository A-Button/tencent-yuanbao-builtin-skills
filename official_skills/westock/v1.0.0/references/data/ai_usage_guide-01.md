# WeStock Data - AI 深度参考指南 · 分册 01

[本手册索引](ai_usage_guide.md) · [技能入口](../../SKILL.md)

> 仅查当前需要的章节；示例和分析模板不增加用户条件。遵循入口的停止规则，默认文字回答，仅明确要求文件时创建文件。

# WeStock Data - AI 深度参考指南

> **定位**：本文档提供详细的数据格式参考、分析模板。命令列表和基本用法请参见 [SKILL.md](../../SKILL.md)。
> 完整分析场景示例请参见 [scenarios-guide.md](./scenarios-guide.md)。

---

## 一、输出格式

命令执行后输出 **Markdown 表格**，AI 直接从表格中读取数据进行分析。

**单股查询**：输出一个 Markdown 表格，每列对应一个数据字段。

**批量查询**：输出批量摘要行 + 每个 symbol 的独立表格。

**查询失败**：可能输出带`success: false`/`error`的JSON，也可能只有业务错误文本；退出码0不保证业务成功。`--raw`在单标的、批量和日期模式下的结构不固定，按[解析分支](../parsing.md)识别，不统一取某一层`data`。



---

## 二、各命令数据格式

### 实时行情（`westock quote`）

输出表格列（共通字段，三市场均返回）：
`code | name | price | prevClose | open | high | low | volume | amount | change | changePercent | turnoverRate | volumeRatio | rangePct | avgPrice | peRatio | peFwd | peLyr | pbRatio | dividendRatioTtm | totalMarketCap | circulatingMarketCap | totalShares | floatShares | high52week | low52week | chg5d | chg10d | chg20d | chg60d | chgYtd`

#### 市场差异化字段（按 `market_type` 区分）

| 字段 | 说明 | A股 | 港股 | 美股 |
|------|------|:---:|:---:|:---:|
| `price_ceiling` | 涨停价（元） | ✅ | — | — |
| `price_floor` | 跌停价（元） | ✅ | — | — |
| `inner_volume` | 内盘（主动卖出量） | ✅ | — | — |
| `outer_volume` | 外盘（主动买入量） | ✅ | — | — |
| `wb_ratio` | 委比（%） | ✅ | ✅ | — |
| `lot` | 每手股数 | — | ✅ | — |
| `adr_conversion_price` | ADR 换算价（港元） | — | ✅ | — |
| `relative_hk_stock_price` | 相对港股价格 | — | ✅ | — |
| `relative_hk_stock_chg_pct` | 相对港股涨跌幅（%） | — | ✅ | — |
| `dividend_ttm` | 股息 TTM（元） | — | ✅ | ✅ |
| `eps_ttm` | 每股收益 TTM（元） | — | — | ✅ |
| `pre_market_price` | 盘前价（美元） | — | — | ✅ |
| `pre_market_price_chg` | 盘前涨跌额 | — | — | ✅ |
| `pre_market_price_chg_pct` | 盘前涨跌幅（%） | — | — | ✅ |
| `post_market_price` | 盘后价（美元） | — | — | ✅ |
| `post_market_price_chg` | 盘后涨跌额 | — | — | ✅ |
| `post_market_price_chg_pct` | 盘后涨跌幅（%） | — | — | ✅ |

> `market_type` 取值：`1`=沪A，`51`=深A，`62`=北交所，`100`=港股，`200`=美股。
> 差异字段仅在对应市场返回，其他市场该字段为 `undefined`，分析时需先判断。

#### 可转债维度字段（仅可转债代码返回，来源 `Kzz_*`）

可转债（沪 `sh11xxxx`/`sh13xxxx`、深 `sz12xxxx`）走 `westock quote` 时，在上述通用 + A股交易机制字段之外，额外返回以下转债维度字段；单只查询以竖排「项目/内容」表展示（规模换算为亿元、日期规整为 `YYYY-MM-DD`，缺失字段自动跳过）。

| 字段 | 说明 |
|------|------|
| `bond_equity_value` | 转股价值 |
| `bond_pure_value` | 纯债价值 |
| `bond_equity_premium` | 转股溢价率（%） |
| `bond_pure_premium` | 纯债溢价率（%） |
| `bond_double_low` | 双低 |
| `bond_rating` | 转债评级 |
| `bond_total_size` | 总规模（万元） |
| `bond_undue_size` | 剩余规模（万元） |
| `bond_term` | 期限（年） |
| `bond_undue_term` | 剩余期限（年） |
| `bond_due_date` | 到期日期 |
| `bond_ytm` | 到期收益率（%） |
| `bond_convertible` | 是否转股 |
| `bond_convert_price` | 转股价（元） |
| `bond_convert_start_date` | 转股起始日 |
| `bond_redeem_price_due` | 到期赎回价（元） |
| `bond_redeem_price_compulsory` | 强制赎回价（元） |
| `bond_redeem_price_trigger` | 强赎触发价（元） |
| `bond_buyback_price_trigger` | 回售触发价（元） |
| `bond_buyback_start_date` | 回售起始日 |
| `bond_stock_pb` | 正股 PB |
| `bond_stock_code` | 正股代码 |

> 行情接口**不返回债券简称**（`name` 为空）；可交换债及临近到期老券可能缺失部分 `Kzz_*` 字段，分析时需判空。完整发行要素/条款/现金流用 `bond`。

### 财务三大表（`westock finance`）

默认输出**核心字段窄表**（`--fields core`，★ 标记字段）；`--fields all` 恢复全字段。

> **字段后缀**：`_Q` = 单季度值，`TTM` = 过去 12 月滚动值。无后缀 = 累计值。
> ⚠️ **易混淆**：`OperatingRevenue`（营业收入）≠ `OperatingProfit`（营业利润），二者数值差异大，切勿看错列。
> **比率类指标直读披露值**：ROE / ROA / 毛利率等比率类字段，优先直读报表返回值，**禁止**用「净利润 / 净资产」自行拼算后当作报表值。

#### ★ 常用中文指标 → 英文字段 快速映射

> 用户用中文问某个指标时，先查此表确定所在表 + 字段名，再发对应 `--type` 请求。

| 中文名称 | 所在表 | 英文字段 |
|---------|-------|---------|
| 营业总收入 | income | `TotalOperatingRevenue` |
| 营业收入 | income | `OperatingRevenue` |
| 营业成本 | income | `OperatingCost` |
| 营业利润 | income | `OperatingProfit` |
| 利润总额 | income | `TotalProfit` |
| 归母净利润 | income | `NPParentCompanyOwners` |
| 扣非净利润 | income | `NPDeductNonRecurringPL` |
| 研发费用 | income | `RAndD` |
| 毛利率 | income | `GrossIncomeRatio` |
| 净利率 | income | `NetProfitRatio` |
| ROE | income | `ROEWeighted` / `ROE` |
| ROA | income | `ROA` |
| 营收增长率 | income | `TORGrowRate` |
| 净利润增长率 | income | `NPParentCompanyYOY` |
| 基本每股收益 | income | `BasicEPS` |
| 营业收入TTM | income | `OperatingRevenueTTM` |
| 总资产 | balance | `TotalAssets` |
| 总负债 | balance | `TotalLiability` |
| 净资产(股东权益) | balance | `TotalShareholderEquity` |
| 资产负债率 | balance | `DebtAssetsRatio` |
| 流动比率 | balance | `CurrentRatio` |
| 速动比率 | balance | `QuickRatio` |
| 经营现金流净额 | cashflow | `NetOperateCashFlow` |
| 投资现金流净额 | cashflow | `NetInvestCashFlow` |
| 筹资现金流净额 | cashflow | `NetFinanceCashFlow` |
| 自由现金流(公司) | cashflow | `FCFF` |

> **使用规则**：用户只问营收/利润/ROE 等利润表指标 → `--type income`；只问资产/负债 → `--type balance`；只问现金流 → `--type cashflow`。**只在用户明确要求"三大报表""全面分析"时才不加 `--type`。**

#### A 股利润表（income）字段

| 字段 | 说明 |
|------|------|
| ★ `InfoPublDate` | 报告发布日 |
| `EnterpriseType` | 企业类型 |
| ★ `TotalOperatingRevenue` | 营业总收入（含其他业务收入） |
| `TotalOperatingCost` | 营业总成本 |
| ★ `OperatingRevenue` | 营业收入（主营业务） |
| `OperatingCost` | 营业成本 |
| `OperatingPayout` | 营业税金及附加 |
| `TotalAdminExpense` | 管理费用合计 |
| `OperatingExpense` | 销售费用 |
| ★ `RAndD` | 研发费用 |
| `FinancialExpense` | 财务费用 |
| ★ `OperatingProfit` | 营业利润（= 营业总收入 - 营业支出） |
| ★ `TotalProfit` | 利润总额 |
| ★ `NPParentCompanyOwners` | 归母净利润 |
| `BasicEPS` | 基本每股收益 |
| `DilutedEPS` | 稀释每股收益 |
| `PremiumsEarned` | 已赚保费（保险业） |
| `NetProxySecuIncome` | 代理买卖证券净收入（证券业） |
| `NetSubIssueSecuIncome` | 证券承销净收入（证券业） |
| `NetTrustIncome` | 信托业务净收入（信托业） |
| `_Q` 后缀 | 同名字段的单季度值（如 `OperatingRevenue_Q`） |
| `TotalOperatingRevenueTTM` | 营业总收入 TTM |
| `TotalOperatingCostTTM` | 营业总成本 TTM |
| `OperatingRevenueTTM` | 营业收入 TTM |
| `OperatingCostTTM` | 营业成本 TTM |
| `OperatingPayoutTTM` | 营业税金及附加 TTM |
| `GrossProfitTTM` | 毛利润 TTM |
| `OperatingProfitTTM` | 营业利润 TTM |
| ★ `NPParentCompanyOwnersTTM` | 归母净利润 TTM |

#### A 股资产负债表（balance）字段

| 字段 | 说明 |
|------|------|
| ★ `InfoPublDate` | 报告发布日 |
| `EnterpriseType` | 企业类型 |
| `CashEquivalents` | 货币资金 |
| `BillAccReceivable` | 应收票据及应收账款 |
| `Inventories` | 存货 |
| `OtherCurrentAssets` | 其他流动资产 |
| ★ `TotalCurrentAssets` | 流动资产合计 |
| `LongtermEquityInvest` | 长期股权投资 |
| `TotalFixedAsset` | 固定资产合计 |
| `IntangibleAssets` | 无形资产 |
| `GoodWill` | 商誉 |
| `TotalNonCurrentAssets` | 非流动资产合计 |
| `TotalLiabilities` | 总负债（含衍生） |
| `ShortTermLoan` | 短期借款 |
| `NotAccountsPayable` | 应付票据及应付账款 |
| `TotalCurrentLiability` | 流动负债合计 |
| `LongtermLoan` | 长期借款 |
| `TotalNonCurrentLiability` | 非流动负债合计 |
| ★ `TotalLiability` | 负债合计 |
| `PaidInCapital` | 实收资本（股本） |
| `CapitalReserveFund` | 资本公积 |
| `SurplusReserveFund` | 盈余公积 |
| `RetainedProfit` | 未分配利润 |
| `SEWithoutMI` | 归母股东权益 |
| ★ `TotalShareholderEquity` | 股东权益合计 |
| `TradingAssets` | 交易性金融资产 |
| `DerivativeAssets` | 衍生金融资产 |
| `ReceivablesFin` | 应收款项融资 |
| `AdvancePayment` | 预付款项 |
| `OtherReceivableED` | 其他应收款 |
| `BoughtSellbackAssets` | 买入返售金融资产 |
| `ContractAssets` | 合同资产 |
| `NonCurrentAssetIn1Year` | 一年内到期的非流动资产 |
| `LongtermReceivableAccount` | 长期应收款 |
| `InvestmentProperty` | 投资性房地产 |
| `TConstruInProcess` | 在建工程 |
| `OtherNonCurrentAssets` | 其他非流动资产 |
| `TradingLiability` | 交易性金融负债 |
| `OtherCurrentLiability` | 其他流动负债 |
| `AdvanceReceipts` | 预收款项 |
| `ContractLiability` | 合同负债 |
| `SalariesPayable` | 应付职工薪酬 |
| `OtherPayableED` | 其他应付款 |
| `NonCurrentLiabilityIn1Year` | 一年内到期的非流动负债 |
| `LTAccountPayableTotal` | 长期应付款合计 |
| `BondsPayable` | 应付债券 |
| `LeaseLiabilities` | 租赁负债 |
| `OtherNonCurrentLiability` | 其他非流动负债 |
| `OtherEquityinstruments` | 其他权益工具 |
| `Deposit` | 吸收存款（银行） |
| `LoanAndAdvance` | 发放贷款及垫款（银行） |
| `WorkingCapital` | 营运资金 |
| `InterestBearDebt` | 有息负债 |
| `EBIT` | 息税前利润 |
| `NPDeductNonRecurringPL` | 扣非净利润 |

#### A 股现金流量表（cashflow）字段

| 字段 | 说明 |
|------|------|
| ★ `InfoPublDate` | 报告发布日 |
| `EnterpriseType` | 企业类型 |
| `GoodsSaleServiceRenderCash` | 销售商品提供劳务收到的现金 |
| ★ `NetOperateCashFlow` | 经营活动现金流净额 |
| ★ `NetInvestCashFlow` | 投资活动现金流净额 |
| ★ `NetFinanceCashFlow` | 筹资活动现金流净额 |
| ★ `FCFF` | 自由现金流（企业） |
| ★ `FCFE` | 自由现金流（股权） |
| `_Q` 后缀 | 同名单季度值 |
| `NetOperateCashFlowTTM` | 经营活动现金流净额 TTM |
| `NetInvestCashFlowTTM` | 投资活动现金流净额 TTM |
| `NetFinanceCashFlowTTM` | 筹资活动现金流净额 TTM |
| `NetCashFlowTTM` | 现金净增加额 TTM |

#### 港股利润表（income）字段

| 字段 | 说明 |
|------|------|
| ★ `InfoPublDate` | 报告发布日 |
| `EnterpriseType` | 企业类型 |
| `CurrencyType` / `CurrencyUnit` | 币种 / 货币单位 |
| `PeriodMark` / `ReportType` | 报告期标识 / 类型 |
| ★ `OperatingIncome` | 营业收入 |
| `OperExpenses` | 营业支出 |
| `SalesExpense` | 销售费用 |
| `DevelopmentExpense` | 研发费用 |
| `AdministrationExpense` | 管理费用 |
| `DepDividerSale` | 折旧与摊销 |
| `AssetDeValue` | 资产减值损失 |
| ★ `OperatingProfit` | 营业利润 |
| `FinancialCost` | 财务成本 |
| `EarningBeforeTax` | 税前利润 |
| `Tax` | 所得税 |
| `AftaxProfitfcbusi` / `AftaxProfitfncbusi` | 税后本业务/非本业务利润 |
| ★ `EarningAfterTax` | 税后利润 |
| ★ `ProfitToShareholders` | 归股东利润 |
| `ProfitToMinority` | 少数股东利润 |
| ★ `BasicEPS` / `EPS` | 基本每股收益 |
| `NetAssetPS` | 每股净资产 |
| `OperCashFlowPs` / `CashflowPs` | 每股经营现金流 / 每股现金流 |
| `MainincomePs` | 每股主营收入 |
| ★ `RoeWeighted` | 加权平均净资产收益率（ROE） |
| ★ `ROA` | 总资产收益率 |
| ★ `GrossIncomeRatio` | 毛利率 |
| `OperatingProfitRatio` | 营业利润率 |
| `NetProfitRatio` | 净利率 |
| `EarningBeforeTaxRatio` | 税前利润率 |
| `Operprofittotp` / `Taxtotp` / `Opercashtotp` | 营业利润/税/经营现金流占营收比 |
| `DebtAssetsRatio` | 资产负债率 |
| `EquityMultipler` | 权益乘数 |
| `DebtEquityRatio` | 产权比率 |
| `CurrentRatio` / `QuickRatio` | 流动比率 / 速动比率 |
| `InventoryTRate` / `TotalAssetTRate` / `ArTRate` | 存货/总资产/应收账款周转率 |
| `InventoryTDays` / `ArTDays` | 存货/应收账款周转天数 |
| ★ `OperatingRevenueGr1y` | 营收同比增速 |
| `GrossIncomeGr1y` / `OperProfitGr1y` / `NetProfitGr1y` | 毛利/营业利润/净利润同比增速 |
| ★ `NpParentCompanyGr1y` | 归母净利同比增速 |
| `TotalAssetGr1y` / `BasicEpsGr1y` | 总资产/EPS 同比增速 |
| `OperatingRevenueGr3y` / `NetProfitGr3y` / `NpParentCompanyGr3y` | 营收/净利/归母净利 3 年复合增速 |
| `MainOperIncomeIndustry` / `MainOperIncomeProduct` / `MainOperIncomeRegion` | 主营收入行业/产品/地区分布 |

#### 美股利润表（income）字段

| 字段 | 说明 |
|------|------|
| `DisclosureCurrency` / `ShowCurrency` | 披露币种 / 展示币种 |
| `FinancialYear` | 财年 |
| ★ `Sales_Q` | 营业收入（单季度） |
| `Cogs_Q` | 营业成本（单季度） |
| ★ `GrossIncome_Q` | 毛利润（单季度） |
| `SaleGeneralAdminExp_Q` | 销售管理费用（单季度） |
| `OtherOperatingExp_Q` | 其他营业费用（单季度） |
| ★ `EBIT_Q` | 息税前利润（单季度） |
| `NonOperatingIncome_Q` | 非经营收入（单季度） |
| `InterestExpense_Q` | 利息费用（单季度） |
| `PretaxXordCharge_Q` | 税前特殊项目（单季度） |
| ★ `PretaxIncome_Q` | 税前利润（单季度） |
| `IncomeTax_Q` | 所得税（单季度） |
| `AffiliateCompIncome_Q` | 联营企业收益（单季度） |
| `OtherAdjustment_Q` | 其他调整（单季度） |
| `ConsolidateNetIncome_Q` | 合并净利润（单季度） |
| `MinorityInterestExp_Q` | 少数股东损益（单季度） |
| ★ `NetIncome_Q` | 净利润（单季度） |
| `PreferedStockDiv_Q` | 优先股股息（单季度） |
| `BasicNetIncome_Q` | 基本净利润（单季度） |
| ★ `BasicEPS_Q` / `DilutedEPS_Q` | 基本/稀释每股收益（单季度） |
| `NetIncomeAfterXord_Q` | 扣特殊项目后净利润（单季度） |
| `EBITDA_Q` | 息税折旧摊销前利润（单季度） |
| ★ `GrossMargin_Q` | 毛利率（单季度） |
| ★ `NetMargin_Q` | 净利率（单季度） |
| `OperatingMargin_Q` | 营业利润率（单季度） |
| `PretaxMargin_Q` | 税前利润率（单季度） |
| `SalesPs_Q` | 每股销售额（单季度） |
| 无后缀（如 `Sales`） | 累计值（美股数据源通常仅返回季度值 `_Q`，累计值可能为空） |

#### 美股资产负债表（balance）字段

| 字段 | 说明 |
|------|------|
| `DisclosureCurrency` / `ShowCurrency` | 披露币种 / 展示币种 |
| `FinancialYear` | 财年 |
| `CashShortTermInvestment` | 现金及短期投资 |
| `ShortTermReceivable` | 短期应收 |
| `Inventory` | 存货 |
| `OtherCurrentAssets` | 其他流动资产 |
| `CurrentAssets` | 流动资产合计 |
| `PPE` | 固定资产 |
| `AdvancedInvestment` | 预付投资 |
| `LongTermReceivables` | 长期应收 |
| `IntangibleAssets` | 无形资产 |
| `DeferredTaxAssets` | 递延所得税资产 |
| `OtherAssets` | 其他资产 |
| ★ `TotalAssets` | 总资产 |
| `ShortTermDebt` | 短期借款 |
| `AccountsPayable` | 应付账款 |
| `TaxPayable` | 应交税费 |
| `OtherCurrentLiabilities` | 其他流动负债 |
| `CurrentLiabilities` | 流动负债合计 |
| `LongTermDebt` | 长期借款 |
| `ProvisionRisk` | 风险准备金 |
| `DeferredTaxLiabilities` | 递延所得税负债 |
| `OtherLiabilities` | 其他负债 |
| ★ `TotalLiabilities` | 总负债 |
| `NonEquityReserve` | 非权益储备 |
| `PreferedStockValue` | 优先股价值 |
| `CommonStockEquity` | 普通股权益 |
| ★ `ShareHolderEquity` | 股东权益 |
| `CumMinorityInterest` | 累计少数股东权益 |
| ★ `TotalEquity` | 权益总额 |
| `TotalLiabilitiesAndEquity` | 负债与权益合计 |
| `BPS` / `TangiableBPS` | 每股净资产 / 每股有形净资产 |
| `CurrentRatio` / `QuickRatio` | 流动比率 / 速动比率 |
| ★ `LiabilityToAsset` | 资产负债率 |
| ★ `ROE` | 净资产收益率 |
| ★ `ROA` | 总资产收益率 |
| `AssetTurnover` | 总资产周转率 |
| `BusinessDist` / `RegionDist` | 业务分布 / 地区分布 |

#### 美股现金流量表（cashflow）字段

> 美股按季度披露，数据源仅返回 `_Q` 后缀字段，累计值字段为空。

| 字段 | 说明 |
|------|------|
| ★ `CFO_Q` | 经营活动现金流净额（单季度） |
| ★ `Capex_Q` | 资本支出（单季度） |
| ★ `CFI_Q` | 投资活动现金流净额（单季度） |
| ★ `CFF_Q` | 筹资活动现金流净额（单季度） |
| ★ `FreeCF_Q` | 自由现金流（单季度） |
| `NetIncomeCF_Q` | 净利润（单季度） |
| `DepCF_Q` | 折旧摊销（单季度） |
| `WorkingCapitalChg_Q` | 营运资金变动（单季度） |
| `DivCF_Q` / `StockChgCF_Q` / `DebtCF_Q` | 股息/回购/借款现金流（单季度） |

> ★ = `--fields core` 默认输出的核心字段；其余字段需 `--fields all` 或 `--raw` 获取。

### K线（`westock kline`）

输出表格列：`date | open | last | high | low | volume | amount | exchange | change_pct`

> `change_pct` = 当日涨跌幅（%），= (今收 - 前收) / 前收 × 100。

> K线数值为原始数值，AI 在分析时自行进行单位换算

> ⚠️ **周期支持差异**：**美股指数**（`us.DJI`/`us.IXIC`/`us.SPX` 等）**仅支持日K**（`--period day`），不支持分钟K和周/月/季/年K。

### 资金数据

#### 港股资金流向（`westock fund flow hk<代码>`）

| 字段 | 单位 | 说明 |
|------|------|------|
| `TotalNetFlow` | 港元 | 总净流入 |
| `MainNetFlow` | 港元 | 主力净流入 |
| `RetailNetFlow` | 港元 | 散户净流入 |

#### 港股卖空数据（`westock fund short hk<代码>`）

| 字段 | 单位 | 说明 |
|------|------|------|
| `ShortShares` | 股 | 卖空股数 |
| `ShortAmount` | 港元 | 卖空金额 |
| `ShortRatio` | % | 卖空比率（卖空股数/成交量） |

#### A股资金流向（`westock fund flow sh/sz<代码>`）

| 字段 | 单位 | 说明 |
|------|------|------|
| `MainNetFlow` | 元 | 主力净流入（正=流入，负=流出）|
| `JumboNetFlow` | 元 | 超大单净流入 |
| `BlockNetFlow` | 元 | 大单净流入 |
| `MidNetFlow` | 元 | 中单净流入 |
| `SmallNetFlow` | 元 | 小单净流入 |
| `MainInFlow` | 元 | 主力流入 |
| `MainOutFlow` | 元 | 主力流出 |
| `RetailInFlow` | 元 | 散户流入 |
| `RetailOutFlow` | 元 | 散户流出 |

> 扩展字段（历史数据）：`MainNetFlow5D`/`MainNetFlow10D`/`MainNetFlow20D`（5/10/20日主力净流入）、`MainInflowRank`（流入排名）、`MainInflowCircRate`（占流通盘比例）、`MainInflowIndustryRank`（行业排名）

#### 美股卖空数据（`westock fund short us<代码>`）

> ⚠️ **美股限制**：美股不支持 `westock fund flow`（资金流向），只支持 `westock fund short`（卖空数据）

| 字段 | 单位 | 说明 |
|------|------|------|
| `ShortRatio` | % | 卖空比率（卖空股数/流通股数） |
| `ShortShares` | 股 | 卖空股数 |
| `ShortRecoverDays` | 天 | 回补天数（卖空股数/日均成交量） |

#### 北向季度持仓（`westock fund north-holding <股票代码>`）

> 同时查询 `north_holding_detail_cur_quarterly`（最新季）与 `prev_quarterly`（次新季），合并为一张表输出。

| 字段 | 单位 | 说明 |
|------|------|------|
| `EndDate` | YYYYMMDD | 披露截止日 |
| `HoldingCap` | 元 | 持股市值 |
| `HoldingRatio` | % | 持股比例 |
| `HoldingShares` | 股 | 持股数量 |
| `CapChgQ` / `CapChgY` | 元 | 持股市值季/年变动 |

> ⚠️ 与日度 `westock fund flow` 不同：`westock fund north-holding` 是**季度披露**口径的全市场持仓明细。

#### 港股南下资金持仓（`westock fund south-holding <港股代码>`）

> 通过 `stock_quote_snapshot` 的 `LgtHoldInfo` 字段解析，支持批量。

| 字段 | 单位 | 说明 |
|------|------|------|
| `LgtHoldRatio` | % | 南下资金持有比例 |
| `LgtCapChgDaily` | 港元 | 日变动市值 |
| `LgtShareChgDaily` | 股 | 日变动份额 |
| `LgtCapChgQuarterly` | 港元 | 季变动市值 |
| `LgtShareChgQuarterly` | 股 | 季变动份额 |

#### 申万行业北向资金持仓分布（`westock fund north-holding <板块代码>`）

> 根据 `sw1_/sw2_/sw3_` 或 `pt…` 板块代码，查询 `north_holding_statis_sw*` 并按行业名称过滤。仅支持申万行业，不支持概念/地域板块。

| 字段 | 单位 | 说明 |
|------|------|------|
| `SW` | — | 申万行业名称 |
| `HoldingCap` | 元 | 行业北向持股市值 |
| `CapChgQ` / `CapChgY` | 元 | 持股市值季/年变动 |

