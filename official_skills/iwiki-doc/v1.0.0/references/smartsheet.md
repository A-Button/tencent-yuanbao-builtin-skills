# 场景：多维表格操作

## 核心工具

### 1. smartsheetGetFields - 获取字段结构
**何时使用：**
- 在操作表格前了解字段结构
- 确认字段名称和类型
- 查看字段配置信息
**参数：**
```json
{
  "doc_id": "123456"  // 多维表格文档 ID（字符串或数字）
}
```

### 2. smartsheetGetViews - 获取视图列表
**何时使用：**
- 查看表格有哪些视图（表格/看板/甘特图等）
- 获取特定视图 ID
**参数：**
```json
{
  "doc_id": "123456"  // 多维表格文档 ID
}
```

### 3. smartsheetGetRecords - 查询记录
**何时使用：**
- 查询表格数据
- 筛选符合条件的记录
- 获取特定字段的数据
**参数：**
```json
{
  "doc_id": "123456",                         // 多维表格文档 ID（数字）
  "pageNum": 1,                             // 页码，默认 1
  "pageSize": 100,                          // 每页记录数，默认 100，最大 200
  "filterByFormula": "{状态}='进行中'",      // 筛选条件（可选）
  "fields": "标题,负责人,优先级",            // 返回字段（可选，逗号分隔）
  "sort": "优先级 DESC",                     // 排序（可选）
  "viewId": "view123"                       // 指定视图 ID（可选）
}
```

### 4. smartsheetAddRecords - 批量添加记录
**何时使用：**
- 向表格添加新记录
- 批量导入数据
**参数：**
```json
{
  "doc_id": "123456",
  "fieldKey": "name",  // 推荐用 "name"（字段名），字段名重复时用 "id"
  "records": [
    {
      "fields": {
        "标题": "需求分析",
        "负责人": "张三",
        "状态": "待处理",
        "优先级": "高"
      }
    }
  ]
}
```

### 5. smartsheetUpdateRecords - 批量更新记录
**何时使用：**
- 修改已有记录的字段值
- 批量更新状态
**参数：**
```json
{
  "doc_id": 123456,
  "fieldKey": "name",  // 可选，推荐 "name"
  "records": [
    {
      "recordId": "rec123",  // 记录 ID（必填）
      "fields": {
        "状态": "已完成"     // 要更新的字段
      }
    }
  ]
}
```

### 6. smartsheetDeleteRecords - 批量删除记录
**⚠️ 高危操作：数据删除后不可恢复**
**何时使用：**
- 删除不需要的记录
- **必须用户明确确认后才能执行**
**参数：**
```json
{
  "doc_id": 123456,
  "record_ids": ["rec123", "rec456"]  // 要删除的记录 ID 数组
}
```

### 7. smartsheetAddField - 添加字段
**何时使用：**
- 为表格添加新列
- 扩展表格数据结构
**参数：**
```json
{
  "doc_id": 123456,
  "type": "SingleSelect",  // 字段类型（见下方支持的类型）
  "name": "优先级",         // 字段名称
  "property": {                    // 字段配置（可选，根据字段类型不同）
    "options": [
      {"name": "高", "color": "red"},
      {"name": "中", "color": "yellow"},
      {"name": "低", "color": "green"}
    ]
  }
}
```

## 支持的字段类型

| 分类 | 字段类型 | 描述 | 可写入 |
|------|----------|------|--------|
| **文本类** | `SingleText` | 单行文本 | ✅ |
| | `Text` | 多行文本 | ✅ |
| **选择类** | `SingleSelect` | 单选 | ✅ |
| | `MultiSelect` | 多选 | ✅ |
| **数值类** | `Number` / `Currency` / `Percent` / `Rating` | 数字/货币/百分比/评分 | ✅ |
| **日期** | `DateTime` | 日期时间 | ✅ |
| | `CreatedTime` / `LastModifiedTime` | 创建/修改时间（自动） | ❌ |
| **人员** | `Member` | 成员 | ✅ |
| | `CreatedBy` / `LastModifiedBy` | 创建/修改人（自动） | ❌ |
| **关联** | `OneWayLink` / `TwoWayLink` | 单向/双向关联 | ✅ |
| **其他** | `Attachment` / `Checkbox` / `URL` / `Phone` / `Email` | 附件/复选框/链接/电话/邮箱 | ✅ |
| | `WorkDoc` / `MagicLookUp` / `Button` | 工作文档/神奇引用/按钮 | ✅ |
| | `Formula` / `AutoNumber` | 公式/自动编号（自动计算） | ❌ |



