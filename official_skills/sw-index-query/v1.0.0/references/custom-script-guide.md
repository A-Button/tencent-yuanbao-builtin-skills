> 行情优先使用 westock；必要时通过网页检索补充并核实来源、日期与口径。执行与交付遵循 [DATA_SOURCE.md](DATA_SOURCE.md)；最终回复只表达结果与分析范围，不转述内部诊断。

# Custom Script Guide — 第二级 Autonomous Mode 写 Adhoc 脚本指南

> **何时读我**：SKILL.md STEP 4 第二级 Autonomous Mode 激活后，写 adhoc 前必读。
> **本指南内容**：11 条黄金规则 + 3 种调用方式 + 5 个典型场景 + 完整代码模板。
> **数据规则**：行情优先使用 westock 与共享 helper；网页可补充经核实的行情、估值、公告和宏观资料。记录来源、日期、币种与单位，不把不同口径的数字混成一个序列。

## 一、脚本规则

1. **优先复用 `datasource` / `sw_common`**，需要网页补充时由 Agent 使用环境中的搜索和页面读取工具核实，再将结构化数据交给脚本。只有完整可靠的时间序列才参与指标或回测计算。错误留在内部诊断，最终回复只说明结果、覆盖范围与结论边界。

2. **禁止导入系统操作**
   - ❌ `import os; os.system(...)` / `subprocess.run("rm ...")`
   - ✅ `subprocess.run(["python", "scripts/sw_XXX.py", ...])` — 仅允许调预制脚本

3. **脚本必须接受 `--help`，有 argparse，尽量多暴露参数**
   - 追问改参数时不用改代码，直接重跑 `python .scripts/{slug}.py --new-args`
   - 模板见下文"四、完整代码模板"

4. **错误必须 stderr + `sys.exit(1)`**
   ```python
   except Exception as e:
       print(json.dumps({"status":"error","message":str(e)}, ensure_ascii=False),
             file=sys.stderr)
       sys.exit(1)
   ```

5. **stdout 最后一行必须是 JSON**
   ```python
   # 最后一行
   print(json.dumps({
       "status": "ok",
       "summary_text": "...",   # ← agent 回复时引用的核心字段
       ...其他数据,
   }, ensure_ascii=False))
   ```

6. **临时脚本的 UI 交付优先复用预设脚本 emit**（纯数据脚本首选）
   - 默认不 emit，agent 用文字回复
   - 需要 UI 时走"方式 B"（subprocess 调预设脚本，预设自己 emit）
   - **允许自写 HTML 交付**：需要自定义图表/页面时，可 `from sw_html_render import build_page, ...` 组装交互式 HTML 文件（ECharts，红涨绿跌），路径放进 stdout JSON 的 `render_files` 字段，agent 用 present_files 推送。**禁止手写 `<pi-artifact>` 标签或 emit 未注册模板名**（防 "Unknown template" 前端错误）

7. **文件名语义化**
   - ✅ `sector_rotation_2026.py` / `consecutive_pe_decline_tmt.py`
   - ❌ `tmp.py` / `test.py` / `analysis.py` / `a.py`

8. **控制调用量**
   - 批量K线优先按最多6代码分批获取，避免按“行业×日期”逐条查询。
   - 遇限流停止重复调用；改用已有样本或经核实的网页补充，并标明实际数据日期。

9. **多轮修改原则**（防止 session 污染）

   | 改动类型 | 处理方式 |
   |---------|---------|
   | 参数变（时间/范围/阈值） | **不改代码**，重跑 `python .scripts/{slug}.py --new-args` |
   | 逻辑变（算法/过滤/数据源） | **Edit 同一 `{slug}.py`**，slug 不变，重跑 |
   | 方向完全变（问题性质改了） | 新建 `workspace/.scripts/{new_slug}.py`，语义化重命名 |

10. **调试一行式，不落盘 debug 文件**（反污染）

    **禁止**：为了诊断中间变量、检查 API 返回、试函数签名而新建 `debug_*.py` / `check_*.py` / `test_*.py` 文件。session 目录 `workspace/.scripts/` 污染后难追溯。

    **✅ 推荐做法**：
    
    (a) **一行式 `python -c`** — 快速检查 API 返回 / 函数签名：
    ```bash
    python -c "
    import sys; sys.path.insert(0,'/path/to/sw-index-query-portable/scripts')
    from sw_common import fetch_period_dates
    dates = fetch_period_dates('MONTH')
    print('len:', len(dates), 'first3:', dates[:3])
    "
    ```
    
    (b) **主脚本加 `--debug` flag** — 如果需要持久化的诊断逻辑（反复追问会用到），加到主 `{slug}.py` 里：
    ```python
    parser.add_argument("--debug-trend", action="store_true")
    ...
    if args.debug_trend:
        for code, pe_list in trend.items():
            print(f"{code}: PE={pe_list}", file=sys.stderr)
    ```
    下次追问加 `--debug-trend` 跑，诊断和业务同文件。
    
    (c) **read 源码看签名** — 不确定函数参数时：`read scripts/sw_common.py` 比写 debug 脚本更快。

    **❌ 禁止示例**：
    ```
    workspace/.scripts/debug_pe_trend.py      ← 禁止
    workspace/.scripts/check_dp.py            ← 禁止
    workspace/.scripts/test_fetch.py          ← 禁止
    workspace/.scripts/rotation_v2.py         ← 禁止（应 Edit rotation.py）
    workspace/.scripts/tmp.py                 ← 禁止
    ```

