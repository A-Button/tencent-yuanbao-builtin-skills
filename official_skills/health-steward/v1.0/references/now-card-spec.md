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

### 按钮怎么跟对话说话

`actions[].tap.type = 1` 就是「点了往原会话发一句话」。

`type` 三个值：1 = 发消息回会话（`agent_chat.send_prompt`），2 = 开 H5（`h5.url`），
3 = 小程序（**牛仔宿主不支持，不要配**）。一个 tap 只能有一个目标对象。
按钮的主次样式由从左到右的顺序决定，不要传 `style` / `behavior`。

#### 选择卡上，`send_prompt` 要和勾选项连读成一句话

**这条是 `todo_choice` 独有的，写错了不报错，只会发出一句读不通的话。**
选择卡上的 type=1 按钮，端上发出去的内容是：

```text
send_prompt + 当前勾选且未完成的那些 option 的 title（多个用「、」连起来）
```

两段之间**不加任何标点和空格**，直接首尾相接。所以要**把 `send_prompt` 当成半句话来写**，
让它接上 `title` 正好是一句完整的人话：

| `send_prompt` | 勾了「午餐」之后实际发出的话 |
|---|---|
| ✅ `我要记` | `我要记午餐` |
| ✅ `我要跳过` | `我要跳过午餐` |
| ❌ `我要记午餐`（自己就是整句） | `我要记午餐🍱 午餐 · 待记录` |

最后那行是 2026-09-22 线上真实发生的（trace `f6ad2a44`）。模型侧收到这种粘在一起的话
**时而能认出意图、时而认不出**，表现就是「同一个按钮，有时有反应有时没反应」。

勾了两项也要读得通：`我要记` + `午餐、晚餐` = `我要记午餐、晚餐`，仍然成立。
**写之前先把两段拼起来念一遍**，念不顺就是错的。

由此对 `title` 有两条硬要求，它同时是卡面文字**和**句子的一部分：

- **只写短名词**：`早餐` / `午餐` / `晚餐` / `深蹲`。状态、份量、热量一律写进 `desc`。
- **不要带 emoji、`·`、括号**。它们在卡上好看，接进句子里就是噪声。

一项都没勾时发出去的就是那半句（`我要记`）。这时别猜他指哪一餐，回一句问清楚。

没有 `options` 的卡（`image_text` 的日报周报）没有这一层：没东西可追加，`send_prompt`
原样发出，所以那两张卡的按钮**写完整的一句话**，别写成半句。

**`agent_chat` 空对象只许出现在整卡 `tap` 上，按钮上一次都不许。** 这两个形状长得几乎一样，
差一个键就是完全不同的行为：

| 位置 | 写法 | 点下去发生什么 |
|---|---|---|
| 整卡 `tap` | `{"type": 1, "agent_chat": {}}` | 只跳回会话，**不发消息**（报告已经在会话里了，这是故意的）|
| `actions[].tap` | `{"type": 1, "agent_chat": {"send_prompt": "…"}}` | 跳回会话**并发出那句话** |

漏了 `send_prompt` 不会报错、发布照样成功、点击照样跳转——**用户看到的就是「跳过去了但什么都没发生」**。
本文第 3 节那张日报卡里同时有这两种写法，照抄时别把整卡那个空对象顺手抄到按钮上。
发之前把每个 `actions[].tap.agent_chat` 过一遍，确认都带着非空的 `send_prompt`。

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
     "tap": {"type": 1, "agent_chat": {"send_prompt": "我要记"}}},
    {"action_id": "a_skip", "label": "不吃了",
     "tap": {"type": 1, "agent_chat": {"send_prompt": "我要跳过"}}}
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

勾着午餐点「去记录」，发回会话的就是 `我要记午餐`；点「不吃了」是 `我要跳过午餐`。
**餐次状态只在 `desc` 里，不进 `title`**——`title` 要接进句子。

图片由 `now_card` 从预设图库取，不要自己搜：**没记录**的餐次用库里该餐次的长期 HTTPS 地址；
**已记录**的只有档案里本来就是公网 https 才用那张，沙箱路径和内网短链不上卡，退回同一套预设。
也不要给没记录的餐次配一张像是吃过的图——那等于告诉用户他吃过了。库里没有地址就整行不给 `image`。

### S2 训练

