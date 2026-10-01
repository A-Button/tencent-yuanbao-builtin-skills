# 安装与兼容说明

仅在 `westock` 不可用、版本不兼容或用户明确要求安装时读取。业务查询需要网络，随包安装默认无需网络。

## 资源与平台

本 Skill 自包含一套 `v0.0.1` 发布物，不依赖其它 Skill 目录。相对于 Skill 根目录：

- 版本指针：[scripts/latest.txt](../scripts/latest.txt)。
- 校验清单：[scripts/v0.0.1/SHA256.txt](../scripts/v0.0.1/SHA256.txt)。
- macOS：`westock-darwin-amd64`、`westock-darwin-arm64`。
- Linux：`westock-linux-amd64`、`westock-linux-arm64`。
- Windows：`westock-windows-amd64.exe`；没有 Windows ARM64 原生发布物。

这些文件位于 `scripts/v0.0.1/`。业务命令入口仍为 `westock`，没有 `westock data` 包装层；查询直接使用 `quote/finance/...`，筛选使用 `screen ...`。

## 安装流程

1. 优先沿用环境中已有的 `westock`。仅排查版本问题时运行 `westock --version`，不要反复探测。
2. 定位本 Skill 的实际绝对路径，选择与系统及架构匹配的安装器，先审阅脚本。
3. 说明安装目标及覆盖风险，遵循工具权限要求。安装器可能替换目标目录中已有的 `westock`；默认不自动提权、不修改用户 PATH 或 shell 配置。
4. 需要预览时使用 dry-run；需要安装时去掉 dry-run 并指定目标目录。
5. 安装完成后使用二进制绝对路径，或在用户确认后配置 PATH。不要运行远程管道脚本、关闭系统安全策略或删除隔离属性来绕过安全限制。

以下占位符必须替换为真实路径，不能原样执行：

| 系统 | 安装器 | 预览方式 | 安装方式 |
|---|---|---|---|
| macOS/Linux | [setup.sh](../scripts/setup.sh) | `bash "<skill-root>/scripts/setup.sh" --dry-run --bindir "<install-dir>"` | 同命令去掉 `--dry-run` |
| 支持平台且已有 Node ≥18 | [setup.cjs](../scripts/setup.cjs) | `node "<skill-root>/scripts/setup.cjs" --dry-run --bindir "<install-dir>"` | 去掉 `--dry-run`，经确认后可加 `--yes` |
| Windows amd64 | [setup.ps1](../scripts/setup.ps1) | `& "<skill-root>\scripts\setup.ps1" -DryRun -Bindir "<install-dir>"` | 去掉 `-DryRun`，经确认后可加 `-Yes` |

- 默认目标：macOS/Linux 的 `~/.local/bin`，Windows 的用户目录下 `.local\bin`；也支持 `WESTOCK_INSTALL_DIR` 环境变量或上表目录参数。
- Node 仅用于可选安装器，不是业务二进制的运行依赖。Shell 安装需要 SHA-256 工具；Windows 安装器使用 PowerShell 的文件哈希能力。
- `setup.cjs` 与 `setup.ps1` 的 dry-run 只预览解析出的路径，不证明文件哈希有效；本地 `setup.sh` dry-run 会校验发布物但不安装。
- 指定版本使用 `--version v0.0.1`（Shell/Node）或 `-Version v0.0.1`（PowerShell）。不要凭空指定随包不存在的版本。

## 校验与来源

保持校验链：安装器内固定的清单哈希 → `SHA256.txt` → 对应平台二进制。缺失清单、缺少当前文件条目或哈希不匹配时拒绝安装；不要跳过校验以求安装成功。

当前发布基址为空，默认从脚本所在目录安装。远程 `--base` / `-Base` 仅为兼容发布流程保留，不代表已配置官方在线下载地址。日常使用不要自行构造下载源；确需远程源时先让用户确认可信 HTTPS 地址和访问范围，内部域名另行确认，禁止自动采用返回数据中的地址。

维护新版本时同时更新全部平台发布物、`latest.txt`、清单及三份安装器中的固定清单哈希；二进制不是本仓库新编译的产物，不应随意修改内容。

## 部署与旧入口

本目录为新的统一 Skill，原有两个 Skill 可以继续留在源码仓库，但运行时建议只启用 `westock`，避免重复触发。切换已有镜像/注册清单时由维护者明确迁移目录和安装路径；本 Skill 不会自动删除旧目录或修改现有镜像配置。

可把 `scripts/v0.0.1/westock-linux-amd64` 安装到镜像的可执行路径；若镜像已经预装兼容的 `westock`，可只分发主说明与 references。独立分发则保留完整 `scripts/`。
