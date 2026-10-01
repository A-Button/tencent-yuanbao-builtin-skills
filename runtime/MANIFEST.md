# 沙盒运行时组件归档清单

本归档收集了沙盒中除技能目录
之外的关键运行时组件。这些文件共同构成沙盒的隔离、执行、网络与工具链。

## 目录结构与原路径对照

每个子目录名即代表该类文件的原始位置。

### `opt_yb/` — `/opt/yb/sandboxd`

| 归档内路径 | 原绝对路径 | 大小 | 权限 | 类型 |
|---|---|---|---|---|
| `opt_yb/sandboxd` | `/opt/yb/sandboxd` | 15,819,046 B（约 15.1 MiB） | `-rwxr-xr-x` | ELF 64-bit LSB executable，**statically linked**（静态链接），`not stripped`（带符号表） |

Go 语言编写，是沙盒隔离的真正执行者。启动时由 `supervisord` 以
`priority=20` 拉起，配置见 `/opt/yb/supervisor/conf.d/sandboxd.conf`。

### `platform_cli/` — `/usr/local/bin/` 下的平台 CLI 工具

| 归档内路径 | 原绝对路径 | 大小 | 权限 | 类型 |
|---|---|---|---|---|
| `platform_cli/yuanbao-cli` | `/usr/local/bin/yuanbao-cli` | 10,559,672 B | `-rwxr-xr-x` | ELF 64-bit，**dynamically linked**，**stripped**（无符号表） |
| `platform_cli/westock` | `/usr/local/bin/westock` | 2,676,568 B | `-rwxr-xr-x` | ELF 64-bit，**statically linked**，**no section header**（节区头被移除） |
| `platform_cli/magika` | `/usr/local/bin/magika` | 32,548,800 B（约 31 MiB） | `-rwxr-xr-x` | 文件类型识别工具（Mozilla 出品的 Magika） |
| `platform_cli/tdocs-cli` | `/usr/local/bin/tdocs-cli` | 10,559,672 B | `-rwxr-xr-x` | 腾讯在线文档 CLI |
| `platform_cli/app` | `/usr/local/bin/app` | 25,615 B | `-rwxr-xr-x` | Python 脚本，UTF-8 编码，可直接读源码 |

说明：
- `tdocs-cli` 与 `yuanbao-cli` **字节大小完全相同**（10,559,672 B），但 MD5 不同，
  说明是**不同构建但体积巧合相同的两个二进制**。
- `yuanbao-cli`、`tdocs-cli` 已 `strip`，符号表不可见；`westock` 节区头被移除，
  需靠 `strings` / `objdump -d` 逆向分析。

### `py_scripts/` — `/opt/yb/bin/` 下的两个隔离脚本

| 归档内路径 | 原绝对路径 | 大小 | 权限 | Shebang |
|---|---|---|---|---|
| `py_scripts/nexus-isolation.py` | `/opt/yb/bin/nexus-isolation.py` | 902 B | `-rwxr-xr-x` | `#!/usr/bin/python3` |
| `py_scripts/nexus-userns.py` | `/opt/yb/bin/nexus-userns.py` | 1,502 B | `-rwxr-xr-x` | `#!/usr/bin/python3` |

这两个脚本是沙盒边界的真正定义，核心逻辑如下：

**`nexus-isolation.py`**（902 B）
- 作用：在容器的 mount namespace 内启动 Nexus，**不使用 bwrap**。
- 启动目标：`/nix/runtime/nix-env/bin/bash /nix/runtime/nexus/deployment/runtime/start.sh`
  `--host 0.0.0.0 --port 32000 --python-version 3.10`
- 端口从环境变量 `NEXUS_RUNTIME_PORT` 读取，默认 32000，合法范围 1–65535。
- Python 版本从 `NEXUS_PYTHON_VERSION` 读取，默认 `3.10`。
- 注释明确：启动时**不访问 Wiki storage**；共享 mount namespace 让 Nexus
  能观察到快照恢复后挂载的卷，行为类似 sandboxd。
- 通过 `os.execv` 替换进程。

