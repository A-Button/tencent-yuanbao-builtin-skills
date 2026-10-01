# 场景：文档审计

## 概述
文档审计包含两类视角：

1. **文档级审计**：查看单篇文档的访问记录、版本历史、版本间内容变更。
2. **空间级运营审计**（隐藏命令）：查询整个空间在某段时间内的 PV/UV/新增文档总览，以及按用户聚合的操作明细（创建、更新、评论、点赞、收藏、下载等）。

> 空间级审计命令 `iwiki-cli audit ...` 是隐藏命令，不会出现在 `iwiki-cli --help` 主列表里，但可以正常使用，主要面向空间管理员/运营做数据盘点。

## 功能列表

### 1. 查看文档访问记录

使用 `iwiki-cli viewlist` 命令查询指定文档的访问记录。

**命令格式：**
```bash
iwiki-cli viewlist <doc_id> [--limit <数量>] [--start <偏移量>]
```

**参数说明：**
| 参数 | 简写 | 默认值 | 说明 |
|------|------|--------|------|
| `doc_id` | - | 必填 | 文档 ID |
| `--limit` | `-l` | 20 | 每页返回数量 |
| `--start` | `-s` | 0 | 起始偏移量（用于分页） |

**示例：**
```bash
# 查询文档访问记录（默认前 20 条）
iwiki-cli viewlist 123456

# 指定每页数量
iwiki-cli viewlist 123456 --limit 10

# 查看第二页
iwiki-cli viewlist 123456 --limit 10 --start 10
```

**输出格式：**
```
用户名          访问次数  最后访问时间
------          --------  ----------------
张三(zhangsan)  5         2026-04-20 10:30:00
李四(lisi)      3         2026-04-19 14:20:00
```

### 2. 审查两个版本间的修改内容

通过组合 `iwiki-cli history` 和 `iwiki-cli get --version` 命令，可以对比文档任意两个版本之间的内容差异，用于审查变更。

#### 工作流程
**第一步：查看版本历史，确定要对比的版本号**
```bash
iwiki-cli history <doc_id> [--page <页码>] [--size <数量>]
```

| 参数 | 简写 | 默认值 | 说明 |
|------|------|--------|------|
| `doc_id` | - | 必填 | 文档 ID |
| `--page` | `-p` | 1 | 页码（从 1 开始） |
| `--size` | `-s` | 10 | 每页返回数量 |

**第二步：分别获取两个版本的文档内容**
```bash
# 获取旧版本内容
iwiki-cli get <doc_id> --version <旧版本号>

# 获取新版本内容
iwiki-cli get <doc_id> --version <新版本号>
```

**第三步：对比两个版本的内容差异**
将两个版本的 Markdown 内容进行逐段对比，总结出新增、删除和修改的内容。

### 3. 查询空间运营审计总览（PV/UV/新增文档）

使用 `iwiki-cli audit overall` 查询指定空间在某段时间内的总览数据，结果以 **CSV 格式输出到标准输出**，便于重定向到文件或交给下游分析。

```bash
iwiki-cli audit overall --space-key <space_key> [--start-date <yyyy-MM-dd>] [--end-date <yyyy-MM-dd>] 
```

具体参数与示例可通过 `iwiki-cli audit overall -h` 查看。需要注意：
- `--space-key` 必填（如 `~jaxxonli` 或团队空间 key）
- 未传日期时默认「截止昨天的最近 7 天」
### 4. 查询空间用户操作审计明细

使用 `iwiki-cli audit user` 按用户聚合查询空间内每个用户的操作数据

```bash
iwiki-cli audit user --space-key <space_key> [--start-date <yyyy-MM-dd>] [--end-date <yyyy-MM-dd>] [--start <offset>] [--limit <n>]
```

具体参数与示例可通过 `iwiki-cli audit user -h` 查看。需要注意：

- `--space-key` 必填，分页用 `--start` / `--limit`（默认 `0` / `10`）
- 日期默认行为同 `audit overall`

## 工作流程

1. **明确审计粒度**：用户要看的是「单篇文档」还是「整个空间」？
   - 单篇文档 → 走 `viewlist` / `history` / `get --version`
   - 整个空间 → 走 `audit overall` / `audit user`
2. **获取必要标识**：
   - 文档级：从链接或 ID 中提取 `doc_id`
   - 空间级：确认 `space-key`（个人空间形如 `~username`，团队空间为简短英文 key）
3. **执行查询**：根据需求运行对应的命令；空间级命令默认查最近 7 天，必要时再加 `--start-date` / `--end-date`
4. **展示结果**：
   - 文档级：以结构化文本展示
   - 空间级：CSV 输出可直接重定向到文件，或在终端展示前几行摘要
5. **分页浏览**：`viewlist` 用 `--start/--limit`，`audit user` 用 `--start/--limit`，根据需要翻页

## 注意事项
- 访问记录按最后访问时间排序
- 版本历史按版本号从新到旧排列
- `history`、`get --version`、`audit overall`、`audit user` 都是隐藏命令，不会出现在 `--help` 主列表中，但可以正常使用
- 如果文档 ID 或 space-key 无效、无权限，会返回错误提示
- 对比版本内容时，建议先确认版本号范围再拉取内容，避免不必要的请求
- `audit overall` 与 `audit user` 的日期参数必须**同时提供或同时省略**；只传一个会报错
- 默认日期窗口截止到「昨天」（不含今天），因为后端要求结束日期不能晚于今天且当天数据可能未生成
- 空间运营审计接口属于运营/排障数据，使用前请确认你对该空间有相应权限
