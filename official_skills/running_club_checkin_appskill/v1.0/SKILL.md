---
name: running_club_checkin_appskill
description: 用于管理跑团打卡群的成员、打卡记录与周成绩，并在群聊内嵌「打卡录入」卡片 App。当用户消息涉及打卡录入（发运动截图、口述里程、@元宝要求记打卡）、成绩统计、周报/催办等场景时，必须调用此 Skill：识别到打卡意图即出可编辑卡片（draft_checkin），用户在卡片上点确认后才落库（commit_checkin）。
keywords:
  - 打卡
  - 跑团
  - 打卡卡片
  - 录入
  - 确认
  - 周成绩
packageType: app-skill
instructionOnly: false
metadata:
  version: v1.0
---

## 初始化

**命令一律在只读挂载点发起**：`/data/skills/running_club_checkin_appskill/`。脚本不往自己所在目录写任何东西，落盘一律由 `TRACKER_DATA_DIR` 指到 `/data/user_persistent_data`。

**全群只有一个库**：`/data/user_persistent_data/tracker.db`（`tracker.py` / `ledger_api` / `_run.py` 共用）。沙箱里漏掉 `export` 也会落到这个正库，**禁止**在 skill 目录下再建旁路库。

**业务规则代码另有一份可写副本**（运行目录）：`/data/user_persistent_data/running_club_checkin_appskill/assets/`。`assets/tracker.py` 每次启动会自动维护它——`rules.py` / `tracker.py` 缺失才拷、之后永不覆盖（管理员改的阈值不会被技能包更新冲掉），`schema.sql` / `persist_paths.py` 每轮对齐最新版。**这套拷贝在 Python 里完成，你不需要也不允许手工 `cp`/`mkdir`。**

### 硬禁令（违反会拖慢整轮，必须遵守）

- **禁止** `find /`、`find /data`、全盘搜 `tracker.py` / `running_club*`；**禁止**用 `ls` 做排障巡检（不要 `ls /data`、`ls /data/skills`）。
- **禁止**自己用 `cp` / `mkdir` 复制 skill 目录。运行目录由 `assets/tracker.py` 自动播种，你手工拷会拷出第三份残留代码。**命令一律在 `/data/skills/` 下发起。**
- **禁止**在任一业务命令已成功后，再执行 `mkdir` / `cp` / `ls` / `find`。
- **禁止**把路径写成字面量 `{slug}`；本 skill 目录名固定为 `running_club_checkin_appskill`。
- 初始化预算（整轮上限）：业务尝试 →（失败则）**`load_skill` 一次 + 业务一次**。用尽仍失败再告知用户，**停止排障**。

### 流程

**第 1 步：进 skill 目录直接跑业务（不要预先 mkdir/cp，不要先 ls/find）。**

```bash
cd /data/skills/running_club_checkin_appskill
export TRACKER_DATA_DIR=/data/user_persistent_data
python3 assets/tracker.py list_members
# 或：python3 assets/tracker.py period_current "<今天或当前日期时间>"
```

- ✅ **任一业务命令成功** → 初始化完成，**立刻做业务**；禁止再初始化/探测。
- ❌ `cd: No such file or directory`（挂载点还没就绪）→ **不要说未就绪、不要 ls**：再调用一次 `load_skill`（name=`running_club_checkin_appskill`），然后**立刻重跑第 1 步**。
- ❌ **其他错误**（python 报错、参数错）→ 按报错信息改命令重试，不是去 `ls` / `find`。
- 第二次仍失败 → 才回复「打卡技能文件未挂到沙箱，请稍后重试」；**禁止**继续探测。

> 数据库无需手动建——首次命令会按 `assets/schema.sql` 建表；卡片链路与 tracker 共用同一 `tracker.db`。
> `load_skill` 只把说明注入上下文不够，必须让 `/data/skills/running_club_checkin_appskill/` 在沙箱里真实存在才能跑脚本。

## 打卡卡片：总原则（先读这段再动手）

**新模型：识别打卡语义 → 出「可编辑打卡卡片」→ 用户在卡片上点确认才落库。** 不再有「待归属 / 待兑现 / 冲突」这些台账语义；旧台账 operation（`list_ledger` / `ingest_image` / `attribute` / `set_redeem_rules` / `redeem` / `delete_ledger`）已下线，调用会直接报错。

- **落库的唯一入口是「卡片确认后的 `commit_checkin`」。** 任何打卡记录都必须先出卡、等用户在卡片上点确认，你才在下一轮 `commit_checkin` 落库。**没有卡片确认这一步，就绝不能把打卡写进库**——包括但不限于直接跑 `assets/tracker.py add_checkin` / `backfill_checkin` 等写库命令。哪怕这一轮因为某种原因没成功出卡，也只能如实说明、引导用户重发，**不允许"顺手先记上"**。

- **⚠️ 卡片只能由 `draft_checkin`「调用工具」生成，不能靠文字描述。** 对象已按语序定下来、并拿到**任意**字段（哪怕只有打卡对象名、或只有图里 OCR 出的距离/用时/日期）时，就**必须真正调用一次 `draft_checkin`** 把卡片发出来。**严禁只在回复正文里罗列「距离/用时/日期/配速…」并说「核对无误后点确认即可录入」之类，却没有实际调用 `draft_checkin`**——前端的卡片来自 `draft_checkin` 产生的 app 资源事件，你不调工具，用户界面上就**根本不会出现任何卡片**，也就无从点确认，打卡直接断链（这是真实发生过的线上故障）。记住：**出卡 = 调用 `draft_checkin` 工具，不是把字段用文字念出来**。成功调用 `draft_checkin` 之后，正文只需一句「已生成打卡卡片，请在卡片上核对并确认」，**不要再把字段复述一遍**。对象还没定的记录，允许先问、先不出卡。

**核心原则**：

