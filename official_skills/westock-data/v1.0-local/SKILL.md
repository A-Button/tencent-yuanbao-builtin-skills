---
name: westock-data
description: 查询金融市场数据（行情/财务/资金/新闻等）。覆盖标的：股票（A股/港股/美股/日韩股）、ETF、指数、板块、期货、外汇、可转债。覆盖维度：实时行情、K线/分时、技术指标、筹码、财务报表、资金流向、机构评级与一致预期、研报/脱水研报、新闻/公告、事件标签与风险事件、股东、分红、回购、ETF持仓与净值、宏观经济、市场资讯（热搜/股单/新股/投资日历）等。当用户问"看一下/查一下/怎么样/最新行情/数据"等单标的或市场数据问题时使用。各标的与市场支持的维度有差异，详见正文「已知限制速查」。本技能只做数据查询；按条件/策略/标签筛选股票（选股/找股票）请用 westock-tool。
---

# WeStock Data

**数据源**：腾讯自选股行情数据接口 | **支持市场**：A股（沪深/科创/北交所）、港股、美股、外盘期货（CME/COMEX/CBOT/NYMEX/LME 等）、港股股指期货、外汇（离岸人民币/主要货币对/美元指数）

## 目录与路径约定

任务开始时先确定，占位符必须替换为真实绝对路径：

- `WORK_DIR="<当前工作目录的真实绝对路径>"`：用户工作区，只存放用户明确要求导出的最终文件。
- `RUN="<系统临时目录的真实绝对路径>/westock_data_runs/<run_id>"`：需要暂存查询结果时使用的运行目录；直接查询并回答时无需创建。
- `<run_id>` 使用查询主题短名；每个独立交付使用新的 `<run_id>`，同一查询的迭代复用原 `$RUN`。
- 禁止在 skill 目录下创建文件；不得把 `$RUN` 内的路径作为最终交付路径。

**环境依赖故障处理**：当某条脚本命令因依赖缺失失败（`ModuleNotFoundError`、`ImportError`、`command not found` 等）时，执行一次 `python $YB_SKILL_PATH/westock-data/scripts/ensure_deps.py`，然后**重试原命令一次**。全任务 `ensure_deps` 最多执行一次；补齐后仍失败，则停止并向用户报告，不要循环重试。

---

## ⚙️ 命令调用约定

> 下文示例统一写作 `westock-data <命令>`，这是**逻辑命令名**，并非可执行程序。实际执行规则如下：
>
> - **执行方式**：`node $YB_SKILL_PATH/westock-data/scripts/index.js <命令> [参数]`
> - **禁止**：硬编码任何具体安装路径（如 `~/.openclaw/skills/...`、`/usr/local/...` 等），各运行环境通过 `$YB_SKILL_PATH` 定位
> - **环境**：Node.js v20.19.5，脚本已单文件打包，无需 `npm install`

---

## 功能分组速览

> 下表为快速索引（按功能域分组）。**执行具体命令前的标准流程：先执行 `westock-data help`（人类可读）或 `westock-data help --raw`（JSON）确认命令清单，再读 [references/commands.md](./references/commands.md) 查参数** —— help 输出直接来自 CLI 命令注册表，与代码实时一致，可防文档过时。

| 分组 | 用途 | 命令 |
| --- | --- | --- |
| 行情 | 价格序列/技术指标/筹码 | `quote` `minute` `kline` `technical` `chip` |
| 市场 | 全市场截面/总览/指数/互联互通/新股/涨跌分布 | `lhb` `index` `market-overview` `connect` `ipo` `changedist` |
| 板块 | 板块清单/搜索/成份股/信息/行情榜 | `sector list/search/constituent/info/ranking` |
| 研究 | 评分/评级/预期/研报/脱水研报 | `score` `rating` `consensus` `report` `dehydrated` |
| 事件 | 事件标签/风险事件/投资日历/停复牌 | `events list/tags` `risk` `calendar` `suspension` |
| 资讯 | 新闻、公告、原文 | `news article/market/detail` `notice list/detail` |
| 资金 | 二级市场资金 | `fund flow` `fund short/margin/block` |
| 简况 | 公司基本信息/股东/分红/回购 | `profile` `shareholder` `dividend list/calendar` `buyback` |
| 财务 | 三大报表/财报披露日历 | `finance` `disclosure` |
| ETF | ETF 全维度 | `etf detail/holdings/nav/company/holders/financial` |
| 发现 | 搜索/热搜/股单 | `search` `hot stock/wechat/news/board/etf` `stocklist rank/detail` |
| 宏观 | 宏观指标 | `macro list/indicator` |
| 期货 | 外盘商品/金融期货 + 港股股指期货 | `futures search/detail`（行情用 `quote`） |
| 外汇 | 离岸人民币/主要货币对/美元指数 | `forex search/list`（行情用 `quote`） |
| 债券 | 可转债/可交换债详情 | `bond detail`（行情用 `quote`/`minute`/`kline`） |

