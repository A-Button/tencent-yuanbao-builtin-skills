# cmd-ocr — 图片文字识别

使用 `tdocs-cli ocr ...` 对图片做 OCR——提取图片中的文字，或把图片直接转换成在线文档（Word）/ 在线表格（Excel）。

## 能力分类

| 分类 | 包含的能力 | CLI 命令 |
|---|---|---|
| 文字提取 | 从图片中识别文字内容 | `ocr extract` |
| 图片转 Excel | 批量图片合并生成一份在线表格 | `ocr images-to-excel` |
| 图片转 Word | 批量图片合并生成一份在线文档 | `ocr images-to-word` |

## 参数说明

### ocr extract

| 参数 | 必填 | 说明 |
|---|---|---|
| `--img-base64` | 是 | 图片的 base64 字符串（不要带 `data:image/...;base64,` 前缀） |
| `--extract-type` | 否 | 提取模式：`1`=通用，`2`=高精度，`3`=精简 |

### ocr images-to-excel

| 参数 | 必填 | 说明 |
|---|---|---|
| `--imgs-base64` | 是 | 图片 base64 字符串数组（多张图片会被合并到同一份在线表格） |
| `--title` | 否 | 生成的在线表格标题 |

### ocr images-to-word

| 参数 | 必填 | 说明 |
|---|---|---|
| `--imgs-base64` | 是 | 图片 base64 字符串数组（多张图片会被合并到同一份在线文档） |
| `--title` | 否 | 生成的在线文档标题 |

## 准备图片 base64

CLI 期望接收纯 base64 字符串（不含 `data:` 头）。常用准备方式：

```bash
# POSIX：单张图片转 base64 文件
base64 -w0 input.png > input.b64           # GNU coreutils（Linux）
base64 -i input.png -o input.b64           # macOS

# 通过 @filepath 语法把 base64 内容传给 CLI，避免在终端历史里出现长字符串
tdocs-cli ocr extract --img-base64 @./input.b64 --extract-type 2
```

> `--imgs-base64` 是 array 类型，可在命令行里多次出现：`--imgs-base64 @./a.b64 --imgs-base64 @./b.b64`，每次调用对应一张图片。

## 代表性示例

```bash
# 通用 OCR：提取图片文字
tdocs-cli ocr extract --img-base64 @./screenshot.b64

# 高精度 OCR：适合证件、表格、印刷体
tdocs-cli ocr extract --img-base64 @./id-card.b64 --extract-type 2

# 多张图合并生成一份在线表格
tdocs-cli ocr images-to-excel --title "考勤表" \
    --imgs-base64 @./day1.b64 \
    --imgs-base64 @./day2.b64

# 多张图合并生成一份在线文档
tdocs-cli ocr images-to-word --title "会议纪要扫描件" \
    --imgs-base64 @./page1.b64 \
    --imgs-base64 @./page2.b64
```

## 注意事项

- 图片越大 base64 字符串越长，建议优先用 `@filepath` 语法读入文件，避免终端历史 / 日志里出现超长字符串。
- `images-to-excel` / `images-to-word` 直接落库为腾讯文档资源，命令返回 `file_id` 等字段，可用 `manage query-file-info --file-id <fid>` 进一步操作。

## 权威来源

```
tdocs-cli ocr --help
tdocs-cli ocr extract --help
tdocs-cli ocr images-to-excel --help
tdocs-cli ocr images-to-word --help
```
