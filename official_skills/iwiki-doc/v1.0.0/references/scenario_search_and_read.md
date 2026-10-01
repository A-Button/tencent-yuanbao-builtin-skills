# 场景：搜索、下载、查看和分析文档

**快捷命令：**
```bash
# 搜索文档
iwiki-cli search "关键词"

# AI 搜索
iwiki-cli search "如何部署？" --ai --limit 5

# 获取文档内容
iwiki-cli get 123456

# 获取文档元数据
iwiki-cli metadata 123456

# 查看文档附件列表
iwiki-cli attachlist 123456

# 下载附件
iwiki-cli download <attachmentid> --output ./images/

# 查询我最近查看的文档
iwiki-cli recent view

# 查询我最近编辑的文档
iwiki-cli recent edit

# 查询空间最近更新
iwiki-cli recent space <spacekey> --limit 10
```

## 核心工具

### 1. 搜索文档
#### search - 传统关键词搜索（首选）
**何时使用：**
- 需要按空间筛选
- 需要精确的关键词匹配
- 需要分页浏览搜索结果（使用 --offset）
**用法：**
```bash
iwiki-cli search "项目需求文档"
iwiki-cli search "项目需求文档" --limit 10 --offset 0 --spaces "12345"
```
**参数：**
| 参数 | 缩写 | 默认值 | 说明 |
|------|------|--------|------|
| `--limit` | `-l` | 5 | 返回结果数量 |
| `--offset` | `-o` | 0 | 分页偏移量 |
| `--spaces` | `-s` | "" | 空间 ID 列表，逗号分隔 |
| `--topics` | `-t` | "" | 专题 ID 列表，逗号分隔 |
| `--ai` | `-a` | false | 启用 AI 搜索模式 |

#### search --ai - AI 语义搜索
**何时使用：**
- 传统搜索无结果时
- 查询词是完整句子或问题
- 需要理解查询意图
**用法：**
```bash
iwiki-cli search "如何配置持续集成流水线？" --ai --limit 10
```

### 2. 读取文档内容
#### get - 获取完整文档
**用途：** 获取文档的完整 Markdown 内容
**用法：**
```bash
iwiki-cli get 123456
```

> ⚠️ **特殊文档类型（企业微信文档）**：
> 当 `metadata` 返回的 `content_type` 为 `TXDOC`（企微文档）或 `TXEXCEL`（企微表格）时，
> 文档实际内容存储在企业微信侧，**`iwiki-cli get` 无法读取真实正文**。
> 必须改用 `wecom-cli` 读取，详见下文【读取企业微信文档（TXDOC / TXEXCEL）】。

#### metadata - 获取文档元数据
**用途：** 了解文档的基本信息，**也是判断是否需要走企微读取链路的入口**
**用法：**
```bash
iwiki-cli metadata 123456
```

**返回信息：**
- 创建时间和作者
- 最后修改时间和修改者
- 文档标题、`content_type`
- 所属空间
- `ext.txdoc_fileid` / `ext.txdoc_type`：仅当 `content_type` 为 `TXDOC` / `TXEXCEL` 时存在，分别表示对应的企业微信原始文档 ID 和类型

#### 读取企业微信文档（TXDOC / TXEXCEL）
**适用场景**：`metadata` 返回的 `content_type` ∈ { `TXDOC`, `TXEXCEL` }。文档正文不在 iwiki 侧，需要使用 `wecom-cli` 通过 `ext.txdoc_fileid` 读取。

**品类判定**（综合 iwiki `content_type` 与企微 docid/URL 模式）：
> `TXDOC` / `TXEXCEL` 统一走 `get_doc_content`。

##### 步骤 1：安装 wecom-cli
```bash
wecom-cli --version 2>/dev/null || npm install -g @wecom/cli@0.1.8
```
##### 步骤 2：检查授权
```bash
wecom-cli auth show --auth-status
```
- 输出 `authorized` → 可用
- 输出 `unauthorized` → 执行 `wecom-cli init --noninteractive`，扫码授权后自动退出
##### 步骤 3：读取内容
**A. 文档 / 表格**（`get_doc_content`，异步轮询）
> **重要**：`get_doc_content` 采用异步轮询机制，不是一次调用就能拿到内容。首次调用返回 `task_done: false` 和 `task_id` 是**正常现象**，不是报错（`errcode: 0` 即为成功）。需要携带返回的 `task_id` 再次调用，直到 `task_done: true` 时 `content` 字段才包含完整内容。

1. **取出企微 docid**：从 `iwiki-cli metadata` 返回的 `ext.txdoc_fileid` 字段取得。
2. **首次调用**（不传 `task_id`）：
```bash
wecom-cli doc get_doc_content '{"docid": "<txdoc_fileid>", "type": 2}'
```
3. **检查返回**：若 `task_done: false`，记录返回的 `task_id`。
4. **携带 task_id 继续轮询**：
```bash
wecom-cli doc get_doc_content '{"docid": "<txdoc_fileid>", "type": 2, "task_id": "<TASK_ID>"}'
```
5. **重复 3-4**，直到 `task_done: true`，此时 `content` 字段即为完整 Markdown 内容。
##### 注意事项
- `get_doc_content` 的 `type` 固定 `2`、`smartpage_export_task` 的 `content_type` 固定 `1`，都表示返回 Markdown。
- `errcode: 0` 仅表示「调用成功」，**不代表内容已就绪**，必须看 `task_done`。
- iwiki 的 `ext.txdoc_fileid` 即企微 `docid`，可直接传入。

### 3. 查询最近文档