### 8. smartsheetDeleteField - 删除字段
**⚠️ 高危操作：字段及其所有数据删除后不可恢复**
**何时使用：**
- 删除不需要的字段
- **必须用户明确确认后才能执行**
**参数：**
```json
{
  "doc_id": "123456",
  "fieldId": "fld123"  // 要删除的字段 ID
}
```

## 实践示例

### 示例 1：查询并分析表格数据
**用户需求：** "查看项目管理表格中所有进行中的任务"
**执行步骤：**
1. **先获取字段结构**
```bash
python scripts/connect_mcp.py call smartsheetGetFields '{"doc_id": "123456"}'
```
2. **查询符合条件的记录**
```bash
python scripts/connect_mcp.py call smartsheetGetRecords '{
  "doc_id": "123456",
  "pageNum": 1,
  "pageSize": 50,
  "filterByFormula": "{状态}='\''进行中'\''",
  "fields": "标题,负责人,优先级,截止日期",
  "sort": "优先级 DESC"
}'
```

### 示例 2：批量添加任务
**用户需求：** "在任务表格中添加本周的新任务"
**执行步骤：**
1. **确认字段结构**（确保字段名正确）
```bash
python scripts/connect_mcp.py call smartsheetGetFields '{"doc_id": "123456"}'
```
2. **批量添加记录**
```bash
python scripts/connect_mcp.py call smartsheetAddRecords '{
  "doc_id": "123456",
  "fieldKey": "name",
  "records": [
    {
      "fields": {
        "标题": "需求分析",
        "负责人": "张三",
        "状态": "待处理",
        "优先级": "高",
        "截止日期": "2026-04-20"
      }
    },
    {
      "fields": {
        "标题": "技术方案设计",
        "负责人": "李四",
        "状态": "待处理",
        "优先级": "中",
        "截止日期": "2026-04-22"
      }
    }
  ]
}'
```

### 示例 3：更新任务状态
**用户需求：** "将张三负责的所有任务标记为已完成"
**执行步骤：**
1. **查询需要更新的记录**
```bash
python scripts/connect_mcp.py call smartsheetGetRecords '{
  "doc_id": "123456",
  "filterByFormula": "{负责人}='\''张三'\''"
}'
```
2. **根据返回的 recordId 批量更新**
```bash
python scripts/connect_mcp.py call smartsheetUpdateRecords '{
  "doc_id": 123456,
  "fieldKey": "name",
  "records": [
    {"recordId": "rec123", "fields": {"状态": "已完成"}},
    {"recordId": "rec456", "fields": {"状态": "已完成"}}
  ]
}'
```

### 示例 4：为表格添加新字段
**用户需求：** "在任务表格中添加一个'优先级'单选字段"
**执行步骤：**
```bash
python scripts/connect_mcp.py call smartsheetAddField '{
  "doc_id": 123456,
  "type": "SingleSelect",
  "name": "优先级",
  "property": {
    "options": [
      {"name": "高", "color": "red"},
      {"name": "中", "color": "yellow"},
      {"name": "低", "color": "green"}
    ]
  }
}'
```

### 示例 5：上传图片到表格附件字段
**用户需求：** "将截图上传到任务表格的附件字段"
**执行步骤：**

#### 方法一：使用 smartsheet 命令（推荐，一步完成上传）
```bash
# 上传图片到多维表格，获取 ext 附件信息
python scripts/connect_mcp.py smartsheet ./screenshot.png 4019549905
```