- **只要识别到打卡意图**（发运动截图说打卡、口述「我今天跑了 X 公里」、@元宝要求给某人记打卡等），就出一张**可编辑打卡草稿卡片**（`draft_checkin`）。**信息有啥放啥，允许不全**——缺的字段用户可以在卡片上补。**对象必须先按语序定下来**（见下条）；对象没定的卡先不要出。
- **图和对象按语序绑，不要做「N 图 × M 人」匹配**：说明文字管它**前面最近**那张/那组图。「我的打卡 / 算今天的」= 发送人自己；「evan的打卡」= evan。**一条消息里多张图 + 一句「我的」= 这组都是我的**，禁止把附件 2 匀给另一个人。例：`[图1 图2] →「我的打卡」→ [图3] →「evan的打卡」` = 图1、图2 归发送人，图3 归 evan。**不要**因为看到两个名字，就把 3 张图拆成「两边给我、中间给对方」。对不上（图数和人数对不上、或这句话跟的图不唯一）→ **先问一句「哪张是谁的」**，只出已绑死的卡，未绑死的先不出。
- **区分「打卡录入」与「查询」**：带了新的运动截图或口述成绩，再说「我的打卡 / 算今天的 / evan的打卡」= **录入**，出卡。只有**没有新图、也没有口述成绩**、纯问「看看我这周跑了多少 / 我的打卡记进去了吗」才当**查询**，用只读命令（`find_member` / `calc` / `list_checkins`）文字回答。拿不准是录入还是查询时，有图就按录入出卡；没图再当查询。
- **一卡 = 一条待落库 checkin**。语序绑好之后，每条记录分别调 `draft_checkin`，每次一个**独立 `card_id`**。先绑人，再出卡；不是先按图数出齐再猜 `member`。
- **⚠️ 一卡 = 一次 `bash`，禁止串跑。** 每张卡必须**单独调一次 `bash` 工具**，`command` 里只能有 **1 行** `python3 scripts/_run.py ledger_api '...draft_checkin...'`。**禁止**在同一次 `bash` 的 `command` 里用换行或 `&&` 连写多个 `_run.py`（会把多段 `__ONEAGENT_APP_RESULT__` 挤进同一份 stdout，超长截断后客户端会丢卡——真实故障：5 张 draft 串一条 bash，群里只收到 3 张）。多张卡时**同一轮可 batch 调多个 `bash`**（每次仍只含 1 个 `draft_checkin`），不要合并成一条命令。
- **每张卡引用「那条带图/打卡消息」本身**（`quote`）：**优先引用带图那条消息**——`quote.seq_id` 填被引用消息的 seq_id（供前端点击跳转）、`quote.image_url` 填图 URL、`quote.text` 用简短占位如 `[图片]`，**不要把 `@元宝…` 整句原话塞进去**。draft 时定死、随卡不变；引用块由前端 host 渲染并支持点击跳到被引用消息。
- **draft 不落库**——它只出卡，绝不写 `checkin`。**只有用户在卡片上点「确认」**，你才会在下一轮收到确认信号并 `commit_checkin` 落库。
- **落库前建档必须完成（建档前置）**：打卡对象若在群内**未建档**，先在群里提示/确认建档（`add_member`），**建档完成后再出卡**；`draft_checkin` 返回 `member_registered=false` 时提醒用户先建档。**落库阶段绝不自动建档。**

### 每轮决策（按序判）

1. **是不是打卡意图？** 运动截图 / 口述里程 / @元宝要求记打卡 → 是。表情包、风景、闲聊 → 不是，普通回复即可。
2. **打卡对象是谁、建档了吗？** 先按上一条语序规则把每张图绑到人；绑不上就问，不要猜。未建档 → 先提示建档，**不出卡**；已建档 → 继续。
   - **有图且附件行有 `img_id=` 时，出卡前先查重**（与 `find_member` 串在同一次 bash）：`find_by_img <id1> [<id2> …]`（可裸 id / 整条 url；`_NN` 后缀自动削掉）。**判重粒度 = 图片 id + 当前成员 + 当前期次**（先 `period_current`）；与已有记录按 `occurred_at` + `distance_km` 比对，只补差集。差集为空 = 重发或「以这张图为准」：**不再出重复卡**，用已有记录报累计。**禁止手写 SQL 查重**（`activity` 列名陷阱会导致查重静默失效）。`img_id=-` 表示无稳定 id → **跳过 `find_by_img`**，改按同成员+同期+同日期+同里程判重。
3. **拆几张卡 → 每张都必须实际调用 `draft_checkin`（不是文字描述）**：只给**已经绑死对象**的记录出卡：一条记录一张卡，独立 `card_id` + 各自的 `quote`（引用对应的那条消息/那张图）。有啥字段填啥（member / distance_raw / unit / activity_type / occurred_at / duration_seconds / location / img_id / note）。**地点认得出就填 `location`（卡面上的「地点」行），不要塞进 `note`——`note` 不出卡。** 认不出地点就不传 `location`，禁止编造。**对象已定、也识别出打卡内容时，不能只用文字把它说出来——必须走 `draft_checkin` 工具，否则不会有卡。** 对象未定的那几张，允许只问一句，先不出卡。**每张卡各调一次 `bash`**（见下条「一 bash 一 draft」），同一轮可连续 batch 多个 `bash`，禁止把多个 `draft_checkin` 拼进同一条 `command`。
4. **等用户确认**：全部 `draft_checkin` 的 `bash` 都跑完后，**先核对本轮 tool 回包**：应有 **N 条** `__ONEAGENT_APP_RESULT__`（N = 本轮要出的卡数）。不足 N 条 → **补调缺的 `bash`**，禁止先说「N 张卡都出好了」。核对无误后再 `send_message` 导语（一句即可，**不要复述字段**），**不要自己 `commit_checkin`**。
5. **收到确认信号**（下一轮上下文中会出现「用户点击了运动打卡卡片【确认】」，下面跟着「卡片当前数据如下」列出这张卡的字段）→ 把快照里每一行译成 `commit_checkin` JSON 传全（`member` / `occurred_at` / `activity_type` / `distance_raw` / `location` 等），**禁止只传 `card_id` + `today`**——bash 脚本读不到 app.env / 底账。回执一句「已录入」即可。**确认成功后前端会把这张卡就地冻结成绿色「已确认」快照、常驻消息流**（按钮消失、不可再编辑，作为一份历史快照永久保留，刷新后仍在）——你无需也无法再更新它。**取消由前端直接把卡片置灰保留、不经过你**——你不会收到取消消息，无需处理。**注意：确认消息本身不含协议 JSON，字段都在「卡片当前数据如下」里；收到它时只 `commit_checkin` 落库并简短回执，绝不因为这条消息再 `draft_checkin` 出新卡，也不要把字段罗列/复述出来。**
   - **⚠️ 确认轮＝只办本轮这一张卡，其它一律不碰。** 后端在确认轮**只会把「被确认那张卡」的 env 快照**注入 system（按 card_id 精确取回，不是全部待办卡）。因此你**只对这张卡 `commit_checkin` 落库**即可。**严禁在确认轮里为「历史里其它还没确认的草稿卡」再 `draft_checkin` / 再出卡 / 再提醒**——哪怕对话历史里明明还留着别人（如另一位成员）那张没点确认的卡。那些卡会等**它们自己的确认轮**各自处理；你这一轮多画一张，界面上就会凭空冒出/重复一张卡（这是真实发生过的线上故障：确认 A 的卡，回复却把 B 的卡又画了一遍）。记住：**一轮确认 = 落一张卡 + 一句回执，不多做任何 draft。**
   - **⚠️ 用户点确认失败会自动换卡。** `commit_checkin` 校验失败或没落库成功时，skill **已经**把旧卡打成取消态、并新出一张待确认卡（回包 `reissued=true`，带 `cancelled_card_id` / `new_card_id`）。你只要把失败原因告诉用户、请他们在**新卡**上补齐再确认。**不要**对旧卡再 commit，**不要**再自己 `draft_checkin`，**不要**绕去 `add_checkin`。
   - `send_message` **必须引用这张卡片所在消息**（`ref_seq_id` 填本条确认消息的 seq_id）。这是确认回执，即使发送者是元宝也要引用。
   - **⚠️ 无条件先调 `commit_checkin`。** 不要先查成员/期次去预判能不能落库，也不要自己判定失败就只回文字。未建档等失败原因 skill 会接住并把旧卡 `update` 成已取消、另出一张待确认新卡；你不调，那张卡就永远停在「待确认」。
