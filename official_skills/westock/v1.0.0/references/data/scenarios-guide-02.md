# WeStock Data - 常见分析场景详解 · 分册 02

[本手册索引](scenarios-guide.md) · [技能入口](../../SKILL.md)

> 仅查当前需要的章节；示例和分析模板不增加用户条件。遵循入口的停止规则，默认文字回答，仅明确要求文件时创建文件。

### 7.5 北向资金持仓查询

```
用户："贵州茅台北向资金持仓情况怎么样？"
→ westock fund north-holding sh600519
→ 解析最新季 + 次新季：HoldingCap/HoldingRatio/HoldingShares/CapChgQ/CapChgY
→ 输出季度对比表（持股市值、持股比例、季年变动）

用户："电子行业北向资金持仓分布如何？"
→ 若用户未给代码：westock search 电子 --type sector → 取板块代码
→ westock fund north-holding pt01801080
→ 解析 HoldingCap/CapChgQ/CapChgY
→ 注意：仅支持申万行业，概念/地域板块不支持

用户："今天北向成交最活跃的股票有哪些？"
→ 技能内路由：westock screen ranking --type north_active_d（固定 Top20 日榜）
```

---

## 十、简况（公司基本信息/股东/分红/回购）

> 命令：`westock profile` `westock shareholder` `westock dividend/calendar` `westock buyback`

### 8.1 分红数据查询

```
用户："贵州茅台的分红情况如何？"
→ westock search 贵州茅台 → 获取 sh600519
→ westock dividend sh600519 → 解析分红明细（reportEndDate, dividendPlan, cashDiviRMB 等）
→ 输出分红情况分析
```

### 8.2 跨市场分红历史对比

```
用户："对比腾讯和苹果近3年的分红记录"
→ westock dividend hk00700,usAAPL --years 3
→ 解析批量查询结果 中各股票的 plans[]
→ 注意货币差异：港股 cashDivPerShare（港元）、美股 dividend（美元）
→ 输出跨市场分红对比分析
```

### 8.3 A股分红历史查询

```
用户："查看贵州茅台近5年的分红记录"

AI 步骤：
1. 搜索股票：westock search 贵州茅台 → sh600519
2. 查询分红历史：westock dividend sh600519 --years 5
3. 解析 plans[] 中的分红方案（reportEndDate, cashDiviRMB, dividendPlan）
4. 注意：A股分红数据为"每10股派息"（cashDiviRMB）
5. 分析每年分红趋势（分红金额、分红频次、股利支付率变化）
6. 输出分红历史趋势分析
```

### 8.4 港股分红历史查询

```
用户："查看腾讯近几年的分红记录"

AI 步骤：
1. 查询分红历史：westock dividend hk00700 --years 5
2. 解析 plans[] 中的分红方案
3. 分析每年分红趋势（每股派息、合计派现、分红频次）
4. 输出分红历史趋势分析
```

### 8.5 分红历史自定义年数

```
用户："查看苹果近10年的分红记录"

AI 步骤：
1. 查询分红历史：westock dividend usAAPL --years 10
2. 解析 plans[] 中的分红方案
3. 分析美股季度分红特征（每季度分红金额、年度累计）
4. 注意：美股可能包含 splitInfo（拆合股信息）
5. 输出长期分红趋势分析
```

### 8.6 跨市场分红历史对比

```
用户："对比贵州茅台、腾讯和苹果近3年的分红情况"

AI 步骤：
1. 批量查询分红历史：westock dividend sh600519,hk00700,usAAPL --years 3
2. 解析批量查询结果 中各股票的 plans[]
3. 注意各市场数据格式差异：
   - A股：cashDiviRMB（每10股派息，元）
   - 港股：cashDivPerShare（每股派息，港元）
   - 美股：dividend（每股分红，美元）
4. 统一换算为每股派息金额进行对比
5. 输出跨市场分红对比分析
```

### 8.7 分红除权日查询

```
用户："苹果什么时候除权派息？"

AI 步骤：
1. 搜索股票：westock search 苹果 → usAAPL
2. 查询分红历史：westock dividend usAAPL --years 5
3. 解析 plans[] 中的除权日列表
4. 展示每次的除权日、支付日、每股分红
5. 输出分红除权日历
```

