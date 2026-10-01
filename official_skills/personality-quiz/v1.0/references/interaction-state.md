# 出生信息会话状态契约

所有新排盘由 `chart_quick.py` 在内部生成此状态，模型不必填写或读取。

只在维护旧宿主状态接口或诊断适配器时读取本文件。正常问法见 [chart-flow.md](chart-flow.md)，标准化引擎输入见 [chart-contract.md](chart-contract.md)；不要在会话层复制引擎 schema 或报告规则。

## 状态对象

| 字段 | 内容 | 约束 |
|---|---|---|
| `schema_version` | 状态版本 | 当前 `1.4.0` |
| `interaction_variant` | 交互来源 | 固定 `dynamic-guided` |
| `mode` | 排盘体系 | `bazi\|western\|combined` |
| `intake` | 用户原始语义值 | 保留原意，不猜测或改写成更精确值 |
| `resolved` | 宿主解析后的日期、时间、时区和位置 | 未解析字段为 `null` |
| `request` | 产物、问题、主题、布局和分享偏好 | 不影响排盘事实 |
| `state` | 当前阶段 | 使用下方状态表 |
| `missing_fields` | 阻塞首份盘面的用户可回答字段 | 只含出生日期、城市或当前歧义所需地区信息 |
| `warnings` | 非阻塞说明 | 不作为隐藏控制字段 |
| `chart_revision` | 当前独立任务的成功盘面版本 | 未生成成功为 `0`；当前生产流水线成功后为 `1` |

未知顶层字段不得静默传给引擎。

### `intake`

| 字段 | 允许值 |
|---|---|
| `calendar` | `gregorian\|lunar\|null`；未写时投影为公历 |
| `birth_date` | 用户所选历法中的 `YYYY-MM-DD` 或 `null` |
| `birth_time` | 当地钟表时间 `HH:MM`、`shichen` 的十二地支之一、`range` 的明确起止时间原文、模糊时间原文，或 `null` |
| `time_accuracy` | `exact\|shichen\|approximate\|range\|unknown\|withheld\|null`；`null` 表示用户没有给出可归类的时间语义，是否已给过填写机会由 `time_prompted` 区分 |
| `time_prompted` | `true\|false`；是否已经给过一次出生时间填写机会 |
| `lunar_is_leap_month` | `true\|false\|null` |
| `birth_city_raw` | 城市级文本或 `null` |

出生时间不构成 `missing_fields`，也不阻塞日期级初盘。`time_accuracy=null` 且 `time_prompted=false` 时仍处于一次性可选精度采集阶段；发出交互即写 `time_prompted=true`。用户明确不知道写 `unknown`，不愿提供写 `withheld`；唯一一次交互后仍留空则保留 `null`，但因 `time_prompted=true` 可以进入日期级初盘。不得从姓名、IP、设备位置或模糊时段补出精确出生信息。

### `resolved`

| 字段 | 内容 |
|---|---|
| `local_date` | 已确定性转换的公历当地日期 |
| `local_datetime` | 仅准确时间可用时存在的当地 ISO 时间 |
| `lunar_datetime` | 农历完整单盘需要的当地 ISO 时间 |
| `timezone` | IANA 时区 |
| `fold` | 夏令时回拨的 `0\|1\|null` |
| `historical_utc_offset` | 有来源的历史偏移或 `null` |
| `location` | 城市标签、来源和 `city` 精度；当前能力不使用坐标时经纬度可省略 |
| `ambiguity_code` | 当前唯一阻塞歧义或 `null` |
| `chart_precision` | `exact\|time-range\|date-only\|null` |

地点来源必须非空；解释性来源说明放入 `warnings`，不得塞入坐标字段。

### `request`