6. **收到超时自动确认**（「运动打卡卡片超时未操作，系统自动确认」）→ 按「卡片当前数据如下」译成 JSON 调 `commit_checkin`，**必须带 `auto=true`**。这一轮**只有 update，没有 create**：
   - **成功**：只 `update` 这张卡为已确认，回「已录入」。
   - **失败**：skill **已经**只把这张卡 `update` 成已取消，**不会出新卡**。你只告诉用户超时未落库、卡片已取消。**不要**再 `draft_checkin`，**不要**对这张卡再 commit，**不要**说已录入。
   - **若任一必填字段为 `（空）`**（如对象/日期/距离/时长）：禁止从历史补填；照缺参 `commit_checkin(auto=true)`，由 skill 取消该卡。
   - `send_message` **必须引用这张卡片所在消息**（`ref_seq_id` 填本条超时确认消息的 seq_id）。
   - **⚠️ 无条件先调 `commit_checkin`，落不落得进库由 skill 判。** 严禁先 `find_member` / `list_members` / `period_current` 去预判「这人建档了吗、能不能落库」，更严禁自己判定失败就只回一句文字。哪怕对象明显没建档，也要照调——未建档、日期非法、重复打卡这些失败原因 skill 都会接住，并**把这张卡 `update` 成已取消下发给客户端**，再把原因回给你转述。你不调，客户端那张卡就一直停在「待确认」，用户看到的是一张永远转圈的卡（这是真实发生过的线上故障：模型查到 `member_not_found` 就直接回「卡片已超时自动取消」，可卡片根本没被取消）。

### 硬约束（少而硬）

- **draft 必须带 `user_id`**：填本轮触发这张卡的那个人的 `user_N`（看消息 extra：`user_1` / `user_2`）。A 替 B 打卡填 A。漏填会报缺参、不出卡。禁止留空，禁止拿对象名/成员 id/元宝顶替。确认/超时确认不用填。
- **一卡一 `card_id`；纠正＝`supersedes` → 旧卡 update 已取消 + 新卡 create**：多条记录分别 `draft_checkin`，各带不同 `card_id`；同一条记录的 draft→commit 用**同一个 `card_id`**串起来。**首次 draft 就要显式传一个你自己生成、能记住的 `card_id`**（如 `c_<member>_<两三位随机>`），不要依赖脚本兜底生成。**用户要求纠正/修改某张【还没确认】的卡**（如「说错了，是 00:54:20」「他用时改成 00:29:00 哈」「距离不对，是 3.99」）时：**另开一张【新 `card_id`】的卡**承载纠正后的全部字段，并把**被纠正那张卡的旧 `card_id` 填进 `supersedes`**。skill 会同轮把旧卡 `update` 成已取消、再 `create` 新卡。**怎么拿到旧 `card_id`**：优先看上下文里那张未确认卡的 `card_id`，其次看你上一轮 `draft_checkin` 返回的 `card_id`。⚠️ **不要复用旧 `card_id`、不要漏填 `supersedes`、不要自己再调 `cancel_checkin`**。只有当用户明显是给**另一个人/另一条记录**打卡时，才是全新的一张卡（不带 `supersedes`）。
- **对用户禁止贴命令**：群聊回复里不要出现 `python3`、`assets/tracker.py`、`add_member`、`ledger_api` 或任何 CLI。让用户建档就说「先把 XX 建成群成员」，等用户明确说建档你再自己调命令，不要把命令教给用户。
- **建档前置只管出卡这一步**：未建档时不 `draft_checkin`、不落库，用人话提示建档（别硬记、别贴命令）。但**已经有卡在等确认时，这条不能拿来跳过 `commit_checkin`**：确认 / 超时确认收到就必须调，未建档会报 `MEMBER_NOT_FOUND`，skill 据此把卡打成终态（超时→已取消；用户点确认→旧卡取消 + 新卡待确认）。**卡片的终态只能由 skill 下发，你用文字宣布不算。**
- **落库最小字段**：`member`（已建档）/ `occurred_at` / `activity_type` / `distance_raw`(>0) 四者齐全才能 `commit_checkin`，**禁止只传 `card_id`**；卡片本身也会在这四项齐全前禁用「确认」按钮。
- **快照（空）= 禁止猜填**：「卡片当前数据如下」里，凡 `required: true` 的字段若显示为 `（空）`（如 `对象（member）：（空）`、`日期（occurred_at）：（空）`、`距离（distance_raw）：（空）`），表示界面快照里该字段确实缺失。**禁止**用上一轮 `draft_checkin` 回包、历史 tool、`card_id`、触发语或 `find_member` 结果补填任一字段。照缺参调 `commit_checkin`，由 skill 走失败/取消协议；**禁止**自行填上后说已录入。
- **运动类型默认户外跑、有信号必须直接改**：`draft_checkin` 不传 `activity_type` 时默认 `outdoor_run`（卡片/后端同口径），让草稿天然可确认。但只要**截图或用户描述**表明是其它类型（游泳 `swim`、健走 `walk`、跑步机 `treadmill`、室内跑 `indoor_run` 等），**必须在 `draft_checkin` 就直接传对应类型覆盖默认值，禁止反问用户"是不是户外跑"**。默认只是"没有任何信号时"的兜底，不是让你偷懒不看图。
- **一次落库 = 一条 operation**：`commit_checkin` 内部一条命令原子落库，禁止你自己拼多步。`draft_checkin` 同理：**一次 `bash` 只跑一个 `ledger_api` JSON**；多卡 = 多次 `bash`，不是一条 `bash` 里多行 `_run.py`。
- `commit_checkin` 幂等：同一卡重复确认（同人+同天+同里程）视为已录入，不会重复记。
- 数字字段传 JSON number；`phase=error` 且 `reissued=true` 时是用户点确认失败：旧卡已取消、新卡已出，如实说失败原因并等用户在新卡上确认，禁止旁路 `add_checkin`、禁止对旧卡再 commit。超时（`auto=true` / `reissued=false`）只取消旧卡、没有新卡，禁止再 draft。
- `display_mode` 只透传、不编造；draft/commit 固定挂消息卡片，无需你指定。

### 修改已落盘记录（编辑流）

用户要改一条**已经录入/落库**的打卡（如「把 cloe 那条 10 公里改成 3.99」「她那天是游泳不是跑步」）时，**不要**直接改库，走卡片编辑流：

