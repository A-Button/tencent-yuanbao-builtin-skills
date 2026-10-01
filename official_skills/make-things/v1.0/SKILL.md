---
name: make-things
description: 管理用户需要持续跟进的事情、待办及时间或条件触发规则。用于把场景方案转成待办、设置提醒或条件监测、查询与调整已有安排、根据用户回报更新待办。复杂目标的规划由对应场景 Skill 完成；一次性问答和纯内容生成不需要本技能。
metadata:
  version: v1.0
---

# make-things 1.0

场景 Skill 决定做什么，并提供所需 Connector 或 additional tools；本 Skill 负责保存 Thing / Todo、关联 Trigger 和维护状态。字段、时间格式及单个工具的用法见注入工具的 description 和参数 Schema。

## 组织事项

- **Thing** 保存持续跟进的目标和约束，硬约束写入 goal。一个会话可以包含多个 Thing，按目标和真实 Thing ID 选择对应的一件。
- **Todo** 是需要推进的一件具体事项：title 说明要做什么，description 补充展示说明，schedule_info 记录事项的日期、时间或相对期限（行前/出发前/提前/截止）等安排，status 记录进展。
- **Trigger** 决定何时运行、是否判断条件、命中后投递什么。一条 Todo 可以关联多条规则；纯 Todo 不必创建规则。是否带 judge 取决于业务条件，不取决于事项由用户还是元宝执行。

Todo 的 schedule_info 表示事项本身的安排，相对期限也算安排；Trigger 表示何时提醒或执行。例如“7:00 起床、提前半小时提醒”，Todo 是 7:00，Trigger 是 6:30。改成 8:00 起床时，Agent 应更新 Todo 的安排，并把对应 Trigger 改到 7:30，保留“提前半小时”的要求。是否需要创建提醒，按用户委托判断。

小时级重复（每小时 / 每 N 小时）的调度真源是 Trigger 的 `rrule`，不是 Todo 的 `schedule_info.time.cycle`。cycle 没有小时档，不能用日/周/月去顶。

每条 Todo 都必须带 `schedule_info`，且 `kind` 只能是 `TIME`（1）或 `MONITOR`（2）。禁止省略 `schedule_info`、禁止只传空对象、禁止 `kind` 缺省或为 0。分不清是时间安排还是条件监测、或两边信息都缺时，先 `ask_user_question` 补齐，不要 `write_todos`。

## 取当前时刻

系统提示只有日期（`Asia/Shanghai`），没有墙上时钟。拼「明天 8:00」这类绝对本地时刻，用提示里的日期即可。拼「N 分钟后 / 今天 HH:MM」必须先 bash 取钟：

```bash
TZ='CST-8' date '+%Y%m%dT%H%M%S'
TZ='CST-8' date -d '+70 seconds' '+%Y%m%dT%H%M%S'
```

只用 `TZ='CST-8'`（POSIX 偏移，不依赖 tzdata）。禁止 `TZ=Asia/Shanghai`：沙箱没有 zoneinfo 时会被忽略，`date` 静默回到 UTC。规则字段 `timezone` 仍写 `Asia/Shanghai`。`run_at` / `dtstart` 必须晚于刚取到的这根钟，已经过去的时间不要创建。

周期规则 `rrule` 不带 `RRULE:` 前缀。已确认 `FREQ=HOURLY/DAILY/WEEKLY/MONTHLY/YEARLY`。每小时写 `FREQ=HOURLY`，每 N 小时加 `INTERVAL`（如 `FREQ=HOURLY;INTERVAL=2`）。钟点只放 `dtstart`，不加 `BYHOUR`。分钟重复未确认，不要用大量单次规则模拟。用户要分钟级重复时说明做不到，给出已确认的小时或按天选项，等用户选定再创建；不要自行改成每小时并声称已按原频率安排。

**`schedule_info.kind` 必填，只能是 1 或 2。** 工具参数写字符串：`TIME`=1（有日期、钟点、按天及以上周期、相对期限），`MONITOR`=2（按条件监测）。0 是未指定，下游卡片会缺日期/重复等信息；不要省略 `kind`，也不要传空 `schedule_info` 把 kind 落成 0。

选哪个看已有信息，缺了就反问，不要猜、不要先落库再补：

- 用户给了何时做（某天、几点、每天/工作日/每周/每月、行前/提前/截止、每小时）→ `TIME`
- 用户给了看什么条件（天气、股价、邮件到达等）→ `MONITOR`
- 「何时」和「看什么」都没有，或有时间但缺必填细节（ONCE 无日期、相对期限无锚点、有钟点不知哪一天、有监测意向但对象/阈值不清）→ 先反问补齐再创建。不要写 `kind=0`，也不要用 `DAILY` 空 `date` 去凑。

