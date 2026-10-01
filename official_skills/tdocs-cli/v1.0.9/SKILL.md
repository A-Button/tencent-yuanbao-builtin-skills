# tdocs-cli

腾讯文档 CLI (tdocs-cli)，用于在终端中管理和操作腾讯文档。

支持 macOS、Linux、Windows；支持 AMD64 和 ARM64。CLI 是静态编译的单二进制文件，无外部依赖。

## 前置说明

tdocs-cli 已预装并完成授权，开箱即用，无需任何安装或登录操作，直接执行命令即可。

### 执行命令

```
tdocs-cli --help
tdocs-cli <group> --help
tdocs-cli <group> <command> --help  # slide 子命令除外
tdocs-cli slide <command> -h        # slide 子命令统一写法
```

**绝不要自行编造命令或参数名称，务必通过运行时帮助确认（`slide` 子命令用 `-h`，其余用 `--help`）；命令是否允许调用仍以本 SKILL.md 的硬性约束为准。**

## 能力路由表

仅加载与当前任务匹配的参考文档（路径相对于本 skill 目录）。按需渐进加载，避免一次性读取不相关内容。

| 任务分类 | 入口文档 |
| --- | --- |
| 文件创建 / 搜索 / 重命名 / 移动 / 删除 / 权限 / 空间管理 / 上传 / 下载 / 网页剪藏 | `references/cmd-manage.md` |
| 在线文档创建 / 编辑（Word 类：报告、公文、合同、论文、文章等，**在线首选**） | `references/cmd-doc.md` |
| 已有在线 Sheet 的明确小改（有限白名单与调用预算） | `references/cmd-sheet.md` |
| 已有在线 PPT 的原地小改（文本 / 形状 / 页面 / 有限表格操作） | `references/cmd-slide.md` |
| 智能文档 smartcanvas（读取 / 增量编辑已有文档；仅用户明确要求「智能文档 / smartcanvas」时新建） | `references/cmd-smartcanvas.md` |
| 独立思维导图（层次化知识整理，统一走在线 `mind`） | `references/cmd-mind.md` |
| 流程图（流程架构展示） | `references/cmd-flowchart.md` |
| 知识库空间（创建空间、查询空间列表 / 节点） | `references/cmd-space.md` |
| 图片 OCR（文字提取、图片转 Word / Excel） | `references/cmd-ocr.md` |
| 跨命令异步工作流（导入 / 导出文件、网页剪藏） | `references/cmd-workflow.md` |
| 输出格式、jq 过滤、安全诊断 | `references/output-and-debug.md` |
| 错误排查 | `references/troubleshooting.md` |
| 高频命令速查 | `references/cheatsheet.md` |

## 生成文档：先定「在线还是本地」，再选工具

用户要"创建 / 生成"文档时，先判断倾向（要在线腾讯文档 / 要本地文件 / 没明说），再按产物类型选工具：

| 产物类型 | 要在线文档 | 要本地文件 | 没明说倾向 |
|---|---|---|---|
| 文档 / 报告 / 文章 | `doc create-with-markdown`（DOC） | 使用本地文档能力 | **默认本地** |
| 表格 | 新建/复杂修改：本地产出并验收后导入；已有在线小改：`sheet` 白名单 | 使用本地表格能力 | **默认本地** |
| PPT | 新建：本地产出并验收 `.pptx` 后单次导入；已有在线 PPT：`slide` 原地小改 | 使用本地 PPT 能力 | **默认本地** |

在线 DOC 新建时，优先使用 `doc create-with-markdown` 一步创建并写入 Markdown；从响应的 `.data.file_id` 和 `.data.file_url` 记录实际 ID 与链接，后续写入始终复用该 ID。

要点：**文档 / 表格 / PPT 在没明说时都默认走本地**，只有用户明确要"腾讯文档 / 在线文档 / 在线编辑文档"时才走本 CLI。新建或复杂 Sheet 先在本地完成并验收，再单次导入；仅已有在线 Sheet 的明确小改开放有限白名单。新建 PPT 不调用 tdocs-cli 的 AI 生成能力，统一导入已完成的本地 `.pptx`；已有在线 PPT 优先用 `slide` 做白名单内的原地小改。**独立思维导图统一走在线 `mind create-by-markdown`**；流程图要在线用 `flowchart create-by-mermaid`；多维表格（smartsheet）暂未支持。在线创建 Word 类文档默认用 `doc create-with-markdown`；已有 DOC 使用增量编辑命令。仅当用户明确要求「智能文档 / smartcanvas」时才新建 smartcanvas。

