# WeStock Data - 常见分析场景详解

> **定位**：本文档是 SKILL.md 的 **L3 层补充材料**，提供完整的分析场景示例和详细操作步骤。
>
> **使用方式**：AI 在遇到不确定的分析场景时按需加载本文档。命令列表和基本用法请参见
> [SKILL.md](../SKILL.md)。
>
> **场景总数**：共 64 个场景，按 15 个功能分组组织。

---

## 一、行情（价格序列/技术指标/筹码）

> 命令：`quote` `minute` `kline` `technical` `chip`

### 场景 1：分析成交量趋势

```
用户："分析牧原股份近20天的成交量"
→ westock-data search 牧原股份 → westock-data kline sz002714 --period day --limit 20 → 从表格中提取volume → 计算统计指标 → 输出分析报告
```

### 场景 2：多股对比（使用批量查询）

```
用户："对比腾讯和阿里巴巴的市值"
→ westock-data quote hk00700,usBABA → 一次查询两只股票 → 解析批量查询结果 → 提取市值 → 输出对比
```

### 场景 3：指数/板块K线分析

```
用户："上证指数近一个月的走势"
→ westock-data kline sh000001 --period day --limit 30 → 解析K线数据 → 计算区间涨跌幅 → 输出趋势分析

用户："半导体板块近一周的K线走势"
→ westock-data sector search 半导体 → 获取板块代码（如 pt01801081）
→ westock-data kline pt01801081 --period day --limit 5 → 解析K线 → 输出走势
```

### 场景 4：指数/板块分时走势

```
用户："大盘今天的分时走势怎么样"
→ westock-data minute sh000001 → 解析分时数据 → 输出走势分析

用户："半导体板块今天的盘中走势"
→ westock-data sector search 半导体 → 获取板块代码（如 pt01801081）
→ westock-data minute pt01801081 → 解析分时 → 输出走势
```

### 场景 5：筹码成本分析

```
用户："分析一下茅台的筹码分布情况"

AI 步骤：
1. 搜索股票：westock-data search 贵州茅台 → sh600519
2. 查询筹码数据：westock-data chip sh600519
3. 解析筹码盈利率（chipProfitRate）→ 判断获利盘/套牢盘比例
4. 对比收盘价与平均成本（chipAvgCost）→ 判断当前价位相对筹码成本的位置
5. 分析集中度（chipConcentration90/70）→ 集中度越低，筹码越集中
6. 输出筹码分析结论
```

### 场景 6：筹码趋势分析

```
用户："看看招商银行近一个月的筹码变化趋势"

AI 步骤：
1. 搜索股票：westock-data search 招商银行 → sh600036
2. 查询历史筹码：westock-data chip sh600036 --start 2026-02-10 --end 2026-03-10
3. 解析 items[] 中每日的筹码数据
4. 分析趋势：
   - 盈利率趋势（上升 = 获利盘增加）
   - 平均成本趋势（上升 = 筹码成本抬升，主力可能在建仓）
   - 集中度趋势（下降 = 筹码趋于集中，可能有主力控盘）
5. 输出筹码变化趋势分析
```

---

## 二、市场（全市场截面/总览/指数/互联互通/新股）

> 命令：`lhb` `index` `market-overview` `connect` `ipo`

### 场景 7：查询股票基本信息

```
用户："查询腾讯控股的股价"
→ westock-data search 腾讯控股 → 获取 hk00700 → westock-data quote hk00700 → 展示价格和涨跌幅
```

### 场景 8：指数行情查询

```
用户："查一下今天大盘的涨跌情况"
→ westock-data search 上证指数 → 获取 sh000001 → westock-data quote sh000001 → 展示涨跌幅和成交额
```

### 场景 9：多指数对比

```
用户："对比沪深两市今天的表现"
→ westock-data quote sh000001,sz399001 → 解析批量查询结果 → 对比涨跌幅 → 输出分析
```

### 场景 10：跨市场指数对比