**`nexus-userns.py`**（1,502 B）
- 作用：在 bwrap 之前把普通容器用户映射到隔离的 user namespace。
- 实现：父进程 `fork` 出子进程 → 子进程调用 `unshare(0x10000000)`，
  即 `CLONE_NEWUSER`（创建新的用户命名空间）→ 通过管道同步 →
  **父进程以容器命名空间中的能力写入子进程的 `uid_map` / `gid_map`**：
  内容为 `0 0 65536\n`（即把容器内的 root 映射到隔离命名空间中的 root，
  范围 0–65535）。
- 关键注释："The trusted parent writes the maps while it still has capabilities
  in the container namespace. The child cannot modify these maps afterwards."
  这保证了映射关系在写入后不可篡改。
- 采用双管道（ready / release）做同步握手，确保映射先于子进程继续执行完成。

### `ca_certs/` — `/usr/local/share/ca-certificates/` 下的自定义 CA

| 归档内路径 | 原绝对路径 | 大小 | 权限 | 格式 |
|---|---|---|---|---|
| `ca_certs/zeroproxy-ca.crt` | `/usr/local/share/ca-certificates/zeroproxy-ca.crt` | 1,164 B | `-rw-r--r--` | PEM 证书（`-----BEGIN/END CERTIFICATE-----`） |

证书主体解析：
- **Subject / Issuer**：`CN=ZeroProxy MITM CA`，`O=ZeroProxy`
- **序列号**：`RMUs5xBw4Ph7dN1m9iMWCD`
- **有效期**：`2026-09-23 03:27:24Z` 至 `2125-08-30 03:27:24Z`（100 年有效期，
  典型的中间人代理自签名 CA 特征）
- **公钥算法**：RSA 2048-bit
- **用途**：这是沙盒出站流量的 **MITM（中间人）代理 CA**——沙盒内所有 HTTPS
  请求会被 ZeroProxy 解密并重签，故需把该 CA 导入信任链。这是理解沙盒
  网络模型的关键证据。

### `apparmor/` — `/opt/google/chrome/apparmor.d/` 下的 AppArmor 配置

| 归档内路径 | 原绝对路径 | 大小 | 权限 | 格式 |
|---|---|---|---|---|
| `apparmor/google-chrome-stable` | `/opt/google/chrome/apparmor.d/google-chrome-stable` | 468 B | `-rw-r--r--` | AppArmor profile 文本 |

配置内容要点：
- `abi <abi/4.0>,` — 使用 AppArmor 4.0 ABI。
- `profile google-chrome-stable /opt/google/chrome/chrome flags=(unconfined)`
  即**针对 Chrome 主二进制的 profile，但标记为 `unconfined`（不限制）**。
- `userns,` — 允许创建用户命名空间（**这是沙盒在 Ubuntu 23.10+ 上工作的
  前提**，注释引用了 Ubuntu 官方博文：
  https://ubuntu.com/blog/ubuntu-23-10-restricted-unprivileged-user-namespaces ）。
- `include if exists <local/google-chrome-stable>` — 可选的站点级覆盖。

## 沙盒启动链路（供交叉参考）

```
PID 1: ags_runtime_entrypoint.sh
  └─ supervisord
      ├─ priority 10: envd          （环境守护）
      ├─ priority 20: sandboxd      （本归档 opt_yb/sandboxd）
      └─ priority 30: nexus-runtime （由 nexus-isolation.py / nexus-userns.py 配置）
```

入口脚本会执行：`mkdir -p /run/yb /var/lib/yb-sandboxd /data/workspace
/data/inputs /data/outputs /data/skills`。

## 相关路径备忘（本次未归档，供定位）

- 技能目录：`/mnt/official_skills/`
- Chromium 浏览器：`/opt/chromium/chrome-linux/chrome`（525 MiB）
- 官方 Chrome：`/opt/google/chrome/chrome`（293 MiB，带 MEIPreload / WidevineCdm / PrivacySandboxAttestations）
- matplotlib 缓存：`/opt/matplotlib/`（含中文字体配置，沙盒绘图中文显示依赖此配置）
- supervisord 配置：`/opt/yb/supervisor/conf.d/`（sandboxd.conf / envd.conf / nexus-runtime.conf）
- 软链接链：`/usr/local/bin/chrome → /usr/bin/google-chrome-stable → /opt/google/chrome/google-chrome`
