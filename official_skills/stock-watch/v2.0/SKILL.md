---
name: stock-watch
description: AI 盯盘助手 + 金融数据查询（make-things 垂直场景，内置 westock CLI）。两大用途：(1) 个股（A股/港股/美股）看盘与长期盯盘——给操作建议、盯盘中异动、到价/止损提醒、查公告新闻研报、每晚收盘后推当日盘面与资讯日结；结论与行情渲染成主对话卡片，Thing/Todo/Trigger 与 Now 动态走 make-things。(2) 金融市场结构化数据查询——股票（A股/港股/美股/日韩股）、ETF、指数、板块、期货、外汇、可转债的行情、财报、研报、新闻、公告、事件、股东、分红、ETF持仓、热搜榜、新股/投资日历、龙虎榜，以及行业经营数据、申万行业估值/盈利预测/财务、全球宏观经济。取数一律 CLI 优先、web_search 兜底。不用于下单交易；筛股用 westock-screener。
keywords:
  - 盯盘
  - 盯盘卡
  - 到价提醒
  - 止损提醒
  - 异动
  - 收盘日报
  - 资讯汇总
  - 行情查询
  - 财报
  - K线
  - 资金流向
  - 龙虎榜
  - 宏观数据
  - ETF
packageType: app-skill
instructionOnly: false
metadata:
  version: v3.34-cowboy
---

# AI 盯盘助手

## 出卡（第一条就照做，不要找 app）

沙箱里没有 `app`、也没有 `/data/skills/bin/app`（exit 127）。不要去 `/nix` 里找。
找不到 `app` 不是读不到数据，也不是环境坏了。

**进了这个技能、有行情或结论可展示，就要出卡片。** 不要只回文字。

```bash
python3 /data/skills/stock-watch/scripts/_run.py <tool> '<json>'
```

例：问盘面必须 `show_quote`，问资讯必须 `show_news`。一轮主对话只出一张 xcard，两种不要一起出。操作建议写在正文，不要 `show_advice`，也不要因此把该出的那张卡省掉。`_run.py` 的原始 stdout 会追加
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

**分工**：本 Skill 决定分析口径、观察条件、Todo 和何时发布，也自带 `_run.py` 出主对话卡。make-things 管 Thing/Todo/Trigger 与 `show_widget`。**stock-kline 渲染卡当前出不来**——可以 `westock kline` 取数写进分析，但不要 `load_app` / `emit_kline.py` 去出那张图。westock-data 只提供行情和资讯，不负责编排。

## 这一轮走哪条

先认这一轮是下面哪一件事，只走那一条。主对话一轮只出一张 xcard。步骤以表里那一份为准，别在这里现编。

| 这一轮 | 主对话 | Now | 步骤 |
|---|---|---|---|
| 看看盘面、看看股票、现在怎么样、要操作建议 | `show_quote`。不要 `show_news`，不要 `show_advice` | 本会话还没发过股票 Now 卡，发 1 张 `stock`。已经发过，这一轮又不是再问盘面，就不发 | [scenarios.md](./references/scenarios.md) 场景一 |
| 问公告、新闻、研报，或资讯总结 | `show_news`。不要 `show_quote` | 问的是总结、且已有盯盘 Thing，才发 1 张资讯 `recommend_list`。问某一条细节不发 | [scenarios.md](./references/scenarios.md) 场景四 |
| 用户要盯、创建 Thing | 按上面两行只出一张。**必须加载 make-things 并把 Thing 建上**，默认异动监控和每晚 20:00 日结。没拿到真实 ID 不能写「已创建」 | 本会话还没发过股票 Now 卡就发 1 张 `stock`。先看盘已经发过，创建这轮不要再发 | [triggers.md](./references/triggers.md)「创建」 |
| 到价或异动把你叫醒 | 再跑一次 `check_anomaly`。`triggered` 才出卡：到价 `show_alert_hit`，异动 `show_anomaly`。不是 true 就不写说明 | 同样才发 1 张 `stock`，只放命中的那一只 | [triggers.md](./references/triggers.md)「回调与动态」 |
| 每晚 20:00 日结 | 日结写在正文 | 先 1 张 `stock`，再 1 张盘面总结。资讯 Todo 没挂上就不搜；挂上了才搜，和已推过的做差，有新的才发 | [now-cards.md](./references/now-cards.md) |

