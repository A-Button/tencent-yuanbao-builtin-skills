---
name: running_club_checkin
description: 用于管理跑团打卡群的成员、打卡记录与周成绩。当用户消息涉及以下任一场景时，必须调用此Skill
---

## 初始化

**背景**：skill 装在只读目录 `/data/skills/{slug}/`，不能在那里写数据。所以要把脚本复制到可写的**工作目录** `/data/user_persistent_data/{slug}` 再运行。数据库与审计（`tracker.db` / `audit_log.jsonl`）通过环境变量 `TRACKER_DATA_DIR` 落在 `/data/user_persistent_data`。

每个会话开始，按下面走即可：

**第 1 步：直接进入工作目录并运行命令（不要预先创建/复制）。** 

```bash
cd /data/user_persistent_data/{slug}                # 工作目录（脚本副本所在）
export TRACKER_DATA_DIR=/data/user_persistent_data  # 数据库/审计的持久化目录
python3 assets/tracker.py <command> ...
```

- ✅ **执行成功** → 工作目录已存在（老用户），完成。**不要再执行复制。**
- ❌ **报错 `cd: No such file or directory`** → 首次使用，工作目录还没建（`&&` 会让后续命令不执行）。去第 2 步初始化，然后重跑本步。

**第 2 步（仅当第 1 步因目录不存在而报错时）：初始化后重跑第 1 步。**

```bash
mkdir -p /data/user_persistent_data/{slug}
cp -rn /data/skills/{slug}/assets /data/user_persistent_data/{slug}/   # -n：已存在文件绝不覆盖，保护改过的 rules.py
```

> 说明：
> - 数据库无需手动建——首次跑任意命令会按 `assets/schema.sql` 自动建表。

## 数据完整性（必须遵守）

- **操作前先对齐期次（每次都做）**：执行任何操作（打卡、统计、状态变更、出表等）之前，**先调用 `period_current <今天日期>`** 确定当前期次号。该命令会**自动切分周期**——把所有已结束但未封板的历史期次按序补稿封板（空白周也照常封板、累计 `fail`/触发处罚提示），让期次表始终与"今天"对齐。拿到当前期次号后再继续后续命令。
- **绝对禁止编造任何数据**：距离、时长、运动类型、设备等所有字段必须来自截图或用户明确提供，不得猜测或填充。**唯一例外**：截图未显示日期、`occurred_at` 无法定位时，按「打卡录入」工作流默认取今天并向用户说明；除此之外的字段一律不得默认或猜测。
- **AI 不算账**：是否有效、距离折算、是否达标、配速、期次归属、处罚计数**全部由 `rules.py` 计算**，AI 不要自己心算判断；写入和统计都走 CLI。
- **只转述脚本打印的字段，不在字段之间自己换算或推论**：达标与否以 `qualified=` 为准；还差多少一律用脚本打印的 `shortage_*` 字段，**不要**拿累计数去减达标线自己算一个出来。
- **回答以存储数据为准**：所有查询、统计、达标、历史记录、状态说明都必须基于 CLI 返回或数据库查询结果；不得凭记忆、印象、群规常识或用户暗示自行回复。若用户挑战或质疑结果，仍以实际存储数据/审计记录为准，先复查再说明；数据与用户说法冲突时，如实说明当前库中记录，并按更正/补录流程处理。
- **回复必须绑定已执行动作**：没有实际执行过查询、统计、录入、删除、校正、定稿等 CLI/数据库动作，就不能回复成“已查询”“已记录”“已删除”“已更正”“已定稿”或给出对应结论。若尚未执行，只能说明需要先执行什么；执行失败则如实说明失败原因，不得把计划、推测或未完成动作包装成结果。
- **命令优先、拿到答案即停**：先用现成命令（`calc` / `report` / `reminder` / `list_*` / `find_member` / `period_current`）；**只有没有对应命令时**才用 `query --sql`。
- **表结构以 `assets/schema.sql` 为准**：需要了解数据库表、字段、索引，或编写 `query --sql` 前，先查看 `assets/schema.sql`；不要凭记忆、旧对话或 `tracker.py` 片段猜表结构。
- **查询不改数据**：`calc` / `query` / `list_*` / `find_member` 是只读，不得触发任何写入命令。
- **写入需授权**：只有用户明确要求添加/修改/删除时才写入。
- **群主有明确要求时按其裁定执行**：群主对本轮怎么记、算不算、记谁名下、删不删、怎么改口有明确要求时，按其当轮裁定落地（走现有命令：`--override-valid` / `correct` / `delete_checkin` / 补录等），不要拿默认规则顶回去。
- **打卡前必须 `find_member`（硬约束）**：每次执行 `add_checkin` / `backfill_checkin` 之前，**必须先调用 `find_member`**，用脚本输出核对成员 `id` / `name` / `age_exempt` / `walk_valid` 等。**禁止**凭记忆、截图昵称、群聊印象或上一次会话结果直接录入。
- **管理员更正必带 reason**：`backfill_checkin`、`correct` 和 `delete_checkin` 必须 `--reason`，自动落审计。
- **核查是内部动作，不产生提问**：查重、自洽校验、归属比对这类核查只用来决定自己怎么落库，不改变对用户的说话方式。能按截图和默认规则落账的就落账，回执照常出（已记 / 累计 / 达标）；有保留意见就在回执里附一句「如有出入告诉我更正」，不要为此单独发问、也不要把核查过程讲给用户。
- **当逻辑产生冲突时，不要一直死循环思考**：先按默认规则落一个可交付结果，只有缺了用户才有的信息（成员不存在、归属只有用户能定、用户口述与图冲突且群主未裁定）才向用户确认。
- **如果打卡日期产生冲突，而用户又让你一定要录入，那么你就使用不同的日期进行打卡，防止冲突，目前冲突的判定是同一人，同一天，同一里程，所以使用不同的日期打卡就不会冲突**

