# 用户求职档案与读写规则

`/data/user/job-hunting/state.json` 是当前登录用户的求职事实账本。宿主按用户隔离
`/data/user`，因此不要向用户索取、也不要向脚本传递 `userId`。账本和相邻的
`materials/` 跨对话、跨沙箱保留，但不是第二套 Thing 状态树。

所有读写通过 `scripts/state_store.py` 完成；不要直接重定向或覆盖 `state.json`。
如运行环境需要替换挂载点，可由宿主设置 `JOB_HUNTING_DATA_DIR`，模型不得自行修改。

## 路径

```text
/data/user/job-hunting/
├── state.json
├── state.json.bak
├── materials/
│   ├── resumes/<resume_id>/source.<ext>
│   ├── resumes/<resume_id>/normalized.md
│   └── <其他准备与复盘材料>
└── events/<thing-id>/...
```

- `state.json`：求职意向、当前简历引用、诊断、版本索引和面试事实。
- `state.json.bak`：最近一次成功账本的备份，只用于损坏恢复。
- `materials/resumes/`：简历原件和规范化副本；正文不塞进账本。
- `events/`：`show_widget` 原请求和真实回执（`interview-setup-<key>`、`interview-callback-<key>-*`、`prep-setup-<key>`、`prep-update-<key>-*`、`jobs-after-task`、`watch-setup-*`、`watch-run-*`），不代表 Thing/Trigger 状态。面试相关四类都按 `<company-role-round-key>` 分文件，一件 Thing 里多场面试各存各的；有 `now_id` 的 `prep-setup-<key>.receipt.json` 只表示这场面试已发过准备待办 Now，不挡其他面试；`prep-update-<key>-<clock>.receipt.json` 的 `<clock>` 带日期，用来判断这场面试当天是否已发过进度卡。职位卡按 Thing 记，有 `now_id` 的 `jobs-after-task.receipt.json` 表示已发过职位 Now。

## 确定性读写

加载 Skill 后，将下面的相对脚本路径解析到本 Skill 目录再执行：

```bash
python3 scripts/state_store.py paths
python3 scripts/state_store.py read
python3 scripts/state_store.py write --input-file /tmp/job-hunting-state.json --expected-revision <读取到的revision>
python3 scripts/state_store.py freeze-resume --source <原件路径> --normalized <规范化Markdown路径>
```

`read` 在账本尚不存在时返回 revision 0 的空结构；主文件损坏而备份有效时从备份读取，
同时在 stderr 给出警告。主文件和备份都不可用、或 schema 未知时停止，不得重置为空。

写入流程：

1. `read` 并记住 `revision`。
2. 在内存中保留未修改字段，只合并本轮已确认事实。
3. 把完整候选 JSON 写入临时输入文件。
4. 使用读取到的 revision 调用 `write`。
5. 返回 `revision_conflict` 时重新读取，合并本轮变化后再提交；不得拿旧快照覆盖新变化。

`write` 会校验基础结构、把 schema 升级为当前版本、递增 revision、更新时间、先保存备份，
再以同目录临时文件原子替换主文件。

## 单一真源边界

| 数据 | 真源 |
| --- | --- |
| 求职意向、简历引用/诊断/版本、面试公司/岗位/轮次/时间、面试准备项与其进度、准备与复盘路径 | 用户账本与 `materials/` |
| 长程目标、面试提醒 Todo、全部 `rule_ids`、Trigger 开关和时间 | make-things Thing/Todo/Trigger |
| XCard 当前展示 | 本轮事实投影，不反向改状态 |
| 动态是否已发布 | `events/` 里带真实 `now_id` 的 `show_widget` 回执 |
| 本轮 Web Search 岗位结果 | 本轮搜索结果，不长期保存 |

顶层 `thing_id` 与 interview 的 `todo_id` 只是定位提示，不代表 Thing/Todo 存在或处于某状态；
跨对话使用前必须重读 make-things。不要把 Trigger ID、规则配置、`now_id` 或发布回执
写进账本。

## schema_version 5

未知值使用 `null` 或空数组，不填示例人物：

```text
schema_version, revision, updated_at, thing_id,
task { intent, timeline, created_at, job_watch },
profile { active_resume_id, resume_path, diagnosis, resume_versions[] },
interviews[]
```

### task.intent

保存用户明确表达的：`target_roles`、`locations`、`salary_expectation`（含币种与月薪/年包、
税前/税后口径）、`experience`、`track`、`employment_type`、`exclusions`。偏好只来自用户
明说，不从简历臆测。