11. **量化回测优先复用共享 helper**（防手写回测出错）

    涉及净值曲线、最大回撤、MDD 起止日期、Sharpe/Calmar、RSI/均线策略回测时，优先调用：

    ```bash
    python backtest_helper.py（可选平台工具） --help
    ```

    **推荐分工**：
    - adhoc 负责用 `sw_common` 取数、清洗、生成 `workspace/backtests/{slug}/input.csv`
    - `backtest_helper.py（可选平台工具）` 负责净值/回撤/指标/图片输出

    **禁止**：在 adhoc 里临时重写复杂 MDD、净值曲线、RSI 回测核心逻辑；除非 helper 明确不支持，并且 stdout JSON 里说明降级原因。

    **交付要求**：helper 输出目录必须是 `workspace/backtests/{slug}/`；图片和 CSV/JSON 交付必须使用 `attach` 工具，禁止在回复中手写任何图片、文件或下载链接。

---

## 二、三种调用方式

### 方式 A · `import` 函数库（纯数据组合）

**场景**：需要自定义计算、组合多个 API 数据，不需要 UI 推送。

```python
from sw_common import fetch_kline_one
from sw_common import fetch_period_snapshot

# 拿 K 线 + 月末截面，自己组合计算
kline = fetch_kline_one("801780", period="DAY", days=250)
monthly = [fetch_period_snapshot("MONTH", None, "一级行业") for i in range(12)]

# 计算 rotation 速度 / streak / 等任意指标
result = compute_my_metric(kline, monthly)

print(json.dumps({"status":"ok", "summary_text":"...", "data":result}))
```

**优点**：完全自主，灵活。**缺点**：无 UI，用户只看文字。

---

### 方式 B · `subprocess` 调预设脚本（UI 推送）

**场景**：有现成的预设脚本能完成部分工作，想复用它的 UI 推送能力。

```python
import subprocess, json

# 调预设脚本，它自己通过 chat.artifact_event 推送模板到前端
r = subprocess.run([
    "python",
    "scripts/sw_comp.py",
    "--code", "801001", "--name", "申万50"
], capture_output=True, text=True)

# 取最后一行 stdout（JSON 摘要）
summary = json.loads(r.stdout.strip().split("\n")[-1])

# 组合到自己的结果里
print(json.dumps({
    "status": "ok",
    "summary_text": f"已推送申万50成分饼图，Top3: {summary['top3']}",
    ...
}))
```

**优点**：复用预设脚本的 UI 和数据。**缺点**：预设脚本的模板事件会额外推到前端。

---

### 方式 C · 混合（推荐大多数场景）

**场景**：adhoc 内既要自主计算，又要前端有图。

```python
import subprocess, json
from sw_common import fetch_period_snapshot

# Step 1: 调预设脚本推热力图给用户看
subprocess.run(["python", ".../sw_heatmap.py"], check=False)

# Step 2: 自主拉 12 个月末截面算 rotation
monthly = [fetch_period_snapshot("MONTH", None, "一级行业") for i in range(12)]
rotation = compute_rotation_speed(monthly)

# Step 3: 输出 JSON 给 agent 回复
print(json.dumps({
    "status": "ok",
    "summary_text": (
        f"2026 行业轮动分析：前端已展示当日热力图；"
        f"过去 12 月轮动速度 {rotation['speed']:.2f}，"
        f"最频繁切换的板块：{', '.join(rotation['hot_sectors'])}"
    ),
    ...
}))
```

---

## 三、5 种追问场景示例

### 场景 1：AskUserQuestion 选择返回 → 跳 Step 0 直接执行

