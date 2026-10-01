# 出卡工具的字段细则

六个 `_run.py` 工具各自要哪些字段、怎么填、配色口径、常见坑。**字段怎么写以这一份为准**；什么时候出哪张卡看 main-chat-cards.md。

# 智能盯盘卡

## 出卡

沙箱没有 `app`。只准：

```bash
python3 /data/skills/stock-watch/scripts/_run.py <tool> '<json>'
```

例：`... _run.py show_quote '{"code":"sh600519","name":"贵州茅台","price":1685.2,"change":7.1,"change_pct":0.42,"currency":"CNY","as_of":"09-19","as_of_kind":"close"}'`。
必须带完整路径。`_run.py` 的原始 stdout 会追加 `__ONEAGENT_APP_RESULT__`；宿主会在
工具结果回给模型前消费这一行并转成 `app.data`，所以模型通常只看到第一行业务 JSON
和 `[Command finished with exit code 0]`。这是出卡成功的正常结果，**不要因为看不到
sentinel 重跑或误报失败**。不要找 `/data/skills/bin/app`，不要去 `/nix` 里翻。

**进了这个技能就要出卡片。** 有快照就跑上面那条；取数失败才允许只回文字。
一条 bash 只跑一个 `_run.py`。命令必须单独一行，不接 `| head`、`| python -c`、`>/dev/null`。
禁止直接执行 `scripts/` 下的 handler。直跑没有 `__ONEAGENT_APP_RESULT__`，卡面不刷新。
不要 `cat` / 打印 `assets/ui/*.json` 或 `assets/app.yaml`。

**不用再为出卡额外 `load_skill`。** 卡资源跟这份文档在同一个包里，本技能一加载
`app.resource_list` 就随着下发了。用户反馈「卡没出来」时直接重跑那条命令。
（旧版把卡拆成了一个独立技能，才需要每回合先加载它一次。那个技能已并进本包并下线，
再去加载会失败、卡也不会出——出卡就是上面那一条命令，没有前置步骤。）

三张 A2UI 对话卡，**没有全屏页**。「查看详情」打开腾讯自选股小程序个股页
（`https://wzq.gtimg.com/mm/detail?market=…&type=…&scode=…`，`market` 与 `type` 同值成对：
`0` 深 / `1` 沪 / `2` 港 / `3` 美 / `bj` 北，`scode` 填裸代码，本包自己算，你不用传）；
「帮我分析」回传给 Agent 在对话里继续答。不要用 `open_workspace`。

| 资源 | 画什么 | 工具 |
|---|---|---|
| `ai_apps.skills.stock_watch_main_res` | 单标的事件卡：大价格 + 涨跌 + 提示行 + 两个动作 | `show_alert_set` / `show_alert_hit` / `show_anomaly` / `show_quote` |
| `ai_apps.skills.stock_watch_advice_res` | 白底大卡 + 每只股票一块灰底：时刻、名称、代码·交易所、现价涨跌、理由、「查看详情 / 帮我分析」 | `show_advice` |
| `ai_apps.skills.stock_watch_news_res` | 多标的资讯列表：归属标的 · 标题 + 彩色标签 + 「时间 · 来源 · 解读」 | `show_news` |

三份组件树是分开的，因为字段没有一个是共用的——拿单标的那棵树去渲染资讯出参，
绑定会全部落空，卡面一片空白，而且引擎不报错。`_run.py` 按 tool 从 `app.yaml`
查 `resourceUri`，不要在任何地方写死。

## 角色与入口

**这个包不取数、不判定、不存数据。** 它只渲染你这一轮已经取到的那份快照。

| 要什么 | 找谁 |
|---|---|
| 行情、涨跌幅、数据时刻、K 线、资金流、公告新闻 | `westock-data` |
| Trigger 的 Judge 取数 | 原生 `stock_market_data` |
| 盯盘条件、持仓、提醒阈值的真源 | make-things 的 `Thing.goal` |
| 把上面这些画成一张卡 | **本包** |
| K 线图 | `stock-kline` 当前渲染卡出不来；stock-watch 只取数，不调它出卡 |

盯盘状态**不存在本包里**。每次调用都要把完整快照当入参传进来；本包不记上一轮，
也不会替你补字段。

## 执行优先级（严格约束，单一真源）

1. **`as_of` 写行情数据时刻，不是当前系统时间。** 拿不到就按下面「数据时刻怎么取」降级，
   并把 `as_of_kind` 如实标出来。把昨收标成实时比不显示更糟——用户会拿它做决定。
