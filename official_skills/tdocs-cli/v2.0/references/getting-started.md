# 安装与授权

> 本文是写给 **Agent** 的标准作业程序（SOP）。每一步都有"做什么 / 为什么 / 不要做什么"。
> 严格按编号顺序执行，不要跳步，不要把内部细节（后台 PID、状态文件、stderr TUI、二维码）泄露给用户。

---

## 一、安装

### macOS / Linux

```
curl -fsSL https://txdocs-addon-1251316161.cos.ap-guangzhou.myqcloud.com/static/tdocs/install.sh | sh
```

### Windows（PowerShell）

```
irm https://txdocs-addon-1251316161.cos.ap-guangzhou.myqcloud.com/static/tdocs/install.ps1 | iex
```

默认装到 `~/.local/bin/`（*nix）或 `%LOCALAPPDATA%\bin\`（Windows）。如提示找不到命令，把该路径加入 `PATH`。
验证：`tdocs-cli version`。

---

## 二、授权（OAuth Device Flow）

### Step 1. 拉起授权

```
tdocs-cli auth login --detach
```

CLI 在后台轮询授权，并尝试打开浏览器，stdout 输出单行 JSON：

```
{"event":"verification","verification_uri_complete":"...","user_code":"XXXX","expires_in":600}
```

读取 `verification_uri_complete` 与 `user_code`，按下面模板**原样**展示给用户：

```
请在浏览器打开：<verification_uri_complete>
授权码 <user_code>（10 分钟有效）
```

配套两条状态命令（CLI 自身管理，**不要**自行写脚本轮询）：

| 命令 | 用途 | 输出（单行 JSON） |
|---|---|---|
| `tdocs-cli auth login --status` | 查后台授权状态 | `{"state":"polling \| done \| denied \| expired \| error \| canceled \| none", ...}` |
| `tdocs-cli auth login --cancel` | 终止后台授权 | `{"state":"canceled \| none", ...}` |

### Step 2. 等待用户回复

> ✅ **触发条件**：用户明确回复"已授权 / 完成 / 好了"、"取消 / 不登录了"或"重试 / 链接打不开"等语义后，**才执行本步骤**。在此之前不要主动轮询 `--status`。

| 用户回复语义 | 行为 |
|---|---|
| 已完成 | 进入 Step 3 |
| 放弃 | 执行 `tdocs-cli auth login --cancel`，中止流程 |
| 重试 | 执行 `tdocs-cli auth login --cancel`，回 Step 1 重新走一遍 |

### Step 3. 验证最终授权结果

```
tdocs-cli auth status
```

> 注意：这里是 `auth status`（验证 token 是否生效），不是 `auth login --status`（查后台 device flow 进度）。

| 输出 | 处理 |
|---|---|
| `authorized` | 回 `SKILL.md` 第 3 步继续用户原指令 |
| `unauthorized` | 告诉用户"未检测到授权完成，请确认浏览器内是否点了同意"，再次询问"已授权 / 重试 / 取消"，按 Step 2 分支处理；不限次数，由用户决定何时放弃 |

---

## 硬性约束（授权场景）

1. **不要自己打开浏览器**：CLI 已尝试打开（macOS `open` / Linux `xdg-open` / Windows `rundll32`），不要再调 `xdg-open`、`open`、`Start-Process <url>` 等命令。
2. **不要写脚本轮询**：`--status` 由用户回复触发，不要 `while sleep` / `for` 循环主动查。
3. **不泄漏内部细节**：后台 PID、状态文件路径、stderr TUI、二维码等只是实现细节，不要展示给用户。
4. **取消/重试必须先 cancel**：放弃或重试前先 `auth login --cancel`，避免后台轮询泄露。