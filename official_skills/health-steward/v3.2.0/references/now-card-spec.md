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
| 只跳转，不自动上屏 | `{"type": 1, "agent_chat": {}}` | 这几张健康卡的按钮都不用空跳转 |
| 跳转并上屏一句用户的话 | `{"type": 1, "agent_chat": {"send_prompt": "…"}}` | 点击本身已经把这句话交给会话 |

上屏的那句话用产品定的这几句，不要改成「我要记午餐」「看看今天的日报」这类别的说法。

#### 不要用选择卡

`todo_choice` 会画出勾选框，并且把端上发出的内容拼成：

```text
send_prompt + 当前勾选且未完成的 option.title（多个用「、」连接）
```

两段之间不加标点或空格。三餐和训练都不要用这张卡。`select_mode` 是数字（1 单选，2 多选），但配了它就会出现勾选框。

| 按钮 | `send_prompt` | 上屏文字 |
|---|---|---|
| 去记录（三餐） | `这是我今天的午餐` | 就是这一句。推荐列表不会再拼接餐次名 |
| 不吃了 | `今天不吃午餐` | 就是这一句。早餐、晚餐换成对应餐次 |
| 去记录（训练） | `我今天练了这些：臀桥、硬拉` | 就是这一句。推荐列表不会再拼接动作名 |
| 改计划 | `我想调整今天的训练计划` | 就是这一句。还没说改哪一项，先问，不要当成练完 |

点完 Now 卡不会改自己，对话里记完也不会写回这张卡。

日报、周报不是推荐列表，按钮上的 `send_prompt` 就是完整的一句：日报「我要看今天的健康日报」，周报「我要看本周的健康周报」。整卡点击用同一句。

## 2. 三餐和训练都用推荐列表

`recommend_list` 的 `data.items` 一行一个：`item_id`、`title`，可选 `desc`、`image`（URL 字符串）。没有 `select_mode`、`selected`、`done`，也就没有勾选框。

### 三餐必须有一行和两个按钮，不许退化成纯文字

**S1 三餐只有一种合法形态：`recommend_list` + 只有这一餐的 `items` + 两个按钮。**
少了行或按钮就发不出去——这里说的不是报错，是发得出去但用户拿不到入口：

| 缺了什么 | 用户看到的 |
|---|---|
| `card_type` 用了 `image_text` / `todo_remind` | 一张纯文字卡，没有行也没有按钮，只能干看着 |
| `card_type` 用了 `todo_choice` | 右侧多出一个勾选框，点按钮还会把餐次名再接一次 |
| `items` 空 | 卡上没有这一餐 |
| 没有 `actions` | 有标题但没有出口，点哪里都回不到会话 |

**别把三餐收成没有按钮的纯文字。** 一次只提醒一餐，就只列这一行，不要把另外两餐也列上。两个按钮上的话已经写完整。「去记录」上屏「这是我今天的午餐」，「不吃了」上屏「今天不吃午餐」（早餐、晚餐换成对应餐次）。

一眼分辨自己发出去的是哪种：我们的卡一定带 `source: {"label": "健康记录"}`、一定有底部按钮。
训练卡和三餐卡都有带图的行。三餐那张图是占位，只留在 Now 卡上，不要带进主对话。截图里没有来源和按钮的那张，就不是本 Skill 发的
（Todo 本身也会在 NOW 里露出来，长得像一条纯文字提醒，那个不归这里管，也不要试图给它加按钮）。

### S1 三餐：推荐列表，没有勾选框

```json
{
  "card_type": "recommend_list",
  "title": "今天的午餐",
  "summary": "9月21日 · 还没记",
  "source": {"label": "健康记录"},
  "thingId": "<真实 thing_id>",
  "todoId": "todo-s1-meals",
  "actions": [
    {"action_id": "a_go_record", "label": "去记录",
     "tap": {"type": 1, "agent_chat": {"send_prompt": "这是我今天的午餐"}}},
    {"action_id": "a_skip", "label": "不吃了",
     "tap": {"type": 1, "agent_chat": {"send_prompt": "今天不吃午餐"}}}
  ],
  "data": {
    "items": [
      {"item_id": "lunch", "title": "午餐",
       "desc": "待记录 · 拍一张我帮你算"}
    ]
  }
}
```

只列这一餐。点「去记录」发送 `这是我今天的午餐`。这句话本身还没有食物也没有图，不要立刻记录、不要出卡；等用户拍一张或说出吃了什么，再 `diet_record`，有图带上 `photoUrl`，那一轮出饮食卡。点「不吃了」发送 `今天不吃午餐` 并执行跳过。推荐列表不会把餐次名再接到这两句后面。

这一餐还没记，行上的 `image` 是预设占位图，只给 Now 卡用。`send` 为 true 时回执另有一句 `chat_note`：主对话只看那句，不要再写一段提醒，不要把这张图贴进正文，不要写 `<media_info>`，不要调 `image_generation`。禁止把 `show_widget` 参数、回执或历史里的 `image` 地址抄进正文、`<media_info>`、`present_files` 或 `photoUrl`。这些图不是用户拍的，不是这一餐。`photoUrl` 只接受用户本轮刚上传的图。不要搜图，不要换图。沙箱路径和内网短链不上卡。

