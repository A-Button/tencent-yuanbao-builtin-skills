# 智能文档编辑指南

本文档详细说明如何使用 `tdocs-cli smartcanvas edit` 命令编辑已有智能文档。

阅读本文前，请先了解 `references/smartcanvas/entry.md` 中的基本概念。

---

## 编辑命令概览

```
tdocs-cli smartcanvas edit --file-id <file-id> --action <ACTION> [--id <block-id>] [--content <mdx>]
```

### 四种操作类型

| Action | 说明 | --id 参数 | --content 参数 |
|--------|------|-----------|----------------|
| `INSERT_BEFORE` | 在指定 Block 前插入 | 锚点 Block ID（必填） | MDX 内容（必填） |
| `INSERT_AFTER` | 在指定 Block 后插入 | 锚点 Block ID（空则追加到末尾） | MDX 内容（必填） |
| `DELETE` | 删除指定 Block | 目标 Block ID（必填） | 不需要 |
| `UPDATE` | 修改指定 Block | 目标 Block ID（必填） | 新 MDX 内容（必填） |

---

## 强制约束

1. **Block ID 必须来自 read/find 返回结果**：`UPDATE` 和 `DELETE` 操作的 `--id` 必须先通过 `read-content` 或 `find-elements` 获取，禁止编造或猜测 ID
2. **readonly 块不可操作**：当 read/find 返回的 MDX 中某个组件带有 `readonly` 属性时，该组件及其子元素的 ID 均不可用作锚点或操作目标
3. **MDX 格式规范**：`--content` 中的 MDX 内容须遵循 `references/smartcanvas/mdx-references.md`

---

## 辅助命令

### 读取文档内容

```
tdocs-cli smartcanvas read-content --file-id <file-id> [--page-id <page-id>]
```

- 返回页面完整 MDX 内容，含 Block ID 标注
- 不指定 page-id 时自动获取第一个页面

### 搜索 Block

```
tdocs-cli smartcanvas find-elements --file-id <file-id> --query "关键词"
```

- 返回匹配的 Block 列表，含 ID 和 MDX 内容片段
- 用于精确定位编辑锚点

---

## 典型工作流

### 定位策略

- 有关键词 → 优先 `find-elements`
- `find-elements` 找不到 → 降级用 `read-content` 全文搜索（**长文必须循环 `--next-token` 翻页到尽**）
- 无关键词 → 直接 `read-content`（**长文必须循环 `--next-token` 翻页到尽**；仅需通读纯文本时优先 `manage get-content`）
- **禁止砍输出 / pipe 摘要**：read-content / get-content 的 stdout **禁止**套任何 pipe（`| head/tail/cut/sed/awk/grep/python/python3/node/jq/2>&1|head -c` 全禁，禁止"读完只提取片段"）。唯一允许：先 `> /tmp/x.json` 落盘，再读文件做后续处理

### 工作流一：用户指定了编辑位置（有关键词）

```
步骤 1：搜索定位
  → tdocs-cli smartcanvas find-elements --file-id <fid> --query "关键词"
  → 检查返回结果

步骤 2A：找到匹配 Block
  → 确认锚点 Block ID
  → tdocs-cli smartcanvas edit --file-id <fid> --action <ACTION> --id <block-id> --content "..."

步骤 2B：未找到（降级）
  → tdocs-cli smartcanvas read-content --file-id <fid>
  → 在返回内容中定位目标
  → tdocs-cli smartcanvas edit ...
```

### 工作流二：用户未指定位置

```
步骤 1：读取全文
  → tdocs-cli smartcanvas read-content --file-id <fid>

步骤 2：根据文档结构选择操作
  → 插入到最前：--action 1 --id <首个Block ID>
  → 插入到最后：--action 2（不传 --id）
  → 修改内容：--action 4 --id <目标Block ID>
  → 删除内容：--action 3 --id <目标Block ID>
```

### 工作流三：在「XXX」后插入

```
步骤 1：tdocs-cli smartcanvas find-elements --file-id <fid> --query "XXX"
步骤 2：确认锚点后
  → tdocs-cli smartcanvas edit --file-id <fid> --action 2 --id <锚点ID> --content "新内容"
```

### 工作流四：修改「XXX」为新内容

```
步骤 1：tdocs-cli smartcanvas find-elements --file-id <fid> --query "XXX"
步骤 2：确认目标后
  → tdocs-cli smartcanvas edit --file-id <fid> --action 4 --id <目标ID> --content "新MDX内容"
```

### 工作流五：删除「XXX」

```
步骤 1：tdocs-cli smartcanvas find-elements --file-id <fid> --query "XXX"
步骤 2：确认目标后
  → tdocs-cli smartcanvas edit --file-id <fid> --action 3 --id <目标ID>
```

### 工作流六：追加到文档末尾

```
tdocs-cli smartcanvas edit --file-id <fid> --action 2 --content "追加内容"
```

---

## 分栏（ColumnList）操作

### 创建分栏

```
步骤 1：确定插入位置（find 或 read 获取锚点）
步骤 2：构造 ColumnList MDX（至少 2 列，width 之和 100%）
步骤 3：
  → tdocs-cli smartcanvas edit --file-id <fid> --action 2 --id <锚点> --content "<ColumnList>..."
```

### 修改已有分栏内容

不能单独对 Column 内子块操作。必须对整个 ColumnList 执行 UPDATE：

```
步骤 1：read/find 获取 ColumnList 的 ID 和完整内容
步骤 2：在原有结构上修改目标列内容
步骤 3：
  → tdocs-cli smartcanvas edit --file-id <fid> --action 4 --id <ColumnList ID> --content "完整新ColumnList MDX"
```

### 修改列数或宽度

同样对整个 ColumnList 执行 UPDATE，传入调整后的完整 MDX。

---

## 边界场景处理

### ColumnList 删除列

- 删除后只剩 1 列 → 必须将 ColumnList 整体替换为普通块内容（去掉容器，内容平铺）
- 删除后剩 2+ 列 → 对 ColumnList 执行 UPDATE，重新分配 width

### Callout / BlockQuote 清空

- 内容全部被删除时，容器本身也必须删除
- 操作：对容器 ID 执行 DELETE

### 列表删除含子项的列表项

- 删除父列表项时，子项会一并删除
- 若需保留子项：先 UPDATE 将子项提升为独立块，再 DELETE 父项

### Table 操作

- 禁止单独操作 TableRow / TableCell
- 修改表格内容（增删行、改单元格）→ 对整个 Table 执行 UPDATE，传入完整表格 MDX
- Table 通常带 readonly 属性，此时需选择表格上方或下方的非只读 Block 作为锚点

---

## 图片编辑

编辑时插入图片的约束与创建时一致：

1. 禁止使用外部 URL
2. 必须先上传获取 image_id
3. 将 image_id 填入 `<Image src="image_id" />`

```
tdocs-cli smartcanvas edit --file-id <fid> --action 2 --id <锚点> --content "<Image src=\"上传返回的image_id\" alt=\"描述\" />"
```