```
用户："对比恒生指数和纳斯达克今天的表现"

AI 步骤：
1. 批量查询行情：westock-data quote hkHSI,us.IXIC
2. 分别解析各指数的行情数据
3. 对比涨跌幅
4. 输出跨市场指数对比分析
```

### 场景 11：新股申购分析

```
用户："最近有什么新股可以申购？"

AI 步骤：
1. 查询沪深新股：westock-data ipo --market hs
   → 格式化输出按状态分类（即将发行/今日可申购/即将上市/中签号公布/已上市），含发行价、市盈率、申购代码、上市日、可比公司、风险提示等
2. 可选：查询港股新股：westock-data ipo --market hk
   → 格式化输出按申购日/上市日分类，含入场费、认购倍数、募集金额等
3. 可选：查询美股新股：westock-data ipo --market us
   → 格式化输出按状态分组（注册中/已定价/已提交等），含行业、发行价、价格区间、承销商等
4. 直接基于格式化输出，输出新股申购机会分析
```

### 场景 12：今日市场点评（market-overview summary）

```
用户："今天 A 股市场怎么样？"

AI 步骤：
1. 一键拉取大盘画像：westock-data market-overview （默认 type=summary）
2. 解析 14 维度得分（估值/情绪/技术/趋势/风格轮动 等）+ 状态文案
3. 综合给出今日市场点评，标注偏强/偏弱维度
4. 如需补充，叠加 --type updown（涨跌停/红绿盘）/ --type margin（两融）/ --type valuation（中证全指 PE 百分位）
```

### 场景 13：沪深港通成份股查询（connect）

```
用户："沪股通有哪些标的"

AI 步骤：
1. 拉沪股通成份股：westock-data connect --exchange sh
2. 分页拉全量：westock-data connect --exchange sh --limit 100 --offset 0
3. 拉深股通：westock-data connect --exchange sz
4. 输出标的池（注意：connect 是"标的池"列表，不是资金流量；查北向资金流量请用 fund flow sh600000）
```

> ⚠️ **职责边界**：`connect` = 沪深港通**标的池**（标的列表）；`fund` = 资金流量（金额数据）；二者不要混用。

### 场景 14：查询指数成份股

```
用户："沪深300有哪些成份股？"

AI 步骤：
1. 查询沪深300成份股：westock-data index constituent sh000300
2. 解析返回的成份股列表
3. 输出成份股列表
4. 可按行业分布统计
```

---

## 三、板块（板块清单/成份股/信息/行情榜）

> 命令：`sector list/search/constituent/info/ranking`

### 场景 15：板块行情分析

```
用户："半导体板块今天的涨跌情况"
→ westock-data sector search 半导体 → 获取板块代码（如 pt01801081） → westock-data quote pt01801081 → 展示涨跌幅和成交额
```

### 场景 16：查询概念股列表（⚠️ 常见易错场景）

```
用户："华为概念有哪些股票？"
用户："AI概念股有哪些？"
用户："新能源汽车概念股"

⚠️ 错误做法：用 search 搜板块（search 不支持板块搜索）或用外部搜索工具
✅ 正确做法：用 sector search 两步查询

AI 步骤：
1. 搜索概念板块代码：westock-data sector search 华为
   → 返回匹配的板块列表（如 style_pt01801517 华为概念）
2. 用板块代码查成份股：westock-data sector constituent style_pt01801517
   → 返回华为概念的全部成份股列表
3. 输出概念股列表（代码、名称）
4. 可选：批量查询行情 westock-data quote <代码列表> → 补充行情数据
```

> **关键区分**：
> - `sector search 华为` → 拿到板块代码后，用 `quote`/`kline`/`minute` 查板块行情
> - `sector search 华为` → 再用 `sector constituent <代码>` 查成份股

### 场景 17：查询行业成份股

```
用户："电子行业有哪些成份股？"

AI 步骤：
1. 查询申万一级电子行业成份股：westock-data sector constituent pt01801080
2. 解析返回的成份股列表
3. 输出成份股列表（代码、名称）
4. 可补充成份股数量统计
```

### 场景 18：板块成份 + 行情联动分析