1. **`find_checkin` 定位**：按 `member`（+ 可选 `date` / `period`）只读查出目标记录，拿到它的 `event_id` 与现有字段。多条命中就先问清用户改的是哪条。
2. **`draft_checkin` 出预填编辑卡**：用查到的现有字段**预填**一张新卡（`member` / `distance_raw` / `unit` / `activity_type` / `occurred_at` / `duration_seconds` / `location` 都填上现值），并**带上 `event_id`**（这标记它是"编辑某条已落盘记录"而非新增）。给它一个新的 `card_id`。
3. **用户在卡片上改完点确认** → 你收到确认信号，调 `commit_checkin` 时**带上同一个 `event_id`** → 走**编辑模式**：整体更正那条 checkin（`event_id` 不变、引用不变，一次调用原子完成），**绝不新增一条**。
4. 落库最小字段与新增一致；确认后同样就地冻结成绿色「已确认」快照。

> `event_id` 只在编辑流出现：新增打卡的 `draft_checkin` / `commit_checkin` **不要**带 `event_id`。

### 删除已落盘记录（`delete_checkin`，不出卡）

用户要**删掉**一条已经录入的打卡（如「把 cloe 8/4 那条删了」「我那条 10 公里记错了删掉」）时，走 `find_checkin` → `delete_checkin`，**不出卡、不改动前端任何已完成的卡片，只由你文字回复**：

1. **`find_checkin` 定位**：按 `member`（+ 可选 `date` / `period`）只读查出候选，拿到目标 `event_id`。
2. **判断指令是否清晰**：
   - **指令强硬清晰、且 `find_checkin` 命中唯一一条**（明确指向某人某天某条，如「删掉 cloe 8/4 那条 10 公里」）→ 直接 `delete_checkin`（带该 `event_id`）。
   - **指令模糊 / 命中多条** → 把候选（日期、距离、类型）列给用户，让其指明删哪条，**得到明确答复后再删，绝不擅自删**。
3. **删除后回执**：`delete_checkin` 回执带该成员**当前期次最新累计**（`period_total` / `qualified` / `shortage_km`）——据此自然语言告知「已删除，X 本期还剩 N 公里 / 是否仍达标」。

> `delete_checkin` 只按 `event_id` 删（软删），是删除的**唯一入口**；删除**不需要也不会出卡**，也不 `supersede`/不动前端已确认的绿色快照卡。仍**禁止**绕过 `ledger_api` 直接跑 `assets/tracker.py delete_checkin`。

## 数据完整性（必须遵守）

- **操作前先对齐期次（每次都做）**：执行任何操作（打卡、统计、状态变更、出表等）之前，**先调用 `period_current <当前日期或日期时间>`** 确定当前期次号。该命令会**自动切分周期**——把所有已结束但未封板的历史期次按序补稿封板（空白周也照常封板、累计 `fail`/触发处罚提示），让期次表始终与"当前时间"对齐。拿到当前期次号后再继续后续命令。
- **绝对禁止编造任何数据**：距离、时长、设备、截图日期、地点等字段必须来自截图或用户明确提供，不得猜测或填充。地点认得出就写 `location`，认不出就不传，不写「暂缺」、不把公园名/路线塞进 `note`。**唯一例外**是 `activity_type`：无任何信号时允许默认 `outdoor_run`（见硬约束），但一旦截图/描述有信号就必须直接改成实际类型，绝不反问用户。
- **AI 不算账**：是否有效、距离折算、是否达标、配速、期次归属、处罚计数**全部由 `rules.py` 计算**，AI 不要自己心算判断；写入和统计都走 CLI。
- **回答以存储数据为准**：所有查询、统计、达标、历史记录、状态说明都必须基于 CLI 返回或数据库查询结果；不得凭记忆、印象、群规常识或用户暗示自行回复。若用户挑战或质疑结果，仍以实际存储数据/审计记录为准，先复查再说明；数据与用户说法冲突时，如实说明当前库中记录，并按更正/补录流程处理。
- **回复必须绑定已执行动作**：没有实际执行过查询、统计、录入、删除、校正、定稿等 CLI/数据库动作，就不能回复成“已查询”“已记录”“已删除”“已更正”“已定稿”或给出对应结论。若尚未执行，只能说明需要先执行什么；执行失败则如实说明失败原因，不得把计划、推测或未完成动作包装成结果。
- **命令优先、拿到答案即停**：先用现成命令（`calc` / `report` / `reminder` / `list_*` / `find_member` / `period_current`）；**只有没有对应命令时**才用 `query --sql`。
- **表结构以 `assets/schema.sql` 为准**：需要了解数据库表、字段、索引，或编写 `query --sql` 前，先查看 `assets/schema.sql`；不要凭记忆、旧对话或 `tracker.py` 片段猜表结构。
- **查询不改数据**：`calc` / `query` / `list_*` / `find_member` 是只读，不得触发任何写入命令。
- **打卡落库/修改只经卡片确认**：写/改 checkin 的唯一路径是用户在卡片上确认后的 `commit_checkin`（新增=不带 event_id；修改已落盘=带 event_id 的编辑模式，见「修改已落盘记录」）；不得直接跑 `add_checkin` / `backfill_checkin` / `correct` 等命令改库。**删除**是唯一不经卡片的写操作，走 `ledger_api` 的 `delete_checkin`（见「删除已落盘记录」），同样**不得**绕过 `ledger_api` 直接跑 `assets/tracker.py delete_checkin`。

## 文件说明

| 文件 | 职责 | 可否修改 |
|------|------|----------|
| `assets/tracker.py` | CLI 启动器（播种运行目录后转发给实现体） | **不要修改** |
| `assets/tracker_impl.py` | CLI 实现 + SQLite CRUD + 期次/统计编排 + 周报/提醒成文 | **不要修改** |
| `assets/rules.py` | 纯计算函数（有效性/折算/达标/期次/处罚/单位） | 只读挂载上的**播种模板**；要改请改运行目录那份，见「修改 rules.py 的规范」 |
| `assets/schema.sql` | tracker 建表脚本（member/period/checkin） | 不要修改 |
| `assets/app.yaml` | App Skill manifest（UI 资源 + `ledger_api` 工具 + 可见性） | 不要修改 |
| `assets/persist_paths.py` | 库路径解析 + 运行目录播种规则 | 不要修改 |
| `scripts/_run.py` | Agent 侧 App 包装器（校验 + sentinel 旁路；draft/commit 固定挂 card 资源、透传 card_id） | **不要修改（出卡协议）** |
| `scripts/ledger_api.py` | 打卡业务 handler（仅 draft_checkin/commit_checkin 卡片流） | **不要修改（出卡协议）** |
| `scripts/card_schema.py` | 卡片 `card_data` 渲染契约 | **不要修改（出卡协议）** |
| `scripts/cli_contract.py` | `ledger_api` operation 契约 + 可见性 | **不要修改（出卡协议）** |
| `/data/user_persistent_data/tracker.db` | SQLite 数据库（持久化数据） | 通过 CLI 操作 |
| `/data/user_persistent_data/audit_log.jsonl` | 写入/校正/删除/定稿审计（追加） | 只读 |