**核心定位提示**：
- **"行情序列" vs "市场截面"**：`quote`/`kline`/`minute`/`technical`/`chip` 是单标的时序数据；`lhb`/`market-overview`/`index` 是全市场截面
- **"研究" vs "事件"**：`研究` 组（score/rating/consensus/report）是多维度评估与研究；`事件` 组（events/risk）是个股事件标签与风险监控
- **"事件标签速览" vs "风险事件细查"**：`events`（42 类全场景标签速览） vs `risk`（8 类风险事件 + 字段细查，仅 A 股）
- **"资金" vs "财务"**：`fund` 是二级市场资金流向；`finance`/`disclosure` 是财务报表与披露日历
- **"板块"独立分组**：`sector` 专用于板块/概念股查询（清单/搜索/成份股/画像），与 `index`（指数）和 `search`（股票搜索）职责分离
- **期货**：先用 `futures search 关键词` 拿合约代码（如 `fuGC`/`hf_CAD`/`r_hdHSImain`），再用 `quote <代码>` 查行情、`futures detail <代码>` 查合约资料
- **外汇**：先用 `forex search 关键词`/`forex list` 拿品种代码（如 `fxCNH`/`fxUSDJPY`/`fxDINIW`），再用 `quote <代码>` 查行情、`kline <代码>` 查K线、`minute <代码>` 查当日分时
- **可转债**：行情/分时/K线直接用 `quote`/`minute`/`kline`（代码沿用沪 `sh11xxxx`/`sh13xxxx`、深 `sz12xxxx`，无需特殊命令）。`quote` 对可转债除通用价格/成交字段外，额外返回**转债维度**（转股价值/纯债价值、转股/纯债溢价率、双低、总规模/剩余规模、评级、期限/到期日/到期收益率、是否转股/转股价、赎回回售触发价、正股代码/正股 PB），单只查询时以竖排「项目/内容」表展示；发行/评级/期限利率/转股/赎回回售等完整要素用 `bond detail <代码>`（`--terms` 看条款全文、`--schedule` 看利率变动/现金流/赎回回售明细）
- **日韩股票**：先用 `search 关键词 --market jp|kr` 拿统一前缀代码（韩股 `ks*`/`kq*`，日股 `t*`，如 `ks005930`/`t7203`），再用 `quote <代码[,代码...]>` 查实时行情（支持批量）。仅支持搜索与实时行情两类查询，**不支持** K线/分时/技术指标/筹码等；货币为韩元/日元，展示时禁用人民币符号

**与其它 skill 的边界（避免选错 skill）**：

- **「哪天有什么事」用本 skill 的日历，不要用 `westock-tool`**：查"某天的财报发布/新股发行/分红派息/停复牌/股东大会"等**日历型事件** → 用本 skill `calendar`（如 `calendar --type stock --event financial_report --market hs`）；`westock-tool event` 是按**事件筛选股票**（选股），语义不同，不要混用。
- **「最近有哪些新股」用本 skill 的 `ipo`/`calendar`，不要用 `westock-tool`**：查新股**日历/清单**（沪深/港股/美股）→ `ipo --market hs|hk|us` 或 `calendar --event ipo --market hk`；`westock-tool` 的 `label`/`filter` 是选股工具，不负责新股日历。
- **「查某只股票的某项数据」一律优先本 skill**：行情/财务/资金/事件/新闻/板块成份等数据查询都在本 skill；只有**按条件/策略/标签筛选出一批股票**（选股）才用 `westock-tool`，**全市场扫 ST/高质押率** 等筛选用 `westock-tool ranking`。

---

## 已知限制速查

