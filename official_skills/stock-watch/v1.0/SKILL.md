---
name: stock-watch
description: AI 盯盘助手（make-things 垂直场景）。个股（A股/港股/美股）的看盘与长期盯盘：给几只票下操作建议、盯盘中异动、到价/止损提醒、查公告新闻研报、每晚收盘后推当日盘面与资讯日结。结论与行情由本技能渲染成主对话卡片；Thing/Todo/Trigger 与 Now 动态走 make-things。不用于下单交易，也不用于全市场选股筛股。
keywords:
  - 盯盘
  - 盯盘卡
  - 到价提醒
  - 止损提醒
  - 异动
  - 收盘日报
  - 资讯汇总
packageType: app-skill
instructionOnly: false
metadata:
  version: v3.6-cowboy
---

# AI 盯盘助手

## 出卡（第一条就照做，不要找 app）

沙箱里没有 `app`、也没有 `/data/skills/bin/app`（exit 127）。不要去 `/nix` 里找。
找不到 `app` 不是读不到数据，也不是环境坏了。

**进了这个技能、有行情或结论可展示，就要出卡片。** 不要只回文字。

```bash
python3 /data/skills/stock-watch/scripts/_run.py <tool> '<json>'
```

例：咨询完用 `show_advice`，只看行情用 `show_quote`。`_run.py` 的原始 stdout 会追加
`__ONEAGENT_APP_RESULT__`，宿主随后消费它并转成 `app.data`；模型通常只看到第一行
业务 JSON 和 `[Command finished with exit code 0]`。这是正常成功结果，**不要因为模型
输出里没有 sentinel 而重跑或误报失败**。一条 bash 只跑一个 `_run.py`，单独一行，不要接管道。

**出卡不用再额外 `load_skill`。** 卡资源（`app.resource_list`）跟这份 SKILL.md 在同一个包里，
本技能一加载就随着下发了。直接跑上面那条 python3，也不要为了「确认卡资源在」再加载一次自己。
用户反馈「卡没出来」时重跑那条命令即可。

**不要去搜工具名，那条 python3 就是出卡。** 出卡不是一个能被 `tool_search` 搜到的工具——
搜 `bash` 会返回 0 条，然后你会以为环境坏了。它就是上面那行命令，照着跑。

> **本包之外没有第二个盯盘卡技能可加载。** 出卡所需的一切——三份组件树、`app.yaml`、
> `_run.py`——都在本包里。旧版把卡拆成了一个独立技能，需要每回合先加载它；那个技能
> 已经并进来并下线，再去加载会失败，卡也不会出。看到旧文档或旧会话里那种两步写法，
> 一律按这份为准：**加载本技能 → 直接跑上面那条 python3**，中间没有第二次加载。
>
> 沙箱脚本路径现在是 `/data/skills/stock-watch/scripts/_run.py`，`envelope.app.id` 是
> `stock-watch`，卡资源 URI 是 `ai_apps.skills.stock_watch_{main,advice,news}_res`。

只在已配置本 Skill 和 make-things 牛仔版的 Agent 使用。各 Skill 加载版本以本轮已发布配置为准。
（下文凡提到「牛仔端 / 牛仔宿主 / 牛仔 Thing」，说的都是**运行环境**的行为差异，与本包叫什么无关。）

**分工**：本 Skill 一身两职——既决定分析口径、观察条件、Todo 和何时发布，也自带出盯盘卡的
`_run.py`（事件标题 + 名称代码 + 现价涨跌 + 两个后续动作）；make-things 管 Thing/Todo/Trigger
与 show_widget。**stock-kline 渲染卡当前出不来**——可以 `westock kline` 取数写进分析，但不要
`load_app` / `emit_kline.py` 去出那张图。**westock-data 是数据来源**（行情、K 线、技术指标、
资金流向、新闻、公告、研报、事件、财务、评级）。westock-data 不是另一层场景编排。

**四个场景**（细节与命令见 [references/data-recipes.md](./references/data-recipes.md)）：

1. **咨询建议** —— 多源取数 + 给操作建议，答完主动询问是否创建盯盘 Thing。不出 K 线渲染卡。
2. **异动监控** —— 标的已在盯盘 Thing 下，按 Judge 判异动（量比+涨跌幅），命中发动态到 Now。
3. **到价提醒** —— 用户要监控某价位时，在该股票监控 Thing 下建到价 Trigger，命中发动态。
4. **资讯查询** —— 问公告/新闻/研报时，westock news 为主 + web_search 兜底，整理成 item 卡片回答；另有每晚汇总/盘中即时主动推送。

## 内部 JSON 与用户交付

