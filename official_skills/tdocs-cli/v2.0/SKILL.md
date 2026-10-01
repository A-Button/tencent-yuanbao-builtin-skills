# tdocs-cli

腾讯文档 CLI (tdocs-cli)，用于在终端中管理和操作腾讯文档。

支持 macOS、Linux、Windows；支持 AMD64 和 ARM64。CLI 是静态编译的单二进制文件，无外部依赖。

## 前置说明

tdocs-cli 已预装并完成授权，**开箱即用，无需任何安装或登录操作**，直接执行命令即可。

### 执行命令

```
tdocs-cli --help
tdocs-cli <group> --help
tdocs-cli <group> <command> --help
```

**绝不要自行编造命令或参数名称，务必通过 `--help` 确认。**

## 能力路由表

仅加载与当前任务匹配的参考文档（路径相对于本 skill 目录）。按需渐进加载，避免一次性读取不相关内容。

| 任务分类 | 入口文档 |
|---|---|---|
| 文件创建 / 搜索 / 重命名 / 移动 / 删除 / 权限 / 空间管理 / 上传 / 下载 / 网页剪藏 | `references/cmd-manage.md` |
| 智能文档（报告、笔记、文章、总结等，**首选**；创建优先用 `smartcanvas create-by-mdx`） | `references/cmd-smartcanvas.md` |
| 文档编辑（论文、公文、合同等专业 Word 档） | `references/cmd-doc.md` |
| 思维导图（层次化知识整理） | `references/cmd-mind.md` |
| 流程图（流程架构展示） | `references/cmd-flowchart.md` |
| 知识库空间（创建空间、查询空间列表 / 节点） | `references/cmd-space.md` |
| 图片 OCR（文字提取、图片转 Word / Excel） | `references/cmd-ocr.md` |
| 跨命令异步工作流（导入 / 导出文件、网页剪藏） | `references/cmd-workflow.md` |
| 输出格式、jq 过滤、调试 | `references/output-and-debug.md` |
| 错误排查 | `references/troubleshooting.md` |
| 高频命令速查 | `references/cheatsheet.md` |

## 生成文档：先定「在线还是本地」，再选工具

用户要"创建 / 生成"文档时，先判断倾向（要在线腾讯文档 / 要本地文件 / 没明说），再按产物类型选工具：

| 产物类型 | 要在线文档 | 要本地文件 | 没明说倾向 |
|---|---|---|---|
| 文档 / 报告 / 文章 | `smartcanvas create-by-mdx` | `docx` skill | **默认在线** → `smartcanvas create-by-mdx` |
| 表格 | `xlsx` skill 生成 `.xlsx` → `workflow import-file` 导入 | `xlsx` skill | **默认本地** → `xlsx` skill |
| PPT | `pptx` skill 生成 `.pptx` → `workflow import-file` 导入 | `pptx` skill | **默认本地** → `pptx` skill |

要点：**只有"文档类"在没明说时默认走在线，表格 / PPT 默认本地**。表格、PPT 的在线需求一律"本地 skill 生成 → `workflow import-file` 导入"（`sheet` / `slide` 在线生成已下线，详见硬性约束 #7 / #8）。思维导图 / 流程图要在线用 `mind create-by-markdown` / `flowchart create-by-mermaid`，没明说时同样默认本地；多维表格（smartsheet）暂未支持。

## 读取文档：先定目的，再选读法

读取腾讯文档前，先想清楚这次要拿什么，再选最合适的命令：

- **通读 / 核对整篇** → 文档不大时用 `manage get-content` 一次拿全；**文档较大（约 1.5 万字以上）改用 `smartcanvas read-content` 翻页到 `next_token` 为空**，因为单次输出过大会被截断。**严禁只读片段（`| head`、`[:N]` 等）就当作读完整篇**。
- **只取某字段 / 定位某段** → `smartcanvas find-elements --query "<关键词>"`，只返回相关 Block，不要把全文拉下来再筛。
- **只做计数 / 提取标记**（数词频、列 Block ID 等）→ 可用管道或脚本精确提取，不受"读全"约束。

详细规则与示例见 `references/cmd-smartcanvas.md` 规则 #6。

## 硬性约束

1. **`--help` 为准**：具体命令和参数以运行时 `--help` 为准，文档仅列出稳定的命令组和示例。
2. **kebab-case**：CLI 使用 `import-file`、`--file-id` 等短横线形式。
3. **只读**：不要在本 skill 的工作流中修改 CLI 源码或后端。
4. **命令找不到时**：先执行 `tdocs-cli cache refresh` 再重试。
5. **禁止编写脚本**：不要生成 .sh / .bat / .ps1 脚本来包装 CLI 操作。直接逐条执行 CLI 命令即可——CLI 本身就是跨平台的。
6. **删除文档白名单**：`manage delete-file` **仅允许删除"本次会话中由当前 Agent 通过 tdocs-cli 创建或导入的文档"**，且必须先用本次会话中记录的 `file_id` 精确匹配；对用户存量文档（包括用户提供的 file_id、search-file/list-file 检出的他人文档、用户网盘内已存在的文档）一律**禁止调用** `manage delete-file`，即使用户口头要求"删掉"也应改为提示用户在腾讯文档前端自行操作。详见 `references/cmd-manage.md`「删除文档白名单」章节。
7. **PPT 生成能力下线（保留导入）**：`slide` 子命令组（AI 生成 PPT）当前为付费内测能力，已对本 skill 关闭。**禁止调用** `slide create-slide` / `slide slide-progress`。用户需要 PPT 时，**优先建议**：① 让用户在腾讯文档前端自行操作；② 若必须由 Agent 产出，先生成本地 `.pptx` 文件，再通过 `workflow import-file` 导入腾讯文档。同时**禁止**通过 `manage create-file` 创建空白 PPT 类型文档（`--file-type` 任何 PPT/slide 取值均禁用）。
8. **电子表格能力下线**：`sheet` 子命令组（电子表格读写、单元格操作、结构变更）当前已对本 skill 关闭。**禁止调用** `sheet` 任何子命令（包括 `sheet get-cell-data` / `sheet set-cell-value` / `sheet add-sheet` / `sheet delete-dimension` 等）。用户需要电子表格时，**优先建议**：① 让用户在腾讯文档前端自行操作；② 若必须由 Agent 产出表格类内容，先生成本地 .xlsx 文件，再通过 `workflow import-file` 导入腾讯文档。同时**禁止**通过 `manage create-file --file-type sheet` / `--type 2` 创建空白电子表格。
9. **多维表格能力全部下线（含导入）**：`smartsheet` 子命令组（多维表格读写、视图、字段、记录）及相关导入能力当前均已对本 skill 关闭。**禁止调用** `smartsheet` 任何子命令（包括 `smartsheet list-sub-sheet` / `list-records` / `add-record` / `update-record` / `delete-record` / `add-field` 等）。**禁止**通过 `workflow import-file` 向多维表格类型文档导入数据，**禁止**通过 `manage create-file --file-type smartsheet` 创建空白多维表格。即使用户明确要求"多维表格 / smartsheet / 结构化数据表"，也应直接提示用户该能力暂未开放，请用户在腾讯文档前端自行操作。