### 8.8 股东研究分析

```
用户："查一下茅台的十大股东"

AI 步骤：
1. 搜索股票：westock search 贵州茅台 → sh600519
2. 查询股东数据：westock shareholder sh600519
3. 解析 top10Shareholders（十大股东）和 top10FloatShareholders（十大流通股东）
4. 解析 shareholderNum（股东户数）→ 总户数/A股户数/环比变动/户均持股
5. 分析持股集中度、机构/个人占比、持股变动趋势
6. 输出股东结构分析报告
```

### 8.9 港股股东与机构持仓分析

```
用户："腾讯的机构持仓情况怎么样？"

AI 步骤：
1. 查询股东数据：westock shareholder hk00700
2. 解析 shareholderInfo（持股股东）→ 主要股东持股比例
3. 解析 shareholderDist（股东分布）→ 各类机构持股情况
4. 解析 instHoldingStats（机构持仓统计）→ 机构数量变化、增减持趋势
5. 输出机构持仓分析
```

### 8.10 公司回购查询

```
用户："查看小米最近的回购情况"

AI 步骤：
1. 搜索股票：westock search 小米集团 → hk01810
2. 查询回购数据：westock buyback hk01810
3. 解析回购明细：日期、回购股份、回购金额、回购均价
4. 计算累计回购金额、平均回购价格
5. 输出回购分析
```

---

## 十一、财务（三大报表/财报披露日历）

> 命令：`westock finance` `westock disclosure`

### 9.1 财务分析

```
用户："分析贵州茅台的盈利能力"
→ westock finance sh600519 → 提取关键指标 → 计算同比/环比 → 输出分析结论
```

### 9.2 财报多期对比分析

```
用户："看看浦发银行和招商银行最近4期的利润表"
→ westock finance sh600000,sh600036 --type income --limit 4
→ 解析批量查询结果 → 提取各期营收、净利润、毛利率
→ 计算同比/环比增长率 → 输出两家银行盈利能力对比

用户："查看腾讯最近4期的综合损益表"
→ westock finance hk00700 --type income
```

### 9.3 财报披露日查询

```
用户："茅台什么时候发财报？"

AI 步骤：
1. 搜索股票：westock search 贵州茅台 → sh600519
2. 查询财报披露日历：westock disclosure sh600519
3. 解析 items[] 中的披露日列表
4. 区分已披露和预约披露日期
5. 输出最近的财报披露日历
```

---

## 十二、ETF（ETF 全维度）

> 命令：`westock etf profile` / `overview` / `holdings` / `nav`

### 10.1 ETF 全景分析

```
用户："分析一下沪深300ETF的基本情况"

AI 步骤：
1. 搜索 ETF：westock search 沪深300ETF --type etf → sh510300
2. 查询基金档案：westock etf profile sh510300
3. 查询运作概览：westock etf overview sh510300
4. 解析基本信息：类别、成立日期、管理人、托管人、跟踪指数
5. 解析 classification（4 级详细分类）：资产类别 / 投资风格 / 细分领域 / 具体方向 / 跟踪标的
6. 解析 managerHistory（基金经理历史）：当前在任 / 首任 / 任职最长 / 全部历任
7. 解析费用：认购费率、管理费率、托管费率、销售服务费
8. 解析净值/规模：单位净值、溢折率、规模、份额、净申购
9. 解析收益：今年以来、近1月/3月/6月/1年/3年收益率
10. 解析回撤：最大回撤指标
11. 输出 ETF 全景分析报告
```

### 10.2 ETF 持仓分析

```
用户："沪深300ETF的重仓股有哪些？"

AI 步骤：
1. 搜索 ETF：westock search 沪深300ETF --type etf → sh510300（确认 etfDetail=支持）
2. 查询成分股：westock etf holdings sh510300
3. 解析 topStockChanges 与 holdings（申赎清单全量成分）
4. 输出 ETF 持仓分析
```

### 10.3 ETF 净值趋势分析

