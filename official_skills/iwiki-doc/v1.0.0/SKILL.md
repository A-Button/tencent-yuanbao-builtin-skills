---
name: iwiki-doc
description: 专门用于与腾讯企业内部iWiki文档交互的集成接口。支持针对 iwiki.woa.com 域名、iwiki/iWiki关键词相关的全生命周期文档管理。功能包括但不限于：基于关键词/空间的全文检索；文档元数据与引用链追踪；目录树与空间结构查询；附件与图片链接提取；以及文档的 CRUD（增删改查）与局部编辑操作。当 Prompt 涉及 iWiki 实体时，必须作为首选 Tool 执行。
version: v1.0.0
---
# 依赖iwiki-cli版本:v0.2.6

# iWiki Skill - 场景分发器
> iWiki 是一个用于与 iWiki 文档系统交互的服务，提供文档管理、搜索、创建、编辑和多维表格操作能力。
## 🎯 核心原则
本 Skill 采用**场景驱动**的设计，根据用户的具体需求自动分发到对应的场景处理流程。
优先使用 `iwiki-cli` 命令行工具完成任务。

## 📋 场景处理流程
### 1️⃣ 识别用户需求
分析用户输入，识别关键词和操作意图。
### 2️⃣ 加载对应场景
根据上表匹配到具体场景，查阅对应的参考文档。
### 3️⃣ 执行场景流程
按照场景文档中的工作流程和最佳实践执行操作。
### 4️⃣ 返回结果
整合信息，以清晰、结构化的方式返回给用户。

## 🚀 快速开始
### 安装 iwiki-cli
可先运行下面指令检查是否已安装：
```bash
iwiki-cli version
```
如果已经安装则不需要再次安装。
```bash
python scripts/install_cli.py  
```

