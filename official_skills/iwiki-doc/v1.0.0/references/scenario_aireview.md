# 场景：文档 AI 评审

**快捷命令：**
```bash
# 获取文档所在空间的评审规则列表
iwiki-cli aireview list -d 123456

# 获取指定规则的详细内容
iwiki-cli aireview detail 10621 -d 123456

# 也可以直接指定空间 ID
iwiki-cli aireview list -s 789
iwiki-cli aireview detail 10621 -s 789
```

## 核心工具

### 1. aireview list - 获取评审规则列表
**用途：** 获取指定空间下已发布的 AI 评审规则列表
**用法：**
```bash
iwiki-cli aireview list -d <docId>
iwiki-cli aireview list -s <spaceId>
```
**参数：**
| 参数 | 缩写 | 默认值 | 说明 |
|------|------|--------|------|
| `--doc` | `-d` | "" | 文档 ID（自动推断空间 ID） |
| `--space` | `-s` | "" | 空间 ID（直接指定，跳过推断） |

**返回示例：**
```
规则 ID    规则名称
-------  --------
10621    文档规范查询
```

### 2. aireview detail - 获取评审规则详情
**用途：** 获取指定评审规则的详细评审要求（order_desc）
**用法：**
```bash
iwiki-cli aireview detail <ruleId> -d <docId>
iwiki-cli aireview detail <ruleId> -s <spaceId>
```
**参数：**
| 参数 | 缩写 | 默认值 | 说明 |
|------|------|--------|------|
| `--doc` | `-d` | "" | 文档 ID（自动推断空间 ID） |
| `--space` | `-s` | "" | 空间 ID（直接指定，跳过推断） |

**返回示例：**
```
- 准确性：内容与技术实现、业务需求一致，无错误；
- 规范性：格式、术语符合公司标准；
- 实用性：贴合工作场景，具备可操作性；
- 安全性：不包含公司敏感信息。
```

### 3. 其他相关工具
评审流程还需配合以下命令使用：
```bash
# 读取文档内容
iwiki-cli get <docId>

# 获取文档元数据
iwiki-cli metadata <docId>

# 添加评审评论
iwiki-cli comment add <docId> --content "<p>评审建议内容</p>"
```

## 完整评审工作流

### 步骤 1：获取评审规则
```bash
# 获取规则列表
iwiki-cli aireview list -d <docId>

# 获取具体规则的评审要求
iwiki-cli aireview detail <ruleId> -d <docId>
```

### 步骤 2：读取文档内容
```bash
iwiki-cli get <docId>
```

### 步骤 3：执行评审
根据评审规则中的 `order_desc` 要求，逐条对文档内容进行分析和评审：
1. **逐条对照规则**：将文档内容与每条评审标准进行对比
2. **标记问题**：记录不符合规则的具体位置和原因
3. **生成建议**：针对每个问题给出具体的修改建议

### 步骤 4：生成评审报告并创建评论
将评审结果以结构化评论的形式添加到文档：
```bash
iwiki-cli comment add <docId> --content "<评审报告XHTML>"
```

**评审报告格式示例：**
```html
<h2>AI 评审报告</h2>
<p><strong>评审规则：</strong>文档规范查询</p>

<h3>评审结果</h3>
<table>
  <tbody>
    <tr>
      <th>评审维度</th>
      <th>结果</th>
      <th>说明</th>
    </tr>
    <tr>
      <td>准确性</td>
      <td>✅ 通过</td>
      <td>内容与技术实现一致</td>
    </tr>
    <tr>
      <td>规范性</td>
      <td>⚠️ 建议改进</td>
      <td>部分术语不统一</td>
    </tr>
  </tbody>
</table>

<h3>具体建议</h3>
<ol>
  <li><strong>第X节</strong>：建议将"xxx"改为"yyy"，与公司规范统一</li>
  <li><strong>第Y节</strong>：缺少安全性说明，建议补充</li>
</ol>
```

## 实践示例

### 示例 1：对文档执行完整评审
**用户需求：** "帮我评审文档 123456"
**执行步骤：**

1. **获取评审规则列表**
```bash
iwiki-cli aireview list -d 123456
```
输出：
```
规则 ID    规则名称
-------  --------
10621    文档规范查询
```

2. **获取规则详情**
```bash
iwiki-cli aireview detail 10621 -d 123456
```
输出评审标准：
```
- 准确性：内容与技术实现、业务需求一致，无错误；
- 规范性：格式、术语符合公司标准；
...
```

3. **读取文档内容**
```bash
iwiki-cli get 123456
```

4. **按规则逐条评审文档内容**
将文档内容与每条评审标准对比，记录问题和建议。

5. **将评审结果作为评论添加到文档**
```bash
iwiki-cli comment add 123456 --content "<h2>AI 评审报告</h2><p>...</p>"
```

### 示例 2：只查看评审规则
**用户需求：** "看看这个空间有哪些评审规则"
**执行步骤：**
```bash
iwiki-cli aireview list -d 123456
```

### 示例 3：多规则评审
如果空间下有多条规则，需逐一获取详情并分别评审：
```bash
iwiki-cli aireview list -d 123456
# 假设返回多条规则
iwiki-cli aireview detail 10621 -d 123456
iwiki-cli aireview detail 10622 -d 123456
# 综合所有规则的要求进行评审
```

## 注意事项
1. **`-d` 和 `-s` 二选一**：传 `-d` 文档 ID 会自动推断空间 ID；传 `-s` 直接指定空间 ID
2. **隐藏命令**：`aireview` 是隐藏命令，不会出现在 `iwiki-cli --help` 中，但可以正常使用
3. **评论格式**：评审结果以评论形式添加时，内容必须是 XHTML 格式
4. **评审客观性**：评审应严格按照规则中的 `order_desc` 标准执行，保持客观
5. **多规则场景**：如果有多条规则，应综合所有规则的要求生成一份完整报告