**Todo.schedule_info.time.cycle 与 Trigger.rrule 不是同一套枚举。** cycle 只有 `ONCE/DAILY/WORKDAY/WEEKLY/MONTHLY`，没有 `HOURLY`。小时级（含每 N 小时）有「何时」，`kind` 仍写 `TIME`；调度只写在 Trigger 的 `rrule` 上。Todo **禁止**用 `cycle=DAILY`（或 WORKDAY/WEEKLY/MONTHLY）去凑「每小时」：下游会按 cycle 重写 `display_text`（例如变成「每天 11:00」），`date` 空着端上就是「日期：无」。小时级不传 `time.cycle` / `time.date`，在 title 或 description 写明「每小时」。`write_todos` 回包若把展示改成「每天 HH:MM」而规则是 `FREQ=HOURLY`，说明误写了 DAILY，应立刻去掉该条 `time` 再写入，不要当作成功。

## 创建顺序

1. **定位或创建空 Thing。** 查询当前会话，按目标选择真实 Thing；已知 ID 时重读详情。多个候选无法确定目标时补齐必要信息，不默认取第一件。需要新目标时创建空 Thing。
2. **规划 Todo，暂不写入。** 根据场景准备本批完整待办和稳定 Todo ID；同一创建意图重试复用原 ID。
3. **准备需要的规则。** 从已加载场景 Skill 提供的真实工具中选择 judge 取数调用，填写条件及命中后的工作。不做 tool search；缺能力时只加载已知且能提供该能力的场景 Skill，仍缺失则说明缺口。
4. **创建停用 Trigger。** 相对时间先按上节取钟再填 `run_at`。用 `trigger/create_trigger` 关联 Thing 和预设 Todo，显式传 `enabled=false`；此时 Todo 可以尚未落库。收集返回的真实 trigger_id。
5. **一次写入本批 Todo。** 把各自 trigger_id 存入 Todo.rule_ids。每条都必须带完整 `schedule_info`，`kind` 只能是 `TIME` 或 `MONITOR`。不能只建 Trigger、不能省略 `schedule_info`、不能只传空对象。日及以上的时间型写 `kind=TIME`，且 `time` 必填：cycle、time_of_day，ONCE/MONTHLY 再加 date；DAILY 不要留空 `date` 指望前端自己补，没有明确开始日就反问。包括绝对日期/钟点、按天/工作日/周/月的周期，以及相对期限（行前/出发前/提前/截止）；标题或说明里出现这些词就必须写 TIME。相对期限先有锚点日期（用户给出或写进 goal 的假设出发日）再换成绝对 date；锚点未知时先反问「确定出行日期」，不要创建「行前 N 天」，禁止用省略 `schedule_info` 或 `kind=0` 代替。「日期还没最终确认」不算没有安排。小时级也写 `kind=TIME`，但不要填 `cycle=DAILY`，不要因此补一个空日期。监测型写 `kind=MONITOR`、不填 time。选不出 1 还是 2 时停在反问，不要 `write_todos`。再调用 `write_todos`，保留既有其他 Todo。
6. **检查依赖并启用。** Todo 关联写入成功后，检查下节授权，再用 `trigger/update_trigger` 启用已准备好的规则。等待授权、依赖失败或用户要求暂不运行的规则保持停用。

## 授权与投递动作

启用前分别检查 judge 的取数依赖和投递后动作的执行依赖。工具出现在对话中不代表已授权，也不能仅凭它属于 Connector 或 additional tools 判断是否需要授权。

- 已有明确有效的授权结果，或明确无需授权，不重复试跑；场景 Skill 加载时完成的授权可以复用。
- 需要检查时优先用实际提供的授权状态接口；没有此入口时，可执行一次无副作用的取数调用。试跑即使命中也不执行通知或业务动作。
- 明确未授权或授权失效时沿用系统授权卡片；已有卡片则等待该流程恢复，授权后继续原规则。普通超时、参数错误、服务故障不当作未授权或条件未命中。
- 不用发邮件、下单、删除等写操作试授权；只读成功不能证明已有写权限。授权不明且没有安全检查方式时保持停用。定时运行后授权失效也须走实际错误和授权流程。

**投递 Prompt 是否要求加载 Skill，取决于这一次具体动作：**

- 只是提醒或告知，直接写内容，不附加加载指令。
- 要执行动作且工具依赖某个 Skill，写“先加载【实际 Skill 名称】，再【具体动作及上下文】”；依赖多个就分别列明。使用创建时真实已知的名称和自然语言，不发明斜杠语法。
- 不因创建时加载过 Skill、带 judge 或话题涉及邮件就自动要求加载；后台需要该能力时才显式恢复。

Prompt 要能独立定位目标和执行工作，不用“照刚才做”等历史指代，不含凭据。取数调用只取数，判断及投递由 Trigger 执行链处理；未命中不投递，失败不能伪装成 false。命中条件不扩大用户委托，拟写回复和发送邮件须按实际要求区分。

## 修改与失败恢复

Todo 的 title、description、schedule_info 和状态都由 Agent 更新。每次修改前重读最新 Thing，并根据 Todo.rule_ids 查询关联 Trigger；判断本次改动会影响哪些规则。写入 Todo 后，继续更新受影响的 Trigger，不能只保存 Todo 就认为整次调整完成。