2. **一个业务事件一张卡。** 四个工具对应四种事件，不要用 `show_quote` 假装触发了提醒，
   也不要用 `show_alert_set` 显示一条已经触发的提醒。
3. **阈值与条件的真源是 `Thing.goal`。** 传给本包的 `alert_price` / `alert_direction`
   必须和那边一致，不要凭会话里的旧文本填。
4. **异动 `grade` 如实写。** 扶摇（`hithink-finance`）未接入前写不出 `verified`。
5. **算术和格式化交给工具。** 涨跌额、涨跌幅、小数位、交易所后缀都由本包算，
   不要自己拼成字符串再传。

## 数据时刻怎么取

`as_of` 和 `as_of_kind` 成对出现。按下面的顺序取第一个拿得到的：

| 顺序 | 来源 | `as_of_kind` | 说明 |
|---|---|---|---|
| 1 | `westock quote` 若输出 `updateTime` | `realtime` | 批量一次调用就带回每只票的行情时刻，最划算。**是否输出需实测**：官方字段表没列它。 |
| 2 | `westock minute <code>` 最后一个点 | `minute` | 分钟级，形如 `09/18 16:07`。不支持批量，每只票一次调用。 |
| 3 | `westock kline <codes> --period day --limit 1` 的 `date` | `close` | 只到交易日。卡上会自动补「收盘」后缀。 |

**本卡是单标的卡，所以第 2 条的「不支持批量」不构成理由——交易时段内必须走到
`realtime` 或 `minute`，不许直接跳到 `close`。** 只有当天休市、或前两条都确实取不到时
才允许用 `close`；那种情况下卡上会显示「09/18 收盘」，这是如实降级，不是默认档。

**禁止拿当前系统时间冒充行情时刻。** 三条都取不到就如实说明取数失败，不要出卡。

## Agent 操作

六个场景各一个工具，字段各自声明，不要混着传。下面前四个走单标的那份组件树，
`show_advice` / `show_news` 各走自己那份。

### 到价 / 止损提醒已设置

用户刚给出价位、规则也已按实际结果处理之后：

```bash
python3 /data/skills/stock-watch/scripts/_run.py show_alert_set '{"code":"hk00700","name":"腾讯控股","price":9.006,"change":1.4,"change_pct":0.93,"currency":"HKD","as_of":"09/18 16:03","as_of_kind":"minute","alert_direction":"below","alert_price":8}'
```

标题会渲染成「已为腾讯控股设置 8.00 止损提醒」。`above` 出「止盈」，`below` 出「止损」。

### 到价 / 止损提醒已触发

只在 Judge 命中、**且你复查后条件仍然成立**时用：

```bash
python3 /data/skills/stock-watch/scripts/_run.py show_alert_hit '{"code":"sz300750","name":"宁德时代","price":7.96,"change":-0.36,"change_pct":-4.32,"currency":"CNY","as_of":"14:05","as_of_kind":"minute","alert_direction":"below","alert_price":8}'
```

### 异动命中

```bash
python3 /data/skills/stock-watch/scripts/_run.py show_anomaly '{"code":"sz300373","name":"扬杰科技","price":42.18,"change":3.76,"change_pct":9.8,"currency":"CNY","as_of":"10:32","as_of_kind":"minute","volume_ratio":3.2,"grade":"inferred","reason":"液冷温控订单消息 + 主力净流入 2.1 亿"}'
```

拿不到量比就**整个字段省略**，不要填 0 冒充；没有明确消息面就省略 `reason`，
卡上会显示「暂无明确消息面」。

**异动卡发完，正文里要加一句「今日不再重复提醒，明天开盘恢复」。** 这条规则命中后会
把自己停用（当日涨跌幅是累计值，不停的话每小时都会再命中一次），次日由 20:00 日结恢复。
不说这句，用户会以为监控挂了。

### 普通行情快照

没有盯盘事件、只是要把行情摆出来时：

```bash
python3 /data/skills/stock-watch/scripts/_run.py show_quote '{"code":"sh600519","name":"贵州茅台","price":1685.2,"change":7.1,"change_pct":0.42,"currency":"CNY","as_of":"09-19","as_of_kind":"close"}'
```

### 咨询建议（多标的）

回答完「这几只该怎么操作」之后，把结论同时落成一张卡：