```
用户："沪深300ETF近一个月净值走势如何？"

AI 步骤：
1. 搜索 ETF：westock search 沪深300ETF --type etf → sh510300
2. 查询净值历史：westock etf nav sh510300 --start 2026-02-10 --end 2026-03-10
3. 解析每日净值、净值涨跌（`navChange`/`navChangePct` 由相邻日 `EtfNav` 差分；区间内首日无前值）
4. 计算区间收益率、最大回撤
5. 输出净值趋势分析
```

### 10.4 ETF 费用对比

```
用户："对比沪深300ETF和创业板ETF的费用"

AI 步骤：
1. 搜索 ETF：westock search 沪深300ETF --type etf → sh510300
2. 搜索 ETF：westock search 创业板ETF --type etf → sz159915
3. 批量查询档案：westock etf profile sh510300,sz159915
4. 对比费用：认购费率、管理费率、托管费率、销售服务费
5. 对比规模、份额、流动性（etf overview）
6. 输出 ETF 费用对比分析
```

### 10.5 ETF 溢折率分析

```
用户："分析一下沪深300ETF的溢折率情况"

AI 步骤：
1. 查询运作概览：westock etf overview sh510300
2. 解析 etfDisc（溢折率）、etfDiscAvg*（同指数平均溢折率）
3. 判断溢价/折价程度及与同类 ETF 的对比
4. 输出溢折率分析
```

### 10.6 ETF 基金经理稳定性分析

```
用户："沪深300ETF的基金经理稳定吗？历任都有谁？"

AI 步骤：
1. 查询基金档案：westock etf profile sh510300
2. 解析 managerHistory：
   - current（当前在任）：与 first（首任）一致 → 经理"超长稳定"
   - longest（任职最长）数组里的人是否仍在 current 内 → 老将仍在岗
   - history（全部历任）数量 → 历任更换次数（少 = 稳定，多 = 频繁更换）
3. 结合 managers 数组（含 intro / experienceYears / returnDuringTenure）补充任职履历和任内回报
4. 输出经理稳定性结论（如"自成立以来仅 1 任经理，柳军任职超 12 年"）
```

---

## 十三、发现（搜索/热搜）

> 命令入口：`westock search`、`westock hot stock`、`westock hot sector`、`westock hot etf`。新闻相关搜索直接使用 `web_search`。

### 11.1 查看市场热搜

```
用户："今天市场有哪些热门股票？"

AI 步骤：
1. 查询热搜股票：westock hot stock
   → 格式化输出排名、名称、代码、最新价、涨跌幅
2. 可选：查询热门板块：westock hot sector
3. 可选：查询热搜ETF：westock hot etf
4. 基于榜单描述股票、板块和 ETF 热度，不仅凭新闻标题解释上涨原因
```

若需要新闻背景或财经热点，直接使用 `web_search` 并阅读关键报道原文，注明来源与实际日期；搜索结果排序不是平台热文榜，不虚构新闻热度排名。未能核验的内容只能作为线索列出，不能补写事实。

### 11.2 行业板块分析

```
用户："今天哪些行业板块涨得好？资金在流向哪里？"

AI 步骤：
1. 查询板块行情榜：westock sector ranking
   → 格式化输出行业/概念/地域板块资金流向（净流入TOP和净流出TOP）、北向资金热门板块（当日/近5日/近20日）
2. 直接基于格式化输出，输出行业板块资金面和涨幅分析
```

---

## 十四、宏观（宏观指标）

> 命令：`westock macro list/indicator`

### 12.1 查看最新核心宏观指标

```
用户："当前宏观经济面怎么样？"

AI 步骤：
1. 查询最新核心宏观指标：westock macro indicator cn_core
2. 解析返回的各项核心指标数据（会自动返回 p1 和 p2 两个数据集）
3. 从 GDP 增速、CPI/PPI、PMI、社融、M2 等维度综合分析
4. 输出宏观经济面全景概览
```

### 12.2 PMI 趋势分析

```
用户："看看最近半年PMI走势"

AI 步骤：
1. 查询 PMI 区间数据：westock macro indicator cn_pmi --start 2024 --end 2025
2. 提取每月 PMI 数值（制造业/非制造业/综合）
3. 分析 PMI 是否连续处于荣枯线（50）以上
4. 结合子项（新订单、生产、就业等）分析经济景气度变化
5. 输出 PMI 趋势分析报告
```

