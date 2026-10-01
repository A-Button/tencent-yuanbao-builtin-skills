# 输出合同与文件隔离

用户指定格式优先；以下为本Skill默认。全部原始消息使用user/assistant及文本part；除非另有要求，不添加system/tool、工具轨迹、作者解释或评分标签。

## 同一JSON中的多Session

顶层必须是数组，无外层metadata对象。每个Session结构如下（示例只有两条消息，不代表目标长度）：

```json
[
  {
    "session_id": "thread-synthetic-example-01",
    "uid": "test1-uid",
    "session_date": "2027-07-12",
    "history_messages": [
      {
        "role": "user",
        "part": [{"type": "TEXT", "text": {"text": "先把现在的方案给我看看，别只写个标题。"}}],
        "index": 1
      },
      {
        "role": "assistant",
        "part": [{"type": "TEXT", "text": {"text": "这里应填写完整的助手回复，而不是交付物占位句。"}}],
        "index": 2
      }
    ]
  }
]
```

- `session_id`每段唯一，在后续引用中保持稳定；不必依赖UUID工具，但不能复制同一ID到多段。
- 单用户剧本所有`uid`一致；多用户场景须事先明确，不擅自增加人物对应的用户账号。
- `session_date`为故事内日期，不是创作日期；只需要日期时不加每条消息时间。
- `index`从1开始、每Session重新计数，连续无重复。引用以`session_id + index`定位。
- 多个TEXT part时按顺序阅读；不要把评分点或隐藏设定放进额外part。
- 留出Session只有一条user消息、index=1，不附assistant、答案提示或预期调用轨迹。

## 默认交付文件

同一版本目录中存放：

1. `OUTLINE.md`：先保存的大纲，含输入来源、Session设计、长度和假设。
2. `sessions.json`：完整历史 + 最后的留出Session，用于人审。
3. `history-only.json`：精确投影历史Session，排除留出Session，作为记忆构建候选输入。
4. `question-only.json`：同一schema，只含留出Session，供回答阶段使用。
5. `conversation-review.md`：逐Session、日期、index的完整明文，不能用摘要替代长回复。
6. `REPORT.md`：生成统计、Skill依据、两列rubrics主表、证据和更新关系、未验证项。
7. `judge-rubrics.json`：评分项与证据的机器可读版本；不进入记忆或回答阶段。
8. `manifest.json`：版本、合成声明、作者设定、输入材料来源、历史/留出ID清单、计量结果与校验状态。文件Hash只在实际计算后记录。
9. `REVIEW.md`：按review-and-repair.md执行的自审结果、问题定位、返修轮次与剩余风险。修订已有样本时可兼容使用`REVISION-REVIEW.md`，交付时指明实际文件，不强制复制两份相同报告。

最终交付必须包含与最终JSON同版本的完整`conversation-review.md`供用户审阅。返修影响消息时同步重建明文、题目映射、Rubric引用、统计和Hash；不能只改JSON或只改明文。自审通过标记`pending_user_review`，不写成正式题库已准入。

不要求生成代码或可执行脚本。若环境支持、用户希望下载，可打包上述文件；不把原始私人附件、凭证或真实日志一起塞入包。

### 分支/干扰与多个问题的扩展

原始消息schema不变，作者侧分类不加入TEXT或额外模型可见字段。有分支/干扰时，在大纲、报告或独立作者台账记录事件类型、Session/消息范围与问题/rubric映射；不强制为每个简单样本增加独立文件。

多个留出问题时提供`TASK-MAP.json`或等价的明确清单：每题ID、问题Session、允许历史Session ID集合与文件、截止日期、rubric归属；文件名可随用户约定调整。分别导出每题的无问题历史与单条问题，避免把全部问题和后续桥接当成一条线性历史。共有历史可以复用同一文件。

人审全集可按日期排列，但必须标明不能直接用于Memory build。后续桥接只进入相应后续题的历史，不包含其他留出题的模型答案。截止内的干扰Session保留在候选记忆输入中，不提前按相关性剔除。

## 追溯与修订

创建新目录/版本，保留已交付历史产物。大纲先于详细对话保存。修订改变规模、人物或结尾考点时，写明与确认大纲的差异，必要时重新确认，不能悄悄重定义题目。

报告写明创作日期、故事日期、使用的Skill材料名称/版本与来源、用户确认依据。没有时间戳或Hash能力时只记录能验证的信息，不编造精确审计字段。

在`manifest`记录：历史Session与留出Session数、每段用户/助手消息数、正文字符数、单条助手最大长度、最低长度是否满足、token是否真正测量、JSON是否实际解析、rubric证据是否检查。未知写`not_measured`/`not_run`，不要写`passed`。

单问题交付前确认：`sessions.json = history-only.json + question-only.json`（按原顺序）。多问题时逐题验证其组合等于指定历史加该题单条user；检查题目互不污染、未来状态不倒流、干扰按时间范围保留。所有rubric引用都必须存在于该题允许的最终历史，而非过期底稿或另一题答案。

## 无文件工具时

按相同逻辑分段提供内容，并说明尚未落盘。不要以缺少外部服务为由拒绝纯写作；但也不要假装已创建下载包或自动校验。若一轮容纳不下约定规模，保存/输出明确检查点、已完成范围与待生成Session，不能交付省略号冒充全量完成。