```
用户："帮我看看半导体板块的成份股，并查看涨幅前5的行情"

AI 步骤：
1. 查询申万二级半导体成份股：westock-data sector constituent pt01801081
2. 取返回的成份股代码列表
3. 批量查询行情：westock-data quote <前N只代码逗号分隔>
4. 按涨跌幅排序取前5
5. 输出板块成份 + 涨幅排行分析
```

### 场景 19：板块成份股查询

```
用户："半导体板块有哪些成份股"

AI 步骤：
1. 搜索板块代码 → pt01801081
2. 拉取成份股：westock-data sector constituent pt01801081
3. 输出成份股清单（含代码/名称/涨跌/成交额等）
```

> ⚠️ 易混淆：用户问"板块成份股"用 `sector <代码>`（不带 fields）；问"板块怎么样/相关基金/热点"用 `sector <代码> --fields ...`。

---

## 四、研究（评分/评级/预期/研报/脱水研报）

> 命令：`score` `rating` `consensus` `report` `dehydrated`

### 场景 20：机构评级与一致预期分析

```
用户："看看茅台的机构评级和一致预期"

AI 步骤：
1. 搜索股票：westock-data search 贵州茅台 → sh600519
2. 查询评级数据：westock-data rating sh600519
   → 解析机构评级分布（买入/增持/中性/减持/卖出）
3. 查询一致预期：westock-data consensus sh600519
   → 解析 EPS/净利润/营收的一致预期值和增长率
4. 查询评分：westock-data score sh600519
   → 解析综合评分、细分维度评分
5. 输出机构研究综合报告
```

### 场景 21：研报查询与脱水研报

```
用户："看看最近有哪些关于茅台的研报"

AI 步骤：
1. 搜索股票：westock-data search 贵州茅台 → sh600519
2. 查询研报列表：westock-data report sh600519 --limit 10
   → 解析研报标题、机构、分析师、评级、发布时间
3. 可选：查询脱水研报：westock-data dehydrated --limit 20
   → 解析核心观点、投资建议、目标价
4. 输出研报摘要和核心观点
```

---

## 五、事件（事件标签/风险事件/投资日历/停复牌）

> 命令：`events list/tags` `risk` `calendar` `suspension`

### 场景 22：投资日历查询

```
用户："本周有哪些重要的财经事件？"

AI 步骤：
1. 查询有事件的日期：westock-data calendar
   → 格式化输出月历视图，★ 标记有事件的日期
2. 从月历中筛选本周日期
3. 逐日查询事件详情：westock-data calendar 2026-03-10 --limit 30
   → 格式化输出事件列表（按重要性排序），含星级、时间、国家、内容、前值/预测/实际值
4. 可按地区筛选：westock-data calendar 2026-03-10 --limit 30 --market hs
5. 可按指标筛选：westock-data calendar 2026-03-10 --limit 30 --market hs --indicator 1
6. 直接基于格式化输出，输出本周财经事件日历
```

### 场景 23：个股事件总览（events tags）

```
用户："最近茅台有什么大事"

AI 步骤：
1. 拉事件标签：westock-data events tags sh600519
2. 解析返回的事件 ID 列表（如 7=分红实施 / 23=董监高变动 / 12=限售解禁 等）
3. 按事件分类分组展示（董监高/分红/财报/指数变动/限售解禁等 9 大类）
4. 如需深挖某类，再用 risk 钻取（如 --types pledge 看质押细节）
```

### 场景 24：事件 → 风险细查链路（events + risk）

```
用户："看看 sh600519 有没有质押风险"

AI 步骤：
1. 先看事件全貌：westock-data events tags sh600519
2. 若含质押/解禁标签，用 risk 钻取明细：
   westock-data risk sh600519 --types pledge,unlock
3. 解析质押率（已修复 100 倍单位错误）/ 解禁规模 / 解禁日期
4. 输出风险细节
```

### 场景 25：高管变动 / 增减持 / 评级变动监控（risk 新类型）