| 字段 | 允许值或规则 |
|---|---|
| `artifact` | `chart\|conclusion\|analysis\|report\|null` |
| `question` | 用户原话或 `null` |
| `topics` | 九个固定主题中的零至多个，按用户选择顺序去重 |
| `include_luck_cycles` | 普通盘面或普通分析的按需大运请求；其缺省值不等于用户拒绝深报固定大运模块 |
| `gender_for_bazi` | 用户主动提供时保存 `male\|female`；未知、保密或未提供均不阻塞基础盘 |
| `share_card` | `auto\|required\|forbidden` |
| `layout` | `desktop\|mobile` |

`artifact`、`question`、`topics`、`share_card` 和 `layout` 不改变盘面 revision。`artifact=null|chart` 表示 HTML-only 快路径；盘面展示后只允许一次非阻塞的深度报告主题多选，不直接启动语义步骤。显式 `conclusion|analysis|report`，或用户在盘后选择主题并把 `artifact` 更新为 `report` 后，才允许启动相应语义步骤。进入八字 `report` 即表示系统默认准备固定大运模块，无需单独大运意图；只有用户明确拒绝才产生组装后的 `luck_cycle_context.status=excluded`，不得从 `include_luck_cycles=false|null` 推断拒绝。传统排运字段不得用于称呼、人格或身份推断，纯西洋盘不保存它们。

## 状态迁移

| `state` | 进入条件 | 下一状态 |
|---|---|---|
| `collecting` | 日期或城市仍缺失，或 `time_accuracy=null` 且 `time_prompted=false` | `ready_for_chart\|needs_resolution\|cancelled` |
| `needs_resolution` | 城市、历法或准确时刻存在阻塞歧义 | `ready_for_chart\|collecting\|cancelled` |
| `ready_for_chart` | 日期与原始城市已齐；时区位置已解析或原始城市可由随包快速表唯一解析；且 `time_accuracy` 已归类或 `time_prompted=true` | `chart_generated\|needs_resolution\|cancelled` |
| `chart_generated` | 盘面事实与 HTML 已原子写入，但尚未在回复中交付 | `chart_ready\|cancelled` |
| `chart_ready` | 至少一个盘面 revision 已成功并展示 | `ready_for_report\|done\|cancelled` |
| `ready_for_report` | 报告主题已确定 | `chart_ready\|done\|cancelled` |
| `done` | 当前请求已交付 | 终态 |
| `cancelled` | 用户取消或明确结束 | 终态 |

约束：

- `ready_for_chart` 之后不得保留用户可回答的排盘硬缺字段；时区位置可以留给流水线的确定性快速表完成。若 `time_accuracy=null`，必须已有 `time_prompted=true`。报告主题缺失不能阻止先展示盘面。
- `ambiguity_code` 非空时必须处于 `needs_resolution`。
- `chart_revision>0` 必须对应已经成功写出的事实产物，加载页不计成功。流水线成功后先应用 `state_patch` 进入 `chart_generated`；只有回复里输出了指向该 HTML 的 `<media_info>` 交付标签，宿主才应用响应中的 `delivery_patch` 进入 `chart_ready`。未输出标签时保持 `chart_generated`，不得开始解释、主题提问或报告。
- `request.artifact=null|chart` 在 `chart_ready` 后不追加模型生成，但可以提供一次可跳过的深度报告主题多选。用户选择任意主题时写入 `request.topics`、把 `request.artifact` 更新为 `report` 并进入 `ready_for_report`；跳过或明确只要盘面时进入 `done`。该交互不得阻塞 `chart_generated → chart_ready`。
- 只有 `missing_fields` 中用户可回答的硬缺字段、一次非阻塞出生时间采集、阻塞计算的真实歧义和盘面后的深度报告主题多选可以转成用户问题。内部解析状态、`warnings`、其他可选字段、日期级降级、顺逆条件分支和软校验结果直接由系统处理，不要求用户确认。大运不是报告主题，不得单独占用一次提问。

## 歧义代码

