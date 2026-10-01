# 外部来源与吸收说明

本文件记录外部Skill的完整包审计、许可证、吸收内容和未引入内容。运行个人计划时无需读取。

2026-07-27通过SkillHub官方下载接口重新取得当前包，并逐文件读取。

| 来源 | 版本与许可 | 已吸收 | 未引入 |
|---|---|---|---|
| [30天学习计划制定师](https://skillhub.cn/skills/xiaozhi-learning-plan) | 2.0.0；MIT-0 | 五步流程、感受与数据对照、边界确认、首版校准、阶段模式、考前策略、任务颗粒度、时段和弹性原则 | 学习DNA、历史活跃度、家庭看板、自动执行监控和长期记录 |
| [中国健身计划生成器](https://skillhub.cn/skills/fitness-plan-cn) | 1.0.0；MIT | 目标判断、动作量化、周计划、强度递进、执行步骤、自检和风险边界 | 平台化通用文案；持续打卡由首期能力边界排除 |
| [求职全流程教练](https://skillhub.cn/skills/job-hunting-coach) | 1.0.0；MIT | 职业定位、JD三级匹配、材料准备、投递节奏、轮次策略、高频问题、模拟反馈、跨行业迁移、Offer核对、谈判、背调、交接和入职准备 | 简历全文代写、固定薪资涨幅、劳动法律判断、长期状态维护和上游PDF生成做法 |
| [JD＋简历→面试题预测助手](https://skillhub.cn/skills/jd-interview-prep) | 1.0.0；MIT-0 | 匹配分析、必问/针对/追问题目组合、单题答题要点、STAR提示和备考手册结构 | 外部大模型调用和默认DeepSeek端点；文件解析由现有工具完成 |
| [面试助手](https://skillhub.cn/skills/interview-coach) | 1.0.0；未声明许可证 | 重新表述题型分层、出题依据、难度、追问、红线、BEI/情景题和真实性规则 | 未复制原文、`.env`、外部OCR、自动依赖安装和简历改写模式 |

## 完整包文件盘点

| 来源 | 下载包内文件 | 处理结果 |
|---|---|---|
| 30天学习计划制定师 | `SKILL.md`、`references/plan-templates.md`、`skill-card.md`、`_meta.json` | 全部读取；`plan-templates.md`仅列四种类型且标注待补充，因此没有可复制细节 |
| 中国健身计划生成器 | `SKILL.md`、`README.md`、`LICENSE.md`、`_meta.json` | 全部读取；上游没有scripts或references |
| 求职全流程教练 | `SKILL.md`、`_meta.json` | 全部读取；SKILL提到的三个references未包含在下载包中，未假装吸收缺失文件 |
| JD＋简历→面试题预测助手 | `SKILL.md`、`generate_questions.py`、`parse_file.py`、`skill-card.md`、`_meta.json` | 全部读取；生成脚本中的问题结构已写入本地面试规则 |
| 面试助手 | `SKILL.md`、`references/question-types.md`、`references/resume-optimization.md`、`scripts/parse_input.py`、`.env`、`_meta.json` | 全部读取；未声明许可证的文字只提炼方法并重新表达 |

## 本地落点

| 上游内容 | 本地文件 |
|---|---|
| 学习五步流程、考前模式和任务规范 | `study-prep.md` |
| 健身目标、训练、递进、自检和风险边界 | `fitness-fat-loss.md` |
| 职业全流程阶段、岗位定位、JD抽样、材料、投递、面试、Offer和入职计划 | `job-search-interview.md` |
| `generate_questions.py`的题目组合与`question-types.md`的题型方法 | `interview-question-design.md` |
| 面试题包的字段、题量、重复题和类型覆盖检查 | `scripts/validate_interview_question_pack.py` |

## 脚本处理

- 元宝已有 `read`、`pdf`、`docx` 和图片理解能力，不需要重复的文件解析脚本。
- `interview-coach/scripts/parse_input.py` 会在运行时自动安装依赖；图片和扫描PDF还会把文件发送到PaddleOCR服务，因此不复制。
- `jd-interview-prep/parse_file.py` 与现有文件工具重复，因此不复制。
- `jd-interview-prep/generate_questions.py` 本质是“固定提示词 + 外部模型调用”，默认端点为DeepSeek，会发送简历与JD。其问题结构和输出契约已经本地化，不保留外发代码。
- 新增 `scripts/validate_interview_question_pack.py`，只做本地JSON结构校验，不联网、不读取PDF/DOCX、不发送简历或JD。

## MIT许可证声明

`fitness-plan-cn`：

Copyright (c) 2026 ikun

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files, to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies, and to permit persons to whom the Software is furnished to do so, subject to inclusion of this copyright and permission notice.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

`job-hunting-coach`：

The source declares the MIT license and author Klesen. The adapted planning rules retain this attribution; no original executable code is included.

`xiaozhi-learning-plan` 与 `jd-interview-prep`：

两份Skill的`skill-card.md`声明MIT-0。当前Skill保留来源链接和改写说明；未引入外部模型调用代码。
