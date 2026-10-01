---
name: bookkeeping_checkin_appskill
description: 用于群聊记账，在群聊内嵌「记账录入」卡片 App。当用户消息涉及记账（口述消费/收入、发支付截图、@元宝要求记一笔账）、账目查询与统计等场景时，必须调用此 Skill：识别到记账意图即出可编辑卡片（draft_txn），用户在卡片上点确认后才落库（commit_txn）。
keywords:
  - 记账
  - 记一笔
  - 消费
  - 支出
  - 收入
  - 账单
  - 记账卡片
packageType: app-skill
instructionOnly: false
metadata:
  version: v1.0
---

## 初始化

**代码不持久化**：全部脚本只在只读挂载点 `/data/skills/bookkeeping_checkin_appskill/` 原地跑。**禁止**复制到 `/data/user_persistent_data/`，**禁止**改任何 `.py`（包括 `vocab.py`）。脚本不往自己所在目录写任何东西。唯一落盘是账目库，由 `TRACKER_DATA_DIR` 指到 `/data/user_persistent_data`。

**库文件**：`/data/user_persistent_data/bookkeeping.db`。**不是 `tracker.db`**——那个是跑团打卡技能的库，两个技能共享同一个持久化目录，别写串。沙箱里漏掉 `export` 也会落到这个正库，**禁止**在 skill 目录下再建旁路库。

### 硬禁令（违反会拖慢整轮，必须遵守）

- **禁止** `find /`、`find /data`、全盘搜 `tracker.py` / `bookkeeping*`；**禁止**用 `ls` 做排障巡检（不要 `ls /data`、`ls /data/skills`）。
- **禁止**用 `cp` / `mkdir` 把 skill 复制到 `/data/user_persistent_data/` 或别处再跑。那个目录跨会话持久，复制出来的副本会一直残留，技能包更新后你执行到的仍是旧代码。**一律在 `/data/skills/` 下原地跑。**
- **禁止**编辑 skill 目录下任何文件（词表、协议、schema 一律只读）。词表未覆盖用 `other`，不要改 `vocab.py`。
- **禁止**在任一业务命令已成功后，再执行 `mkdir` / `cp` / `ls` / `find`。
- **禁止**把路径写成字面量 `{slug}`；本 skill 目录名固定为 `bookkeeping_checkin_appskill`。
- 初始化预算（整轮上限）：业务尝试 →（失败则）**`load_skill` 一次 + 业务一次**。用尽仍失败再告知用户，**停止排障**。

### 流程

**第 1 步：进 skill 目录直接跑业务（不要预先 mkdir/cp，不要先 ls/find）。**

```bash
cd /data/skills/bookkeeping_checkin_appskill
export TRACKER_DATA_DIR=/data/user_persistent_data
python3 assets/tracker.py list_members
```

- ✅ **任一业务命令成功** → 初始化完成，**立刻做业务**；禁止再初始化/探测。
- ❌ `cd: No such file or directory`（挂载点还没就绪）→ **不要说未就绪、不要 ls**：再调用一次 `load_skill`（name=`bookkeeping_checkin_appskill`），然后**立刻重跑第 1 步**。
- ❌ **其他错误**（python 报错、参数错）→ 按报错信息改命令重试，不是去 `ls` / `find`。
- 第二次仍失败 → 才回复「记账技能文件未挂到沙箱，请稍后重试」；**禁止**继续探测。

> 数据库无需手动建——首次命令会按 `assets/schema.sql` 建表。
> `load_skill` 只把说明注入上下文不够，必须让 `/data/skills/bookkeeping_checkin_appskill/` 在沙箱里真实存在才能跑脚本。

## 记账卡片：总原则（先读这段再动手）

**识别记账语义 → 出「可编辑记账卡片」→ 用户在卡片上点确认才落库。**

- **落库的唯一入口是「卡片确认后的 `commit_txn`」。** 任何一笔账都必须先出卡、等用户在卡片上点确认，你才在下一轮 `commit_txn` 落库。**没有卡片确认这一步，就绝不能把账写进库**——包括但不限于直接跑 `assets/tracker.py add_txn` / `correct` / `delete_txn` 等写库命令。哪怕这一轮因为某种原因没成功出卡，也只能如实说明、引导用户重发，**不允许"顺手先记上"**，更不允许在没落库时说"已经记好了"。

