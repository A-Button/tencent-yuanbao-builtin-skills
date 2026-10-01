# Now 卡：怎么调 `show_widget`

依据 2026-09-21 线上 trace（13 张卡发布成功）与 make-things 的 Show Widget Reference。
本文里的字段名和取值都是实跑验证过的，不是推测。

**这份文档在 2026-09-21 整体重写过。** 之前写的那一套（`skill_name` / `uri` /
`kind` / `eventId` / `recommendation.id` / `activity.*`）是旧协议，**现在传了会被拒**。
看到别处还留着旧写法，以本文为准。

## 1. 请求长什么样

顶层只有这些字段，`data` 就是正文对象本身，**不要再包一层 `widget` 或 `{todo_choice: {...}}`**：

| 字段 | 必填 | 说明 |
|---|---|---|
| `card_type` | 是 | 字符串，五选一：`image_text` / `recommend_list` / `todo_remind` / `todo_choice` / `stock`。**传字符串不传数字。** |
| `title` | 是 | 整张卡的短标题 |
| `data` | 是 | 正文对象，结构随 `card_type` 变 |
| `summary` | 否 | 标题下的灰字。日期、状态这类信息拼成一句话放这儿 |
| `source` | 否 | `{"label": "健康记录"}`。不传 icon |
| `actions` | 否 | 底部按钮数组，`{action_id, label, tap}` |
| `tap` | 否 | 点整卡的落地 |
| `thingId` | 否 | 真实 thing_id。**camelCase，不是 `thing_id`** |
| `todoId` | 否 | 真实 todo_id，填了就必须同时给 `thingId` |

**顶层 `card_type` 用字符串，嵌套的枚举用数字**——`select_mode`、`tap.type`、`badge.tone`
都是数字。这条很容易搞混。

**这些一个都不要传**：`widget`、`skill_name`、`uri`、`push`、`triggerId`、`eventId`、
`user_id`、`conversation_id`、`kind`。用户和会话由可信上下文给，模型不指定。
整份请求上限 64KB。

### 按钮回主对话：先区分跳转和提交

`tap.type` 三个值：1 = 回原会话（`agent_chat`），2 = 开 H5（`h5.url`），3 = 小程序（**牛仔宿主不支持，不要配**）。一个 tap 只能有一个目标对象。按钮的主次样式由从左到右的顺序决定，不要传 `style` / `behavior`。

回原会话有两种合法写法：

| 行为 | 写法 | 适用场景 |
|---|---|---|
| 只跳转，不自动上屏 | `{"type": 1, "agent_chat": {}}` | 用户回去后还要上传照片、输入调整内容，或报告已经在会话中 |
| 跳转并提交明确动作 | `{"type": 1, "agent_chat": {"send_prompt": "…"}}` | 点击本身已经表达完整意图，如跳过一餐、确认完成所选动作 |

**判断标准：按钮能否单独代表用户已经完成一次业务操作。** 不能就只跳转，不能为了驱动模型自动发送“我要记录”“我要调整”“看看报告”等占位文字。

#### 选择卡上，有 `send_prompt` 时必须和勾选项连读

`todo_choice` 会把端上发出的内容拼成：

```text
send_prompt + 当前勾选且未完成的 option.title（多个用「、」连接）
```

两段之间不加标点或空格。因此只对“提交动作”的按钮设置 `send_prompt`，并把它写成能和短标题连读的半句话：

| 按钮 | `send_prompt` | 勾选午餐后的上屏文字 |
|---|---|---|
| 不吃了 | `今天不吃` | `今天不吃午餐` |
| 去记录 | 不传 | 不自动上屏；只回会话，等待用户发餐食照片或文字 |

训练同理：完成按钮可用 `我练完了` + 动作名；“改计划”只跳回会话，等待用户说具体改什么。

`option.title` 仍只写短名词（如早餐、午餐、深蹲），状态、份量和热量写进 `desc`，不要带 emoji、`·` 或括号。

日报、周报已经生成在原会话中，整卡和“看完整报告”按钮都只跳转，不再自动发送“看看今天的日报”等占位消息。

## 2. 三餐和训练都用待办选择卡（`todo_choice`）

`data` 里必须显式给 `select_mode`：1 = 单选，2 = 多选。不许用 0，也不许按项数猜。

`options` 每项：`option_id`（同卡唯一）、`title`，可选 `desc`、`image`（URL 字符串）、
`selected`（初始勾选）、`done`（已完成，置灰禁选）。

### 这两张卡必须是选择卡，不许退化成纯文字

**S1 三餐和 S2 训练的提醒，只有一种合法形态：`todo_choice` + 非空 `options` + 两个按钮。**
少了任何一样就发不出去——这里说的不是报错，是发得出去但用户拿不到入口：