```
T1 用户："某个行业今天怎么样"
T1 Agent thinking: intent="行业热力"命中白名单，但 scope 缺失
         → 第一级 + 澄清，不执行
         → 调用 AskUserQuestion（选项：消费/TMT/周期/金融，输入框兜底其他板块）

T2 用户：（选择 "TMT"）
T2 Agent thinking: 识别到上轮 AskUserQuestion 的返回
         → **跳 Step 0**，直接用 scope=tmt
         → bash python sw_heatmap.py --scope tmt
```

### 场景 2：参数调整（"再看看 / 换时间窗口"）

```
T1 用户："申万50 行情"
T1 Agent: 第一级 → sw_chart.py --mode realtime --code 801001

T2 用户："看近半年的"
T2 Agent thinking: 同 intent，只改 time → 仍第一级
         → 单指数K线统一走研报模板：sw_kline_report.py --code 801001 --days 125
         → bash python sw_kline_report.py --code 801001 --days 125
```

### 场景 3：升级第二级

```
T1 用户："银行行情"
T1 Agent: 第一级 → sw_chart.py --mode realtime --code 801780

T2 用户："那它连续 3 年跌了吗，帮我综合看看"
T2 Agent thinking: 检测到"综合看看"+ 非白名单 intent → 第二级
         → read custom-script-guide.md
         → 写 workspace/.scripts/bank_3yr_decline_review.py（行情优先走 sw_common）
         → 执行 → 回复
```

### 场景 4：第二级细化 → Edit 同文件

```
T1 用户："2026 A 股行业轮动分析"
T1 Agent: 第二级 → 写 workspace/.scripts/rotation_2026.py
        脚本里：parser.add_argument("--scope", default="all")

T2 用户："聚焦 TMT 再看看"
T2 Agent thinking: 同 slug 任务，只改 scope 参数
         → **不改代码**，直接：
         → bash python workspace/.scripts/rotation_2026.py --scope tmt
```

### 场景 5：第二级修正 → Edit 同文件改逻辑

```
T1 用户：写 adhoc 算"行业一年收益"，拿到结果
T2 用户："不对，应该排除创业板指数"
T2 Agent thinking: 算法过滤规则要改 → **Edit 同一个 {slug}.py**
         → Edit 加入：excluded_codes = ["399006", ...]
         → bash python .../{slug}.py 重跑
         → slug 保持不变
```

---

## 四、完整代码模板

**复制 `scripts/.adhoc-template.py` 到 `workspace/.scripts/{slug}.py` 即可**。

模板已预设：
- argparse 骨架（含常用 `--scope` `--days` `--verbose` 参数槽）
- 类型注解 + docstring
- stdout JSON + stderr 错误处理
- 注释标注"在此填业务逻辑"

**关键：写时尽量暴露参数给 argparse**，追问改参数不用改代码。

---

## 五、常见错误（agent 自检清单）

写完 adhoc 后在 thinking 里问自己：

- [ ] 文件名语义化了吗？（不是 tmp.py）
- [ ] stdout 最后一行是 JSON 吗？
- [ ] 错误用 stderr 吗？
- [ ] 行情优先复用 `datasource`/`sw_common`，网页补充已核实原页面？
- [ ] 跨市场/第三方数据是否走 WorkBuddy 能力（专业 skill / WebSearch / Connector），并标注了来源与口径？
- [ ] 按批次获取行情，避免重复请求？
- [ ] 追问场景下选对了"重跑 / Edit / 新建"？
- [ ] 需要 UI 时复用了预设脚本，或自写 HTML 时用了 `sw_html_render.build_page`（未手写 `<pi-artifact>`）？
- [ ] 回测/净值/MDD/RSI/均线任务优先用了 `backtest_helper.py（可选平台工具）` 吗？

---

## 六、能力边界

| 用户问 | 方案 |
|-------|------|
| 具备经核实的行情序列 + 可以用Python完成计算 | ✅ 第二级 Autonomous，写 adhoc（走 `sw_common` 取数） |
| 所需字段或时间窗口需要补充 | ✅ 网页检索原页面或使用已连接的金融工具核实；最终仅说明实际样本范围和可支持的结论，不解释内部尝试过程 |
| 港美股 / 大宗商品 / 宏观 / 其他指数体系 | ✅ 转 WorkBuddy 平台能力获取（`neodata-financial-search`、WebSearch、金融类 Connector、用户自定义 skill 等），不在 sw-index-query adhoc 中拒答 |
| 港股个股行情/走势/技术面/深度分析 | ✅ 转 `neodata-financial-search` 或 WorkBuddy 通用金融能力处理 |
| 行业行情 + 第三方资料混合分析（如"申万行业 vs 美股板块联动"） | ✅ adhoc 内分源取数后合并计算，分别标注来源与时点/口径，不做隐式混算 |
| 需要预测 / 投资建议 | ❌ 固定拒绝（合规），只陈述数据 |