### 12.3 GDP 全景分析

```
用户："分析一下最新的GDP数据"

AI 步骤：
1. 查询全部 GDP 相关指标：westock macro indicator cn_gdp cn_cpi_ppi cn_consumption cn_investment --year 2025
2. 解析 GDP 增速（实际 vs 名义）
3. 分析 CPI/PPI 价格走势（通胀/通缩信号）
4. 分析消费和投资数据（内需强弱）
5. 输出 GDP 多维度分析报告
```

### 12.4 货币政策环境判断

```
用户："当前货币政策环境如何？"

AI 步骤：
1. 查询货币指标：westock macro indicator cn_financing cn_fundquantity cn_fundcost --year 2025
2. 分析社融规模（financing）→ 实体经济融资需求
3. 分析 M1/M2 增速（fundquantity）→ 货币供应宽松度
4. 分析利率水平（fundcost）→ 资金成本变化
5. 综合判断货币政策取向（宽松/中性/偏紧）
6. 输出货币政策环境分析
```

### 12.5 宏观数据 + 市场联动分析

```
用户："PMI下滑对A股有什么影响？"

AI 步骤：
1. 查询 PMI 趋势：westock macro indicator cn_pmi --start 2024 --end 2025
2. 查询同期上证指数走势：westock quote sh000001
3. 对比 PMI 走势与指数走势的相关性
4. 分析 PMI 下行期间哪些板块受影响更大
5. 输出宏观-市场联动分析
```

### 12.6 通胀全景 + CPI/PPI 剪刀差

```
用户："最近通胀压力怎么样？"/"CPI和PPI差距说明什么？"

AI 步骤：
1. 查询价格指标：westock macro indicator cn_cpi_ppi --start 2024 --end 2025
2. 关注核心指标：
   - CPI_YOY（CPI 同比）vs CPI_YOY_CORE（核心 CPI，剔除食品和能源）
   - PPI_YOY（PPI 同比）、PPIRM_YOY（购进价格）
   - PRICE_SCISSORS_CPI_PPI（CPI-PPI 剪刀差）、PRICE_SCISSORS_PPI_PPIRM（PPI-PPIRM 剪刀差）
3. 专业研判：
   - CPI 上升 + 核心 CPI 平稳 → 食品/能源驱动型通胀（暂时性）
   - CPI > PPI（剪刀差为正）→ 下游议价能力强，消费类利润扩张
   - CPI < PPI（剪刀差为负）→ 上游成本压力，下游利润受挤压
   - PPI > PPIRM → 制造业利润率改善
4. 拆分分项：CPI_YOY_FOOD（食品）/ CPI_YOY_NON_FOOD（非食品）/ PPI_YOY_PRODUCE（生产资料）/ PPI_YOY_LIVE（生活资料）
5. 输出通胀压力评估 + 板块影响（消费/上游资源/中游制造）
```

### 12.7 国债收益率曲线与期限结构分析

```
用户："看看国债收益率曲线"/"长短端利差怎么样？"/"是牛陡还是熊平？"

AI 步骤：
1. 查询收益率曲线：westock macro indicator cn_yield_curve --year 2025
2. 查询期限利差与曲线形态：westock macro indicator cn_term_spread --date <最新>
3. 关注核心字段：
   - YTM_YIELD_2Y / 5Y / 10Y / 30Y（关键期限点位）
   - Yield10Y / Yield2Y、TermSpread（10Y-2Y 期限利差，bps）
   - CurveFormD/W/M/Q/Y（日/周/月/季/年形态：牛陡/牛平/熊陡/熊平）
   - LongDifD/W/M/Q/Y、ShortDifD/W/M/Q/Y（长短端多周期变动）
4. 形态语义：
   - **牛陡**（短端下行更快）→ 货币宽松预期、降息周期初期
   - **牛平**（长端下行更快）→ 经济衰退预期、避险买长债
   - **熊陡**（长端上行更快）→ 经济复苏 / 通胀预期上升
   - **熊平**（短端上行更快）→ 流动性收紧、加息周期
5. 期限利差判断：
   - 利差扩大（陡峭化）→ 经济预期改善
   - 利差收窄甚至倒挂 → 衰退信号（参考美债经验）
6. 输出曲线形态判断 + 货币政策含义 + 大类资产建议
```