```
用户："最近哪些高管在减持茅台"

AI 步骤：
1. 拉取高管增减持明细：westock-data risk sh600519 --types executivetransfer
   （别名 executive 也可：--types executive）
2. 解析每条增减持记录：高管姓名、变动数量、变动方向、变动后持股
3. 输出增减持汇总
```

```
其他新增 risk 类型：
- westock-data risk <code> --types leaderchange     # 高管变动（任免）
- westock-data risk <code> --types bondrating       # 评级信息（如 AAA/AA+）
```

---

## 六、资讯（新闻、公告、原文）

> 命令：`news article/market/detail` `notice list/detail`

### 场景 26：公告全文查询

```
用户："查看贵州茅台最近的财务公告内容"

AI 步骤：
1. 搜索股票：westock-data search 贵州茅台 → sh600519
2. 查询公告列表：westock-data notice list sh600519 --type 1
3. 从列表中获取公告ID（如 nos1224809143）
4. 查询公告内容：westock-data notice detail nos1224809143
   → 格式化输出标题、发布时间、关联股票、相关链接（PDF/原文/翻译），A股/北交所直接展示正文内容，港股/美股展示PDF下载链接
5. 直接基于格式化输出，输出公告内容摘要
```

### 场景 27：新闻与资讯查询

```
用户："看看最近有哪些关于茅台的新闻"

AI 步骤：
1. 搜索股票：westock-data search 贵州茅台 → sh600519
2. 查询新闻列表：westock-data news article sh600519 --limit 20
   → 解析新闻标题、来源、发布时间、摘要
3. 可选：查询市场新闻：westock-data news market --limit 20
   → 解析市场要闻、政策动向
4. 可选：查询新闻详情：westock-data news detail <newsId>
5. 输出新闻摘要和关键信息
```

---

## 七、资金（二级市场资金）

> 命令：`fund flow` `fund short/margin/block`

### 场景 28：批量资金流向分析

```
用户："对比腾讯和美团的资金流向"
→ westock-data fund flow hk00700,hk03690 --date 2026-03-10 → 一次查询两只 → 解析批量查询结果 → 对比资金面
```

### 场景 29：A股资金流向分析

```
用户："分析中芯国际的资金面"
→ westock-data fund flow sh688981 → 解析 MainNetFlow/JumboNetFlow → 输出资金面判断
```

### 场景 30：港股资金与卖空分析

```
用户："腾讯控股的资金流向情况"
→ westock-data fund flow hk00700 → 解析 TotalNetFlow/MainNetFlow/RetailNetFlow → 输出资金分析

用户："腾讯控股的卖空情况如何"
→ westock-data fund short hk00700 → 解析 ShortShares/ShortAmount/ShortRatio → 卖空比率>15%需关注
```

### 场景 31：美股卖空数据分析

```
用户："苹果公司的卖空情况"
→ westock-data fund short usAAPL → 解析 ShortRatio/ShortShares/ShortRecoverDays → ShortRatio>10%或ShortRecoverDays>5天需关注
```

---

## 八、简况（公司基本信息/股东/分红/回购）

> 命令：`profile` `shareholder` `dividend list/calendar` `buyback`

### 场景 32：分红数据查询

```
用户："贵州茅台的分红情况如何？"
→ westock-data search 贵州茅台 → 获取 sh600519
→ westock-data dividend list sh600519 → 解析分红明细（reportEndDate, dividendPlan, cashDiviRMB 等）
→ 输出分红情况分析
```

### 场景 33：跨市场分红历史对比

```
用户："对比腾讯和苹果近3年的分红记录"
→ westock-data dividend list hk00700,usAAPL --years 3
→ 解析批量查询结果 中各股票的 plans[]
→ 注意货币差异：港股 cashDivPerShare（港元）、美股 dividend（美元）
→ 输出跨市场分红对比分析
```

### 场景 34：A股分红历史查询

