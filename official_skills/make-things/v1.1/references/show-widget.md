# Show Widget：公共字段与 NowCard 正文

字段依据：[下游 things_now.proto](https://zhiyan.woa.com/plugin_ifbook/17187/repo/#/ifbook/repo/ifbook-managed/ver/baseline/proto/ifbpf-caIUguDxNu/content)，基线版本，2026-09-20 核对。

## 卡片的定位

`show_widget` 发的卡进 **Now 流**；对话内当前不渲染卡，详情靠投递后的会话回复承接。卡是缩略形态：标题最多两行、摘要一行——**内容要自含结论**，用户不点开也能看懂这次发生了什么。用户点卡跳回对应会话看详情、继续对话，所以任务类卡片的点击落地默认用 agent_chat 回到会话。

## 什么时候发

**发卡是一次独立判断，不跟着任何动作自动发生。** 以下都不自动代表要发新卡：App 数据刷新、Todo 更新、Trigger 到点命中。

五条判断，任一不满足就不发：

| # | 判断 | 说明 |
| --- | --- | --- |
| 1 | **有实质变化** | 结论、数值或状态与上次发的那张不同。复述同样的内容不发 |
| 2 | **用户看得懂且用得上** | 卡片是给用户看的结果，不是执行日志。「已检查、无变化」不值得占一张卡 |
| 3 | **同一事项一天一张为上限** | 同一 Thing 一天内多次有进展，合并成一张最新的；不为每次检查各发一张 |
| 4 | **没料就不发** | 条件未命中、取数为空、无新增——只更新任务说明的进展行，不发卡 |
| 5 | **规则命中不等于要发卡** | 命中只说明该执行业务动作。是否发卡按前四条再判一次 |

创建卡片**不幂等**，没有内容去重——同一进展判重了就是两张卡，用户侧看到的是重复打扰。第 3 条那个上限是靠模型自己守的，工具不会兜。

---

## 请求边界与公共字段

调用本包绑定的 `show_widget`，直接传以下顶层字段。使用本包延迟加载的 `show_widget@v1.0-cowboy`，工具入参以注入的精简 Schema 为准；正文和公共对象结构见本 Reference。

| 字段 | 必填 | 定义与填写方式 |
| --- | --- | --- |
| `card_type` | 是 | 字符串：`image_text`、`recommend_list`、`todo_remind`、`todo_choice`、`stock`；与 data 正文类型对应，不传数字。 |
| `title` | 是 | 整张卡片的简短标题，说明本次通知、推荐、选择或行情主题。 |
| `data` | 是 | 所选正文消息的对象，见下面五种示例。图文卡没有封面时可传 `{}`。 |
| `summary` | 否 | 标题下的灰字说明。日期、地点、评分等结构化信息拼成可读字符串放这里，不新增公共字段。 |
| `source` | 否 | `{label: "来源名称"}`，按真实来源填写；图标由 H5 固定，不传 icon。 |
| `actions` | 否 | 底部按钮数组，每个按钮为 `{action_id, label, tap}`，见下文。股票卡不配按钮。 |
| `tap` | 否 | 点击整卡的落地目标，见下文。省略时整卡不跳转；独立按钮或推荐项仍按各自 tap 响应。 |
| `thingId` | 否 | 关联的真实 Thing ID；仅发布卡片不必新建 Thing，ID 来自当前会话的真实查询或创建回包。 |
| `todoId` | 否 | 关联的真实 Todo ID；填写时必须同时提供所属 `thingId`。发布前重读 Thing 核对归属。 |

**data 直接是所选正文对象**，不是完整 NowCard，也不包 `{todo_choice: {...}}` 等 oneof 分支。`title/summary/source/actions/tap` 是调用方填写的顶层公共字段，不等下游补齐，不塞进 data；正文 item/option 的 `title`、推荐项的 `tap` 是合法嵌套字段。

命名通则：**工具的顶层关联字段用 camelCase**（`thingId` / `todoId`，不要照搬 IDL 的 `thing_id` / `todo_id`）；**`data` 正文与点击动作里的所有嵌套字段一律用 IDL 的 snake_case，枚举一律用数字**——`select_mode`、`badge.tone`、`tap.type`、`mp_type`、`trend` 都是数字，不是字符串。顶层 `card_type` 是例外，用表中的字符串。新增字段时按这条通则推断，不要另造风格。

不传旧的 `widget/skill_name/uri/push/triggerId`，也不传 `user_id/conversation_id/eventId` 或其他额外顶层字段。用户和会话来自可信上下文，不由模型指定或编造。不执行 render 脚本，不生成 HTML，不为发布绑定 App，不增加 `mcp_app_ids`。发布卡片不代表系统弹通知，不能承诺设备推送。

## 底部按钮与点击目标

`actions` 的每个元素只包含：

- `action_id`：同卡唯一的不透明字符串，作为 React key，例如 `a7f2`。不要用它编码确认、关闭等行为；行为由 tap 决定。
- `label`：用户可见的按钮文字。
- `tap`：该按钮的点击目标，使用下面的 Tap 结构。

H5 按按钮从左到右的顺序决定主次样式；不要额外传 `style/behavior`，也不要假定按钮有关闭卡片的语义。没有按钮需求时省略 actions，股票卡不配按钮。

整卡 `tap`、`actions[].tap` 和推荐项 `data.items[].tap` 共用同一种结构。每个 Tap 必须有匹配的数字 type 和**唯一一个**目标对象：
任务类卡片没有明确的独立落地时，`tap` 用 type=1 的 agent_chat 回到会话；不要编造 H5 地址。

| type | 唯一目标字段 | 内容 |
| --- | --- | --- |
| 1 `TAP_TYPE_AGENT_CHAT` | `agent_chat` | `{send_prompt: "向原会话发送的内容"}`；不填 send_prompt 时传 `{}`，只打开会话，不发送消息。 |
| 2 `TAP_TYPE_H5` | `h5` | `{url: "实际 H5 地址"}`。 |
| 3 `TAP_TYPE_MINI_PROGRAM` | `mini_program` | `{name: "gh_原始ID", path: "页面路径", mp_type: 0}`；path 可省略。 |

牛仔宿主当前不支持打开小程序，不为牛仔卡配置此落地。mini_program.name 必须是 gh_ 原始 ID，不是 AppID；mp_type 为 0 正式、1 开发、2 体验。只填实际已知目标，不编造 ID 或落地地址。IDL 中的 type=4 image_preview 一期 H5 不支持，暂不下发；不要用 type=0 代替省略 tap。

选择卡需要确认并回传 Agent 时，在顶层 actions 配置“确认选择”按钮，使用 type=1 的 agent_chat，send_prompt 写成以冒号结尾的语境前缀（见选择卡示例）。用户确认时 H5 追加所选且未完成的选项，再发回原会话；不要在前缀里预先写死用户选择，也不要扩大用户委托。发布卡片本身不触发发送。

## 五种正文

先按场景选类型，再按下面各节填 `data`：

| 场景 | `card_type` | `data` 消息与主要字段 |
| --- | --- | --- |
| 图文通知、说明、一句话进展 | `image_text` | `ImageTextData`：`cover`（可选，没图传 `{}`） |
| 多条图文推荐，供用户挑 | `recommend_list` | `RecommendListData`：`items`（`item_id`/`title`/`desc`/`image`/`tap`），3–5 条 |
| 多条待办提醒，只展示不互动 | `todo_remind` | `TodoRemindData`：`items`（`item_id`/`title`/`desc`/`badge`）、`footnote` |
| 要用户单选或多选 | `todo_choice` | `TodoChoiceData`：`select_mode`、`options`（`option_id`/`title`/`desc`/`image`/`selected`/`done`） |
| 一组股票行情 | `stock` | `StockData`：`items`（`time`/`name`/`code`/`current_price`/`prev_close_price`/`change`/`trend`） |

**`todo_remind` 与 `todo_choice` 最容易选错**：只是把几件事摆出来给用户看，用 `todo_remind`；需要用户勾选并回传，才用 `todo_choice`。**提醒卡自身不创建任何 Trigger**——它只是展示，到点不会有动作，要真提醒必须另外配规则。

### 图文内容：ImageTextData

只有可选 `cover: {url: string}`，主图 URL 使用真实可访问的 HTTPS 地址。没有图片时 data 可以为 `{}`，文字内容由顶层公共 `title/summary` 提供。不要把旧的 `body/notice/image/buttons` 放进 data。

```json
{
  "card_type": "image_text",
  "title": "周末出行提示",
  "summary": "出发前核对路线和天气。",
  "data": {
    "cover": {
      "url": "https://example.com/cover.jpg"
    }
  }
}
```

示例图片 URL 仅说明结构，实际调用请换成真实图片；取不到图片时省略 cover。

### 推荐列表：RecommendListData

`items` 按 IDL 注释组织为 3–5 条。每项 `item_id`、`title`；可选 `desc`、`image`（URL **字符串**）、`tap`。同卡 item_id 唯一且后续快照保持稳定。推荐项没有独立落地时省略 tap。

```json
{
  "card_type": "recommend_list",
  "title": "周末活动推荐",
  "summary": "三个轻松的安排，按兴趣选择。",
  "data": {
    "items": [
      {
        "item_id": "walk",
        "title": "城市绿道散步",
        "desc": "在树荫下走走，安排一个轻松的下午。"
      },
      {
        "item_id": "read",
        "title": "咖啡馆阅读",
        "desc": "留一小时读完喜欢的章节。"
      },
      {
        "item_id": "cook",
        "title": "在家做一顿饭",
        "desc": "试一道收藏已久的食谱。"
      }
    ]
  }
}
```

### 待办提醒：TodoRemindData

`items` 每项包含 `item_id`、`title`；可选 `desc`、`badge: {text, tone}`。`footnote` 是列表下方备注。badge.tone 为 0（未指定）、1（信息/蓝）、2（警告/橙），标签实际文案由 text 指定。提醒项没有 image、completed 或 done 字段。

```json
{
  "card_type": "todo_remind",
  "title": "出发前的准备",
  "source": {
    "label": "出行计划"
  },
  "data": {
    "items": [
      {
        "item_id": "ticket",
        "title": "核对车票",
        "desc": "确认出发车站和时间。",
        "badge": {
          "text": "出发前确认",
          "tone": 2
        }
      },
      {
        "item_id": "umbrella",
        "title": "带上雨伞",
        "desc": "查看目的地天气后准备。"
      }
    ],
    "footnote": "建议提前整理随身物品。"
  }
}
```

### 待办选择：TodoChoiceData

必须显式给 `select_mode`，1 = `SELECT_MODE_SINGLE`（单选），2 = `SELECT_MODE_MULTI`（多选），不用未指定的 0，也不根据项数猜模式。

`options` 每项包含 `option_id`、`title`；可选 `desc`、`image`（URL 字符串）、`selected`（初始选中布尔值）、`done`（已完成布尔值）。option_id 同卡唯一；单选至多预选一项。done=true 的项置灰禁选、不进确认拼句，生成时不要再 selected=true。

```json
{
  "card_type": "todo_choice",
  "title": "今天想做哪些锻炼？",
  "summary": "可多选，确认后发回会话。",
  "actions": [
    {
      "action_id": "a7f2",
      "label": "确认选择",
      "tap": {
        "type": 1,
        "agent_chat": {
          "send_prompt": "关于今天的锻炼，我选择："
        }
      }
    }
  ],
  "data": {
    "select_mode": 2,
    "options": [
      {
        "option_id": "bridge",
        "title": "臀桥",
        "desc": "3 组 × 15 次",
        "selected": true
      },
      {
        "option_id": "plank",
        "title": "平板支撑",
        "desc": "3 组 × 40 秒"
      },
      {
        "option_id": "squat",
        "title": "深蹲",
        "desc": "3 组 × 12 次",
        "done": true
      }
    ]
  }
}
```

单选只需将 select_mode 改成 1，并保证至多一个未完成项 selected=true。

### 选择卡回传纪律
**卡片的 `option_id` / `item_id` 和业务 Todo 标识是两套 ID 体系，没有映射关系**——不要拿卡片上的 ID 去写 `rule_ids` 或定位 Todo。需要更新事项状态时重读 Thing，按真实归属和实际执行结果更新。
选择由 H5 本地维护，勾选不落库；确认按钮在顶层公共 actions 配置，不放进正文 data。用户确认回到原会话后，根据实际回传内容与原卡片匹配选项，再继续执行。不要假定新 IDL 保证旧客户端的 `selectedIds` 回调字段。选中不代表已完成，更新业务 Todo 前需核对真实事项及完成证据。

### 股票：StockData

`data` 为 `{"items": [...]}`，items 是 `StockItem` 数组。一个 Now 承载一组股票，每只股票渲染成一张 stock 子卡，按后台给定的列表顺序展示，不自行重排。纯展示，无图表、无按钮，不配置 actions。

| StockItem 字段 | 类型 | 含义 |
| --- | --- | --- |
| `time` | string | 行情时间展示串，如 `09/18 16:07:58`，不是时间戳。 |
| `name` | string | 股票名称。 |
| `code` | string | 股票代码展示串，如 `03750·HK`。 |
| `current_price` | string | 格式化后的现价，显示在右上方。 |
| `prev_close_price` | string | 格式化后的昨收价，显示在现价下方。 |
| `change` | string | 格式化后的涨跌幅，如 `+0.14%`、`0.00%`、`−1.64%`。 |
| `trend` | StockTrend 数字枚举 | 同时决定 current_price、prev_close_price、change 三处数值的配色，见下表。 |

| trend | 枚举 | 含义与配色 |
| --- | --- | --- |
| 0 | `STOCK_TREND_UNSPECIFIED` | 未指定，端上按平盘灰兜底。 |
| 1 | `STOCK_TREND_FLAT` | 平盘，灰色。 |
| 2 | `STOCK_TREND_RISING` | 上涨，红色。 |
| 3 | `STOCK_TREND_FALLING` | 下跌，绿色。 |

时间、名称、代码、价格和涨跌幅使用真实行情数据；价格与涨跌幅保留后台给定的格式化展示串，不转成数字、不丢失小数位或符号。trend 使用实际行情对应的枚举；0 只表示未指定，不作为已确认平盘的替代值。

**`trend` 要和 `change` 的方向一致**：`change` 为正配 `2`，为负配 `3`，零配 `1`。填反了卡片会显示红色的跌幅或绿色的涨幅，工具不会报错，用户直接看到矛盾数字。

以下为结构示例，使用虚构股票与示意行情，实际调用须替换为真实数据：

```json
{
  "card_type": "stock",
  "title": "自选股行情",
  "data": {
    "items": [
      {
        "time": "09/18 16:07:58",
        "name": "示例股票 A",
        "code": "DEMO-A",
        "current_price": "10.200",
        "prev_close_price": "10.000",
        "change": "+2.00%",
        "trend": 2
      },
      {
        "time": "09/18 16:07:58",
        "name": "示例股票 B",
        "code": "DEMO-B",
        "current_price": "9.800",
        "prev_close_price": "10.000",
        "change": "−2.00%",
        "trend": 3
      }
    ]
  }
}
```

整份请求最多 64KB。

## 发布结果与失败恢复

只有工具成功返回真实 `now_id` 才报告已发布，不再读取旧的 `recommendation.id` 或依赖 `deduplicated` 标志。创建**不幂等**，完全相同的参数再次调用也可能产生另一张卡片，不承诺重复快照会去重。

超时、连接中断或回包缺失时，不能自动重试，也不能换标题、改 data 后重发。若实际环境提供卡片记录查询能力，先查询核对真实发布结果；本工具没有声明查询接口，不编造查询工具。无法确认时如实说明发布结果尚未确认。只有明确未创建且失败原因已修复时才重新调用；重新发布另一张卡片应有实际业务需要或用户明确要求。

普通 App 刷新不自动发布，发布后不再另发 notify；发布成功也不等于用户已读、选择已确认或 Todo 已完成。

本技能采用新的工具参数与 IDL 正文契约。旧的 `widget` 包装、`selectionMode/selectedIds/completed`、通知 `body/buttons` 及旧行情结构不能混入请求。若运行环境仍只接受旧协议，报告协议不匹配，不回退拼接旧字段，也不宣称端上已显示。