| 限制项 | 说明 |
| --- | --- |
| 风险事件 | 仅支持A股（sh/sz/bj），**港股美股不支持 `risk` 命令**；港股美股查询时应明确告知用户该限制 |
| 全市场风险筛选 | `risk` 是**单股查询**（输入代码取该股事件明细）；想"全市场扫 ST/质押率高的股票"请用 `westock-tool ranking` |
| 龙虎榜 | 仅支持A股 |
| 大宗交易/融资融券 | 仅支持沪深市场（sh/sz） |
| 资金流向（fund flow） | 美股**不支持** `fund flow`，仅支持 `fund short`（卖空数据） |
| 筹码成本 | 仅支持沪深京A股（sh/sz/bj） |
| 股东结构 | 仅支持A股和港股 |
| 货币单位 | 港股返回港元/美元，美股返回美元，展示时必须标注正确货币单位，禁止使用人民币符号 |
| `search`/`minute` | 不支持批量查询 |
| 期货 | `quote`/`minute`/`kline` 均支持期货代码（`fu*` 外盘/`r_hd*` 港股股指，外盘多为**延时行情**）；`hf_*`（LME 金属）仅支持 `quote`；合约资料用 `futures detail`；期货**不支持复权**（资讯可用 `news`） |
| 外汇 | `quote`/`kline`/`minute` 均支持外汇代码（`fx*`）；外汇**仅提供当日分时**（`minute` 的 `--days 5` 对外汇无效，会被忽略并返回当日数据）；外汇**不支持复权**（资讯可用 `news`）；品种代码用 `forex search`/`forex list` 获取 |
| `news` 标的范围 | `news article` 除个股外，还支持指数（`sh000001`）、ETF（`sh510300`）、板块（`pt01801081`）、可转债（`sh113052`）、期货（`fuCL`）、外汇（`fxUSDCNH`）等代码；接口不分页，用 `--limit` 控制返回条数 |
| 可转债 | `quote`/`minute`/`kline` 直接支持可转债代码（沪 `sh11xxxx`/`sh13xxxx`、深 `sz12xxxx`）；`quote` 额外返回**转债维度字段**（转股价值/溢价率/双低/规模/评级/转股/赎回回售/正股 等，单只竖排展示），但行情接口**不返回债券简称**（`name` 为空，可借 `bond detail` 的发行人/正股代码识别）；完整发行要素用 `bond detail`，可交换债及临近到期老券可能缺失部分转股（`Kzz_*`）字段 |
| 日韩股票 | 仅支持**搜索**（`search --market jp\|kr`）与**实时行情**（`quote` 接受 `ks*`/`kq*`/`t*` 代码，支持批量），**不支持** K线/分时/技术指标/筹码/资金/财务等；行情数据源不返回涨跌额/涨跌幅（由最新价与昨收自算）；货币为韩元/日元，禁用人民币符号 |

---

## 批量查询与通用参数

**所有查询类命令均支持逗号分隔多股代码**，返回 Markdown 表格（每个 symbol 独立表格）。

```bash
westock-data quote sh600000                      # 单股
westock-data quote sh600000,sz000001,hk00700     # 批量
```

**通用参数**：

| 参数 | 说明 | 适用命令 |
| --- | --- | --- |
| `--date` | 指定日期 `YYYY-MM-DD`，默认今天 | 资金流向、技术指标、龙虎榜、`calendar` 等 |
| `--start` / `--end` | 区间查询起止日期 | 资金流向、技术指标、筹码、K线等 |
| `--limit` | 返回数量限制 | 大部分查询命令 |
| `--num` | 返回期数（如 `--num 4` 返回最近4期） | finance（财务报表） |
| `--days` | 分时天数（如 `--days 5`） | minute（分时数据） |
| `--tab` | 龙虎榜标签（如 `--tab jg,yzb`） | lhb |
| `--types` | 风险事件类型（如 `--types pledge,unlock`） | risk |
| `--event` | 股票日历事件类型过滤，可选值：`financial_report`/`dividend`/`ipo`/`trading_halt`/`meeting`/`lockup_release`/`rights_issue`/`all`（默认 `all`） | `calendar --type stock` |
| `--raw` | 输出严格 JSON 而非 Markdown 表格（**全局**） | 所有命令 |

> **`--raw` 全局开关**：所有命令通用；带上后输出严格 JSON（多 section 命令自动包成 `{ sections: [...] }`），不带则输出 Markdown 表格。便于程序化消费。

> 详细返回格式、字段说明见 [references/ai_usage_guide.md](./references/ai_usage_guide.md)

---

## 🎯 高频意图 → 精确命令（含关键参数）

> 以下意图容易选错命令或漏掉关键参数，请优先按本表给出的**精确写法**执行（参数名以此为准）。

