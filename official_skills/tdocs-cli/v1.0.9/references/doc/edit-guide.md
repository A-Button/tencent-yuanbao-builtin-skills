# 在线 DOC 编辑指南

使用本指南增量编辑已有在线 DOC。全程复用目标文档的同一个 `file_id`，不删除重建。

## 标准流程

1. **确认目标**：及时记录用户给出的或上一步返回的 `file_id` 和链接，后续原样复用。
2. **按目的定位**：
   - 指定文字 → `doc find --text`
   - 看标题和段落结构 → `doc resolve-document-structure` / `doc get-outline`
   - 追加到末尾 → `doc get-last-operable-pos`
3. **选择最小写操作**：只修改目标位置，不把局部编辑扩大成全文重写。
4. **刷新结构**：写操作改变内容长度或段落结构后，后续仍需坐标时重新定位。
5. **定点验收**：只回读受影响位置，确认修改生效。
6. **失败恢复**：先诊断参数和坐标；除 `troubleshooting.md` 明确认定的速率限制外，禁止同参 sleep 重发。针对同一目标，修正参数后最多再提交一次。

## 插入与追加

`idx` 是字符插入位置，不是段落序号。必须使用结构或末尾位置命令的真实返回。

```bash
# 1. 获取末尾真实位置并记录为 shell 变量 idx
tdocs-cli doc get-last-operable-pos \
    --file-id '<file_id>' \
    --version-info '{}'

# 2. 使用上一步返回的 idx 追加
tdocs-cli doc insert-markdown --file-id '<file_id>' \
    --idx "$idx" \
    --base64-markdown "$(printf '%s' '追加内容' | base64 | tr -d '\n')" \
    --version-info '{}'
```

插入后重新查询末尾或目标附近结构，确认内容只出现一次且位置正确。

### 插入空行与换行

空行是**段落**，不是文本内容。用 `insert-paragraph` 插入段落分隔符，它不写入任何字符：

```bash
tdocs-cli doc insert-paragraph --file-id '<file_id>' \
    --idx "$idx" \
    --level 10 \
    --version-info '{}'
```

`--level 10` 为正文级；插入标题段落才改用对应标题级别。正文中间需要换行同样用它分段。

禁止改用 `insert-markdown` 传空字符串、`\n`、空格、`<br>` 或 `<p>&nbsp;</p>`：这些都得不到空行，HTML 实体会作为正文字符原样写入，用户看到的是 `&nbsp;` 字面量。失败时按「标准流程」重新确认 `idx` 再试，不要换一种编码重试。

## 精确替换

### 精确范围

先用 `doc find` 定位；0 命中时停止写入并核对全/半角或原文，单点修改使用返回的真实 `begin/end`：

```bash
tdocs-cli doc find --file-id '<file_id>' \
    --text "旧文本" \
    --version-info '{}'

tdocs-cli doc replace-text --file-id '<file_id>' \
    --ranges "$range" \
    --text "新文本" \
    --version-info '{}'
```

其中 `"$range"` 是根据本次 `find` 返回构造的单元素 JSON 数组，形如 `[{"begin":<真实起点>,"end":<真实终点>}]`。

### 全部匹配项

仅在用户要求修改全部命中且 `find` 已确认范围时使用：

```bash
tdocs-cli doc find-and-replace --file-id '<file_id>' \
    --old-text "旧文本" \
    --new-text "新文本" \
    --version-info '{}'
```

写后分别 `find` 旧文本和新文本，按命中位置确认目标已改；不要用全文回读代替定点验收，也不要只凭写命令成功响应收口。

## 字符样式

字体、字号、加粗、斜体、颜色等使用 `update-text-property`。

1. 先用 `resolve-document-structure` 获取每个目标段落的 `start_index/end_index`。
2. 每个 range 只能落在单个段落内。
3. 多段统一样式时按段拆成多个 range；相同属性的 ranges 合并为一次提交，不逐段循环调用。
4. `--property` 显式带 `vertical_align:0`，表示保持当前上下标状态。

```bash
tdocs-cli doc update-text-property --file-id '<file_id>' \
    --ranges "$ranges" \
    --property '{"font_family":"宋体","font_size":10.5,"bold":true,"vertical_align":0}' \
    --version-info '{}'
```

禁止覆盖全文的跨段大 range。写后用 `get-text-property --idx "$idx"` 抽查；`"$idx"` 取自目标段落真实范围，不使用段落序号。

## 段落版式

对齐、行距、段前段后间距、缩进和编号使用 `modify-paragraph`。数值和多词 flag 使用 `=`：

```bash
tdocs-cli doc modify-paragraph --file-id '<file_id>' \
    --ranges "$ranges" \
    --jc=both \
    --line-spacing=1.5 --has-line-spacing=true \
    --version-info '{}'
```

硬性限制：

- 数值和多词 flag 一律使用 `--flag=value`；不要写成 `--line-spacing-rule 1`。
- 不依赖 `--first-line-indent*`：当前实测命令成功但未落地；不要虚报成功或用空格改正文。
- 不使用 `--p-style`，改用具体版式属性。
- 字体和字号不属于段落版式，改用 `update-text-property`。

写后用 `get-paragraph-property --idx "$idx"` 抽查目标段落。

## 样式流程

1. 用最新 `resolve-document-structure` 构造 ranges。
2. 预检：字符 range 全部单段、无全文大 range；数值 flag 用 `=`；无首行缩进 flag 和 `--p-style`。
3. 相同字符属性 / 段落属性分别合并提交。
4. 每类字符样式、段落版式各定点抽查一次；出现 `50000` 时停止后续写入并进入恢复。

## `50000` 恢复

1. 不 `sleep`，不重发原命令。
2. 字符样式检查最新结构、单段 range 和全文大 range；段落版式检查 `=` 与 `--p-style`。
3. 坐标不确定时重新 `resolve-document-structure`。
4. 只修正一个已确认原因，同一目标最多再提交一次。
5. 仍失败则停止该路径并降级说明，不继续猜 range 或 flag。

## 写后验收

- 插入：目标位置存在新内容，且只出现一次。
- 替换：定点回读受影响位置，修改数量符合预期。
- 字符样式：目标 range 均位于单段，抽查字号、字体或加粗等属性。
- 段落版式：抽查目标段落的对齐、行距、间距或缩进。
- 结构性编辑：确认后续命令未复用写入前的旧坐标。
- 资源身份：后续写入继续使用开始时记录的 `file_id`。