- **⚠️ 卡片只能由 `draft_txn`「调用工具」生成，不能靠文字描述。** 只要识别到记账意图并拿到**任意**字段（哪怕只有一个金额），就**必须真正调用一次 `draft_txn`** 把卡片发出来。**严禁只在回复正文里罗列「金额/分类/账户…」并说「核对无误后点确认即可」，却没有实际调用 `draft_txn`**——前端的卡片来自 `draft_txn` 产生的 app 资源事件，你不调工具，用户界面上就**根本不会出现任何卡片**，也就无从点确认，记账直接断链。记住：**出卡 = 调用 `draft_txn` 工具，不是把字段用文字念出来**。成功调用之后，正文只需一句「已生成记账卡片，请在卡片上核对并确认」，**不要再把字段复述一遍**。

**核心原则**：

- **只要识别到记账意图**（「刚在麦当劳花了38块5」「发了工资8000」「@元宝 记一笔打车25」、发支付截图等），就出一张**可编辑记账草稿卡片**（`draft_txn`）。**信息有啥放啥，允许不全**——缺的字段用户可以在卡片上补。
- **区分「记账」与「查询」**：像「我这个月花了多少」「上周的账」这类**查询**，用 `find_txn` 取数后**用文字回答**即可，不出卡、更不写库；而「花了/收了多少钱」这类**录入**意图，才走 `draft_txn` 出卡。拿不准时，宁可当查询用文字答，也不要擅自记账。
- **一卡 = 一笔待落库流水**。多笔账（如「今天打车25、午饭38、晚上电影60」）就**分别调多次 `draft_txn`**，每次一个**独立 `card_id`**，各出一张卡。
- **draft 不落库**——它只出卡，绝不写流水。**只有用户在卡片上点「确认」**，你才会在下一轮收到确认信号并 `commit_txn` 落库。
- **建档前置（与跑团同一条）**：归属人必须是**已建档成员**（见下方「成员管理」）。**未建档 → 先提示建档，不出卡**；`draft_txn` / `commit_txn` 都会报 `MEMBER_NOT_FOUND`。**绝不为了记一笔账就自动建档**：建档意味着这人是群成员，得由用户明确表态。建档完成后再 `draft_txn`。

### 必填字段与缺失兜底（重要）

**必填三项**：`owner`（归属人）、`transaction_type`（收入/支出）、`amount`（金额）。

缺失时这样处理，**不要为了凑齐字段反复追问**：

| 字段 | 缺失时怎么办 |
|------|--------------|
| `user_id` 发起人 | **必填 `user_N`**——本轮触发这张卡的那个人（看消息 extra）。不要问用户，从上下文取。漏了不出卡 |
| `owner` 归属人 | **记谁名下填谁的姓名**。「我的」= extra 的群昵称；「给 evan 记」= evan。**禁止填 sender_id / user_N**。**须已建档**；未建档先提示建档，**不出卡** |
| `occurred_at` 日期 | **默认当天**，不要问 |
| `transaction_type` 类型 | **提示用户选**（但仍要先出卡，让他在卡片上选） |
| `amount` 金额 | **提示用户补**（但仍要先出卡，让他在卡片上填） |
| `category` 分类 | 判断不出来就**留空**，服务端兜底成「其他」，不要问 |
| `account` 账户 | 判断不出来就**留空**，服务端兜底成「其他」，不要问 |
| `currency` 货币单位 | **默认人民币**，不要问。用户说了哪种就填哪种（中文名优先），表外币种也原样填，**不要说不识别** |
| `merchant` 商户 | 可为空，不要问 |
| `note` 备注 | 可为空，不要问 |

> 只有**类型**和**金额**这两项值得开口问，而且要**先出卡再问**——让用户直接在卡片上补，比来回打字快。其余字段一律走默认/兜底，问了反而啰嗦。

### 每轮决策（按序判）

