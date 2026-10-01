# 盘面交付后的产物

明确产物优先：已有问题或主题只确定内容范围，不把普通分析或只要盘面升级为报告。新排盘按 `after_delivery` 继续；已有本 Skill 盘面复用当前文件，不重算。下面各分支只读取当前需要的材料。

| 层级 | 当前动作 |
|---|---|
| `chart` | 只展示确定性 HTML，不自动生成速览或快速解读；脚本返回的报告主题入口可跳过 |
| `conclusion` | 展示成功后用一至两句回答，不另写前置速览 |
| `analysis` | 展示成功后直接展开 2—4 个相关发现和必要限制；明确求助或有具体困扰时才给建议 |
| `report` | 用户明确要求深报，或在盘后选择主题时启动下面的两阶段流水线；不另写聊天长报告 |

## 结论／普通分析

只读取当前去身份化分析盘和对应的 [八字](bazi-report.md) 或 [西占](western-report.md) 方法，以及 [chart-language.md](chart-language.md)、[safety.md](safety.md)。不加载报告候选或正文 Schema。事实不足就缩小内容，缺失字段不推导补齐。

新盘复用 `artifacts.analysis_charts`，不另跑准备命令。旧盘／导入盘才用 `prepare_analysis_chart.py <chart.json> --output <私有目录>/analysis-chart.json`；明确要求当前大运的八字分析另加 `--current-luck-cycle`。准备失败不回读原始出生资料补写解释。

## 报告启动

新排盘优先由 `chart_followup.py` 处理盘面展示后的主题选择与报告准备；返回 `continue_reports` 时报告目录已经建立，直接使用其中的阶段响应，不再运行 prepare。提问工具与续接契约见 [chart-flow.md](chart-flow.md#一次主题选择直接接报告)。已有问题／主题直接映射；明确“整体／全面报告”取全部九项。需要映射时读 [topic-selection.md](topic-selection.md)。旧盘没有续接状态时，才用下面的手动启动命令。仅缺主题时，优先调用真实 `ask-user-question`，一次可跳过的不限多选同时推荐并收集主题；不先询问“是否需要报告”，不在盘面展示前提问。

主题选择任意项继续，跳过结束；不把未作答当作默认同意。`<selected_chart_json>` 是当前已验证的体系 JSON；`<report_dir>` 是其私有目录内尚不存在的新子目录。多个主题重复 `--topic`：

```bash
python3 scripts/report_pipeline.py prepare <selected_chart_json> \
  --report-dir <report_dir> --topic career
```

八字深报默认在原局之后、关注主题之前包含大运模块，不再询问“是否看大运”，不要求用户提供性别或选择匿名分支。只有用户明确拒绝大运才加 `--omit-luck-cycle`；未提及不等于拒绝。日期级／时间基础不支持时由脚本显示固定不可用边界，其余报告继续。西占不适用该模块。

西占深报的 prepare 只投影太阳、上升、月亮、金星、水星的已确定星座，按星座页配色渲染；原始十天体 JSON 不改动。候选范围不进入报告事实，未知上升不补齐。五项是取材范围，不强制每个主题重复讲五遍。

脚本返回 `next_references`、`next_input` 和 `next_command`。只读取当前 `next_references` 中尚未加载的文档及返回的去身份化数据，写入 `next_input` 后执行 `next_command`，无需重新判断下一步骤：

1. `hypotheses_required`：生成一次候选，运行 `validate-hypotheses`。
2. `content_required`：用已验证候选生成一次正文，运行 `finalize`。
3. `complete`：仅当 `delivery.ok` 为 true，把返回的 `media_info` 贴进草稿并运行 `verify_command`。没有通过就不算交付，不能说报告已生成。

两次计划内语义生成之外，不增加规划、评分、速览或润色调用。硬错误只按具体字段修正，warning 不触发返工。标题、章节、Markdown 与 HTML 全部由脚本确定；维护呈现才读 [report-presentation.md](report-presentation.md)。

组合盘的八字与西占各自使用独立报告目录，分别交付，不跨体系或 revision 混用；没有统一比较报告 Schema。用户明确要比较时，在两份已验证结论之上做简短聊天对照。