```
用户："查看贵州茅台近5年的分红记录"

AI 步骤：
1. 搜索股票：westock-data search 贵州茅台 → sh600519
2. 查询分红历史：westock-data dividend list sh600519 --years 5
3. 解析 plans[] 中的分红方案（reportEndDate, cashDiviRMB, dividendPlan）
4. 注意：A股分红数据为"每10股派息"（cashDiviRMB）
5. 分析每年分红趋势（分红金额、分红频次、股利支付率变化）
6. 输出分红历史趋势分析
```

### 场景 35：港股分红历史查询

```
用户："查看腾讯近几年的分红记录"

AI 步骤：
1. 查询分红历史：westock-data dividend list hk00700 --years 5
2. 解析 plans[] 中的分红方案
3. 分析每年分红趋势（每股派息、合计派现、分红频次）
4. 输出分红历史趋势分析
```

### 场景 36：分红历史自定义年数

```
用户："查看苹果近10年的分红记录"

AI 步骤：
1. 查询分红历史：westock-data dividend list usAAPL --years 10
2. 解析 plans[] 中的分红方案
3. 分析美股季度分红特征（每季度分红金额、年度累计）
4. 注意：美股可能包含 splitInfo（拆合股信息）
5. 输出长期分红趋势分析
```

### 场景 37：跨市场分红历史对比

```
用户："对比贵州茅台、腾讯和苹果近3年的分红情况"

AI 步骤：
1. 批量查询分红历史：westock-data dividend list sh600519,hk00700,usAAPL --years 3
2. 解析批量查询结果 中各股票的 plans[]
3. 注意各市场数据格式差异：
   - A股：cashDiviRMB（每10股派息，元）
   - 港股：cashDivPerShare（每股派息，港元）
   - 美股：dividend（每股分红，美元）
4. 统一换算为每股派息金额进行对比
5. 输出跨市场分红对比分析
```

### 场景 38：分红除权日查询

```
用户："苹果什么时候除权派息？"

AI 步骤：
1. 搜索股票：westock-data search 苹果 → usAAPL
2. 查询分红历史：westock-data dividend list usAAPL --years 5
3. 解析 plans[] 中的除权日列表
4. 展示每次的除权日、支付日、每股分红
5. 输出分红除权日历
```

### 场景 39：股东研究分析

```
用户："查一下茅台的十大股东"

AI 步骤：
1. 搜索股票：westock-data search 贵州茅台 → sh600519
2. 查询股东数据：westock-data shareholder sh600519
3. 解析 top10Shareholders（十大股东）和 top10FloatShareholders（十大流通股东）
4. 解析 shareholderNum（股东户数）→ 总户数/A股户数/环比变动/户均持股
5. 分析持股集中度、机构/个人占比、持股变动趋势
6. 输出股东结构分析报告
```

### 场景 40：港股股东与机构持仓分析

```
用户："腾讯的机构持仓情况怎么样？"

AI 步骤：
1. 查询股东数据：westock-data shareholder hk00700
2. 解析 shareholderInfo（持股股东）→ 主要股东持股比例
3. 解析 shareholderDist（股东分布）→ 各类机构持股情况
4. 解析 instHoldingStats（机构持仓统计）→ 机构数量变化、增减持趋势
5. 输出机构持仓分析
```

### 场景 41：公司回购查询

```
用户："查看小米最近的回购情况"

AI 步骤：
1. 搜索股票：westock-data search 小米集团 → hk01810
2. 查询回购数据：westock-data buyback hk01810
3. 解析回购明细：日期、回购股份、回购金额、回购均价
4. 计算累计回购金额、平均回购价格
5. 输出回购分析
```

---

## 九、财务（三大报表/财报披露日历）

> 命令：`finance` `disclosure`

### 场景 42：财务分析

```
用户："分析贵州茅台的盈利能力"
→ westock-data finance sh600519 → 提取关键指标 → 计算同比/环比 → 输出分析结论
```

### 场景 43：财报多期对比分析

```
用户："看看浦发银行和招商银行最近4期的利润表"
→ westock-data finance sh600000,sh600036 --type lrb --num 4
→ 解析批量查询结果 → 提取各期营收、净利润、毛利率
→ 计算同比/环比增长率 → 输出两家银行盈利能力对比

用户："查看腾讯最近4期的综合损益表"
→ westock-data finance hk00700 --type zhsy    # ⚠️ 港股用 zhsy，不是 lrb
```