1. **是不是记账意图？** 口述消费/收入、支付截图、@元宝要求记账 → 是。闲聊、问价格、讨论要不要买 → 不是，普通回复即可。
2. **归属人建档了吗？** 未建档 → 先提示建档，**不出卡**、**不要**自己 `add_member`；已建档 → 继续。
3. **拆几笔 → 每笔都必须实际调用 `draft_txn`（不是文字描述）**：N 笔账 = N 次 `draft_txn`，每次独立 `card_id`。有啥字段填啥。
4. **等用户确认**：出卡后停手，文字只说一句「已生成记账卡片，请在卡片上核对并点确认」，**不要复述字段、不要自己 `commit_txn`**。
5. **收到确认信号**（下一轮上下文中会出现「用户点击了记账打卡卡片【确认】」，下面跟着「卡片当前数据如下」列出这张卡的字段）→ 按这些字段调 `commit_txn` 落库，回执一句「已记账」即可。确认成功后前端会把这张卡就地冻结成「已确认」快照常驻消息流。**取消由前端直接把卡片置灰保留**。
   - **⚠️ 确认轮＝只办本轮这一张卡，其它一律不碰。** 后端在确认轮**只会把「被确认那张卡」的 env 快照**注入 system。**严禁在确认轮里为「历史里其它还没确认的草稿卡」再 `draft_txn` / 再出卡 / 再提醒**。记住：**一轮确认 = 落一笔账 + 一句回执，不多做任何 draft。**
   - **⚠️ 确认只有两条互斥链路，不要拼在一起。**
     - **成功**：只 `update` 用户点的那张卡为已确认，**不出新卡**。这时才能回「已记账」。
     - **失败**：skill **已经**把旧卡 `update` 成取消，并 `create` 一张待确认新卡（`reissued=true`）。你只告诉用户失败原因，请他们在**新卡**上再点确认。**本轮禁止**对 `new_card_id` 再 `commit_txn`，**禁止**说已记账，**不要**再 `draft_txn` / `add_txn`。
   - `send_message` **必须引用这张卡片所在消息**（`ref_seq_id` 填本条确认消息的 seq_id）。这是确认回执，即使发送者是元宝也要引用。
   - 有 `owner_id`（卡片 `ownerName.raw.memberId`）就可以 commit，不必再勉强造一个 `owner` 字符串。
   - **⚠️ 无条件先调 `commit_txn`。** 不要先 `find_member` / `list_members` 去预判归属人建档没建档、能不能落库，也不要自己判定失败就只回文字。未建档等失败原因 skill 会接住并把旧卡 `update` 成已取消、另出一张待确认新卡；你不调，那张卡就永远停在「待确认」。
6. **收到超时自动确认**（「记账打卡卡片超时未操作，系统自动确认」）→ 按这些字段调 `commit_txn`，**必须带 `auto=true`**。这一轮**只有 update，没有 create**：
   - **成功**：只 `update` 这张卡为已确认，回「已记账」。
   - **失败**：skill **已经**只把这张卡 `update` 成已取消，**不会出新卡**。你只告诉用户超时未落库、卡片已取消。**不要**再 `draft_txn`，**不要**对这张卡再 commit，**不要**说已记账。
   - `send_message` **必须引用这张卡片所在消息**（`ref_seq_id` 填本条超时确认消息的 seq_id）。
   - **⚠️ 无条件先调 `commit_txn`，落不落得进库由 skill 判。** 严禁先 `find_member` / `list_members` 去预判「这人建档了吗、能不能落库」，更严禁自己判定失败就只回一句文字。哪怕归属人明显没建档，也要照调——未建档、金额缺失这些失败原因 skill 都会接住，并**把这张卡 `update` 成已取消下发给客户端**，再把原因回给你转述。你不调，客户端那张卡就一直停在「待确认」，用户看到的是一张永远转圈的卡（这是真实发生过的线上故障：模型查到 `member_not_found` 就直接回「卡片已超时自动取消」，可卡片根本没被取消）。

### 硬约束（少而硬）

