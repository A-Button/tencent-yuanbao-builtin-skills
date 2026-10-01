#!/usr/bin/env python3
"""
iWiki CLI 安装脚本 (跨平台 Python 版本)

支持 Linux / macOS / Windows，无额外依赖（仅用标准库）。

用法:
    python install_cli.py                         # 安装最新版本
    python install_cli.py --version v0.0.7        # 安装指定版本
    python install_cli.py --dir ~/.local/bin      # 安装到自定义目录
    python install_cli.py --check                 # 仅检查最新版本
"""

import argparse
import hashlib
import json
import os
import platform
import shutil
import stat
import sys
import tempfile
import urllib.error
import urllib.request

# ── 配置 ────────────────────────────────────────────────────────────────────
MIRRORS_BASE = "https://mirrors.tencent.com/repository/generic/iwiki-cli"
BINARY_NAME = "iwiki-cli"

# ── 颜色输出 ────────────────────────────────────────────────────────────────
_NO_COLOR = os.environ.get("NO_COLOR") or (sys.platform == "win32" and not os.environ.get("WT_SESSION"))

def _c(code, text):
    if _NO_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"

def info(msg):    print(f"{_c('34', '[INFO]')} {msg}")
def success(msg): print(f"{_c('32', '[ OK ]')} {msg}")
def warn(msg):    print(f"{_c('33', '[ ! ]')} {msg}")
def error(msg):
    print(f"{_c('31', '[ X ]')} {msg}", file=sys.stderr)
    sys.exit(1)


# ── 系统检测 ────────────────────────────────────────────────────────────────
def detect_os():
    s = platform.system().lower()
    if s == "linux":
        return "linux"
    if s == "darwin":
        return "darwin"
    if s == "windows":
        return "windows"
    error(f"不支持的操作系统: {s}")

def detect_arch():
    m = platform.machine().lower()
    if m in ("x86_64", "amd64"):
        return "amd64"
    if m in ("aarch64", "arm64"):
        return "arm64"
    error(f"不支持的架构: {m}")

def default_install_dir(os_name):
    if os_name == "darwin":
        return os.path.join(os.path.expanduser("~"), ".iwiki")
    if os_name == "windows":
        local = os.environ.get("LOCALAPPDATA", os.path.join(os.path.expanduser("~"), "AppData", "Local"))
        return os.path.join(local, "iwiki-cli")
    # linux
    return "/usr/local/iwiki-cli"


# ── 网络工具 ────────────────────────────────────────────────────────────────
def download(url, dest=None, timeout=120):
    """下载文件，返回路径或字节内容"""
    req = urllib.request.Request(url, headers={"User-Agent": "iwiki-cli-installer/1.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        error(f"下载失败 (HTTP {e.code}): {url}")
    except urllib.error.URLError as e:
        error(f"下载失败 (网络错误): {e.reason}\n  地址: {url}")

    data = resp.read()
    if dest:
        with open(dest, "wb") as f:
            f.write(data)
        return dest
    return data

def fetch_json(url):
    try:
        data = download(url, timeout=15)
        return json.loads(data)
    except (json.JSONDecodeError, SystemExit):
        return None

def head_header(url, header_name):
    """发送 HEAD 请求，获取指定响应头"""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "iwiki-cli-installer/1.0"})
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return resp.headers.get(header_name, "").strip()
    except Exception:
        return ""


# ── 版本获取 ────────────────────────────────────────────────────────────────
def fetch_latest_version():
    info("正在获取最新版本...")
    obj = fetch_json(f"{MIRRORS_BASE}/version.json")
    if obj and obj.get("version"):
        return obj["version"]
    error("无法获取最新版本号，请通过 --version 手动指定版本")


