# 在线 Sheet 命令参考

仅在 `edit-guide.md` 判定为在线小改后加载。

## 坐标与读取

- `sheet_id` 来自 `get-sheet-info`，不是工作表名称。
- 行列索引从 `0` 开始；`get-cell-data` 的 `end-row/end-col` 包含边界。
- 一次读取不超过 20,000 个单元格；在线小改只读取目标区域，不扫描整表。

```bash
tdocs-cli sheet get-cell-data --file-id '<file_id>' \
    --sheet-id '<sheet_id>' \
    --start-row 0 --start-col 0 --end-row 9 --end-col 3 \
    --return-csv=false
```

## 批量写值

多格值用一次 `set-range-value`。每个元素都带零基 `row/col`、`value_type` 及对应值字段：

```bash
tdocs-cli sheet set-range-value --file-id '<file_id>' \
    --sheet-id '<sheet_id>' \
    --values '[
      {"row":1,"col":2,"value_type":"STRING","string_value":"已完成"},
      {"row":2,"col":2,"value_type":"NUMBER","number_value":42},
      {"row":3,"col":2,"value_type":"FORMULA","formula_value":"=C3*2"}
    ]'
```

`value_type` 支持 `STRING`、`NUMBER`、`BOOL`、`FORMULA`。公式回读通常只有计算结果；需要精确验证公式文本时转为本地处理。

## 区域样式

同一连续区域的样式用一次 `set-cell-style`：

```bash
tdocs-cli sheet set-cell-style --file-id '<file_id>' \
    --sheet-id '<sheet_id>' \
    --start-row 0 --start-col 0 --end-row 0 --end-col 3 \
    --format '{"bold":true,"font_size":16,"font_color":"FF000000","bg_color":"FFEAF2F8","horizontal_align":"center"}'
```

颜色使用 ARGB；字号为整数 pt。当前 `get-cell-data` 不返回样式字段，只能复核目标坐标和值未被破坏；需要强验证具体样式时转为本地处理。

## 行列操作

插入或删除连续行列时使用单次 `count`，不要循环逐行操作：

```bash
tdocs-cli sheet insert-dimension --file-id '<file_id>' \
    --sheet-id '<sheet_id>' --dimension-type row \
    --index 3 --count 2 --direction after
```

`direction` 支持 `before` / `after`；插入或删除会改变后续零基索引，继续操作前需重新定位。

## 权威来源

```text
tdocs-cli sheet get-sheet-info --help
tdocs-cli sheet get-cell-data --help
tdocs-cli sheet set-range-value --help
tdocs-cli sheet set-cell-style --help
tdocs-cli sheet insert-dimension --help
tdocs-cli sheet delete-dimension --help
```
