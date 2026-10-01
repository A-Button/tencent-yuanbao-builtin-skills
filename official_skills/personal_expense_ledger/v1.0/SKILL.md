---
name: personal_expense_ledger
description: 用于个人或群一起记账：录入花销、查合计、设预算、出日/周/月账单。用户要记账、报一笔花费（如「奶茶18」「午饭42」）、问花了多少/一共多少、要日报周账单月账单，或谈到花销、开销、预算时，调用此 Skill。
keywords:
  - 记账
  - 花销
  - 开销
  - 预算
  - 日报
  - 周账单
  - 月账单
---

## 初始化

**背景**：skill 装在只读目录 `/data/skills/{slug}/`，不能在那里写数据。要把脚本复制到可写工作目录 `/data/user_persistent_data/{slug}` 再运行。数据库与审计通过 `LEDGER_DATA_DIR` 落在 `/data/user_persistent_data`（库名 `ledger.db`，与跑团 `tracker.db` 分开）。

**第 1 步：直接进入工作目录并运行命令（不要预先创建/复制）。**

```bash
cd /data/user_persistent_data/{slug}
export LEDGER_DATA_DIR=/data/user_persistent_data
python3 assets/ledger.py <command> ...
```

- ✅ **执行成功** → 完成，不要再复制。
- ❌ **报错 `cd: No such file or directory`** → 第 2 步初始化后重跑本步。

**第 2 步（仅目录不存在时）：**

```bash
mkdir -p /data/user_persistent_data/{slug}
cp -rn /data/skills/{slug}/assets /data/user_persistent_data/{slug}/   # -n 保护改过的 rules.py
```

> 数据库无需手动建——首次命令会按 `assets/schema.sql` 建表。

本 skill 的 `{slug}` 固定为目录名：`personal_expense_ledger`。

## 数据完整性（必须遵守）

- **绝对禁止编造金额/分类/日期**：一律来自用户明确提供或票据截图；缺字段就问一句或按默认（日期=今天、分类走别名/其它）。
- **禁止写入任何测试/探针/占位数据**：不得为「试试 skill 通不通」「初始化一下」而 `add` 1 元、测试、demo、hello 等假流水。库空着完全正常；第一条必须是用户真实开销。
- **AI 不算账**：合计、预算剩余、日报/周账单成文全部由 CLI 输出；禁止心算后直接回复「一共 X」「今天共 X」。
- **回答以存储数据为准**：查询/汇总/日报必须先跑 CLI；不得凭记忆回复。
- **回复必须绑定已执行动作**：没跑过 `add`/`delete`/`correct`/`calc`/`report`，就不能说「已记上」「今日共花 X」。
- **命令优先**：先用 `find_member` / `add_member` / `add` / `list` / `calc` / `report` / `set_budget`；没有对应命令再用 `query --sql`。
- **表结构以 `assets/schema.sql` 为准**。
- **更正/删除必带 `--reason`**，自动写 `ledger_audit_log.jsonl`；改他人账还要带 `--actor`（管理员）。
- **无排行榜**：不做「谁花最多」排名；但**必须按成员区分汇总**（见下）。

## 群记账硬约束（本次踩坑必守）

1. **不用先手建档**：`add --member <昵称>` 时若成员不存在，**CLI 自动建档**（`id=user_N`，与跑团一致；`name`=展示昵称）。默认把消息里的 **sender_nickname**（没有就用群里能拿到的展示名/uid）传给 `--member`；用户说「记到某某 / 帮某某记」则 `--member` 用某某（也会自动建档）。`--recorded-by` 填当前发言者（默认同归属人）。
2. **别名仍可用**：同一个人多个叫法时，用 `add_alias` / `update_member` 合并，避免「小明/明明」拆成两个人。查找按 name/at_name/alias，**不要**拿中文昵称当 id。发现重复人了再合并，**不要**每次记账先盘问建档。
3. **改删权限**：本人可改自己的流水；改/删别人的必须 `--actor` 为 `is_admin=1` 的管理员。管理员可用 `update_member <谁> --is-admin 1` 设置（需已存在或先记过一笔自动建档）。
4. **范围别搞错**：
   - 「现在一共多少了 / 总共 / 合计」→ `calc --all`
   - 「今天花了多少 / 日报」→ `calc --period day` 或 `report --period day`
   - 「本周 / 周账单」→ `report --period week`
   - 「本月 / 月账单 / 这个月花了多少」→ `report --period month`
5. **截图日期按票面记**；「一共」用 `--all`；数字只许抄 CLI。
6. **禁止测试/探针假流水**。
7. **账单必须带归属人**：`report` 输出里已有 `👥 按成员` / `👤 昵称`；回复时**原样贴 CLI 账单正文**（可删顶底装饰行），**禁止**改写成没有「是谁的」的扁平列表。回执「已记」也要带归属昵称（如「@变 手环950已记」）。

## 文件说明

| 文件 | 职责 | 可否修改 |
|------|------|----------|
| `assets/ledger.py` | CLI + SQLite CRUD + 汇总/日报 | **不要修改** |
| `assets/rules.py` | 分类清单、口语别名、日报/周账单文案 | **唯一可修改**（改工作目录副本，见下） |
| `assets/schema.sql` | 建表（member / txn / budget） | 不要修改 |
| `/data/user_persistent_data/ledger.db` | 成员、流水与预算 | 通过 CLI |
| `/data/user_persistent_data/ledger_audit_log.jsonl` | 写入/更正/删除审计 | 只读 |