# ── 文件校验 ────────────────────────────────────────────────────────────────
def validate_binary(filepath, os_name):
    """校验下载的文件是有效的可执行文件"""
    size = os.path.getsize(filepath)
    if size == 0:
        error("下载文件为空")

    with open(filepath, "rb") as f:
        magic = f.read(4)

    if os_name == "windows":
        # PE 文件以 MZ 开头
        if magic[:2] != b"MZ":
            error("下载内容不是有效的 Windows 可执行文件（可能是 HTML 错误页），请检查版本号或网络")
    else:
        # ELF: \x7fELF  |  Mach-O: various magic numbers
        valid_magics = [
            b"\x7fELF",          # ELF (Linux)
            b"\xcf\xfa\xed\xfe", # Mach-O 64-bit
            b"\xce\xfa\xed\xfe", # Mach-O 32-bit
            b"\xca\xfe\xba\xbe", # Mach-O Universal
            b"\xfe\xed\xfa\xcf", # Mach-O 64-bit (BE)
            b"\xfe\xed\xfa\xce", # Mach-O 32-bit (BE)
        ]
        if magic not in valid_magics:
            error("下载内容不是有效的可执行文件（可能是 HTML 错误页），请检查版本号或网络")

def verify_checksum(filepath, url):
    """通过 HEAD 请求获取 X-Checksum-Sha256 并验证"""
    info("正在验证 checksum...")
    expected = head_header(url, "X-Checksum-Sha256")
    if not expected:
        expected = head_header(url, "x-checksum-sha256")
    if not expected:
        warn("未获取到 X-Checksum-Sha256 响应头，跳过 checksum 验证")
        return

    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    actual = sha.hexdigest()
    expected = expected.lower().strip()

    if actual == expected:
        success(f"checksum 验证通过 (sha256: {actual[:16]}...)")
    else:
        error(f"checksum 验证失败！\n  期望: {expected}\n  实际: {actual}\n文件可能已损坏或被篡改，请重试")


# ── PATH 管理 ───────────────────────────────────────────────────────────────
def ensure_in_path(install_dir, os_name):
    """检查并提示将安装目录添加到 PATH"""
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    # 规范化比较
    norm = os.path.normcase(os.path.normpath(install_dir))
    if any(os.path.normcase(os.path.normpath(d)) == norm for d in path_dirs):
        return  # 已在 PATH 中

    if os_name == "windows":
        _add_to_path_windows(install_dir)
    else:
        _add_to_path_unix(install_dir)

def _add_to_path_unix(install_dir):
    """Unix: 自动写入 shell 配置文件"""
    shell = os.path.basename(os.environ.get("SHELL", "bash"))
    # 按优先级检测配置文件
    candidates = []
    home = os.path.expanduser("~")
    if shell == "zsh":
        candidates = [os.path.join(home, ".zshrc"), os.path.join(home, ".zprofile")]
    elif shell == "fish":
        conf_dir = os.path.join(home, ".config", "fish", "conf.d")
        candidates = [os.path.join(conf_dir, "iwiki-cli.fish")]
    else:
        candidates = [os.path.join(home, ".bashrc"), os.path.join(home, ".bash_profile"), os.path.join(home, ".profile")]

    export_line = f'export PATH="$PATH:{install_dir}"'
    if shell == "fish":
        export_line = f"fish_add_path {install_dir}"

    # 找到第一个已存在的配置文件，或使用第一个候选
    rc_file = candidates[0]
    for c in candidates:
        if os.path.isfile(c):
            rc_file = c
            break

    # 检查是否已经写过
    if os.path.isfile(rc_file):
        with open(rc_file, "r") as f:
            content = f.read()
        if install_dir in content:
            success(f"PATH 已在 {rc_file} 中配置")
            os.environ["PATH"] = f"{os.environ['PATH']}{os.pathsep}{install_dir}"
            return

    # 写入
    try:
        os.makedirs(os.path.dirname(rc_file), exist_ok=True)
        with open(rc_file, "a") as f:
            f.write(f"\n# iWiki CLI\n{export_line}\n")
        os.environ["PATH"] = f"{os.environ['PATH']}{os.pathsep}{install_dir}"
        success(f"已自动添加到 {rc_file}（新终端窗口自动生效）")
    except OSError as e:
        warn(f"无法写入 {rc_file}: {e}")
        warn(f"请手动添加: {export_line}")