- **draft 必须带 `user_id`**：填本轮触发这张卡的那个人的 `user_N`（看消息 extra：`user_1` / `user_2`）。A 帮 B 记账填 A。漏填会报缺参、不出卡。禁止留空，禁止拿归属人名/成员 id/元宝顶替。确认/超时确认不用填。
- **draft 绝不落库；落库只经卡片确认后的 `commit_txn`**：不得跳过卡片直接 `commit_txn`，更不得绕到 `assets/tracker.py add_txn` / `correct` / `delete_txn` 等任何写流水的命令——**这些命令是 `ledger_api` 的内部实现，本迭代不给你用**（它们留在 CLI 里是给人工排查与补录的）。唯一落库路径：用户在卡片上点了确认、下一轮拿到该卡快照后调 `commit_txn`。
- **对用户禁止贴命令**：群聊回复里不要出现 `python3`、`assets/tracker.py`、`add_member`、`ledger_api` 或任何 CLI。让用户建档就说「先把 XX 建成群成员」，等用户明确说建档你再自己调命令，不要把命令教给用户。
- **建档前置，且绝不自动建档**：未建档**不出卡、不落库**。`draft_txn` / `commit_txn` 遇到未建档归属人都报 `MEMBER_NOT_FOUND`。此时**用人话告知用户去建档**，不要自己 `add_member` 把人塞进去——建档是"承认这人是群成员"，只能由用户明确要求。
- **建档前置只管出卡这一步，不能拿来跳过 `commit_txn`**：已经有卡在等确认时，确认 / 超时确认收到就必须调 `commit_txn`，未建档会报 `MEMBER_NOT_FOUND`，skill 据此把卡打成终态（超时→已取消；用户点确认→旧卡取消 + 新卡待确认）。**卡片的终态只能由 skill 下发，你用文字宣布不算。**
- **一卡一 `card_id`；纠正＝`supersedes` → 旧卡 update 已取消 + 新卡 create**：**首次 draft 就要显式传一个你自己生成、能记住的 `card_id`**（如 `c_bk_<两三位随机>`），不要依赖脚本兜底生成。**用户要求纠正某张【还没确认】的卡**（如「说错了，是48块」）时：**另开一张【新 `card_id`】的卡**承载纠正后的全部字段，并把**被纠正那张卡的旧 `card_id` 填进 `supersedes`**。skill 会同轮把旧卡 `update` 成已取消、再 `create` 新卡。**不要复用旧 `card_id`、不要漏填 `supersedes`，也不要自己再调一次 `cancel_txn`**。
- **取消时把卡面字段一起传回来**：`cancel_txn` 只有 `card_id` 是必填，但取消后那张卡仍要置灰常驻在消息流里——不传其余字段，卡面会变成一片空行。请把该卡当前显示的字段原样带上。
- **落库最小字段**：`owner` 或 `owner_id` 二选一 / `occurred_at` / `transaction_type` / `amount`(>0) 才能 `commit_txn`。
- **金额只传数字**：`amount` 传 JSON number（`38.5`，不是 `"¥38.5"`）。脚本会兜底剥掉 `¥`/`元` 这类字符，但别依赖它。
- **绝不编造金额**：金额、商户、日期必须来自用户明说或截图，不得猜测填充。分类和账户判断不出来就留空让服务端兜底，**不要瞎猜一个**。
- **一次落库 = 一条 operation**：`commit_txn` 内部原子落库，禁止你自己拼多步。
- **`commit_txn` 幂等**：同一张卡重复确认视为已录入，不会记成两笔（回执里 `duplicate=true`）。
- `phase=error` 且 `reissued=true`：用户点确认失败，旧卡已取消、新卡已出。如实说失败原因并等用户再点确认。禁止本轮再 commit、禁止说已记账。
- `phase=error` 且超时（`auto=true` / `reissued=false`）：只取消了旧卡，**没有新卡**。如实说超时未落库，禁止再 draft / 再 commit。

### 成员管理（建档 / 改名 / 别名）

归属人是群成员，不是自由文本。成员档案走 `assets/tracker.py` 的这几个子命令（**成员管理是 `tracker.py` 里唯一对你开放的写操作——写流水的那几个命令不给你用**）：

消息 extra 里 `sender_id` / `sender_name` 是两套号，**不要混**：

- `sender_id`（`user_3`）每轮会变，**只**填 `draft_txn.user_id`。
- `find_member` / `owner` / `add_member` 传的是**记账对象的姓名**（库字段 `name`），不是 `sender_id`。
- 「我的账」→ 对象=发送人，传入 extra 的群昵称（`用户zhou`）。「给 evan 记」→ 对象=evan，**不要**因为发送人是用户zhou就把 evan 的账查成用户zhou。
- **禁止** `find_member user_3`。

```bash
python3 assets/tracker.py list_members                     # 看有哪些人（先跑这个）
python3 assets/tracker.py find_member '<姓名|@名|别名>'  # 查某人是否已建档
python3 assets/tracker.py add_member <姓名> [--at-name <@名>] [--alias '小翘；翘子'] [--sort <序号>]
python3 assets/tracker.py add_alias  '<姓名>' '<别名>'      # 追加别名（不覆盖已有）
python3 assets/tracker.py update_member '<姓名>' --name <新名> [--status active|exited]
```