```bash
python3 /data/skills/stock-watch/scripts/_run.py show_advice '{"basis":"基于实时行情 + 基本面","footer":"想看更细的资金流向、估值或历史走势，随时继续问我。","items":[{"code":"sz300750","name":"宁德时代","price":9.12,"change":0.52,"change_pct":6.05,"as_of":"09/21 15:00","as_of_kind":"close","advice":"持有","reason":"主力流入，但 MA20 仍压制，持有不追高。"},{"code":"sh600519","name":"贵州茅台","price":1652,"change":-28.1,"change_pct":-1.67,"as_of":"09/21 15:00","as_of_kind":"close","advice":"观望","reason":"跌破 20 日线，尚无企稳信号。"}]}'
```

`advice` 只能取 `持有 / 加仓 / 观望 / 减仓 / 回避`。`reason` 必须在 30 个字符以内，
只用一句话说清这个标签怎么来的；传长了也会由 handler 截到 30 个字符。
两者都必须来自本轮真实分析——**这张卡最容易被拿来编**，因为它只要文字不要数据。
`basis` 据实写：没查基本面就别写「基于实时行情 + 基本面」。最多 6 行。
每只票**必须**带 `as_of` / `as_of_kind`，涨跌额 `change` 和涨跌幅 `change_pct` 有就都传——
灰底面板跟单标的卡同一套字段（时刻、名称、`601020·SH`、现价、涨跌），不要再把代码揉进标题里。
每行自带「查看详情」和「帮我分析」：「查看详情」打开该票的自选股小程序页，
「帮我分析」把追问发回给你，按单标的卡同一套口径继续答。

### 资讯汇总

**一次汇总横跨几只票，合成一张卡**，归属标的**逐条**给（`code` + `name`），本包会拼成
「名称 · 标题」；行业新闻这类没有归属的省略这两个字段就行。

```bash
python3 /data/skills/stock-watch/scripts/_run.py show_news '{"source_line":"来自「资讯监控」· 盯盘 2 只 · 每晚 20:00 汇总推送","summary":"已按重要度排序，盘中重大消息此前已即时推送。","items":[{"kind":"notice","code":"sz300750","name":"宁德时代","title":"签订海外储能大单","stance":"利好","published_at":"2 小时前","origin":"巨潮资讯","takeaway":"订单超预期，短期偏利好"},{"kind":"report","code":"sh600519","name":"贵州茅台","title":"中信证券「买入」","published_at":"今早","takeaway":"目标价上调至 1900"},{"kind":"news","title":"财经新闻 · 锂价止跌反弹","published_at":"昨晚","origin":"财联社","takeaway":"成本端边际改善"}]}'
```

排序和 `stance` 判断由你做，本包只负责画。**标签取值的规则**：给了 `利好` / `利空`
就标它，否则退回显示类型（公告 / 研报 / 事件 / 新闻）。拿不准就别给 `stance`——
标一个类型是陈述事实，标一个方向是下判断。

利好/利空的配色**逐条**跟随那一条自己的标的：A 股利好红、美股利好绿。列表里混进
美股时卡底会自动标出口径。最多 6 条。

## 只出在主对话

这三张卡都是 A2UI，**只在主对话里渲染**。`_run.py` 的原始 stdout 第二行是
`__ONEAGENT_APP_RESULT__`；tool_proxy 会先把它解析成 `structured_content(app.data)`，
再从模型可见输出中剔除。模型看到业务 JSON 且命令 exit code 0、业务 JSON 的 `phase`
不是 `error`，就继续正常回答；**不要检查模型可见文本里是否还有 sentinel，也不要重跑**。
业务 JSON 为 `phase:error` 或命令非零才算出卡失败，如实报告且不要冒充成功。

**Now 动态不走 xcard 链路。** 不要把 `show_widget` 的任何字段指向本包——
Now 发的是 make-things 的五种卡（`stock` / `recommend_list` 等），A2UI 不在其中。
动态要提醒今日行情或资讯，由 stock-watch 按它自己的 Now 出卡约定去发，不要调本包冒充。

出卡成功后把信封里的稳定 App ID（`envelope.app.id`，即 `stock-watch`）合并进当前
Thing 的 `mcp_app_ids`，**保留其他已有绑定**。牛仔 Thing 黑板只认
这个稳定 App ID，不要找 `bindingId`。不要把 `stock-kline` 写进去——它现在不出渲染卡。

## 字段说明

**`code`** — 必须带市场前缀（`sh` / `sz` / `bj` / `hk` / `us`），裸六位数字会被拒。
只有名称时先 `westock search` 拿代码，不要猜交易所后缀——猜错等于静默换了一只票。
卡上的「00700·HK」和那个小标都由前缀派生。