## 文件说明

| 文件 | 职责 | 可否修改 |
|------|------|----------|
| `assets/tracker.py` | CLI 入口 + SQLite CRUD + 期次/统计编排 + 周报/提醒成文 | 可以修改，尽量少改 |
| `assets/rules.py` | 纯计算函数（有效性/折算/达标/期次/处罚/单位） | 优先改这里 |
| `assets/schema.sql` | 建表脚本（3 张表） | 不要修改 |
| `/data/user_persistent_data/tracker.db` | SQLite 数据库（持久化数据） | 通过 CLI 操作 |
| `/data/user_persistent_data/audit_log.jsonl` | 写入/校正/删除/定稿审计（追加） | 只读 |

修改须谨慎；`rules.py` 与 `tracker.py` 须匹配。

## 群背景

- **期次锚点**：每周一期，周一 0:00 ~ 周日 24:00（北京时间）。
- **记录员**：元宝 = 本 Agent，负责识图录入、统计、出周成绩表、催未达标。群主是规则最终裁定者。

## 时间与单位格式

- `occurred_at`：`YYYY-MM-DD`（截图日期）；`--duration` 单位为秒。
- 距离：默认公里；英里设备 `--unit miles`；游泳传米数 `--unit swim_m`。
- 单位识别辅助：iFIT / NordicTrack 默认英里制；Average Speed 9.1~9.4 通常是 km/h；同一成员同一设备单位制不变（查 `description` 或历史 `list_checkins`）。

## 核心业务规则（具体实现在 `rules.py`）

1. **达标线**：周累计**有效**距离 ≥ 10 公里（游泳折算后即 ≥ 2500 米）。
2. **有效性（按类型分流）**：跑步配速 ≤ 10'00" 有效；10'00"~10'30" 有效但 `note` 提示管理员；> 10'30" 无效；< 4'00" 疑似错误判无效待确认。健走默认无效（距离仍留档），仅 `walk_valid` 成员有效。游泳全员可用、不限配速、1km 折算跑步 4km。`age_exempt`（60岁+）任何形式只看距离。
3. **期次归属（极严格）**：按 `occurred_at`（截图日期）归属，不是提交日期；绝不跨期混数。日常 `add_checkin` 只录当前期，历史/已封板期新增记录必须走管理员补卡 `backfill_checkin --reason`；如需更正走 `correct`/`delete_checkin`
4. **纪律处罚**：未达标发红包（人工）；连续 3 周未达标 → 强制退群；连续 4 周病假 → 退群休养。`period_finalize` 据此打印 `alert`。
5. **单位换算**：英里 km = miles × 1.60934；游泳 km = 米 ÷ 1000 × 4。

