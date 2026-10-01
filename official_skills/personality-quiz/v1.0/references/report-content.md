# 报告第二阶段：结构化正文

只在 `content_required` 时读取。用返回的 `validated_hypotheses` 扩写正文，写入 `next_input`；不回读原始出生资料。仅当 `timing_contract.required=true` 时读取其中的 `analysis_chart`，只用于 `timing`。

把正文写入第一阶段返回的 `next_input`。下面是模型负责填写的固定输入结构；系统字段由脚本在组装时注入：

```json
{
  "overview": {
    "hypothesis_ids": ["h1"],
    "paragraphs": [{"text": "一个总体判断。", "highlights": ["总体判断"]}]
  },
  "insights": [
    {
      "hypothesis_id": "h1",
      "paragraphs": [{"text": "一个可观察的现实表现。", "highlights": ["现实表现"]}]
    }
  ],
  "timing": {
    "paragraphs": [{"text": "当前大运与原局互动形成的阶段分析。", "highlights": ["阶段分析"]}],
    "signal_paths": [
      "chart.details.luck_cycle_focus.cycle.stem.ten_god",
      "chart.details.day_master.stem"
    ]
  },
  "takeaways": ["一个可用实际表现对照的观察点；有具体困扰时可写对应建议。"]
}
```

规则：

- `overview.hypothesis_ids` 引用 1—3 个不重复入选候选；每条 `insight.hypothesis_id` 只能引用入选候选。
- `overview`、普通 `insights` 与 `takeaways` 只扩写已验证的原局候选；`luck_cycle_focus` 只用于 `timing`，不得让其中任一匿名分支渗入性格或用户主题并写成确定结论。
- `overview` 只根据已入选候选和用户主题生成，保持脱离聊天也能独立阅读；不得假设盘面后已经存在任何前置速览或普通分析。
- 不要抄写 `schema_version`、`chart_system`、`primary_topics`、`insight.topic` 或候选 `claim`；脚本从冻结配置与候选中注入前四项，`claim` 只保留在候选文件中。
- `insights` 按 `selected_ids` 顺序使用全部入选候选；每项只需写 `hypothesis_id` 和 `paragraphs`。
- `paragraphs[].text` 每项只写一个观点；`highlights` 为零至一个在原文中恰好出现一次的短语。所有用户可见文本只写单段纯文本，不得包含 Markdown 链接、图片或反引号代码。
- 每条 insight 使用 1—3 个短段；主题越多，每条越短，但不得遗漏任何已选主题。
- `takeaways` 使用 1—3 条可对照的观察点，例如“计划变化后，通常是先确认安排，还是先表达不满”。用户明确求助或提供具体困扰时才写对应的低风险建议；不强制行动清单，不复述正文，不调用工具要求作答。
- `timing` 仅在返回的 `timing_contract.required=true` 时填写，结构为上例的 `paragraphs` 与 `signal_paths`；遵守当前状态的 `instruction`。大运事实只进入本模块，不进入 `overview/insights/takeaways`，不抄写状态、分支或不可用原因。
- 大运不是 `primary_topics` 或第十个用户主题；不可用说明和章节位置由脚本处理，不增加第三次模型调用。
- 默认省略称谓，不写姓名、出生资料、职业履历、公司、成就、婚史、资产或过去事件。

完成后执行返回的 `next_command`：

```bash
python3 scripts/report_pipeline.py finalize <report_dir>
```

该命令依次完成正文校验、Markdown 装配和 HTML 渲染；全部通过后才发布 `report.html`，失败不交付半成品。Markdown 结构由确定性装配器保证，独立 Markdown 校验器只留给离线审计，不在生产链重复运行。结构、盘面路径、主题一致性、身份字段 allowlist 与已知词法门控不通过是硬错误；篇幅、段长、重点位置和文风 lint 只返回 warning，不触发模型返工。语义安全仍须遵循 `safety.md`，不声称脚本能完整判断这一层。

