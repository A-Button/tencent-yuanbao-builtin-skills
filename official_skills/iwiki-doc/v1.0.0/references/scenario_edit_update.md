# 场景：编辑和更新文档

**快捷命令：**
```bash
# 仅修改标题
iwiki-cli update 123456 --title "新标题" --rename-only

# 更新文档内容（从命令行指定）
iwiki-cli update 123456 --title "标题" --body "# 更新内容..."

# 更新文档内容（从文件读取）
iwiki-cli update 123456 --title "标题" --file ./content.md

# 在文档末尾追加
iwiki-cli append 123456 --after "## 新章节..."

# 移动文档
iwiki-cli move 123456 --parent 789012

# 复制文档
iwiki-cli copy 123456 --parent 789012

# 更新 HTML 文档（content_type=CTX，详见 scenario_create_import.md）
iwiki-cli update-html 123456 --file ./page.html
```

> **HTML 文档更新说明：** `iwiki-cli update` 仅适用于 MD / DOC 类文档。必须使用 `iwiki-cli update-html` 命令进行更新，详细用法见
> [scenario_create_import.md](./scenario_create_import.md) 示例 6。


## 核心工具
### 1. update --rename-only - 仅修改标题
**何时使用：**
- 只需要修改文档标题
- 不改变文档正文内容
**用法：**
```bash
iwiki-cli update 123456 --title "新的文档标题" --rename-only
```

### 2. update - 完整更新文档
**何时使用：**
- 更新整个文档内容
- 修改文档的大部分内容
- 需要重新生成文档结构
**用法：**
```bash
# 从命令行指定内容
iwiki-cli update 123456 --title "文档标题" --body "# 新内容\n\n..."

# 从文件读取内容（推荐，适合大量内容）
iwiki-cli update 123456 --title "文档标题" --file ./content.md

# 如果本地所属的空间需要审批
iwiki-cli update 123456 --title "文档标题" --file ./content.md --comment "修复错误描述"
```
**参数：**
| 参数 | 缩写 | 默认值 | 说明 |
|------|------|--------|------|
| `--title` | `-t` | "" | 文档标题（不指定则保持原标题） |
| `--body` | `-b` | "" | 直接指定文档内容 |
| `--file` | `-f` | "" | 从文件读取内容 |
| `--rename-only` | `-r` | false | 仅重命名标题，不修改内容 |

### 3. append - 局部更新
注意：追加图片附件链接的时候不能使用，要使用update
**何时使用：**
- 在文档开头插入内容
- 在文档末尾追加内容
- **只在用户明确要求时使用**
- **注意：若文档所在空间开启了审批，`append` 不支持，需改用 `update` + `--comment`**
**用法：**
#### 在开头插入
```bash
iwiki-cli append 123456 --before "# 新增的开头内容"
```

#### 在末尾追加
```bash
iwiki-cli append 123456 --after "## 附加章节\n\n这是追加的内容"
```

#### 从文件读取
```bash
iwiki-cli append 123456 --before-file ./header.md
iwiki-cli append 123456 --after-file ./appendix.md
```

**参数：**
| 参数 | 缩写 | 默认值 | 说明 |
|------|------|--------|------|
| `--title` | `-t` | "" | 文档标题（可选，不指定则保持原标题） |
| `--before` | | "" | 在文档开头插入的内容 |
| `--after` | | "" | 在文档结尾追加的内容 |
| `--before-file` | | "" | 从文件读取要插入到开头的内容 |
| `--after-file` | | "" | 从文件读取要追加到结尾的内容 |

### 4. move - 移动文档
**何时使用：**
- 调整文档位置
- 移动到其他父目录
- 调整文档顺序
**用法：**
```bash
# 移动到新父目录（追加到末尾）
iwiki-cli move 123456 --parent 789012

# 移动到目标文档下方
iwiki-cli move 123456 --parent 789012 --position below --target 9876

# 移动到目标文档上方
iwiki-cli move 123456 --parent 0 --position above --target 9876
```
**参数：**
| 参数 | 缩写 | 默认值 | 说明 |
|------|------|--------|------|
| `--parent` | `-p` | 0 | 新的父目录 ID，不变则传 0 |
| `--position` | `-P` | "append" | 位置：append / below / above |
| `--target` | `-T` | 0 | 目标文档 ID（position 为 below/above 时必填） |
| `--no-wait` | | false | 不等待任务完成，直接返回 task_id |
| `--interval` | | 1 | 轮询间隔（秒） |

**position 说明：**
- `append`：追加到目标目录末尾
- `below`：插入到某个文档之下（需要指定 --target）
- `above`：插入到某个文档之上（需要指定 --target）

### 5. copy - 复制文档
**何时使用：**
- 需要复制文档到新位置
- 备份重要文档
**用法：**
```bash
iwiki-cli copy 123456 --parent 789012
```
**参数：**
| 参数 | 缩写 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--parent` | `-p` | **是** | 0 | 目标父目录 ID |


## 实践示例
### 示例 1：更新文档内容
**用户需求：** "更新文档 123456 的内容"
**执行步骤：**
1. **获取原文档内容（可选）**
```bash
iwiki-cli get 123456
```
2. **修改内容并保存到文件**
```
在原内容基础上进行修改，保存为 content.md
```
3. **更新文档**
```bash
iwiki-cli update 123456 --title "标题" --file ./content.md
```

### 示例 2：在文档开头插入提示
**用户需求：** "在文档开头添加一个重要提示"
**执行步骤：**
```bash
iwiki-cli append 123456 --before "> **重要提示：** 本文档已更新，请注意查看最新版本。"
```

### 示例 3：移动文档到新位置
**用户需求：** "将文档 123456 移动到文档 789012 下"
**执行步骤：**
```bash
iwiki-cli move 123456 --parent 789012
```

### 示例 4：复制文档
**用户需求：** "将文档 123456 复制到另一个目录"
**执行步骤：**
```bash
iwiki-cli copy 123456 --parent 789012
```

## 审批流程

部分空间（如规范类、对外公开的知识库等）开启了审批机制，**发布新文档或修改文档内容都需要先提交审批**，由管理员审核通过后才会正式生效。

#### 未提供 `--comment` 时
CLI 拒绝执行并给出提示：
```
当前空间发布/修改文档需要进行审批，是否提交审批？
参考命令: iwiki-cli update 123456 --title 文档名 --file <file> --comment "申请理由"
```
#### 提供 `--comment` 后
CLI 自动走审批流程（无需人工判断）：
审批提交成功后输出：
```
文档 123456 审批已提交
```