### 12.8 股债性价比（风险溢价）与大类资产配置

```
用户："现在股票贵不贵？"/"股债怎么选？"/"红利股有性价比吗？"

AI 步骤：
1. 查询溢价率最新水平：westock macro indicator cn_premium_value --date <最新>
2. 查询溢价率历史曲线（约 2400 条日频）：westock macro indicator cn_premium_curve --date <最新>
3. 关注核心字段：
   - DividendPremium（红利溢价率：股息率 - 10Y 国债收益率）
   - EquityPremium（股债溢价率：1/PE - 10Y 国债收益率）
   - DprPct10Y / EprPct10Y（过去 10 年历史百分位）
4. 专业研判：
   - 股债溢价率 10Y 分位 > 80% → 股票相对债券极具吸引力（市场底部信号）
   - 股债溢价率 10Y 分位 < 20% → 股票相对债券偏贵（市场高估区）
   - 红利溢价率 10Y 分位 > 80% → 红利策略性价比高，适合配置高股息蓝筹
   - 红利溢价率持续走高 → 资金"避险"特征，关注银行/煤炭/电力/运营商
5. 历史曲线趋势：
   - 拐点识别：从历史高位回落 → 风险资产开始反攻
   - 持续走低 → 警惕股票泡沫，债券吸引力上升
6. 输出大类资产配置建议（股 vs 债 vs 红利）
```

### 12.9 流动性投放与货币市场利率

```
用户："央行最近在投放还是回笼？"/"MLF 利率怎么走？"

AI 步骤：
1. 查询公开市场操作 MLF：westock macro indicator cn_mlf --year 2025
2. 查询货币市场利率：westock macro indicator cn_fundcost --year 2025
3. 关注核心字段：
   - MLF_OPERATION_3M / 6M / 1Y（不同期限操作金额）
   - MLF_BALANCE_MONTH（月末余额）、MLF_DUE（到期量）、MLF_NET_INJECTION（净投放）
   - SHIBOR_OVERNIGHT / 1W / 1M / 3M / 1Y（同业拆借利率）
   - FDR007 / FR007（银行间回购定盘利率）
4. 专业研判：
   - MLF 净投放为正 + 短端利率下行 → 流动性宽松
   - MLF 净回笼 + SHIBOR 上行 → 流动性边际收紧
   - MLF 操作以 1Y 为主 → 央行引导中长期利率下行
   - SHIBOR 1Y 与 MLF 利差走扩 → 银行负债成本压力
5. 政策信号：
   - MLF 续作量 > 到期量 → 呵护流动性
   - 1Y MLF 利率下调 → 引导 LPR 下调，传导至实体融资成本
6. 输出货币政策操作意图 + 流动性松紧度评估
```

### 12.10 工业景气全景（5 维交叉验证）

```
用户："工业经济好不好？"/"看看制造业景气度"

AI 步骤：
1. 并行查询 5 个工业相关指标：
   - westock macro indicator cn_profit cn_valueadded cn_prosperity cn_capacity_utilization cn_power_consumption --year 2025
2. 关键字段交叉验证：
   - **量**：IAV_CUM_YOY（工业增加值累计同比）+ POWERUSE_ELEC_YTD_YOY（用电量累计同比）
   - **效**：ENTERPRISE_PROFIT_CUM_YOY（工业企业利润累计同比）
   - **能**：CAPU_CAPU（产能利用率）+ CAPU_CAPU_MFG（制造业产能利用率）
   - **景气**：ENT_BOOM_IDX_Q（企业景气指数）+ ENT_EXP_BOOM_IDX_Q（预期景气指数）
3. 行业分项对比：
   - 高景气：观察 IAV_CUM_YOY_HIGH_TEC（高技术）、IAV_CUM_YOY_TMT（电子）
   - 周期回暖：黑色金属（FERR）、有色金属（NFERR）、化工（CHEM）的产能利用率与利润同步走高
   - 需求验证：相关产品产量（如 PROD_OUT_STEEL_YOY 钢材产量、PROD_OUT_AUTO_YOY 汽车）
4. 专业研判：
   - 工业增加值 ↑ + 用电量 ↑ + 产能利用率 ↑ → 真实复苏（量价齐升）
   - 利润 ↑ 但产能利用率 ↓ → 价格驱动型（警惕涨价不可持续）
   - 当期景气 vs 预期景气背离 → 拐点信号
5. 输出工业景气评分 + 高景气子行业清单
```