**`price` / `change` / `change_pct`** — 照取数返回值原样传数字，不要自己拼成字符串。
卡上的小数位按 `price` 自身精度对齐：`9.006` 出三位（涨跌额渲染成 `+1.400`），
`1685.2` 出两位（`+7.10`）。涨跌幅固定两位。

**`as_of_kind`** — `realtime` / `minute` / `close`。只有 `close` 会在卡上补「收盘」后缀。
交易时段内不许用 `close`，理由见「数据时刻怎么取」。

**`note`（提示行，可选）** — 卡片下半部那一行灰字。不传时本包自己算：到价两个场景出
「触发条件 + 现价距阈值还有多少」，异动出「量比 + 归因」，行情快照不显示。传了就整条覆盖，
内容必须有数据依据——这一行是卡上唯一回答「离我关心的那条线还有多远」的地方，
摆一句套话等于把它浪费掉。美股的配色口径会自动接在这一行末尾，`note` 覆盖不掉它。

## 涨跌配色按市场惯例走

| 市场 | 上涨 | 下跌 |
|---|---|---|
| `sh` / `sz` / `bj` / `hk` | 红 | 绿 |
| `us` | **绿** | **红** |

不搞一刀切，是因为本卡一次只画一只票、不存在多市场混排，跟随各自惯例是安全的；真正
危险的是让一个看惯美股的人把绿色读成上涨。美股那张卡会在提示行自动补一句
「美股口径：绿涨红跌」，只在确实染了色时才出——解释一个不存在的颜色只是噪音。

出参里 `is_up` / `is_down` / `is_flat` 是**方向语义**，`is_red` / `is_green` 是**显示口径**，
两者在美股是反的。卡片绑的是后者；要改配色规则只动 `_card.py` 的 `GREEN_MEANS_UP`，
不用碰组件树。

**`note`（提示行）** — 卡片正文下面那一行灰字，不传时本包自己算：到价两个场景算
「触发条件 + 现价距阈值还有多少」，异动拼「量比 + 归因」，行情快照不显示。传了就整条覆盖，
内容必须有数据依据——这一行是卡上唯一回答「离我关心的那条线还有多远」的地方，
摆一句套话等于把它浪费掉。

**`currency`** — 按市场标注，港股港元、美股美元，**禁用人民币符号**。

**`grade`（异动归因质量）**：

| 值 | 什么时候用 |
|---|---|
| `verified` | 拿到了成品异动原因（扶摇 `analysis_content`）。扶摇未接入前用不到这个值 |
| `inferred` | 自己用 news / events / fund flow 拼出来的判断。**当前默认就是它** |
| `unknown` | 取数成功，但确实没有可归因的内容 |

## 常见坑

- **`alert_direction` 和 `alert_price` 必须同时给。** 两个都在 `required` 里，缺一个 CLI 直接拒。
- **`show_alert_set` 不代表规则已启用。** 卡上只陈述条件本身；规则仍停用、授权未完成或启用
  失败时，正文要写「已记下观察，规则尚未运行」，不能写「已开启」。
- **涨跌方向不猜。** `change_pct` 缺失或为 0 时卡片走默认色，不染红绿。
- **单标的那四个工具一次只画一只票。** 多只票用 `show_advice`，别拿 `show_quote` 连发四张。
- **`show_advice` 的 `advice` 和 `reason` 是判断，不是数据。** 没做分析就别出这张卡。
- **`show_news` 拿不准方向就省略 `stance`。** 标一个类型是陈述事实，标一个方向是下判断。
- **本包不画 K 线。** `stock-kline` 渲染卡当前出不来，不要为了配图去调它。
- **卡上的按钮一律 `action.functionCall`，没有 `action.event`。** 追问回对话用
  `{"call":"sendQuery","args":{"prompt":{"path":"…"}}}`，跳外链用 `openUrl`。
  `action.event` 虽然能过 schema 校验，渲染端却不认——按钮画得出来，点了没反应，
  而且不报错，只能靠人点一下才发现。改卡时不要照抄旧样例里的 `event` / `userMessage`。
  List 模板里的按钮绑**相对路径**（`analyze_prompt`），不是 `/analyze_prompt`。

## 沟通规则

- 休市时只报最近交易时刻，不声称是实时价格。
- 取数失败如实说，不要用上一轮的数据冒充这一轮，也不要编点位。
- 本包不执行交易，不给投资建议，展示的是客观数据。涉及判断的措辞要注明「非投资建议」。
