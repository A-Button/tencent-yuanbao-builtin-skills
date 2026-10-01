# job-hunting 链路验收

仅在用户明确要求验收时执行，不拿测试数据冒充真实求职安排。

## XCard

- `app.yaml` 只声明四张 `application/a2ui+json` 卡片，每张有唯一模型可见 render tool。
- 四个 JSON 顶层只有 `components`，存在 `root`，引用闭合，按钮有真实 action。
- 简历、求职任务、岗位和面试示例 DataModel 分别通过 XCard schema 与严格视觉静态审计。
- 工坊可用时，用真实 Host 验证工具结果能挂载卡片、岗位原页可点击、按钮能回投 Agent。
- 岗位搜索三条分支都必须出现 `render_job_search_results` 挂载：原页核验成功的职位列表、页面读取失败的“待核验”职位列表、没有候选的 `jobs=[]` 空态。三条分支都不得只输出 Markdown 职位清单。
- Trace 中必须先出现 `app job-hunting describe`，后出现 `render_job_search_results`；render 成功后才允许最终回复或 `ask_user_question`。
- 岗位卡挂载后，正文末尾只问一个下一步：账本有未结束且相关的 interview 时点名该场面试并询问是否拆准备待办；没有时引导投递后登记面试；零结果只问换条件重搜。不得重复询问改简历或持续关注，也不得只写泛泛的「还需要什么帮助」。

## 求职任务

- 从面试提醒卡点击“帮我准备”后，Trace 中先重读并复用当前求职 Thing，再以稳定 `key` 把 3–5 个面试准备项写入账本这场面试的 `prep_items[]`；Trace 里不出现为准备项调用的 `write_todos`，重复点击不新增重复 Thing，也不重建已有准备项。
- 准备项不进 make-things：不建 Todo、不写 `schedule_info`、不创建 Trigger；任务页里这件 Thing 下只出现面试提醒 Todo。已有准备项的 `status` 和 `detail` 不会因刷新任务卡丢失。
- 写入后重读账本，计数只来自目标面试的 `prep_items[]`；`done` 计入已完成，其余计入未完成，完成度计算正确。
- `render_career_task` 成功挂载后才能声称任务已创建或更新；“跟进相关岗位”和“去准备”都能回投 Agent。
- 点“去准备”后从任务卡第一条未完成 Todo 开始辅导；该项练完并经用户确认后，重读 Thing、以完整快照把它写为 `DONE`，刷新任务卡进度，再询问是否进入下一项；只打开卡片或刚开始辅导不得标完成。
- 本轮实际写入准备项且这场面试尚无 `prep-setup-<key>.receipt.json` 的 `now_id` 时，必须再发一张 `card_type="todo_remind"` 准备待办 Now；同一场面试再点「帮我准备」不重发，同一 Thing 下换一场面试要重新发。
- 已发过准备待办 Now 后，每次把准备项写为 `done` 或增删改准备项都要在对话里重新挂任务卡；准备进度 Now（`prep-update-<key>-<clock>`）**每场面试每天至多一张**，连续「去准备」推进过程中不逐项发卡，等本轮结束或全部完成再发一张汇总：badge 与重读后的准备项状态一致，全部完成时标题为「…准备已完成」且去掉「去准备」；当天已发过、暂停、恢复或无变化写入都不发。

## 岗位关注

- 点岗位卡「持续关注」后先问频率；确认后 Trace 依次出现：停用创建一条 `rrule` Trigger（`UNTIL` 为开启日加 7 天）→ `write_todos` 写入 `watch-jobs` 与真实 `rule_ids` → 重读 → 启用 → 写 `task.job_watch` → 立即发一张岗位关注开启 Now。
- 再次开启或改条件时原地更新同一条 Trigger，不出现第二条关注规则。
- 到点回调只推相对 `seen_keys` 的新增岗位：≥3 条为 `recommend_list`，1–2 条为 `todo_remind`，0 条不发卡；Web Search 失败不发卡。只有开启那一次和到期那一次允许在 0 条时发 `image_text`。
- 最后一次推送带「续一周」，之后 `watch-jobs` 为 `DONE`、`job_watch.active=false`；「续一周」原地延长 `UNTIL` 并重新启用。
- 「取消关注」先删除 Trigger 再移除 `rule_ids`，Todo 不标 `DONE`；关注开启期间场景 5 不再发一次性职位 Now。

## 用户档案持久化

- 不提供 `userId`，默认路径为 `/data/user/job-hunting/state.json`；`JOB_HUNTING_DATA_DIR` 只由宿主覆盖。
- 首次读取不存在的账本返回 revision 0；成功写入后 revision 递增，并产生可恢复的最近备份。
- 使用旧 revision 写入会得到 `revision_conflict`，不会覆盖另一个会话已经保存的新事实。
- 上传简历经 `freeze-resume` 后，原件与规范化副本都位于 `/data/user/job-hunting/materials/resumes/<resume_id>/`；账本不含简历全文，也不保留 `/data/inputs/...` 路径。
- 新对话未上传简历时能读取 `profile.active_resume_id` 和 `profile.resume_path` 继续诊断或匹配岗位；目标文件缺失时停止并要求用户重新提供。
- 岗位定制简历追加新版本但不默认替换当前基础简历；用户明确切换后，active ID 与路径一致。

## 面试提醒创建

使用一件标明“验收”的空 Thing、一个稳定面试 Todo 和停用 once Trigger。面试与提醒时刻来自真实墙上时钟，留足创建余量。

核对顺序：创建空 Thing → 创建停用 Trigger → 一次写入完整 Todo 与全部 rule_ids → 重读 → 启用 → 保存并发布初始面试卡。规则未启用时卡片不得写已开启。

## 回调与幂等

- 到点后宿主回投原会话；回调重读 Thing、Trigger 和面试事实。
- `show_widget` 请求顶层只有 `card_type`（字符串）、`title`、`data`、`summary`、`source`、`actions`、`tap`、`thingId`、`todoId`，ID 为本轮真实回包值；没有 `conversation_id`、`triggerId` 等多余顶层字段，正文不包卡型同名分支。
- 记录 Trigger ID、Fire ID、Turn ID、返回的 `now_id` 与数据库重读结果；不得用模型自报代替服务证据。
- 重投同一 Fire 不新增 Turn。发布不幂等：原样重试会多出一张卡，超时或结果不确定时不自动重试，如实说明尚未确认。
- 失败、字段缺失或规则解绑保持失败，不解释成未命中或已提醒。

## 改期与收口

- 改期后确认原 Trigger 被原地更新，没有重复规则。
- 用户确认完成或取消后，Todo 和未来 Trigger 正确收口；不影响同 Thing 的其他面试。
- 验收结束只停用本次验收规则，保留证据供评审。
