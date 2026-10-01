# 路由速查指南

> 本文档收纳"什么场景用什么命令"的路由规则。命令本身的语法/参数在 [commands.md](./commands.md)，返回字段在 [ai_usage_guide.md](./ai_usage_guide.md)，分析模板在 [scenarios-guide.md](./scenarios-guide.md)。

---

## 一、本 Skill 是什么

**金融市场结构化数据查询入口**。行情、财务、公告、研报及筛选等使用对应 Westock 命令；所有新闻（包括近期证券资讯、历史报道及热门新闻）直接使用 `web_search`，无需先调用 Westock，也不属于失败降级。具体执行规则见第五节。

- **标的覆盖**：股票（A股/港股/美股/日韩股）、ETF、指数、板块、期货、外汇、可转债
- **数据维度**：行情、K 线、分时、技术指标、筹码、三大财报、披露日历、资金流向、北向资金持仓、机构评级、一致预期、研报、脱水研报、公告、事件标签、风险事件、股东、分红、回购、ETF 持仓/净值、宏观经济
- **市场维度**：热搜榜、股单榜、新股日历、投资日历、龙虎榜、市场涨跌分布、沪深港通成份、板块搜索/成份/行情榜/经营/估值/盈利预测/财务

> **不同标的支持的维度差异较大**，具体能力矩阵见 [§六 能力差异速查](#六能力差异速查标的--维度)。

> 已知命令直接执行；不确定时按命令名定位 [commands.md](./commands.md)，仅在仍有疑问时查目标子命令的 `--help`。本指南聚焦数据查询，筛选与复合任务见 [统一入口](../../SKILL.md)。

---

## 二、结构化数据与资讯的来源边界

- **命中能力先调用 Westock**：行情、K 线、财务、资金、成份、宏观指标及股票池筛选等使用对应命令，不直接以 `web_search`、私有接口直连、其它金融工具或训练记忆替代。正确调用仍存在真实数据缺口时，才进入下述降级流程。
- **公告与研报先走专用入口**：使用 `westock notice list`、`westock notice detail`、`westock report list`、`westock report detail`；拿不到原文时可按降级规则检索公开原文，不能把媒体报道冒充公告或研报。
- **新闻一律直接检索**：近期证券新闻、市场资讯、历史回溯、热门新闻和开放报道均直接使用 `web_search`；不走 CLI 新闻列表、详情或热文榜，也不要求先调用 Westock 失败后再搜索。关键报道须阅读公开原文核验。
- **混合问题分别取证**：例如历史涨跌幅先用 `westock quote`，同期报道用 `web_search`；新闻分流不免除其它能力先用 Westock 的要求，补充数据和原有结果分别注明来源。

**受控降级**：先核对请求参数、日期、市场和字段范围；正确调用后仍因接口异常、覆盖不足或字段缺失取不到数据时，说明原因，保留成功部分，允许用 `web_search` 定向补缺。优先核验公开原始发布，补充项注明来源链接、数据日期、单位及口径差异，不标成 Westock 数据；原文无法核验或口径不一致时保留缺口，不强行填数。

**不得触发降级的正常空结果**：筛选无匹配、尚未披露、该时点确无记录。空值含义不明时先确认状态和覆盖，不自动判定失败；不改市场或放宽条件凑结果，不重建全市场选股器，不绕过登录、付费或权限限制。详细流程见 [入口缺口处理](../../SKILL.md#5-缺口处理停止该分支不无限换源)。

---

## 三、技能内的数据查询与筛选边界

| 场景 | 使用命令 | 不要混淆 |
|---|---|---|
| 「哪天有什么事」（日历视角） | `westock calendar --event ... --market ...` | `screen event` 是事件股票池，不是日历清单 |
| 「最近有哪些新股」（清单视角） | `westock ipo` 或 `westock calendar --event ipo` | 不必先做条件筛选 |
| 「查某只股票的某项数据」 | 对应数据查询命令 | `screen` 用于形成股票池，不代替明细 |
| 「全市场扫 ST」（标签筛股） | `westock screen label --type risk_st` | 不逐股调用风险查询穷举 |
| 「全市场高质押率/高解禁」 | `westock screen event`；排行用 `westock screen ranking` | 与个股事件明细区分 |

筛选语法和市场限制见 [筛选指南](../screener/ai_usage_guide.md)。

---

## 四、高频意图 → 精确命令

| 用户意图 | 精确命令 | 易错点 |
|---|---|---|
| 用户给名称（如"宁德时代"/"腾讯"/"苹果"）查股票代码 | `westock search <关键词>` **默认仅搜股票**（含 A股/港股/美股；排除 ETF/可转债/板块/指数等） | 不要凭印象拼代码；`westock quote` 是已知代码查行情，`westock search` 才是按关键词找代码 |
| 指定某日行情 | `westock quote <代码> --date YYYY-MM-DD` | 直接读返回字段（见 ai_usage_guide.md），**禁止**用 `westock kline` 手算、**禁止**用无 `--date` 的实时 `westock quote` 取当天值 |
| 查 MACD / KDJ / RSI 等技术指标 | `westock technical <代码> [--period 周期]` | 多股用 `westock technical sh600519,sz000651`；支持所有 K 线周期的MA/MACD/KDJ/RSI/BOLL |
| 用户想找其它类型（ETF/可转债/板块/指数/期货/外汇） | `westock search <关键词> --type etf\|bond\|sector\|index\|futures\|forex` | 支持 `--type a,b,c` 逗号分隔一次搜多类型；否则必须显式 `--type` 切换；`--type stock` 等价于默认行为 |
| 用户给名称查指数 | `westock search <关键词> --type index` | 与 `westock quote sh000300` 不同：搜索返回清单，`westock quote` 是已知代码查行情；**不要**用 `westock index list` 翻整张清单（>1400 条）找 |
| 用户想搜板块/概念（如"银行"/"华为概念"） | `westock search <关键词> --type sector` | 跨全部清单一次搜；拿到 code 后再 `westock sector constituent` / `westock sector info` 等 |
| 某天的财报发布事件（沪深/港/美） | `westock calendar --event financial_report --market hs` | 用本 skill `westock calendar`，**勿用** `westock screen event` |
| 某天的分红派息 / 停复牌 / 股东大会等日历 | `westock calendar --event dividend\|trading_halt\|meeting --market hs` | `--event` 多类型用逗号分隔 |
| 最近有哪些新股 | `westock ipo --market hs` 或 `westock calendar --event ipo --market hk` | 勿用 `screen` 股票池替代新股清单 |
| 查 ETF 净值历史（NAV） | `westock etf nav <代码> [--start ... --end ...]`（可批量） | **不是 `westock kline`**！`nav` 优先取 `EtfNav`；`westock kline` 为场内 OHLC |
| 基金档案 + 资产配置 | `westock etf profile` | 分类/管理人/费率 + EtfAssetAllocation |
| 运作概览（行情/规模/资金流/估值） | `westock etf overview` | 行情/规模/溢折率/净申购/估值 |
| 申赎清单 + 重仓涨跌 | `westock etf holdings` | 清单 `etf_prlist_{code}` |
| 查全市场涨跌分布（11 档区间分布、两市成交额） | `westock changedist` | 不是 `westock market-overview --type updown`（后者是多周期上涨家数趋势） |
| 大盘画像看全部维度 | `westock market-overview --type all` | 不要省略 `--type`（默认只返回 summary） |
| 查宏观经济指标（GDP/CPI/PMI/利率/工业/消费/投资 / 美/港/日/欧主题宏观 / 36 个地区海外预期） | `westock macro indicator <短名>` 或 `westock macro expect --area <iso3>` | ⚠️ **不要用 `westock market-overview` 替代**！`westock market-overview` 是 A 股大盘画像，不含宏观指标；⚠️ 必须先正确调用 `westock macro indicator`，禁止直接绕过；仍有真实数据缺口时按第二节用 `web_search` 定向补充并标明来源和口径 |
| 查最新核心宏观（GDP+CPI+PMI+工业+消费+投资一键拿） | `westock macro indicator cn_core` | 一次性返回 7 大核心指标，不要用多次单指标查询拼凑 |
| 查美股 / 港股 / 日本 / 欧元区主题宏观（事件日历型） | `westock macro indicator us_inflation --date <今天>`（单指标）；多指标用**空格**分隔短名 | 海外主题指标统一短名 `<region>_<topic>`（如 `us_employment`/`jp_inflation`），用 `westock macro list --region us` 查可用清单；`macro indicator` **无** `--region` |
| 查 36 个地区海外预期日历（actual/forecast/former） | `westock macro expect --area <iso3> --year <年>` | 地区代码用 `westock macro expect list` 查询；按年归档（与主题型不同） |
| 跟踪美联储降息/加息预期（FOMC 决议/点阵图） | `westock macro indicator us_monetary --date <今天>` + `westock macro expect --area usa --year <当年>` | 三栏对比 ActualValue/ForecastValue/FormerValue；FFR 当前年度/后面1-3年/长期是点阵图维度；详见场景 72 |
| 评估美国通胀压力（CPI/PCE/PPI/通胀预期） | `westock macro indicator us_inflation --date <今天>` | 重点看核心 PCE（美联储锚）+ PPI（上游传导）+ 密歇根 5 年通胀预期（脱锚警讯）；详见场景 73 |
| 中美宏观对比（增长/通胀/货币三维度） | `westock macro indicator us_eco_growth us_inflation us_monetary --date <今天>` + `westock macro indicator cn_core --date <今天>` | 用于判断中美周期错位/共振、人民币汇率、北向资金趋势；详见场景 74 |
| 港股宏观环境（联系汇率制度） | `westock macro indicator hk_eco_growth hk_export_reserve hk_monetary hk_others --date <今天>` + `westock macro indicator us_monetary --date <今天>` | 港币挂钩美元 → 港股流动性受美联储驱动 + 基本面受中国驱动；详见场景 75 |
| 全球三大央行政策对比 | 并行 `us_monetary` + `jp_monetary` + `eu_monetary` --date | 用于美元指数/黄金/Carry trade/新兴市场流动性研判；详见场景 76 |
| 查某条研报 / 脱水研报详情 | `westock report detail <id>` / `westock dehydrated detail <id>` | **不要省略 `detail`**！裸传 ID 或代码会报错并引导正确子命令 |
| 查个股 ESG 评级（中证/聚源） | `westock esg <代码>` | 不是 `westock rating`（机构研报评级）；不是 `westock score`（量化评分） |
| 查批量/单股财务（三大表） | `westock finance sh600519` 或 `westock finance sh600519,sz000651` | 默认拉 income+balance+cashflow，勿拆 3 次 |
| 查资产负债表 | `westock finance <代码> --type balance` | |
| 查利润表 | `westock finance <代码> --type income` | A/HK/US 同一参数 |
| 查公告（按代码 + 类型） | `westock notice list <代码> --type <类型>` | 不要用关键词搜索；先 `westock search` 拿股票代码再调 `westock notice list` |
| 查某条公告全文 | `westock notice detail <公告ID>` | id 是位置参数，不要拿 id 当关键词搜 |
| 期货搜合约 → 看资料 | `westock search <关键词> --type futures` → `westock futures detail <代码>` | 先用 `westock search`；代码查询存在真实覆盖缺口时按第二节用 `web_search` 核对公开资料，不猜测 Westock 代码格式 |
| 热门财经资讯/热文 | `web_search` | 直接搜索并核验原文，不把搜索结果当成特定平台热文榜 |
| 查板块行情榜 / 板块详情 | `westock sector ranking` / `westock sector detail <代码>` | 板块资金流向、涨跌幅等 |
| 查停复牌（按日期/市场） | `westock suspension --market hs\|hk\|us` | 与 `westock calendar --event trading_halt` 的区别：`westock suspension` 直接返回当前停复牌列表，`westock calendar` 只在指定日期有事件时返回；港股停牌优先用 `westock suspension` |
| 查公司基本信息（主营/简介/地址） | `westock profile <代码>`（支持批量） | `westock quote` 是行情快照，不含公司简介；批量用 `westock profile sh600519,hk00700` 而不是 `westock quote` |
| 查个股所属行业/板块（申万行业等） | `westock profile <代码>`（支持批量） | ⚠️ **不是** `westock sector constituent`！`constituent` 是「板块→成份股」，方向相反 |
| 单板块估值精查 | `westock sector valuation <pt代码>`（`--date` 指定日） | 仅板块代码；产业概念自动 merge 5 张估值表；**不支持** `--start`/`--end` 区间 |
| 申万行业未来盈利预测 | `westock sector forecast <pt代码>` | 仅 sw1/sw2 申万行业；聚源概念/地域/三级会明确报错；个股一致预期用 `westock consensus` |
| 申万行业财务截面 | `westock sector finance <pt>`（`--date` 指定日） | sw1/sw2/sw3；**不支持** `--start`/`--end` 区间；非个股 `westock finance`；**不支持聚源概念/地域板块** |
| 查询行业经营数据（如"煤炭行业的产量、价格如何"） | `westock sector oper <行业名称或标识>` | 用中文名称（如 `煤炭`）或标识（如 `coal`）；**不要**传板块代码 `pt*`；`--date` 指定查询日期；`--list` 列出全部 |
| 查个股北向季度持仓（持股市值/持股比例/季年变动） | `westock fund north-holding <代码>` 或 `westock fund north-holding <代码1>,<代码2>` | 同时返回最新季 + 次新季；个股支持逗号批量；与日度 `westock fund flow` 不同 |
| 查港股南下资金持仓（持有比例/日季变动） | `westock fund south-holding <港股代码>` | 仅 `hk` 前缀；不要用 `westock north-holding` |
| 查申万行业北向资金持仓分布 | `westock fund north-holding <板块代码>`（`pt…`） | 仅支持申万 sw1/sw2/sw3 行业，不支持概念/地域板块 |
---

## 五、新闻检索、公告和研报对照

**所有新闻直接使用 `web_search`，不以时间、市场或标的类型决定是否先用 Westock。** 新闻查询不要求证券代码、指数代码或新闻 ID；仅在同时查询行情等数据时，才为对应结构化命令解析代码。

| 需求 | 来源或完整命令 | 执行边界 |
|---|---|---|
| 近期个股、板块、市场等证券资讯 | `web_search` | 按主体、主题和时间检索，核对实际发布时间 |
| 指定历史日期或区间、历史事件回溯 | `web_search` | 不用最新报道替代历史证据 |
| 热门新闻、财经热点 | `web_search` | 搜索结果排序不是特定平台热文榜，不虚构热度排名 |
| 产品动态、企业经营背景、行业报道 | `web_search` | 不要求先搜索证券代码 |
| 公告列表与原文 | `westock notice list`、`westock notice detail` | 专用入口不变，实际执行需带代码或公告 ID |
| 券商研报列表与原文 | `westock report list`、`westock report detail` | 按命令要求传个股、行业代码或研报 ID |
| 脱水研报列表与原文 | `westock dehydrated list`、`westock dehydrated detail` | 详情使用真实研报 ID |
| 个股事件标签 | `westock events` | 结构化标签查询，不等于新闻检索 |

- **关键正文必须核验**：用于摘要、事件判断或涨跌解释的报道须阅读公开原文，不能以标题、搜索摘要或转载次数代替事实证据。仅列标题与元数据时可不逐篇读正文，但须注明未核验；原文不可访问时保留缺口。
- **核对时间与主体**：区分发布/更新时间和事件发生时间，排除同名主体及重复转载；复盘某时点时区分当时已知信息与事后报道。检索结果不保证穷尽指定区间的全部新闻。
- **失败不回退 CLI 新闻**：`web_search` 不可用或没有可靠原文时，说明缺口，不以旧新闻入口、训练记忆或未经核验的摘要补写事实。
- **混合研究分别溯源**：行情、财报、宏观数值及筛选继续先走 Westock，真实缺口按第二节降级；新闻单独注明发布方、日期和原文链接，不标成 Westock 数据。

---

## 六、能力差异速查（标的 × 维度）

| 限制项 | 说明 |
|---|---|
| 风险事件（`westock risk`） | 仅支持 A 股（sh/sz/bj），港股美股不支持；港美股查询时应明确告知用户 |
| 全市场风险筛选 | `westock risk` 是单股查询；全市场扫 **ST 股**用 `westock screen label --type risk_st `；高质押率/高解禁等事件类筛选用 `westock screen event`；排行榜（如两融余额最高）用 `westock screen ranking` |
| 龙虎榜（`westock lhb`） | 仅支持 A 股 |
| 大宗交易/融资融券 | 仅支持沪深市场（sh/sz） |
| 资金流向（`westock fund flow`） | 美股**不支持** `westock fund flow`，仅支持 `westock fund short`（卖空） |
| 北向季度持仓（`westock fund north-holding`） | 仅支持 A 股个股（sh/sz/bj）+ 申万行业板块代码；**不支持**港股/美股/概念地域板块 |
| 南下资金持仓（`westock fund south-holding`） | 仅支持港股（hk）；与日度 `westock fund flow`、A 股 `westock fund north-holding` 不同 |
| 筹码成本（`westock chip`） | 仅支持沪深京 A 股（sh/sz/bj） |
| 股东结构（`westock shareholder`） | 仅支持 A 股和港股 |
| `westock search` / `westock minute` | 不支持多代码批量；`westock minute` 仅单代码 |
| `westock fund north-holding` | 个股支持逗号批量；板块代码可多只；不可与个股混查 |
| `westock fund south-holding` | 仅港股；支持逗号批量 |
| `westock fund flow` | 可多代码，但**须同一市场**（跨市场须分开查） |
| `westock fund margin` / `westock fund block` | 仅沪深（sh/sz）；支持逗号批量 |
| `westock kline` + 期货 `fu*`/`fx*` | 仅单代码 |
| 期货 | `westock quote`/`westock minute`/`westock kline` 均支持期货代码（`fu*` 外盘/`r_hd*` 港股股指，外盘多为延时）；`hf_*`（LME 金属）仅支持 `westock quote`；不支持复权 |
| 外汇 | `westock quote`/`westock kline`/`westock minute` 均支持外汇代码（`fx*`）；外汇仅提供当日分时（`westock minute --days 5` 无效）；不支持复权 |
| 可转债 | `westock quote`/`westock minute`/`westock kline` 直接支持（沪 `sh11xxxx`/`sh13xxxx`、深 `sz12xxxx`）；`westock quote` 额外返回转债维度（转股价值/溢价率/双低/规模/评级等）；行情接口不返回债券简称（`name` 为空），完整发行要素用 `bond` |
| 日韩股票 | 仅支持搜索（`westock search --market jp\|kr`）与实时行情（`westock quote` 接受 `ks*`/`kq*`/`t*` 代码）；不支持 K线/分时/技术/筹码/资金/财务；货币为韩元/日元 |
| ETF 基金维度 | 仅 sh/sz；**子命令必填** |
| ETF 行情（`westock quote`/`westock kline`） | 支持 ETF 代码 |
| ETF 基金详情 | 用 `westock etf profile/overview/holdings/nav`；不要套用个股财务或筹码入口 |

---

## 七、操作规范

- ✅ 使用 CLI 命令查询数据，输出 Markdown 表格供直接读取
- ✅ 查询结果转表格或可读格式展示，不直接输出原始 JSON
- ❌ 不创建临时脚本文件，不将数据分析逻辑写成独立脚本
- ❌ **未知代码禁止凭记忆**：用户给名称未给代码时，**必须先 `westock search` 拿代码再查行情**
  - 默认搜股票：`westock search <关键词>`（仅返回 A股/港股/美股个股，**不会**跨类型 fan-out）
  - 找其它类型：`westock search <关键词> --type etf|bond|sector|index|futures|forex`
  - 日韩股（独立入口）：`westock search <关键词> --market jp\|kr`
- ⚠️ **货币单位**：港股返回港元/美元，美股返回美元，日韩返回日元/韩元。展示时**必须标注正确货币**，禁用人民币符号

---

## 八、股票代码格式

| 市场 | 格式 | 示例 |
|---|---|---|
| 沪市/科创板 | sh + 6位数字 | `sh600000`、`sh688981` |
| 深市 | sz + 6位数字 | `sz000001` |
| 北交所 | bj + 6位数字 | `bj430047` |
| 港股 | hk + 5位数字 | `hk00700` |
| 港股指数 | hk + 指数代码 | `hkHSI`(恒生) |
| 美股 | us + 代码 | `usAAPL` |
| 美股指数 | us. + 指数代码 | `us.IXIC`(纳斯达克)、`us.INX`(标普500) |
| A 股板块 | pt + 板块代码 | `pt01801081`(半导体) |
| 韩股 | ks/kq + 数字代码 | `ks005930`(三星电子, KS)、`kq` 为 KOSDAQ |
| 日股 | t + 数字代码 | `t7203`(丰田) |

---

## 九、批量查询与通用参数

**大部分查询类命令均支持逗号分隔批量**（含跨市场混合）：

```bash
westock quote sh600000                                    # 单股
westock quote sh600000,sz000001,hk00700,usAAPL            # 批量（混合市场）
westock finance sh600519,sz000651 --type income --limit 4             # 同市场批量，只取所需表
westock finance hk00700 --type income --limit 4                      # 港股另组，跨市场再对齐期间/币种
westock consensus sz300750,hk00700                        # 一致预期批量（A+H 混合）
westock risk sh600000,sz000001,sh600036                   # 风险事件批量
westock index constituent sh000300,hkHSI                  # 指数成份批量
westock sector constituent pt01801080,pt01801780          # 板块成份批量
westock sector info pt01801080,pt01801780                 # 板块信息批量
westock sector valuation pt01801080,pt01801780            # 板块估值截面批量

```

⚠️ **路由原则**：

- 对比多标的时，支持批量的命令使用逗号多代码；跨市场是否可混查按命令判断。跨市场财务比较必须对齐币种、报表期和指标口径，不把同名字段直接视为可比。
- ❌ **禁止「部分批量、部分单股」**——例如 `westock finance sh600519,sz000651` 已批量，却又把 `westock kline`/`westock technical` 拆成两次单股调用；凡 [§六](#六能力差异速查标的--维度) 未列为例外的命令，对比场景一律批量
- ❌ **不要拆成多条独立命令再人工拼接**——同一命令分多次调用浪费 token、断言可能判错；批量返回还能保证字段对齐
- ❌ **不要用 shell `&&`/并行进程**调多条同类命令——直接逗号分隔
- ⚠️ **不支持代码批量**见 [§六能力差异](#六能力差异速查标的--维度) 表格；**支持批量**的常见命令：

```bash
westock quote sh600000,sz000001,hk00700,usAAPL
westock finance sh600519,sz000651 --limit 4
westock finance sh600519,hk00700 --type income --limit 4
westock consensus sz300750,hk00700
westock risk sh600000,sz000001,sh600036
westock index constituent sh000300,hkHSI
westock sector constituent pt01801080,pt01801780
westock sector info pt01801080,pt01801780

```

- ⚠️ 全市场/无代码参数命令（`westock hot`、`westock calendar`、`westock ipo`、`westock market-overview`、`westock lhb` 等）及 `westock search`/`westock minute` 不适用代码批量

**常见参数名（不代表所有命令支持）**：

| 参数 | 适用范围 | 说明 |
|---|---|---|
| `--help` / `-h` | 目标命令 | 有具体疑问时查看参数 |
| `--raw` | 全局 | 严格 JSON 输出；多 section 按返回结构读取 |
| `--date YYYY-MM-DD` | 仅支持单日的命令 | 默认日期按命令区分 |
| `--start` / `--end` | 仅支持区间的命令 | 数据日期通常 YYYY-MM-DD；宏观部分模式按年份 |
| `--limit N` / `--offset N` | 仅支持条数/分页的命令 | `condition` 无 offset；固定榜单另有限制 |

> 命令专属参数（如 `--type` / `--period` / `--fq` / `--exchange` 等）见 [commands.md](./commands.md) 对应章节，或运行 `westock <命令> --help` 查看。**同名参数在不同命令下语义可能不同**（例如 `--type` 在 `westock finance`、`westock search`、`westock calendar`、`westock market-overview` 下各异），以单条命令的 `--help` 为准。

详细返回字段见 [ai_usage_guide.md](./ai_usage_guide.md)。
