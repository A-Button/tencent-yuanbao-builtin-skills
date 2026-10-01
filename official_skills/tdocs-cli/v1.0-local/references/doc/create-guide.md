# 在线 DOC 创建指南

用户明确要求腾讯文档或在线 Word 类文档时使用本指南。普通本地 `.docx` 创建仍使用 `docx` skill。

## 首选路径：一步创建

准备好完整 Markdown 后，优先使用 `doc create-with-markdown` 一次创建并写入：

```bash
tdocs-cli doc create-with-markdown --title "<文档标题>" \
    --base64-markdown "$(printf '%s' '<markdown 正文>' | base64 | tr -d '\n')"
```

长内容可先保存在临时工作目录，再对完整内容做 base64 编码。不要修改或覆盖用户输入文件。

## 标准流程

1. 根据用户要求准备完整 Markdown，保留原文中的事实、数字和必要结构。
2. 执行一次 `doc create-with-markdown`。
3. 从响应的 `.data.file_id` 和 `.data.file_url` 及时记录实际 ID 与链接。
4. 后续追加、样式或修订始终复用该 `file_id`。
5. 用 `manage get-content` 通读验收正文；需要检查标题、列表或样式坐标时再查询 DOC 结构。
6. 最终按根 `SKILL.md` 的 `media_info type=tencent_docs` 规范交付原始链接。

## 同一资源复用

- 创建成功后，当前任务的文档身份就是返回的 `file_id`。
- 用户要求继续修改刚创建的文档时，保持同一链接和同一 `file_id`。
- 不通过删除重建来完成已有文档的修订。
- 命令失败时先诊断原因，禁止原样重试。

## 用户提供现成文件

用户提供 `.docx` 且要求原样导入腾讯文档时，走 `workflow import-file` 路由，不要先把内容重建成另一份在线 DOC。导入和取链流程以 `cmd-workflow.md` 为准。

## 创建后验收

至少确认：

- 标题与正文已写入；
- 关键数字、专有名词和用户要求保留的原文未被误改；
- 没有重复章节；
- 后续编辑使用创建返回的同一个 `file_id`；
- 最终交付链接来自工具原始返回，或对同一 `file_id` 的单次补查。

若验收失败，先判断是内容生成问题、参数错误还是服务端限制。