### 场景 44：财报披露日查询

```
用户："茅台什么时候发财报？"

AI 步骤：
1. 搜索股票：westock-data search 贵州茅台 → sh600519
2. 查询财报披露日历：westock-data disclosure sh600519
3. 解析 items[] 中的披露日列表
4. 区分已披露和预约披露日期
5. 输出最近的财报披露日历
```

---

## 十、ETF（ETF 全维度）

> 命令：`etf detail/holdings/nav/company/holders/financial`

### 场景 45：ETF 全景分析

```
用户："分析一下沪深300ETF的基本情况"

AI 步骤：
1. 搜索 ETF：westock-data search 沪深300ETF → sh510300
2. 查询 ETF 详情：westock-data etf detail sh510300
3. 解析基本信息：类别、成立日期、管理人、托管人、跟踪指数
4. 解析 classification（4 级详细分类）：资产类别 / 投资风格 / 细分领域 / 具体方向 / 跟踪标的
5. 解析 managerHistory（基金经理历史）：当前在任 / 首任 / 任职最长 / 全部历任
6. 解析费用：认购费率、管理费率、托管费率、销售服务费
7. 解析净值/规模：单位净值、溢折率、规模、份额、净申购
8. 解析收益：今年以来、近1月/3月/6月/1年/3年收益率
9. 解析回撤：最大回撤指标
10. 输出 ETF 全景分析报告
```

### 场景 46：ETF 持仓分析

```
用户："沪深300ETF的重仓股有哪些？"

AI 步骤：
1. 搜索 ETF：westock-data search 沪深300ETF → sh510300
2. 查询 ETF 详情：westock-data etf detail sh510300
3. 解析 topStockChanges（重仓股票涨跌幅）→ 股票代码、名称、占比、涨跌幅、较上期变化
4. 解析 holdings（持仓明细）→ 完整持仓列表
5. 分析持仓集中度、行业分布、重仓股涨跌表现
6. 输出 ETF 持仓分析
```

### 场景 47：ETF 净值趋势分析

```
用户："沪深300ETF近一个月净值走势如何？"

AI 步骤：
1. 搜索 ETF：westock-data search 沪深300ETF → sh510300
2. 查询净值历史：westock-data etf nav sh510300 --start 2026-02-10 --end 2026-03-10
3. 解析每日净值、涨跌幅
4. 计算区间收益率、最大回撤
5. 输出净值趋势分析
```

### 场景 48：ETF 费用对比

```
用户："对比沪深300ETF和创业板ETF的费用"

AI 步骤：
1. 搜索 ETF：westock-data search 沪深300ETF → sh510300
2. 搜索 ETF：westock-data search 创业板ETF → sz159915
3. 批量查询详情：westock-data etf detail sh510300,sz159915
4. 对比费用：认购费率、管理费率、托管费率、销售服务费
5. 对比规模、份额、流动性
6. 输出 ETF 费用对比分析
```

### 场景 49：ETF 溢折率分析

```
用户："分析一下沪深300ETF的溢折率情况"

AI 步骤：
1. 查询 ETF 详情：westock-data etf detail sh510300
2. 解析 disc（溢折率）、discountRatioCurve（溢折率曲线）、avgDiscountRatioCurve（同指数平均溢折率）
3. 判断溢价/折价程度及与同类 ETF 的对比
4. 输出溢折率分析
```

### 场景 50：ETF 基金经理稳定性分析

```
用户："沪深300ETF的基金经理稳定吗？历任都有谁？"

AI 步骤：
1. 查询 ETF 详情：westock-data etf detail sh510300
2. 解析 managerHistory：
   - current（当前在任）：与 first（首任）一致 → 经理"超长稳定"
   - longest（任职最长）数组里的人是否仍在 current 内 → 老将仍在岗
   - history（全部历任）数量 → 历任更换次数（少 = 稳定，多 = 频繁更换）
3. 结合 managers 数组（含 intro / experienceYears / returnDuringTenure）补充任职履历和任内回报
4. 输出经理稳定性结论（如"自成立以来仅 1 任经理，柳军任职超 12 年"）
```