改规则时编辑的是工作目录里的副本：  
`/data/user_persistent_data/personal_expense_ledger/assets/rules.py`  
（首次 `cp -rn` 拷过去后常驻；`-n` 不会覆盖你已改过的版本。）

## 类目（标准 + 可自定义）

**内置标准类**（`rules.py` 的 `CATEGORIES`）：餐饮、奶茶咖啡、交通、日用、娱乐、住房、工资收入、其它。

### 记账时怎么归一（`--category`）

CLI 会走 `normalize_category`，你传之前也可以先归一好再传，规则一样：

1. **已是标准类** → 原样（如 `餐饮`）。
2. **命中口语/品牌别名** → 归到标准类（如 `奶茶`/`喜茶` → `奶茶咖啡`，`午饭` → `餐饮`）。别名表在 `CATEGORY_ALIASES`。
3. **信息够、能明确归到某一标准类** → **直接归过去**，不必问用户（如「麦当劳套餐」→ 餐饮，「地铁通勤」→ 交通）。把最终标准类名传给 `--category`；细节放 `--note`。
4. **用户明确要新类、或现有类都不贴切** → 允许自定义类名写入：
   - **要短**：建议 **2～6 个字**（如 `宠物`、`房租水电`）；**硬上限 12 字**（更长会被收成「其它」）。
   - **禁**笼统词：支出 / 收入 / 花费 / 开销（会归「其它」）。
   - 例：用户说「记到宠物粮」且不想并进日用 → `--category 宠物 --note 猫粮`。
5. **完全说不清** → `--category` 省略或「其它」，用 `--note` 留原话；不要编造类目。

### 用户要「加一个固定类 / 改映射」时（改 `rules.py`）

当用户说「以后医美单独一类」「霸王茶姬都算奶茶」等 **要固化** 的需求：

1. 编辑工作目录 `assets/rules.py`（路径见上），**不要**改只读包 `/data/skills/...`。
2. **新标准类**：把短名加入 `CATEGORIES`；可选在 `CATEGORY_EMOJI` 加一个表情。
3. **口语归一**：在 `CATEGORY_ALIASES` 增加 `'口语或品牌': '标准类名'`。
4. 改完后下一次 `add`/`report` 即生效；**不必**重启。旧流水仍保留当时写入的 category 字符串。
5. 回执用白话说明「已加上类目 X」或「已把 Y 归到 Z」；**不要**贴大段源码。

临时记一笔用自定义短名即可；只有用户希望「以后都这样」才改 `rules.py`。

## 使用场景（群里一起随手记）

适合「吃饭 + 奶茶」一起记账。说话即记：用 sender_nickname 自动建档；周账单按人分段。

## 工作流

### 成员（可选维护，非记账前置）

多数情况**不用管**。需要时：

```bash
python3 assets/ledger.py find_member <昵称|别名>
python3 assets/ledger.py list_members
python3 assets/ledger.py add_alias <昵称> '外号'          # 合并叫法
python3 assets/ledger.py update_member <昵称> --is-admin 1
python3 assets/ledger.py add_member <id> <name> ...      # 仅特殊场景手建
```

### 记一笔

1. 归属人 = 当前 `sender_nickname`，或话里「记到某某」的某某。
2. **类目**：能归一到标准类就归一；用户要新类用短名（见「类目」节）。细节进 `--note`。
3. 直接记（不存在则自动建档）：
   `python3 assets/ledger.py add <金额> --member '<sender_nickname或某某>' [--recorded-by '<发言者>'] [--category 奶茶|餐饮|自定义短名] [--note 喜茶] [--occurred-at YYYY-MM-DD] [--image-url URL]`
4. 回执看 `txn_id`；若返回 `member_created=1` 说明刚自动建档，不必再向用户确认建档。

### 查流水 / 汇总（禁止心算）

| 用户说法 | 命令 |
|----------|------|
| 一共多少 / 总共 / 现在多少了 | `calc --all`（可加 `--detail`） |
| 今天花了多少 | `calc --period day` |
| 本周花了多少 | `calc --period week` 或周账单 |
| 本月花了多少 | `calc --period month` 或月账单 |
| 某个人 | `calc --all --member '昵称或别名'` |

### 日报 / 周账单 / 月账单

```bash
python3 assets/ledger.py report --period day
python3 assets/ledger.py report --period week
python3 assets/ledger.py report --period month
```

账单 stdout 含按成员分段；群聊回复必须保留 `👤 谁`，不要自行重排成无归属明细。

### 更正 / 删除

1. `calc --all --detail` 或 `list` 定位 `txn_id`
2. 本人：`correct/delete ... --reason '...' --actor '<自己>'`
3. 改他人：操作者须为管理员，`--actor '<管理员>'`

### 预算（可选）

```bash
python3 assets/ledger.py set_budget --period week --amount 500
python3 assets/ledger.py show_budget
```

## CLI 命令

```bash
# 直接记账（自动建档）—— --member 用群消息 sender_nickname
python3 assets/ledger.py add 18 --category 奶茶 --note 喜茶 --member '张三'
python3 assets/ledger.py add 42 --category 餐饮 --note 午饭 --member '李四' --recorded-by '张三'

# 可选：补别名 / 设管理员
python3 assets/ledger.py add_alias 张三 '三哥'
python3 assets/ledger.py update_member 张三 --is-admin 1

# 汇总 / 账单
python3 assets/ledger.py calc --all --detail
python3 assets/ledger.py report --period week
python3 assets/ledger.py report --period month
```

## 明确不做

- 多账户（微信/支付宝分账）、转账、汇率
- AA 自动分摊、排行榜、处罚
- 强制截图才能记账
- **强制先建档再记账**（已改为自动建档）
