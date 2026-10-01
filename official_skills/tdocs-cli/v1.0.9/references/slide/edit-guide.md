# 在线 PPT 编辑指南

使用本指南对已有在线 PPT 做白名单内的原地小改。小改全程复用目标文档的同一个 `file_id`，不删除重建、不导入新副本；白名单无法完成的复杂需求按文末 V2 流程执行。

新建 PPT 不用本指南：先用可用的本地 PPT 创建能力产出并验收 `.pptx`，再单次 `workflow import-file` 导入。

## 标准流程

任何写操作都走这四步，不要跳过前两步直接改。**纯页级操作（增删页、移动页）不涉及形状，跳过第 2 步**：

```bash
# 1. 摸清结构：总页数、页面尺寸
tdocs-cli slide slide-get-info --file-id '<file_id>'

# 2. 定位目标页的形状，拿到真实 shape_id
tdocs-cli slide slide-get-page-info --file-id '<file_id>' --page-index <n>

# 3. 执行改动（见下方对应工作流）

# 4. 定点回读验收，按改动类型选命令（见文末「写后验收」）
```

`page_index` 和 `shape_id` 必须来自第 1、2 步的真实返回。**猜坐标、猜 ID 是本入口最常见的失败原因。**

## 定位策略

先想清楚"要改的东西在哪"，再选定位方式：

用户口语的「第 N 页」是从 1 数的，`--page-index` 从 0 数，换算是 `page_index = N - 1`。定位后核对一下这一页的内容是否与用户描述吻合，不吻合就改用 `slide-find-text` 按内容找。

| 已知条件 | 定位方式 |
|---|---|
| 知道在第几页 | 直接 `slide-get-page-info --page-index <n>` 看这一页的形状 |
| 只知道文字内容、不知道在哪页 | 先 `slide-find-text --search "<关键词>"` 全文查，拿到页码再取形状 |
| 要读某形状现有文字与样式区间 | `slide-get-text` |

改文字前**先读原文**。文本样式命令按 `--index` + `--count` 定位字符范围，不读原文就算不出正确范围。`slide-get-text` 的返回里 `length` 就是文本总长度，直接拿来算 `--count`，不要自己数字符；`runs` 数组给出已有样式区间的 `start` / `end`。

`slide-get-page-info` 返回的 `shapes[]` 里，形状 ID 的字段名是 **`id`**（不是 `shape_id`），位置尺寸在 `bounds` 里（`x` / `y` / `w` / `h`，单位磅），`text` 字段还能直接预览形状内文字。

## 工作流一：改现有文字

整段替换用 `slide-set-text`（覆盖式）：

```bash
tdocs-cli slide slide-get-text --file-id '<file_id>' --page-index 2 --shape-id '<shape_id>'

tdocs-cli slide slide-set-text --file-id '<file_id>' --page-index 2 \
    --shape-id '<shape_id>' --text "2026 年第一季度经营回顾"
```

只改局部：

- 末尾追加 → `slide-append-text --text "补充说明"`
- 中间插入 → `slide-insert-text --index <位置> --text "..."`
- 删除一段 → `slide-delete-text --index <起始> --count <长度>`

全篇统一替换某个词，用按页替换：

```bash
tdocs-cli slide slide-find-text --file-id '<file_id>' --search "2025"
# 对返回中命中的每一页执行
tdocs-cli slide slide-find-replace-text --file-id '<file_id>' --page-index <n> \
    --search "2025" --replace "2026"
```

`slide-find-replace-text` 是**按页**生效的，需要先用 `slide-find-text` 查出所有命中页，再逐页替换，不要只改第一页就当作全改完。

## 工作流二：调文字样式

`slide-set-text-property` 按字符范围设置样式，改之前先 `slide-get-text` 读出真实文本长度：

```bash
# 只加粗开头一段：范围按 slide-get-text 的 runs / length 算，单位是 UTF-16 码元
tdocs-cli slide slide-set-text-property --file-id '<file_id>' --page-index 2 \
    --shape-id '<shape_id>' --index 0 --count <码元数> \
    --bold true --color 'FF0000'

# 整段换字体字号：count 用读到的文本总长度
tdocs-cli slide slide-set-text-property --file-id '<file_id>' --page-index 2 \
    --shape-id '<shape_id>' --index 0 --count <文本总长度> \
    --font-name '思源黑体' --font-size 18
```

用户说"前几个字"这类模糊范围时，以 `slide-get-text` 返回的实际内容为准，不要按字面印象估。整段改样式直接用 `length`；只改一部分时参考 `runs` 里已有的区间边界。