- **`id` 由脚本自增分配**（`1` / `2` / `3`…），**不要自己填、不要传拼音、不要传 `user_N`**。建档只传群昵称（如 `用户zhou`）。`id` 建档后不可改——它是流水的外键。姓名改了 `id` 不动，历史流水的展示名会自动跟着变（库里只存 `member_id`，姓名 JOIN 实时取，**不需要回填**）。
- **查人 / 建档传对象姓名，不要传 `sender_id`**：`user_1` / `user_2` 每轮重编。替别人记就查对方的名字，不要默认用发送人昵称。
- **`--alias` 是整体覆盖，`add_alias` 才是追加。** 想加一个别名别用 `update_member --alias`，会把原有别名冲掉。
- **匹配顺序**：姓名/`at_name`（精确）→ 别名（模糊）。**不按档案 id 查**，也不要用消息 extra 里的 `user_N`。别名模糊匹配可能命中多人（取 `sort_order` 最小者），拿到结果**要核对 `name` 是不是想找的那个人**，不对就让用户说清楚。
- 记账时**优先传 `owner`（群昵称）**。只有客户端卡片回传了 `ownerName.raw.memberId` 才填 `owner_id`（那是档案数字 id，**不是** `user_N`）。解析到就把 `ownerName` 显示成**档案里的正式姓名**（用户说「小翘」，卡面显示「翘翘」）。
- **成员离群**：`update_member <姓名> --status exited`，**不要删档**——删了历史流水的归属人就断了。`exited` 的人不在 `list_members` 默认列表里，但历史账目照常可查。

### 枚举取值（传机器码，不传中文）

- `transaction_type`：`income`（收入）/ `expense`（支出）。一期没有转账。
- `category`（**依赖类型**，传对应组里的 id）：
  - `income`：`salary` 工资 / `bonus` 奖金 / `investment_income` 理财收益 / `part_time` 兼职 / `red_packet` 红包 / `other` 其他
  - `expense`：`dining` 餐饮 / `transportation` 交通 / `shopping` 购物 / `entertainment` 娱乐 / `education` 教育 / `medical` 医疗 / `housing` 住房 / `travel` 旅游 / `investment` 投资 / `other` 其他
- `account`：`wechat` 微信支付 / `alipay` 支付宝 / `bank_card` 银行卡 / `cash` 现金 / `credit_card` 信用卡 / `other` 其他
- `currency`（**传中文名称**，默认人民币；卡面可自填）：常用 `人民币` / `美元` / `欧元` / `日元` / `英镑` / `港元` / `澳元` / `加元` / `瑞士法郎` / `新加坡元`。传 `CNY`/`USD` 等会归一成中文。用户说了表外币种（如韩元、泰铢）**原样填进去**，**禁止**回复「不识别 / 不支持 XX 货币」。

> 类型/分类/账户优先传机器码更准（脚本会归一「餐饮」→`dining`、「微信」→`wechat`）。分类认不出所属类型时会退回 `other`，不会硬塞。货币单位直接传中文名，表外的原样传。

### 修改已落盘记录（编辑流）

用户要改一笔**已经记过**的账（如「上午那笔麦当劳是42不是38」）时，**不要**直接改库，走卡片编辑流：

1. **`find_txn` 定位**：按 `owner`（+ 可选 `date` / `month`）只读查出目标记录，拿到它的 `txn_id` 与现有字段。多条命中就先问清用户改的是哪笔。
2. **`draft_txn` 出预填编辑卡**：用查到的现有字段**预填**一张新卡（各字段都填上现值），并**带上 `txn_id`**（这标记它是"编辑某条已落盘记录"而非新增）。给它一个新的 `card_id`。
3. **用户在卡片上改完点确认** → 调 `commit_txn` 时**带上同一个 `txn_id`** → 走**编辑模式**：整体更正那条流水（`txn_id` 不变，一次调用原子完成），**绝不新增一笔**。

> `txn_id` 只在编辑流出现：新增记账的 `draft_txn` / `commit_txn` **不要**带 `txn_id`。

### 删除已落盘记录（`delete_txn`，不出卡）

1. **`find_txn` 定位**：拿到目标 `txn_id`。
2. **判断指令是否清晰**：
   - **指令强硬清晰、且命中唯一一条**（如「删掉我 8/9 那笔麦当劳」）→ 直接 `delete_txn`。
   - **指令模糊 / 命中多条** → 把候选（日期、金额、商户）列给用户，让其指明删哪笔，**得到明确答复后再删，绝不擅自删**。