## 群背景
- **期次锚点**：第 432 期 = 2026-03-23（周一），每周一期，周一 0:00 ~ 周日 24:00（北京时间）。
- **记录员**：元宝 = 本 Agent，负责识图录入、统计、出周成绩表、催未达标。群主是规则最终裁定者。

## 时间与单位格式

- `occurred_at`：`YYYY-MM-DD`（截图日期）；`--duration` 单位为秒。
- 距离：默认公里；英里设备 `--unit miles`；游泳传米数 `--unit swim_m`。
- 单位识别辅助：iFIT / NordicTrack 默认英里制；Average Speed 9.1~9.4 通常是 km/h；同一成员同一设备单位制不变（查 `description` 或历史 `list_checkins`）。

## 核心业务规则（具体实现在 `rules.py`）

1. **达标线**：周累计**有效**距离 ≥ 6 公里（游泳折算后即 ≥ 1500 米）。
2. **有效性（按类型分流）**：跑步配速 ≤ 10'00" 有效；> 10'00" 无效；< 2'00" 疑似错误判无效待确认。健走默认无效（距离仍留档），仅 `walk_valid` 成员有效。游泳全员可用、不限配速、1km 折算跑步 4km。`age_exempt`（60岁+）任何形式只看距离。
3. **期次归属（极严格）**：按 `occurred_at`（截图日期）归属，不是提交日期；绝不跨期混数。`commit_checkin` 新增时只录当前期，非当前期/已封板期会被拒；修改已落盘记录走卡片编辑流（见「修改已落盘记录」）。
4. **纪律处罚**：未达标发红包（人工）；连续 3 周未达标 → 强制退群；连续 4 周病假 → 退群休养。`period_finalize` 据此打印 `alert`。
5. **单位换算**：英里 km = miles × 1.60934；游泳 km = 米 ÷ 1000 × 4。

## 工作流

### 打卡录入

**打卡录入统一走卡片确认制**（见上方「打卡卡片：总原则」）：识别打卡意图 → `draft_checkin` 出可编辑卡片 → 用户确认 → `commit_checkin` 落库。不论有图无图（口述里程也出卡）。

> **本迭代：新增/修改 checkin 的唯一路径都是卡片确认后的 `commit_checkin`。** `assets/tracker.py add_checkin` / `correct` 是 `commit_checkin` 的内部实现，**你不要直接调用**，也不要直接跑 `backfill_checkin`。**新增打卡**：`draft_checkin` → 确认 → `commit_checkin`。**修改一条已落盘记录**：`find_checkin` 查到 `event_id` → `draft_checkin` 出预填现值且带 `event_id` 的编辑卡 → 用户改完确认 → `commit_checkin`(带 `event_id`) 编辑模式整体更正（见「修改已落盘记录」）。新增/修改都经卡片确认，绝不自行写库。**删除**是例外、不经卡片：走 `ledger_api` 的 `delete_checkin`（见「删除已落盘记录」），仍不得直接跑 `assets/tracker.py delete_checkin`。

**图片 id 全链路**（和旧 skill 底账口径一致，只是多了一层卡片）：

1. **上游**：消息附件行给 `img_id=<32位hex>`（可能带 `_NN` 后缀）；图链（`https://image_N`）只填 **`quote.image_url`** 供前端跳转，**不进信封、不去重**。
2. **出卡**：`draft_checkin` 从**本轮消息**读 `img_id` 传入 JSON（有则必传；`-` 表示无稳定 id）。skill 把它放在 structuredContent **信封层**（与 `card_id` 并列，不进 `card_data`）→ host/客户端写入该卡的 **app.env**。
3. **确认落库**：`commit_checkin` **只认 app.env 快照**里「卡片当前数据如下」的 `图片ID（img_id）` 行——**禁止**从 draft 回包、历史 tool、上一轮对话补 member / 距离 / img_id。快照有就传 JSON，skill 编成 `--raw img=…` 落库；快照无则不写 `img=`（仍可按无图打卡落库）。
4. **录入前查重**：有稳定 `img_id` 时出卡前 `find_by_img`（见步骤 2）；落库时 tracker 仍按 `raw_summary` 里的 `img=` 做同人同日同里程判重（两条 `img=` 不同则放行）。

### 查询某人本周期打卡情况

1. 先确定"本周期"期次号：`period_current <当前日期或日期时间>`。
2. 查成员：`find_member <name|@名>`（传打卡对象的姓名；禁止填 sender_id / user_N）。
3. 看累计与达标：`calc --member <name|@名> --period <N>` —— 输出每条明细（日期/类型/距离/配速）+ 本期 `total_km` / `count` / `qualified` / `shortage_km`。
5. 用 `calc` 的输出组织回执，不要把 SQL/JSON 贴给用户。

### 删除 / 更正打卡记录（本迭代未开放）

改动已落盘的 checkin（删除 `delete_checkin` / 更正 `correct` / 补卡 `backfill_checkin`）**本迭代不提供**。用户如提出删除或改动某条打卡，先用 `list_checkins --member <name|@名> --date <YYYY-MM-DD>` 只读查出来给用户看，并如实说明"改动已落盘记录暂未开放，后续版本再支持"，**不要执行任何写库/删除命令**。

### 登记病假 / 恢复 / 销假

1. 查成员：`find_member <name|@名>`（传对象姓名，禁止填 sender_id）。
2. 登记：`add_status <id> <occurred_at> sick_leave [--reason '<请假说明>']`。`occurred_at` 决定请假生效时间**默认只管当期，下一期自动恢复**；要续假就下期再登记一次。连续病假周数据此**现算**。
3. 恢复期同理：`add_status <id> <occurred_at> recovering`。
4. **销假/提前回归**：`add_status <id> <occurred_at> active`
5. **已封板期不可改状态**（报 `period_finalized`）；确需更正历史请假用 `correct period <num> member_status '<JSON>'`。

### 查询某人状态 / 病假时长

1. `find_member <name|@名|别名> [--asof <YYYY-MM-DD 或 YYYY-MM-DD HH:MM>]` 一条命令即可，输出含 `status`（**有效状态**，按 `--asof` 所属期派生）、`since`（当前连续请假段的起始周一）、`alias`（别名串，；分隔）、`sick`（病假第几周，含当周）、`recover`（恢复期第几周，含当周）、`fail`（连续未达标周数）。这些都由脚本**现算**，无需自己数。**传打卡对象的姓名**：「我的」用 extra 群昵称，「evan的」用 evan；禁止填 sender_id / user_N（每轮会变）。
2. `--asof` 不传=当前期；**可传未来日期查"那一周的状态"**（含已提前登记的假）。
3. 若 `status=sick_leave`，`sick=N` 即**当前所处的病假第 N 周**（含未封板的当周；刚请假当周为 1）；越接近 `SICK_LIMIT`（4）越要在回执里提示管理员。
4. 用这几个字段组织回执，不要把原始 `key=value` 整行贴给用户。

