# 取数 Playbook（westock-data → 四个场景）

## 数据取数：三条通道

- **交互分析 / 异动归因 / 回调正文** → 用 **westock-data**（无依赖的多条查询同轮并行；支持逗号的命令批量成 1 次调用；代码带市场前缀，只给名称先 `westock search`；货币按市场标注，禁用人民币符号）。
- **资讯/公告/研报（场景四）** → **westock news 为主 + web_search 兜底**：westock 覆盖近期、结构化、权威，优先；用户指定较早时间段、历史公告，或 westock 返回不足时，用 web_search 补齐。**仅场景四的资讯类允许 web_search**；行情、K 线、技术、财务、资金等仍一律走 westock，禁 web_search。
- **Judge（Trigger 取数）** → 按工具名调 **`check_anomaly`**。交易时段、量比、涨跌幅都在脚本里算完，`condition` 只认回包 `triggered` 为 true。不要用 `stock_market_data` 自己比阈值。

常用 westock 命令：`quote`（现价/涨跌幅/量比/成交额/PE/市值）、`kline`（K 线）、`technical`（MA/MACD/KDJ/RSI/BOLL）、`fund flow`（主力资金，美股用 `fund short`）、`news list --type`、`report list`、`notice list --type`、`events`、`finance`/`consensus`/`rating`。逐场景配方见 data-recipes.md。

本文件把四个场景要用到的取数命令固化下来，供本 Skill 交互分析、资讯查询、异动归因、回调正文取数时查阅。**行情/K 线/技术/财务/资金类禁止 web_search，一律走 westock**；**仅场景四资讯类允许 westock news + web_search 兜底**。无依赖的多条查询**同一轮并行**发出。

> 分工：**Judge（Trigger 取数）用** `check_anomaly`（按工具名，不跑 bash）；**交互分析 / 资讯 / 异动归因 / 回调正文用** `westock`。二者不要混用。

代码必须带市场前缀（`sh`/`sz`/`bj`/`hk`/`us`）；只给名称先 `westock search <名称>` 拿代码。货币按市场标注，港股港元、美股美元，禁用人民币符号。

---



## 场景一：咨询建议 & 询问是否创建盯盘

用户带着持仓/自选来问「怎么操作」。目标：每只票给「现状 + 理由 + 操作建议」，再顺势询问是否建长线盯盘。K 线用 `westock kline` / `technical` 取数写进分析，**不要**走 `emit_kline.py` / `stock-kline` 出渲染卡（当前画不出来）。

一次并行取数（N 只票用逗号批量，1 条命令）：

```bash
westock quote sh600519,sz300750             # 现价/涨跌幅/量比/成交额/换手/PE/市值/52周高低
westock technical sh600519,sz300750         # MA/MACD/KDJ/RSI/BOLL → 多空排列、金叉死叉、超买超卖、支撑压力
westock fund flow sh600519,sz300750         # 主力/超大单净流入（A股）→ 资金方向；港股用 TotalNetFlow/MainNetFlow；美股改用 fund short
westock news list sh600519,sz300750 --limit 5   # 近期新闻（消息面）
westock report list sh600519,sz300750 --limit 3 # 机构研报（评级/目标价方向）
westock events sh600519,sz300750            # 事件标签速览（解禁/减持/回购/财报/指数调整等）
```

需要更深时再按需补：`westock finance`（三大表）、`westock consensus`（A股一致预期）、`westock rating`（港美股机构评级目标价）、`westock chip`（沪深筹码）、`westock risk`（沪深风险明细）。

输出规范：