3. **删除后回执**：`delete_txn` 回执带该归属人**当月最新收支合计**，据此自然语言告知「已删除，你这个月还剩支出 ¥N」。

> `ledger_api` 的 `delete_txn` 只按 `txn_id` 软删，是删除的**唯一入口**；不出卡、不动前端已确认的快照卡。仍**禁止**绕过 `ledger_api` 直接跑 `assets/tracker.py delete_txn`——那条是人工排查用的同名命令，走它你拿不到当月合计回执，也不在 App 的回包链路里。

## 记账录入 App（嵌入群聊 · App Skill）

Agent 侧**唯一入口**：

```bash
python3 scripts/_run.py ledger_api '<json>'   # 一次 operation
python3 scripts/_run.py describe              # 入参 / 枚举 / 可见性 / 示例
```

输出 `phase=bookkeeping_card`（出卡/状态变更）、`bookkeeping_list`（查询）、`bookkeeping_deleted`（删除）或 `phase=error`。纠正（带 `supersedes`）和确认失败重出这两种情况一次会吐两张卡，stdout 也就不止一个 JSON。只有 `status=pending` 的新卡才挂消息卡片资源，`confirmed` / `cancelled` 只回数据不挂资源，无需你指定。

### 业务流（卡片确认制）

```
识别记账意图（口述 / 截图 / @记一笔）
   ↓
draft_txn（每笔一次，独立 card_id）  ← 不落库，只出可编辑卡片
   ↓  用户在卡片上核对/补充字段，点「确认」
（下一轮）收到确认信号 + system 里该卡 env 快照
   ↓
commit_txn（读该卡 env 字段，一条命令原子落一笔流水）
   ↓
回执「已记账」（卡片就地冻结成「已确认」快照常驻）；用户点「取消」时卡片前端置灰保留
```

| operation | 做什么 | Agent |
|-----------|--------|-------|
| `draft_txn` | 出可编辑记账草稿卡片（**不落库**）；信息有啥放啥；多笔多调、各带独立 `card_id` | 允许 |
| `commit_txn` | 用户确认后落库一笔流水；带 `txn_id` 时为编辑模式（整体更正已落盘记录，不新增） | 允许 |
| `cancel_txn` | 用户点取消：把卡片打成 cancelled 终态，不落库 | 允许 |
| `find_txn` | 只读查询已落库流水（按 owner/date/month/type），供定位 `txn_id` 或回答统计问题；回包带 `summary`；查的人没建档时回 `member_not_found=true`（**这跟「有档但没记录」说法要区分**）；不写库、不出卡 | 允许 |
| `delete_txn` | 删除一笔已落库流水（软删，按 `txn_id`）；**不出卡**；回执带当月最新合计 | 允许 |

参数要点：

- `card_id`：一卡一个，串起同一笔账的 draft→commit；首次 draft 就显式给。
- `user_id`：**必填，这张卡的发起人**——谁触发的这笔记账。上下文里是 `user_1` / `user_2` 这种匿名标识，**每张卡填触发它的那个人**（A 帮 B 记时填 A 的 `user_N`，`owner` 仍是 B）。多人同时记账就各填各的。**禁止留空、禁止拿归属人名字/成员 id/元宝顶替。** 确认/超时确认不用你填。
- `owner` / `owner_id`：归属人（**须已建档**）。文本用 `owner`，填**对象姓名**：「我的」用 extra 群昵称，替别人记用对方名字。只有客户端卡片回传了 `ownerName.raw.memberId` 才填 `owner_id`。**禁止**把 `sender_id` / `user_N` 填进 `owner` / `owner_id` / `find_member`。
- `amount`：金额，JSON number，落库须 > 0。卡面上金额和货币单位是两行：`amount` 与 `currencyUnit`（对应入参 `currency`，默认 `人民币`）。
- `transaction_type` / `category` / `account` / `currency`：见上方枚举。
- `occurred_at`：`YYYY-MM-DD`，默认今天。
- `merchant` / `note`：商户与备注，可为空。
- `image_url` / `quote`：支付截图与被引用消息，透传用，不上卡面。
- `today`：`commit_txn` 必带当前日期（漏传脚本按东八区当天兜底）。
- `update_seq_id`：卡片挂在历史消息上时，`commit_txn` / `cancel_txn` 必带（客户端经 app.env 上报的那条消息 seq_id）。