## 工作流

### 打卡录入

0. **本周综合打卡先确认**：如果用户发来的是"本周综合打卡"、"周汇总"、"一周累计"这类内容。如果包含每条明细，那么按照明细一条一条记录——**一张周打卡图里有几次运动就录几条，一图对应多行是正常情况，不要因为它们出自同一张图就合并或丢弃**。如果只有汇总，无逐条明细，那么合并成一条打卡记录计入，录入后向用户说明："已按周汇总合并成一条记录计入"
1. 识图提取：`occurred_at`（截图日期）、`distance_raw`、`unit`、`duration`（秒）、`activity_type`、`device`、原始描述（`--raw`）。**截图没有显示日期、`occurred_at` 无法定位时，默认按今天处理（`occurred_at` = `--today`），并在回执里简单说明一句**（如"截图没看到日期，已按今天记录"）。
   - **三项自洽校验**：距离、时长、配速必须对得上（配速 ≈ 时长 ÷ 距离）。算出的配速与图上显示的差超 5%，就是有字段读错了（最常见是把 PACE、速度、剩余时间那栏当成了距离）——重新分析各栏分别对应哪个字段、改对再落库，别带着矛盾继续录，也别把它当"数据异常"抛给用户确认。图上有配速就以图上为准。
   - **记下图片 id**：附件里的 `img_id=<32位十六进制>`（可能带 `_NN` 尺寸后缀）就是这张图的唯一 id，录入时写进 `--raw`，格式 `img=<id>; <原始描述>`。每条新写入都必须带上，去重靠它。只进工具参数，**不得出现在回执里**。
     - `img_id=-` 表示这张图确实没有稳定 id。此时**跳过 `find_by_img`**，改用「同成员 + 同期次 + 同 `occurred_at` + 同折算后 `distance_km`」比对已有记录来判重，并在 `--raw` 里只写描述、不带 `img=`。`--raw` 描述里别带撇号和双引号（配速写「7分16秒」，别写 `7'16"`），否则 bash 引号会崩、命令跑不起来。
2. **确认当前期次（`add_checkin` 前必做）**：先 `period_current <今天日期>` 拿到当前期次号，它会自动切分历史期次（补稿封板）。
3. 查成员（`find_member`）：录入用的成员 `id` / `user_id`、`name`、`at_name`（回执 @ 用）、`age_exempt` / `walk_valid`、单位习惯等一律以脚本输出为准，如果成员查询不到，需要先向用户确认，不要擅自建档
4. **按图片 id 查已有记录**（内部去重，与上一步 `find_member` 串在同一次 bash 调用）：`find_by_img <id1> [<id2> ...]`，多张图一次全传进去。它自己削 `_NN` 后缀、自己拼 LIKE，逐个 id 回一行 `img=<id> hits=<N>`。**不要改用 `query` 手写 SQL 查这件事**——`checkin` 表里没有 `activity` 列（真名 `activity_type`），手写时极易多带一个不存在的列名，整条查询报 `sql_error` 后一行输出都没有，查重就静默失效了。
   - **判重粒度 = 图片 id + 当前成员 + 当前期次**，不是图片 id 本身——一张周汇总图有几次运动就录几条。拿本轮要录的和查出的「同成员同期」记录按 `occurred_at` + `distance_km` 比对，只补录差集；别只比日期，无日期截图按今天落账，同期隔天重发日期就变了。差集为空就是重发或「以这张图为准」：不写库，拿现有记录报累计。
   - 查出的记录挂在**别人**名下、或落在更早的期次，都不影响本轮给当前这人录卡；归属只在用户这轮点名要改时才用 `correct` 动。
5. `add_checkin ... --today <今天日期>` —— **`--today` 必填**。脚本会据此强制校验：`occurred_at` 晚于今天、或早于当前期，直接拒绝（`error=checkin_date_rejected`），无需你心算判断。valid / 折算 / note / 期次自动算出。
6. 用输出里的 `note`（如"配速略超标，提示管理员"）决定是否 @ 管理员；用输出里的**累计字段**和 `qualified` 给出回执——脚本为这笔打印了几个累计口径就报几个（只打印 `period_total` 时就用它）。