## 打卡录入 App（嵌入群聊 · App Skill）

Agent 侧**唯一入口**：

```bash
python3 scripts/_run.py ledger_api '<json>'   # 一次 operation（只有 draft_checkin / commit_checkin）
python3 scripts/_run.py describe              # 入参 / 可见性 / 示例
```

输出 `phase=checkin_card` 成功，或 `phase=error`。纠正（带 `supersedes`）和确认失败重出这两种情况一次会吐两张卡，stdout 也就不止一个 JSON。只有 `status=pending` 的新卡才挂消息卡片资源 `ui://running_club_checkin_appskill/card`（A2UI 骨架 DSL + 客户端 `RunGroupCheckIn` 组件渲染，无 HTML 产物），`confirmed` / `cancelled` 只回数据不挂资源，无需你指定 `display_mode`。

**`bash` 用法（多卡必看）**

| 场景 | 正确 | 错误 |
|------|------|------|
| 出 1 张卡 | 1 次 `bash`，command 里 1 个 `_run.py` + 1 个 `draft_checkin` | — |
| 出 3 张卡 | **3 次 `bash`**（可同一轮 batch），每次 1 个 `draft_checkin` | **1 次 `bash`，command 里 3 行 `_run.py`** |

```bash
# ✅ 正确：一次 bash，一张卡
python3 scripts/_run.py ledger_api '{"operation":"draft_checkin","card_id":"c_a",...}'

# ❌ 禁止：一次 bash，多行 draft（stdout 易截断，客户端会少卡）
python3 scripts/_run.py ledger_api '{"operation":"draft_checkin","card_id":"c_a",...}'
python3 scripts/_run.py ledger_api '{"operation":"draft_checkin","card_id":"c_b",...}'
python3 scripts/_run.py ledger_api '{"operation":"draft_checkin","card_id":"c_c",...}'
```

出卡成功后，bash 回包会出现 `__ONEAGENT_APP_RESULT__` 行（一行一张卡）。**说「N 张卡出好了」之前，必须数够 N 行**；不够就补调 `bash`，不要先 `send_message`。

### 业务流（卡片确认制）

```
识别打卡意图（图 / 口述 / @记打卡）
   ↓  判断打卡对象是否已建档；未建档先建档，不出卡
draft_checkin（每条记录一次，独立 card_id + quote）  ← 不落库，只出可编辑卡片
   ↓  用户在卡片上核对/补充字段，点「确认」
（下一轮）收到「用户点击了运动打卡卡片【确认】」+ 卡片当前数据
   ↓
commit_checkin（按「卡片当前数据如下」译成 JSON 传参，一条命令原子落 checkin）
   ↓
回执「已录入」（卡片就地变绿「已确认」快照常驻）；用户点「取消」时卡片前端置灰保留、不经过你
```

| operation | 做什么 | Agent |
|-----------|--------|-------|
| `draft_checkin` | 出可编辑打卡草稿卡片（**不落库**）；信息有啥放啥；**一卡一次 `bash`**，多卡多次 `bash`（可 batch），各带独立 `card_id` + `quote` | 允许 |
| `commit_checkin` | 用户确认后落库一条 checkin（内部封装 `add_checkin`，原子）；`member` 须已建档；带 `event_id` 时为编辑模式（整体更正已落盘记录，不新增） | 允许 |
| `find_checkin` | 只读查询已落库打卡（按 member/period/date），供"修改已落盘记录"定位 `event_id` + 现值预填卡片；不写库、不出卡 | 允许 |
| `delete_checkin` | 删除一条已落库 checkin（软删，按 `event_id`）；**不出卡**、不动前端已完成卡片；回执带该成员当期最新累计。清晰唯一命中可直接删，模糊/多条先 `find_checkin` 让用户确认（见「删除已落盘记录」） | 允许 |

> 旧台账 operation（`list_ledger` / `ingest_image` / `attribute` / `set_redeem_rules` / `redeem` / `delete_ledger`）**已下线**，调用会报「不支持的 operation」。别再尝试用它们查台账或记账。

参数要点（draft/commit）：
- `card_id`：一卡一个，串起同一条记录的 draft→commit；不传则脚本兜底生成，但多卡时建议你显式给不同值。
- `user_id`：**必填，这张卡的发起人**——谁触发的这条打卡。上下文里是 `user_1` / `user_2` 这种匿名标识，**每张卡填触发它的那个人**（A 替 B 打卡时填 A 的 `user_N`，`member` 仍是 B）。多人同时打卡就各填各的。**禁止留空、禁止拿对象名字/成员 id/元宝顶替。** 确认/超时确认不用你填。
- `member`：打卡对象的姓名 / @名 / 别名。「我的打卡」= 发送人的群昵称（extra 里的 `sender_name`，如 `用户zhou`）；「evan的打卡」= evan，**不要填发送人**。**禁止填 `sender_id` / `user_N`**。须能解析到已建档成员。未建档 → 先建档。**按语序填**（说明文字管它前面最近的图；一条消息多图 +「我的」= 整组都是发送人）。禁止把一张图匀给另一个人来凑「两个人都有卡」。对象没定就不要出这张卡。
- `distance_raw`：里程数值（别名 `distance_km`），落库须 > 0。`unit` 默认 `km`（英里 `miles` / 游泳米数 `swim_m`）。
- `activity_type` 默认 `outdoor_run / treadmill / indoor_run / swim / walk`（群可在运行目录 `rules.ACTIVITY_TYPES` 扩展）。
- `occurred_at`：`YYYY-MM-DD`（截图日期），默认今天。`duration_seconds`：识到用时就一并给（秒，JSON number）。
- `location`：卡面上的「地点」行，可选。截图或用户口述能认出城市/地标/路线就填成品文本（如 `合肥·天鹅湖`、`人才公园`）；大陆写市，境外先写国家，台湾/香港/澳门加「中国」前缀。图上没写就按最直接的地标推断；跑步机或确无位置线索就不传，**禁止编造、禁止写暂缺**。**不要把地点写进 `note`**——`note` 是给模型和落库看的备注，**不出卡**；地点只有进 `location` 才会显示在卡片上。
- `img_id`（可选）：附件行里的稳定图片 id（`img_id=<32位hex>`）；`img_id=-` 表示无稳定 id。
- `quote`：该卡引用的「那条带图/打卡消息」，形如 `{"seq_id":"12","sender":"张三","text":"[图片]","image_url":"https://image_1"}`（**图链只放这里**）。**优先引用图片那条消息**：`seq_id` 填被引用消息的 seq_id（前端据此点击跳转）、`image_url` 填图、`text` 用 `[图片]` 这类占位而非 `@元宝…` 原句。draft 后随卡固定不变。
- `today`：`commit_checkin` 必带当前日期（漏传脚本按东八区当天兜底）。

