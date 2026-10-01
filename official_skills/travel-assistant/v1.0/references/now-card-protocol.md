# NOW 卡片协议（show_widget 入参）

使用本文件指导卡片组装及 `prepare_card`、`show_widget` 调用。`show_widget` 来自 `make-things`，
**先 `load_skill` 加载它才拿得到**；保持加载状态，不要额外加载卡片 Skill 或 UI 资源。

**先分清两层，混起来会直接发不出卡：**

```
skill  ──>  show_widget 工具  ──>  后台 NowCard  ──>  H5 渲染
            字符串 card_type        整数 card_type
            扁平 data               具名正文子对象
            camelCase thingId       snake_case thing_id
```

你调的是左边那个工具，**本文件写的就是工具入参**。`docs/personal_assistant/now技术方案.md` 和后台
IDL 描述的是右边那层，两者之间由工具做映射，不要把后台那套直接填进 `show_widget`。

口径以 `make-things` 自带的 `references/show-widget.md` 为准：顶层 `card_type` 用字符串、正文直接放
扁平 `data`、关联 ID 用 camelCase 的 `thingId` / `todoId`。**除此之外的顶层字段一律不传**，包括
`conversation_id`——会话来自可信上下文，由平台补入，模型指定会被拒。

例外只有一条：`data` 正文和 `tap` 里的**嵌套**字段一律 snake_case，枚举一律用数字
（`select_mode`、`badge.tone`、`tap.type`、`mp_type`）。只有顶层 `card_type` 是字符串。

