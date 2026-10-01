---
name: wiki
description: "个人内容资料库的统一入口，负责解读或保存当前资料，以及查找、使用历史资料。当前支持公众号文章和可解析网页链接。用户只发一个链接时默认加载；用户想理解、总结、提炼、评价或比较资料本身，或明确要求保存、查找、使用历史资料时，也应加载。若资料只用于改写、翻译、创作、写报告或完成其他任务，且没有保存或调用历史资料的要求，则不要加载。"
---

# Wiki：个人内容的统一知识入口

`/data/library` 是该用户跨会话持久的个人内容资料库。本技能统一处理三类意图：**解读当前资料、保存当前资料、查找或使用历史资料**。单篇资料需要完整总结、历史对比和价值判断时，再读取 `content-digest` 参考文档。

**铁律：检索必须渐进式三阶段，不得跳步、不得合并、不得并行全库扫描**——先发现已有分类/标签分布，再据此筛选候选，最后才下钻读命中条目；同主题召回同样受此约束。细则见 §4。

## 1. 先判断类型和意图

必须先完成本节路由，再调用工具或读写资料库。

### 1.1 当前支持的内容类型

- 公众号文章链接；
- 可解析的公开网页文章链接。

上传文档、PDF、图片、音频、视频和 AI 产物当前暂不支持。这里只是一期能力范围，不是 wiki 的长期边界；未来增加类型时，扩展本节和 frontmatter description 的「当前支持」列表即可，解读 / 保存 / 查找三类意图不变。

普通网页是否为可解析文章，在 Fetch 后确认：正文为空，或只得到登录墙、打开 App 提示、错误页、导航、指标或不足以理解全文的残片，均视为不可解析。

### 1.2 选择唯一处理流程

按表格从上到下判断，命中后停止，不要同时进入多个主流程。

| 用户意图 | 处理流程 |
|---|---|
| 明确查找、追问或使用以前发过、存过、处理过的资料 | 走 §4「历史查询」；若还要完成任务，查到后继续完成，不进入单篇解读 |
| 明确只收藏 / 只存一下 / 不用总结，且只有一个链接 | 走 §5「静默保存」，不得读取 `content-digest` |
| 把单个当前链接用于其它任务，同时明确要求保存 | 完成用户任务，并走 §5「静默保存」；不得进入单篇解读或重复入库 |
| 总结、概括、提炼、评价或判断单篇资料，判断值不值得读，或与历史资料比较新增 / 重复 / 冲突 | 走 §6.1「单篇解读」，读取 [content-digest](./references/content-digest.md) 并严格执行 |
| 总结、比较或判断多篇当前资料，同时要求保存 | 走 §6.2「多资料解读」完成当次回答，但不入库；说明一期批量保存暂不支持 |
| 总结、比较、筛选或判断多篇当前资料本身 | 走 §6.2「多资料解读」，不得读取 `content-digest`，默认不入库 |
| 针对当前资料问一个具体问题，但不要求完整总结或阅读判断 | 读取当前资料后直接回答；除非用户同时明确要求保存，否则不入库 |
| 当前资料只用于改写、翻译、创作、写报告或完成其它具体任务 | 交回正常回答；不读写资料库，不读取 `content-digest` |
| 只发送一个受支持链接，没有附加要求 | 默认走 §6.1「单篇解读」 |
| 只发送多个链接，没有附加要求 | 不默认解读、不入库；交回正常回答，简短询问用户想总结、比较还是做其它事情 |
| 明确要求批量保存多个链接 | 一期不做批量入库；简洁说明当前仅支持逐条保存，请用户单独发送 |

混合意图只执行一次正确流程：调用历史资料时先查历史；单篇解读即使同时要求保存，也只走 §6.1，因为该流程默认完成一次入库；其它任务同时要求保存单个链接时，完成任务并走 §5；多资料解读同时要求保存时，只完成解读并说明一期不支持批量保存。

加载本技能不等于获准读写资料库。只有历史查询、单链接明确保存和 `content-digest` 的默认入库可以读写 `/data/library`；其它流程不得顺手入库。

## 2. 用户可见输出边界

只呈现用户需要的结果，不暴露内部判断和执行过程：

- 不展示路由名称、字段名、条目 id、内部路径、工具名、调用参数、检索命令或执行旁白；
- 引用历史内容时可展示文章标题和来源 URL，不展示 `ent_id`；
- 始终说「你之前存过 / 转给我处理过」，不说「你已经知道 / 已经看过」；
- 抓取或查询失败时只说明用户能理解的结果和下一步，不解释内部链路。

## 3. 知识层结构

```text
/data/library/
  raw/<id>/                # 原始层（不可变）：仅上传/AI 产物类才有，存 source.<ext> / content.md
  wiki/
    index.json             # 轻量结构化索引；查找入口
    log.md                 # 审计时间线
    entries/<id>.md        # 条目元数据、结构化要点和知识正文
```