#### recent view - 最近查看的文档
**何时使用：**
- 用户想回顾自己最近看过的文档
- 用户说"我之前看过一个文档，帮我找找"
- 需要总结用户近期关注的内容

**用法：**
```bash
iwiki-cli recent view
iwiki-cli recent view --page 1 --page_size 15
```

#### recent edit - 最近编辑的文档
**何时使用：**
- 用户想查看自己最近写的或修改过的文档
- 用户说"总结一下我最近写的文档"

**用法：**
```bash
iwiki-cli recent edit
iwiki-cli recent edit --page 1 --page_size 10
```

#### recent space - 空间最近更新
**何时使用：**
- 用户想了解某个空间最近的变更动态

**用法：**
```bash
iwiki-cli recent space <spacekey> --limit 10
```

### 4. 查看文档结构
#### tree - 获取目录树
**用途：** 查看空间的文档结构
**用法：**
```bash
iwiki-cli tree --parent 12345
```

### 5. 查看附件列表
#### attachlist - 查看文档的附件列表
**用途：** 获取指定文档下的所有附件信息，便于确认附件 ID 后再下载
**用法：**
```bash
iwiki-cli attachlist 123456
iwiki-cli attachlist 123456 -l 20
iwiki-cli attachlist 123456 --start 10
```
**参数：**
| 参数 | 缩写 | 默认值 | 说明 |
|------|------|--------|------|
| `--limit` | `-l` | 10 | 每页返回数量 |
| `--start` | `-s` | 0 | 起始偏移量（分页） |

### 6. 下载附件
#### download - 下载附件文件
**用途：** 根据附件 ID 下载附件到本地
**用法：**
```bash
iwiki-cli download 78910
iwiki-cli download 78910 --output ./images/
```

## 实践示例
### 示例 1：查看文档元数据和搜索相关文档
**用户需求：** "查看文档 123456 的基本信息"
**执行步骤：**
1. **获取文档元数据**
```bash
iwiki-cli metadata 123456
```
2. **获取文档内容**
```bash
iwiki-cli get 123456
```

### 示例 2：搜索结果翻页
**用户需求：** "搜索'API文档'，查看第3页结果"
**执行步骤：**
1. **计算 offset**
```
每页 5 条（默认），第 3 页的 offset = (3-1) * 5 = 10
```
2. **执行搜索**
```bash
iwiki-cli search "API文档" --offset 10
```

### 示例 3：使用 AI 搜索并获取文档
**用户需求：** "搜索如何部署微服务"
**执行步骤：**
1. **AI 搜索**
```bash
iwiki-cli search "如何部署微服务" --ai --limit 5
```
2. **获取文档内容**
```bash
iwiki-cli get 123456
```

### 示例 4：浏览空间目录结构
**用户需求：** "查看空间的文档树"
**执行步骤：**
1. **获取空间信息**
```bash
iwiki-cli space devcloud
```
2. **获取目录树**
```bash
iwiki-cli tree --parent 12345
```
### 示例 5：总结用户最近写的文档
**用户需求：** "总结一下我最近写的文档"
**执行步骤：**
1. **获取最近编辑文档列表**
```bash
iwiki-cli recent edit --page_size 10
```
2. **逐一获取文档内容**（根据返回的 doc_id）
```bash
iwiki-cli get <doc_id>
```
3. **汇总分析**：对获取到的文档内容进行归类、提炼核心要点，向用户呈现总结。

### 示例 6：读取企业微信文档（TXDOC / TXEXCEL）
**用户需求：** "帮我看下这篇 iwiki 文档 7890123 的内容"
**执行步骤：**
1. **先取 metadata 判断品类**
```bash
iwiki-cli metadata 7890123
```
返回片段：
```json
{
  "content_type": "TXDOC",
  "ext": { "txdoc_fileid": "DOC_xxx", "txdoc_type": "..." }
}
```
2. **判定为企微文档，改走 wecom-cli**（首次调用）
```bash
wecom-cli auth show --auth-status   # 确认已授权
wecom-cli doc get_doc_content '{"docid": "DOC_xxx", "type": 2}'
```
3. **轮询直到 `task_done: true`**
```bash
wecom-cli doc get_doc_content '{"docid": "DOC_xxx", "type": 2, "task_id": "<上一步返回的 task_id>"}'
```
4. **取 `content` 字段** 作为文档正文进行后续分析。

> 若 `content_type` 为其他值（如 `DOC`），直接用 `iwiki-cli get 7890123` 即可，无需 wecom-cli。

### 示例 7：回顾最近浏览的文档
**用户需求：** "帮我找找我之前看过的一篇关于XX的文档"
**执行步骤：**
1. **获取最近查看列表**
```bash
iwiki-cli recent view --page_size 15
```
2. **在结果中匹配关键词**：根据标题筛选可能的目标文档
3. **获取文档内容确认**
```bash
iwiki-cli get <doc_id>
```

## 错误处理

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| 搜索无结果 | 关键词不准确 | 尝试 AI 语义搜索或调整关键词 |
| 文档不存在 | docid 错误或已删除 | 确认 docid 是否正确 |
| 无权限访问 | 用户无查看权限 | 联系文档所有者申请权限 |
| 附件下载失败 | attachmentid 错误 | 确认附件 ID 是否正确 |

## 注意事项

1. **搜索结果可能很多：** 使用 --offset 分页，避免一次性获取过多结果
2. **AI 搜索有限额：** 优先使用传统搜索，AI 搜索作为补充
3. **附件链接有时效：** 下载链接是临时的，需要及时使用
