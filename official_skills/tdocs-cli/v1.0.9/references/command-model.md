# 命令结构

## 命令分组

```
tdocs-cli
├── version          # 版本信息
├── auth             # 认证管理
├── cache            # 缓存管理
├── manage           # 文件管理（含网页剪藏 scrape-url / scrape-progress）
├── smartcanvas      # 智能文档操作（仅用户明确要求时新建）
├── doc              # 文档编辑（论文、公文、合同等）
├── sheet            # 在线表格（仅已有在线 Sheet 的有限小改）
├── slide            # 在线 PPT（仅已有在线 PPT 的白名单内小改）
├── mind             # 思维导图
├── flowchart        # 流程图
├── space            # 知识库空间管理
├── ocr              # 图片 OCR
└── workflow         # 跨命令异步工作流（导入/导出）
```

`version`、`auth`、`cache` 是固定命令；其余服务的子命令可能随服务端更新变化。

## 查看命令与参数

```
tdocs-cli --help                       # 列出所有命令组
tdocs-cli <group> --help               # 列出组内命令
tdocs-cli <group> <command> --help     # 非 slide：列出参数、类型、默认值、是否必填
tdocs-cli slide <command> -h           # slide 子命令统一写法
tdocs-cli <group> <command> --help --utility   # 非 slide：同时显示工具类/辅助命令
```

运行时帮助是参数签名的权威来源；本 skill 的白名单决定是否允许调用。`slide` 子命令统一用 `tdocs-cli slide <command> -h`，其余命令用 `--help`。

## 命名规则

CLI 统一使用 kebab-case：

| 示例 | CLI 写法 |
|---|---|
| 导入文件 | `import-file` |
| 文件 ID 参数 | `--file-id` |
| 创建文档 | `create-file` |

## 命令找不到时

```
tdocs-cli cache refresh
tdocs-cli --help
```