解析器已经同时给出完整选项、彼此独立且都阻塞计算的用户可回答歧义，可以在一次交互中合并询问；会话状态仍只以 `ambiguity_code` 记录当前主歧义，因此该合并是宿主交互层优化，不声称由状态对象承载。没有真实候选时只保留当前 code，不让模型补造选项。只有回答前一项后才能发现的依赖歧义，才允许重新解析后再追加一次。内部处理 code 只服从流水线的 `next_action`，不持久化成待用户回答的 `ambiguity_code`。不得把内部状态、可自动默认的口径或可降级项包装成歧义交给用户。

| code | 固定处理 |
|---|---|
| `ambiguous_city` | 同名城市的国家、地区或邻近大城市 |
| `timezone_unresolved` | 为宿主解析补充国家或省州 |
| `dst_fold_required` | 回拨当天第一次还是第二次当地时间 |
| `nonexistent_local_time` | 核对跳时造成的不存在时刻 |
| `xinjiang_clock_required` | 出生记录使用北京时间还是新疆时间 |
| `historical_offset_required` | 系统降级，不向用户询问技术格式 |
| `lunar_leap_month_required` | 是否为闰月 |
| `western_requires_gregorian` | 系统完成确定性公历转换；不可用时停止相应体系，不向用户询问技术字段 |
| `combined_lunar_conversion_required` | 系统先完成农转公历；不可用时停止相应体系，不向用户询问技术字段 |

## 投影与 revision

会话层只提供已解析状态；`chart_pipeline.py` 按 [chart-contract.md](chart-contract.md) 确定性投影引擎输入：

- 准确到分钟且没有歧义：完整单盘；
- 三个模式的十二时辰或明确起止时间：`time-range` 核验；八字四柱一致时直接出完整四柱，西占上升等稳定项正常展示，仅真实跨界项保留候选；
- 无明确边界的模糊、未知、保密或已询问后留空：日期级初盘；
- 组合盘分别写入两套引擎输入，不在对话层手算历法或天文数据。

`time_accuracy=range` 必须保留可解析的 `birth_time`，不得仅存一个 range 标签却丢弃起止边界；`resolved.chart_precision` 不得残留为 date-only。范围的日期转换只改变历法表达，不缩窄或扩大时间窗口。

当前生产流水线只接收 `chart_revision=0` 并生成 revision 1，不支持在同一任务内创建 r2/r3。用户后来补充准确时间，或日期、历法、时区、`fold`、历史偏移、位置、日界口径等出生事实发生变化时，必须新建隔离的独立排盘任务和私有目录，从 `chart_revision=0` 重新生成其首版产物；旧任务及旧产物保留，不能覆盖、拼接或手工调用底层引擎冒充后续 revision。只改变产物深度、问题、主题、布局或分享偏好不重跑排盘。

## 失败与隐私

- 结构化引擎错误只按 `chart_pipeline.py` 返回的 `next_action` 与 `recovery` 处理：只有 `ask_choice`、`ask_text` 可进入用户澄清；`resolve_internally`、`degrade`、`stop` 不得写成用户问题。内部修复或降级最多执行一次，同一 error code 再现即停止；对用户只显示 `recovery.user_message`，不转述可能含技术字段的内部 `error.message`。需要澄清时再更新对应 `missing_fields` 或用户可回答的 `ambiguity_code`，且不自动替换时间和地点。
- 原始出生资料只留在私有运行目录与会话状态；生成式解释只读取去身份化盘面。
- 报告目录绑定体系和 revision，组合盘不得共享或覆盖路径。
- 交付已经完成、流程取消且宿主能够确认产物不再被消费时，只执行响应返回了 `cleanup_command` 的私有运行目录的精确清理命令；已发布到工作区的交付文件不在清理范围内；若目录生命周期由宿主管理，则交由宿主回收，不声称存在本 Skill 无法验证的 TTL 自动清理。日志不得记录完整日期、时间和地点组合。