| 缺了什么 | 用户看到的 |
|---|---|
| `card_type` 用了 `image_text` / `todo_remind` | 一张纯文字卡，没有行也没有按钮，只能干看着 |
| `options` 空 | 卡上没有可勾的东西，两个按钮拼不出内容 |
| 没有 `actions` | 有清单但没有出口，点哪里都回不到会话 |

**别因为「这次只有一餐没记」就简化成一行字。** 提醒的价值全在那两个按钮上：
用户勾一下、点一下就回到会话继续；退化成文字卡之后他得自己打字，等于没提醒。

一眼分辨自己发出去的是哪种：我们的卡一定带 `source: {"label": "健康记录"}`、一定有带图的选项行、
一定有底部按钮。截图里没有这三样的那张，就不是本 Skill 发的（Todo 本身也会在 NOW 里露出来，
长得像一条纯文字提醒，那个不归这里管，也不要试图给它加按钮）。

### S1 三餐：线上验证过的真实请求

```json
{
  "card_type": "todo_choice",
  "title": "今天的三餐，看看还差哪顿",
  "summary": "9月21日 · 三餐打卡状态，可多选确认",
  "source": {"label": "健康记录"},
  "thingId": "<真实 thing_id>",
  "todoId": "todo-s1-meals",
  "actions": [
    {"action_id": "a_go_record", "label": "去记录",
     "tap": {"type": 1, "agent_chat": {}}},
    {"action_id": "a_skip", "label": "不吃了",
     "tap": {"type": 1, "agent_chat": {"send_prompt": "今天不吃"}}}
  ],
  "data": {
    "select_mode": 2,
    "options": [
      {"option_id": "breakfast", "title": "早餐",
       "desc": "已吃 · 酸辣粉+两个卤蛋，约550kcal，已记下",
       "image": "<检索到的同类菜品图>", "done": true, "selected": false},
      {"option_id": "lunch", "title": "午餐",
       "desc": "待记录 · 还没记上，拍一张我帮你算",
       "image": "<检索到的美食图>", "selected": true},
      {"option_id": "dinner", "title": "晚餐",
       "desc": "待记录 · 晚上记得拍一张",
       "image": "<检索到的美食图>", "selected": true}
    ]
  }
}
```

勾着午餐点「去记录」只回到会话，不自动发送文字，用户可直接上传照片或输入「这是我的午餐」；点「不吃了」才发送 `今天不吃午餐` 并执行跳过。
**餐次状态只在 `desc` 里，不进 `title`**——提交动作仍会把 `title` 接进句子。

图片由 `now_card` 从预设图库取，不要自己搜：**没记录**的餐次用库里该餐次的长期 HTTPS 地址；
**已记录**的只有档案里本来就是公网 https 才用那张，沙箱路径和内网短链不上卡，退回同一套预设。
也不要给没记录的餐次配一张像是吃过的图——那等于告诉用户他吃过了。库里没有地址就整行不给 `image`。

### S2 训练

同一套骨架，换成一个动作一行：`title` 只写动作名，`desc` 写组数 × 次数或秒数（照抄 `workout_today` 回执里动作的 `meta`），`image` 放标准示范图，已完成动作 `done: true`。

```json
[{"action_id": "a_adjust", "label": "改计划",
  "tap": {"type": 1, "agent_chat": {}}},
 {"action_id": "a_done", "label": "练了这些，帮我记上",
  "tap": {"type": 1, "agent_chat": {"send_prompt": "我练完了"}}}]
```

勾选臀桥和硬拉后点完成，发送 `我练完了臀桥、硬拉`；点「改计划」只回到会话，等待用户输入具体调整。未勾动作时点完成只会发送 `我练完了`，此时必须追问具体动作，不能默认整场完成。

动作多的时候按对话里那张训练卡的规矩：未完成优先，最多三行，其余在 `summary` 里带一句
「还有 N 个动作」。

## 3. 日报周报：带封面图的图文卡（`image_text`）

S3、S4 不发选择卡，发**带一张封面图的图文卡**：`card_type: "image_text"`，
封面放 `data.cover.url`，总结写在 `title` 和 `summary` 里。

```json
{
  "card_type": "image_text",
  "title": "今天的健康日报",
  "summary": "摄入 1034 kcal，能量缺口 -320 kcal；膳食纤维偏低，晚上补一份深色蔬菜。",
  "source": {"label": "健康记录"},
  "thingId": "<真实 thing_id>",
  "todoId": "todo-s3-daily",
  "tap": {"type": 1, "agent_chat": {}},
  "actions": [
    {"action_id": "a_open_report", "label": "看完整日报",
     "tap": {"type": 1, "agent_chat": {}}}
  ],
  "data": {"cover": {"url": "<预设图库里的日报封面，公网 HTTPS>"}}
}
```

