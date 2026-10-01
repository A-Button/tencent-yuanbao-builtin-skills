# cmd-doc — 在线 DOC 入口

使用 `tdocs-cli doc ...` 创建或增量编辑腾讯文档的 Word 类在线文档。普通本地 `.docx` 任务使用可用的本地文档能力。

## 能力分类

本表只用于能力发现，不是完整命令清单；选定能力后再按需加载 guide，并用当前 `--help` 确认签名。

| 分类 | 代表能力 / 命令 |
|---|---|
| 创建 | `create-with-markdown` |
| 定位与读取 | `resolve-document-structure`、`get-outline`、`find`、`get-last-operable-pos` |
| 内容插入 | `insert-markdown`、`insert-paragraph`（空行/分段）、`insert-paragraph-with-text`、`insert-table`、`insert-image` |
| 精确替换 | `replace-text`、`find-and-replace`、`replace-image` |
| 样式与版式 | `get-text-property`、`update-text-property`、`get-paragraph-property`、`modify-paragraph`、`copy-format` |
| 表格 | `get-table-info`、`insert-rows`、`insert-cols`、`set-table-layout`、`set-table-properties` |
| 文档结构与协作 | `insert-comment`、`insert-task`、链接、附件、页眉页脚、脚注和页码 |
| 修订与比较 | `list-recent-ai-edits`、`revert-revision`、`accept-all-revisions`、`compare-documents` |

## 核心概念

| 概念 | 说明 |
|---|---|
| `file_id` | 在线 DOC 的资源身份；已有文档后续操作始终复用同一值 |
| `idx` | 单个插入或定位位置，不是段落序号 |
| `begin/end` | 文本或段落范围，来自当前结构或查找结果 |
| `version-info` | 写操作的版本参数；需要显式版本时必须使用 API 返回值 |

## 典型工作流

- **新建 DOC**：准备完整 Markdown → `create-with-markdown` → 记录返回的 ID/链接 → 验收。
- **追加内容**：`get-last-operable-pos` → 使用真实 `idx` 写入 → 定点回读。
- **精确替换**：`find` → 用返回的 `begin/end` 调 `replace-text` → 分别检查旧值和新值。
- **样式版式**：`resolve-document-structure` → 构造 ranges → 字符样式与段落版式分别合并写入 → 属性抽查。
- **表格操作**：先用 `resolve-document-structure` 定位表格，再以表格内真实 `idx` 调 `get-table-info`，最后插入行列或修改布局和属性。
- **改标题**：文件名与正文一级标题是两个对象，按用户措辞和当前内容消歧；两处明显对应时可同步，明显不同时先询问。用户点名的是**章节标题**时只改该章节，不动文件名。详见 `cmd-manage.md`「改标题」。

## 硬性约束

1. **坐标必须来自当前真实结构**：`idx` 是插入位置；`begin/end` 是文本或段落范围。两者都来自本次 `resolve-document-structure`、`get-outline`、`find` 或 `get-last-operable-pos` 返回，禁止固定值、段落序号或估算值。
2. **已有 DOC 始终复用同一 `file_id`**：写操作可能改变结构，后续仍需坐标时重新定位；失败也不得通过新建、导入或删除重建规避。

## 通用约定

- 字面 `file_id` 使用单引号，如 `--file-id '<file_id>'`；历史 ID 可能含 `$`。shell 变量使用 `--file-id "$fid"`。
- `doc find` 使用具名参数 `--text`。
- `insert-markdown` 优先传 `--base64-markdown`，避免特殊字符破坏参数。

## 渐进式参考

按当前任务只加载需要的文档：

| 场景 | 参考文档 |
|---|---|
| 新建在线 DOC、记录 ID/链接、创建后继续编辑 | `doc/create-guide.md` |
| 编辑已有 DOC、追加/替换、样式版式、写后验收与恢复 | `doc/edit-guide.md` |
| 查询坐标、复杂参数范式和已实测限制 | `doc/entry.md` |

复杂编辑同时需要参数细节时，再补读 `doc/entry.md`。

## 权威来源

```text
tdocs-cli doc --help
tdocs-cli doc <command> --help
```

命令参数以当前 `--help` 为准；是否允许调用仍以根 `SKILL.md` 的硬约束为准。
