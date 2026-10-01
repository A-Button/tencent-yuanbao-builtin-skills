# 场景：为文档添加评论和批注

**快捷命令：**
```bash
# 获取文档评论
iwiki-cli comment get 123456

# 获取第2页评论
iwiki-cli comment get 123456 --page 2

# 获取划词批注
iwiki-cli comment get 123456 --inline

# 添加评论（注意XHTML格式）
iwiki-cli comment add 123456 --content "<p>这是评论内容</p>"

# 回复评论
iwiki-cli comment add 123456 --content "<p>我同意你的观点</p>" --parent 789

# 从文件读取评论内容
iwiki-cli comment add 123456 --file ./comment.html
```

## 核心工具
### 1. comment get - 获取文档评论
**用途：** 获取文档的评论列表，支持分页和多级评论结构
**用法：**
```bash
iwiki-cli comment get 123456
iwiki-cli comment get 123456 --page 2
```
**参数：**
| 参数 | 缩写 | 默认值 | 说明 |
|------|------|--------|------|
| `--page` | `-p` | 1 | 页码，每页 10 条 |
| `--inline` | `-i` | false | 获取划词批注而非普通评论 |

### 2. comment get --inline - 获取划词批注
**用途：** 获取文档中的划词批注（内联评论）
**用法：**
```bash
iwiki-cli comment get 123456 --inline
```

**返回结构：**
```json
{
  "inline_comments": [
    {
      "id": "inline_001",
      "content": "<p>这里需要补充说明</p>",
      "creator": "wangwu",
      "reply_to": "zhangsan",
      "mark_content": "核心逻辑",
      "is_deleted": false
    }
  ]
}
```

### 3. comment add - 添加评论
**用途：** 为文档添加顶级评论或回复其他评论
**用法：**
```bash
# 添加顶级评论
iwiki-cli comment add 123456 --content "<p>这是我的评论内容</p>"

# 回复评论
iwiki-cli comment add 123456 --content "<p>回复内容</p>" --parent 789

# 从文件读取评论
iwiki-cli comment add 123456 --file ./comment.html
```
**参数：**
| 参数 | 缩写 | 默认值 | 说明 |
|------|------|--------|------|
| `--content` | `-c` | "" | 评论内容 |
| `--parent` | `-r` | 0 | 父评论 ID（回复时指定，0=顶级评论） |
| `--file` | `-f` | "" | 从文件读取评论内容 |

**重要：** 评论内容必须使用 XHTML 格式！

## XHTML 格式规范
### 基本元素
评论内容必须用合适的 XHTML 标签包装：
```html
<!-- 段落 -->
<p>这是一段评论</p>

<!-- 标题 -->
<h1>一级标题</h1>
<h2>二级标题</h2>

<!-- 强调和斜体 -->
<strong>加粗文本</strong>
<em>斜体文本</em>

<!-- 代码 -->
<code>const x = 1;</code>

<!-- 列表 -->
<ul>
  <li>项目1</li>
  <li>项目2</li>
</ul>

<ol>
  <li>第一步</li>
  <li>第二步</li>
</ol>
```

### 表格结构

```html
<table>
  <tbody>
    <tr>
      <th>列名1</th>
      <th>列名2</th>
    </tr>
    <tr>
      <td>数据1</td>
      <td>数据2</td>
    </tr>
  </tbody>
</table>
```

### 换行和格式

```html
<!-- 换行使用 <br /> -->
<p>第一行<br />第二行</p>

<!-- 多段落 -->
<p>第一段内容</p>
<p>第二段内容</p>
```

## 实践示例
### 示例 1：查看文档的所有评论
**用户需求：** "查看文档 123456 的所有评论"
**执行步骤：**
1. **获取第一页评论**
```bash
iwiki-cli comment get 123456
```
2. **计算总页数**
```
如果 total = 25，每页 10 条
总页数 = ceil(25 / 10) = 3 页
```
3. **递归获取所有页**
```bash
iwiki-cli comment get 123456 --page 2
iwiki-cli comment get 123456 --page 3
```

4. **整理并展示**
```
- 展示所有顶级评论
- 对每个评论展示其回复（next_level_comments）
```

### 示例 2：为文档添加评论
**用户需求：** "在文档 123456 中添加评论：'这个方案需要考虑性能问题'"
**执行步骤：**
```bash
iwiki-cli comment add 123456 --content "<p>这个方案需要考虑性能问题</p>"
```

### 示例 3：回复特定评论
**用户需求：** "回复评论 ID 为 789 的评论：'我同意，建议增加缓存'"
**执行步骤：**
```bash
iwiki-cli comment add 123456 --content "<p>我同意，建议增加缓存</p>" --parent 789
```
## 注意事项
1. **评论内容必须是 XHTML：** 纯文本会被拒绝，至少要用 `<p>` 包装
2. **分页获取评论：** 默认每页 10 条，超过时需要翻页
3. **多级回复结构：** 评论可能有多层嵌套，需要递归处理
4. **划词批注独立：** `--inline` 和普通评论返回不同类型的评论
5. **高危操作需确认：** 删除评论等操作需要用户二次确认（如果未来支持）
