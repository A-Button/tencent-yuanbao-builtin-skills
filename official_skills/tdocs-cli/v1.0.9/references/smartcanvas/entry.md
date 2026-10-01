# 智能文档（SmartCanvas）命令参考

本文档为 `smartcanvas` 命令组的完整参数与返回字段参考。任务型工作流请看 `create-guide.md` / `edit-guide.md`。

阅读本文前，建议先看 `cmd-smartcanvas.md` 了解能力全貌与核心概念。

新建命令仅在用户明确要求「智能文档 / smartcanvas」时使用；普通在线 Word 类文档默认走 `doc`。

---

## 命令总览

| 命令 | 用途 |
|---|---|
| [`create-smartcanvas-by-mdx`](#create-smartcanvas-by-mdx) | 用户明确要求 smartcanvas 时，一步创建带 MDX/Markdown 内容的智能文档 |
| [`get-top-level-pages`](#get-top-level-pages) | 查询文档顶层页面列表 |
| [`read`](#read) | 读取页面完整 MDX 内容 |
| [`find`](#find) | 按关键词搜索 Block |
| [`edit`](#edit) | 插入 / 更新 / 删除 Block |

需指定父目录或分多段写入时可退化为 `manage create-file --type 8` + `smartcanvas edit`，详见 `create-guide.md`。

---

## create-smartcanvas-by-mdx

一步创建带内容的智能文档。用户已明确要求 smartcanvas 时，**优先使用本命令**；仅当需要指定 `--parent-id` / `--space-id` 等放置位置时才退化为两步流程。

```bash
tdocs-cli smartcanvas create-smartcanvas-by-mdx --title "<标题>" --mdx @./body.mdx
```

| 参数 | 必填 | 说明 |
|---|---|---|
| `--title` | ✅ | 文档标题 |
| `--mdx` | ✅ | 文档正文，默认 MDX；支持 `@filepath` 从文件读取 |
| `--content-format` |  | `mdx`（默认，推荐）/ `markdown`；为空时按 `mdx` 解析 |

**返回**：`file_id`、`url`、`error` 字段，可用 `--jq '.file_id'` / `--jq '.url'` 提取。
> 注意返回字段不统一：`create-smartcanvas-by-mdx` 返回 `url` + `error`；而兜底用的 `manage create-file` 返回的是 `doc_url`（且无 `error` 字段）。下游取链接要按命令区分：智能文档一步创建取 `.url`，`create-file` 取 `.doc_url`。

**强制约束**：
- 图片必须先通过 `manage upload-image` 上传得到 `image_id` 再使用，禁止 http/https 外链；MDX 须遵循 `mdx-references.md`。
- **正文不要用一级标题 `# 标题`**：`--mdx` 正文里的 h1（`# xxx`）在 `read` / `get-content` 中会丢失（页面标题取自 `--title`）。文档标题一律走 `--title`，正文从二级标题 `##` 起写。

---

## get-top-level-pages

查询文档的顶层页面列表，获取 `page_id` 用于后续读取。

```bash
tdocs-cli smartcanvas get-top-level-pages --file-id '<file_id>'
```

| 参数 | 必填 | 说明 |
|---|---|---|
| `--file-id` | ✅ | 文档唯一标识符 |

**返回**：`pages[].page_id`、`pages[].title`

---

## read

读取指定页面的完整 MDX 内容。不指定 `--page-id` 时自动获取第一个页面。

```bash
tdocs-cli smartcanvas read --file-id '<file_id>' [--page-id <page-id>] [--next-token <token>] [--size <n>]
```

| 参数 | 必填 | 说明 |
|---|---|---|
| `--file-id` | ✅ | 文档唯一标识符 |
| `--page-id` |  | 页面 ID，为空时取第一个页面 |
| `--next-token` |  | 分页游标，从上次返回的 `next_token` 传入 |
| `--size` |  | 每页子节点数，最大 20，默认 20 |

**返回**：`content`（MDX 文本）、`next_token`（非空表示还有更多内容）

**强制约束（避免长文截断）**：
- 单次调用最多返回 ~7000 字，**只要 `next_token` 非空就必须继续翻页直到为空**，禁止只读首页就开始判断或编辑。
- **通读 / 编辑定位时禁止砍输出或 pipe 摘要**：禁止用 `head` / `tail` / `cut` / `sed` / `awk` / `grep` / `jq` 等截断、摘要后冒充完整阅读。大文档用 `manage get-content --jq '.content' --format plain > /tmp/<name>.txt` 落盘，再分段读完。仅做计数或提取标记时，可用单次管道或内联命令遍历完整输出并只返回结果；禁止只处理截断片段或创建脚本文件。
- 仅需"通读全文纯文本"时，**优先**用非分页的 `tdocs-cli manage get-content --file-id '<file_id>'`，一次拿全（实测可达 20000+ 字），无需翻页。
- 翻页骨架：

```bash
tok=""
while :; do
  out=$(tdocs-cli smartcanvas read --file-id '<file_id>' --next-token "$tok")
  echo "$out" | jq -r '.content'
  tok=$(echo "$out" | jq -r '.next_token // empty')
  [ -z "$tok" ] && break
done
```

**使用场景**：编辑前通读全文；`find` 找不到时降级查找。

---

## find

按关键词在文档所有页面中搜索 Block，返回匹配 Block 的 ID 和 MDX 片段。

```bash
tdocs-cli smartcanvas find --file-id '<file_id>' --query "<关键词>"
```

| 参数 | 必填 | 说明 |
|---|---|---|
| `--file-id` | ✅ | 文档唯一标识符 |
| `--query` | ✅ | 搜索文本 |

**返回**：`blocks[].id`（可作 `edit` 锚点）、`blocks[].content`（MDX 片段）

> **已知限制（召回不稳定）**：`find` 后端召回当前不稳定，文档正文里确实存在的词也可能返回空 `blocks`。`find` 返回空时**不要据此判定"文档里没有"**，应降级用 `read` 通读全文（长文翻页到尽）/`manage get-content` 一次拿全，再人工定位目标 Block。

---

## edit

编辑文档，支持四种操作。

```bash
tdocs-cli smartcanvas edit --file-id '<file_id>' --action <1|2|3|4> [--id <block-id>] [--content "<MDX>"]
```

| `--action` | 操作 | `--id` | `--content` |
|---|---|---|---|
| `1` | INSERT_BEFORE | 锚点 Block ID（必填） | MDX（必填） |
| `2` | INSERT_AFTER | 锚点 Block ID（空则追加到末尾） | MDX（必填） |
| `3` | DELETE | 目标 Block ID（必填） | 不需要 |
| `4` | UPDATE | 目标 Block ID（必填） | 新 MDX（必填） |

| 参数 | 必填 | 说明 |
|---|---|---|
| `--file-id` | ✅ | 文档唯一标识符 |
| `--action` | ✅ | 操作类型 1/2/3/4 |
| `--id` | 条件 | 锚点/目标 Block ID，见上表 |
| `--content` | 条件 | MDX 内容，支持 `@filepath` 读取文件 |

**强制约束**：

- `UPDATE` / `DELETE` 及定位锚点用的 ID **必须**来自 `read` / `find` 返回结果，禁止编造。
- 返回 MDX 中带 `readonly` 的组件及其子元素 ID 不可作为锚点或操作目标。
- MDX 内容须遵循 `mdx-references.md`。
- 图片必须先上传获取 `image_id`，禁止 http/https 外链。

**示例**：

```bash
# 在指定 Block 后插入
tdocs-cli smartcanvas edit --file-id '<file_id>' --action 2 --id <bid> --content "## 新章节"

# 追加到末尾
tdocs-cli smartcanvas edit --file-id '<file_id>' --action 2 --content "追加内容"

# 修改 / 删除
tdocs-cli smartcanvas edit --file-id '<file_id>' --action 4 --id <bid> --content "新内容"
tdocs-cli smartcanvas edit --file-id '<file_id>' --action 3 --id <bid>

# 从文件读取长内容
tdocs-cli smartcanvas edit --file-id '<file_id>' --action 2 --content @./body.mdx
```

定位策略、典型工作流、分栏/表格等边界场景详见 `edit-guide.md`。

---

## 权威来源

```
tdocs-cli smartcanvas --help
tdocs-cli smartcanvas <command> --help
```

`file-id` 通过 `manage search-file` / `manage ai-search-file` 搜索，或从 `manage create-file` 返回获取。
