# 主对话盯盘卡（stock-watch）

主对话里那三张 A2UI 卡：六个工具怎么选、公共字段、数据时刻怎么取、为什么只出在主对话。末尾附 K 线当前为什么不出渲染卡。

## 展示盯盘卡（stock-watch）

命令见文首「出卡」。事件类场景（到价已设置、到价已触发、异动命中）用它出卡；K 线另走下一节。
不要用 K 线卡代替盯盘卡——K 线卡只有走势，没有事件标题、触发条件和后续动作。

六个工具，一个业务事件一个，字段各自声明，不要混着传：

| 工具 | 什么时候用 | 除公共字段外还要 |
|---|---|---|
| `show_alert_set` | 用户刚设好到价/止损，规则已按实际结果处理之后 | `alert_direction` + `alert_price` |
| `show_alert_hit` | Judge 命中**且复查后条件仍成立** | `alert_direction` + `alert_price` |
| `show_anomaly` | 异动命中，归因做完之后 | `grade`，可选 `volume_ratio` / `reason` |
| `show_quote` | 没有盯盘事件，只是把行情摆出来 | — |
| `show_advice` | **场景一**：咨询完给几只票下操作标签 | `basis` + `items[].advice/reason`，见下 |
| `show_news` | **场景四**：资讯汇总或盘中即时推送，几只票合成一张 | `source_line` + `items[].kind/title`，见下 |

前四个是单标的卡，后两个是列表卡（各有自己的组件树，最多 6 行）。

公共字段：`code`（带市场前缀）、`name`、`price`、`change`、`change_pct`、`currency`、
`as_of`、`as_of_kind`，以及可选的 `note`（提示行，不传由卡片自己算）。涨跌额、小数位、
交易所后缀都由那个包算，**不要自己拼成字符串再传**。

**涨跌配色由卡片按市场定**：沪深京港涨红跌绿，美股绿涨红跌，美股那张会自动标出口径。
你在对话正文里描述涨跌时沿用同一套，别让正文和卡面两种口径打架。

```bash
python3 /data/skills/stock-watch/scripts/_run.py show_alert_set '{"code":"hk00700","name":"腾讯控股","price":9.006,"change":1.4,"change_pct":0.93,"currency":"HKD","as_of":"09/18 16:03","as_of_kind":"minute","alert_direction":"below","alert_price":8}'
```

### 数据时刻（`as_of` / `as_of_kind`）

**`westock quote` 的输出列里没有时间戳**，所以数据时刻要单独取。按顺序取第一个拿得到的，
并把粒度如实写进 `as_of_kind`：

| 顺序 | 来源 | `as_of_kind` |
|---|---|---|
| 1 | `westock quote` 若输出 `updateTime`（**需实测**，官方字段表未列） | `realtime` |
| 2 | `westock minute <code>` 最后一个点（不支持批量，单标的场景够用） | `minute` |
| 3 | `westock kline <codes> --period day --limit 1` 的 `date` | `close` |

盯盘卡是单标的卡，所以第 2 条「不支持批量」不构成理由——**交易时段内必须走到 `realtime`
或 `minute`，不许直接跳到 `close`**。只有当天休市、或前两条确实取不到时才降级到 `close`，
那时卡上会显示「09/18 收盘」。

**禁止拿当前系统时间冒充行情时刻**，也禁止把昨收标成 `realtime`。三条都取不到就如实报告
取数失败，不出卡。

### 盯盘卡只出在主对话

`_run.py` 的原始 stdout 第二行是 `__ONEAGENT_APP_RESULT__`，宿主据此在**主对话**
渲染这张卡，并在工具结果回给模型前剔除该行。这是 `stock-watch` 唯一的出场地。
模型看到业务 JSON 且命令 exit code 0、业务 JSON 的 `phase` 不是 `error`，就继续正常回答；
**不要检查模型可见文本里是否还有 sentinel，也不要为“确认出卡”再跑一次。**

**Now 动态不走 xcard 链路。** Now 发的是 make-things 的五种卡（见「Now 动态发什么卡」），
A2UI 卡不在其中，任何字段里都不要写 `stock-watch`。

把信封里的稳定 App ID（`envelope.app.id`，即 `stock-watch`）合并进当前 Thing 的
`mcp_app_ids`，**保留其他已有绑定**。牛仔 Thing 黑板只认稳定 App ID，不要找 `bindingId`。
**不要把 `stock-kline` 写进 `mcp_app_ids`**——它现在不出渲染卡，绑上去也没有可展示的图。

业务 JSON 为 `phase:error` 或命令非零才算出卡失败，如实报告且不要冒充成功。
出卡本身**不等于**发动态——发动态的时机见本节下面那节末尾与「回调与动态」。

## 展示 K 线（当前不出渲染卡）

**`stock-kline` 的图目前画不出来。** 调它出卡只会得到一张空卡或坏卡，分析照做、卡不要出。

- **禁止** `load_app(stock-kline)`，禁止跑本包 `emit_kline.py`，禁止手写 `__ONEAGENT_APP_RESULT__` 冒充 K 线已展示。
- **禁止** 把 `stock-kline` 写进 `mcp_app_ids`。
- **禁止** 对用户说「K 线图已展示 / 图表已就绪」。牛仔端 `show_chart=1` 同样不会出图，回文里的「k线图将展示给user」是主端通道，不要据此声称已出图。
- `westock kline` / `technical` **照常取**，均线、支撑压力、量能写进盯盘卡和正文。K 线是分析材料，不是一张要渲染的卡。
- 用户点名要看图：用文字讲位置和形态，并说明当前出不了 K 线卡。不要为了交差去调 stock-kline。

本包仍留着 `scripts/emit_kline.py`，等渲染通路可用后再打开。现在调用等于出一张坏卡。

行情仍用 `stock_market_data` 读真价，`show_chart=0`，写明价格、币种和数据时刻；休市只报最近交易时刻。

`stock-watch` 的 `_run.py` 返回 `phase:error` 或命令非零时要如实报告。模型可见输出
没有 `__ONEAGENT_APP_RESULT__` 是宿主已消费它的正常现象，不算失败、不得重跑。K 线卡没出不算失败。

发动态（`show_widget`）只在这些时机：**用户提出要盯某只/某组（新建盯盘）**、已有盯盘 Thing 时用户问股票/盘面或资讯总结（卡型见「Now 动态发什么卡」）、到价命中、异动命中、**每晚 20:00 收盘日结（盘面总结 + 资讯总结两张）**、盘中重大推送、用户明确要求通知、验收阳性的“链路验收”动态。尚未建 Thing 且**没提盯盘**的纯咨询、某一条公告的细节问答、普通图表刷新不发布。

**全清单盘面总结只属于 20:00 那一档**，其余时机一律只发 `stock`，别顺手追发。

