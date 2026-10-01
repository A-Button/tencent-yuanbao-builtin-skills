# 在线 DOC 命令与参数参考

本文只解释易混淆概念、复杂参数范式和已实测限制。创建或编辑任务的完整流程由 `cmd-doc.md` 直接路由到对应 guide。

## 坐标语义

- `idx`：单个插入位置，用于 `insert-*` 等命令。
- `begin/end`：范围边界，用于 `replace-text`、`update-text-property`、`modify-paragraph` 等命令。
- `paragraph_index`：结构结果中的段落序号，不等于字符坐标，不能直接填入 `idx` 或 `begin/end`。
- `start_index/end_index`：结构节点的真实范围。写操作可能改变后续坐标；结构变化后要重新查询。
- `find` 返回的匹配范围只用于当前版本；写入后继续编辑时重新定位。

按目标选择定位命令：

- 看完整节点和真实范围：`doc resolve-document-structure`
- 看标题层级与正文范围：`doc get-outline`
- 定位某段文字：`doc find --text`
- 追加到末尾：`doc get-last-operable-pos`

```bash
tdocs-cli doc resolve-document-structure \
    --file-id '<file_id>' \
    --version-info '{}'
```

超长文档可使用 `resolve-document-structure` 的 `--offset` / `--limit` 分页；只定位一个已知字符位置时可传 `--idx`。

## `version-info`

多数写命令接收 object 类型的 `--version-info`。未指定基准版本时可用：

```bash
--version-info '{}'
```

需要显式版本控制时，值形如：

```bash
--version-info '{"base_version":12,"is_latest":false}'
```

版本值必须来自当前 API 返回，禁止猜测。若一次写入改变了文档结构，后续坐标和版本均以新返回为准。

## array / object 参数范式

`--ranges` 是 JSON 数组，形如 `[{"begin":<真实起点>,"end":<真实终点>}, ...]`；`--property` 是 JSON object。先根据最新结构构造 `"$ranges"`，再传入命令：

```bash
tdocs-cli doc update-text-property --file-id '<file_id>' \
    --ranges "$ranges" \
    --property '{"font_family":"宋体","font_size":10.5,"bold":true,"vertical_align":0}' \
    --version-info '{}'
```

字符样式可组合使用 `bold`、`italic`、`underline`、`strikethrough`、`small_caps`、`color`、`background_color`、`font_size`、`font_family`、`highlight`、`vertical_align`。具体字段仍以当前 `update-text-property --help` 为准。

## `update-text-property` 实测限制

- 每个 `{"begin","end"}` 必须完整落在单个段落节点的 `[start_index,end_index]` 内。
- 一个 range 跨越多个段落会返回 `50000`；不要把它解释为服务繁忙后原样重试。
- 多段统一样式时，把每个段落拆成独立 range，再放进同一个 `--ranges` 数组提交。
- 禁止使用 `[{"begin":0,"end":1695}]` 一类覆盖全文、跨多段的大 range。

## `modify-paragraph` 实测限制

- 数值和多词 flag 使用 `--flag=value`，例如 `--line-spacing=1.5`、`--line-spacing-rule=1`。
- `--first-line-indent*` 当前实测命令成功但导出未落地；不要依赖或宣称缩进成功。
- 不使用 `--p-style`；当前实测会返回 `50000`，应改用具体的对齐、行距、间距或缩进属性。
- `modify-paragraph` 的 range 可以覆盖多个段落，但边界仍应来自真实结构。
- 字体和字号属于字符样式，使用 `update-text-property`，不使用 `modify-paragraph`。

```bash
tdocs-cli doc modify-paragraph --file-id '<file_id>' \
    --ranges "$ranges" \
    --jc=both \
    --line-spacing=1.5 --has-line-spacing=true \
    --version-info '{}'
```

已验证的段落属性包括：`--jc`、`--line-spacing` 与 `--has-line-spacing=true`、段前段后间距及对应 `--has-*=true`、`--indent`、`--numbering`、`--block-quote=true` 与 `--has-block-quote=true`。取值以当前 `modify-paragraph --help` 为准；首行缩进是上述已知例外。

## 已知不稳定端点

`replace-image` / `revert-revision` 在健康文档上也可能连续返回 `50000`。参数核对后仍失败时，不要死磕重试；改走等效路径或向用户说明限制。

## 权威来源

```text
tdocs-cli doc --help
tdocs-cli doc <command> --help
```
