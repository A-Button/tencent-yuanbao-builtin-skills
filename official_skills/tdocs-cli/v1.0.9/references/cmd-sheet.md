# cmd-sheet — 在线 Sheet 入口

仅对**已有在线 Sheet 的明确小改**使用 `tdocs-cli sheet ...`。新建或复杂修改转为本地处理，验收后通过 `workflow import-file` 导入为新资源；多维表格不属于本入口。

## 能力分类

本表只列当前允许的在线小改能力，不是完整 `sheet` 命令清单；未列出的子命令均不在白名单内。

| 分类 | 能力 | CLI 命令 |
|---|---|---|
| 子表识别 | 获取子表 ID、名称和行列信息 | `sheet get-sheet-info` |
| 区域读取 | 批量读取目标区域的值 | `sheet get-cell-data` |
| 批量写值 | 一次写入多个单元格的字符串、数值、布尔值或公式 | `sheet set-range-value` |
| 区域样式 | 一次设置连续区域的字体、颜色、填充和对齐 | `sheet set-cell-style` |
| 行列结构 | 一次插入连续多行或多列 | `sheet insert-dimension` |
| 行列结构 | 一次删除连续多行或多列 | `sheet delete-dimension` |

## 核心概念

| 概念 | 说明 |
|---|---|
| `file_id` | 已有在线 Sheet 的资源身份；全程复用同一值 |
| `sheet_id` | 子表 ID，来自 `get-sheet-info`，不是工作表名称 |
| `row/col` | 从 `0` 开始的行列索引 |
| 调用预算 | 最多一次批量读、一次主写、一次定点复核；未知 `sheet_id` 时可额外查询一次 |

## 典型工作流

- **批量改值**：必要时 `get-sheet-info` → 一次 `get-cell-data` → 构造完整 values → 一次 `set-range-value` → 定点复核。
- **区域样式**：一次 `get-cell-data` 确认连续区域 → 一次 `set-cell-style` → 复核目标值未被破坏；当前 API 不返回具体样式字段。
- **插入或删除行列**：一次 `get-cell-data` 确认零基位置 → 一次 `insert-dimension` / `delete-dimension --count` → 重新读取受影响区域。
- **现成文件只导入**：用户提供 `.xlsx` / `.xls` 且不改内容时，直接单次 `workflow import-file`。
- **新建或复杂修改**：复用本地源文件或先导出，使用可用的本地表格能力修改并验收后单次导入新资源；原链接不覆盖。

## 硬性约束

1. 只允许操作已有在线 Sheet，禁止 `manage create-file --type 2`。
2. 执行前必须能构造完整 payload；禁止边读边写或逐格循环。
3. 多格值必须合并为一次 `set-range-value`，禁止多个 `set-cell-value`。
4. 连续区域样式和行列结构分别使用一次区域 / `count` 操作。
5. 禁止 `operation-sheet`；其余未列入白名单的 `sheet` 子命令也不得调用。
6. 新建、大批量、多工作表、复杂公式/图表/结构重排或需要精确验证公式文本时，转为本地处理。
7. smartsheet / 多维表格仍全面禁用，不能通过本入口绕过。

## 通用约定

- 字面 `file_id` 使用单引号，如 `--file-id '<file_id>'`；shell 变量使用 `--file-id "$fid"`。
- 读写与复核始终使用同一 `file_id` / `sheet_id`。
- 行列索引从 `0` 开始；读取范围的结束行列包含边界。

```bash
tdocs-cli sheet set-cell-style \
    --file-id '<file_id>' --sheet-id '<sheet_id>' --start-row 0 --start-col 0 \
    --style '{"font":{"bold":true}}' --output-format json
```

`sheet set-cell-style` 的业务样式对象优先使用 `--style`；旧版 `--format '<JSON对象>'` 仍兼容。该命令需要同时指定 CLI 输出格式时，使用无歧义的 `--output-format`。

## 渐进式参考

按当前任务只加载需要的文档：

| 场景 | 参考文档 |
|---|---|
| 判断在线小改是否准入、控制调用预算、写后验收 | `sheet/edit-guide.md` |
| 查询坐标、批量 payload、命令差异和实测边界 | `sheet/entry.md` |

## 权威来源

```text
tdocs-cli sheet --help
tdocs-cli sheet <command> --help
```

命令参数以当前 `--help` 为准；是否允许调用仍以根 `SKILL.md` 的硬约束为准。
