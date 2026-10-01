---
name: personality-quiz
description: 用于用户了解自己的 MBTI 或人格倾向、进行人格测试或结果解读，探索星座性格、相处方式或 MBTI × 星座趣味对照；也支持塔罗抽牌与牌意解读，结合出生信息占卜、算命或生成八字/西洋星盘及分析、深度报告，轻量每日运势、相关体系知识与比较，以及用户提供的紫微、印度占星等盘面解读。按上述意图触发，不要求用户明确说“测试、抽牌、排盘”；面相、手相相关意图（包括看相、掌纹解读及相关知识问答）不触发；普通写作、翻译、泛心理咨询，或只顺带提及性格、星座时不触发。
---

# Personality Quiz

按用户意图选择一个主路由，只读取命中的入口；后续材料按当前阶段加载，脚本源码和页面维护规范不进入正常执行路径。

| 路由 | 何时使用 | 执行入口 |
|---|---|---|
| `personality` | 开始人格测试、解释已有四字母或连续分数、人格知识；已有结果不强迫重测 | [personality.md](references/personality.md) |
| `zodiac` | 星座性格、相处方式或 MBTI × 星座轻量对照；不因提到生日自动排盘 | [zodiac-personality.md](references/zodiac-personality.md) |
| `tarot` | 新抽牌或解释已有牌面；已有牌面不重抽 | [tarot.md](references/tarot.md) |
| `chart` | 结合出生信息占卜、算命，新排或复算 `bazi\|western\|combined`；解释本 Skill 已验证盘面 | 新排盘读 [chart-flow.md](references/chart-flow.md)，运行 `chart_quick.py`；已有盘面只读 [output-levels.md](references/output-levels.md) |
| `imported` | 第三方或既有八字、西占、紫微、吠陀等盘面，未要求复算 | [imported-chart.md](references/imported-chart.md) |
| `knowledge` | 不需个人计算的概念、历史、流派或体系比较；人格和星座标签知识仍用各自入口 | 直接回答；需要精确出处时读 [source-registry.md](references/source-registry.md) |
| `entertainment` | 明确要求今日灵感、每日趣味运势等日期化低风险内容 | [safety.md](references/safety.md)；不收集出生资料、不冒充个人排盘预测 |

已有外部盘面优先 `imported`，明确复算才转 `chart`。仅自述太阳／月亮／上升标签不等于经过核验的完整盘面。主路由确实无法判断时，才读 [clarification-contract.md](references/clarification-contract.md)；资料足够直接执行。

新排盘读取入口后，先把原始出生字段交给 `chart_quick.py`，再按返回动作继续。八字固定使用出生地民用钟表时间、午夜换日；不做真太阳时校正、不转成北京时间、不先手算干支，也不为基础四柱追问性别。用户明确要求其他时间口径时说明当前能力边界，不擅自替换其要求。

明确的出生起止时间或时辰在八字、西占和组合盘中均原样进入范围核验，不替换为中点或整日。范围内稳定项正常展示和解释，只有真正跨界的项目显示候选；上升也遵守此规则。

## 事实与表达

个性化模型解释前读取 [safety.md](references/safety.md)；确定性页面构建不增加模型检查。区分引擎／来源事实、传统或象征解释与低风险可逆建议。不得手算或补造盘面事实、把结果写成现实履历、固定本质、科学预测或诊断；不得要求用户填写 IANA 时区或经纬度。

原文、页码、流派考据或资料冲突才查来源表，单体系只读匹配的一张。星座轻解读用其入口的简短说明；其余传统文化模型结果结尾保留：

`AI生成内容｜传统文化与自我反思，仅供参考，不是经科学验证的预测，也不构成医疗、法律、投资或其他专业建议。`

## 文件交付

生产脚本已经把页面写到宿主能收取的位置并返回绝对路径。不改写 HTML，不自己挑目录，不把产物移到别处，也不传 `--output` 指向脚本给出的路径之外。脚本返回 `ok: false` 时把 JSON 原样停住，不要改 skill 脚本、不要写兼容包装、不要手动复制或重命名产物。

先看返回的 `delivery.ok`：

- `false`：只转述 `delivery.message`。不能说页面已生成、已附上，也不能让用户去打开。
- `true`：先写一两句说明，把 `media_info` 原样贴到正文之后，写入草稿后必须运行返回的 `verify_command`。该命令会检查文件还在、没有超过宿主 2MB 附件上限、回复里确实含有同一段 `media_info`。退出码非 0 则不得发出完成态回复。

```
python3 scripts/verify_html_delivery.py --html "<output>" --reply-file <本轮回复草稿>
```

没有通过这道门就等于没交付。贴出路径文本、源码预览或 Markdown 链接都不算交付。

盘面先交付，交付后必须执行 `after_delivery.next_command`，不能在只发出盘面后提前结束。返回 `ask_report_topics` 时优先调用宿主真实的 `ask-user-question`，一次可跳过多选；用户选择后复用原盘生成深报。宿主明确要求交付为本轮最后一次动作时，保留 `followup_session` 到下一可交互时机续接，不视为跳过；产出失败不进入分析或报告。

出生资料、盘面 JSON 与报告中间件留在生产入口自建的私有目录，不进 `<media_info>`。需要手工写入输入文件的流程先用 `secure_run_dir.py create`；脚本返回 `cleanup_command` 时才需要清理，且要等产物不再被消费，宿主管理的目录交由宿主回收。

分享卡仅在用户明确要求或宿主已启用自动策略时读取 [share-card.md](references/share-card.md)，不改变主结论。