- **结论先行**：先一句话总判断，再逐只展开。
- 每只票写在正文：`名称 代码 · 建议标签（持有/加仓/观望/减仓/回避）` + 一行理由（技术面 + 资金面 + 消息面综合）+ `现价/涨跌幅`，注明数据时刻与币种；休市只报最近交易时刻。涨跌配色按市场惯例：沪深京港涨红跌绿，**美股绿涨红跌**。**禁止 `show_advice`**，不要出「个股操作建议」卡。问盘面必须 `show_quote`，这一轮只出这一张，不要再出 `show_news`。
- 收尾主动提议：「要不要把这几只加入长期盯盘」，用户同意即走 SKILL.md「创建」。用户只要行情/不通知时，不启用任何规则。
- **说了盯盘必须建上。**「帮我盯一下 Meta」要加载 make-things，建 Thing / Todo / Trigger，默认异动监控和每晚 20:00 日结。没拿到真实 ID 不能写「已创建」。主对话该出的 `show_quote` 照出。本会话还没发过股票 Now 卡就发一张 `stock`；先看盘已经发过，创建这轮不要再跑 `now_stock.py`，也不要再跟一张 `recommend_list`，不要改成 `image_text`。
- **已有盯盘 Thing、问的是股票或盘面**：主对话该出的 A2UI 仍出；Now 按 SKILL.md「Now 动态发什么卡」发 **1 张** `stock`（`data.items` 放今天要盯的，最多 3 只；`trend` 按实际涨跌：2 涨红 / 3 跌绿），**不追发全清单** `recommend_list`。股票卡 `data` 必须是 `{items}`，**不要传** `hint`，不要把 `code/price/rising` 平铺在 `data` 根上。
- **全清单盘面总结** `recommend_list` **只在每晚 20:00 的收盘日结发**，当面问、到价命中、异动命中一律不发。总结卡的涨跌用彩色圆点 + ▲▼，口径写进卡面。
- **股票卡不配 `actions`，以 make-things 为准。**「帮我分析」挂在 20:00 那张盘面总结上（顶层 `actions`，`tap.type=1` 带 prompt），每项 `tap` 用 `type=2` 跳自选股个股页（URL 与主对话「查看详情」同一条规则）。股票卡配不配整卡 `tap` **只看** `items` **里有几只**：一只就配（到价/异动天然一只，只盯一只时的盘面卡也是），两只以上不配——指向谁都不对。多标的盘面卡因此是纯展示卡，别硬塞 `actions` 凑交互。
- `summary` **与每项** `desc` **各只画一行**：都压到 ≤ 20 字，判断依据写进正文，别指望卡面展开。
- 客观陈述，附风险声明，不构成投资建议。

---





## 场景二：异动监控（在盯盘 Thing 下；未盯盘则先按「创建」新建，默认即含异动）

**Judge 判定用** `check_anomaly`（`mode: anomaly`），condition 只读 `triggered`。写法见 [triggers.md](./triggers.md)，不要在这里另写一套。

**默认异动规则（一期固定）**：`量比 ≥ 2` **且** `涨跌幅绝对值 ≥ 5%`（涨、跌都算异动），两条同时满足才命中。阈值由入参带进 `check_anomaly`。空数据、错误、不在交易时段都不命中，也不凭推测启用。港股、美股经常没有量比，脚本降级成只看涨跌幅，不要另改 condition，不臆造量比值。

**命中回调后做异动归因**（这一步用 `westock`）：

```bash
westock news list sz300750 --limit 5        # 找放量/异动当天的消息面
westock events sz300750                       # 是否有大宗/龙虎榜/解禁/减持/财报等事件
westock fund flow sz300750                    # 主力资金是否配合
```

回调正文：`show_anomaly` 盯盘卡（标的 + 现价涨跌 + 量比 + **一句异动原因**，引用 news/events）。**不要**再跑 `emit_kline.py`。取不到明确原因就省略 `reason`，卡上会显示「暂无明确消息面」，不编造。量比拿不到就整个字段省略，不要填 0 冒充。

---



## 场景三：到价提醒

一期**只做到价提醒**，不做持仓成本演算。用户提到「监控某价位 / 跌到 X 提醒 / 涨到 Y 提醒」→ 在该股票监控 Thing 下按「创建」建到价 Trigger。

到价单独建一条规则，不跟异动合并，写法见 [triggers.md](./triggers.md)「两类规则」：Judge 调 `check_anomaly`，传 `mode: alert` 和 `alert_price` / `alert_direction`，condition 只读 `triggered`。设好规则时用 `show_alert_set` 出卡，命中回调时用 `show_alert_hit` 出卡（标的 + 现价涨跌 + 触发条件）。**不要**再跑 `emit_kline.py`。

---



## 场景四：资讯 / 公告 / 研报查询（westock news + web_search 兜底）

**c第一优先 westock**（近期、结构化、权威）——批量 + 并行；`news list --type` 分取新闻/研报/公告，或 `--type 3` 全类型：

```bash
westock notice list sh600519 --type 5        # 公告（--type：0全部/1财务/2配股/3增发/4股权变动/5重大/6风险/7其他）
westock news list sh600519 --limit 10        # 财经新闻（--type：0公告/1研报/2新闻/3全部）
westock report list sh600519 --limit 5        # 机构研报（评级/目标价）
westock events sh600519                        # 事件标签（回购/分红/解禁/减持/财报/指数调整…）
westock dehydrated                             # 脱水研报（可选，行业风口）
```

**web_search 兜底**：westock news 只覆盖**近期**且范围有限。遇到下列情况用 web_search 补：

- 用户**指定较早时间段**或问**历史公告/资讯**（westock 只给最新的，web_search 能按指定时间搜）；
- westock 对该标的/该主题返回为空或明显不足。
兜底后整合两源、按标的与时间去重、**标明来源**（区分 westock / web），冲突时以交易所/公司公告口径为准。⚠️ 仅资讯类可 web_search；行情/K 线/财务/资金等仍禁 web_search。

