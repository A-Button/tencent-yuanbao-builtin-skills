# 排盘与首次回答

提取用户已有的原始出生字段，直接运行本入口；不搜索、手算或先选择时间流派。脚本处理历法、时区、范围和缺项，返回后按动作继续。

```bash
python3 scripts/chart_quick.py <<'JSON'
{"mode":"bazi","birth_date":"1992-09-15","birth_city":"杭州","birth_time":"14:30"}
JSON
```

普通“排盘／看看八字／看看星盘”默认给概要与简要分析，再附盘面。明确只要盘面时传 `include_summary=false`；明确一句话、分析或深报时使用对应 artifact。资料缺失仍用同一入口，不先制作问卷。日期用所选历法的 YYYY-MM-DD；时辰、范围、大约／左右、未知等原意保留，不补中点。

西占 HTML 展示已核验的太阳、上升、月亮、金星、水星位置、太阳简述、四项速览短标签与必要的不确定说明，不输出逐项详细解读卡。独立星座页可由用户点击生成本地 PNG 并保存或分享。默认的西占配置关系分析由模型读取 `before_delivery.analysis_charts.western` 写在同一回复正文中，然后附排盘 HTML；内容标准见 [western-report.md](western-report.md)。

| 字段 | 输入／默认值 |
|---|---|
| `mode` | bazi（默认）／western／combined |
| `birth_date`、`birth_city`、`birth_time` | 已有日期、城市、时间原文；缺失省略或 null |
| `calendar`、`lunar_is_leap_month` | 默认 gregorian；农历 lunar，闰月复用已知 true/false |
| `artifact` | chart（默认）／conclusion／analysis／report |
| `include_summary` | 默认 true；明确只要盘面才 false，不影响显式 conclusion/analysis |
| `question`、`topics` | 已有问题和主题 ID；不为填满字段追问 |
| `offer_report` | 默认 true；明确只要盘面或拒绝后续报告时 false |
| `omit_luck_cycle` | 默认 false；用户明确拒绝八字深报大运时 true |
| `gender_for_bazi`、`include_luck_cycles` | 仅复用主动提供的 male/female；明确要求盘面大运才 true，不询问或阻塞首盘 |
| `time_prompted` | 默认 false；续接保留返回值，不重置 |

主题 ID 为 career/emotion/family/economy/social/talent/spiritual/study/health。完整 Schema 见 [chart-request.schema.json](../scripts/chart-request.schema.json)，正常调用无需另读。

## 按返回动作继续

- `ask`：将返回问题交给宿主真实的 ask_user_question／ask-user-question。标题引导填写，真实选项正常提供，可选“不清楚 / 不想说”，输入栏接受自由文本；无需专用填空控件。工具不可用或确实无法承载所需输入时，用一条普通消息。保留 `resume_request`，只覆盖用户已回答字段及选项的 patch；跳过时间按日期级继续，跳过必需日期／地点则说明无法完成计算，不重复逼问或伪造值。
- `resolve_city`：由宿主可靠解析城市，只补 resolution 的 timezone/location（坐标成对选填），保持原始日期与钟表时间，再调用一次。无可靠解析能力时说明边界，不让用户填技术格式。
- `repair_request`：按返回字段修正格式一次；重复失败停止。其他失败遵循 recovery，不把技术问题抛给用户。
- `display_chart`：仅当 `delivery.ok=true`，先执行返回的 `before_delivery`（若有）：读取其中分析盘、`user_question` 和当前体系方法，写概要或用户要求的解释，随后原样贴入 media_info。整份草稿运行 verify_command，通过后发出，再执行 after_delivery.next_command。没有 before_delivery 时不补造概要；交付失败不进入分析或报告。

出生时间的可跳过机会由脚本记录，不再自行追问。准确时间、范围与日期级仅使用各自稳定事实，不让用户按性格挑时柱或上升。需要诊断接口才读 [chart-contract.md](chart-contract.md)。

## 交付成功以后

`after_delivery.next_command` 调用 `chart_followup.py <followup_session> delivered`，只在已经输出 `<media_info>` 交付标签后执行。它将后续动作提升为顶层 `next_action` 并持久化。`post-chart.json` 是私有续接状态，不需要模型读取。

- `done`：结束，不重复正文中的分析。
- `ask_report_topics`：结果已交付后，用真实提问工具一次收集想深入的主题，可多选、自由填写或跳过。用户未答不算同意。
- `wait_report_topics`：等待已呈现问题，不重复弹窗。
- `map_known_report_topics`：用户已要报告且有问题，直接映射主题，执行 on_answer_command，不再确认。
- `continue_reports`：报告目录已准备，按返回的阶段响应与 [output-levels.md](output-levels.md) 继续。
- `read_analysis_charts`：仅用于旧会话续接；按返回数据完成尚未回答的解释，不重复新流程的正文。

### 一次主题选择，直接接报告

复用返回 question 和真实工具 Schema。多选不可用时，在标题引导填写多个主题，保留真实选项与“不清楚 / 不想说”，不将多主题限制成互斥单选。无提问工具才用普通消息。成功呈现但未收到答案时执行 on_presented_command；直接得到答案可执行 on_answer_command --topic <ID>（多个主题重复参数）。明确跳过执行 on_skip_command；调用失败不记录已呈现，允许一次普通消息降级。

选择命令只在交付成功后生效。盘后用户有具体自然语言问题时，随 `select` 传 `--question '用户原话'`；`continue_reports.user_question` 会把它带给候选与正文阶段，不能只保留主题 ID。原排盘请求已有问题而盘后没有新问法时，沿用该问题。已有主题直接复用；相同选择不重排盘，改变已开始报告的主题或问题需新修订。拒绝大运时随选择加入 --omit-luck-cycle，不另问一轮。宿主要求交付为本轮最后动作时，保留 followup_session 到下一可交互时机执行 delivered，不把延后记作跳过。

只改变问题、主题或产物深度时复用原盘；出生事实改变才新建隔离任务，不覆盖或混用。cleanup_command 等到产物不再被消费才执行。首次概要由当前回复直接完成，不为它增加候选、评分、复核或润色流程。