- **改标题或说明：** 检查规则的名称、投递内容、judge 条件和取数参数是否仍符合修改后的事项，更新受影响的部分；仅调整展示措辞且不影响规则含义时，保留原规则配置。
- **改事项安排：** 根据原有提醒或执行要求更新 Trigger 时间，例如保留“提前半小时”；不把所有规则时间直接改成 Todo 时间。与本次改期无关的规则保持原样。日及以上安排改小时级时，保留 `kind=TIME`，去掉会冒充每天的 `cycle`/`date`，只改 Trigger 的 `rrule`；小时级改回按天时，再补齐 `time.cycle` 与开始日。改完后 `kind` 仍必须是 1 或 2，缺新安排信息就先反问。
- **暂停或完成：** 检查每条关联规则是否仍需运行。暂停事项时停用继续推进该事项的规则；完成后停用已无用途的提醒或监测。仍有用户明确要求的后续动作时保留相应规则。恢复事项时重新检查时间和依赖，只启用本次需要恢复的规则，不启用全部停用规则。
- **移除 Todo：** 先取消其关联规则，确认取消成功后用 `write_todos(merge=true)` 把该条标 `status=DELETED`（软删除，条目仍在列表中）。不要 `merge=false` 漏掉该条或提交空数组来硬删。暂时停用规则用 enabled=false；明确取消规则时才删除 Trigger。
- 使用 `write_todos` 保留所有未修改的可写字段及规则引用；版本冲突后重读并合并本次改动。已有规则使用 `trigger/update_trigger` 调整，不删除重建。
- 创建 Thing 的结果不确定时，先按会话查询核对，不重复创建；仍无法确定目标时说明状态。Thing / Todo 写入结果不确定时也先重读，再补做未完成的改动。
- Todo 已保存但关联 Trigger 更新失败：重读实际状态，只补做失败的规则更新，并如实说明哪些提醒或执行安排尚未同步。暂停或完成后仍在运行的无用规则优先处理，不能声称已经全部停用。
- Trigger 创建成功但 Todo 写入失败：保留停用规则，重读后复用原 Todo ID 和 trigger_id 补写。创建结果不确定时先用 `trigger/list_triggers` 按 Thing / Todo 核对，不盲目重建；无法唯一定位时说明不确定状态。
- 部分启用失败只恢复失败部分。用户放弃本次创建时，取消本次已创建且不再需要的规则。

提醒发出、规则命中、调度结束都不等于事项完成。用户负责的事项根据明确回报或可靠完成证据更新；元宝执行的事项根据实际结果更新。重复事项执行一次不自动结束整个 Todo，暂停或取消不能标成已完成。Todo 状态和 Trigger 开关由不同工具写入，Agent 负责按上述规则一起维护。

只报告实际结果：待办是否保存、哪些提醒已启用、哪些仍需授权或处理。按工具成功数据和错误判断，无返回不等于成功；界面的“更新中”标记消失也不等于关联规则已同步。内部 ID 不向用户索取或复述。向用户说明频率时以 Trigger 实际 `rrule` / `next_fire_at` 为准，不要复述被下游改写过的 Todo `display_text`。分钟重复、去重或冷却能力未确认，不作承诺。小时级用 `FREQ=HOURLY`。

## 三个例子

例子中的 Skill、工具和 ID 必须来自实际加载、查询或创建结果。

- **明天 8:00 提醒喝水。** 创建空 Thing、预设 Todo，创建停用的 once 规则，instruction 写“提醒用户喝水”，不带 judge，也不要求加载 Skill。Todo 写 `schedule_info.kind=TIME`、`cycle=ONCE`、对应日期与 `time_of_day=08:00`。保存关联后，无额外授权依赖即可启用；提醒发出不自动完成“喝水”。
- **每小时提醒喝水。** 同上，Trigger 用 `trigger_kind=rrule`、`rrule=FREQ=HOURLY`，`dtstart` 取下一个整点或用户指定时刻。每两小时则 `FREQ=HOURLY;INTERVAL=2`。Todo 写 `schedule_info.kind=TIME`，不要填 `cycle=DAILY`，也不要留空 `date`；在 title 或 description 写「每小时提醒喝水」。提醒发出不自动完成“喝水”。
- **帮我记着喝水（没说何时、也没说按什么条件）。** 先反问是每天固定几点，还是按某个条件提醒；用户答完再写 `kind=TIME` 或 `MONITOR`。不要先 `write_todos` 把 `kind` 落成 0。
- **北京明天有雨时提醒带伞。** Todo 写 `schedule_info.kind=MONITOR`、不填 time。使用场景已加载的天气查询工具和地点参数；condition 写“查询结果显示北京次日有降雨时命中”，prompt 写“告知用户北京次日有雨，提醒出门带伞”。投递只告知，不要求重新加载天气 Skill；若委托要求投递后再查天气，则按真实依赖加加载指令。确需试授权时查一次天气，不执行提醒。
- **指定邮件到达后拟写回复。** Todo 写 `schedule_info.kind=MONITOR`。judge 只读取邮件，condition 限定发件人、主题或内容；prompt 写“先加载【实际邮件 Skill 名称】，再读取命中的目标邮件，按【用户要求】拟写回复”，附足够的目标上下文并由运行时补充真实命中证据。只要求拟写就不发送，也不试发邮件验证授权。