加工规范：

- **按重要度排序**：重大公告 / 评级或目标价变动 / 事件（解禁减持等）> 一般财经新闻。
- 每条同时标类型和情绪 `利好 / 利空 / 中立`（利好红、利空绿、中立灰）+ **一句话解读**（对股价潜在影响）+ 来源 + 时间 + 原文 `url`。
- 判断依据来自内容本身（研报评级方向、目标价上调/下调、公告类型、事件性质），拿不准标「中立」，不臆断。

**主对话必须 `show_news`**：每条资讯一个 item（标题可点原文 / 来源·时间 / 类型标签 + 情绪标签 / 一句话解读）。不要只回文字列表。问某一条/某只的细节，不发动态、不挂 K 线。

**问资讯总结 / 今日资讯**（已有盯盘 Thing）：Now 发 1 张 `recommend_list`，覆盖关注标的的今日资讯，不要附 `stock` 卡。版式与颜色口径见 SKILL.md「Now 动态发什么卡」。

主动推送（走 triggers.md「回调与动态」的 `show_widget`）：

1. **每晚 20:00 收盘日结**：每日固定时间的原生 Trigger，收盘后先发一张 `stock`（今天值得盯的，最多 3 只），再发盘面总结 `recommend_list`（覆盖清单全部标的的收盘行情，清单非空就发）。资讯 Todo 没挂上就不搜。挂上了才搜，和已推过的资讯做差，有新的才发资讯总结；取数失败不当成没有新资讯。**一个 Trigger 管这一档日结，不要为股票卡、盘面总结、资讯总结各建定时规则。** 禁止 create_timer。
2. **盘中重大不另建规则。** 没有资讯事件来源，不要用每小时 Timer 或 judge 去轮询。开了资讯监控也只在上面这条 20:00 日结里搜并做差。发出去的资讯卡仍是 `recommend_list`，不要改发 `stock`。

发布 `show_widget` 纪律：资讯路径卡型用 `recommend_list`（`item_id` / `title` / `desc`），顶层 `actions` 配一个「聊聊对持仓的影响」（`tap.type=1`，`send_prompt` 以这句话开头、后面带上具体标的名称，如「聊聊对持仓的影响：腾讯控股、阿里巴巴今天这些资讯」——只发按钮那几个字，主对话收到的就是那几个字，不知道指哪几只）；**每条** `tap` **一律** `type=2` **跳这条新闻的原文页**——URL 从 westock news 的返回里取（默认 markdown 表没有 url 列，加 `--raw` 取 JSON 拿全量字段），不许拿 `id` 拼链接，真取不到就那一条不配 `tap`，不要退回主对话，利好/利空用彩色圆点表达（口径见 SKILL.md）；`title` / `desc` 各 ≤ 20 字，超了会被截断；真实 `now_id` 才算发出，**平台不去重、不幂等**，超时或回包缺失时如实报告「发布结果未确认」，不要自动重试。`now_id` 不等于牛仔 Now 已经把 RecommendList 画出来。

---



## 数据时刻（盯盘卡的 `as_of`）

`westock quote` **的输出列里没有时间戳**（`code | name | price | prevClose | open | high | low | volume | amount | change | changePercent | turnoverRate | volumeRatio | …`），所以盯盘卡的
「变动时间」要单独取。按顺序取第一个拿得到的，并把粒度如实写进 `as_of_kind`：

```bash
westock quote hk00700                                  # ① 若输出 updateTime → as_of_kind=realtime（需实测）
westock minute hk00700                                 # ② 取最后一个点 → as_of_kind=minute（不支持批量）
westock kline hk00700 --period day --limit 1           # ③ 取 date → as_of_kind=close
```

①最划算但**官方字段表没列** `updateTime`，先实测再依赖；②单标的场景（到价、异动）用它；
③批量刷新时用它，卡上会自动补「收盘」后缀。

**禁止拿当前系统时间冒充行情时刻**，也禁止把昨收标成 `realtime`。三条都取不到就如实报告
取数失败，不出卡。

## 通用取数纪律（摘自 westock-data）

- 默认输出已是结构化 Markdown 表格，直接读，不要用脚本/正则解析；不要 `| grep`/`| head`/`&&` 截断拼接，用命令自身参数控制条数。
- 批量：支持逗号的命令 1 次调用多代码；不支持批量的（`search`/`minute`）分开但同轮并行。
- 空结果说明「暂无数据」，区分「代码不支持」与「时点无披露」；命令失败如实转述，不用训练数据补数。
- web_search **只用于场景四资讯/公告/研报**兜底；行情/K 线/技术/财务/资金等命令失败时不得降级到 web_search。