### 上下文里的卡片（确认链路 = 历史卡，同一套结构）

卡片**一出现（draft 渲染）就会写一次 app.env**，之后用户每次编辑字段也会静默把**该卡当前字段**回写 app.env（**后端按 `card_id` 分键各存各的**，多张卡并存互不覆盖）。

送给模型时，**历史消息里挂着的卡**和**本轮点确认的卡**用同一套结构，都在该条消息的 `ext.card_env.ui_snapshot` 里，不要另造一份「卡片当前数据如下」人话列表。改旧卡、纠正、commit 都从这里读：

| 你要的 | 从哪读 |
|--------|--------|
| 卡片 ID | `ui_snapshot.card_id` / `card_data.cardId` |
| 字段 | `card_data.cardPayload.sections` 里各 field 的 `value.raw` / `displayText`（`ownerName.raw.memberId`、`amount.raw` 等） |
| 卡片状态 | `card_data.status`：`0` 待确认 / `1` 已确认 / `2` 已取消 |
| 改哪条消息 | `ui_snapshot.update_card_info.update_seq_id`（就是这张卡所在消息的 seq_id），`commit_txn` 原样传 `update_seq_id` |

**确认轮（新增流）**多一行 `ext.gui_action: checkin/confirm`，且信封 `ui_snapshot.status` 可能是 `processing`（端上待录入）；卡面 `card_data.status` 在点下去的瞬间往往还是 `0`。字段以这份 snapshot 为准，不要凭记忆。

**历史流**没有 `gui_action`（用户没点）。正文仍是当时那句导语，但必须带上同一份 `ext.card_env`，且 `card_data.status` 必须是**当前真实状态**（已确认=`1`、已取消=`2`、还没点=`0`）。没有这份结构就无法 update 旧卡。

用户点取消不经过你：端上直接变 `2`，你不会收到取消轮；历史里再见到这张卡时 status 已是 `2`，不要再 commit、不要再出一张。

> **`card_data.status=0` 的历史卡还在等**：用户这条消息是在改它的字段（如「是48不是38」）→ **开一张新 `card_id` 的卡**，旧卡 id 填进 `supersedes`。skill 会把旧卡 update 成已取消并 create 新卡。`status=1` 是已落库快照，不要当草稿再 commit；要改已入账的记录走 `find_txn` + 带 `txn_id` 的编辑卡。回执用自然语言，不要贴 JSON/命令。

## tracker.py CLI 参考

所有命令在工作目录 `/data/skills/bookkeeping_checkin_appskill` 下通过 `python3 assets/tracker.py <command>` 调用。结构固定的单行结果输出 `key=value`，`list_txns` / `query` 输出 JSON（备注/商户里可能有空格，`key=value` 会被截断）。

**对你开放**——成员管理（见上方「成员管理」）与只读查询：

```bash
python3 assets/tracker.py list_txns [--member <m>] [--date <YYYY-MM-DD>] [--month <YYYY-MM>] [--type income|expense] [--limit <n>]
python3 assets/tracker.py summary  [--member <m>] [--month <YYYY-MM>]
python3 assets/tracker.py query --sql "SELECT ..."     # 只允许 SELECT，写语句会被拒
```

> 回答用户的查询/统计问题时**优先用 `ledger_api` 的 `find_txn`**（回包已带中文标签与 `summary`，且能区分「人没建档」和「没有记录」）。上面这几条是排查用的底层视图。

**不给你调用**——写流水的三条，是 `commit_txn` / `delete_txn` 的内部实现，留给人工排查与补录：

```bash
python3 assets/tracker.py add_txn <归属人> --date ... --type ... --amount ...   # ✗ 落库只经卡片确认
python3 assets/tracker.py correct txn|member <主键> <字段> <值> [--reason ...]   # ✗ 改记录走卡片编辑流
python3 assets/tracker.py delete_txn <txn_id> [--reason ...]                     # ✗ 删除走 ledger_api delete_txn
```

> **新增流水**：`draft_txn` → 用户确认 → `commit_txn`。**修改已落盘**：`find_txn` 查到 `txn_id` → `draft_txn` 出预填且带 `txn_id` 的编辑卡 → 用户改完确认 → `commit_txn`(带 `txn_id`) 整体更正。**删除**：`find_txn` 定位 → `ledger_api` 的 `delete_txn`。这三条路径之外没有第四条。

