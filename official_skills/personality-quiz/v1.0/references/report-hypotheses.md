# 分析候选池

只在 `hypotheses_required` 时读取；使用返回的 `chart_system`、`primary_topics` 和 `analysis_chart`。

先提出候选，再筛选。保留与问题相关、有盘面信号、能用具体表现说明的解释，剔除套话和传记联想。表达使用 [chart-language.md](chart-language.md) 和对应体系 reference 中的输出表达，候选数量与事实范围在本文件维护。

## JSON 结构

```json
{
  "schema_version": "2.0.0",
  "chart_system": "bazi",
  "primary_topics": ["career"],
  "candidates": [
    {
      "id": "h1",
      "topic": "personality",
      "claim": "一句低风险、具体、有适用条件的判断",
      "manifestation": "一个可观察的偏好、反应、取舍或高频场景",
      "cost_or_contrast": "这一表现的适用条件、局限或另一种可能表现",
      "signal_paths": [
        "chart.details.ten_gods.heavenly_stems.month",
        "chart.details.twelve_growth_stages.month"
      ]
    }
  ],
  "selected_ids": ["h1", "h4", "h7"]
}
```

## 筛选

- 候选池至少覆盖 `personality` 和所有用户关注主题。建议数量为 `max(8, 主题数 × 2 + 2)` 至 `max(12, 主题数 × 2 + 2)`；数量只作本地 warning，不追加生成回合。
- 一个主题时选择性格 1—2 条、该主题 2—3 条；两个主题时只保留性格 1 条，每个主题 1—2 条；三个及以上主题时保留性格 1 条、每个主题各 1 条，确保用户自由多选后没有主题被丢弃。
- 直接选择与盘面结构一致、与用户主题相关、具体且能由现实经验判断像或不像的候选；不要输出自评分或选择说明。
- `signal_paths` 是盘面信号来源，不叫“证据”。每条候选使用 1—4 条真实路径；一个强主信号即可提出候选，不为了凑两个家族虚构现实桥梁。
- 第一阶段候选只使用原局事实，不得引用 `chart.details.luck_cycle_focus`。大运事实保留给第二阶段专属 `timing` 模块，尤其不得把匿名条件分支悄悄写进性格或用户主题候选。
- 若一句话换到结构相反的命盘仍大概率成立，判为通用度高并淘汰。
- 若结论依赖具体行业、公司、作品、知名事件或公众人物标签，判为传记风险并淘汰。
- 若同一主题有多条近义判断，只留最具体、最能被用户回答“像/不像”的一条。

### 出生时段范围盘

当 `analysis_mode=time_range_stable_facts` 时，八字完整 `chart.pillars` 存在表示四柱在范围内一致，可引用该盘已提供的具体 `pillars/details` 路径；否则 `signal_paths` 只能引用 `chart.stable.*`。西占只引用稳定的太阳、月亮、金星、水星星座及实际存在的 `chart.stable.ascendant.sign`；稳定上升正常参与解释，不因输入是范围而省略。真正跨界的项目不挑选候选，也不补造缺失字段或分钟精度；精确起运不进入候选。

### 日期级初盘

当 `analysis_mode=date_only_stable_facts` 时，`signal_paths` 只能引用 `chart.stable.*`。`chart.possible.*` 只用于向用户说明范围，不能被候选选择为某个确定分支；时柱、上升点、宫位、精确度数、时间敏感相位和大运起点均不得进入候选。若稳定字段不足以支持具体判断，减少候选或降级产物，不要求用户补交已选择保密的信息。

## 选材范围

优先写与用户问题相关的做事偏好、压力下的反应、互动方式和具体取舍。没有用户情境时保持条件表达，不推断隐藏动机，不排序所谓真实欲望，也不强行为每个优点搭配一个缺点。

表达示例放在相应 reference 的输出表达段中，不能作为当前盘面的信号或直接套用的候选。

## 提交

写入返回的 `next_input` 后执行 `next_command`，即 `python3 scripts/report_pipeline.py validate-hypotheses <report_dir>`。只有通过后才读取下一阶段契约，不提前加载正文或呈现规范。
