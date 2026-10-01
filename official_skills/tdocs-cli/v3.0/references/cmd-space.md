# cmd-space — 知识库空间

使用 `tdocs-cli space ...` 管理腾讯文档知识库空间——创建空间、查询空间列表与空间内的节点（文件 / 文件夹）。

> 「空间」是腾讯文档中以知识库形式组织的文件容器；空间内部的层级用「节点」表示。普通 *我的文档* 文件树请使用 `manage list-file`，本组命令仅面向知识库空间。

## 能力分类

| 分类 | 包含的能力 | CLI 命令 |
|---|---|---|
| 创建 | 创建一个新的知识库空间 | `space create-space` |
| 查询 | 查询当前账号可见的空间列表 | `space query-space-list` |
| 查询 | 查询某个空间下的节点（文件 / 子文件夹） | `space query-space-node` |

## 参数说明

### space create-space

| 参数 | 必填 | 说明 |
|---|---|---|
| `--title` | 是 | 空间标题，长度 1~36 字符 |
| `--description` | 否 | 空间描述 |

### space query-space-list

| 参数 | 必填 | 说明 |
|---|---|---|
| `--num` | 否 | 分页页码，从 0 开始；每页最多返回 100 个空间 |
| `--order-by` | 否 | 排序方式：`1`=按查看时间，`2`=按编辑时间，`3`=按创建时间 |
| `--query-by` | 否 | 查询范围：`0`=全部，`1`=我创建的，`2`=我加入的 |
| `--descending` | 否 | `true`=降序，`false`=升序 |

> 服务端没有 "前 N 条" 参数；如果只想拿前 5 / 前 10 条，先按业务排序拉第 0 页，再用 `--jq '.spaces[:5]'` 截取。

### space query-space-node

| 参数 | 必填 | 说明 |
|---|---|---|
| `--space-id` | 是 | 空间 ID（来自 `query-space-list` 的 `space_id` 字段） |
| `--parent-id` | 否 | 父节点 ID；不传时返回空间根节点下的内容 |
| `--num` | 否 | 分页页码，从 0 开始；每页返回 20 个节点 |

## 代表性示例

```bash
# 创建一个新空间
tdocs-cli space create-space --title "团队知识库" --description "项目相关文档"

# 列出我创建的空间，按编辑时间倒序，仅看前 5 条
tdocs-cli space query-space-list --query-by 1 --order-by 2 --descending true \
    --jq '.spaces[:5] | .[] | {space_id, title, file_cnt, member_cnt}'

# 查询某个空间根节点下的文件 / 子文件夹
tdocs-cli space query-space-node --space-id <space-id>

# 进入空间内某个子文件夹继续展开
tdocs-cli space query-space-node --space-id <space-id> --parent-id <parent-node-id> --num 0
```

## 与其他命令的衔接

- 拿到 `space query-space-node` 返回的节点 `id` 后，可作为业务命令的 `--parent-id` 用于在该空间内创建文档：例如 `mind create-by-markdown --parent-id <node-id>`、`flowchart create-by-mermaid --parent-id <node-id>` 等。
- 普通"我的文档"目录浏览请使用 `manage list-file`，与本组命令面向场景不同。

## 权威来源

```
tdocs-cli space --help
tdocs-cli space create-space --help
tdocs-cli space query-space-list --help
tdocs-cli space query-space-node --help
```