def _add_to_path_windows(install_dir):
    """Windows: 自动写入用户 PATH 注册表"""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_ALL_ACCESS)
        try:
            user_path, _ = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            user_path = ""
        if install_dir.lower() not in user_path.lower():
            new_path = f"{user_path};{install_dir}" if user_path else install_dir
            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
            os.environ["PATH"] = f"{os.environ['PATH']}{os.pathsep}{install_dir}"
            success("已将安装目录添加到用户 PATH（新终端窗口自动生效）")
        winreg.CloseKey(key)
    except Exception as e:
        warn(f"无法自动添加 PATH，请手动将 {install_dir} 添加到系统环境变量 PATH 中")


# ── 主流程 ──────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="iWiki CLI 安装脚本")
    parser.add_argument("--version", "-v", default=os.environ.get("IWIKI_CLI_VERSION", ""),
                        help="指定版本号 (如 v0.0.7)，默认安装最新版本")
    parser.add_argument("--dir", "-d", default=os.environ.get("IWIKI_CLI_INSTALL_DIR", ""),
                        help="安装目录")
    parser.add_argument("--check", "-c", action="store_true",
                        help="仅检查最新版本，不安装")
    args = parser.parse_args()

    print()

    # 检测系统
    os_name = detect_os()
    arch = detect_arch()
    success(f"系统: {os_name}/{arch}")

    # 确定版本
    version = args.version or fetch_latest_version()
    if not version:
        error("版本号为空，请通过 --version 手动指定版本")
    success(f"目标版本: {version}")

    if args.check:
        print(f"\n最新版本: {version}")
        return

    # 确定安装目录
    install_dir = args.dir or default_install_dir(os_name)
    install_dir = os.path.expanduser(install_dir)

    # 构建下载 URL
    ext = ".exe" if os_name == "windows" else ""
    filename = f"{BINARY_NAME}-{version}-{os_name}-{arch}{ext}"
    url = f"{MIRRORS_BASE}/{version}/{filename}"
    info(f"下载地址: {url}")

    # 创建安装目录
    os.makedirs(install_dir, exist_ok=True)

    # 下载到临时文件
    info("正在下载...")
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=ext)
    os.close(tmp_fd)
    try:
        download(url, tmp_path)

        # 校验文件格式
        validate_binary(tmp_path, os_name)

        # Checksum 验证
        verify_checksum(tmp_path, url)

        # 移动到安装目录
        binary_ext = ".exe" if os_name == "windows" else ""
        dest = os.path.join(install_dir, f"{BINARY_NAME}{binary_ext}")

        # 如果目标已存在且被占用 (Windows)，先尝试删除
        if os.path.exists(dest):
            try:
                os.remove(dest)
            except OSError:
                old = dest + ".old"
                if os.path.exists(old):
                    os.remove(old)
                os.rename(dest, old)

        shutil.move(tmp_path, dest)
        tmp_path = None  # 已移走，不需要清理

        # 设置可执行权限 (Unix)
        if os_name != "windows":
            st = os.stat(dest)
            os.chmod(dest, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        # macOS: 移除 quarantine 属性
        if os_name == "darwin" and shutil.which("xattr"):
            os.system(f'xattr -d com.apple.quarantine "{dest}" 2>/dev/null')

        success(f"已安装到: {dest}")

    finally:
        # 清理临时文件
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

    # PATH 处理
    ensure_in_path(install_dir, os_name)

    # 完成提示
    print()
    success(f"iWiki CLI {version} 安装成功！")
    print()
    print(f"  登录:  {BINARY_NAME} auth login")
    print(f"  帮助:  {BINARY_NAME} --help")
    print()


if __name__ == "__main__":
    main()
