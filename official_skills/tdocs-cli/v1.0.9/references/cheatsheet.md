# 速查表

高频命令快速参考。

## 文件管理

```
tdocs-cli manage create-file --type 8 --title demo  # 仅用户明确要求 smartcanvas 时
tdocs-cli manage list-file --list-type 1 --jq '.files[] | {file_id, name, ext}'
tdocs-cli manage apply-download --file-id '<file_id>'
tdocs-cli manage query-task --task-id <task-id>
```

## 智能文档

```
# 仅用户明确要求 smartcanvas 时新建；此时首选一步 create-smartcanvas-by-mdx
tdocs-cli smartcanvas create-smartcanvas-by-mdx --title "文档标题" --mdx @./body.mdx

# 兜底：两步流程（仅在需指定父目录/分多段写入时使用）
# 不用 --jq，保留 create-file 完整 JSON 中的 file_id 和 doc_url
tdocs-cli manage create-file --type 8 --title "文档标题"
tdocs-cli smartcanvas edit --file-id '<file_id>' --action 2 --content @./body.mdx
# 若完整响应没有可用链接，只补查一次
tdocs-cli manage query-file-info --file-id '<file_id>' --jq '.file | {file_id, name, doc_url}'

# 读取
tdocs-cli smartcanvas get-top-level-pages --file-id '<file_id>'
tdocs-cli smartcanvas read --file-id '<file_id>' --page-id <page_id>
# read 是分页接口，长文必须循环 --next-token 直到为空；
# 通读全文优先用非分页接口：
tdocs-cli manage get-content --file-id '<file_id>'
# 想通读整篇就要真的读全：翻页到 next_token 为空，或用 get-content 一次拿全；
# 别只取前几行就当作读完。只想找某个字段或某一段，用 find --query 更直接；
# 计数或提取 ID 可用单次管道或内联命令遍历完整输出，不创建脚本文件；
# 大文档用 --jq '.content' --format plain > /tmp/x.txt 落盘，再用 Read 分段读完
```

## 文档编辑

```
tdocs-cli doc resolve-document-structure --file-id '<file_id>' --version-info '{}'
tdocs-cli doc insert-markdown --file-id '<file_id>' --idx "$idx" --markdown "## 新标题" --version-info '{}'
tdocs-cli doc find-and-replace --file-id '<file_id>' --old-text "旧文本" --new-text "新文本" --version-info '{}'
```

## 在线 PPT 编辑（已有文档）

```
tdocs-cli slide slide-get-info --file-id '<file_id>'
tdocs-cli slide slide-get-page-info --file-id '<file_id>' --page-index 2
tdocs-cli slide slide-set-text --file-id '<file_id>' --page-index 2 --shape-id '<shape_id>' --text "新标题"
tdocs-cli slide slide-add-text --file-id '<file_id>' --page-index 2 --x 60 --y 320 --w 400 --h 40 --text "备注"
tdocs-cli slide slide-remove-slide --file-id '<file_id>' --page-index 4
```

`page_index` 从 0 开始；坐标单位是磅（pt）；`shape_id` 只使用在线命令的真实返回。新增命令未返回 ID 时重新 `slide-get-page-info`。新建 PPT 不走这里。

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
tdocs-cli workflow export-file --file-id '<file_id>' --dir ./downloads
```

## 网页剪藏（异步两步）

```
# 1. 提交剪藏任务，拿到 task_id
tid=$(tdocs-cli manage scrape-url --url "https://example.com/article" --jq '.task_id')
# 2. 轮询进度（3–5 秒一次，直到终态）
tdocs-cli manage scrape-progress --task-id "$tid"
```

## 输出与安全诊断

```
tdocs-cli manage list-file --list-type 1 --format table
tdocs-cli manage list-file --list-type 1 --jq '.files[0].file_id'
tdocs-cli manage create-file --type 8 --title demo --dry-run
```

## 提醒

命令参数以运行时帮助为准：`slide` 子命令用 `tdocs-cli slide <command> -h`，其余命令用 `--help`；是否允许调用仍以根 `SKILL.md` 白名单为准。
