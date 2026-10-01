# 在线 PPT 命令与参数参考

本文只解释易混淆概念、复杂参数范式和稳定的易错边界。完整编辑流程见 `edit-guide.md`，能力发现与硬约束见 `cmd-slide.md`。

## 通用参数

所有 `slide` 命令都接受：

| 参数 | 说明 |
|---|---|
| `--file-id` / `--file-url` | 二选一。有 `file_id` 优先用它，全程复用同一值 |
| `--page-index` | 页索引，从 `0` 开始。除 `slide-get-info` / `slide-find-text` / `slide-add-slide(s)` 等作用于整篇的命令外都需要它 |

字面 `file_id` 用单引号包裹（可能含 `$`），shell 变量用双引号：`--file-id "$fid"`。

## 坐标与尺寸

`--x` / `--y` / `--w` / `--h` 统一使用**磅（pt）**，`1pt = 12700 EMU`。`--x` / `--y` 指的是元素**左上角**的坐标。

- 不要传像素值，也不要自己换算成 EMU，服务端接收的就是 pt。
- `slide-add-text` 的 `--w` / `--h` **必须 > 0**，否则文本框不可见。
- `slide-add-image` 的 `--w` / `--h` 传 `<= 0` 时使用图片自身原始尺寸。

页面实际尺寸取 `slide-get-info` 返回的 `w_pt` / `h_pt`，据此再决定坐标，不要按 16:9 之类的比例自行估算。

## `shape_id` 从哪来

`shape_id` 只使用在线命令的实际返回。定位已有形状时，从页面结构读取：

```bash
tdocs-cli slide slide-get-page-info --file-id '<file_id>' --page-index 2
```

**返回里字段名是 `id`，不是 `shape_id`**。取 `data.shapes[].id`，原样填给 `--shape-id`。ID 是不透明值，不按长度、字符集或形态校验，也不自行改写。

新增类命令的返回结构可能不同：实际返回中有 `shape_id` 就直接复用；只有 `trace_id` 或没有 ID 时，必须重新调一次 `slide-get-page-info` 定位新形状。不要预设某条新增命令一定返回或一定不返回 ID。

## 发现类命令的返回结构

以下列出常用返回字段；运行时以实际响应为准，不要猜字段名。

**`slide-get-info`** → `data` 下：

| 字段 | 说明 |
|---|---|
| `slide_count` | 总页数 |
| `slide_ids` | 页 ID 数组，顺序即页序 |
| `w_pt` / `h_pt` | 页面宽高，单位磅。算坐标用这两个 |
| `w_emu` / `h_emu` | 同一尺寸的 EMU 表示，一般用不到 |

**`slide-get-page-info`** → `data` 下有 `shape_count` 与 `shapes` 数组，单个 shape 的常用字段：

| 字段 | 说明 |
|---|---|
| `id` | 形状 ID，填给 `--shape-id` |
| `name` | 可选的形状名；可能为空，不能替代 `id` 作为形状身份 |
| `type` | 形状类型，如 `shape` |
| `text` | 形状内文本，可直接预览，不必为了看内容再调 `slide-get-text` |
| `bounds` | `{x, y, w, h, rotation, flip_h, flip_v}`，单位磅。算相对位置时读这里 |
| `is_placeholder` | 是否为版式占位符 |

**`slide-get-text`** → `data` 下：

| 字段 | 说明 |
|---|---|
| `length` | 文本总长度，**直接用它算 `--count`，不要自己数字符**。返回的是字符串（如 `"6"`），传参时按数值填 |
| `paragraphs` | 段落区间数组，含 `start` / `end` |
| `runs` | 样式区间数组，给出 `start` / `end`。样式字段非空时可作参考；字段为 `null` 只表示接口未返回，不能据此判定写入失败 |

样式验收以实际返回字段为准：`slide-get-page-info` 可能提供 `font_color` / `font_size` / `font_name` 等基础旁证；未返回的粗体、斜体、下划线等状态不能由 CLI 独立确认。不要因字段缺失重复写入，高价值交付确需确认时导出后验收。

**`slide-get-master-info`** → `data` 下有 `master_count` 与 `masters` 数组，每个 master 含 `layout_count` 与 `layouts` 数组，单个 layout 有 `layout_index` / `layout_id` / `layout_type` / `matching_name`。

