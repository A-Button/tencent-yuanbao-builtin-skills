# 方式一：直接 Skill

这是一个 Script-backed Skill 示例。第三方直接交付 `SKILL.md` 和确定性脚本，不包含元宝管理的 `additional_tools.json`、根目录 `assets/`、`manifest.json` 或 `agents/openai.yaml`。

测试命令：

```bash
python3 scripts/calculate_summary.py examples/request.json
```