### <media_info> 增量：腾讯文档链接

当本技能生成腾讯文档（docs.qq.com）链接时，不要套用 `image`/`video`/`file`（尤其不能用 `file`，它要求用 `path` 而不是 `url`）。改用新增 type `tencent_docs`，字段沿用 `url`，并按 `media_info` 协议放在文本最后返回，不要在正文中内联嵌入链接：

```
文字回答内容
<media_info>[{"type": "tencent_docs", "description": "简要描述该文档内容", "url": "https://docs.qq.com/doc/xxxxxxx"}]</media_info>
```

- `url`：照抄工具返回的原始链接，不改写、不截断。
- `description`：必填，简要说明文档内容。
- 正文中不要出现该链接的裸链接或引导句（如"请看：<url>"），文档信息统一通过 `media_info` 携带。
- 链接为空时只用已返回的 `file_id` 补查一次；不得重复创建或导入。

## 读取文档：先定目的，再选读法

读取腾讯文档前，先想清楚这次要拿什么，再选最合适的命令：

- **通读 / 核对整篇** → 先拿 `file_id`，再用 `manage get-content` 一次拿全（对任意类型文档都适用）。通读必须让完整内容进入上下文，禁止截断后当作已读完整篇；文档过大时，用 `--jq '.content' --format plain > /tmp/<name>.txt` 落盘，再用 `Read` 工具分段读完。
- **只取某字段 / 定位某段** → Word 类 DOC 用 `doc find` / `doc get-outline`；smartcanvas 用 `smartcanvas find`。只取相关部分，不要把全文拉下来再筛。
- **只做计数 / 提取标记**（数词频、定位段落等）→ 可用单次管道或内联命令遍历完整输出，结果可只返回统计值；禁止只统计截断片段，也不要为此创建脚本文件。

### 通读整篇文档工作流

1. **拿 `file_id`**：有链接用 `manage query-file-info --url '...'`（取 `.file.file_id`）；否则用创建/导入返回值，或 `search-file` / `list-file`（无 URL 时建议先详细阅读 `references/cmd-manage.md`）。
2. **通读**：`manage get-content --file-id '<file_id>'`

参数、响应与约束详见 `references/cmd-manage.md`。DOC / smartcanvas 结构操作见 `references/cmd-doc.md`、`references/cmd-smartcanvas.md`。

## 硬性约束

