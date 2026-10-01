# offer-e-skill · 求职辅导能力包（平台无关单 Skill 版）

> 由「Offer鹅」专家包（Expert Package / Plugin）重构而来的**标准单 Skill**。原专家包把能力拆成「主 Agent + 6 个子 skill + 8 个 reference + 6 个脚本 + 1 个本地测评 HTML 页」，本 skill 把它们压成一个 `SKILL.md`，知识拆到 `references/`，工具拆到 `scripts/`，剥离了专家包的「身份壳」和「体验壳」，交互层全部降级为**纯文本**，能力层 / 记忆层 / 脚本层完整保留（零能力损耗）。

## 这是什么

一个**阶段感知型校招辅导助手**：先判断你处于求职的哪个阶段，再给针对性建议，覆盖求职全流程：

| 阶段 | 能力 |
| --- | --- |
| §0 阶段路由 | 每次对话先判定你属于哪个阶段 |
| §1 求职初期 | 方向探索（迷茫 / 不知道适合什么方向 / 纠结方向） |
| §2 能力建设 | 已定方向，补能力 / 项目 / 实习 |
| §3 校招冲刺 | 简历诊断、面试辅导与模拟陪练、面试复盘、投递 / 岗位查询、防诈骗 |
| §4 职业路径 | 已有 offer 的取舍、长期职业路径规划 |
| §5 职业测评 | 职业锚校园版：结果码解析 + 画像解读 |

## 目录结构

```
offer-e-skill/
├── SKILL.md                    # 单 skill 主文件（frontmatter + 头部 + §0~§5）
├── README.md                   # 本文件（说明，不参与评测）
├── references/                 # 知识库（原样搬运，仅 2 处局部改写）
│   ├── career-memory.md        # 记忆系统说明（路径改写为 ~/.offer-e/）
│   ├── career-memory-template.md  # 记忆文件模板
│   ├── sprint-reference.md     # 冲刺阶段参考
│   ├── guides/                 # resume-guide / interview-guide
│   ├── knowledge/              # job-database
│   ├── safety/                 # sensitive-topics / anti-fraud-keywords / interview-safety-rules
│   └── assessment/             # knowledge_base / dialogue_examples（卡片→纯文本）
└── scripts/                    # 工具（仅 career_memory.py 改了默认路径）
    ├── memory/career_memory.py     # 记忆读写（默认路径 ~/.offer-e/offer-e-memory.md）
    ├── recruit/                    # fetch_recruit_info / fetch_recruit_jds（直连 join.qq.com）
    ├── resume/resume_checker.py    # 简历检查
    ├── safety/fraud_checker.py     # 防诈骗检查
    └── utils/check_python_env.py   # Python 环境自检
```

## 与原专家包的关系

- **不覆盖原文件**：本 skill 是独立复制到新目录，源目录 `/Users/dylan/Downloads/offer-e/` 未被触碰。
- **剥离了什么（身份壳 + 体验壳）**：
  - `plugin.json` / `avatars/expert.png` / `agents/` / `README.md`（身份声明、头像、开场白人设）
  - `skills/assessment/assets/index.html` + `resolve_asset_path.py`（本地测评 HTML 页）
  - `present_files` / `show_widget` / `AskUserQuestion` / `${CODEBUDDY_PLUGIN_ROOT}` / 子 skill 装载机制（WorkBuddy 运行时依赖）
- **保留了什么（能力层 + 记忆层 + 脚本层）**：
  - 决策优先级链（Step1~Step4）、12 类意图路由矩阵、红线、6 阶段全流程
  - 8 个 reference 知识库、结果码解析器、M1~M7 + 13 条铁律
  - 6 个脚本（代码零改动，仅记忆脚本默认路径标准化）

## 记忆路径

记忆文件默认写入 `~/.offer-e/offer-e-memory.md`（固定绝对路径，跨会话 / 跨工作目录不漂移）。可通过环境变量覆盖：

```bash
export OFFER_E_MEMORY_PATH=/path/to/your/memory.md
```

## 运行环境

- Python ≥ 3.10 且 < 3.14（脚本纯标准库，无第三方依赖）。运行前可用 `scripts/utils/check_python_env.py` 自检。
- 腾讯校招信息**必须**优先跑 `scripts/recruit/fetch_recruit_*.py` 直连 `join.qq.com`，禁止用 WebSearch/WebFetch 替代。
