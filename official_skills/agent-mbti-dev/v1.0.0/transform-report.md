# agent-mbti 改造报告

| 项目 | 值 |
|------|-----|
| slug | agent-mbti |
| 类型 | 纯提示词 + JSON/MD 参考 |
| 评估结论 | 🟢 完全兼容 |

## 改动点

1. 剥离 SKILL.md front matter，移除付费功能说明
2. 参考文件移至 `references/`（survey-free.json、user-survey-free.json、personality-types.md、scoring.md）
3. 删除 `_meta.json`，生成 `skill.yaml`（binding_tools: []）

## 已知限制

- 无脚本，模型直接按 SKILL.md 流程执行问卷和诊断