1. **帮助管签名，硬性约束管权限**：具体命令和参数以运行时帮助为准；是否允许调用以本节硬性约束为准，不能因命令仍出现在帮助中就绕过下线策略。`slide` 子命令统一用 `tdocs-cli slide <command> -h` 查签名，其余命令用 `--help`。
2. **kebab-case**：CLI 使用 `import-file`、`--file-id` 等短横线形式。
3. **只读**：不要在本 skill 的工作流中修改 CLI 源码或后端。
4. **命令找不到时**：先执行 `tdocs-cli cache refresh` 再重试。
5. **禁止编写脚本**：不要生成 .sh / .bat / .ps1 脚本来包装 CLI 操作。直接逐条执行 CLI 命令即可——CLI 本身就是跨平台的。
6. **权限与分享以用户意图为准**：用户要求分享、公开访问或协作编辑时，可按其目标调用 `manage get-privilege` / `manage set-privilege` 设置满足目标的最小权限；仅为排查“打不开 / 无权限”且用户没有表达分享意图时，不得擅自扩大权限，尤其不得将用户存量文档设为 `PUBLIC_WRITE`。删除仍按下一条白名单执行。
7. **会话内存量文档优先原位编辑**：当会话中已有腾讯文档在线链接，用户随后要求编辑且未明确要求另存时，优先复用其 `file_id` 和原链接做精准局部修改。白名单无法可靠完成复杂改动时，按对应类型参考文档执行；仅在该类型明确允许新版本时，才先说明限制并征得用户同意，再用可用的本地文件能力产出新版本。新版本上传并确认可交付前，禁止删除旧版本。
8. **删除文档白名单**：`manage delete-file` **仅允许处理本次会话中由当前 Agent 通过 tdocs-cli 创建或导入、且在会话中有明确 `file_id` 记录的文档**。替换版本时必须先上传并验证新版；旧版有价值或判断不清时保留并用 `V2` / `V3` 区分。只有确认旧版无保留价值时才可按白名单清理。用户提供的链接、搜索发现的文档、用户网盘存量或来源不明的文件一律禁止删除。详见 `references/cmd-manage.md`。
9. **PPT 新建走本地成品导入，已有在线 PPT 原地小改**：禁止使用 tdocs-cli 的 AI 生成 PPT 能力。新建 PPT 只对已完成并验收的本地 `.pptx` 执行一次 `workflow import-file`。修改已有在线 PPT 时复用原 `file_id`，按 `references/cmd-slide.md` 白名单原地编辑；动画、图表、批注、分组、节编辑、主题、新建表格等未开放能力不得调用。白名单无法可靠完成复杂改动时，经用户确认可产出并导入 V2，保留原链接并说明未覆盖。
10. **Sheet 仅开放已有在线小改**：只有满足 `references/cmd-sheet.md` 准入与调用预算时，才允许 `get-sheet-info`、`get-cell-data`、`set-range-value`、`set-cell-style`、`insert-dimension`、`delete-dimension`；其余 `sheet` 子命令均禁用，尤其禁止 `operation-sheet` 和逐格 `set-cell-value`。新建、复杂修改或无法守住预算时转为本地处理，验收后单次导入为新资源；仍禁止 `manage create-file --type 2`。
11. **多维表格能力全部下线（含导入）**：`smartsheet` 子命令组（多维表格读写、视图、字段、记录）及相关导入能力当前均已对本 skill 关闭。**禁止调用** `smartsheet` 任何子命令（包括 `smartsheet list-sub-sheet` / `list-records` / `add-record` / `update-record` / `delete-record` / `add-field` 等）。**禁止**通过 `workflow import-file` 向多维表格类型文档导入数据，**禁止**通过 `manage create-file --type 9`（SMART_SHEET）创建空白多维表格。即使用户明确要求"多维表格 / smartsheet / 结构化数据表"，也应直接提示用户该能力暂未开放，请用户在腾讯文档前端自行操作。
12. **命令失败先诊断，禁止盲目重试**：任一命令报错时先弄清原因再动作；除 `429` / `400007` 等明确的速率限制可按 `troubleshooting.md` 退避重试外，**禁止「`sleep` 后重发一模一样的命令」**。
    - **参数/flag 报错**（`unknown flag`、参数缺失、`local validation failed` 等）是本地错误，改命令才有用：按第 1 条查运行时帮助，**禁止**把某个 flag 换成"看着像"的另一个反复盲试（例如 `manage search-file` 用 `--pattern` + `--tag-info`，不是 `--keyword`）。
    - **`file_id` 原样使用**上一步 API 返回的值，禁止拼接、删改前缀或用文档 URL 代替。字面 ID 用单引号（如 `--file-id '300000000$HoSwmcmjAMsP'`），shell 变量用双引号（`--file-id "$fid"`）；禁止把变量写成 `'$fid'`。
    - **`import-file` 有副作用**：同一本地文件只导入一次；返回体 `file_url` 暂空 **不等于失败**，勿对同一文件重复导入而产生多份在线副本——需要时复用上一步已得到的 `file_id`。`import-file` **不响应 `--jq` / `--format`**，只输出固定完整 JSON，从中读 `file_id` 字段即可。
13. **写操作完成后保留链接**：创建或编辑后需要向用户交付腾讯文档链接（含 `media_info`）时，优先复用创建响应或原文档的 URL；若没有可用 URL，只用已记录的 `file_id` 调一次 `manage query-file-info --file-id '<file_id>'`，从 `.file.doc_url` 或 `.file.tencent_doc_url` 补取。禁止为取链接重复创建或导入。
14. **禁止使用 `--debug`**：`--debug` 是每条命令都可见的全局 flag，会输出含完整 Authorization、Cookie 与票据的请求头和响应头。**在 CLI 完成可靠脱敏前，禁止使用、保存或转发 `--debug` 输出。** 参数核对用单发 API 命令的 `--dry-run`，响应结构用 `--jq '.'`，故障上报只使用普通输出中已有的错误码或 trace ID。详见 `references/output-and-debug.md`。