链接类没有 `raw/<id>/` 目录，见下方留底规则。

沙箱启动时 `/data/library` 已建好完整结构，无需检查目录是否存在。

### type × source（内容形态 × 来源）

`type` 答「这是什么形态」，`source_kind` 答「哪来的」——两者独立。

| `type` | 含义 | 解析方式 |
|---|---|---|
| `article` | 图文内容：网页、公众号、AI 文字产物 | `web_fetch` 取正文 |
| `file` | 办公文件：ppt / word / excel / pdf 等 | 复用 `[user_doc_content]` |
| `image` | 图片（本地或 url） | 复用 `[user_image_description]` |
| `video` | 视频（本地或 url） | 留源、未解析 |
| `other` | 兜底 | 视情况 |

| `source_kind` | 含义 |
|---|---|
| `upload` | 用户上传的文件 |
| `url` | 链接来的 |
| `artifact` | AI 生成的产物 |

`status`：`parsed`（已解析出正文）/ `source_only`（仅留源、未解析）。

### 原始层留底规则

- **链接类**（`source_kind=url`）：`source_raw` 直接记录 URL；不创建 `raw/<id>/` 目录——链接本身就是原始来源，后续需要可重新 Fetch。
- **上传文件类**（file / image）：传 `source_file`（沙箱绝对路径），工具自动拷贝进 `raw/<id>/source.<ext>` 并把 `source_raw` 改写为该相对路径。
- **AI 产物**：有沙箱产物时同上传文件处理；纯文字产物同链接类，不留底。

### 条目 schema（entries/<id>.md frontmatter）

```yaml
id: ent_20260703_0007
title: 标题
type: article
status: parsed
source_kind: url
source_raw: https://...
category: 资讯
topicTags: [Claude, Opus 新版本]
summary: 一句话摘要
keyInsights:
  - text: Opus 4.8 诚实性评测首次满分。
    diff: added
    ref: ""
    group: ""
body: 知识正文，或由 content-digest 模板渲染的展示正文
```

### 3.1 category

从以下 7 类中选最贴切的一类：

| 大类 | 边界 |
|---|---|
| 健康 | 身体与心理健康、运动、饮食营养、睡眠、就医 |
| 学习 | 知识技能、读书、思维方法、自我成长、教育 |
| 关系 | 家庭、亲子、婚恋、社交、人际沟通 |
| 事业 | 工作、职业发展、创业、管理、理财投资 |
| 生活 | 衣食住行、休闲娱乐、兴趣爱好、旅行、消费 |
| 资讯 | 时事热点、行业动态、科技 · AI |
| 其他 | 无法归入以上类别 |

口径：理财投资 → 事业；科技 · AI → 资讯；情感 → 关系。

### 3.2 topicTags

生成 2–4 个主题 / 对象级标签，如「减脂」「Claude」「ETF 定投」。能复用已有标签就逐字复用，不造近义重复；太粗的「AI / 健身」归 category，太细的具体数字和结论归 keyInsights。

写入前先查看已有标签：

```bash
jq '[.[].topicTags[]] | unique' /data/library/wiki/index.json
```

### 3.3 keyInsights

每条为 `{text, diff, ref, group}`：

- `text`：自包含的一条知识要点；
- `diff`：`added` / `repeated` / `contradicted` / `""`；
- `ref`：`repeated` / `contradicted` 时填写真实命中的历史条目 id，其它情况可空；
- `group`：可选分组标题，无自然分组时留空。

同主题历史只作为内容关系基线，不代表用户已经理解。完全重复时仍应给重点速览，不得返回空内容。

## 4. 历史查询

历史查询优先使用知识层；只有知识层不足以回答时才重新 Fetch 来源 URL。

**必须渐进式三阶段检索，不得跳步、不得合并、不得并行全库扫描**：先 Step 1 发现，再 Step 2 筛选候选，最后才 Step 3 下钻读条目。凡涉及 `/data/library` 的检索都受此约束，同主题召回同样适用（见下）。

### Step 1：发现已有分类和标签（必做，且必须是第一条命令）

第一步只读取轻量索引结构，不读条目正文：

```bash
jq 'group_by(.category) | map({category: .[0].category, count: length}) | sort_by(-.count)' /data/library/wiki/index.json
jq '[.[].topicTags[]] | group_by(.) | map({tag: .[0], count: length}) | sort_by(-.count)' /data/library/wiki/index.json
```

禁止用 `cat` / `head` / `tail` 把完整 `index.json` 灌入上下文，也不要一开始就全库 grep `entries/`，也不得跳过本步直接进入 Step 2。