**输出示例：**
```json
📊 多维表格图片上传结果:
================================================================================
✅ 上传成功!
   文件名:     screenshot.png
   文件大小:   186.5 KB
   图片尺寸:   972×1498
   文件类型:   image/png
   表格 ID:    4019549905

📋 ext 内容（用于写入表格）:
--------------------------------------------------------------------------------
{
  "token": "space/2026/04/17/a39f3da15d28489ca729495490735e53",
  "name": "screenshot.png",
  "size": 190972,
  "width": 972,
  "height": 1498,
  "mimeType": "image/png"
}
--------------------------------------------------------------------------------

⚠️  提醒: 请将上述 ext 的内容写入对应表格的附件字段
```

### 示例 6：删除过期记录
**用户需求：** "删除已归档的旧任务"
**执行步骤：**
1. **查询要删除的记录**
```bash
python scripts/connect_mcp.py call smartsheetGetRecords '{
  "doc_id": "123456",
  "filterByFormula": "{状态}='\''已归档'\''"
}'
```
2. **向用户确认删除操作**
```
⚠️ 即将删除 5 条记录，删除后不可恢复，是否确认？
```
3. **用户确认后执行删除**
```bash
python scripts/connect_mcp.py call smartsheetDeleteRecords '{
  "doc_id": 123456,
  "record_ids": ["rec123", "rec456", "rec789"]
}'
```



## 支持的视图类型

| 视图类型 | 英文标识 | 适用场景 |
|----------|----------|----------|
| 表格 | `Grid` | 数据查看、编辑 |
| 画廊 | `Gallery` | 图片展示、产品目录 |
| 看板 | `Kanban` | 任务管理、项目进度 |
| 甘特图 | `Gantt` | 项目规划、进度追踪 |
| 日历 | `Calendar` | 日程安排、事件管理 |
| 架构 | `Architecture` | 层级结构展示 |

## 筛选条件语法

支持的筛选表达式：
```
{字段名}='值'              # 等于
{字段名}!='值'             # 不等于
{字段名}>'100'            # 大于（数值）
{字段名}<'100'            # 小于（数值）
AND({条件1}, {条件2})      # 与
OR({条件1}, {条件2})       # 或
```

**示例：**
```bash
# 高优先级且未完成的任务
filterByFormula="AND({优先级}='高', {状态}!='已完成')"

# 本周截止的任务
filterByFormula="{截止日期}>'2026-04-14'"
```

## 重要注意事项

### ⚠️ 高危操作
- **`smartsheetDeleteField`** 和 **`smartsheetDeleteRecords`** 删除后数据不可恢复
- 执行前必须向用户说明影响范围
- 必须获得用户明确确认后才能执行

### 📎 附件字段操作
- **上传图片流程**：先使用 `smartsheet` 命令上传图片获取 ext 内容，再使用 `smartsheetUpdateRecords` 将 ext 写入附件字段
- **附件字段格式**：附件字段的值是数组类型，每个附件是一个包含 `token`、`name`、`size`、`width`、`height`、`mimeType` 的对象
- **追加附件**：如需追加附件而非替换，先用 `smartsheetGetRecords` 获取现有附件数组，将新附件添加到数组末尾后更新
- **灰度功能**：图片上传功能使用了灰度接口（`x-scope: gray`），需要确保有访问权限

### 💡 最佳实践
1. **操作前先验证**：使用 `smartsheetGetFields` 确认字段名和类型
2. **fieldKey 推荐用 `name`**：更直观，只有字段名重复时才用 `id`
3. **分页规范**：单次最多 200 条，大数据量必须分页处理
4. **自动字段不可写**：`Formula`、`AutoNumber`、`CreatedTime`、`LastModifiedTime`、`CreatedBy`、`LastModifiedBy` 等字段只能查询，添加/更新记录时不要包含这些字段
5. **小批量测试**：批量操作前先用少量数据测试，确认无误后再批量执行
6. **图片上传推荐方法**：优先使用 `python scripts/connect_mcp.py smartsheet` 命令，它封装了完整的上传流程，比手动调用多个 API 更简单可靠

---

- [← 返回主 Skill 文档](../SKILL.md)