### 管理员统一补卡

1. 只有管理员明确要求补历史/上一期/已封板期的新打卡时，才用补卡入口；日常当前期录入仍走 `add_checkin`。
2. 先查成员：`find_member <id|name|@名>`，确认 `id` / `name` 是目标成员。
3. 用 `backfill_checkin ... --today <今天日期> --reason '<原因>'` 新增补卡记录；距离、单位、时长、设备、截图日期等字段仍必须来自截图或用户明确提供。
4. `backfill_checkin` 会落审计，仍拒绝未来日期和重复记录；补卡不触发自动封板，也不重写已封板期次的冠军/封板字段。
5. 更正/删除已有记录不要用补卡：更正用 `correct ... --reason '<原因>'`，删除用 `delete_checkin ... --reason '<原因>'`。

### 出周成绩表 / 周报（用 report）

**何时用**：凡涉及周总结 / 周报 / 周成绩表 / 报表 / 本周汇总 / 出表 / 定稿表等"要发群的整表" → 用 `report`；只是临时查打卡或排行 → 用 `calc`（见下一节）。

1. `period_current <今天日期>` 对齐期次，拿到期号 N（自动补稿封板历史期次）。
2. `report --num <N> [--rocket '{"id":"..","name":"..","distance":N}'] [--grandslam <N>] [--out <路径>]` 生成成文，**原样**发群，别贴 SQL/JSON。

### 查询打卡情况（用 calc）

1. 先 `period_current <当前时间>` 拿到期号 N。
2. **整体排行**：`calc --period <N>`（按公里降序，只含已打卡成员；要全员/未打卡名单用 `report`/`reminder`）。
3. **查某人**：`find_member <id|name|@名>` 拿 `id` → `calc --member <id> --period <N>`（出明细 + `total_km` / `count` / `qualified` / `shortage_km`）。
4. 用 `calc` 输出组织回执，别把 SQL/JSON 贴给用户。

### 删除打卡记录（按日期，限单个成员）

1. **先定位成员**：`find_member <id|name|@名>` 拿到 `id`，确认删的是对的人。
2. **按成员 + 日期列出当天打卡**：`list_checkins --member <id> --date <YYYY-MM-DD>`（`--member` 必带，把范围锁定到这一个人）。输出每条的 `event_id` / `activity` / `distance_km`。
3. **确认要删哪条**：
   - 0 条（输出 `(empty)`）→ 该成员当天没有记录，告知用户，不执行删除。
   - 1 条 → 即为目标。
   - 多条（同一人同一天多次运动）→ **不要擅自猜**，除非用户说了删除当天所有的记录
5. 逐条删除：`delete_checkin <event_id> --reason '<原因>'`（软删，`deleted_at` 标记，可审计追溯）。
6. 删除后若涉及达标判断，用 `calc --member <id> --period <N>` 重新出该成员本期累计，再组织回执。

### 登记病假 / 恢复 / 销假

1. 查成员：`find_member <id|name|@名>` 拿到 `id`。
2. 登记：`add_status <id> <occurred_at> sick_leave [--reason '<请假说明>']`。`occurred_at` 决定请假生效时间**默认只管当期，下一期自动恢复**；要续假就下期再登记一次。连续病假周数据此**现算**。
3. 恢复期同理：`add_status <id> <occurred_at> recovering`。
4. **销假/提前回归**：`add_status <id> <occurred_at> active`
5. **已封板期不可改状态**（报 `period_finalized`）；确需更正历史请假用 `correct period <num> member_status '<JSON>'`。

### 查询某人状态 / 病假时长

1. `find_member <id|name|@名|别名> [--asof <YYYY-MM-DD>]` 一条命令即可，输出含 `status`（**有效状态**，按 `--asof` 所属期派生）、`since`（当前连续请假段的起始周一）、`alias`（别名串，；分隔）、`sick`（病假第几周，含当周）、`recover`（恢复期第几周，含当周）、`fail`（连续未达标周数）。这些都由脚本**现算**，无需自己数。
2. `--asof` 不传=当前期；**可传未来日期查"那一周的状态"**（含已提前登记的假）。
3. 若 `status=sick_leave`，`sick=N` 即**当前所处的病假第 N 周**（含未封板的当周；刚请假当周为 1）；越接近 `SICK_LIMIT`（4）越要在回执里提示管理员。
4. 用这几个字段组织回执，不要把原始 `key=value` 整行贴给用户。