### app.env（确认落库的数据来源）

卡片**一出现（draft 渲染）就会写一次 app.env**，之后用户每次编辑字段也经 `ui/update-model-context` 静默把**该卡当前字段**回写 app.env（**后端按 `card_id` 分键各存各的**，多张卡并存互不覆盖）。用户点确认/取消时，页面发 `/app/message` 触发你这一轮，并在触发前最后再刷一次该卡 env。**确认轮里后端只会把「被确认那张卡」的快照注入 system**（按该轮 `card_id` 精确取回），所以你 system 上下文里通常只看到**这一张**待落库卡的字段。因此**你 `commit_checkin` 的字段只认本轮 user 里「卡片当前数据如下」**——bash 读不到原始 app.env JSON，也看不到 draft 回包。**禁止**从 draft 回包、历史 tool、`card_id`、触发语或 `find_member` 补 member / 距离等；某行是 **`（空）`** 就是快照里没有，禁止自行填上。**图片**：开了 `attach_img_id` 的群，确认快照会从 `ui_snapshot` 顶层渲染 `图片ID（img_id）`；有则 `commit_checkin` 必传，无则省略。

| 卡片当前数据如下 | commit 参数 |
|------------------|-------------|
| 对象（member）：翘翘 | `"member":"翘翘"` |
| **任意必填字段：（空）** | **禁止补填；照缺参 commit，由 skill cancel** |
| 距离（distance_raw）：5.02 km | `"distance_raw":5.02,"unit":"km"` |
| 时长（duration_seconds）：0:43:02 | `"duration_seconds":2582` |
| 地点（location）：合肥·天鹅湖 | `"location":"合肥·天鹅湖"` |
| 图片ID（img_id）：40c622… | `"img_id":"40c6222367a53fad8a543496e2f91611"`（快照有则必传） |

> **看到「待确认卡快照」＝有一张卡在等，用户此刻多半是在纠正它**：只要 system 上下文里存在某张**未确认**卡的 env 快照（带 `card_id`），而用户这条消息是在**改它的字段**（用时/距离/日期/对象/地点等，如「他用时00:29:00哈」），这就是**纠正**——**开一张新 `card_id` 的卡**承载纠正后字段，并把那张旧卡的 `card_id` 填进 `supersedes`。skill 会把旧卡 update 成已取消并 create 新卡。**不要复用旧 id、不要漏填 `supersedes`**。只有当用户明显是在给**另一个人/另一条记录**打卡时，才是不带 `supersedes` 的全新卡。**尤其注意：用户可能在卡片上改过距离/用时/日期等，历史轮里 `draft_checkin` 的旧数字一律作废，一切以该卡最新界面快照为准。确认消息是「用户点击了运动打卡卡片【确认】」，字段在紧随其后的「卡片当前数据如下」里——你必须按这份数据落库；收到确认只 `commit_checkin`，不要再 `draft_checkin` 出卡、也不要复述字段。**回执用自然语言，不要贴 JSON/命令。

## CLI 命令

所有命令在工作目录 `/data/skills/running_club_checkin_appskill` 下通过 `python3 assets/tracker.py <command>` 调用，输出为 `key=value` 纯文本。

### 成员管理

消息 extra 里有两套号，**不要混**：`sender_id=user_3` 每轮会变，**只**填 `draft_checkin.user_id`。`find_member` / `member` 传的是**打卡对象的姓名**（库字段 `name`）：「我的打卡」→ `用户zhou`（extra 群昵称），「evan的打卡」→ `evan`。禁止 `find_member user_3`。

```bash
# 添加成员（id、name 必填）。--age-exempt 1 表示 60岁+ 豁免；--walk-valid 1 表示健走有效
# --alias 别名/外号（多值用 ； 或 ，分隔，仅供查找）；建档时只在很确定时才填，见下方提示
python3 assets/tracker.py add_member <id> <name> [--at-name <@名>] [--alias '小祥；祥子'] [--sort <n>] \
    [--status active] [--age-exempt 0|1] [--walk-valid 0|1] [--description '<文本>']

# 更新成员（只改提供的字段；可改 status 用于退群 exited / 外卡 wildcard 等管理态）
# --alias 是【整体覆盖】别名（传空串清空）；只想补充别名请用下面的 add_alias
python3 assets/tracker.py update_member <name|@名> [--name ...] [--at-name ...] [--alias ...] \
    [--sort n] [--status ...] [--age-exempt 0|1] [--walk-valid 0|1] [--description ...]

# 给已注册成员【追加】别名（去重，不覆盖已有；多值用 ； 或 ，分隔）
python3 assets/tracker.py add_alias <name|@名> '<别名>'

python3 assets/tracker.py find_member <name|@名|别名> [--asof <YYYY-MM-DD 或 YYYY-MM-DD HH:MM>]
python3 assets/tracker.py list_members [--asof <YYYY-MM-DD 或 YYYY-MM-DD HH:MM>]
```

> **`name` / `at_name` / `alias` 三者职责不同**：
> - `name`：正式名（精确匹配）。
> - `at_name`：群里 @ 人的句柄（**单值、精确**，`reminder` 直接拿它拼 `@xxx` 发群）。**不要废弃**——别名不能替代它的 @ 功能。
> - `alias`：别名/外号（**多值、`LIKE` 模糊匹配**），只用于查找，不参与 @人。
>
> **查找匹配规则**：`find_member` 按库字段 `name` / `at_name` / `alias` 查，入参是**打卡对象的姓名**。发送人可能替别人打卡，不能一律传 extra 的 `sender_name`。「我的」才用群昵称，「evan的」用 evan。**不要传 `sender_id` / `user_N`**（每轮会变，只用来填 `draft_checkin.user_id`）。别名模糊匹配可能命中多人（取 `sort_order` 最小者），**拿到结果务必核对 `name` 是不是想找的人**。

> **⚠️ 写别名前必须确认（重要）**：只有当你**非常确定**某个称呼确实是该成员的别名时，才写进 `alias`（`add_member --alias` / `add_alias` / `update_member --alias`）。**只要有一点不确定，先在群里/向用户问清楚「这是不是某某的别名」，得到明确确认后再补充**。绝不要凭猜测往别名字段里塞，错误的别名会让以后查错人。

### 打卡录入 / 查询

**打卡录入/修改都走卡片流**（新增：`draft_checkin` → 确认 → `commit_checkin`；修改已落盘：`find_checkin` → `draft_checkin`(预填+event_id) → 确认 → `commit_checkin`(event_id)）。**删除**不走卡片：`find_checkin` 定位 → `ledger_api` `delete_checkin`（清晰唯一即删，模糊/多条先让用户确认）。`add_checkin` / `correct` 只作为 `commit_checkin` 的内部实现，`backfill_checkin` 及直接跑 `assets/tracker.py delete_checkin` **不给你调用**（删除只经 `ledger_api` `delete_checkin`）。只读查询：