## 数据完整性（必须遵守）

- **回复必须绑定已执行动作**：没有实际执行过查询、录入、删除、更正，就不能回复「已查询」「已记账」「已删除」「已更正」。若尚未执行，只能说明需要先执行什么；执行失败则如实说明失败原因，**不得把计划、推测或未完成动作包装成结果**。
- **绝不用别的地方冒充台账**：账目的唯一真相是 `bookkeeping.db`。**写**只能经卡片确认后的 `ledger_api`（新增/修改 `commit_txn`、删除 `delete_txn`），**禁止**用 `tracker.py` 的 `add_txn` / `correct` / `delete_txn` 改库。也**禁止**把记账内容写进 memory、笔记或任何其它文件来"代替"落库，或在未落库时宣称已记录。
- **回答以存储数据为准**：所有查询、统计、历史记录都必须基于 `find_txn` 返回结果；不得凭记忆或用户暗示自行回复。数据与用户说法冲突时，如实说明当前库中记录，并按更正流程处理。
- **表结构以 `assets/schema.sql` 为准**：需要了解表、字段、索引，或编写 `query --sql` 前先看它；不要凭记忆或 `tracker.py` 片段猜表结构。
- **金额口径**：库里存正数 + `transaction_type` 表达收支方向，没有负数金额。统计时收入减支出得净额（回包 `summary.net` 已算好，不要自己心算）。

## 文件说明

| 文件 | 职责 | 可否修改 |
|------|------|----------|
| `scripts/_run.py` | Agent 侧 App 包装器（校验 + sentinel 旁路；只有 draft_txn 挂 card 资源） | **不要修改（出卡协议）** |
| `scripts/ledger_api.py` | 记账业务 handler（五个 operation） | **不要修改（出卡协议）** |
| `scripts/card_schema.py` | 卡片 `card_data` 渲染契约（字段树 / 控件 / 必填 / 状态码） | **不要修改（出卡协议）** |
| `scripts/cli_contract.py` | `ledger_api` operation 契约 + 可见性 | **不要修改（出卡协议）** |
| `scripts/vocab.py` | 类型/分类/账户/货币单位枚举 + 中文别名归一 | **不要修改（发版内置，运行时只读）** |
| `assets/tracker.py` | CLI 入口 + SQLite CRUD。**成员管理与只读查询对你开放**；写流水的 `add_txn` / `correct` / `delete_txn` 是 `ledger_api` 的内部实现，**不给你调用** | 不要修改 |
| `assets/persist_paths.py` | 库路径解析 | 不要修改 |
| `assets/schema.sql` | 建表脚本（`member` + `txn` + `reissue_lock`） | 不要修改 |
| `assets/app.yaml` | App Skill manifest（UI 资源 + `ledger_api` 工具 + 可见性） | 不要修改 |
| `/data/user_persistent_data/bookkeeping.db` | SQLite 数据库（**本 skill 唯一持久化**） | 只通过 `ledger_api` 操作 |

## 词表只读

`scripts/vocab.py` 是发版内置词表，**运行时不要改**。加分类/账户走重新发版，不要在沙箱里改文件。遇到词表没有的分类或账户：**先按 `other` 出卡并在备注里写明**，不要自己造 id（客户端选项表里没有，会渲染不出来）。

## 边界情况

- **归属人查不到**：先分清是「没建档」还是「叫法没录进别名」。若用户明说「小翘就是翘翘」，那是**加别名**（`add_alias`）而不是新建一个人——**建档前先 `find_member` 确认这人是不是已有档案的另一个叫法**，否则同一个人会有两份档、账目被劈成两半。
- **一笔账涉及两个账户**（如「从银行卡转到支付宝」）：一期没有转账类型，表达不了。如实告诉用户暂不支持转账，或建议按支出/收入各记一笔。
- **外币消费**：货币单位用中文名，默认人民币。常用见上方枚举。用户明说外币就按他说的出卡（表外也原样填），不要擅自折算成人民币，**不要**说不识别或不支持该货币。
- **分期/退款**：一期没有对应字段。退款可按「收入 + 备注写明是退款」记，但要先跟用户确认这样记可以。
- 遇到词表未覆盖的分类：**先按 `other` 出卡并在备注里写明**，不要自己造一个新的 id（客户端选项表里没有，会渲染不出来）。**不要**改 `vocab.py`。
