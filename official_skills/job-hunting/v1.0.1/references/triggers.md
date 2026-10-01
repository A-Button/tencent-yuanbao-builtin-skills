# 面试提醒 Trigger 设计

本 Skill 只创建两类规则：面试临近提醒用 make-things 原生 `once` Trigger；场景 6 岗位关注用一条带 `UNTIL` 的 `rrule` Trigger（见文末「岗位关注」）。不创建投递跟进、宿主 cron、私有 Timer 或逐轮 DELAY。

## 创建门禁

- 面试必须有带时区的精确 `scheduled_at`。只有日期或“下午”等时段时不建 Trigger，先询问具体面试或提醒时刻。
- 相对提醒先按 make-things 规则读取真实墙上时钟；已经过去的候选跳过。
- 用户未指定提前量时，默认使用 T-24h 与 T-2h（面试前一天的同一时刻，和当天提前两小时）；距离面试不足 24 小时时，只保留仍在未来的候选。用户要求优先。
- 一场面试一个稳定 Todo，可关联多条 `rule_ids`。

## 创建 payload

每条提醒先停用创建：

```json
{
  "instruction": "加载 job-hunting，重读当前 Thing 与对应面试事实；确认面试未取消或改期后，按本 Skill 发布本轮面试提醒卡。",
  "trigger_kind": "once",
  "title": "临近面试提醒",
  "run_at": "<YYYYMMDDTHHMMSS>",
  "rrule": "",
  "dtstart": "",
  "enabled": false,
  "thing_id": "<真实 thing_id>",
  "todo_id": "interview-<stable-key>",
  "timezone": "Asia/Shanghai"
}
```

创建顺序：`get_thing`/空 Thing → 预设 Todo ID → 创建全部停用 Trigger → 一次 `write_todos` 写入完整 Todo 与全部真实 `rule_ids` → 重读核对 → 逐条 `trigger/update_trigger` 启用。

首次写入空 Thing 使用最新 version、`merge=false`；后续修改使用 `merge=true`，但提交项仍是完整快照，保留未修改的 title、description、schedule_info、action、status 和全部 rule_ids。面试 Todo 必须带 `schedule_info`（`kind=TIME`，与已确认时刻一致）；省略或空对象会被 Things 以 `100001` 拒绝。不设 Trigger 只表示 `rule_ids=[]`，不能省掉安排。

## 初始动态

Todo 和本批规则达到实际状态后，按 [NOW 卡片](now-cards.md) 发布 `card_type="todo_remind"`。先把完整请求存到 `/data/user/job-hunting/events/<thing_id>/interview-setup-<company-role-round-key>.json`，再调用 `show_widget`；回执存 `interview-setup-<company-role-round-key>.receipt.json`。同一 Thing 下每场面试各用自己的 key。顶层传真实 `thingId` 和提醒 `todoId`（驼峰），不传 `conversation_id`、`widget`、`uri`、`eventId`、`triggerId`。Trigger 工具用的是 snake_case `thing_id`/`todo_id`，只有 `show_widget` 这两个顶层字段是驼峰，别互相抄。只有真实 `now_id` 才算成功。规则仍停用或启用失败时，title 与 badge 只能写提醒尚未运行。

## 回调

1. 只信任宿主本轮提供的 Thing/Todo/Trigger 身份。
2. `get_thing` 重读；必要时 `trigger/list_triggers` 核对 Trigger 仍在 Todo.rule_ids 中且启用。
3. 用 `scripts/state_store.py read` 重读 `/data/user/job-hunting/state.json` 中的对应面试；已取消、已完成、改期或事实冲突时不执行旧提醒。
4. 按当前时钟重算倒计时，按 [NOW 卡片](now-cards.md) 组装 `todo_remind`。与同一场面试上一张快照无实质变化则保持静默。保存 `interview-callback-<company-role-round-key>-<clock>.json` 后调用 `show_widget`，顶层传真实 `thingId`、`todoId`；回执另存。不传 `conversation_id`、`triggerId`、`eventId`。
5. 只有 `now_id` 算成功；超时不自动重试。提醒发出不自动完成面试 Todo。

## 改期