---

## 十一、发现（搜索/热搜/股单）

> 命令：`search` `hot stock/wechat/news/board/etf` `stocklist rank/detail`

### 场景 51：查看市场热搜

```
用户："今天市场有哪些热门股票？"

AI 步骤：
1. 查询热搜股票：westock-data hot stock
   → 格式化输出排名、名称、代码、最新价、涨跌幅
2. 可选：查询微信热股：westock-data hot wechat
3. 可选：查询热门板块：westock-data hot board
4. 可选：查询热搜ETF：westock-data hot etf
5. 可选：查询热文排名：westock-data hot news --limit 20
6. 直接基于格式化输出，综合输出市场热点概览
```

### 场景 52：浏览股单

```
用户："有什么好的选股策略推荐？"

AI 步骤：
1. 查询热门股单列表：westock-data stocklist rank
   → 格式化输出股单名称、ID、描述、持仓数、平均涨跌幅、关注人数、分页信息
2. 可选翻页：westock-data stocklist rank --sort updateTime --limit 20 --offset 20
3. 选择感兴趣的股单查询详情：westock-data stocklist detail gd000767
   → 格式化输出股单信息、成分股列表（按涨跌幅排序）
4. 直接基于格式化输出，输出股单推荐列表
```

### 场景 53：行业板块分析

```
用户："今天哪些行业板块涨得好？资金在流向哪里？"

AI 步骤：
1. 查询板块行情榜：westock-data sector ranking
   → 格式化输出行业/概念/地域板块资金流向（净流入TOP和净流出TOP）、北向资金热门板块（当日/近5日/近20日）
2. 直接基于格式化输出，输出行业板块资金面和涨幅分析
```

---

## 十二、宏观（宏观指标）

> 命令：`macro list/indicator`

### 场景 54：查看最新核心宏观指标

```
用户："当前宏观经济面怎么样？"

AI 步骤：
1. 查询最新核心宏观指标：westock-data macro indicator core_indicatros_cur
2. 解析返回的各项核心指标数据
3. 从 GDP 增速、CPI/PPI、PMI、社融、M2 等维度综合分析
4. 输出宏观经济面全景概览
```

### 场景 55：PMI 趋势分析

```
用户："看看最近半年PMI走势"

AI 步骤：
1. 查询 PMI 区间数据：westock-data macro indicator pmi --start 2024 --end 2025
2. 提取每月 PMI 数值（制造业/非制造业/综合）
3. 分析 PMI 是否连续处于荣枯线（50）以上
4. 结合子项（新订单、生产、就业等）分析经济景气度变化
5. 输出 PMI 趋势分析报告
```

### 场景 56：GDP 全景分析

```
用户："分析一下最新的GDP数据"

AI 步骤：
1. 查询全部 GDP 相关指标：westock-data macro indicator gdp,cpi_ppi,consumption,investment --year 2025
2. 解析 GDP 增速（实际 vs 名义）
3. 分析 CPI/PPI 价格走势（通胀/通缩信号）
4. 分析消费和投资数据（内需强弱）
5. 输出 GDP 多维度分析报告
```

### 场景 57：货币政策环境判断

```
用户："当前货币政策环境如何？"

AI 步骤：
1. 查询货币指标：westock-data macro indicator financing,fundquantity,fundcost --year 2025
2. 分析社融规模（financing）→ 实体经济融资需求
3. 分析 M1/M2 增速（fundquantity）→ 货币供应宽松度
4. 分析利率水平（fundcost）→ 资金成本变化
5. 综合判断货币政策取向（宽松/中性/偏紧）
6. 输出货币政策环境分析
```

### 场景 58：宏观数据 + 市场联动分析