## 文本范围：`index` + `count`

文本类命令用**起始位置 + 长度**定位，不是起止对：

| 参数 | 含义 |
|---|---|
| `--index` | 起始位置，从 0 开始 |
| `--count` | 长度 |

两者的**单位都是 UTF-16 码元**，与 `slide-get-text` 返回的 `length` 同一口径。所以整段改样式时直接取 `length` 填 `--count`（例如 `--index 0 --count <length>`），**不要自己数字符**——中英文混排或含 emoji 时手数必错。改完回读确认落点正确。

覆盖文本会改变长度，因此顺序固定为**先 `slide-set-text` 改内容，再 `slide-set-text-property` 设样式**；反过来做，样式范围会落在旧文本的位置上。

`slide-insert-text` 只需要 `--index`（插入点），`slide-delete-text` 与 `slide-set-text-property` 需要 `--index` + `--count`。

## 两种调用模式（仅 `slide-set-text` 与 `slide-set-shape-properties`）

只用下面两种，一次一种：

| 模式 | 传什么 | 用在什么时候 |
|---|---|---|
| A 单形状 | `--shape-id` + 属性 | 只改一个形状 |
| B 批量一对一 | `--shapes` 数组，每项自带 `shape_id` 和各自的属性 | 多个形状、各改各的 |

`--shape-id` 与 `--shapes` **互斥**，同时传会报错。模式 B 下所有变更合并为一个撤销单元、一次广播，比循环调用模式 A 更高效。

这两个命令当前只使用上面的 A/B 模式，**不要使用 `--shape-ids` 批量多对一模式**。要对多个形状套同一份内容或属性，使用模式 B，在每个元素中明确写入属性。

**`slide-set-text-property` 没有批量模式**，只接受 `--shape-id`。要给多个形状套同一组样式只能逐个调用，没有捷径。

⚠️ 它的 `-h` **描述文字**里写着"支持三种模式……批量一对一传 shapes 数组、批量多对一传 shape_ids 数组"，但 **Flags 段并没有这两个参数**——描述来自上游接口文档，CLI 未暴露对应 flag。照描述传 `--shapes` / `--shape-ids` 会直接报 unknown flag。**以 Flags 段为准，不要按描述文字拼参数。**

## 数组类参数的元素结构

`<array>` 类参数传 JSON 数组，可用 `@filepath` 从文件读入：

| 参数 | 所属命令 | 单元素字段 |
|---|---|---|
| `--texts` | `slide-add-texts` | `x` / `y` / `w` / `h` / `text` / `font_color` / `font_name` / `font_size` / `fill_color` / `border_color` / `border_dash` / `border_width` |
| `--shapes` | `slide-add-shapes` | `x` / `y` / `w` / `h` / `shape_type` / `fill_color` / `fill_alpha` / `border_color` / `border_dash` / `border_width` / `border_alpha` |
| `--shapes` | `slide-set-shape-properties` | `shape_id` / `fill_color` / `fill_alpha` / `border_color` / `border_alpha` / `border_width` / `border_dash` / `x` / `y` / `w` / `h` / `rotation` |
| `--lines` | `slide-add-line-shapes` | `x1` / `y1` / `x2` / `y2` / `line_type` / `color` / `dash` / `width` |
| `--shapes` | `slide-set-text` | `shape_id` / `text` |
| `--shape-ids` | `slide-reorder-shape`、`slide-remove-shapes` | 字符串数组，长度 >= 1 |
| `--page-indexes` | `slide-duplicate-slide` | 整数数组（0-based），长度 >= 1 |
| `--page-indices` | `slide-move-slide` | 整数数组（0-based），长度 >= 1 |

注意 `slide-duplicate-slide` 用 `--page-indexes`、`slide-move-slide` 用 `--page-indices`，拼写不同，以 `-h` 为准。

## 颜色与透明度

- 颜色是 **6 位十六进制、不带 `#`**，例如 `FF0000`、`000000`。
- `--fill-color` / `--border-color` 传 `none` 表示移除填充 / 边框；不传表示保持不变。
- `--fill-alpha` / `--border-alpha` 取值 `0~100`，**`0` 是完全不透明、`100` 是完全透明**，与常见直觉相反。设置了颜色但没传 alpha 时默认为 `0`（不透明）。

