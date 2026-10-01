# IPIP 量表与计分契约

## 量表

- `quick`：Mini-IPIP-20，每项人格维度 4 题，题库为 `scripts/mini_ipip_items.json`。
- `deep`：IPIP-50 Big-Five Factor Markers，每项 10 题，题库为 `scripts/ipip_big_five_50_items.json`。

两套英文题目均来自 IPIP 公有领域资源，允许商业使用。简体中文是项目试译，不得称为发布方认可或完成本地心理测量验证的正式中文版。第五项保留 `Intellect/Imagination` 的含义，中文称“智性与想象”。IPIP-50 的情绪稳定性题在展示时统一转向为情绪敏感性。

## 确定性计分

每题按 1—5 作答：

- 正向题：`keyed = response`
- 反向题：`keyed = 6 - response`

各维度分别求总分和原始均值。Quick 总分范围 4—20，Deep 为 10—50，均值范围均为 1—5。无目标人群常模时，只展示本次原始均值和同次测量内的相对图谱，不输出人口百分位、准确率、概率或置信度。

四轴映射固定为：

- 外向性 → E / I
- 智性与想象 → N / S
- 宜人性 → F / T
- 尽责性 → J / P

情绪敏感性不参与四字母映射。高侧百分比采用精确整数有理数并按 `ROUND_HALF_UP` 取整：

```text
high = round_half_up((sum - item_count_per_trait) × 100 / (4 × item_count_per_trait))
low = 100 - high
```

字母直接比较总分与 `3 × item_count_per_trait`：高于中点取高侧字母，低于中点取低侧字母，正好中点显示 `X`。显示百分比的取整不得反向决定字母。

只有所有原始答案完全相同才标记 `straight_lining`。该状态仍可展示五项图谱，但不得输出四字母类型、常见称呼或深度人格结论。

## 展示边界

完整四字母代码可从 `scripts/mbti_type_labels.json` 读取一个大众常见的简中称呼；这些称呼不是 Myers-Briggs 官方名称或固定身份。不得生成认知功能堆栈，也不得加入 16Personalities 的 A/T 第五轴。

结果底部显示：`题目基于IPIP公开国际人格测试题目池选取；测试结果不宜作为任一诊断依据。`

需要核验来源或许可时只读取 [sources-personality.md](sources-personality.md)。
