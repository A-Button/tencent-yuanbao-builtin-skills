# 排盘：提取字段后直接运行

新排盘／复算八字、西占、组合盘都使用本入口。提取用户已给的原始字段后立即调用下列命令，不预先选择时间流派、计算时差或推演四柱。默认值、时间精度、历法与夏令时校验、城市解析和补问由脚本处理；仅在返回 `resolve_city` 时补地点解析。不需要先读引擎契约、会话状态、源码或报告规则。

```bash
python3 scripts/chart_quick.py <<'JSON'
{"mode":"western","birth_date":"1992-09-15","birth_city":"杭州","birth_time":"14:30"}
JSON
```

资料缺失也调用同一入口，不自行设计问卷。日期整理为用户所选历法的 `YYYY-MM-DD`；时间保留原意，丑时传 `丑时`，大约／左右保留模糊词，不补分钟或中点。普通“排盘／看看八字／看看星盘”默认 `chart`；明确结论、分析、深报才选择相应产物，已有主题不改变产物层级。

| 字段 | 输入／默认值 |
|---|---|
| `mode` | `bazi`（默认）／`western`／`combined`，只计算用户要求的体系 |
| `birth_date`、`birth_city` | 所选历法日期、城市原文；缺失省略或 `null` |
| `birth_time` | 钟表时间、时辰、模糊原文、`不清楚`、`保密`；未提及省略或 `null` |
| `calendar`、`lunar_is_leap_month` | 默认公历 `gregorian`；农历 `lunar`，闰月标记只复用已知 `true/false` |
| `artifact` | `chart`（默认）／`conclusion`／`analysis`／`report` |
| `question`、`topics` | 已有问题原文和主题 ID 数组；未提供省略。ID 为 `career/emotion/family/economy/social/talent/spiritual/study/health`；明确全面报告可传全部九项 |
| `offer_report` | 默认 `true`；明确只要盘面或拒绝报告时 `false` |
| `omit_luck_cycle` | 默认 `false`；用户明确拒绝八字深报的大运模块时传 `true`，随续接状态保留 |
| `gender_for_bazi`、`include_luck_cycles` | 仅复用主动提供的 `male/female`；明确要求盘面大运才传 `true`。不询问、不阻塞首盘；纯西占自动丢弃这些字段 |
| `time_prompted` | 默认 `false`；续接时保留脚本返回值，不重新初始化 |

完整机器契约为 [chart-request.schema.json](../scripts/chart-request.schema.json)，正常调用无需另读。用户未提时间时脚本合并提供一次可跳过机会；已明确大概、范围、未知、保密或已询问后留空时不再追问。八字、西占、组合盘均支持明确起止时间（如 `上午10:00–12:00之间`）与时辰范围，原样填写 `birth_time`，不删掉范围或擅自归为全天。引擎仅核验所给范围，稳定项正常显示，只有跨界项保留候选；已核验稳定的上升照常解读。没有明确边界的“大概／左右”、未知与保密才走日期级；不能补造出生分钟、宫位或大运起点。

## 按返回动作继续

| `next_action` | 当前动作 |
|---|---|
| `ask` | 原样显示 `question.prompt`，只采集其中的字段。保留 `resume_request`，回答后只覆盖已回答字段，选择题合入对应 `patch`，重跑同一入口。跳过时间时保留 `null` 和已置 `true` 的 `time_prompted` |
| `resolve_city` | 宿主解析城市，只补 `resolution.timezone` 与 `resolution.location={label,source,precision:"city"}`，保持 `resume_request` 中出生日期和钟表时间原样，再调用同一入口一次。坐标成对选填，不用于自行修正出生时间；无可靠解析能力时说明边界，不让用户填写技术字段 |
| `repair_request` | 按 `error.fields` 修正输入格式一次，不转成用户问题；重复失败停止 |
| `display_chart` | 仅当 `delivery.ok` 为 true：把 `media_info` 贴进回复草稿，运行 `verify_command`，通过后发出。然后记录 `delivery_patch` 并立即执行 `after_delivery.next_command`。`delivery.ok` 为 false 或校验未通过时不要说盘面已附上，也不进入后续阶段 |

