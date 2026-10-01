# cmd-slide — 已有在线 PPT 原地小改

使用 `tdocs-cli slide ...` 对**已有在线 PPT** 做白名单内的原地小改：改文字、调样式、增删形状与图片、增删页，以及有限表格操作。全程复用同一 `file_id`，链接不变。

**新建 PPT 不走本入口**：先用可用的本地 PPT 创建能力产出并验收 `.pptx`，再用 `workflow import-file` 单次导入；不要调用 tdocs-cli 的 AI 生成能力，也不要用 `slide` 从空白文档逐页搭建。

## 能力分类

本表只列已在本入口开放的能力，不是完整 `slide` 命令清单；未列出的子命令（动画、图表、批注、分组、节编辑、主题、新建表格）当前不在白名单内。

| 分类 | 能力 | CLI 命令 |
|---|---|---|
| 发现 | 总页数、`slide_ids`、页面尺寸 | `slide-get-info` |
| 发现 | 某页全部形状摘要（**`shape_id` 的来源**） | `slide-get-page-info` |
| 发现 | 母版页信息 | `slide-get-master-info` |
| 发现 | 节结构（仅作为移动页前的只读检查） | `slide-get-sections` |
| 文本 | 读取形状文本与样式区间 | `slide-get-text` |
| 文本 | 覆盖 / 追加 / 插入 / 删除文本 | `slide-set-text`、`slide-append-text`、`slide-insert-text`、`slide-delete-text` |
| 文本 | 全文查找、按页查找替换 | `slide-find-text`、`slide-find-replace-text` |
| 文本 | 字符级样式（粗斜体、颜色、字体、字号） | `slide-set-text-property` |
| 形状 | 新增文本框 / 形状 / 线条箭头 / 图片 | `slide-add-text`、`slide-add-texts`、`slide-add-shape`、`slide-add-shapes`、`slide-add-line-shape`、`slide-add-line-shapes`、`slide-add-image` |
| 形状 | 改属性（颜色、边框、位置、尺寸、旋转） | `slide-set-shape-properties` |
| 形状 | 调层级、删除 | `slide-reorder-shape`、`slide-remove-shapes` |
| 页面 | 增 / 删 / 复制 / 移动幻灯片 | `slide-add-slide`、`slide-add-slides`、`slide-remove-slide`、`slide-duplicate-slide`、`slide-move-slide` |
| 页面 | 页背景与可见性 | `slide-set-page-properties` |
| 页面 | 页码 / 日期 / 备注 / 页脚 | `slide-add-page-number`、`slide-add-datetime`、`slide-add-notes`、`slide-add-footer` |
| 有限表格 | 修改已有表格的单元格 | `slide-set-cell-text` |
| 有限表格 | 增删行列、合并与取消合并 | `slide-insert-table-rows`、`slide-insert-table-cols`、`slide-delete-table-rows`、`slide-delete-table-cols`、`slide-merge-table-cells`、`slide-unmerge-table-cells` |

## 核心概念

| 概念 | 说明 |
|---|---|
| `file_id` | 在线 PPT 的资源身份，编辑全程复用同一值；与 `--file-url` 二选一 |
| `page_index` | 页索引，**从 0 开始**。所有页级命令都用它定位 |
| `shape_id` | 形状身份，只能来自在线命令的真实返回，**禁止编造或猜测**。`slide-get-page-info` 的字段名是 `id`，填参数时才叫 `--shape-id`；新增命令若未返回 ID，就重新读取页面结构 |
| 坐标与尺寸 | `--x` / `--y` / `--w` / `--h`，一律传**磅（pt）**，指元素左上角。不要传像素，也不要换算成 EMU（1pt = 12700 EMU 仅供理解，服务端收的就是 pt） |
| 文本范围 | `--index` 起始位置 + `--count` 长度，**不是** `begin/end` 这种起止对；单位是 UTF-16 码元，与 `slide-get-text` 的 `length` 同口径 |
| 颜色 | 6 位十六进制且**不带 `#`**，如 `FF0000`；部分属性传 `none` 表示移除 |
| 透明度 | `--fill-alpha` / `--border-alpha` 取 0~100，**0 = 完全不透明**，100 = 完全透明 |

结构层次：`file_id` → 幻灯片页（`page_index`）→ 形状（`shape_id`）→ 文本区间（`index` + `count`）

## 代表性示例

