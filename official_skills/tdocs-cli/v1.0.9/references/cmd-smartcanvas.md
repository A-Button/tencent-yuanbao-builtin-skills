# cmd-smartcanvas — 智能文档

使用 `tdocs-cli smartcanvas ...` 读取 / 增量编辑已有智能文档；仅当用户明确要求「智能文档 / smartcanvas」时用于新建。

智能文档排版美观、组件丰富，内容格式使用 **MDX**，向下兼容全部 Markdown 语法。普通在线 Word 类文档默认走 `doc`，不要自行改用 smartcanvas 新建。

## 能力分类

| 分类 | 能力 | CLI 命令 |
|---|---|---|
| 创建（仅用户明确要求时） | 一次性通过 MDX/Markdown 创建带内容的新文档 | `smartcanvas create-smartcanvas-by-mdx` |
| 创建（显式要求时的兜底） | 两步创建：先建空白文档再写入 | `manage create-file --type 8` + `smartcanvas edit` |
| 读取 | 读取页面完整 MDX 内容（**分页**，单页 ~7000 字，需循环 `next_token`） | `smartcanvas read` |
| 读取 | 一次性获取整篇文档纯文本（**非分页**，"通读全文"优选） | `manage get-content` |
| 搜索 | 按关键词搜索 Block | `smartcanvas find` |
| 导航 | 获取顶层页面列表 | `smartcanvas get-top-level-pages` |
| 编辑 | 插入 / 更新 / 删除 Block | `smartcanvas edit` |

## 核心概念

| 概念 | 说明 |
|---|---|
| `file-id` | 文档唯一标识符 |
| `page-id` | 页面 ID，Page 是文档的基本容器单元 |
| Block ID | 块 ID，`read` / `find` 返回 MDX 中的 `id` 属性值，用作 `edit` 锚点 |

结构层次：`file-id` → `Page` → `Block`（Heading / Paragraph / Table / Callout / ColumnList / Image / ...）

## 代表性示例

```bash
# 用户明确要求智能文档时：优先一次性 MDX 创建
tdocs-cli smartcanvas create-smartcanvas-by-mdx --title "会议纪要" --mdx @./body.mdx

# 兜底：两步创建（仅在 create-smartcanvas-by-mdx 不满足需求时使用，例如需指定父目录）
# 不用 --jq，保留 create-file 完整 JSON 中的 file_id 和 doc_url
tdocs-cli manage create-file --type 8 --title "会议纪要"
tdocs-cli smartcanvas edit --file-id '<file_id>' --action 2 --content @./body.mdx
# 仅当完整响应没有可用链接时补查一次
tdocs-cli manage query-file-info --file-id '<file_id>' --jq '.file | {file_id, name, doc_url}'

# 读取页面完整内容（短文档：< 7000 字）
tdocs-cli smartcanvas read --file-id '<file_id>'

# 读取页面完整内容（长文档：必须循环翻页直到 next_token 为空）
tok=""
while :; do
  out=$(tdocs-cli smartcanvas read --file-id '<file_id>' --next-token "$tok")
  echo "$out" | jq -r '.content'
  tok=$(echo "$out" | jq -r '.next_token // empty')
  [ -z "$tok" ] && break
done

# 或：直接调非分页接口一次性拿全文（推荐用于"通读全文"场景）
tdocs-cli manage get-content --file-id '<file_id>'

# 搜索 Block 并编辑
tdocs-cli smartcanvas find --file-id '<file_id>' --query "项目背景"
tdocs-cli smartcanvas edit --file-id '<file_id>' --action 2 --id <block-id> --content "## 新章节"
```

`create-smartcanvas-by-mdx` 参数：`--title`（必填）、`--mdx`（必填，支持 `@filepath`）、`--content-format`（可选，`mdx`（默认）/ `markdown`）。
`--action` 取值：`1`=INSERT_BEFORE / `2`=INSERT_AFTER / `3`=DELETE / `4`=UPDATE。
`--content` / `--mdx` 支持 `@filepath` 从文件读取。

## 硬性约束

1. **Block ID 必须真实**：`UPDATE` / `DELETE` 及定位锚点所用的 ID 必须来自 `read` / `find` 返回结果，禁止编造。
2. **readonly 块不可动**：返回 MDX 中带 `readonly` 属性的组件及其子元素 ID 均不可作为锚点或操作目标。
3. **图片禁用外链**：所有 `<Image>` / Markdown 图片必须先上传获取 `image_id` 再填入 `src`，禁止 http/https 外链。
4. **MDX 规范强制**：使用高级组件时须严格遵循 MDX 规范（缩进 4 空格、块级组件三段式写法、颜色使用 token 等）。
5. **读全文必须读全**：`read` 是**分页接口**（单页上限 ~7000 字），返回 `next_token` 非空就**必须**继续翻页直到为空，禁止只读首页就开始编辑。需要"通读全文"时，**优先**改用非分页的 `manage get-content --file-id '<file_id>'` 一次拿全。
6. **先确定目的，再选读法；凡是"通读"就必须读到全文**：
   - **通读 / 理解 / 核对整篇**：必须让完整内容进入上下文——`read` 循环翻页到 `next_token` 为空，或用 `manage get-content` 一次拿全。**严禁只读到一部分就当作读完整篇**，基于残缺内容得出的结论不可信。文档过大时，用 `--jq '.content' --format plain > /tmp/<name>.txt` 落盘，再用 `Read` 工具分段读完。

     ```bash
     # ✅ 通读：一次拿全，或循环翻页到 next_token 为空
     tdocs-cli manage get-content --file-id '<file_id>'
     # ❌ 通读却只取片段，再当作已读完整篇
     tdocs-cli smartcanvas read --file-id '<file_id>' | head -50
     ```
   - **找某字段 / 定位某段 / 校验某处改动**：用 `smartcanvas find --query "<关键词>"` 直接拿到相关 Block，不要拉全文再筛。
   - **只做计数或提取标记**（如数某词出现几次、列出所有 Block ID）：用单次管道或内联命令遍历完整输出，结果可只返回统计值；禁止只统计截断片段，也不要创建脚本文件。

## 渐进式参考

按任务按需加载：

| 场景 | 参考文档 |
|---|---|
| 创建新文档（模板匹配、图片、frontmatter） | `references/smartcanvas/create-guide.md` |
| 编辑已有文档（定位策略、边界场景） | `references/smartcanvas/edit-guide.md` |
| MDX 语法规范（组件、属性、颜色 token） | `references/smartcanvas/mdx-references.md` |
| 完整命令参数与返回字段 | `references/smartcanvas/entry.md` |

## 权威来源

```
tdocs-cli smartcanvas --help
tdocs-cli smartcanvas <command> --help
```
