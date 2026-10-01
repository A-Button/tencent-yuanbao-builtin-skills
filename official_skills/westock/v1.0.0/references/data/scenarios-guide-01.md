# WeStock Data - 常见分析场景详解 · 分册 01

[本手册索引](scenarios-guide.md) · [技能入口](../../SKILL.md)

> 仅查当前需要的章节；示例和分析模板不增加用户条件。遵循入口的停止规则，默认文字回答，仅明确要求文件时创建文件。

# WeStock Data - 常见分析场景详解

> **定位**：本文档是 SKILL.md 的 **L3 层补充材料**，提供完整的分析场景示例和详细操作步骤。
>
> **使用方式**：AI 在遇到不确定的分析场景时按需加载本文档。命令列表和基本用法请参见
> [SKILL.md](../../SKILL.md)。
>
> **场景总数**：共 70+ 个场景，按 15 个功能分组组织。
>
> **来源与降级**：本文件中的 Westock 命令均为优先路径；正确调用仍因接口异常、覆盖不足或字段缺失取不到数据时，按 [入口缺口处理](../../SKILL.md#5-缺口处理停止该分支不无限换源) 使用 `web_search` 仅补缺失部分，注明原因、原文来源、日期与口径。筛选无匹配、尚未披露等正常空结果不触发降级；所有新闻直接使用 `web_search`，不适用 Westock 优先和失败降级流程。

---

## 一、行情（价格序列）

> 命令：`westock quote` `westock minute` `westock kline`

### 1.1 分析成交量趋势

```
用户："分析牧原股份近20天的成交量"
→ westock search 牧原股份 → westock kline sz002714 --period day --limit 20 → 从表格中提取volume → 计算统计指标 → 输出分析报告
```

### 1.2 多股对比（使用批量查询）

```
用户："对比贵州茅台和格力电器近半年走势、财务、资金面"
→ 一次批量（各 1 条；不要 kline/technical 按股拆开）：
   westock quote sh600519,sz000651
   westock kline sh600519,sz000651 --period day --limit 120
   westock technical sh600519,sz000651
   westock finance sh600519,sz000651 --limit 4
   westock fund flow sh600519,sz000651
   westock fund north-holding sh600519,sz000651
```

若需要新闻辅助解释走势，直接使用 `web_search` 按公司、事件主题和目标日期区间检索，并阅读关键报道原文；近期新闻不能冒充半年历史覆盖。只分析走势、财务、资金时，不额外查询新闻；其它结构化数据命令不因此改用网页。

```
用户："对比腾讯和阿里巴巴的市值"
→ westock quote hk00700,usBABA → 一次查询两只股票 → 解析批量查询结果 → 提取市值 → 输出对比
```

### 1.3 指数/板块K线分析

```
用户："上证指数近一个月的走势"
→ westock kline sh000001 --period day --limit 30 → 解析K线 → 输出趋势分析
（⚠️ 走势用 kline 看趋势；但"某天/区间涨跌幅"用 `westock quote --date` 直接读返回字段，不要用 kline 手算）

用户："半导体板块近一周的K线走势"
→ westock search 半导体 --type sector → 获取板块代码（如 pt01801081）
→ westock kline pt01801081 --period day --limit 5 → 解析K线 → 输出走势

用户："茅台 2025 年全年的日K"（按日期范围）
→ westock kline sh600519 --start 2025-01-01 --end 2025-12-31 → 解析K线 → 输出年度走势
（提示：--start/--end 优先级高于 --limit；仅指定 --start 时 end 默认今天）
```

### 1.4 指数/板块分时走势

```
用户："大盘今天的分时走势怎么样"
→ westock minute sh000001 → 解析分时数据 → 输出走势分析

用户："半导体板块今天的盘中走势"
→ westock search 半导体 --type sector → 获取板块代码（如 pt01801081）
→ westock minute pt01801081 → 解析分时 → 输出走势
```

### 1.4.1 技术指标多周期分析

`westock technical` 支持**日K/周K/月K/季K/年K/分钟K**等周期技术指标；AI 做趋势分析时可同时拉多周期对比（美股指数仅支持日K，非日周期返回 `TECHNICAL_002`）：

```
用户："分析茅台的中长期技术面"
→ westock technical sh600519 --period day               # 日K最新
→ westock technical sh600519 --period week              # 周K技术指标
→ westock technical sh600519 --period month --limit 12  # 月K近12期
→ 对比日线/周线/月线 MACD、KDJ 状态 → 给出多周期共振判断
```

## 二、技术分析（衍生指标/筹码）

> 命令：`westock technical` `westock chip`

### 2.1 筹码成本分析

```
用户："分析一下茅台的筹码分布情况"

AI 步骤：
1. 搜索股票：westock search 贵州茅台 → sh600519
2. 查询筹码数据：westock chip sh600519
3. 解析筹码盈利率（chipProfitRate）→ 判断获利盘/套牢盘比例
4. 对比收盘价与平均成本（chipAvgCost）→ 判断当前价位相对筹码成本的位置
5. 分析集中度（chipConcentration90/70）→ 集中度越低，筹码越集中
6. 输出筹码分析结论
```

### 2.2 筹码趋势分析

```
用户："看看招商银行近一个月的筹码变化趋势"

AI 步骤：
1. 搜索股票：westock search 招商银行 → sh600036
2. 查询历史筹码：westock chip sh600036 --start 2026-02-10 --end 2026-03-10
3. 解析 items[] 中每日的筹码数据
4. 分析趋势：
   - 盈利率趋势（上升 = 获利盘增加）
   - 平均成本趋势（上升 = 筹码成本抬升，主力可能在建仓）
   - 集中度趋势（下降 = 筹码趋于集中，可能有主力控盘）
5. 输出筹码变化趋势分析
```

---

## 三、市场（全市场截面/总览/互联互通/新股）

> 命令：`westock lhb` `westock market-overview` `westock connect` `westock ipo`

### 2.1 查询股票基本信息

```
用户："查询腾讯控股的股价"
→ westock search 腾讯控股 → 获取 hk00700 → westock quote hk00700 → 展示价格和涨跌幅
```

### 2.2 新股申购分析

```
用户："最近有什么新股可以申购？"

AI 步骤：
1. 查询沪深新股：westock ipo --market hs
   → 格式化输出按状态分类（即将发行/今日可申购/即将上市/中签号公布/已上市），含发行价、市盈率、申购代码、上市日、可比公司、风险提示等
2. 可选：查询港股新股：westock ipo --market hk
   → 格式化输出按申购日/上市日分类，含入场费、认购倍数、募集金额等
3. 可选：查询美股新股：westock ipo --market us
   → 格式化输出按状态分组（注册中/已定价/已提交等），含行业、发行价、价格区间、承销商等
4. 直接基于格式化输出，输出新股申购机会分析
```

### 2.3 今日市场点评（market-overview summary）

```
用户："今天 A 股市场怎么样？"

AI 步骤：
1. 一键拉取大盘画像：westock market-overview （默认 type=summary）
2. 解析 14 维度得分（估值/情绪/技术/趋势/风格轮动 等）+ 状态文案
3. 综合给出今日市场点评，标注偏强/偏弱维度
4. 如需补充，叠加 --type updown（涨跌停/红绿盘）/ --type margin（两融）/ --type valuation（中证全指 PE 百分位）
```

### 2.4 沪深港通成份股查询（connect）

```
用户："沪股通有哪些标的"

AI 步骤：
1. 拉沪股通成份股：westock connect --exchange sh
2. 分页拉全量：westock connect --exchange sh --limit 100 --offset 0
3. 拉深股通：westock connect --exchange sz
4. 输出标的池（注意：connect 是"标的池"列表，不是资金流量；查北向日度资金流量请用 `westock fund flow sh600000`；查北向季度持仓请用 `westock fund north-holding sh600519`；查申万行业北向分布请用 `westock fund north-holding <板块代码>`）
```

> ⚠️ **职责边界**：`westock connect` = 沪深港通**标的池**（标的列表）；`westock fund flow` = 日度资金流量；`westock fund north-holding` = 北向季度持仓（个股或申万行业）；三者不要混用。

---

## 四、指数（清单/搜索/成份股/行情对比）

> 命令：`westock index list/constituent` + `westock search --type index`；指数行情用 `westock quote` / `westock search --type index`

### 3.1 指数行情查询

```
用户："查一下今天大盘的涨跌情况"
→ westock search 上证指数 → 获取 sh000001 → westock quote sh000001 → 展示涨跌幅和成交额
```

### 3.2 多指数对比

```
用户："对比沪深两市今天的表现"
→ westock quote sh000001,sz399001 → 解析批量查询结果 → 对比涨跌幅 → 输出分析
```

### 3.3 跨市场指数对比

```
用户："对比恒生指数和纳斯达克今天的表现"

AI 步骤：
1. 批量查询行情：westock quote hkHSI,us.IXIC
2. 分别解析各指数的行情数据
3. 对比涨跌幅
4. 输出跨市场指数对比分析
```

### 3.4 查询指数成份股

```
用户："沪深300有哪些成份股？"

AI 步骤：
1. 查询沪深300成份股：westock index constituent sh000300
2. 解析返回的成份股列表
3. 输出成份股列表
4. 可按行业分布统计
```

---

## 五、板块（搜索/成份股/信息/行情榜/经营/估值/预测/财务）

> 命令：`westock search --type sector` / `westock sector constituent/info/ranking/oper/valuation/forecast/finance`

### 3.1 板块行情分析

```
用户："半导体板块今天的涨跌情况"
→ westock search 半导体 --type sector → 获取板块代码（如 pt01801081） → westock quote pt01801081 → 展示涨跌幅和成交额
```

### 3.2 查询概念股列表（⚠️ 常见易错场景）

```
用户："华为概念有哪些股票？"
用户："AI概念股有哪些？"
用户："新能源汽车概念股"

⚠️ 错误做法：默认 `westock search 华为` 只搜股票，搜不到板块；或用外部搜索工具
✅ 正确做法：用 `westock search <关键词> --type sector` 两步查询

AI 步骤：
1. 搜索概念板块代码：westock search 华为 --type sector
   → 返回匹配的板块列表（如 style_pt01801517 华为概念）
2. 用板块代码查成份股：westock sector constituent style_pt01801517
   → 返回华为概念的全部成份股列表
3. 输出概念股列表（代码、名称）
4. 可选：批量查询行情 westock quote <代码列表> → 补充行情数据
```

> **关键区分**：
> - `westock search 华为 --type sector` → 拿到板块代码后，用 `westock quote`/`westock kline`/`westock minute` 查板块行情
> - `westock search 华为 --type sector` → 再用 `westock sector constituent <代码>` 查成份股

### 3.3 查询行业成份股

```
用户："电子行业有哪些成份股？"

AI 步骤：
1. 查询申万一级电子行业成份股：westock sector constituent pt01801080
2. 解析返回的成份股列表
3. 输出成份股列表（代码、名称）
4. 可补充成份股数量统计
```

### 3.4 板块成份 + 行情联动分析

```
用户："帮我看看半导体板块的成份股，并查看涨幅前5的行情"

AI 步骤：
1. 查询申万二级半导体成份股：westock sector constituent pt01801081
2. 取返回的成份股代码列表
3. 批量查询行情：westock quote <前N只代码逗号分隔>
4. 按涨跌幅排序取前5
5. 输出板块成份 + 涨幅排行分析
```

### 3.5 板块成份股查询

```
用户："半导体板块有哪些成份股"

AI 步骤：
1. 搜索板块代码 → pt01801081
2. 拉取成份股：westock sector constituent pt01801081
3. 输出成份股清单（含代码/名称/涨跌/成交额等）
```

> ⚠️ 易混淆：用户问"板块成份股"用 `westock sector constituent <代码>`；问"板块估值/盈利预测/财务"用 `westock sector valuation/forecast/finance <代码>`；问"板块概况"用 `westock sector info <代码>`。

### 3.6 申万行业基本面三连

```
用户："银行行业现在估值怎么样？盈利前景如何？"
用户："帮我分析一下半导体行业的基本面：财报、估值和一致预期"
用户："电子和银行哪个行业估值更低、盈利增速更好？"

⚠️ 错误做法：
- 用 `westock finance sh600036`（个股三大表）回答行业问题
- 用 `westock consensus`（个股一致预期）代替行业预测
- 用 `westock market-overview --type valuation`（全市场中证全指）代替单行业估值
- 概念/地域板块不支持 `westock sector forecast` / `westock sector finance`。预测支持申万 sw1/sw2，财务支持 sw1/sw2/sw3；先搜索并确认行业映射，不能擅自用相近行业代替用户指定的概念板块。

✅ 正确做法：finance（已披露）→ valuation（贵不贵）→ forecast（未来预期）

AI 步骤：
1. 若用户未给代码：westock search 银行 --type sector
   → 取申万行业 pt 代码（如 pt01801780 银行一级）
2. 同一轮并行查询三条（深研单行业）：
   westock sector finance pt01801780
   westock sector valuation pt01801780
   westock sector forecast pt01801780
3. 解读链条：
   - finance：`revenueTTM` / `netProfitTTM` / `roeTTM` / `debtRatio` → 当下盈利与杠杆
   - valuation：`PeTTM` + `PeTTMPct` 等百分位 → 相对历史贵不贵
   - forecast：未来 3 年 `netProfitYoy` / `pe` / `peg` → 机构一致预期增速与估值
4. 指定日期：westock sector finance pt01801780 --date 2026-03-31
   或 westock sector valuation pt01801780 --date 2026-06-25
5. 多行业对比：截面命令支持逗号批量
   westock sector valuation pt01801780,pt01801080
   westock sector forecast pt01801780,pt01801080
   westock sector finance pt01801780,pt01801080
6. 输出：基本面→估值→预期三段分析，指出增速与估值是否匹配

> **职责边界**：`westock sector oper` = 行业经营指标（产量/库存等，传行业中文名）；`westock sector finance/valuation/forecast` = 申万行业财报/估值/一致预期（传 pt 代码）。
```

---

## 六、研究（评分/评级/预期/研报/脱水研报）

> 命令：`westock score` `westock rating` `westock consensus` `westock report` `westock dehydrated`

### 4.1 机构评级与一致预期分析

```
用户："看看茅台的机构评级和一致预期"

AI 步骤：
1. 搜索股票：westock search 贵州茅台 → sh600519
2. 查询评级数据：westock rating sh600519
   → 解析机构评级分布（买入/增持/中性/减持/卖出）
3. 查询一致预期：westock consensus sh600519
   → 解析 EPS/净利润/营收的一致预期值和增长率
4. 查询评分：westock score sh600519
   → 解析综合评分、细分维度评分
5. 输出机构研究综合报告
```

### 4.2 研报查询与脱水研报

```
用户："看看最近有哪些关于茅台的研报"

AI 步骤：
1. 搜索股票：westock search 贵州茅台 → sh600519
2. 查询研报列表：westock report list sh600519 --limit 10
   → 解析研报标题、机构、分析师、评级、发布时间
3. 可选：查询脱水研报：westock dehydrated --limit 20
   → 解析核心观点、投资建议、目标价
4. 输出研报摘要和核心观点
```

---

## 七、事件（事件标签/风险事件/投资日历/停复牌）

> 命令：`westock events` `westock risk` `westock calendar` `westock suspension`

### 5.1 投资日历查询（个股事件日历）

```
用户："本周有哪些个股事件？" / "今天有哪些股票分红/发财报？"

AI 步骤：
1. 查询指定日期的个股事件：westock calendar --date 2026-03-10
   → 按事件类型分组输出（财报发布/分红派息/新股发行/停复牌/会议/限售解禁/增发）
2. 默认查当天，可按 --date 指定日期，--market 指定市场（hs/hk/us）
3. 按事件类型筛选：westock calendar --date 2026-03-10 --event dividend --market hs
   → --event 取值：financial_report/dividend/ipo/trading_halt/meeting/lockup_release/rights_issue/all
4. 多类型用逗号分隔：westock calendar --date 2026-03-10 --event dividend,financial_report
5. 若需查本周，逐天查询周一至周五各天数据，汇总输出
6. 宏观经济日历请使用 westock macro indicator cn_calendar_future|cn_calendar_hist
```

> ⚠️ `westock calendar` 是**个股事件日历**（查某天哪些股票有分红/财报/IPO等事件），不含宏观经济指标。
> 与 `westock suspension` 的区别：`suspension` 返回当前全市场停复牌列表，`calendar --event trading_halt` 只返回指定日期有停复牌事件的股票。

### 5.2 个股事件总览（events）

```
用户："最近茅台有什么大事"

AI 步骤：
1. 拉事件标签：westock events sh600519
2. 解析返回的事件 ID 列表（如 7=分红实施 / 23=董监高变动 / 12=限售解禁 等）
3. 按事件分类分组展示（董监高/分红/财报/指数变动/限售解禁等 9 大类）
4. 如需深挖某类，再用 risk 钻取（如 --types pledge 看质押细节）
```

### 5.3 事件 → 风险细查链路（events + risk）

```
用户："看看 sh600519 有没有质押风险"

AI 步骤：
1. 先看事件全貌：westock events sh600519
2. 若含质押/解禁标签，用 risk 钻取明细：
   westock risk sh600519 --types pledge,unlock
3. 解析质押率（已修复 100 倍单位错误）/ 解禁规模 / 解禁日期
4. 输出风险细节
```

### 5.4 高管变动 / 增减持 / 评级变动监控（risk 新类型）

```
用户："最近哪些高管在减持茅台"

AI 步骤：
1. 拉取高管增减持明细：westock risk sh600519 --types executivetransfer
   （别名 executive 也可：--types executive）
2. 解析每条增减持记录：高管姓名、变动数量、变动方向、变动后持股
3. 输出增减持汇总
```

```
其他新增 risk 类型：
- westock risk <code> --types leaderchange     # 高管变动（任免）
- westock risk <code> --types bondrating       # 评级信息（如 AAA/AA+）
```

---

## 八、资讯（新闻、公告、原文）

> 新闻统一直接使用 `web_search`，包括近期证券资讯、历史事件回溯、开放资讯及热门新闻；不查询证券代码或新闻 ID 作为前置步骤。公告继续使用 `westock notice list`、`westock notice detail`，规则见 [新闻路由](./routing-guide.md)。
>
> **关键正文必须核验**：本文件所有场景中，用于摘要、事件判断或涨跌解释的关键报道，必须阅读搜索命中的公开原文，而非只看标题或搜索摘要。仅列标题与元数据时可不逐篇阅读；未获取正文不能声称已核验事实或作确定性归因。

### 6.1 公告全文查询

```
用户："查看贵州茅台最近的财务公告内容"

AI 步骤：
1. 搜索股票：westock search 贵州茅台 → sh600519
2. 查询公告列表：westock notice list sh600519 --type 1
3. 从列表中获取公告ID（如 nos1224809143）
4. 查询公告内容：westock notice detail nos1224809143
   → 格式化输出标题、发布时间、关联股票、相关链接（PDF/原文/翻译），A股/北交所直接展示正文内容，港股/美股展示PDF下载链接
5. 直接基于格式化输出，输出公告内容摘要
```

### 6.2 近期证券新闻查询与关键正文核验

用户：“看看最近关于茅台的证券新闻，概括关键事件。”

1. 直接使用 `web_search`，按公司全名、证券新闻主题及用户指定时间范围检索；有主体歧义时先确认，不要求先获取证券代码或新闻 ID。
2. 按相关性、实际发布时间和来源可靠性筛选结果，合并重复转载；需要市场背景时再增加相应市场或行业关键词，不机械扩展查询。
3. **必要步骤**：阅读每条影响摘要、事件判断或归因的关键报道原文，核对主体、事实、发布时间、事件时间和来源。标题及搜索摘要只作线索，不当成正文。
4. 基于已核验正文概括关键事件，附发布方、日期和原文链接。区分事件事实与影响判断，不能仅凭新闻与涨跌时间相邻就断言因果关系。
5. 原文不可访问或只有标题摘要时注明未核验，检索覆盖不足时说明缺口；不得补写事实，也不回退到 CLI 新闻入口。仅要标题清单时可以不逐篇读正文，但须明确展示的是标题和元数据。

### 6.3 历史及开放资讯检索

- **历史回溯**：如“回顾某公司 2025 年上半年的重要事件”，直接用 `web_search` 按公司全名、事件和日期范围检索，并以原文核对实际发生时间。
- **开放资讯**：如“梳理某公司近期产品发布和行业背景”，即使涉及上市公司也用 `web_search` 查公开资料，不强制先转为证券代码。
- **正文与时间核验**：对影响结论的报道打开公开原文，确认发布/更新时间、实际事件时间及主体，附发布方与原文链接；搜索摘要只作线索。原文不可访问时标记未核验，不能声称完整覆盖。
- **混合分析**：若同时需要股价、财报或资金数据，按对应 Westock 命令查询，并将结构化数据与报道分别注明来源。研究某个历史时点时，事后报道只能作后续背景，不能冒充当时已知信息。

---

## 九、资金（二级市场资金）

> 命令：`westock fund flow` / `westock fund short` / `westock fund margin` / `westock fund block` / `westock fund north-holding`

### 7.1 批量资金流向分析

```
用户："对比腾讯和美团的资金流向"
→ westock fund flow hk00700,hk03690 --date 2026-03-10 → 一次查询两只 → 解析批量查询结果 → 对比资金面
```

### 7.2 A股资金流向分析

```
用户："分析中芯国际的资金面"
→ westock fund flow sh688981 → 解析 MainNetFlow/JumboNetFlow → 输出资金面判断
```

### 7.3 港股资金与卖空分析

```
用户："腾讯控股的资金流向情况"
→ westock fund flow hk00700 → 解析 TotalNetFlow/MainNetFlow/RetailNetFlow → 输出资金分析

用户："腾讯控股的卖空情况如何"
→ westock fund short hk00700 → 解析 ShortShares/ShortAmount/ShortRatio → 卖空比率>15%需关注
```

### 7.4 美股卖空数据分析

```
用户："苹果公司的卖空情况"
→ westock fund short usAAPL → 解析 ShortRatio/ShortShares/ShortRecoverDays → ShortRatio>10%或ShortRecoverDays>5天需关注
```