同一套骨架，换成一个动作一行：`title` **只写动作名**（它要接进句子，见上面那节），
`desc` 写组数 × 次数或秒数（照抄 `workout_today` 回执里那个动作的 `meta`，不要自己凑），
`image` 放该动作的标准示范图，已完成的动作 `done: true`。两个按钮同样是冒号前缀：

```json
[{"action_id": "a_adjust", "label": "改计划",
  "tap": {"type": 1, "agent_chat": {"send_prompt": "我想调整"}}},
 {"action_id": "a_done", "label": "练了这些，帮我记上",
  "tap": {"type": 1, "agent_chat": {"send_prompt": "我练完了"}}}]
```

勾了臀桥和硬拉再点第二个，发回来的是 `我练完了臀桥、硬拉`；点第一个是 `我想调整臀桥、硬拉`。
**一项都没勾时发出去的就是那半句**（`我练完了`），这时别去猜他练了什么，回一句问他是哪几个。

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
  "tap": {"type": 1, "agent_chat": {"send_prompt": "看看今天的日报"}},
  "actions": [
    {"action_id": "a_open_report", "label": "看完整日报",
     "tap": {"type": 1, "agent_chat": {"send_prompt": "看看今天的日报"}}}
  ],
  "data": {"cover": {"url": "<预设图库里的日报封面，公网 HTTPS>"}}
}
```

**封面用预设图库里的长期 HTTPS 地址**，`now_card` 已经填进 `data.cover.url`，不要再搜、
不要换成跟本人数据相关的图。`data.cover` 是唯一放图的位置。**库里没有地址就整个 `cover` 不传**
（`data` 退回 `{}`），不要塞一个打不开的地址——加载失败比没有图更难看。

**整卡 `tap` 和按钮都发同一句话**（日报 `看看今天的日报`，周报 `看看本周的周报`）：
点卡面任何位置都回到会话并把这句话发出去，模型接住再把报告讲一遍。两处写成同一句，
改文案时不会只改一半。

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

所以 HTML 走会话这条路：报告本来就会作为附件出现在对话里。卡上**整卡 `tap` 和按钮都带
`send_prompt`**（`看看今天的日报` / `看看本周的周报`），点哪儿都回到会话并把这句话发出去，
模型接住之后把报告讲一遍、需要时重出一份——比一个隔天就 403 的链接可靠。

**这张卡上不许出现空的 `agent_chat`。** 空对象只跳转不发话，用户点完什么都没发生。
空对象只在「就是要纯跳转」时才用，本卡不属于那种情况。

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

**③ 选择卡的 `send_prompt` 写成整句，会发出一句读不通的话。** 2026-09-22 线上实例
（trace `f6ad2a44`）：按钮是 `我要记午餐`，勾选项 title 是 `🍱 午餐 · 待记录`，
用户收到的是 `我要记午餐🍱 午餐 · 待记录`。端上把两段直接首尾相接，不加标点。
现象是**同一个按钮时而有反应时而没反应**——发出去的话随勾选变化，模型有时认得出意图有时认不出。
改法见「选择卡上，`send_prompt` 要和勾选项连读成一句话」：`send_prompt` 写半句（`我要记`），
`title` 只写短名词（`午餐`），拼起来是 `我要记午餐`。

**④ 按钮的 `agent_chat` 漏了 `send_prompt`，是一种「全绿的失败」。** 发布回包有 `now_id`、
点击也确实跳回了会话，只是那句话没发出去，链路上没有任何一处会报错——只有用户会发现
「点了没反应」。

**⑤ 发布不幂等，且没有去重。** 成功的唯一凭据是回包里的 `now_id`
（形如 `{"now_id":"117307250507777"}`）。没有 `recommendation.id`，也没有 `deduplicated`——
同样的参数再调一次就是**另发一张卡**。所以超时或回包缺失时**不要自动重试**，
如实说发布结果未确认。

## 5. 还画不了什么

`todo_choice` 能画带图的列表，但**画不了柱状图**。所以 S3 日报、S4 周报的两张图表
仍然走工作区的 HTML 产物，Now 这边只发一条能点回会话的通知卡。

对话里的 A2UI 卡（`assets/ui/*.card.json`）和 Now 卡是**两套东西**：前者是自有组件树，
后者是平台的五种模板之一。两边的视觉不会自动一致，改了一边不等于另一边跟着变。