## CLI 命令

所有命令在工作目录 `/data/user_persistent_data/{slug}` 下通过 `python3 assets/tracker.py <command>` 调用，输出为 `key=value` 纯文本。

### 成员管理

```bash
# 添加成员（id、name 必填）。--age-exempt 1 表示 60岁+ 豁免；--walk-valid 1 表示健走有效
# --alias 别名/外号（多值用 ； 或 ，分隔，仅供查找）；建档时只在很确定时才填，见下方提示
python3 assets/tracker.py add_member <id> <name> [--at-name <@名>] [--alias '小祥；祥子'] [--sort <n>] \
    [--status active] [--age-exempt 0|1] [--walk-valid 0|1] [--description '<文本>']

# 更新成员（只改提供的字段；可改 status 用于退群 exited / 外卡 wildcard 等管理态）
# --alias 是【整体覆盖】别名（传空串清空）；只想补充别名请用下面的 add_alias
python3 assets/tracker.py update_member <id|name|@名> [--name ...] [--at-name ...] [--alias ...] \
    [--sort n] [--status ...] [--age-exempt 0|1] [--walk-valid 0|1] [--description ...]

# 给已注册成员【追加】别名（去重，不覆盖已有；多值用 ； 或 ，分隔）
python3 assets/tracker.py add_alias <id|name|@名> '<别名>'

python3 assets/tracker.py find_member <id|name|@名|别名> [--asof <YYYY-MM-DD>]
python3 assets/tracker.py list_members [--asof <YYYY-MM-DD>]
```

> **`name` / `at_name` / `alias` 三者职责不同**：
> - `name`：正式名（精确匹配）。
> - `at_name`：群里 @ 人的句柄（**单值、精确**，`reminder` 直接拿它拼 `@xxx` 发群）。**不要废弃**——别名不能替代它的 @ 功能。
> - `alias`：别名/外号（**多值、`LIKE` 模糊匹配**），只用于查找，不参与 @人。
>
> **查找匹配规则**：`find_member` / 各命令的成员入参写法不变，脚本内部依次 `id`→`name`/`at_name`（精确）→`alias`（模糊）匹配；别名模糊匹配可能命中多人（取 `sort_order` 最小者），**拿到结果务必核对 `id`/`name` 是不是想找的人**。

> **⚠️ 写别名前必须确认（重要）**：只有当你**非常确定**某个称呼确实是该成员的别名时，才写进 `alias`（`add_member --alias` / `add_alias` / `update_member --alias`）。**只要有一点不确定，先在群里/向用户问清楚「这是不是某某的别名」，得到明确确认后再补充**。绝不要凭猜测往别名字段里塞，错误的别名会让以后查错人。

### 打卡录入

```bash
# 录入一条打卡（valid / distance_km / note / period 由 rules.py 自动算出）
# --today 必填：今天的日期 YYYY-MM-DD
python3 assets/tracker.py add_checkin <member> <occurred_at> <activity_type> <distance_raw> --today <今天日期> \
    [--unit km|miles|swim_m] [--duration <秒>] [--device <名>] [--raw 'img=<图片id>; <原始描述>'] [--override-valid 0|1]

# 管理员补卡：给历史/已封板期新增打卡记录（必须带 reason，落审计）
python3 assets/tracker.py backfill_checkin <member> <occurred_at> <activity_type> <distance_raw> --today <今天日期> \
    --reason '<补卡原因>' [--unit km|miles|swim_m] [--duration <秒>] [--device <名>] [--raw 'img=<图片id>; <原始描述>'] [--override-valid 0|1]

python3 assets/tracker.py list_checkins [--member <m>] [--period <n>] [--date <YYYY-MM-DD>]

# 按图片 id 查已有打卡（录入前查重专用，别手写 LIKE SQL）
# 传裸 id / img=<id> / 整条 url 都行，_NN 后缀自动削掉；逐个 id 回一行 img=<id> hits=<N>
python3 assets/tracker.py find_by_img <id1> [<id2> ...]

# 软删一条（带 reason，落审计）
python3 assets/tracker.py delete_checkin <event_id> --reason '<原因>'

# 通用校正一列（带 reason）。改 checkin 原始字段会自动重算派生列；
# 直接改 valid 视为管理员覆盖，recompute 不再回填它
python3 assets/tracker.py correct <member|checkin|period> <pk> <field> <value> --reason '<原因>'
```