卡片请求、工具回包、setup 记录及回调事件 JSON 都是内部执行数据，不是用户交付物。除非用户明确要求导出，否则不得把它们作为下载链接、附件、文件卡片或原始 JSON 代码块交付。主对话仍通过 `_run.py` 出卡，Now 动态仍通过 `show_widget` 发布，执行结果用自然语言说明；不得为隐藏 JSON 而截断、重定向或吞掉 `_run.py` 的 stdout / sentinel。

需要保存发布请求与真实回执时，遵循 [references/triggers.md](./references/triggers.md) 的内部记录约定。不得用 `tee` 或重定向把内部 JSON 写到 `/data/workspace` 等会被自动收集为附件的产物位置，也不得仅靠隐藏文件名或更换扩展名规避。用户明确要求导出时，另行生成所需导出文件，不把内部执行记录直接充当交付物。

## 细则在哪一份

这份只管路由：进了技能先出卡、四个场景各是什么。**具体怎么写、写多长、什么时候发，
一律去对应的 reference 查，不要凭印象写**——下面每一份都是被线上问题反复修出来的。

| 你要做什么 | 去哪一份 |
|---|---|
| 出主对话盯盘卡：什么时候出哪张、数据时刻怎么取 | [references/main-chat-cards.md](./references/main-chat-cards.md) |
| 那张卡的字段怎么填、配色口径、六个工具的完整示例 | [references/card-tools.md](./references/card-tools.md) |
| 发 Now 动态：选卡型、发几张、什么时候发 | [references/now-cards.md](./references/now-cards.md) |
| 走某个场景：咨询 / 异动 / 到价 / 资讯的完整步骤 | [references/scenarios.md](./references/scenarios.md) |
| 建 Thing/Todo/Trigger、命中后回调、用户改主意 | [references/triggers.md](./references/triggers.md) |
| 取数：三条通道的分工、westock 逐场景命令配方 | [references/data-recipes.md](./references/data-recipes.md) |
| 链路验收 | [references/acceptance.md](./references/acceptance.md) |
| 为什么不能用 `app <id> <tool>` 那套写法 | [references/cli-alias.md](./references/cli-alias.md) |

**卡的两份分工**：`main-chat-cards.md` 回答「这一步该不该出卡、出哪张」，
`card-tools.md` 回答「这张卡每个字段填什么」。字段口径以后者为准。

三条最容易踩空、放在这儿免得漏看：

- **Now 卡和主对话 A2UI 卡是两套东西。** Now 走 make-things 的 `show_widget` 五选一，
  A2UI 走 `_run.py`。改一边不等于另一边跟着变，任何 Now 字段里都不要写 `stock-watch`。
- **出卡不等于发动态。** 出卡是主对话那张 A2UI，发动态是 Now。发动态的时机见
  [now-cards.md](./references/now-cards.md) 和 [triggers.md](./references/triggers.md)，
  别把两件事当一件做。
- **Now 卡的入参一律由脚本生成，不要手拼 JSON。** `now_board.py` / `now_news.py` /
  `now_stock.py` 三个脚本各管一种卡，把打印出来的那行原样丢给 `show_widget`。手拼过两次，
  两次都拼串了（署名用错、标题自己编、解读被挤掉）。
- **要说「现在几点」「开没开盘」「下次几点触发」，先取钟,不要凭上下文推。**
  系统提示里只有日期、没有墙上时钟,而会话历史里的时间戳是**上一轮**的——照着它答,
  就会出现 09-23 上午 11:17 回你「现在是 09-22 19:53,休市状态」(2026-09-23 实际发生)。
  盘中被说成休市,后面整段判断跟着错。

  ```bash
  TZ='CST-8' date '+%Y-%m-%d %H:%M %A'
  ```

  只用 `TZ='CST-8'` 这个 POSIX 偏移。沙箱里没有 zoneinfo，换成 IANA 时区名
  （`Asia/Shanghai` 那种写法）会被静默忽略、回落到 UTC——差 8 小时，而且不报错。**这跟 `as_of` 是两回事**:`as_of` 写行情数据时刻、永远来自取数返回值,
  取钟只用来回答「此刻」和判断交易时段,不许拿它填进卡里。

- **规则把你叫醒，不等于该说话。** 没命中或不在交易时段 → **对用户零输出**
  （一个可见字符都不能有）。「静默结束」「不取数不发卡不通知」「规则保持启用」
  全算违规——嘴上说不通知，会话里已经推了。详见
  [triggers.md](./references/triggers.md)「被叫醒不等于该说话」一节。

- **异动一天只报一次。** 命中后那条规则自己停用，次日由 20:00 日结恢复——当日涨跌幅
  是累计值，上午到了 +6% 后面每小时都还是 +6%，不停就会报一整天。卡上要说明
  「今日不再重复提醒，明天开盘恢复」。

- **异动是定时轮询判出来的，不是行情推过来的。** 最快每小时一跳，没有去重也没有冷却，
  判据和代价见 [triggers.md](./references/triggers.md)。