```
用户："PMI下滑对A股有什么影响？"

AI 步骤：
1. 查询 PMI 趋势：westock-data macro indicator pmi --start 2024 --end 2025
2. 查询同期上证指数走势：westock-data quote sh000001
3. 对比 PMI 走势与指数走势的相关性
4. 分析 PMI 下行期间哪些板块受影响更大
5. 输出宏观-市场联动分析
```

---

## 十三、期货（外盘商品/金融期货 + 港股股指期货）

> 命令：`futures search/detail` + `quote`（支持期货代码）

### 场景 59：期货行情查询（关键词→代码→行情）

```
用户："现在国际金价多少？"

AI 步骤：
1. 关键词找代码：westock-data futures search 黄金 → fuGC（COMEX黄金）
2. 查询行情：westock-data quote fuGC
3. 解析最新价、涨跌幅、货币单位（USD）
4. 说明为延时行情（isDelayed），并给出生成时间
```

### 场景 60：期货合约资料查询

```
用户："WTI原油期货的合约规格是怎样的？"

AI 步骤：
1. 关键词找代码：westock-data futures search 原油 → fuCL（WTI原油，NYMEX）
2. 查询合约资料：westock-data futures detail fuCL
3. 解析交易所、合约规模、货币币种、最小变动单位、交易时间、所在时区
4. 输出合约规格说明
```

---

## 十四、外汇（离岸人民币/主要货币对/美元指数）

> 命令：`forex search/list` + `quote`/`kline`/`minute`（支持外汇代码 `fx*`）

### 场景 61：外汇行情查询（关键词→代码→行情）

```
用户："离岸人民币现在多少？"

AI 步骤：
1. 关键词找代码：westock-data forex search 离岸 → fxCNH（离岸人民币）
2. 查询行情：westock-data quote fxCNH
3. 解析最新价、涨跌幅
4. 给出生成时间
```

### 场景 62：外汇走势查询（K线/分时）

```
用户："美元日元近一个月走势如何？"

AI 步骤：
1. 关键词找代码：westock-data forex search 美元日元 → fxUSDJPY
2. 查询日K：westock-data kline fxUSDJPY --period day --limit 30
3. 解析区间高低点、涨跌幅，描述趋势
4. 提示：外汇仅提供当日分时（minute），不支持五日分时
```

---

## 十五、债券（可转债 / 可交换债）

> 命令：`quote`/`minute`/`kline`（支持可转债代码 沪 `sh11xxxx`/`sh13xxxx`、深 `sz12xxxx`）+ `bond detail`（发行要素/条款/现金流）

### 场景 63：可转债行情查询（价格 + 转债维度）

```
用户："兴业转债现在行情怎么样？转股价值和溢价率高不高？"

AI 步骤：
1. 查询行情：westock-data quote sh113052
   （可转债走专属字段集，除价格/成交外额外返回转债维度，单只竖排「项目/内容」表展示）
2. 解析通用字段：最新价、涨跌幅、成交额
3. 解析转债维度：转股价值（bond_equity_value）、转股溢价率（bond_equity_premium）、
   双低（bond_double_low）、转股价（bond_convert_price）、正股代码（bond_stock_code）
4. 结合溢价率高低、双低值给出客观描述（不做投资建议）
5. 提示：行情接口不返回债券简称（name 为空），如需发行人/评级/条款用 bond detail
```

### 场景 64：可转债基本面与条款（行情 + 详情联动）

```
用户："兴业转债的规模、到期日和赎回回售条款是什么？"

AI 步骤：
1. 行情快照看规模/期限：westock-data quote sh113052
   → 总规模（bond_total_size）、剩余规模（bond_undue_size）、到期日（bond_due_date）、
     到期收益率（bond_ytm）、强赎触发价/回售触发价
2. 详情看完整发行要素与条款：westock-data bond detail sh113052
   → 发行人、票面利率、期限
3. 条款全文：westock-data bond detail sh113052 --terms
4. 利率变动/现金流/赎回回售明细：westock-data bond detail sh113052 --schedule
5. 综合行情与详情，客观说明规模、到期安排与赎回/回售触发条件
```

---

**记住**：westock-data 是数据查询工具，AI 负责数据分析和洞察！