- [入参](#入参)
- [四种卡型](#四种卡型)
- [点击](#点击)
- [按钮与选择回传](#按钮与选择回传)
- [发布](#发布)

## 入参

```json
{
  "card_type": "todo_remind",
  "title": "出发前一天",
  "source": {"label": "成都三日游"},
  "summary": "09/27 出发，先核对这些",
  "thingId": "真实 thingId",
  "todoId": "真实 todoId",
  "data": {
    "items": [{"item_id": "passport", "title": "护照身份证", "badge": {"text": "必带", "tone": 2}}]
  },
  "tap": {"type": 1, "agent_chat": {"send_prompt": "出发前再确认一次证件"}}
}
```

提供必填的 `card_type`、`title` 和扁平 `data`。按需提供 `source`、`summary`、`actions`、`tap`
和两个关联 ID。

- 公共标题、摘要、来源、按钮、整卡 tap **不放进 `data`**。`summary` 承载标题下灰字，以及已格式化的日期／地点／评分。
- **`data` 直接是正文对象**，不要再包一层 `{"todo_remind": {...}}`——那是后台 oneof 分支，不是工具入参。
- **`card_type` 与 `data` 正文必须对得上**，对不上端上按「没有正文」把整张卡丢掉。
- 仅使用当前会话真实回包中的 ID。提供 `todoId` 时同时提供 `thingId`；没有关联时两个都省略。
- 将 ID 放在卡片根节点，**不要放入 `tap`**；`tap.agent_chat` 仅包含 `send_prompt`。
- 不传 `conversation_id`、`user_id`、`eventId`、`widget`、`skill_name`、`uri`、`triggerId`、`push`、
  `card_id` 或任何其他顶层字段。用户与会话由平台公参补入，模型指定或编造会被拒。

## 四种卡型

仅使用以下四种卡型。不要使用兜底卡型、自定义 HTML 或 `stock` 股票卡。

| `card_type` | `data` 内容 | 要点 |
| --- | --- | --- |
| `"image_text"` | `cover? {url}` | 只传 HTTPS url，不传 width/height。端上裁到固定高 140 |
| `"recommend_list"` | `items` 3–5 条 | 每项 `item_id/title/desc?/image?/tap?`；`image` 是 URL 字符串 |
| `"todo_remind"` | `items` 1–20 条，`footnote?` | 每项 `item_id/title/desc?/badge?`；`badge.tone` 仅使用 1 蓝 / 2 橙 |
| `"todo_choice"` | `select_mode` + `options` | `select_mode` 用 1 单选 / 2 多选，不用 `single`/`multi` |

确定目的地后的**到达快览**按对象分别用 `image_text`：城市介绍、一个当地美食、
一个真实景点可以是三张独立卡，单卡绝不混装几个对象。
每张标题点名对象（不超过 18 个汉字），`summary` 写一条有来源、
无需点开也能理解的建议（不超过 40 个汉字），有真实 HTTPS 图片才传
`data.cover.url`。这类快览每张都配置整卡
`"tap":{"type":1,"agent_chat":{}}`，点击只打开卡片的原会话，不自动发送消息。
没有可交付的文章详情 H5 时不加“看详情”按钮，也不写“点开看攻略”。
Web Search 找到的长文只用于核实并压缩摘要，不能把全文塞进卡片。
同一对象仅发一次，按对象分别保存 `now_id`；同一趟旅行每天主动到达快览
默认最多三张有内容的卡，其中景点最多一张，普通途经景点不逐个推送。

已知航班/高铁的行前提醒用**无图 `image_text`**，具体检票口或座次仅从可核实资料填入。
例如用户票据明确写了 G1234 的「07 车 12F」，但没有可用的实时检票口数据：

```json
{
  "card_type": "image_text",
  "title": "G1234 出发前核对",
  "summary": "18:00 深圳北上车 · 07车12F（车票）· 检票口请看车站屏幕",
  "source": {"label": "行前信息"},
  "thingId": "真实 thingId",
  "todoId": "真实 todoId",
  "data": {}
}
```

样例中的班次和座位只说明字段写法，不能直接作为真实用户的票务数据。若从可信实时来源
获得检票口或登机口，连同查询时间写入摘要，并在会话说明以现场信息为准；不要用可售座别
冒充个人座位。行前提醒是一次性 Trigger 的交付，发布前重读 Todo，避免改签后发旧班次。

用户明确要求到达后通知当地天气时，也用无图 `image_text`：`title` 点名城市和天气，`summary` 写回调当时查到的实况、温度和查询时间，`source.label` 标真实天气来源，`data={}`，并关联真实 `thingId` / `todoId`。天气没有改变行程也要交付这张通知卡；不能用对话里的 `show_panel.weather` 代替。取数失败则如实发简短的无法核实提示，不编造天气。

`todo_choice.options[]`：`option_id/title/desc?/image?/selected?/done?`。`done` 不得同时 `selected`；
单选至多一项初始选中。不使用旧的 `items`/`selectionMode`/`selectedIds`/`completed`。

将 `done` 用于已完成项；端上会将该项置灰、禁用点击，并从确认文案中排除。不要暗示用户可以取消完成状态。
仅生成 `badge.tone=1`（蓝色）或 `badge.tone=2`（橙色）。本地校验器仅为历史已发布卡片保留
`tone=0` 兼容，不要在新卡中使用。

每个 item 或 option 仅使用上表列出的字段。不要为 `todo_remind` 的 item 配置 `tap`；该 item 不支持单独点击。

三处可以放图：`image_text.cover.url`、`recommend_list.items[].image`、`todo_choice.options[].image`。
都只收 HTTPS，取图口径见 [card-media.md](card-media.md)，取不到就省略字段，不要塞占位图。

完整 Schema：[show-widget.schema.json](show-widget.schema.json)（`oneOf` 把 `card_type` 和正文绑死，
多一个字段就被拒），单卡型见 [image_text](image_text.schema.json)、
[recommend_list](recommend_list.schema.json)、[todo_remind](todo_remind.schema.json)、
[todo_choice](todo_choice.schema.json)。

```json
{"card_type":"todo_choice","title":"今天练什么？","data":{"select_mode":2,"options":[{"option_id":"walk","title":"散步"},{"option_id":"stretch","title":"拉伸"},{"option_id":"run","title":"跑步","done":true}]},"actions":[{"action_id":"a1","label":"确认","tap":{"type":1,"agent_chat":{"send_prompt":"我选择："}}}]}
```

## 点击

省略 `tap` 以生成纯展示卡片。保持 type 与载荷一一对应：

| type | 载荷 | 说明 |
| --- | --- | --- |
| `1` | `agent_chat` | 回到卡片原会话；传 `{}` 只打开会话，提供 `send_prompt` 才自动发送消息 |
| `2` | `h5.url` | 打开 HTTPS 页面 |
| `3` | `mini_program` | `name` 是 `gh_` 原始 id，不是 AppID；`mp_type` 可选，缺省为 0 正式，1 开发 / 2 体验 |
| `4` | `image_preview` | 端上一期没接，不要下发 |

仅提供受支持的 `type`。端上会将未知 `type` 视为不可点击，且不会降级为打开会话。

**让 `tap.agent_chat` 只包含可选的 `send_prompt`。** 推荐卡用空对象 `{}`，不要为“返回会话”虚构用户消息。将关联 ID 放在卡片根节点，不要向 `tap` 添加 `conv_id` 或 `task_id`。
整卡、item 和按钮应返回同一会话。仅在 `type=1` 时使用三个 ID；跳转 H5 或小程序时不使用这些参数。

仅在三处配置点击：整卡 `tap`、底部 `actions[].tap`，以及 `recommend_list` 专有的 `items[].tap`。
将 `todo_remind` 的 item 用作纯展示；需要逐条点击时改用 `recommend_list`。
目的地、美食、景点等推荐 `image_text` 配整卡回会话 `tap`；推荐列表同时给整卡和
每个 `items[].tap` 配相同的 `{"type":1,"agent_chat":{}}`，使标题、留白与每项都回同一会话。
每日行程总览的点击也回原会话；卡片本身写清当下的关键信息。

避免为 `todo_choice` 配置整卡 `tap`。将交互限制为选择选项和点击底部按钮，防止跳转导致选择丢失。

小程序落地先用 `prepare_landing` 生成，规则见 [landing-pages.md](landing-pages.md)。
`h5.url` 只用于已部署的真实 HTTPS 地图唤端页等外部落地；不用于自建行程详情页。
skill 包里的 `ui://` 资源不能直接作为 NOW 落地。

## 按钮与选择回传

`actions[]` 每项 `{action_id,label,tap}`，**最多 2 个**。不传 `style`、`behavior`、`dismiss`。

将 `action_id` 设为卡片内唯一字符串，仅用于端上渲染的 React key。不要使用 `later` 或 `confirm` 等暗示内建行为的语义名称。
通过 `tap` 定义按钮行为；点击按钮不会消费或删除卡片。

按语义排列按钮：最后一个按钮渲染为主按钮，其余按钮渲染为次按钮。将「稍后 / 其他」放在前面，
将「确认 / 预约」放在最后。点击按钮不会删除卡片。

`todo_choice` 的确认按钮必须用 `type=1`，`send_prompt` 写成**以冒号收尾的前缀**，产品会把选中项标题
产品会按选项顺序使用「、」拼接标题；`done` 项置灰且不进入消息。不要在前缀中预写用户选择或扩大委托范围。

仅在用户点击确认后返回原会话。卡片选择只保存在本地，不会写入数据库。需要持久化时，依次重读 Thing、调用
`write_todos`，并按需发布完成态卡片。

## 发布

需要预校验时先调用 `prepare_card`，再将同一对象传给 `show_widget`。

仅在返回真实 `now_id` 时报告成功。创建接口没有幂等键或内容去重；超时或结果不确定时不要自动重试或报告成功，
应先核对动态列表。将请求控制在 64KB 以内；发布不会触发系统推送。

发布前完成内容校对。协议不提供编辑接口或折叠态字段；需要修改时发布新卡，撤下操作由后台在后续下发时处理。