### Step 2：筛选候选

根据用户提到的标题、主题、作者、实体或 Step 1 发现的分类 / 标签，用 jq 只返回候选的轻量字段：

```bash
# 标题、摘要或标签中的关键词
jq '.[] | select(((.title + " " + .summary + " " + (.topicTags | join(" "))) | test("关键词"; "i"))) | {id, title, source_raw, category, topicTags, summary}' /data/library/wiki/index.json

# 已知来源 URL 时做身份查找
jq '.[] | select(.source_raw == "https://...") | {id, title, source_raw, category, topicTags, summary}' /data/library/wiki/index.json
```

无命中时才降级为：

```bash
grep -ril "关键词" /data/library/wiki/entries/
```

### Step 3：读取知识层并回答

只读取 Step 2 命中的 `wiki/entries/<id>.md`。先用其中的 `summary`、`keyInsights` 和 `body` 回答：

- 足以回答：直接作答，不 Fetch；
- 不足以回答且条目是 `source_kind=url`（`source_raw` 即来源 URL）：重新 Fetch 来源页面，补足本次回答；
- Fetch 结果只用于本次回答，不自动覆盖或更新旧条目；
- Fetch 失败：回答知识层能确认的部分，并说明原页面暂时无法重新读取；
- 未找到候选：直接说明资料库里暂未找到，不凭空引用历史内容。

引用来源使用文章标题 + URL；不得向用户展示内部 id。

### 同主题召回

`content-digest` 和静默保存需要判断历史关系时，**必须依次执行以上三步、不得跳过 Step 1、不得直接拿本篇 category/topicTags 去跳级筛选**：先 Step 1 发现已有分类和标签分布，再 Step 2 用当前内容的 category/topicTags 圈候选，读取命中条目的 `keyInsights`，再按语义判断真正同主题以及 `added/repeated/contradicted`。标签相同不等于同一主题；`ref` 只能来自真实命中。

## 5. 静默保存

只在用户明确要求保存单个链接、且本次不进入单篇解读时执行：

1. Fetch 链接，获取标题和足以理解全文的正文；不可解析时不入库，并简洁说明；
2. 静默生成 `summary`、`keyInsights`、`category`、`topicTags`；必要时按 §4 召回同主题历史并标关系；
3. 生成供以后查询使用的内部知识 `body`，内容由摘要和核心要点组成；
4. 调用一次 `wiki/ingest_entry`：传 `source_raw`（链接类填 URL）、`render_type=""` 和知识字段；
5. 只有保存意图时，成功只回复「已存进资料库了」；若同时还有其它任务，完成任务后简短说明已保存。不得展示工具返回的内部 `body`、摘要、要点、标签或条目 id。

最小调用示例：

```text
wiki/ingest_entry(
  title="Claude Opus 4.8 发布",
  source_raw="https://...",
  render_type="",
  category="资讯",
  topicTags=["Claude", "Opus 新版本"],
  summary="……",
  keyInsights=[{"text":"……","diff":"","ref":"","group":""}],
  body="……（内部知识正文）"
)
```

本流程生成知识层但不向用户展示总结；入库只表示「用户存过」，不代表用户已理解。

## 6. 当前资料解读

### 6.1 单篇解读

单篇资料命中 §1.2 的完整总结、阅读判断或历史对比后，立即用 `read` 工具读取：

`/data/skills/wiki/references/content-digest.md`

读取时提供必要的 `description`，不要先 `find` / `ls` 探路，也不要再次 `load_skill('wiki')`。进入 reference 后必须按其流程完成 Fetch、召回、字段判断和一次 `wiki/ingest_entry`，不得退化成普通总结。

工具参数使用 `render_type="content_digest"`。

### 6.2 多资料解读

只在用户明确要求理解或判断多篇当前资料本身时执行，例如分别总结、比较异同、筛选重点或判断哪篇值得读：

1. 逐篇 Fetch，只依据成功读取的正文回答；
2. 按用户问题完成当次总结、比较或判断，不套用单篇三段式模板；
3. 部分链接不可解析时，明确指出未读到哪些资料，不补写其观点；
4. 不读取 `content-digest`，不调用 `wiki/ingest_entry`，不创建合并条目，默认不入库。

若多个链接没有附加要求，交回正常回答询问用户意图；若用户明确要求批量保存，说明一期仅支持逐条保存。

## 7. 工具

- 取当前网页内容：`web_fetch(url=..., prompt="")`，`prompt` 固定传空字符串，取完整正文，不要自己写摘要指令。
- 读取内容解读规则：`read /data/skills/wiki/references/content-digest.md`
- 入库：`wiki/ingest_entry`
- 检索：`jq`，无结构化命中时再用 `grep`
- 资料库路径一律使用绝对路径 `/data/library/...`