面试时间变了，要动的不止 Trigger。按顺序做：

1. 先用 `state_store.py write` 更新这场 interview 的 `scheduled_at`，再按 make-things 规则取一次真实墙上时钟。
2. `get_thing` 重读，`trigger/list_triggers` 列出这场面试 Todo 下的全部规则，拿到每条真实的 `run_at` 与 `enabled`。
3. **按提前量重算，不要把规则时间直接改成新的面试时刻。** 原来是 T-24h 的仍取新 `scheduled_at` 减 24 小时，T-2h 同理；用户自定义的提前量原样保留。
4. 逐条 `trigger/update_trigger` 提交新 `run_at`，`rrule`、`dtstart` 保持空字符串，不删除重建。
5. 重算后仍在未来的保持启用；**落在过去的那条改 `enabled=false`**，不留一条时刻已过的启用规则。
6. 改期往后推时，原来因为来不及而没建的提醒可能又成立了（本来只建了 T-2h，改到下周后 T-24h 有了空间）：按创建门禁补建——停用创建 → `write_todos` 追加 `rule_ids`（带全原有 ID）→ 重读 → 启用。
7. **Todo 的 `schedule_info` 同样要改**：这场面试 Todo 的 `date`、`time_of_day` 对齐新 `scheduled_at`。准备项存在账本、没有 `schedule_info`，不参与这一步。用完整快照提交，原样保留 `title`、`action`、`status` 和全部 `rule_ids`。
8. 与本次改期无关的规则（别场面试、岗位关注）原样不动。
9. 重读核对后在对话里重新挂一张 `interview-reminder` 卡。倒计时变了算实质变化，可按 [NOW 卡片](now-cards.md) 的门禁补一张提醒 Now；这场面试当天已发过就不再发。

已经触发过的 once 规则改 `run_at` 后会不会重新响，没有确认过。核对 `list_triggers` 回包里的实际状态，不能默认它一定会再触发；确认不会时按第 6 条当新规则补建，并从 `rule_ids` 里换掉旧 ID。

## 其他修改与结束

- 暂停：停用仍会推进该 Todo 的规则，保留事实和 Todo。
- 永久取消规则：先 `trigger/delete_trigger`，成功后再用完整 Todo 快照移除对应 rule_id。
- 面试完成或取消：仅在用户明确确认后更新事实、收口 Todo 并停用未来规则，不影响其他面试。
- Trigger 创建成功但 Todo 写入失败：保留停用规则，查询恢复并复用原 ID；不能盲目重建。

## 岗位关注

一个用户同一时间只有一条，绑定 Todo `watch-jobs`（`schedule_info={"kind":"MONITOR"}`）。停用创建：

```json
{
  "instruction": "加载 job-hunting，按场景 6 到点回调处理：重读当前 Thing 与账本 task.job_watch，按保存条件搜索岗位并与 seen_keys 做差集；有新增岗位时才发布岗位关注 Now，没有新增只记录检查时间，到期那一次另发收口卡。",
  "trigger_kind": "rrule",
  "title": "岗位关注推送",
  "run_at": "",
  "rrule": "FREQ=DAILY;UNTIL=20260930T235900",
  "dtstart": "20260924T090000",
  "enabled": false,
  "thing_id": "<真实 thing_id>",
  "todo_id": "watch-jobs",
  "timezone": "Asia/Shanghai"
}
```

| 频率 | `rrule` |
| --- | --- |
| 每天 | `FREQ=DAILY;UNTIL=<截止日>T235900` |
| 工作日 | `FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;UNTIL=<截止日>T235900` |
| 每周 | `FREQ=WEEKLY;UNTIL=<截止日>T235900` |

- `dtstart` 是今天之后第一个符合频率的推送时刻，时分即推送时刻；截止日默认开启日加 7 天。
- 换条件、换频率或「续一周」都用 `trigger/update_trigger` 原地改 `rrule`、`dtstart` 并保持 `run_at=""`，不删除重建。
- 取消：先 `trigger/delete_trigger`，成功后再用完整 Todo 快照移除 `rule_ids`。
- 到期后规则自然不再触发；最后一次回调负责收口 Todo 与 `task.job_watch.active`。