## 枚举取值

| 参数 | 所属命令 | 取值 |
|---|---|---|
| `--shape-type` | `slide-add-shape(s)` | `rect` / `ellipse` / `triangle` / `rightArrow` / `leftArrow` 等预设块；空串默认 `rect` |
| `--line-type` | `slide-add-line-shape(s)` | `line` / `arrow` / `doubleArrow`；空串默认 `line` |
| `--dash` | `slide-add-line-shape(s)` | `solid` / `dash` / `dot`；空串默认 `solid` |
| `--border-dash` | `slide-set-shape-properties` 等 | `solid` / `dot` / `dash` / `lgDash` / `dashDot` / `lgDashDot` / `lgDashDotDot` / `sysDash` / `sysDot` / `sysDashDot` / `sysDashDotDot` |
| `--underline` | `slide-set-text-property` | `sng`（单线）/ `dbl`（双线）/ `none`。**是字符串不是布尔值，绝不能传 `true`** |
| `--strikethrough` | `slide-set-text-property` | `sngStrike`（单线）/ `noStrike`。同样**不能传 `true`**；`dblStrike` 会被降级成单线 |
| `--op` | `slide-reorder-shape` | `0`=置顶 / `1`=置底 / `2`=上移 / `3`=下移 |
| `--layout-index` | `slide-add-slide(s)` | 首个母版下的布局序号，默认 `0`。取值必须落在该母版 `layout_count` 范围内，先用 `slide-get-master-info` 查，见下方「布局怎么挑」 |

## 易错边界

### 下划线 / 删除线传错值会静默失效

服务端可能不校验 `--underline` / `--strikethrough` 的错误取值，命令返回成功也不代表样式有效。必须按上表的字符串枚举填写，不要凭 `--bold true` 的印象类推——`--bold` / `--italic` 才是布尔值。

### 布局怎么挑（`--layout-index`）

插页前先 `slide-get-master-info` 看这份文档实际有哪些布局：

- **布局数量因文档而异**：`--layout-index` 必须落在目标母版的 `layout_count` 范围内，不要预设固定数量。
- 若 `matching_name` 为空或 `layout_type` 无法解释，就不能可靠判断哪个布局是“空白版式”。
- 用户要“空白页”时，如果只有一个布局就直接用它；有多个但返回信息不足时，用默认布局插入后回读该页结构，或说明版式需要在前端调整，不要假装识别成功。

### 插页索引有边界

`slide-add-slide` / `slide-add-slides` 的 `--index` 必须落在 `[0, 当前页数]`：等于当前页数表示追加到末尾，**不支持 `-1`**。插页前先调 `slide-get-info` 拿 `slide_count`，不要靠试错找边界。

### 新增形状必须可见

`slide-add-shape` / `slide-add-shapes` 至少要设置 `--fill-color` 或 `--border-color` 之一，否则形状对用户不可见，调用会被服务端拒绝。

### 图片不接受远程链接

`slide-add-image` 只接受两种来源，二选一：

- `--image-id`：已上传图片的加密 ID，有效期一天
- `--content`：base64 编码内容（不含 `data:` 前缀），仅适合小图

**不支持 http(s) 远程 URL**。

### 插入表格行的高度参考

`slide-insert-table-rows` 的 `--reference-row-index` 指定新行按哪一行的高度生成（0-based）。不传按 `0` 处理；超出已有行数时新行使用默认行高。

### 箭头的两种形态

`rightArrow` / `leftArrow` 是**固定方向的图形预设块**，只能用 `slide-add-shape` 添加，不能指定起点终点。要画"从 A 点到 B 点的箭头线"必须用 `slide-add-line-shape` 并设 `--line-type arrow`（双向箭头用 `doubleArrow`）。两者视觉效果完全不同：用户给了起点终点或说"把 A 和 B 连起来"时按线条箭头执行，只笼统说"加个箭头"、看不出要连什么时才问清。

## 权威来源

```
tdocs-cli slide --help
tdocs-cli slide <command> -h
```
