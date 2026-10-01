> 行情优先使用 westock；必要时通过网页检索补充并核实来源、日期与口径。执行与交付遵循 [DATA_SOURCE.md](DATA_SOURCE.md)；最终回复只表达结果与分析范围，不转述内部诊断。

# 澄清流程模板库（AskUserQuestion 多轮）

> **何时读此文件**：STEP 2 识别到 **0 个指数**，但意图类别**必须有指数参数**时（深度分析/技术诊断/历史行情/成分股），Agent 必须**用 AskUserQuestion 工具推送选项让用户选择，不得中断**。
>
> **禁止**：识别不到指数就回复"查不到相应申万指数"然后停在那里。那是破坏体验的做法。

---

## 使用指引（WorkBuddy 环境）

WorkBuddy 的澄清交互通过内置 **AskUserQuestion 工具**完成（等价于原平台的 pi-choices，且自带自由输入框）：

1. 根据用户意图选择下方对应模板（行业选择 / 指数选择 / 板块选择）
2. 调用 AskUserQuestion 工具，构造选项（每问题 **2-4 个选项**，每个选项 = `label` + `description`；用户随时可通过工具自带输入框自由输入，**无需再单列"其他"选项**）
3. 推送后**结束本轮回复**——等用户选择；AskUserQuestion 会把用户选择（或自由输入内容）作为下一条消息发给 agent
4. 下一轮 agent 收到选择（如收到 `"电子"` 或 `"801080"`），进入正常 STEP 2 → STEP 3 流程

**硬规则**：每轮只能发起 1 次澄清（AskUserQuestion 一次调用可含 1-4 个问题，但**同一轮只问 1 个问题**）。连续推两个澄清会导致用户选择丢失。

> 若 AskUserQuestion 工具不可用（纯文本通道），降级为：在回复正文中列出 2-4 个带代码的候选 + 邀请用户"回复行业名或代码"。

---

## 模板 1：行业选择（31 个一级行业）

**触发场景**：
- 技术诊断缺 --code（"某个行业今年以来技术分析"）
- 深度分析缺 --code（"某个一级行业的深度分析"）
- 行业成分股查询缺 --code

**推送方式**（AskUserQuestion，选高频 4 个 + 工具自带输入框兜底任意行业）：

```
question: "请选择要分析的一级行业（也可直接输入行业名或代码）"
options:
  - label: "银行",            description: "801780"
  - label: "电子",            description: "801080"
  - label: "医药生物",        description: "801150"
  - label: "食品饮料",        description: "801120"
```

用户选 label（如"电子"）或自由输入（如"801780"）后，下一轮 agent 走 STEP 2 正常识别即可。

---

## 模板 2：指数选择（常见指数 + 自由输入兜底）

**触发场景**：
- 历史行情（K 线）缺 --code（"某个指数的日 K 线图"）
- 实时行情/分时缺 --code
- 指数成分股缺 --code

因指数总量庞大（市场表征 9 + 一级 31 + 二级 124 + 风格 16 + 大类风格 6 + 金创 4 + 基金 ~40），**不做全量选项**，列常见 + 输入框兜底：

```
question: "请选择或输入指数（名称或代码均可）"
options:
  - label: "申万A指",     description: "801003 · 全市场表征"
  - label: "申万300指数", description: "801300 · 大盘蓝筹"
  - label: "申万50",      description: "801001 · 超大盘"
  - label: "申万创业",    description: "801005 · 创业板"
```

用户选常见项（如"申万300指数"）或自由输入（如"银行"或"801780"），下一轮 agent 走 STEP 2 识别。

---

## 模板 3：板块范围选择（6 个 scope 预设）

**触发场景**：
- 行业热力缺范围（"帮我查询某板块涨跌"）
- 收益风险矩阵缺范围
- 市场仪表盘缺范围

```
question: "请选择板块（也可直接输入：高端制造 / 防御 / 全部 31 个一级行业）"
options:
  - label: "消费",     description: "consumer · 医药/食品/家电/商贸/美容/纺服/农林/轻工"
  - label: "TMT",      description: "tmt · 电子/计算机/通信/传媒"
  - label: "周期",     description: "cyclical · 有色/钢铁/煤炭/化工/石化/建材"
  - label: "金融",     description: "finance · 银行/非银金融/房地产"
```

用户选择后 agent 将收到的 label（或自由输入）**反向映射**为 `--scope` 参数：

| label / 输入 | --scope 参数 |
|-------|-------------|
| 消费 | `consumer` |
| TMT | `tmt` |
| 周期 | `cyclical` |
| 金融 | `finance` |
| 高端制造 | `mfg` |
| 防御 | `defensive` |
| 全部 / 全部31个 / all | `all`（或不传 --scope） |

---

## 多轮流程示例

**示例 1：技术诊断场景**

```
Turn 1 用户：某个行业今年以来技术分析
Turn 1 Agent：
  [识别 STEP 2 = 0 个指数, 意图=技术诊断 → 触发澄清]
  [调用 AskUserQuestion：模板 1 行业选择（银行/电子/医药生物/食品饮料）]
  正文："请选择要分析的一级行业，或直接输入行业名/代码。"

Turn 2 用户：电子（AskUserQuestion 返回的选择）
Turn 2 Agent：
  [STEP 2 识别 1 个 = 电子 (801080)]
  [执行 sw_tech.py --code 801080 --name 电子 --days 250]
  ...
```

**示例 2：K 线场景（用户自由输入）**

```
Turn 1 用户：某个指数的日K线图
Turn 1 Agent：
  [调用 AskUserQuestion：模板 2 指数选择]

Turn 2 用户：银行（自由输入）
Turn 2 Agent：
  [STEP 2 模糊匹配到 = 银行 (801780)]
  [执行 sw_kline_report.py --code 801780 --name 银行 --days 90]
```

**示例 3：板块场景**

```
Turn 1 用户：帮我查询某板块涨跌，我下一条给出
Turn 1 Agent：
  [调用 AskUserQuestion：模板 3 板块选择]

Turn 2 用户：TMT
Turn 2 Agent：
  [反向映射 TMT → --scope tmt]
  [执行 sw_heatmap.py --scope tmt]
```

---

## 反模式（禁止）

- ❌ 一轮发起 2 次澄清（AskUserQuestion 一次只问 1 个问题）想省一轮
- ❌ 推完澄清后继续执行脚本（"先选择，我顺便也跑一下默认的"）
- ❌ 用户没说明时猜一个默认值（如默认选申万 50）→ 不尊重用户意图
- ❌ 在正文里平铺列 31 个行业让用户"输入名称回复" → 用 AskUserQuestion 选项交互（选项 label + 输入框兜底）