**不要用 `runs[]` 的空样式字段判定失败。** 当前接口可能无法回读粗体、斜体、下划线等结果；命令返回成功只表示请求被接受，不等于已独立验收。不要因此重复写入，也不要向用户宣称已回读确认。`slide-get-page-info` 可旁证 `font_color` / `font_size` / `font_name`；高价值交付确需确认时，导出后用本地能力验收。

下划线和删除线要传字符串枚举（`sng` / `dbl` / `none`、`sngStrike` / `noStrike`），**传 `true` 会返回成功但实际没有效果**，详见 `entry.md`。`--bold` / `--italic` 才是布尔值。

`slide-set-text-property` **只支持单形状**，只能对每个 `shape_id` 逐条调用。注意它 `-h` 的描述文字声称支持 `shapes` / `shape_ids` 批量模式，但 Flags 段没有这两个参数，照着传会报 unknown flag——**以 Flags 段为准**。

换整段文字则不同，`slide-set-text` 支持批量，多个形状一次改完：

```bash
# 批量一对一：每个形状换各自的文字
tdocs-cli slide slide-set-text --file-id '<file_id>' --page-index 2 \
    --shapes '[{"shape_id":"<id1>","text":"新标题"},{"shape_id":"<id2>","text":"新副标题"}]'
```

## 工作流三：新增文本框与形状

新增前先看清这一页已有形状的位置，避免叠在一起。坐标单位是磅（pt），从 `slide-get-info` 拿页面尺寸后再定位置。若占位符的 `bounds` 为全 `0`，说明位置不可用，不能据此排版；避开该占位符或询问用户放置位置。

```bash
# 文本框：w/h 必须 > 0
tdocs-cli slide slide-add-text --file-id '<file_id>' --page-index 2 \
    --x 60 --y 320 --w 400 --h 40 \
    --text "数据来源：财务部" --font-size 12 --font-color '666666'

# 形状：必须给 fill-color 或 border-color，否则不可见、会被拒绝
tdocs-cli slide slide-add-shape --file-id '<file_id>' --page-index 2 \
    --x 100 --y 100 --w 200 --h 80 --shape-type rect --fill-color 'D9E2F3'

# 线条箭头：从起点到终点，与图形箭头块不是一回事
tdocs-cli slide slide-add-line-shape --file-id '<file_id>' --page-index 2 \
    --x1 100 --y1 200 --x2 300 --y2 200 --line-type arrow --color '000000' --width 2
```

一次加多个用批量命令（`slide-add-texts` / `slide-add-shapes` / `slide-add-line-shapes`），传对象数组，比循环调用单条高效。

调整已有形状的位置、大小、颜色用 `slide-set-shape-properties`；调层级用 `slide-reorder-shape --op`（`0` 置顶 / `1` 置底 / `2` 上移 / `3` 下移）；删除用 `slide-remove-shapes --shape-ids`。

## 工作流四：插入图片

`slide-add-image` 不接受 http(s) 远程链接。两种来源二选一：

```bash
# 方式一：已上传图片的加密 ID（有效期一天）
tdocs-cli slide slide-add-image --file-id '<file_id>' --page-index 2 \
    --x 80 --y 120 --w 300 --h 200 --image-id '<image_id>'

# 方式二：纯 base64 内容，不含 data: 前缀，仅适合小图
tdocs-cli slide slide-add-image --file-id '<file_id>' --page-index 2 \
    --x 80 --y 120 --w 300 --h 200 --content '<base64_content>'
```

`--w` / `--h` 传 `<= 0` 时按图片原始尺寸放置。优先使用跨平台的 `image_id`；base64 编码由当前环境已有能力完成，不在本 skill 中硬编码 shell 管道。用户给的是网络图片链接时，先说明不支持外链，请用户提供本地文件或先上传。

## 工作流五：增删页

```bash
# 先拿页数，插入位置必须 ∈ [0, 当前页数]，不支持 -1
tdocs-cli slide slide-get-info --file-id '<file_id>'

# --index 是新页插入后自己占据的 0-based 位置。
# 想插在原来的 page_index 2 这一页之后，就传 --index 3
tdocs-cli slide slide-add-slide --file-id '<file_id>' --index 3 --layout-index 1

# 批量插多页，共用同一布局
tdocs-cli slide slide-add-slides --file-id '<file_id>' --index 3 --count 2 --layout-index 1

# 删除某页
tdocs-cli slide slide-remove-slide --file-id '<file_id>' --page-index 4

# 复制页（page-indexes 是数组）
tdocs-cli slide slide-duplicate-slide --file-id '<file_id>' \
    --page-indexes '[2]' --target-page-index 5

# 移动页前必须同时读取节结构和当前页序
tdocs-cli slide slide-get-sections --file-id '<file_id>'
tdocs-cli slide slide-get-info --file-id '<file_id>'

# 无节结构时可按页索引移动（注意这里是 page-indices）
tdocs-cli slide slide-move-slide --file-id '<file_id>' \
    --page-indices '[2]' --before-slide-index 0
```