| 用户意图 | 精确命令（关键参数不可省） | 易错点 |
| --- | --- | --- |
| 某天的财报发布事件（沪深/港/美） | `calendar --type stock --event financial_report --market hs` | 用本 skill `calendar`，**勿用** `westock-tool event`；`--market` 取 `hs/hk/us` |
| 某天的分红派息 / 停复牌 / 股东大会等日历 | `calendar --event dividend\|trading_halt\|meeting --market hs` | `--event` 多类型用逗号分隔 |
| 最近有哪些新股（沪深/港/美） | `ipo --market hs`（或 `calendar --event ipo --market hk`） | **勿用** `westock-tool` 的 label/filter |
| 在指定清单中搜板块（如申万一级里的银行） | `sector search 银行 --scope industry_list_sw1` | 勿用 `sector list` 后自行筛选 |
| 热门财经资讯/热文榜 | `hot news` | `hot` 是热搜命令族，子命令 `stock`/`wechat`/`news`/`board`/`etf` 分别对应热搜股票/微信热股/热文/热门板块/热搜 ETF；找"今日财经热文"用 `hot news` |

---

## 股票代码格式

| 市场 | 格式 | 示例 |
| --- | --- | --- |
| 沪市/科创板 | sh + 6位数字 | `sh600000`、`sh688981` |
| 深市 | sz + 6位数字 | `sz000001` |
| 北交所 | bj + 6位数字 | `bj430047` |
| 港股 | hk + 5位数字 | `hk00700` |
| 港股指数 | hk + 指数代码 | `hkHSI`(恒生) |
| 美股 | us + 代码 | `usAAPL` |
| 美股指数 | us. + 指数代码 | `us.IXIC`(纳斯达克)、`us.INX`(标普500) |
| A股板块 | pt + 板块代码 | `pt01801081`(半导体) |
| 韩股 | ks/kq + 数字代码 | `ks005930`(三星电子,KS)、`kq` 为 KOSDAQ |
| 日股 | t + 数字代码 | `t7203`(丰田) |

---

## 使用规范

- ✅ 使用 CLI 命令查询数据，命令输出 Markdown 表格，AI 直接从表格中读取数据
- ✅ 查询结果应转为表格或可读格式展示，禁止直接输出原始 JSON
- ❌ 不创建临时脚本文件，不将数据分析逻辑写成独立脚本
- ❌ **未知代码禁止凭记忆**：用户给名称（如"宁德时代"）、未给代码时，**必须先 `search` 拿代码再查行情**；股票/ETF/可转债用 `search`，板块/概念股用 `sector search`，日韩股用 `search --market jp\|kr`
- ⚠️ **货币单位**：港股返回港元/美元，美股返回美元，禁止使用人民币符号

---

## 📖 详细文档引用

**当你需要执行具体命令时，必须先读取详细文档**：

1. **命令详细用法** → 读取 [references/commands.md](./references/commands.md)
   - 包含每个命令的完整语法、参数说明、使用示例
   - 按功能分组组织（章节「一」～「十五」），便于快速查找
   - 检索提示：查某分组直接搜章节标题（如 `## 七、资金`）；查某命令搜命令名（如 `westock-data fund`）

2. **分析场景模板** → 读取 [references/scenarios-guide.md](./references/scenarios-guide.md)
   - 包含按功能分组的完整分析场景
   - 每个场景提供命令组合和分析模板
   - 检索提示：文件较大，按场景标题搜索（如 `### 场景` 或关键词），避免整文件加载

3. **返回字段说明** → 读取 [references/ai_usage_guide.md](./references/ai_usage_guide.md)
   - 包含 API 返回字段的详细解释
   - 便于数据解析和展示
   - 检索提示：文件较大，按命令名搜对应小节（小节标题形如 `### 实时行情（\`quote\`）`，可直接搜命令名 `quote`），只读所需片段

**重要**：不要凭记忆使用命令，务必先读取上述文档确认用法！

---

## 重要声明

> ⚠️ **重要声明**：
>
> 1. 本技能仅提供客观市场数据的查询与展示服务，所有返回数据均来源于公开市场信息，不含任何主观分析、投资评级或交易建议。
> 2. 本技能不构成证券投资咨询服务，使用本技能获取的数据不应作为投资决策的唯一依据。
> 3. 数据可能存在延迟，请以交易所官方数据为准。
> 4. 投资有风险，决策需谨慎。如需专业投资建议，请咨询持牌证券投资顾问机构。

**数据来源**：腾讯自选股数据接口