`occurred_at` 用**截图日期**（决定期次归属）。`activity_type` / `--unit` 必须是 `rules.py` 里 `ACTIVITY_TYPES` / `UNITS` 的值（默认类型 `outdoor_run / treadmill / indoor_run / swim / walk`，默认单位 `km / miles / swim_m`）。游泳传原始米数 + `--unit swim_m`；英里制设备传原始英里 + `--unit miles`。

`add_checkin` 写入前自动拦截三类情况（直接报错、不写入）：

- **日期非法（仅当前期可录）**：`occurred_at` 晚于 `--today`，或所属期次早于当前期（默认 `BACKFILL_MAX_LAG=0`），拒绝（`error=checkin_date_rejected`）。此判定**只比较期次号、不依赖封板状态**，对从无打卡的历史空白期同样生效。确需新增历史打卡用 `backfill_checkin --reason`；更正/删除已有记录用 `correct` / `delete_checkin`。
- **已截止周期不可补录（兜底）**：当前期若被提前 `finalized`，仍拒绝（`error=period_finalized`）。
- **重复打卡判定**：**同一人 + 同一天 + 同里程（折算后 `distance_km`）** 视为重复，拒绝（`error=duplicate_checkin`）。同日不同里程的多次运动正常分别录入；**同日同里程但两条 `img=` 不同时放行**（那是两次真实运动）。任一条没带图片 id（老数据、口述录入）仍按重复拒绝，确属两次真实运动的只能用 `correct` 人工处理。

写入成功后若多打印 `warn=same_image_in_period img=<id> existing=<N>`，是提示不是错误：周汇总图录多条明细属正常，忽略即可；若本轮只该录一条，说明图被重复消费，`delete_checkin` 撤掉刚写的再出回执。

### 状态变更

```bash
# 直接更新 member.status（单一真相源）并落审计；occurred_at 仅写进审计备注
python3 assets/tracker.py add_status <member> <occurred_at> <active|sick_leave|recovering|suspended> [--reason ...]
```

退群（`exited`）/ 外卡（`wildcard`）这类管理态直接 `update_member --status` 或 `correct member`。

### 期次管理

```bash
python3 assets/tracker.py period_current <今天日期>   # 返回该日期所属期次（自动建期）；并自动切分周期：把之前未封板的期次按序补稿封板（打印 auto_finalized=...）。日期由你从上下文传入
python3 assets/tracker.py period_finalize --num <N> [--champion <member>]
```

`period_current` 是**每次操作的第一步**：除返回当前期次外，会把"今天"之前所有未封板期次按序自动定稿（与 `add_checkin` 同口径，含空白周），输出形如 `auto_finalized=period=<N> ...` 及可能的 `alert=...`。因此它**会写数据**（定稿、累计 `sun`/`fail`、触发处罚提示），不属于只读命令。

`period_finalize`：标记定稿 + 冠军 `sun_count +1`，并按现算的连续计数打印处罚提示（`alert=...`）。
**幂等**：对已定稿的期次重复执行直接 `skipped=already_finalized`、不重复累加 `sun_count`（定时任务重跑安全）。务必按期次顺序定稿。

### 统计与输出

```bash
# 单人本期累计 + 达标（也支持 --from/--to 日期范围）
python3 assets/tracker.py calc --member <m> --period <N>

# 全期排行（临时查"本周打卡情况/排行"用这个，只含已打卡成员）
python3 assets/tracker.py calc --period <N>

# 周成绩表 / 周报 / 周总结（要发群的整表走这个，别用 calc 拼整表）；确定性成文，可 --out 存档
python3 assets/tracker.py report --num <N> \
    --rocket '{"id":"..","name":"..","distance":N}' --grandslam <N> [--out /data/user_persistent_data/第N期.md]

# 周日未达标提醒
python3 assets/tracker.py reminder --num <N>

# 任意只读分析（SQL）
python3 assets/tracker.py query --sql "SELECT ..."

# 改了 rules.py 后回填全部（或某期）派生列
python3 assets/tracker.py recompute [--period <N>]
```