**封面用预设图库里的长期 HTTPS 地址**，`now_card` 已经填进 `data.cover.url`，不要再搜、
不要换成跟本人数据相关的图。`data.cover` 是唯一放图的位置。**库里没有地址就整个 `cover` 不传**
（`data` 退回 `{}`），不要塞一个打不开的地址——加载失败比没有图更难看。

整卡 `tap` 和按钮都只回到原会话，不发送新的用户消息。日报、周报 HTML 已经在会话中，点击行为只是定位回报告上下文，不能额外上屏“看看今天的日报”“看看本周的周报”等占位文字。

`summary` 里的数字照抄 `report_daily` 回执的 `intake_kcal` / `total_burn_kcal` /
`balance_kcal`，别从卡面文案回读。周报同理，换成 `todo-s4-weekly` 和周口径的数。

### 为什么 HTML 文件不能挂在卡上

**卡上给不了 HTML 的链接，这是硬限制，不要试。** 三条都堵死了：

- **模型看不到产物地址。** `report_daily` 回给模型的只有 `report_path`，
  是沙箱路径 `/data/workspace/health-daily-2026-09-20.html`。平台确实会把产物传到 COS
  并生成 `doc_content.url`，但那是打包 FILE part 时在下游生成的，不进模型上下文
  （2026-09-21 trace：215 个 `for_model` 段里含该 URL 的是 0 个）。
- **那个地址活不过两小时。** 它是预签名 URL，`q-sign-time` 给的有效期 7200 秒。
  Now 动态会长期留在 feed 里，隔天点开就是 403。
- **没有转存工具。** 当轮 23 个工具里没有任何上传/转存能换一个长期地址。

所以 HTML 走会话这条路：报告本来就会作为附件出现在对话里。卡上整卡 `tap` 和按钮都使用空的 `agent_chat`，只负责回到原会话，不再自动发送占位消息，也不重新生成报告。

## 4. 踩过的五个坑

**① `done: true` 的项不能同时 `selected: true`。** 线上真报过
`[40001] done option cannot be selected`，整次发布失败。已完成的餐次/动作要么
`done: true, selected: false`，要么干脆不给 selected。

**② 图片必须是公网可达的 HTTPS 地址，而且用预设图库，不要现搜。** `now_card` 已经把
`assets/now_images.json` 里的长期地址填进 `image` / `cover`。不要再用 `picture_search`：
早先没点名工具时模型干脆不配图（真机复现过），搜到的又经常是打不开的短链。
`image_generation/generate` 是画图不是配图，这里不要用它。报过 `[40001] image/H5 URL must be HTTPS`。
更隐蔽的一种是**协议对了但域名不可达**：`yb-test.woa.com/xxx` 是内部短链，
卡片能提交成功但端上一张图都加载不出来，实测 HTTP 000 连不上。
沙箱里的本地文件也不行——卡片只认 URL，把图下载到沙箱并不能让它显示。
预设库里没有可用地址时，整行不给 `image`，封面则整个 `cover` 不传。

**③ 导航按钮误带 `send_prompt`，会把系统占位话术伪装成用户消息。** 例如“去记录”自动上屏“我要记午餐”，但用户真正要做的是上传照片；“看完整日报”自动上屏“看看今天的日报”，也会污染对话。导航型按钮统一使用空 `agent_chat`，只跳转。

**④ 提交按钮没有 `send_prompt`，才是「全绿的失败」。** 跳过一餐、完成所选动作这类按钮如果只跳转，业务不会执行且链路不报错。只有这类明确提交动作必须带自然语言 `send_prompt`；选择卡还要与 `option.title` 连读检查。

**⑤ 发布不幂等，且没有去重。** 成功的唯一凭据是回包里的 `now_id`
（形如 `{"now_id":"117307250507777"}`）。没有 `recommendation.id`，也没有 `deduplicated`——
同样的参数再调一次就是**另发一张卡**。所以超时或回包缺失时**不要自动重试**，
如实说发布结果未确认。

## 5. 还画不了什么

`todo_choice` 能画带图的列表，但**画不了柱状图**。所以 S3 日报、S4 周报的两张图表
仍然走工作区的 HTML 产物，Now 这边只发一条能点回会话的通知卡。

对话里的 A2UI 卡（`assets/ui/*.card.json`）和 Now 卡是**两套东西**：前者是自有组件树，
后者是平台的五种模板之一。两边的视觉不会自动一致，改了一边不等于另一边跟着变。