```bash
# 按图片 id 查已有打卡（出卡前查重用；可裸 id / img=<id> / 整条 url，多张一次传完）
python3 assets/tracker.py find_by_img <id1> [<id2> ...]

# 列打卡记录（可按成员/期次/日期过滤），用于回答「这周跑了多少」这类无新图查询
python3 assets/tracker.py list_checkins [--member <m>] [--period <n>] [--date <YYYY-MM-DD>]
```

落库时的字段口径（供你在 `draft_checkin` 组织卡片时对齐）：`occurred_at` 用**截图日期**（决定期次归属）；`activity_type` 须在运行目录 `rules.ACTIVITY_TYPES` 内（默认五种，群可自增）；游泳传原始米数 + `unit=swim_m`，英里制设备传原始英里 + `unit=miles`。有代跑折算的类型（如游泳），卡面会自动出「折算跑步」行。地点有线索就填 `location`，没有就不传。

**重复打卡判定**：同一人 + 同一天 + 同里程（折算后 `distance_km`）视为重复（`error=duplicate_checkin`，幂等视为已录入）；**同日同里程但两条 `img=` 不同则放行**。任一条没带图片 id 仍按重复拒绝。落库后若出现 `warn=same_image_in_period`，是提示不是错误（周汇总图多条明细属正常）。

`commit_checkin` 落库时自动拦截：**未来日期 / 非当前期**（`error=checkin_date_rejected`）、**已封板期**（`error=period_finalized`）、**重复打卡**（见上）。命中即如实反馈，不要绕开卡片补写。

### 状态变更

```bash
# 直接更新 member.status（单一真相源）并落审计；occurred_at 仅写进审计备注
python3 assets/tracker.py add_status <member> <occurred_at> <active|sick_leave|recovering|suspended> [--reason ...]
```

退群（`exited`）/ 外卡（`wildcard`）这类管理态直接 `update_member --status` 或 `correct member`。

### 期次管理

```bash
python3 assets/tracker.py period_current <当前日期或日期时间>   # 返回该时间所属期次（自动建期）；并自动切分周期：把之前未封板的期次按序补稿封板（打印 auto_finalized=...）。日期/时间由你从上下文传入
python3 assets/tracker.py period_finalize --num <N> [--champion <member>]
```

`period_current` 是**每次操作的第一步**：除返回当前期次外，会把"今天"之前所有未封板期次按序自动定稿（与 `add_checkin` 同口径，含空白周），输出形如 `auto_finalized=period=<N> ...` 及可能的 `alert=...`。因此它**会写数据**（定稿、累计 `sun`/`fail`、触发处罚提示），不属于只读命令。

`period_finalize`：标记定稿 + 冠军 `sun_count +1`，并按现算的连续计数打印处罚提示（`alert=...`）。
**幂等**：对已定稿的期次重复执行直接 `skipped=already_finalized`、不重复累加 `sun_count`（定时任务重跑安全）。务必按期次顺序定稿。

### 统计与输出

```bash
# 单人本期累计 + 达标（也支持 --from/--to 日期范围）
python3 assets/tracker.py calc --member <m> --period <N>

# 全期排行
python3 assets/tracker.py calc --period <N>

# 周成绩表（确定性成文，可 --out 存档）
# 🚀 保持者由脚本从 period 表自动取（历史最大周冠军距离），--rocket 已不再读取；
# 大满贯次数固定 🏃x33，--grandslam 仅为兼容旧调用保留。
python3 assets/tracker.py report --num <N> [--out /data/user_persistent_data/第N期.md]

# 周期截止前未达标提醒
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

打卡回执由 AI 用 `add_checkin` 的输出自己组织（日常用亲近称呼如"某某大哥"；周成绩表用全名+尊称，见各成员 `description`）。

## 修改 rules.py 的规范

### 改哪个文件

改**运行目录**那份，挂载上那份是只读的、改不动：

```
/data/user_persistent_data/running_club_checkin_appskill/assets/rules.py
```

首次跑任意业务命令时它会自动从挂载播种，之后技能包再发新版也不会覆盖它——所以管理员定过的阈值一直有效。同理，这份文件里的改动**不会**随技能包升级拿到包内的新规则，需要时手工同步。

**改 `rules.py` 必须用 `bash`，禁止用 `text_edit`。** `text_edit` 只能改群记忆文档（`soul.md` / `memory.md` / `learnings.md`）；传 sandbox 绝对路径（如上面的 run-dir `rules.py`）会报 `invalid path`。用 `bash` 里的 `python3 -c` 或 heredoc 做读写/`str.replace` 即可。

### 原则

1. **只改函数内部逻辑/数值或顶部常量**，不改函数签名（参数名、返回类型）。
2. **保持纯函数**：不读数据库、不做 I/O、不 import sqlite3。
3. **每个分支都有兜底 return**，保留类型标注。
4. **不要删除已有函数**：`scripts/` 下的出卡代码永远是包内最新版，会调用 `rules` 里的函数（如 `to_km`）。删掉会让出卡链路报 `AttributeError`。
5. 改完后跑 `python3 assets/tracker.py recompute` 回填历史数据的派生列。

### 可修改的函数 / 常量

| 名称 | 作用 |
|------|------|
| `ACTIVITY_TYPES` / `UNITS` / `ACTIVITY_LABELS` | 允许的运动类型、单位、卡面中文名（群自增类型在此登记） |
| `QUALIFY_KM` / `MILES_TO_KM` / `SWIM_FACTOR` / `PACE_*` / `PERIOD_*` / `BACKFILL_MAX_LAG` / `FAIL_LIMIT` / `SICK_LIMIT` | 各项阈值/系数/锚点/补录窗口常量 |
| `effective_km(activity_type, distance_raw, unit)` | 距离折算（英里、游泳代跑、群自定义类型） |
| `equivalent_factor(activity_type, distance_raw, unit)` | 代跑系数（出卡「折算跑步」行用，一般不用手改） |
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

**"新增骑行，5 公里折 1 公里跑步"**（`ACTIVITY_TYPES` + `ACTIVITY_LABELS` + `effective_km` + `judge_validity` 四处一起改）：

```python
ACTIVITY_TYPES = ("outdoor_run", "treadmill", "indoor_run", "swim", "walk", "cycle")
ACTIVITY_LABELS = {**ACTIVITY_LABELS, "cycle": "骑行"}

# effective_km 里、return km 之前：
if activity_type == "cycle":
    return km / 5.0

# judge_validity 里、健走分支之前：
if activity_type == "cycle":
    return (distance_km > 0, "")
```

改完后 `recompute` 回填；出卡会自动带「折算跑步」行（系数由 `effective_km` 推导，无需改 `scripts/`）。

## 边界情况

遇到 `rules.py` 未覆盖的场景：**先在群里问管理员，得到决定后再写入**（用 `--override-valid` 或 `correct`），事后把新规则加进 `rules.py` 对应函数。不要猜——猜错会让 valid/距离进入错误状态，影响后续所有统计。