`report` / `reminder` 直接输出可发群里的成文，**不要把 SQL/JSON/审计贴给用户**。

## 输出格式

```
# add_checkin（含本期累计，便于直接写回执）
event_id=wangyang_2026-05-18_01 member=王阳 occurred_at=2026-05-18 period=440 activity=outdoor_run distance_km=11.71 valid=1 note= period_total=11.71 qualified=1 shortage_km=0

# calc 单人
[detail]
event_id=... date=2026-05-18 activity=outdoor_run distance_km=11.71 pace=6'03"/km
[total]
member=王阳 total_km=20.71 count=2 qualified=1 shortage_km=0

# calc 排行
[ranking]
rank=1 member=王阳 total_km=20.71 count=2 qualified=1

# 错误
error=member_not_found query=张三
```

## 修改 rules.py 的规范

### 原则

1. **只改函数内部逻辑/数值或顶部常量**，不改函数签名（参数名、返回类型）。
2. **保持纯函数**：不读数据库、不做 I/O、不 import sqlite3。
3. **每个分支都有兜底 return**，保留类型标注。
4. 改完后跑 `python3 assets/tracker.py recompute` 回填历史数据的派生列。

### 可修改的函数 / 常量

| 名称 | 作用 |
|------|------|
| `ACTIVITY_TYPES` / `UNITS` / `QUALIFY_KM` / `MILES_TO_KM` / `SWIM_FACTOR` / `PACE_*` / `PERIOD_*` / `BACKFILL_MAX_LAG` / `FAIL_LIMIT` / `SICK_LIMIT` | 允许的运动类型和单位；以及各项阈值/系数/锚点/补录窗口常量 |
| `effective_km(activity_type, distance_raw, unit)` | 距离折算（英里、游泳代跑） |
| `judge_validity(activity_type, distance_km, duration_seconds, age_exempt, walk_valid)` | 有效性判定 → `(valid, note)` |
| `is_qualified(total_km)` | 是否达标 |
| `period_for_date(occurred_at)` / `period_bounds(num)` | 期次归属与边界 |
| `reject_checkin_date(occurred_at, today)` | 录入日期合法性（未来日期/当前期以前补录）→ `(reject, reason)` |
| `fail_streak(qualified_recent_first)` | 连续未达标周数（遇达标即停） |
| `status_streak(statuses_recent_first, target)` | 连续病假/恢复周数（每期有效状态新→旧，遇不等即停） |
| `discipline_alert(counts)` | 处罚提示 |

### 修改示例

**"达标线改成 15 公里"**：

```python
QUALIFY_KM = 15.0
```

**"健走配速 ≤ 9'00 也算有效"**（在 `judge_validity` 的 walk 分支加判断）：

```python
if activity_type == "walk":
    pace = pace_sec_per_km(distance_km, duration_seconds)
    if walk_valid or (pace is not None and pace <= 9 * 60):
        return (True, "")
    return (False, "非豁免成员健走不计入")
```

**"连续 2 周未达标就退群"**：

```python
FAIL_LIMIT = 2
```

**"新增骑行，5 公里折 1 公里跑步"**（`ACTIVITY_TYPES` + `effective_km` + `judge_validity` 三处一起改）：

```python
ACTIVITY_TYPES = ("outdoor_run", "treadmill", "indoor_run", "swim", "walk", "cycle")

# effective_km 里、return distance_raw 之前：
if activity_type == "cycle":
    return distance_raw / 5.0

# judge_validity 里、健走分支之前：
if activity_type == "cycle":
    return (distance_km > 0, "")
```

## 边界情况

遇到 `rules.py` 未覆盖的场景：**先在群里问管理员，得到决定后再写入**（用 `--override-valid` 或 `correct`），事后把新规则加进 `rules.py` 对应函数。不要猜——猜错会让 valid/距离进入错误状态，影响后续所有统计。