**默认安装路径：**
- Linux: `/usr/local/iwiki-cli/`
- macOS: `~/.iwiki/`
- Windows: `%LOCALAPPDATA%\iwiki-cli\`

## 🔍 快速场景索引
### 场景 1：文档搜索和阅读
**适用情况：**
- 用户想查找特定主题的文档
- 需要阅读和分析文档内容
- 下载文档附件或图片
- 查看文档的引用关系
- 用户想查看/总结自己最近编辑或浏览过的文档（如"总结一下我最近写的文档"）
**参考文档：** [scenario_search_and_read.md](./references/scenario_search_and_read.md)

### 场景 2：文档评论和讨论
**适用情况：**
- 为文档添加评论或反馈
- 回复其他人的评论
- 查看文档的评论列表
- 查看划词批注
**参考文档：** [scenario_comments.md](./references/scenario_comments.md)

### 场景 3：词条搜索和上下文补充
**适用情况：**
- 查询某个术语或名词的定义
- 批量查询多个词条
- 通过 AI 搜索理解用户问题
- 补充专业背景知识
**参考文档：** [scenario_glossary_search.md](./references/scenario_glossary_search.md)

### 场景 4：文档创建和导入
**适用情况：**
- 在 iWiki 中创建新文档
- 将本地文件导入到 iWiki
- 批量导入文档（zip 压缩包）
- 同步代码仓库的文档
- 用户说"在我的空间下写入"（需通过最近文档确定用户空间）

**参考文档：** [scenario_create_import.md](./references/scenario_create_import.md)
### 场景 5：文档编辑和更新
**适用情况：**
- 修改文档标题或内容
- 在文档头部/尾部追加内容
- 移动文档到其他位置
- 复制文档或文档树

**参考文档：** [scenario_edit_update.md](./references/scenario_edit_update.md)
### 场景 6：多维表格操作
**适用情况：**
- 查询多维表格的数据
- 向表格添加新记录
- 更新表格记录
- 删除表格记录（需确认）
- 管理表格字段（添加/删除）
**参考文档：** [smartsheet.md](./references/smartsheet.md)

### 场景 7：文档 AI 评审
**适用情况：**
- 根据评审规则对文档进行自动评审
- 查看空间下的评审规则列表
- 读取文档内容并按规则生成修改建议
- 将评审结果以评论形式添加到文档
**参考文档：** [scenario_aireview.md](./references/scenario_aireview.md)

### 场景 8：文档审计
**适用情况：**
- 查看单篇文档的访问记录、版本历史，了解谁访问了文档、访问频次
- 对比文档任意两个版本之间的内容变更
- 查询整个空间在某段时间内的运营总览（PV/UV/新增文档数）
- 查询空间内每个用户的操作明细（创建、更新、评论、点赞、收藏、下载等）
**参考文档：** [scenario_audit.md](./references/scenario_audit.md)

### 场景 9：创建待办任务列表（TaskList）
**适用情况：**
- 在文档中创建待办任务（taskList / taskItem）
- 为任务指定负责人（@mention）
- 设置任务截止日期（date）
- 配置到期提醒（remind），包括提醒时间、提前天数、重复规则、提醒对象
- 构造包含 taskList 的 pmjson body
- 批量创建多个任务项并分配给不同负责人
**参考文档：** [scenario_tasklist.md](./references/scenario_tasklist.md)

### 场景 10：跨会话长期记忆（远端 Hy-Memory：用户偏好 / 事实 / 经验）
**适用情况：**
- **用户主动表达偏好**（领域、术语、检索范围、回答风格、工作流、禁忌）
- **沉淀零碎事实 / 知识 / 经验**，并能按语义搜索回灌
- **工具调用出错或多次重试仍不正确，经用户指引修正后，把纠正经验写入远端记忆**
- 关键词：记忆 / 记住 / 我以后想 / 默认就用 / 长期记忆 / longmemory
**核心命令：** `iwiki-cli memory <write|search>`

```bash
iwiki-cli memory write   --content "用户偏好用 Go 写 CLI，偏好简洁 API"
iwiki-cli memory search  "用户的编程偏好"
```

**调用规约（MUST，全局生效）：**
1. **前置 search** —— 调用任何 `iwiki-cli` 子命令之前，**或调用其它任何工具之前**（包括其它 MCP / CLI / 代码搜索 / 编辑工具），都建议先用本任务相关的关键词 `memory search "<query>"` 检索一次远端记忆，把命中的【用户偏好】+【经验教训】注入本次决策。
2. **同步偏好 write** —— 当用户明确表达偏好（"以后默认……" / "我希望……"），立即 `memory write --content "用户偏好：……"` 沉淀到远端。
3. **错误回灌 write** —— 当**任意工具**调用出错、或多次重试仍不正确，经用户指引修正后，立即 `memory write --content "经验教训：<错误现象> → <用户指引> → <正确做法>"` 把纠正过程结构化沉淀（不限于 iwiki-cli 自身的错误，也包括其它工具/命令的踩坑）。

**参考文档：** [scenario_memory.md](./references/scenario_memory.md) · [longmemory_api.md](../../longmemory_api.md)


## ⚠️ 重要约定和最佳实践
### 1. 搜索优先级
- **术语查询：** 优先使用 `iwiki-cli glossary <keyword> --exact`
- **文档搜索：** 首选 `iwiki-cli search`（支持筛选和分页）
- **AI 搜索：** 作为补充，使用 `iwiki-cli search --ai`
### 2. 内容格式规范
- **Markdown 文档：** `contenttype: "MD"`, `is_html: false`
- **富文本文档：** `contenttype: "DOC"`, `is_html: true`
- **评论内容：** 必须使用 XHTML 格式

### 3. 认证配置
安装完成后需先登录。AI 环境中推荐使用 `login` + `check` 两步完成：
```bash
# 第一步：发起授权（会输出浏览器链接，用户需在浏览器中完成授权）
iwiki-cli auth login
# 第二步：检查授权是否完成（可多次调用）
iwiki-cli auth check
```
也可手动保存 PAT Token：
```bash
iwiki-cli auth save <token>
```

### 4. 临时文件管理
- 打包上传时，将 Markdown 和附件打包成 zip，完成后删除临时 zip

**注意：本 Skill 是场景分发器，具体操作流程请参考对应的场景文档！**