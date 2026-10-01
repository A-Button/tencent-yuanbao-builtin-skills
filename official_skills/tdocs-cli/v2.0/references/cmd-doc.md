# cmd-doc — 文档编辑

使用 `tdocs-cli doc ...` 操作腾讯文档的 Word 类文档——论文、公文、合同等专业文档编辑。

## 能力分类

| 分类 | 包含的能力 | CLI 命令 |
|---|---|---|
| 结构查看 | 获取文档完整结构树 | `doc resolve-document-structure` |
| 结构查看 | 获取文档大纲 | `doc get-outline` |
| 结构查看 | 获取文档末尾可操作位置 | `doc get-last-operable-pos` |
| 查找 | 查找文本 | `doc find` |
| 查找替换 | 查找并替换文本 | `doc find-and-replace` |
| 插入 | 在指定位置插入文本 | `doc insert-text` |
| 插入 | 在指定位置插入段落 | `doc insert-paragraph` |
| 插入 | 在指定位置插入 Markdown 内容 | `doc insert-markdown` |
| 插入 | 在指定位置插入表格 | `doc insert-table` |
| 插入 | 在指定位置插入图片 | `doc insert-image` |
| 插入 | 在指定位置插入分页符 | `doc insert-page-break` |
| 插入 | 插入任务 | `doc insert-task` |
| 插入 | 插入批注 | `doc insert-comment` |
| 替换 | 替换指定范围内的文本 | `doc replace-text` |
| 替换 | 替换图片 | `doc replace-image` |
| 图片 | 获取文档中所有图片信息 | `doc get-images` |
| 样式 | 更新文本属性（加粗、斜体、颜色等） | `doc update-text-property` |

## 重要概念

| 概念 | 说明 |
|---|---|
| `file-id` | 文档唯一标识符 |
| `file-url` | 文档 URL 链接（可选，用于辅助定位） |
| `version-info` | 版本参数（object 类型，大部分写入操作需要） |
| `idx` | 文档位置索引，通过 `get-outline` 或 `resolve-document-structure` 获取 |

## 典型工作流

1. 先用 `doc resolve-document-structure` 或 `doc get-outline` 了解文档结构
2. 确定插入/编辑位置的 `idx`
3. 使用 `insert-text` / `insert-markdown` / `insert-table` 等命令操作

## 代表性示例

```bash
# 获取文档结构
tdocs-cli doc resolve-document-structure --file-id <file-id> --version-info '{}'

# 获取文档大纲
tdocs-cli doc get-outline --file-id <file-id> --version-info '{}'

# 获取文档末尾位置
tdocs-cli doc get-last-operable-pos --file-id <file-id> --version-info '{}'

# 在指定位置插入 Markdown 内容
tdocs-cli doc insert-markdown --file-id <file-id> --idx 10 --markdown "## 新标题" --version-info '{}'

# 查找并替换文本
tdocs-cli doc find-and-replace --file-id <file-id> --old-text "旧文本" --new-text "新文本" --version-info '{}'

# 更新文本样式（加粗）
tdocs-cli doc update-text-property --file-id <file-id> \
    --IndexRanges '[{"begin":0,"end":5}]' \
    --property '{"bold":true}' \
    --version-info '{}'
```

## 权威来源

```
tdocs-cli doc --help
tdocs-cli doc <command> --help
```

确定所需能力后即可停止阅读本文件——权威的命令和参数列表来自 `--help`。