```bash
# 1. 先发现：拿总页数
tdocs-cli slide slide-get-info --file-id '<file_id>'

# 2. 再定位：拿目标页所有形状，从中挑出要改的 shape_id
tdocs-cli slide slide-get-page-info --file-id '<file_id>' --page-index 2

# 3. 读原文（改之前先看清楚现有内容与样式区间）
tdocs-cli slide slide-get-text --file-id '<file_id>' --page-index 2 --shape-id '<shape_id>'

# 4. 改：整段覆盖
tdocs-cli slide slide-set-text --file-id '<file_id>' --page-index 2 \
    --shape-id '<shape_id>' --text "2026 年第一季度经营回顾"

# 5. 改样式：--count 用第 3 步返回的 length，不要自己数字符
tdocs-cli slide slide-set-text-property --file-id '<file_id>' --page-index 2 \
    --shape-id '<shape_id>' --index 0 --count <length> --bold true --color 'FF0000'

# 6. 新增一个文本框（w/h 必须 > 0）
tdocs-cli slide slide-add-text --file-id '<file_id>' --page-index 2 \
    --x 60 --y 320 --w 400 --h 40 --text "数据来源：财务部" --font-size 12

# 7. 验收：回读同一形状，确认改动生效
tdocs-cli slide slide-get-text --file-id '<file_id>' --page-index 2 --shape-id '<shape_id>'
```

## 硬性约束

1. **先发现再编辑**：任何写操作前先 `slide-get-info` 确认页数；改动落到某个形状上时（文本、样式、形状属性、表格）还须先 `slide-get-page-info` 拿到真实 `shape_id`。纯页级操作无需形状发现。禁止猜测 `page_index` 或 `shape_id`。
2. **在线身份必须重新发现**：本地 PPT 的页号、shape 引用和内部 ID 不能用于在线文档。`shape_id` 只用在线命令实际返回的原值，不拼接、不按格式猜测。新增命令返回中有 ID 就直接复用；没有就重新 `slide-get-page-info`，不要假设固定返回结构。
3. **新建 PPT 不走 slide**：新建只导入已完成并验收的本地 `.pptx`，禁止 tdocs-cli AI 生成路径。
4. **原地小改优先，复杂改动生成 V2**：白名单内能力复用原 `file_id`。无法可靠完成的复杂重构先说明限制并征得用户同意，再导出当前版本或复用本地源文件生成 V2；新版上传并验收前禁止删除旧版，版本保留与清理按 `cmd-manage.md` 执行。
   **删页不是删文档**：`slide-remove-slide` 删的是文档内的一页，属本入口白名单，用户要求"删掉第 N 页"照做即可；`manage delete-file` 删的是整篇文档，仍按 `cmd-manage.md`「删除文档白名单（硬性约束）」执行。两者不要混。
5. **查帮助统一用 `-h`**：使用 `tdocs-cli slide <command> -h` 核对参数，不维护容易过期的例外命令清单。
6. **新增形状必须可见**：`slide-add-shape` / `slide-add-shapes` 必须至少设置 `--fill-color` 或 `--border-color` 之一，否则形状对用户不可见，调用会被拒绝。
7. **图片禁用外链**：`slide-add-image` 不接受 http(s) 远程 URL，只接受已上传的 `--image-id` 或 base64 `--content`（仅适合小图）。
8. **箭头要分清**：`rect` / `ellipse` / `rightArrow` 等是**图形预设块**，用 `slide-add-shape`；从起点到终点的**线条箭头**用 `slide-add-line-shape` 并设 `--line-type arrow`。用户给了起点终点或说"把 A 和 B 连起来"时按线条箭头执行；只笼统说"加个箭头"、看不出要连什么时才问清。
9. **失败先诊断，禁止盲目重试**：`retcode 50000` 是无明确诊断价值的兜底错误。不要仅因文案显示“服务繁忙”就 `sleep` 后原样重试；先核对参数、在线返回的 ID、索引和白名单能力。没有新的诊断依据时停止重复调用，并按第 4 条安全降级。
10. **未开放的子命令不得调用**：动画、图表、批注、分组、节编辑、主题相关命令当前不在白名单内；`slide-get-sections` 仅作为移动页前的只读检查。用户要求未开放能力时说明限制，并让用户选择前端操作或按第 4 条生成 V2；不要猜测命令或绕过白名单。

## 渐进式参考

按当前任务只加载需要的文档：

| 场景 | 参考文档 |
|---|---|
| 编辑工作流（定位策略、六类改动的完整步骤、写后验收） | `references/slide/edit-guide.md` |
| 参数范式、坐标换算、批量模式、易错边界 | `references/slide/entry.md` |

## 权威来源

```
tdocs-cli slide --help
tdocs-cli slide <command> -h
```

命令参数以当前 `-h` 为准；是否允许调用仍以根 `SKILL.md` 的硬约束为准。
