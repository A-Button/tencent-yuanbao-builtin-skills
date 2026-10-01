# 八字分析规范

本文件维护八字的事实范围、解释方法与输出表达。公共语气见 [chart-language.md](chart-language.md)，链路写法见下方“输出表达”。普通分析只用本方法；报告的候选与正文契约分别由流水线在对应阶段返回，不提前读取。

## 可用事实

只使用去身份化分析盘中真实存在的路径；显式 `conclusion|analysis` 的新排盘读取 `analysis_charts.bazi` 指向的文件，深度报告或旧盘流程读取报告目录中的 `analysis-chart.json`。普通 `chart|null` 不读取本文件：

- `chart.pillars`
- `chart.details.day_master`
- `chart.details.heavenly_stems`
- `chart.details.earthly_branches`
- `chart.details.hidden_stems`
- `chart.details.ten_gods`
- `chart.details.twelve_growth_stages`
- `chart.details.element_counts`
- `chart.details.stem_relations`
- `chart.details.branch_relations`
- `chart.details.previous_jie`、`next_jie`
- `chart.details.luck_cycle_focus`，只用于用户明确请求的当前阶段分析或报告第二阶段 `timing`；报告候选不引用

时辰范围盘使用 `analysis_mode=time_range_stable_facts`：四柱全部稳定时可使用脚本提供的完整 `pillars/details`；否则只使用 `chart.stable.*`，不选取候选柱。时辰明确不等于分钟明确，不补算精确起运。

日期级初盘只解释 `chart.stable`。只有 `chart.stable.pillars.month` 存在时才可生成行为判断；月柱不稳定时，明确请求的结论或分析只说明精度边界，不写主轴、关键张力、性格或现实表现。不得根据柱值自行推导输入中缺失的十神、旺衰、格局、藏干、关系或其他事实。

## 按需结论与分析

规则：

- `conclusion` 用一至两句直接回答，通常 60—120 个可见汉字，不强求长度。“主轴”和“关键张力”只用于选材，不作为可见标签；稳定事实不足时缩为一句，不用套话补足。
- `analysis` 直接按下方解释方法展开 2—4 个与问题相关的发现，不先生成或复述一份 `conclusion`。
- `conclusion` 不解释术语、不复述四柱、不罗列五行、不写行动建议，也不展开事业、情感等生活领域。`analysis` 只展开用户明确提出的问题，并遵循下方解释方法。两者都不谈不存在于分析盘中的大运、流年或阶段预测。
- 精确盘只使用去身份化分析盘中 1—3 个真实信号支撑每条判断，但不向用户展示盘面路径。日期级只读取 `chart.stable.*` 和 `chart.uncertainty` 的变量柱名称与候选数量；分析盘不提供 `chart.possible` 候选值。若稳定月柱缺失，精度说明就是全部回答，不用年柱、日柱或日主补写行为判断。
- 去身份化准备失败时仍交付已验证 HTML，不回读原始出生资料补写解释，也不追加用户问题。
- 用户明确要深度报告时不生成前置速览；HTML 展示后直接进入报告主题和两阶段流水线。

## 解释方法

1. 先按 [bazi-judgment.md](bazi-judgment.md) 综合月令、根气、生扶耗泄和结构关系，找出一个主轴与一个最重要的矛盾。
2. 四柱、藏干、十神、长生和干支关系是传统解释信号；不要只数五行、只看纳音，或把合冲刑害直接写成吉凶与现实事件。
3. 普通分析只展开 2—4 个与用户问题直接相关的发现，不依次介绍全部十神、五行或柱位。
4. 专业词只在有助理解时出现，并立即翻译成可观察的偏好、反应或取舍。
5. 普通结论或分析只在用户明确问当前阶段时使用 `luck_cycle_focus`；深度报告的阶段解释由第二阶段 `timing_contract` 约束。两者都不自行挑选完整大运列表，也不补造流年。

低风险解释可以直接进入内容，但应保留适用条件，不声称已经知道用户的表现。信号不足的内容直接省略。通用安全边界遵循 [safety.md](safety.md)，不在报告中重复展开检查过程。

## 输出表达

- 一句结论：先用一句日常语言概括最相关的做事偏好或取舍；需要时再补一句条件。不用“主轴、关键张力、命格层次”等标签开头，也不先引用古籍定性。
- 普通分析：按用户问题选二至四点，每点概括清楚，再用具体场景解释。展开可以温和细致，让用户理解某种反应何时会出现；不从盘面编造已经发生的工作、家庭或关系经历。
- 深度报告：`claim` 和 `overview` 的概括句平实简短；`manifestation` 与 `insights` 用日常表现展开。`cost_or_contrast` 写真实适用条件或另一种表现，不强凑反转。`takeaways` 以可对照观察点为主，求助或具体困扰才给建议。
- 大运：首句说明当前可解释的阶段主题，再解释与原局的联系；条件分支同样展开，不替用户选边。不可用说明由脚本生成，模型不补写。

术语有助理解时再出现；解释中可以保留必要的温度，不把“克制”误读为省略原因。原文引用按需使用 [原文与出处](source-registry.md#原文与出处)，不能用一句古籍代替对当前盘面的解释。
