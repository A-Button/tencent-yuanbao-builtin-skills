# NOW 卡片：面试提醒与职位推荐

通过 make-things 延迟加载的 `show_widget` 发布。字段契约以 make-things 的
`references/show-widget.md` 为准，本文只写求职场景怎么填。
不要额外加载卡片 Skill、不要跑 `prepare_card`、不要生成 HTML。

`show_widget` 是函数工具，不要 bash，不要 `app job-hunting show_widget`。
工具列表里没有它，说明 make-things 未挂上：如实说明发布通道不可用后结束，
不要用对话 XCard 冒充已上推荐页。

- [何时发](#何时发)
- [线格式](#线格式)
- [面试提醒 todo_remind](#面试提醒-todo_remind)
- [准备待办 todo_remind](#准备待办-todo_remind)
- [准备进度 todo_remind](#准备进度-todo_remind)
- [职位推荐 recommend_list](#职位推荐-recommend_list)
- [岗位关注](#岗位关注)
- [落盘与成功](#落盘与成功)

## 何时发

发卡是独立判断。`render_*`、写账本、「去准备」、
用户说「再搜一轮」、Trigger 到点本身，都不自动等于要发。

先过 make-things 的五条判断，任一不满足就不发：有实质变化、用户看得懂且用得上、
同一事项一天一张为上限、没料就不发、规则命中不等于要发卡。
创建不幂等也不去重，判重了就是两张卡，上限只能靠自己守。

过了五条判断后，只允许这七处：

| # | 时机 | `card_type` |
| --- | --- | --- |
| 1 | 场景 4：面试 Todo 与本批规则按实际结果落完 | `todo_remind` |
| 2 | 面试提醒 Trigger 回调：面试仍有效，倒计时或面试安排相对上次快照有实质变化 | `todo_remind` |
| 3 | 场景 5：本批面试准备项首次写入账本成功，且这场面试尚无 `prep-setup-<key>.receipt.json` 的 `now_id` | `todo_remind` |
| 4 | 一轮「去准备」推进结束或准备项被增删改，且这场面试当天还没发过进度卡 | `todo_remind` |
| 5 | 场景 5：求职任务第一次创建成功，或任务卡「跟进相关岗位」回投；意向够搜，本轮 3–5 条带 HTTPS URL 的岗位；未开启岗位关注 | `recommend_list` |
| 6 | 场景 6：岗位关注开启或替换，Todo 与规则按实际结果落完 | 按条数选，见[岗位关注](#岗位关注) |
| 7 | 场景 6：岗位关注 Trigger 到点，Web Search 成功且**有新增岗位**；或到期那一次 | 按条数选，见[岗位关注](#岗位关注) |

面试提醒卡和准备待办卡按**每场面试**各一张，用 `<company-role-round-key>` 区分回执，同一 Thing 下第二场面试重新判断。
准备进度卡按**每场面试每天**至多一张。职位卡按 Thing 算，同一天不发第二张；开启岗位关注后不再发第 5 类，岗位只走第 6、7 类。
重复点「帮我准备」只复用 Thing，不连发准备 Now，也不连发职位 Now。
到点检查完没有新增岗位属于「没料」，不发卡，只在账本里记一次检查时间。
对话里登记或查看面试安排仍走 `render_interview_reminder`，不要因此再发一张 Now。

只用 `todo_remind`、`recommend_list`，以及岗位关注里没有列表可摆时的 `image_text`。
不用 `todo_choice`、`stock`。

## 线格式

`card_type` 传字符串，不传数字。正文一律扁平放在顶层 `data` 里，**不要**包一层
`{"todo_remind": {...}}` 这样的卡型同名分支。顶层关联字段用驼峰 `thingId`、`todoId`；
`data` 内部和 `tap` 内部的字段名一律 snake_case，枚举一律数字。

```json
{
  "card_type": "todo_remind",
  "title": "字节一面还有 2 天",
  "source": {"label": "求职助手"},
  "summary": "字节产品岗一面 · 周四 15:00",
  "thingId": "真实 thing_id",
  "todoId": "真实 todo_id",
  "data": {
    "items": [{"item_id": "when", "title": "周四 15:00", "badge": {"text": "待面试", "tone": 2}}]
  }
}
```

必填：`card_type`、`title`、`data`。可选：`source`、`summary`、`actions`、`tap`、`thingId`、`todoId`。

- 公共标题、摘要、来源、按钮、整卡 tap 都在顶层，不塞进 `data`。
- ID 必须来自本轮真实回包。有 `todoId` 必须同时有 `thingId`；没有关联则两个都省略。
- **不传 `conversation_id`、`user_id`、`eventId`**，用户和会话来自可信上下文。
- 不传 `widget`、`skill_name`、`uri`、`triggerId`、`thing_id`、`todo_id`、`push`、`card_id`。
- 顶层多一个 schema 外的字段整个请求就会被拒，不是只忽略那一个字段。

标题最多两行、摘要一行，用户不点开也要看懂发生了什么。整份请求 ≤ 64KB。

点击只三处：整卡 `tap`、`actions[].tap`、`data.items[].tap`（仅 `recommend_list`）。
`todo_remind` 的行不能点。`tap.type`：`1` 回原会话（目标对象 `agent_chat`）、`2` 打开 HTTPS（目标对象 `h5`）。
一个 tap 只带一个目标对象。不要下发 `type=3` 小程序或 `type=4` 图片预览。
`h5.url` 必须是真实 HTTPS，不能是 `ui://` 或 XCard 资源。
`send_prompt` 要能独立定位公司、岗位、轮次，不用「刚才那个」这类指代。

`actions[]` 每项 `{action_id,label,tap}`，最多 2 个。`action_id` 用无语义短键（`a1`、`a2`），
不要用 `later` / `confirm` 编码行为。最后一个按钮是主按钮：「模拟面试」在前，「帮我准备 / 按岗位改简历」在后。
不传 `style`、`behavior`、`dismiss`。

## 面试提醒 todo_remind

只从面试事实投影，不要把对话 XCard 的 `countdown` 等字段原样塞进 `data`。

**这张卡只讲面试本身：什么时候、在哪、还有多久。准备项一条都不进正文**，那是准备待办卡和准备进度卡的内容，
两张都列一遍只会让用户在 Now 流里看到同样几行字。想去准备走「帮我准备」按钮。

| Now 字段 | 来源 |
| --- | --- |
| 顶层 `title` | 倒计时，如「字节一面还有 2 天」；规则未启用写「面试已记录，提醒尚未运行」 |
| 顶层 `summary` | 公司、岗位、轮次和面试时间，一行，如「字节产品岗一面 · 周四 15:00」 |
| `source.label` | 固定「求职助手」 |
| `thingId` / `todoId` | 本轮 `get_thing` 与提醒 Todo 的稳定 ID `interview-...` |
| `actions[0]` | 「模拟面试」，`type=1`，`send_prompt` 写清公司、岗位、轮次，如「请按字节产品岗一面的要求和我来一场模拟面试，一次一题，结束后复盘。」，回场景 2 |
| `actions[1]` | 「帮我准备」，`type=1`，prompt 写清公司、岗位、轮次，回场景 5 |
| `data.items[0]` | `item_id=when`，时间行；`badge.tone` 仅 1 蓝或 2 橙 |
| `data.items[1]` | `item_id=where`，形式或地点行，**仅在账本里已确认时才加**；未确认就只有一行 |
| `data.footnote` | 「提醒发出不代表已完成准备。」 |

`item_id` 只用 `when` / `where`，不要用 Trigger ID。提醒行没有 `image`、`completed`、`done` 字段，也不能带 `tap`。

规则未启用或启用失败：title 与 badge 只能写尚未运行，`badge.tone=1`，不能写「已开启」。
回调时按当前钟重算倒计时；面试 `cancelled` / `completed`、Todo 停用、规则解绑：不发。
与 `events/` 里同一场面试上一张快照相比无实质变化：不发。别场面试的快照不参与比对。

```json
{
  "card_type": "todo_remind",
  "title": "字节一面还有 2 天",
  "source": {"label": "求职助手"},
  "summary": "字节产品岗一面 · 周四 15:00",
  "thingId": "<真实 thing_id>",
  "todoId": "<interview-...>",
  "data": {
    "items": [
      {
        "item_id": "when",
        "title": "周四 15:00",
        "desc": "HR 已约定时间",
        "badge": {"text": "待面试", "tone": 2}
      },
      {
        "item_id": "where",
        "title": "线上视频面",
        "desc": "飞书会议，面试前会发链接"
      }
    ],
    "footnote": "提醒发出不代表已完成准备。"
  },
  "actions": [
    {
      "action_id": "a1",
      "label": "模拟面试",
      "tap": {"type": 1, "agent_chat": {"send_prompt": "请按字节产品岗一面的要求和我来一场模拟面试，一次一题，结束后复盘。"}}
    },
    {
      "action_id": "a2",
      "label": "帮我准备",
      "tap": {
        "type": 1,
        "agent_chat": {
          "send_prompt": "为字节产品岗一面创建或更新面试准备清单，并展示求职任务卡"
        }
      }
    }
  ]
}
```

## 准备待办 todo_remind

场景 5 本批准备项第一次写入账本成功后发，不替代对话里的求职任务 XCard，也不替代场景 4 的面试提醒 Now。

门禁，缺一条就不发：

1. 本轮实际把准备项写入了账本这场面试的 `prep_items[]`，并已重读确认。
2. 对话任务卡 `render_career_task` 已挂上。
3. `events/<thing_id>/prep-setup-<company-role-round-key>.receipt.json` 没有真实 `now_id`。另一场面试的回执不算数。

再次「帮我准备」、「去准备」、「跟进相关岗位」：不发。之后的完成与增删改走下一节「准备进度」。不要用面试提醒那套「模拟面试 / 帮我准备」。

| Now 字段 | 来源 |
| --- | --- |
| 顶层 `title` | 「<公司><轮次>准备已加入待办」，如「字节一面准备已加入待办」 |
| 顶层 `summary` | 公司岗位 + 本批准备项，一行 |
| `source.label` | 固定「求职助手」 |
| `thingId` | 本轮真实 Thing ID。准备项不是 Todo，**不传 `todoId`** |
| `actions[0]` | 「跟进相关岗位」，`type=1`，prompt 与任务卡相同 |
| `actions[1]` | 「去准备」，`type=1`，prompt 与任务卡相同 |
| `data.items` | 每条准备项一行，`item_id` 用 `prep_items[].key`，不要用 Todo 或 Trigger ID |
| `data.footnote` | 「加入待办不代表已完成准备。」 |

```json
{
  "card_type": "todo_remind",
  "title": "字节一面准备已加入待办",
  "source": {"label": "求职助手"},
  "summary": "字节产品岗一面 · STAR 案例 · 岗位追问 · 反问清单",
  "thingId": "<真实 thing_id>",
  "data": {
    "items": [
      {
        "item_id": "star",
        "title": "STAR 项目案例",
        "badge": {"text": "待准备", "tone": 2}
      },
      {
        "item_id": "jd",
        "title": "岗位追问",
        "badge": {"text": "待准备", "tone": 2}
      }
    ],
    "footnote": "加入待办不代表已完成准备。"
  },
  "actions": [
    {
      "action_id": "a1",
      "label": "跟进相关岗位",
      "tap": {
        "type": 1,
        "agent_chat": {
          "send_prompt": "根据我已确认的求职意向、意向工作城市和期望薪资，帮我跟进相关工作岗位。"
        }
      }
    },
    {
      "action_id": "a2",
      "label": "去准备",
      "tap": {
        "type": 1,
        "agent_chat": {
          "send_prompt": "请按当前面试准备任务的顺序，从第一条未完成的准备项开始带我准备"
        }
      }
    }
  ]
}
```

## 准备进度 todo_remind

Now 卡是快照，发出后不能改；进度变化只能再发一张新快照。
**同一场面试每天至多一张进度卡**，逐项推进时不要一项一张。

「去准备」连续推进时先只更新对话任务卡；等这一轮告一段落——用户说先到这、切到别的话题，
或这场面试的准备项全部完成——再按重读后的最新状态发一张汇总进度卡。

门禁，缺一条就不发：

1. 这场面试已有带真实 `now_id` 的 `prep-setup-<key>.receipt.json`；没有时先走上一节。
2. 本轮账本写入成功并已重读，且相对上一张进度快照确有变化：有准备项新写为 `done`，或新增、删除、改名了准备项。
3. 对话任务卡 `render_career_task` 已重新挂上。
4. `events/<thing_id>/` 下这场面试**今天**还没有带 `now_id` 的 `prep-update-<key>-*.receipt.json`。

当天已发过、暂停、恢复、重试写入或内容无实际变化：都不发，只更新对话任务卡。
一次推进里有多项变化只发一张，按重读后的全量状态组卡。

| Now 字段 | 来源 |
| --- | --- |
| 顶层 `title` | 有项完成且未全部完成：「<公司><轮次>准备进度 <已完成>/<总数>」；全部完成：「<公司><轮次>准备已完成」；只有增删改：「<公司><轮次>准备已更新」 |
| 顶层 `summary` | 公司岗位 + 本次变化，一行，如「字节产品岗一面 · 已完成 STAR 案例、岗位追问」 |
| `source.label` | 固定「求职助手」 |
| `thingId` | 本轮真实 Thing ID。准备项不是 Todo，**不传 `todoId`** |
| `data.items` | 重读后这场面试的全部准备项，按任务卡顺序；`done` 为 `{"text": "已完成", "tone": 1}`，`paused` 为 `{"text": "已暂停", "tone": 0}`，其余 `{"text": "待准备", "tone": 2}` |
| `data.footnote` | 未全部完成：「还剩 <n> 项待准备。」；全部完成：「本场面试准备已全部完成。」 |
| `actions` | 未全部完成：与准备待办卡相同，先「跟进相关岗位」、后「去准备」；全部完成：只留「跟进相关岗位」 |

```json
{
  "card_type": "todo_remind",
  "title": "字节一面准备进度 2/3",
  "source": {"label": "求职助手"},
  "summary": "字节产品岗一面 · 已完成 STAR 案例、岗位追问",
  "thingId": "<真实 thing_id>",
  "data": {
    "items": [
      {"item_id": "star", "title": "STAR 项目案例", "badge": {"text": "已完成", "tone": 1}},
      {"item_id": "jd", "title": "岗位追问", "badge": {"text": "已完成", "tone": 1}},
      {"item_id": "questions", "title": "反问清单", "badge": {"text": "待准备", "tone": 2}}
    ],
    "footnote": "还剩 1 项待准备。"
  },
  "actions": [
    {"action_id": "a1", "label": "跟进相关岗位", "tap": {"type": 1, "agent_chat": {"send_prompt": "根据我已确认的求职意向、意向工作城市和期望薪资，帮我跟进相关工作岗位。"}}},
    {"action_id": "a2", "label": "去准备", "tap": {"type": 1, "agent_chat": {"send_prompt": "请按当前面试准备任务的顺序，从第一条未完成的准备项开始带我准备"}}}
  ]
}
```

## 职位推荐 recommend_list

接在场景 5 `render_career_task` 成功之后，不替代任务 XCard。本节是一次性推荐，不建 Trigger；定时推送只走「岗位关注」。

门禁，缺一条就不发：

1. Thing 已定位、本批准备项已写入账本，对话任务卡已挂上。
2. `events/<thing_id>/jobs-after-task.receipt.json` 没有真实 `now_id`（第一次）。
3. `task.intent` 里用户明说过 `locations` 与 `target_roles`。缺了先问，不从简历猜。薪资有则带上，没有按不加薪资约束搜。
4. 按 [岗位发现](discovery.md) 检索并核验，得到 **3–5** 条且每条都有真实 HTTPS `source_url`。

少于 3 条、Web Search 失败或当天已有成功职位回执：对话里说一句，不发 Now，不为此再挂岗位 XCard。
用户主动「再搜」走场景 3 的对话卡。「跟进相关岗位」走本节，不走场景 3。

不要传准备项相关的 `todoId`。`item_id` 只用 `job-1` … `job-5`，同卡唯一。没有图就不传 `image`；
传时 `image` 是 URL 字符串，不是对象。没有 URL 的候选不入列。薪资写进 `desc`，Now 没有单独橙色字段。

```json
{
  "card_type": "recommend_list",
  "title": "按你的意向新找到的岗位",
  "source": {"label": "求职助手"},
  "summary": "深圳 · 前端 · 25K 以上",
  "thingId": "<刚确认的 Thing>",
  "data": {
    "items": [
      {
        "item_id": "job-1",
        "title": "腾讯 · 前端开发工程师",
        "desc": "23-35K·15薪 · 深圳 · 3-5年",
        "tap": {"type": 2, "h5": {"url": "https://真实原页"}}
      },
      {
        "item_id": "job-2",
        "title": "字节跳动 · 前端开发工程师",
        "desc": "30-45K · 深圳 · 3-5年",
        "tap": {"type": 2, "h5": {"url": "https://真实原页"}}
      },
      {
        "item_id": "job-3",
        "title": "美团 · 高级前端开发",
        "desc": "28-40K · 深圳 · 5年以上",
        "tap": {"type": 2, "h5": {"url": "https://真实原页"}}
      }
    ]
  },
  "actions": [
    {
      "action_id": "a1",
      "label": "按岗位改简历",
      "tap": {
        "type": 1,
        "agent_chat": {
          "send_prompt": "请根据这些岗位要求帮我修改简历。"
        }
      }
    }
  ]
}
```

## 岗位关注

场景 6 开启卡和每次到点卡共用本节。`thingId` 取当前 Thing，`todoId` 固定 `watch-jobs`，`source.label` 固定「求职助手」，`summary` 写关注条件，如「深圳 · 产品经理 · 25K 以上」。岗位行 `item_id` 用 `job-1` … `job-5`，薪资写进 `desc`。

按本次要展示的岗位条数选卡型：

| 条数 | `card_type` | 岗位行 |
| --- | --- | --- |
| ≥3 | `recommend_list`，3–5 条 | 每行 `tap` 为 `{"type": 2, "h5": {"url": "<source_url>"}}` |
| 1–2 | `todo_remind` | 每行 `badge: {"text": "新岗位", "tone": 1}`；提醒行不能点，靠「看看这些岗位」进对话卡 |
| 0 | `image_text`，`data` 传 `{}` | 没有列表，结论全写在 `title` 与 `summary` 里 |

**0 条不是每次都发。** 到点检查没有新增岗位属于「没料」，只把检查时间记进账本，不发卡。
只有下面两种 0 条才发 `image_text`：刚开启关注（要让用户确认关注已生效），以及截止日前最后一次推送（要告知到期、可续期）。

| 字段 | 开启卡 | 到点卡 |
| --- | --- | --- |
| `title` | 「已开始关注<城市><岗位>」 | 有新岗位：「<城市><岗位>新增 <n> 个岗位」；到期且 0 条：「<城市><岗位>关注今天到期」 |
| 展示岗位 | 本轮搜索结果 | 相对 `seen_keys` 的新增岗位 |
| `data.footnote`（仅 `todo_remind`） | 「<频率> <时刻> 推送，关注到 <M月D日>。」 | 「下次推送 <时间>，关注到 <M月D日>。」；最后一次改为「关注今天到期，可续一周。」 |
| 规则未启用 | title 改为「关注已记录，推送尚未运行」 | 不适用 |

`recommend_list` 和 `image_text` 都没有 footnote，频率与截止写进 `summary` 末尾，例如「深圳 · 产品经理 · 每天 09:00 · 关注到 9月30日」。

`actions` 至多 2 个，第二个固定「取消关注」（`send_prompt`「请取消当前的岗位关注，不再推送。」）。第一个按优先级取一项，都不满足时只放「取消关注」：

1. 最后一次推送：「续一周」，`send_prompt`「请把当前岗位关注续一周。」
2. 1–2 条新岗位：「看看这些岗位」，`send_prompt`「请展示岗位关注刚推送的新岗位，并给出投递入口。」
3. 到期且 0 条：「放宽条件」，`send_prompt`「最近没有新岗位，请帮我看看怎么放宽岗位关注的条件。」

≥3 条时岗位行本身可点，第一个按钮只在最后一次推送时出现。

```json
{
  "card_type": "todo_remind",
  "title": "深圳产品经理新增 2 个岗位",
  "source": {"label": "求职助手"},
  "summary": "深圳 · 产品经理 · 25K 以上",
  "thingId": "<真实 thing_id>",
  "todoId": "watch-jobs",
  "data": {
    "items": [
      {"item_id": "job-1", "title": "腾讯 · 产品经理", "desc": "25-40K·15薪 · 深圳 · 3-5年", "badge": {"text": "新岗位", "tone": 1}},
      {"item_id": "job-2", "title": "字节跳动 · 产品经理", "desc": "30-45K · 深圳 · 3-5年", "badge": {"text": "新岗位", "tone": 1}}
    ],
    "footnote": "下次推送 明天 09:00，关注到 9月30日。"
  },
  "actions": [
    {"action_id": "a1", "label": "看看这些岗位", "tap": {"type": 1, "agent_chat": {"send_prompt": "请展示岗位关注刚推送的新岗位，并给出投递入口。"}}},
    {"action_id": "a2", "label": "取消关注", "tap": {"type": 1, "agent_chat": {"send_prompt": "请取消当前的岗位关注，不再推送。"}}}
  ]
}
```

到期且没有新岗位时改用图文卡：

```json
{
  "card_type": "image_text",
  "title": "深圳产品经理关注今天到期",
  "source": {"label": "求职助手"},
  "summary": "深圳 · 产品经理 · 25K 以上 · 本周没有匹配的新岗位",
  "thingId": "<真实 thing_id>",
  "todoId": "watch-jobs",
  "data": {},
  "actions": [
    {"action_id": "a1", "label": "放宽条件", "tap": {"type": 1, "agent_chat": {"send_prompt": "最近没有新岗位，请帮我看看怎么放宽岗位关注的条件。"}}},
    {"action_id": "a2", "label": "续一周", "tap": {"type": 1, "agent_chat": {"send_prompt": "请把当前岗位关注续一周。"}}}
  ]
}
```

## 落盘与成功

```text
/data/user/job-hunting/events/<thing_id>/
├── interview-setup-<key>.json
├── interview-setup-<key>.receipt.json
├── interview-callback-<key>-<clock>.json
├── interview-callback-<key>-<clock>.receipt.json
├── prep-setup-<key>.json
├── prep-setup-<key>.receipt.json
├── prep-update-<key>-<clock>.json
├── prep-update-<key>-<clock>.receipt.json
├── jobs-after-task.json
├── jobs-after-task.receipt.json
├── watch-setup-<clock>.json
├── watch-setup-<clock>.receipt.json
├── watch-run-<clock>.json
└── watch-run-<clock>.receipt.json
```

`<key>` 是这场面试的 `<company-role-round-key>`，与 Todo ID `interview-<key>`、`prep-<key>-` 同源。
同一 Thing 下多场面试各存各的，不要互相覆盖，也不要拿别场的回执当门禁。
`prep-update-*` 的 `<clock>` 带日期，用来判断这场面试当天是否已发过进度卡。
职位卡按 Thing 存，不带 key。

先写完整请求，再调用 `show_widget`，再写回执。只有回包含真实 `now_id` 才报告已发布。
创建不幂等；超时或结果不确定时不要自动重试，也不要改字段再发。无法核对时说明尚未确认。
整份请求 ≤ 64KB。发布不是系统推送，发布成功也不等于用户已读或 Todo 已完成。

失败不由对话或前端补假动态。不要用 XCard 冒充已上推荐页。
不要把 `now_id`、Thing/Todo ID 写进 `state.json`。
