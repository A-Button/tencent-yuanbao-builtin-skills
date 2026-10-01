# cmd-mind — 思维导图

使用 `tdocs-cli mind ...` 创建腾讯文档思维导图——层次化知识整理与可视化。

## 能力分类

| 分类 | 包含的能力 | CLI 命令 |
|---|---|---|
| 创建 | 通过 Markdown 创建思维导图 | `mind create-by-markdown` |

## 参数说明

### mind create-by-markdown

| 参数 | 必填 | 说明 |
|---|---|---|
| `--title` | 否 | 思维导图标题 |
| `--markdown` | 否 | Markdown 格式内容（使用层级标题表示节点层次） |
| `--parent-id` | 否 | 父节点 ID（指定存放位置） |

## Markdown 格式说明

使用 Markdown 标题层级（`#`、`##`、`###` 等）来表示思维导图的节点层次结构：

```markdown
# 中心主题
## 分支一
### 子节点 1.1
### 子节点 1.2
## 分支二
### 子节点 2.1
```

## 代表性示例

```bash
# 创建简单思维导图
tdocs-cli mind create-by-markdown --title "项目规划" --markdown @./mindmap.md

# 在指定空间节点下创建
tdocs-cli mind create-by-markdown --title "读书笔记" --markdown "# 核心观点\n## 第一章\n### 要点1" --parent-id <parent-id>
```

**提示**：`--markdown` 支持 `@filepath` 语法从文件读取内容。

## 权威来源

```
tdocs-cli mind --help
tdocs-cli mind create-by-markdown --help
```