字段怎么填看 [card-tools.md](./references/card-tools.md)，取数命令看 [data-recipes.md](./references/data-recipes.md)。

## 内部 JSON 与用户交付

卡片请求、工具回包、setup 记录及回调事件 JSON 都是内部执行数据，不是用户交付物。除非用户明确要求导出，否则不得把它们作为下载链接、附件、文件卡片或原始 JSON 代码块交付。主对话仍通过 `_run.py` 出卡，Now 动态仍通过 `show_widget` 发布，执行结果用自然语言说明；不得为隐藏 JSON 而截断、重定向或吞掉 `_run.py` 的 stdout / sentinel。

需要保存发布请求与真实回执时，遵循 [references/triggers.md](./references/triggers.md) 的内部记录约定。不得用 `tee` 或重定向把内部 JSON 写到 `/data/workspace` 等会被自动收集为附件的产物位置，也不得仅靠隐藏文件名或更换扩展名规避。用户明确要求导出时，另行生成所需导出文件，不把内部执行记录直接充当交付物。

## 漏看就会发错

这几条不在表里展开，但只读了入口也会踩到。细则仍以链接那份为准。

- **Now 和主对话卡是两套。** 主对话走 `_run.py`，Now 走 `show_widget`。任何 Now 字段里都不要写 `stock-watch`。入参用 `now_stock.py` / `now_board.py` / `now_news.py` 打出来的那一行，不要手拼。协议以本轮 make-things 的 `references/show-widget.md` 为准。
- **资讯不要装进股票卡。** 股票卡只能画报价。资讯总结走 `now_news.py`。
- **要说「现在几点」「开没开盘」「下次几点触发」，先取钟，不要凭上下文推。** 系统提示里只有日期、没有墙上时钟，而会话历史里的时间戳是**上一轮**的。照着它答，就会把盘中说成休市。

  ```bash
  TZ='CST-8' date '+%Y-%m-%d %H:%M %A'
  ```

  只用 `TZ='CST-8'` 这个 POSIX 偏移。沙箱里没有 zoneinfo，换成 IANA 时区名（`Asia/Shanghai` 那种写法）会被静默忽略、回落到 UTC。**这跟 `as_of` 是两回事**：`as_of` 写行情数据时刻、永远来自取数返回值，取钟只用来回答「此刻」和判断交易时段，不许拿它填进卡里。
- **说了盯盘就必须建上。** 用户说盯、帮我盯、加入盯盘：加载 make-things，按 [triggers.md](./references/triggers.md)「创建」跑完。回包里有真实 `thing_id`，异动规则和 20:00 日结都已启用，才能写「已创建 / 已纳入盯盘 / 已开启」。工具没调就写这些完成态，是错的。2026-09-28「帮我盯平潭发展、特斯拉、Burberry」只出了行情卡和一段「已为你创建」，全程没加载 make-things。
- **异动没命中不进主对话。** 必须建成带 `check_anomaly` 的 judge，`schedule.rrule` 为 `FREQ=HOURLY`，不是不带 judge 的 Timer，也不是让判定模型自己读 `stock_market_data`。没命中不投递 prompt，会话里没有这一轮。误唤醒后复核 `triggered` 不是 true：不发卡，直接结束，不要写说明。复核取数失败（`phase` 为 error）只在正文写失败原因，不发卡。详见 [triggers.md](./references/triggers.md)「没命中就什么都不发生」。
- **异动一天只报一次。** 命中后那条规则自己停用，次日由 20:00 日结恢复。它是定时轮询判出来的，不是行情推过来的，最快每小时一跳。判据见 [triggers.md](./references/triggers.md)。
