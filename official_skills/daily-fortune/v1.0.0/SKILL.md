---
name: daily-fortune
description: 带自渲染卡片的每日运势 App Skill。在卡片内切换今日/本周/本月/今年与事业/感情/财富/人际，展示由本地确定性引擎计算的运势解读。当用户要求"看看今日运势/本周运势/本月运势/今年运势"或"事业/感情/财富/人际运势"时使用。触发词包括：今日运势、本周运势、本月运势、今年运势、事业运势、感情运势、财富运势、人际运势、运势卡片。
agent_created: true
packageType: app-skill
instructionOnly: false
metadata:
  version: v1.2.0
  dataClassification: sensitive-personal-data
version: v1.0.0
---

# 每日运势

## 角色与入口

这是一个 **App Skill**：调用工具后，界面由 `ui://daily-fortune/main`（`assets/ui/index.html`）在对话里自渲染，
卡片自己读数据、自己发请求，**不生成也不返回任何 HTML 片段**。

- 唯一执行入口：`app daily-fortune daily_fortune '<json>'`
- 查看契约：`app daily-fortune describe`
- 查看工具：`app daily-fortune toollist`
- **禁止直接执行 `daily_fortune.py`**：绕开 CLI 就不会产出结果记录，界面不会挂载也不会刷新。
- **本技能没有订阅与推送能力**：不要承诺"每天自动推送"，也不要调用任何订阅类操作（已移除）。

## 执行优先级（严格约束，单一真源）

1. 任何动作都只能走 `app daily-fortune daily_fortune '<json>'`，没有第二条调用链。
2. 参数拿不准就先 `app daily-fortune describe`，不要凭记忆猜字段名。
3. 一次调用只做一件事；不要为"保险起见"连发多次同义调用。
4. 界面上能做的事（切维度、切主题）**交给用户点**，
   不要替用户连点；用户口头提出时，才由 Agent 代调。
5. 卡片返回什么就是什么，不另写一段文字复述卡片内容。

## 何时使用

- 用户要看"今日/本周/本月/今年运势"或"事业/感情/财富/人际运势"。

## Agent 操作

| 场景 | 调用 |
|---|---|
| 出今日卡 | `app daily-fortune daily_fortune '{"operation":"get_card"}'` |
| 看本周感情 | `app daily-fortune daily_fortune '{"operation":"get_card","timekey":"week","topickey":"love"}'` |
| 某天运势 | `app daily-fortune daily_fortune '{"operation":"get_card","target_date":"2026-09-10"}'` |
| 看他人 | `app daily-fortune daily_fortune '{"operation":"get_card","subject":"spouse-1"}'` |

## 字段说明

入参（顶层平铺，不要套 `payload`）：

- `operation`：`get_card` / `describe`
- `timekey`：`today` | `week` | `month` | `year`
- `topickey`：`career` | `love` | `wealth` | `social`
- `target_date`：`YYYY-MM-DD`，默认今天
- `subject`：档案主体，默认 `self`

返回（结构化，UI 与 Agent 共用同一份）：

- `data.card`：卡片本体（`score` / `keyword` / `overview` / `lucky` / `advice` / `insight` / `transit` / `bazi` / `evidence`）
- `data.needs_profile` + `data.profile_message`：缺出生档案时的引导
- `data.timekey` / `data.topickey`：卡片当前所处维度，UI 据此高亮
- `data.cards`：`cards[timekey][topickey]` 形式的 16 张预生成卡，供界面本地切换
- `transit.topicStar` / `transit.topicRelation`：该领域对应的十神，与流期对它的生克关系
- `card.favorableElement` / `card.favorableRank`：本次取用的喜用五行，及五个五行的优先级

## 运势是怎么随「时段 × 主题」变化的

**两段职责是分开的**：时段决定气场，主题只决定解读的落点。

四个时段取各自的流期锚点：今日→日柱、本周→该周周一的日柱、本月→月柱、今年→年柱。
喜用五行由「日主 + 流期天干 + 流期地支 + 日支状态」打分取最优，与生活领域无关——
所以**指数、概述、幸运色/时段/方位/数字/食物/配饰只随时段变化**，
切「事业/感情/财富/人际」时这些都不动。

每个主题对应一组十神（主星 + 辅星）：事业看官杀与印绶、财富看财星与食伤、
人际看比劫与印绶；感情按性别取——男命妻财、女命官杀，辅星一律看食伤（情感表达）。
辅星是必需的：女命的官杀既是事业星也是夫星，只看主星会让"事业"与"感情"的解读完全相同。
流期对该主星的喜克决定这一领域的顺逆，**只体现在解读区**。

五行只有五种，四个时段可能算出同一种喜用，因此 `buildAllCards` 会先定好四个时段
各自的喜用再做去重：撞上已用过的就退到次喜用，保证**切时段时幸运色确实会变**；
而同一时段内四个主题共用同一个喜用，不去重。

## 卡片交互（用户可直接在卡上做）

- 顶部切换 **今日 / 本周 / 本月 / 今年**
- 解读区切换 **事业/学习 / 感情 / 财富 / 人际**

这些动作**在界面本地完成，不发起新的工具调用**：引擎一次把 4 个时间维度 × 4 个主题共 16 张卡随包下发（`data.cards`），界面切换时直接取本地数据重绘。

为什么这么做：宿主对"UI 主动发起 tools/call"的支持并不一致——有的不响应（按钮一直转、永远 busy）、有的直接拒绝。早先依赖它回调，结果是"点了没反应"。改成一次下发、本地切换后，交互与宿主能力无关，切换也是瞬时的。

只有当本地没有对应数据时（例如传入了别的 `target_date`），界面才会回退到回调工具，并带 12 秒超时兜底，避免永久卡在 busy。

## 常见坑

- **直跑 handler**：绕过 CLI 直接跑 `app.yaml` 里那个 handler 脚本，不会有结果记录，界面不动。
- **stdout 多打一行**：handler 必须只输出一行 JSON，任何调试打印都会让 CLI 解析失败。
- **改了 UI 模板不重建**：改完 `assets/ui/index.template` 必须 `npm run build:ui`，
  运行时读的是 `assets/ui/index.html`。
- **缺出生档案**：`data.needs_profile` 为真时先引导登记，不要对着空卡硬解释。
- **别提订阅**：订阅能力已移除，不要说"已订阅/每天推送"之类的话。

## 隐私与限制

- 出生信息只读本地档案，不联网、不外传；本技能不写任何个人数据文件。
- 评分基于版本化五行规则（45–88），是娱乐性参考，**不是预测**，不构成健康、投资、法律、职业或婚恋决策建议。
- "本周"锚点按目标日期星期几在日干上偏移推导，属近似建模。

## 沟通规则

- 出卡时只说一句"这是你的运势卡片"，不复述卡面内容。
- 缺档案时一句话说明需要出生日期与时间，并说明用途。

完整接口说明见 `references/api_reference.md`。