### S2 训练：推荐列表，没有勾选框

训练不用 `todo_choice`。那种卡一定会画出勾选框，点「去记录」时把勾中的动作名再接到按钮句子后面。改用 `recommend_list`：一行一个未完成的动作，有示范图，没有 `select_mode`、`selected`、`done`。底部仍是两个按钮。不要改成 `image_text` 或 `todo_remind`，那两种没有带图的动作行。

```json
{
  "card_type": "recommend_list",
  "title": "今天的训练",
  "summary": "09-21 · 今日训练",
  "source": {"label": "健康记录"},
  "actions": [
    {"action_id": "a_go_record", "label": "去记录",
     "tap": {"type": 1, "agent_chat": {"send_prompt": "我今天练了这些：臀桥、硬拉"}}},
    {"action_id": "a_adjust", "label": "改计划",
     "tap": {"type": 1, "agent_chat": {"send_prompt": "我想调整今天的训练计划"}}}
  ],
  "data": {
    "items": [
      {"item_id": "ex-1", "title": "臀桥", "desc": "3组 × 12次", "image": "<该动作的预设图>"},
      {"item_id": "ex-2", "title": "硬拉", "desc": "3组 × 8次", "image": "<该动作的预设图>"}
    ]
  }
}
```

未完成的动作全部列上，一行一个，不截成三行。已完成的不放进行里，在 `summary` 里写「已完成 N 个」。排期里的动作都完成了就不要发。点「去记录」发送的就是按钮上这一句，例如 `我今天练了这些：臀桥、硬拉`，和卡上每一行一致，不会再拼接。一句里没有动作名、只收到 `我今天练了这些：` 时追问具体动作，不能默认整场完成。点「改计划」上屏「我想调整今天的训练计划」。这句话还没说改哪个动作、改组数次数还是负重，先问清楚再调 `workout_adjust`，不要当成练完。`show_widget` 没有卡内滑动字段，行多了整张卡变高，由此刻页往下滚。

点下去只把这句话送进对话。这张 Now 卡不会跟着改，对话里记完也不会写回这张卡。

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
  "tap": {"type": 1, "agent_chat": {"send_prompt": "我要看今天的健康日报"}},
  "actions": [
    {"action_id": "a_open_report", "label": "看完整日报",
     "tap": {"type": 1, "agent_chat": {"send_prompt": "我要看今天的健康日报"}}}
  ],
  "data": {"cover": {"url": "<预设图库里的日报封面，公网 HTTPS>"}}
}
```

**封面用预设图库里的长期 HTTPS 地址**，`now_card` 已经填进 `data.cover.url`，不要再搜、
不要换成跟本人数据相关的图。`data.cover` 是唯一放图的位置。**库里没有地址就整个 `cover` 不传**
（`data` 退回 `{}`），不要塞一个打不开的地址——加载失败比没有图更难看。

整卡 `tap` 和按钮都回到原会话，并上屏这一句：日报是「我要看今天的健康日报」，周报是「我要看本周的健康周报」。不要改成「看看今天的日报」。收到之后把已经生成的报告讲出来，不要再出饮食卡。

`summary` 里的数字照抄 `report_daily` 回执的 `intake_kcal` / `total_burn_kcal` /
`balance_kcal`，别从卡面文案回读。周报同理，换成 `todo-s4-weekly` 和周口径的数。

### 为什么 HTML 文件不能挂在卡上

**卡上给不了 HTML 的链接，这是硬限制，不要试。** 三条都堵死了：

- **HTML 不挂在 Now 卡上，用 `present_files` 交到同一轮对话。** `send` 为 true 时 `now_card` 回执带 `report_path`，例如 `/data/workspace/health-daily-2026-09-20.html`。把 `show_widget` 发出之后，调一次 `present_files`，`files` 里只放这个路径的原文。不要改成下划线文件名，也不要自己编路径。不要自己编 `<media_info>`；工具回执若要求终稿再写，路径必须与 `files` 里那条完全相同。平台把产物传到 COS 并生成 `doc_content.url`，那个地址不进模型上下文（2026-09-21 trace：215 个 `for_model` 段里含该 URL 的是 0 个）。
- **那个地址活不过两小时。** 它是预签名 URL，`q-sign-time` 给的有效期 7200 秒。
  Now 动态会长期留在 feed 里，隔天点开就是 403。
- **没有转存工具。** 当轮 23 个工具里没有任何上传/转存能换一个长期地址。

所以 HTML 走会话这条路：报告本来就会作为附件出现在对话里。卡上整卡和按钮都带上面那句上屏文字，把人带回原会话看这份报告，不在卡上挂链接。

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

**③ 上屏文案不要换成另一句。** 「去记录」发出去的就是按钮上那句：「这是我今天的午餐」或「我今天练了这些：臀桥、硬拉」，不是「我要记午餐」。「不吃了」发出去的是「今天不吃午餐」。三餐和训练都用推荐列表，不要改成选择卡，否则端上会把餐次名或动作名再接一次。「看完整日报」上屏「我要看今天的健康日报」，不是「看看今天的日报」。「改计划」上屏「我想调整今天的训练计划」，不要留空。

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