岗位搜索结果是当次 Web 事实，不长期写入状态；用户要求留存某岗位时保存来源快照或笔记到
`materials/`，不要把搜索缓存伪装成仍有效职位。

### task.job_watch

场景 6 岗位关注的业务事实，缺省为 `null`：

```text
active, filters, started_at, until, seen_keys[]
```

- `filters`：开启时 `task.intent` 中地点、岗位、薪资等条件的快照；之后改 `intent` 不自动改关注条件。
- `until`：截止日期 `YYYY-MM-DD`，只用于卡片文案；何时触发以 Trigger 为准。
- `seen_keys`：已推过岗位的去重 key（「公司|岗位名|城市」去空格、转小写），只保留最近 200 个；不保存岗位详情。
- 频率、`rrule`、`trigger_id` 不写这里，以 make-things 为准。

### profile

- `active_resume_id`：当前默认简历版本 ID；必须能在 `resume_versions[]` 中找到。
- `resume_path`：当前默认版本的持久卷路径，通常指向 `normalized.md`；不得保存
  `/data/inputs/...`、短期 URL 或技能安装目录。
- `diagnosis`：`resume_id`、`score`、`highlights[]`、`improvements[]`、`suggestions[]`、
  `diagnosed_at`；全部基于对应版本的真实内容。
- `resume_versions[]`：`id`、`kind(base|tailored)`、`path`、`source_path`、`created_at`、
  `based_on`、`target_job`、`change_summary`。旧记录缺少新增字段时保留原值，不补造。

本轮上传简历时，先提取规范化 Markdown，再调用 `freeze-resume`。用返回的 `resume_id`、
`source_path`、`resume_path` 和 `created_at` 构造版本记录，成功写入账本后才称为已保存。
针对岗位的 `tailored` 版本默认不切换当前基础简历；用户明确要求后才更新
`active_resume_id` 和 `resume_path`。

### interviews

每项保存：

```text
id, company, role, round,
status(planned|scheduled|completed|cancelled),
scheduled_at, time_original, timezone,
mode, location, meeting_link,
outcome, prep_path, review_path,
todo_id, prep_items[]
```

- `planned`：准备对象，尚无精确时刻，不创建 Trigger。
- `scheduled`：已有带时区的精确时刻，可以创建提醒。
- `completed` / `cancelled`：用户明确确认后的事实；时间经过不自动推断。
- `todo_id` 指这场面试的提醒 Todo（`interview-<key>`），使用稳定业务键，仅作定位；Todo 最新状态和 `rule_ids` 必须从 `get_thing` 读取。
- 只有“周四下午”时保存原话、日期和时段，`scheduled_at=null`；不得擅自补具体时间。
- `prep_items[]` 是这场面试的准备清单，每项 `key`、`title`、`detail`、`status(pending|active|done|paused)`、`updated_at`。`key` 在同一场面试内稳定唯一（如 `jd`、`star`、`basics`、`questions`），重复「帮我准备」按 `key` 复用不重建。准备项**不写入 make-things**：Todo 那一层只承载面试本身这类长期安排，准备清单是短期事项，只存账本。因此准备项没有 `schedule_info`、没有 `rule_ids`、不关联 Trigger；需要准备截止提醒时，另外为面试 Todo 加规则，不为单条准备项建 Todo。
- 读到旧账本时，若对应 Thing 里还残留 `prep-*` 开头的 Todo，把它们的标题、说明和状态读进 `prep_items[]`，写入账本成功后再从 Thing 移除，不要两边同时维护。

## 并发、隐私与删除

- 不同简历使用随机 `resume_id`，多个会话同时导入不会覆盖同一文件。
- 两个会话同时改账本时，revision 门禁会拒绝旧快照；必须重读合并。
- 简历全文、手机号、邮箱等个人信息只存在简历材料中，不复制到 Thing、Todo、Trigger、
  XCard DataModel、发布请求或普通日志。
- 用户要求删除某版简历时，先确认目标版本；若它是当前版本，先选择替代版本或将当前引用置空，
  再删除对应目录。不得根据文件名猜测目标，也不得递归删除整个 `/data/user/job-hunting`。

## 旧数据迁移

读取 schema v4 时保留全部业务事实；下一次成功写入自动升级为 v5。若旧 `resume_path` 指向
会话路径、工作区或其他非持久路径，先确认文件存在并用 `freeze-resume` 复制，再更新引用。
原文件不存在时保留旧记录并向用户说明，不能伪造已迁移，也不能清空诊断或面试事实。

早期 schema 中缓存的 Trigger 开关或单个 `trigger_id` 不迁移；真实规则关联重新从
Thing/Todo 读取。