**增删页会让后续页的 `page_index` 整体位移。** 一次改动多页时，要么从后往前操作，要么每步之后重新 `slide-get-info` 确认页序，不要沿用旧索引。

移动页时必须先读取 `slide-get-sections`。无节结构时可按 `--before-slide-index` 移动；存在节时，先根据返回的节 ID、边界和用户目标判断归属，按运行时帮助在 `--before-slide-index` 与 `--after-section-id` 中二选一。无法确定移动后的节归属时，不执行移动，让用户选择前端操作或生成 V2。

`--layout-index` 是**首个母版**（`masters[0]`）下的布局序号，默认 `0`，必须落在该母版自己的 `layout_count` 范围内——文档可能有多个母版，各有各的布局数，不要拿别的母版数字。若 `matching_name` 为空或 `layout_type` 无法解释，就不能可靠认出“空白版式”；可用默认布局插入后回读页面结构，或说明版式需要在前端调整。

## 工作流六：表格操作

表格本身是一个形状。对已有表格，从 `slide-get-page-info` 返回的页面结构中找 `type` 为 `table` 的形状。

本入口只适合已有表格的有限小改，不开放新建表格，也不承诺整表制作、复杂样式或完整回读。用户要求新建整表、图表联动或复杂版式时，按文末“复杂改动与未开放能力”生成 V2，不要强行逐格在线拼装。

```bash
# 写单元格：row / col 是 0-based
tdocs-cli slide slide-set-cell-text --file-id '<file_id>' --page-index 3 \
    --shape-id '<table_shape_id>' --row 1 --col 1 --text "营收"

# 增删行列
tdocs-cli slide slide-insert-table-rows --file-id '<file_id>' --page-index 3 \
    --shape-id '<table_shape_id>' --index 2 --count 1 --reference-row-index 1
tdocs-cli slide slide-delete-table-cols --file-id '<file_id>' --page-index 3 \
    --shape-id '<table_shape_id>' --index 3 --count 1

# 合并单元格；unmerge 也要传 row-span / col-span
tdocs-cli slide slide-merge-table-cells --file-id '<file_id>' --page-index 3 \
    --shape-id '<table_shape_id>' --start-row 1 --start-col 1 --row-span 1 --col-span 3
```

增删行列会让后续索引位移，改完重新读取页面结构再继续。任一步返回 `50000` 时不要改变目标坐标反复试错；核对参数和真实 ID 后仍失败，就停止在线表格操作并让用户选择前端处理或生成 V2。

## 写后验收

改完必须回读确认，不要只凭命令返回成功就收口：

- 改文字 → `slide-get-text` 读同一形状，确认新内容和范围正确
- 改样式 → 读取可见字段作旁证；不可回读的样式标记为“接口无法独立验收”，不要重复写入或声称已确认（见工作流二）
- 加形状 / 图片 → `slide-get-page-info` 确认新形状存在且只有一个，没有重复添加
- 增删页 → `slide-get-info` 确认总页数符合预期
- 表格 → 只能确认表格形状与结构仍存在；无法逐格回读时如实说明未独立验收

发现改错了，用对应的反向命令修正（`slide-remove-shapes` 删掉多加的形状、`slide-set-text` 覆盖回原文），**不要删除整个文档重来**。

## 复杂改动与未开放能力

动画、图表、批注、分组、节编辑、主题、新建表格、整表制作或大规模重排不在本入口的可靠小改范围内。遇到这类需求：

1. 说明原地编辑限制；
2. 让用户选择在腾讯文档前端操作，或生成新版本；
3. 用户选择新版本时，复用本地源文件或先导出当前在线版本，在本地完成并验收后单次导入；
4. 新版文件名使用 `V2` / `V3`，确认新版可交付后再按 `cmd-manage.md` 判断旧版是否保留；
5. 明确说明新链接未覆盖原链接。

## 命令失败时

先判断错误类型再动作，禁止原样重试：

- **参数或 flag 报错**：用 `tdocs-cli slide <command> -h` 核对真实参数名。
- **形状不可见被拒绝**：`slide-add-shape` 补上 `--fill-color` 或 `--border-color`。
- **`retcode 50000`（服务繁忙）**：兜底错误，字面文案不能证明是临时抖动。依次核对参数、请求体、在线返回的 `page_index` / `shape_id` 和当前白名单；没有新的诊断依据时停止重复调用，按“复杂改动与未开放能力”安全降级。
- 其余错误码按 `references/troubleshooting.md` 处理。
