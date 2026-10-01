# 速查表

高频命令快速参考。

## 文件管理

```
tdocs-cli manage create-file --file-type smartcanvas --title demo
tdocs-cli manage list-file --jq '.[] | {id, title, type}'
tdocs-cli manage apply-download --file-id <file-id>
tdocs-cli manage query-task --task-id <task-id>
```

## 智能文档

```
# 创建带内容的智能文档（首选：一步 create-by-mdx）
tdocs-cli smartcanvas create-by-mdx --title "文档标题" --mdx @./body.mdx

# 兜底：两步流程（仅在需指定父目录/分多段写入时使用）
tdocs-cli manage create-file --type 8 --title "文档标题" --jq '.file_id'
tdocs-cli smartcanvas edit --file-id <fid> --action 2 --content @./body.mdx

# 读取
tdocs-cli smartcanvas get-top-level-pages --file-id <fid>
tdocs-cli smartcanvas read-content --file-id <fid> --page-id <pid>
# read-content 是分页接口，长文必须循环 --next-token 直到为空；
# 通读全文优先用非分页接口：
tdocs-cli manage get-content --file-id <fid>
# 想通读整篇就要真的读全：翻页到 next_token 为空，或用 get-content 一次拿全；
# 别只取前几行就当作读完。只想找某个字段或某一段，用 find-elements --query 更直接；
# 只是计数或提取 ID 可以用脚本；文档太大就先 > /tmp/x.json 落盘，再用 Read 分段读完
```

## 文档编辑

```
tdocs-cli doc resolve-document-structure --file-id <fid> --version-info '{}'
tdocs-cli doc insert-markdown --file-id <fid> --idx 10 --markdown "## 新标题" --version-info '{}'
tdocs-cli doc find-and-replace --file-id <fid> --old-text "旧文本" --new-text "新文本" --version-info '{}'
```

## 思维导图

```
tdocs-cli mind create-by-markdown --title "项目规划" --markdown @./mindmap.md
```

## 流程图

```
tdocs-cli flowchart create-by-mermaid --title "部署流程" --mermaid @./flowchart.mmd
```

## 知识库空间

```
tdocs-cli space create-space --title "团队知识库"
tdocs-cli space query-space-list --query-by 1 --order-by 2 --descending true --jq '.spaces[:5]'
tdocs-cli space query-space-node --space-id <space-id>
```

## 图片 OCR

```
tdocs-cli ocr extract --img-base64 @./input.b64 --extract-type 2
tdocs-cli ocr images-to-excel --title "考勤表" --imgs-base64 @./day1.b64 --imgs-base64 @./day2.b64
tdocs-cli ocr images-to-word --title "扫描件" --imgs-base64 @./page1.b64 --imgs-base64 @./page2.b64
```

## 导入 / 导出

```
tdocs-cli workflow import-file --file ./report.xlsx
tdocs-cli workflow export-file --file-id <file-id> --dir ./downloads
```

## 网页剪藏（异步两步）

```
# 1. 提交剪藏任务，拿到 task_id
tid=$(tdocs-cli manage scrape-url --url "https://example.com/article" --jq '.task_id')
# 2. 轮询进度（3–5 秒一次，直到终态）
tdocs-cli manage scrape-progress --task-id "$tid"
```

## 输出与调试

```
tdocs-cli manage list-file --format table
tdocs-cli manage create-file --file-type smartcanvas --title demo --jq '.file_id'
tdocs-cli manage create-file --file-type smartcanvas --title demo --dry-run
```

## 提醒

命令和参数以 `tdocs-cli <group> <command> --help` 为准。
