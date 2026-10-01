# WeStock Data - 详细命令用法 · 分册 01

[本手册索引](commands.md) · [技能入口](../../SKILL.md)

> 仅查当前需要的章节；示例和分析模板不增加用户条件。遵循入口的停止规则，默认文字回答，仅明确要求文件时创建文件。

# WeStock Data - 详细命令用法

> 本文档包含所有命令的完整语法、参数说明、使用示例。
> 按功能分组组织，便于快速查找。
>
> **调用与降级**：命中能力时先正确调用对应 Westock 命令；接口异常、覆盖不足或字段缺失导致仍取不到数据时，按 [入口缺口处理](../../SKILL.md#5-缺口处理停止该分支不无限换源) 使用 `web_search` 定向补缺，保留成功结果并标明来源、日期和口径差异。正常无匹配或尚未披露不是接口失败；降级不代表本命令新增参数或扩大支持范围。

> ⚙️ **示例约定**：统一 CLI，格式为 `westock <子命令> [参数]`。

> 📌 **配套文档**：
> - 路由规则、高频意图对照、能力差异速查 → [routing-guide.md](./routing-guide.md)
> - 完整分析场景模板 → [scenarios-guide.md](./scenarios-guide.md)
> - 返回字段说明 → [ai_usage_guide.md](./ai_usage_guide.md)
>
---

## 一、行情

> 价格序列（`westock quote`/`westock kline`/`westock minute`）。技术分析见下节（`westock technical`/`westock chip`）。

### 实时行情与 K 线

```bash
westock search 腾讯控股                    # 默认仅搜股票（A股/港股/美股，排除 ETF/可转债/板块/指数等）
westock search 沪深300 --type etf          # 搜索 ETF
westock search 银行 --type sector          # 搜索板块
westock search 黄金 --type futures         # 搜索期货
westock search 离岸 --type forex           # 搜索外汇
westock search 三星电子 --market kr        # 日韩股专用入口（独立于 --type）
westock quote sh600000                    # 实时行情（个股/指数/板块/ETF）
westock quote sh600000 --date 2026-03-20  # 指定历史日行情（涨跌幅/量比/收盘价等，见 ai_usage_guide.md）
westock quote ks005930,t7203              # 日韩股票实时行情（韩股 ks/kq、日股 t，支持批量）
westock kline sh600000 --period day --limit 20    # K线（m1/m5/m15/m30/m60/m120/day/week/month/season/year）
westock kline sz000001 --period day --limit 60 --fq qfq    # 复权（qfq/hfq/bfq，默认不复权；指数/板块/港股/美股/可转债强制不复权）
westock kline sh600000 --start 2025-01-01 --end 2025-12-31    # 按日期范围查K（优先级高于 --limit）
westock kline sh600000 --start 2025-06-01                     # 仅指定起始日（end=今天）
westock minute sh600000 --days 5          # 分时（1~5日）

```

> 实时行情按市场差异化：A股含涨跌停价/每手/股息TTM；港股含每手/ADR；美股含盘前盘后/EPS TTM。`westock search`/`westock minute` 不支持多代码批量；`westock fund flow` 跨市场须分开查。完整列表见 [SKILL.md](../../SKILL.md) 或 [routing-guide.md §六/§九](./routing-guide.md)。
> **K线日期范围**：`westock kline` 支持 `--start` / `--end`（YYYY-MM-DD），优先级高于 `--limit`；范围模式下 `--limit` 仅作为返回条数上限保护，默认放宽到 2000。仅指定 `--start` 时 `end` 默认今天；仅指定 `--end` 时自动按周期回溯一段窗口。**期货/外汇 K 线暂不支持日期范围**，传入会自动降级到 `--limit` 模式并提示。
> **统一 `westock search`**：**默认仅搜股票**（A股/港股/美股个股）；用 `--type etf|bond|sector|index|futures|forex` 切换到其它类型，`--type` 支持**逗号分隔多个类型同时搜**（如 `--type etf,index,sector`，按类型分组输出）；日韩股用独立 `--market jp|kr` 入口。⚠️ **港股/美股/沪深不要加 `--market`**（默认搜索已覆盖），`--market` 仅接受 `jp|kr`，传 `hk`/`us`/`hs` 会报错。
> **日韩股票**：`westock quote` 支持韩股 `ks*`/`kq*`（如 `ks005930` 三星电子）、日股 `t*`（如 `t7203` 丰田），可批量；仅支持搜索与实时行情，**不支持** K线/分时/技术指标/筹码等；行情源不直接返回涨跌额/涨跌幅（由最新价与昨收自算），货币为韩元/日元，展示时禁用人民币符号；代码请先用 `westock search --market jp|kr` 获取（日韩股使用独立 `--market` 入口，不归在 `--type` 下）。

---

## 二、技术分析

> 衍生指标与筹码分布（`westock technical`/`westock chip`）。与原始行情数据不同，均为量价推算的分析结果。

### 技术指标与筹码

```bash
westock technical sh600000                                       # 日K技术指标（默认全量 MA/MACD/KDJ/RSI/BOLL）
westock technical sh600000 --period week                         # 周K技术指标
westock technical sh600000 --period month --limit 12             # 月K近12期
westock technical sh600000 --start 2026-02-01 --end 2026-03-01 --limit 30    # 历史区间
westock technical sh600519,sz000001                      # 多股对比
westock chip sh600519                                            # 筹码成本（仅沪深京A股）
```

> 技术指标输出截面或历史区间数据；筹码成本仅支持沪深京A股，用于分析获利盘/套牢盘比例。

---

## 四、市场

> 全市场截面/总览/互联互通。含龙虎榜、市场总览（A 股大盘画像）、涨跌分布、沪深港通成份股。

### 龙虎榜（仅A股）

```bash
westock lhb --type institution,hotmoney    # 龙虎榜（机构榜/游资榜/活跃席位/高胜率买入/高胜率席位）
westock lhb --type activeseat --date 2026-03-20

```

> 龙虎榜仅支持A股。

> ⚠️ **一级 `lhb` vs `fund lhb` 差异**：`westock lhb`（本段）＝ **全市场龙虎榜榜单**，按 `--type`（机构榜/游资榜/活跃席位等）筛选，**不带个股代码**；`westock fund lhb <代码>`（见 §九 资金）＝ **指定个股**的龙虎榜明细（成交统计 `LhbInfos` + 营业部买卖 `LhbTradingDetails`）。二者不要混用。

### 市场总览（A 股大盘画像）

> `westock market-overview` 是 A 股大盘的"宏观体检"：8个维度（画像总评/收盘/区间/技术/涨跌分布/两融/估值/风格）共用同一组 `market_statis_*` 后端清单。
> 不带 type 时默认输出 **summary 画像总评**（14 维度得分 + 状态文案，含估值/情绪/技术/趋势/风格轮动等），
> 是给 LLM 做"市场点评"最直接的入口。

```bash
westock market-overview                                          # 默认 = summary（市场画像总评）
westock market-overview --type trade                             # 三大指数收盘统计 + 两市成交额多周期均值
westock market-overview --type interval                          # 三大指数 5/10/20/60/120/250D 涨跌 + 52W 高低
westock market-overview --type technical                         # 大盘 MACD/KDJ/RSI/BOLL/MA + 神奇九转
westock market-overview --type updown                            # A 股涨跌停/红绿盘/多周期新高新低数
westock market-overview --type margin                            # 两融余额多周期变动
westock market-overview --type valuation                         # 中证全指 PE/PB/PS + 历史百分位（数据通常滞后 1~4 个交易日）
westock market-overview --type rotation                          # 沪深300/中证1000/成长/价值 风格轮动
westock market-overview --type technical,updown                  # 多类一次拉
westock market-overview --type all --date 2026-05-18             # 全部 8 类
westock market-overview list                                     # 列出全部 type

```

### 沪深港通成份股（互联互通）

```bash
westock connect --exchange sh                              # 沪股通成份股（北向 / 陆股通标的池）
westock connect --exchange sz --limit 50 --offset 50       # 深股通成份股（统一用 --limit/--offset 分页）

```

> ⚠️ **职责边界**：`westock connect` = 沪深港通**标的池**（标的列表）；`westock fund flow sh600000` = 北向资金流量（金额数据）；二者不要混用。

### 新股日历

```bash
westock ipo --market hs                    # 新股日历（--market hs/hk/us）

```

> 新股日历查询新股申购与上市信息，支持沪深/港股/美股三个市场。

### A 股交易日历

```bash
westock trade-calendar                                    # 默认当月
westock trade-calendar --date 2026-06-09                  # 单日是否交易日
westock trade-calendar --start 2026-06-01 --end 2026-06-30  # 区间
westock trade-calendar --year 2026 --trading-only         # 全年仅交易日

```

> ⚠️ **`westock trade-calendar` vs `westock calendar`**：`westock trade-calendar` 查**交易所开市/休市**（清单 `calendar_hsj`）；`westock calendar` 查**个股投资事件**（分红/财报/新股等）。二者不可混用。

### 市场涨跌分布

```bash
westock changedist                         # 沪深A股涨跌分布（涨跌/涨跌停/停牌家数 + 上涨占比情绪 + 涨跌幅区间分布 + 两市成交额）

```

> 涨跌分布为沪深A股全市场截面（实时）：概览含上涨/下跌/平盘、涨停/跌停、停牌家数与上涨占比情绪文案；明细为 11 个涨跌幅区间（涨停→>7%→…→平→…→跌停）的家数分布，并附两市成交额及其较上日变动。

---

## 五、指数

> 指数清单、搜索与成份股（A 股 + 港股）。行情/K 线/分时复用 `westock quote` / `westock kline` / `westock minute`。

```bash
westock index constituent sh000300        # A股指数成份股
westock index constituent hkHSI           # 港股指数成份股（恒生指数）
westock index constituent hkHSCEI,hkHSTECH # 多个港股指数
westock index list                         # 指数清单（支持 --limit/--offset 分页）
westock search 沪深300 --type index        # 搜索指数（统一 search 入口）

```

**常用指数**：`sh000001`(上证)、`sz399001`(深证成指)、`sz399006`(创业板)、`hkHSI`(恒生)、`us.IXIC`(纳斯达克)、`us.INX`(标普500)

---

## 六、板块

> 板块/概念股查询（搜索/成份股/信息/行情榜/经营/估值）。

### 板块成份股（含概念股查询）

> ⚠️ **概念股查询**："华为概念股"、"AI 概念股"等问法 → 用 `westock search <关键词> --type sector` → `westock sector constituent <代码>` 两步查询。

```bash
westock search 华为 --type sector            # 搜索板块代码（华为/AI/新能源等概念）
westock sector constituent pt01801080        # 板块成份股

```

> **板块代码**：使用 `westock search --type sector` 返回的 code（如 `pt01801080`、`pt02GN2328`）。

> **`westock sector constituent <代码>` vs `westock sector info <代码>`**：
> - `westock sector constituent <代码>`：返回板块**全部成份股**（含 SectorCode 字段，可逐只展开分析）
> - `westock sector info <代码>`：返回板块**基础信息 + 区间交易数据**（名称、板块类型、成份股数量、区间涨跌幅、区间成交额等）。**不含成份股**，适合用户问"XX板块怎么样"等总览类问题。
>
> ⚠️ **查个股所属行业/板块**（如"茅台属于哪个板块"）→ 用 `westock profile <代码>`，**不要**用 `westock sector constituent`（方向相反，且不接受 sh/sz 个股代码）。

### 行业经营数据（价格/产量/销量等）

> 查询各行业经营指标的历史序列数据，覆盖20+行业。数据包括价格、产量、销量、收入等经营指标。

```bash
westock sector oper 煤炭
westock sector oper 煤炭 --date 2026-06-15
westock sector oper --list               # 列出所有支持经营数据的行业

```

> **行业标识**（非板块代码 pt*）：`media`(传媒) / `elec`(电力设备) / `eltn`(电子) / `re`(房地产) / `text`(纺织服饰) / `nbfin`(非银金融) / `steel`(钢铁) / `utils`(公用事业) / `dfnse`(国防军工) / `env`(环保) / `mach`(机械设备) / `chem`(基础化工) / `comp`(计算机) / `happl`(家用电器) / `bmat`(建筑材料) / `bldg`(建筑装饰) / `trans`(交通运输) / `coal`(煤炭) / `cosm`(美容护理) / `agri`(农林牧渔) / `auto`(汽车) / `trade`(商贸零售) / `socsv`(社会服务) / `petro`(石油石化) / `food`(食品饮料) / `comm`(通信) / `pharm`(医药生物) / `bank`(银行) / `metal`(有色金属)

> **参数说明**：
> - `<行业>`：支持中文名称（如"煤炭"）或标识（如 `coal`），**不要**传板块代码（如 `pt02021291`）
> - `--list`/`-l`：列出所有支持经营数据的行业
> - `--date`：查询日期 YYYY-MM-DD（默认今天）

---

### 板块行情榜（涨幅 / 资金流入）

```bash
westock sector ranking                     # 板块行情榜（行业涨幅 Top10 + 概念涨幅 Top10 + 行业资金流入 Top5 + 北向热门板块）

```

> **`westock sector ranking` vs `westock sector constituent/info` vs `westock hot sector` 区分**：
> - `westock sector ranking`：**全市场板块行情榜**（行业涨幅 + 概念涨幅 + 资金流入 + 北向热门），用于"今天哪些板块在涨/资金在流入"类问题
> - `westock sector constituent/info`：**按代码精查**（成份股 / 画像 / 区间交易），用于"消费板块成份股有哪些 / 半导体板块怎么样"类问题
> - `westock hot sector`（hot 子命令）：板块**热度**排名（搜索/讨论度），用于"哪些板块最火"类问题
> - 决策入口：泛问"市场上哪些板块涨得多/资金流向" → `westock sector ranking`；指定"XX 板块的成份股/画像" → `westock sector constituent/info`；问"哪些板块最热" → `westock hot sector`

### 板块估值（PE/PB/PS/PCF/DIV + 历史百分位）

```bash
westock sector valuation pt01801080
westock sector valuation pt01801080,pt01801081
westock sector valuation pt01801080 --date 2026-06-25

```

> **参数说明**：
> - 仅支持 **板块代码**（`pt*`）
> - `--date`：查询日期（默认今天）；**不支持** `--start`/`--end` 区间

### 行业未来盈利预测

```bash
westock sector forecast pt01801780
westock sector forecast pt01801780,pt01801081
westock sector forecast pt01801780 --date 2026-06-25

```

> **参数说明**：
> - 仅支持 **申万一级/二级行业**板块代码（`pt*`）
> - 输出未来 3 年一致预期表，列含 `year | revenue | netProfit | netAssets | revenueYoy | netProfitYoy | netProfitCagr2Y | pe | pb | ps | roe | peg`（字段说明见 `ai_usage_guide.md` §sector forecast）

### 行业财务指标

```bash
westock sector finance pt01801780
westock sector finance pt01801780,pt01801080
westock sector finance pt01801780 --date 2026-03-31

```

> **参数说明**：
> - 支持申万 **一级/二级/三级**行业（`pt*`）
> - `--date`：查询日期（默认最新财务截面）；**不支持** `--start`/`--end` 区间
> - 聚源概念/地域不支持；字段说明见 `ai_usage_guide.md` §sector finance

---

## 七、研究

> 评分/评级/一致预期/研报/脱水研报。覆盖个股的多维度评估视角。

### 评估与研究

```bash
westock score sh600519                        # 个股评分（综合/资金/基本面/风险/技术 + 周/月/季变动）
                                                   # ↑ 单股查询；评分排行选股请用 westock screen ranking --type CompScore 
westock esg sh600519                          # ESG 评级（默认中证+聚源双源）
westock esg sh600519 --source csi             # 仅中证 ESG
westock rating hk00700                       # 机构评级（港股/美股，3段：目标价&评级 / 评级月度趋势 / 价格 vs 目标价）
westock consensus sh600519                    # 一致预期（A股、港股，自动分发）
westock report list sh600000 --limit 20       # 个股研报列表
westock report list pt01801080 --limit 20     # 行业/板块研报列表（支持个股代码与行业代码）
westock report detail <研报ID>                # 研报详情（ID 从研报列表获取）
westock dehydrated                         # 脱水研报列表
westock dehydrated detail 1056             # 脱水研报详情

```

> **`westock report` 命令使用流程**：
> ⚠️ `report` **仅支持 `list` / `detail` 两个子命令**。机构评级、一致预期是**独立顶层命令**，**不要**写成 `report rating` / `report consensus`：
> - 机构评级：`westock rating <代码>`（港股/美股，如 `westock rating hk00700`）
> - 一致预期：`westock consensus <代码>`（A股/港股，如 `westock consensus sh600519`）
> 1. 先通过 `westock report list sh600000`（个股）或 `westock report list pt01801080`（行业）获取研报列表
> 2. 从列表中复制研报 ID（如 `res832471322631`）
> 3. 使用 `westock report detail res832471322631` 查看完整研报内容

---

## 八、事件

> 事件标签/风险事件/投资日历/停复牌。覆盖个股的事件监控、风险明细与交易状态。

### 事件总览（42 类标签）

> **`westock risk` vs `westock events` 决策入口**：
> - 用户**泛问**"XX 公司有什么风险/事件" → **优先 `westock events`**（看全貌，标签化输出，覆盖中性+利好+风险 42 类）
> - 用户**指定**风险细节（如"质押率"、"诉讼明细"、"解禁规模"） → 用 `westock risk --types <类型>`（含明细字段，仅 8 类）
> - 二者关系：`westock events` 是入口与速览，`westock risk` 是钻取与细查；先 events 后 risk 是常规链路

```bash
westock events sh600519                  # 单股事件标签
westock events sh600519,sz000001         # 批量

```

**事件大类**（共 9 组 42 类）：交易异动（大宗/龙虎榜）、股本变动（回购/定增/分红）、业绩披露（快报/预告/财报）、指数变动（纳入/剔除）、董监高（变动/增减持）、股权事件（股东大会/重组/更名/要约）、限售解禁、法律处罚、停复牌。完整ID→中文映射按[数据字段索引](./ai_usage_guide.md)定位事件总览章节。

### 投资日历

查询个股事件日历，按事件类型分组输出。宏观经济日历请使用 `westock macro indicator cn_calendar_future|cn_calendar_hist`。

```bash
westock calendar                                          # 今天所有类型事件
westock calendar --date 2026-06-04                      # 指定日期
westock calendar --event dividend                          # 只看分红派息
westock calendar --event financial_report --market hs     # 财报发布（沪深）
westock calendar --event ipo --market hk                # 新股发行（港股）
westock calendar --event trading_halt,meeting,lockup_release  # 多类型（逗号分隔）
westock calendar --event all --market us --limit 30     # 美股所有事件，限制30条

```

**参数说明**：

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| `--date` | 查询日期 YYYY-MM-DD | 今天 |
| `--event` | 事件类型过滤，可选值见下表 | `all` |
| `--market` | 市场：`hs`（沪深）/ `hk`（港股）/ `us`（美股） | `hs` |
| `--limit` | 返回条数 | 10 |

**`--event` 可选值**：

| 英文术语 | 中文标签 | API 短码 |
| --- | --- | --- |
| `financial_report` | 财报发布 | cbfb |
| `westock dividend` | 分红派息 | fh |
| `westock ipo` | 新股发行 | xg |
| `trading_halt` | 停复牌 | tfp |
| `meeting` | 会议 | hy |
| `lockup_release` | 限售解禁 | jj |
| `rights_issue` | 增发 | zf |
| `all` | 全部（不筛选） | all |

> 输出按中文标签分组（财报发布/分红派息/新股发行/停复牌/会议/限售解禁/增发）。

### 风险事件（仅A股，8 种类型）

```bash
westock risk sh600000                            # 全部风险事件
westock risk sz000001 --types pledge,unlock      # 仅指定类型
westock risk sh600000,sz000001 --types pledge    # 批量

```

**8 种类型**：`specialtrade`(ST)、`pledge`(质押)、`unlock`(解禁)、`lawsuit`(诉讼)、`seasonedissue`(增发)、`leaderchange`(高管变动)、`executivetransfer`(高管增减持)、`bondrating`(评级)。

**别名**：`st`/`special`→specialtrade、`addition`→seasonedissue、`leader`→leaderchange、`executive`→executivetransfer、`westock rating`→bondrating。

> 无效代码或无风险事件的股票会输出"暂无风险事件"。

### 停复牌信息

```bash
westock suspension --market hs             # 停复牌信息（--market hs/hk/us）

```

---

## 九、资讯

### 新闻检索

所有新闻直接使用 `web_search`，包括近期个股、指数、板块、期货、外汇新闻、历史回溯、热门新闻及开放资讯；不再提供 CLI 新闻调用流程，也无需先查证券代码或新闻 ID。按主体、主题及目标时间检索，关键报道必须阅读公开原文并注明来源和日期；搜索摘要不能代替正文，也不能把搜索结果的顺序当作 Westock 热文榜排名。具体流程见 [路由指南](./routing-guide.md) 与 [场景指南](./scenarios-guide.md)。

### 公告查询

公告和研报保留专用命令；报道提及公告不等于获取了公告原文。以下为公告示例，详情 ID 必须替换为列表实际返回值。

```bash
westock notice list sh600000 --type 1              # 公告列表（--type：0全部/1财务/2配股/3增发/4股权变动/5重大/6风险/7其他）
westock notice detail nos1224809143                # 公告全文（nos沪深→纯文本；nok港股/nou美股→PDF URL）

```

---

## 十、资金

> 二级市场资金数据。含个股资金、卖空数据、融资融券、大宗交易、北向资金持仓。