### 12.11 财政发力强度评估

```
用户："今年财政力度怎么样？"/"专项债发了多少？"

AI 步骤：
1. 查询财政指标：westock macro indicator cn_fiscal --year 2025
2. 关注三大维度：
   - **收入端**：FISCAL_PUB_REV_YTD_YOY（公共预算收入累计同比）+ 税种结构
     - FISCAL_REV_TAX_VAT_YTD_YOY（增值税）→ 经济活跃度
     - FISCAL_REV_TAX_CIT_YTD_YOY（企业所得税）→ 企业盈利
     - FISCAL_REV_TAX_PIT_YTD_YOY（个人所得税）→ 居民收入
     - FISCAL_REV_TAX_SEC_YTD_YOY（证券交易印花税）→ 资本市场活跃度
   - **支出端**：FISCAL_PUB_EXP_YTD_YOY（公共预算支出累计同比）+ 重点领域
     - 民生：教育/医疗/社保（FISCAL_EXP_EDU/MED/SS_YTD_YOY）
     - 基建：交通/城乡（FISCAL_EXP_TRANS/URB_YTD_YOY）
     - 科创：科技（FISCAL_EXP_TECH_YTD_YOY）
   - **债务端**：FISCAL_LGB_ISS_YTD（地方债发行累计）+ FISCAL_LGB_SPC_ISS_YTD（专项债累计）
3. 政策研判：
   - 支出增速 > 收入增速 → 财政积极
   - 专项债前置发行（上半年发行进度高）→ 稳增长意图明确
   - FISCAL_DEFICIT_PRG_YTD（赤字进度）> 历年同期 → 财政力度加码
4. 板块联动：
   - 专项债加速 → 基建（建材/建筑）
   - 教育/医疗支出加速 → 教育/医药板块
   - 科技支出加速 → TMT/高端制造
5. 输出财政政策力度评估 + 受益板块
```

### 12.12 进出口数据深度解读

```
用户："出口怎么样？"/"贸易顺差是多少？"

AI 步骤：
1. 查询进出口指标：westock macro indicator cn_export --year 2025
2. 查询出口交货值（行业分项）：westock macro indicator cn_export_value --year 2025
3. 关注核心字段：
   - EXP_BALANCE_GOODS_SUM_CUM（货物贸易差额累计）
   - EXP_BAL_GOODS_SVC_SUM_CUM（货物+服务贸易差额）
   - EXP_EX_RESERVES_MONTHLY（外汇储备）/ EXP_GOLD_RESERVES_MONTHLY（黄金储备）
   - EDV_EDV_*_YTD_YOY（各行业出口交货值累计同比）
4. 行业出口结构：
   - 传统：纺织（TEXTL）/ 服装（APRL）/ 家具（FURN）
   - 中端制造：通用设备（GNEQ）/ 专用设备（SPEQ）/ 汽车（AUTO）
   - 高端：电气机械（ELEC）/ 电子信息（ICT）/ 仪器仪表（INSTR）
5. 专业研判：
   - 贸易顺差扩大 + 外汇储备稳定 → 国际收支健康
   - 高技术出口（ICT/ELEC）增速 > 传统（TEXTL）→ 出口结构升级
   - 服务贸易逆差收窄（旅行/运输）→ 内需复苏不及预期
   - 黄金储备增加 → 外汇储备多元化（去美元化趋势）
6. 输出出口景气度 + 受益出口链板块（机械/汽车/电子）
```