出生资料的 `question` 是工具无关协议。宿主已验证支持时，把 `text` 映射自由输入、`choice` 映射真实选项；不支持则用一条普通消息，不试错工具 schema，不把自由输入伪装成单选。盘后主题多选单独服从下面的原生工具优先契约。

其他失败只按返回的 `recovery.user_message`、`target` 和 `max_attempts` 处理：内部修复或明确的降级各最多一次；同一错误再现停止。缺少真实候选不自行编造，不向用户转述内部 `error.message`。需要诊断适配器／引擎才读 [chart-contract.md](chart-contract.md)；维护旧宿主状态接口才读 [interaction-state.md](interaction-state.md)。

## 交付成功以后

`after_delivery.next_command` 调用 `chart_followup.py <followup_session> delivered`，只在已经输出 `<media_info>` 交付标签后执行。它将后续动作提升为顶层 `next_action` 并持久化，避免 HTML 交付后漏掉提问。首盘路径不准备深报、不调用模型；`post-chart.json` 是私有续接状态，不需要模型读取。

- `done`：结束。只要盘面／拒绝报告由 `offer_report=false` 表达，不再次推荐。
- `read_analysis_charts`：读取返回的去身份化 `analysis_charts` 和 [output-levels.md](output-levels.md)，完成用户明确的结论／普通分析；不因已有主题升级为深报。文件缺失则说明边界，不回读原始资料补写。
- `ask_report_topics`：必须执行下面的提问契约，不用一句“还想看什么可以告诉我”代替工具。
- `wait_report_topics`：该选择已呈现，等待原问题的回答；不重复弹出、不默认选择任何主题。
- `map_known_report_topics`：用户已明确要报告且给了具体问题，把已有问题映射为主题 ID 后执行返回的 `on_answer_command`；不再询问是否需要。
- `continue_reports`：每个体系的 `reports` 是原有报告流水线的下一阶段响应，按 [output-levels.md](output-levels.md) 读取当前参考、填写 `next_input` 并执行 `next_command`。八字／西占独立生成。

### 一次主题选择，直接接报告

核对宿主可用工具的真实 Schema，优先使用 `ask-user-question`（或该宿主的已验证同义提问工具）。工具可用就调用，不因“已经交付文件”省略。采用返回的 `question.prompt/choices`，一次呈现九个关注领域，允许任意数量多选或跳过，不先问是否需要报告。

- 工具支持多选：按真实 Schema 映射；`question.id` 用作本轮提问标识。返回结构是工具无关契约，不把 `kind` 等字段未经核对直接当成工具参数。
- 工具只支持自由输入：仍用同一工具问一次“想深入看哪些方面”，允许填写多个；不把九个领域改成互斥单选，不限制最多几个。
- 仅当宿主没有可用提问工具时，原样用一条普通消息询问并等待；不能静默结束、伪称调用成功，或为此重排盘。
- 工具成功呈现但答案尚未返回：执行 `on_presented_command`。用户直接返回答案时可跳过该确认命令，直接执行 `on_answer_command --topic <ID>`，多个主题重复参数。
- 用户在主题回答中明确拒绝大运模块时，同一选择命令加 `--omit-luck-cycle`；不为这个选项另问一轮。
- 明确跳过／提交空选择：执行 `on_skip_command` 后结束。工具失败不记录已呈现；说明失败并使用一次普通消息降级，不循环重试控件。

选择命令只在交付成功后才生效，冻结主题顺序、复用原始盘面并准备报告。重复提交相同选择不会重新排盘或重建报告；`resume_command` 返回当前阶段。已开始后改变主题需新建报告修订，不覆盖旧报告。宿主明确要求交付为本轮最后一个动作时，保留响应中的 `followup_session`，下一可交互时机执行同一 `delivered` 命令，不能把延后误记为跳过。

普通 `chart` 只交付确定性 HTML，不自动生成速览或快速解读。报告主题不阻塞首盘；明确普通分析不因已有主题升级为报告。只改变问题、主题或产物深度时复用原盘；出生事实改变时用同一入口新建隔离任务，保留旧产物，不能覆盖或混用。自动目录的精确清理命令由响应返回，待产物不再被消费再执行。
