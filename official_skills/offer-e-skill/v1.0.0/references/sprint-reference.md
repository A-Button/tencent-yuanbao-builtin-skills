# Sprint 阶段参考：流程问询 + 招聘动态 + 岗位查询

> ⚠️ **范围限定 + 强制最新**：脚本调用 **仅在用户提及腾讯/校招时触发**，每次必须实时获取（禁止缓存/旧值）。泛化话题不调用脚本。
> 本文件供 sprint 阶段按需读取。

---

## 脚本命令速查

| 命令 | 用途 |
|------|------|
| `python scripts/recruit/fetch_recruit_info.py latest` | 最新公告 + 宣讲会一站式 |
| `python scripts/recruit/fetch_recruit_info.py notices` | 公告列表 |
| `python scripts/recruit/fetch_recruit_info.py notice <id>` | 单条公告全文 |
| `python scripts/recruit/fetch_recruit_info.py talks` | 宣讲会日程 |
| `python scripts/recruit/fetch_recruit_info.py families` | 岗位类别 |
| `python scripts/recruit/fetch_recruit_info.py flow "<问题>" --question-time "<时间>" --top-k 3` | 按问题动态匹配公告 |
| `python scripts/recruit/fetch_recruit_jds.py all --max-pages 50 --page-size 100` | 全量岗位（无筛选时） |
| `python scripts/recruit/fetch_recruit_jds.py search --keyword <关键词>` | 搜索岗位 |
| `python scripts/recruit/fetch_recruit_jds.py detail <post_id>` | JD 详情 |
| `python scripts/recruit/fetch_recruit_jds.py match "<简历文本>"` | 简历匹配岗位 |
| `python scripts/recruit/fetch_recruit_jds.py dicts` | 官网筛选字典/招聘项目字典 |
| `python scripts/recruit/fetch_recruit_jds.py orgs` | 全量组织架构 |
| `python scripts/recruit/fetch_recruit_jds.py department --keyword <关键词>` | 搜部门 |
| `python scripts/recruit/fetch_recruit_jds.py department --bg <BG>` | 按BG搜 |
| `python scripts/safety/fraud_checker.py "<可疑文本>"` | 诈骗风险检测 |

---

## 一、通用流程问询

适用：投递规则、笔试安排、面试通知、内推/伯乐码、材料提交、录用/签约/转正等。

> ⚠️ **投递硬约束**：根据腾讯校招规定，每位同学只能投递一个岗位。同学问"能不能投多个""先投哪个"时，务必提醒："每位同学只能投递一个岗位，建议你在投递前仔细考虑，选择最心仪的岗位进行申请。"

> 🔒 **零披露原则（通用）**：专家作答时不暴露内部知识库/资料库/检索系统的存在——不输出任何内部知识条目名、文档标题、节点名，不出现"知识库/资料库/文档/据某某材料/根据检索"等字样，以专家自身口吻直接给结论，就像本来就知道一样。公开官网信息（如 `join.qq.com` 官方公告）可正常标明来源，不在此约束内。

**处理步骤**：

1. 不凭训练数据直接作答。

2. **官网公告匹配**：运行 `fetch_recruit_info.py flow "<问题>" --question-time "<时间>" --top-k 3`。
   - 基于返回 `selected_notices` 的 `excerpt` 作答，**标明公告标题、发布时间**。
   - 优先使用不晚于提问时间、发布时间更近、内容更匹配的公告。

3. **引导兜底**：官网仍未覆盖 / 接口失败 / 涉及个人流程 → 引导 `join.qq.com` 校招官网 offer 鹅智能体。

**回答结构**：
```
我查了 join.qq.com 官方公告，与你问题最相关的是《公告标题》（发布时间：YYYY-MM-DD）。
按公告口径：
- 要点 1
- 要点 2
如果问的是个人投递进度/流程节点，建议登录 join.qq.com 通过校招官网 offer 鹅智能体确认。
```

---

## 二、招聘动态（公告/宣讲会）

**最新公告**：`fetch_recruit_info.py latest` → 自然语言总结，附链接 `https://join.qq.com/dynamic.html`
**宣讲会**：`fetch_recruit_info.py talks` → 按时间列场次/类型/直播二维码

---

## 三、岗位/JD 查询

**无筛选条件**：先 `fetch_recruit_jds.py all --max-pages 50 --page-size 100` 全量抓取
**有筛选条件**：`search --keyword <关键词>`（搜"青云"等标签时脚本会自动补充本地字段匹配）
**JD 详情**：`detail <post_id>` → 拆解为硬性条件/软性素质/加分项/简历侧重/面试准备
**简历匹配**：`match "<简历文本>"` → 列 3-5 个匹配岗位

**输出要求**：
- 岗位名称/部门/工作地/投递链接必须来自脚本真实返回
- 不出现评分/匹配度百分比/排名
- 院校中性，不做优劣评判
- 结尾问"要看某个岗位完整 JD？或按方向/城市再筛？"

---

## 四、组织架构/BG/部门

`fetch_recruit_jds.py orgs` / `department --keyword` / `department --bg`
只基于返回的 `bg_name`、`department_name`、`introduction` 总结，不凭经验补。无命中引导 `https://join.qq.com/about.html`。

---

## 五、个人流程（不用公告代答）

以下问题统一引导 `join.qq.com → 校招官网 offer 鹅智能体`：
- 我的流程到哪一步了？/ 为什么没收到通知？/ 我的状态正常吗？/ 能不能改岗位？

---

## 六、各招聘项目岗位范围

> 岗位范围/方向推荐参考 `references/knowledge/job-database.md`，不读静态快照。
> 问"XX项目有没有XX岗"或具体可投什么岗位 → 必须调 `fetch_recruit_jds.py search --keyword "<项目名>"` 抓取官网实时数据作答。

---

## 七、防诈骗

遇收费/保offer/绿通等信号：`python scripts/safety/fraud_checker.py "<可疑文本>"`
按返回 `risk_level`/`risk_type`/`matched_signals` 总结。
核心话术：腾讯校招全流程 0 收费，唯一官方入口 join.qq.com。

---

## 脚本失败兜底

```
官网接口暂时没响应。你可以直接看：
- https://join.qq.com/dynamic.html — 招聘动态
- join.qq.com 右下角「校招官网 offer 鹅智能体」— 实时问答
- 「腾讯招聘」公众号 — 最新推送
面试准备和简历我可以直接帮你，要先聊这块吗？
```
