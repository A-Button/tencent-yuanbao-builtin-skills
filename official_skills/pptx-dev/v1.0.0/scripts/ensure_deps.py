#!/usr/bin/env python3
"""检测并兜底补装本技能的运行依赖（桌面端安全网）：Python 包 / Node 包 / 系统二进制。

一份脚本覆盖三类依赖，按需生效（缺哪份清单就跳过哪类）：
  - Python：读 `requirements.txt`，缺则 `pip` 补装到当前解释器环境。
  - Node：读 `package.json` 的 `dependencies`，缺则 `npm` 本地安装到 `<skill>/node_modules`。
  - 系统二进制：读 `system-requirements.txt`，缺只**告警**——脚本无法安装系统组件
    （如 LibreOffice / Poppler / Tesseract / graphviz），需桌面端预装环境提供。

行为约束（避免版本/全局污染）：
  - 只补“完全缺失”的 Python/Node 包；不升级、不降级已存在的包。
  - Node 走本地安装（`npm install`，非 `-g`），自包含到 `<skill>/node_modules`。
  - 不介入安装源配置：沿用环境的 pip / npm 配置；镜像源由预装环境负责。
  - 二进制只探测（`shutil.which`），从不尝试安装。

每次调用都实时探测（Python 用 importlib.metadata 查分发名、Node 查本地 node_modules、
二进制用 which），不写缓存标记——探测开销极小，且始终反映真实环境状态。

用法：
  python scripts/ensure_deps.py            # 检测 + 按需补装 py/node；探测二进制并告警（默认）
  python scripts/ensure_deps.py --check    # 只检测不安装，列出全部缺失（退出码取决于可安装的 py/node）
  python scripts/ensure_deps.py -q         # 安静模式（告警与错误仍输出）

Node 依赖就绪后，运行 Node 脚本时用本地依赖：
  NODE_PATH=<skill>/node_modules node your_gen.js
"""

from __future__ import annotations

import argparse
import importlib.metadata as md
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SKILL_NAME = SKILL_DIR.name
REQUIREMENTS = SKILL_DIR / "requirements.txt"
NODE_MANIFEST = SKILL_DIR / "package.json"
NODE_MODULES = SKILL_DIR / "node_modules"
SYSTEM_MANIFEST = SKILL_DIR / "system-requirements.txt"

_NAME_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


# --- Python 依赖 --------------------------------------------------------

def parse_requirements(text: str) -> list[tuple[str, str]]:
    """把 requirements.txt 解析为 (dist_name, full_spec) 列表。

    - 忽略空行与整行注释；剥离行内 `#` 注释。
    - dist_name 是分发名（如 Pillow / fonttools），用于安装状态探测。
    - full_spec 是含版本约束的完整片段（如 ``Pillow>=10``），用于 pip 安装。
    """
    reqs: list[tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = _NAME_RE.match(line)
        if not m:
            continue
        reqs.append((m.group(1), line))
    return reqs


def is_installed(dist_name: str) -> bool:
    """依据分发名判断包是否已安装（不实际 import，无副作用、更快）。"""
    try:
        md.version(dist_name)
        return True
    except md.PackageNotFoundError:
        return False


def find_missing(reqs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """返回“完全缺失”的 Python 依赖（已装的原样保留，不管版本）。"""
    return [(name, spec) for name, spec in reqs if not is_installed(name)]


def install(missing: list[tuple[str, str]]) -> subprocess.CompletedProcess:
    """对缺失的 Python 包执行 pip install（读 skill 根目录 requirements.txt）。

    不指定安装源：沿用当前环境的 pip 配置（镜像源由桌面端预装环境的
    pip.conf / 环境变量负责，本脚本不介入源配置）。
    """
    cmd = [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)]
    return subprocess.run(cmd, capture_output=True, text=True)


# --- Node 依赖 ----------------------------------------------------------

def read_node_deps() -> dict[str, str]:
    """读 package.json 的 dependencies（无则返回空 dict）。"""
    if not NODE_MANIFEST.exists():
        return {}
    try:
        pkg = json.loads(NODE_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    deps = pkg.get("dependencies") or {}
    return deps if isinstance(deps, dict) else {}


def is_node_installed(name: str) -> bool:
    """本地 node_modules 是否已装该包（存在其 package.json 即认为可用）。"""
    return (NODE_MODULES / name / "package.json").exists()


def find_missing_node(deps: dict[str, str]) -> list[str]:
    """返回本地 node_modules 里“完全缺失”的 Node 依赖名。"""
    return [name for name in deps if not is_node_installed(name)]


def install_node() -> subprocess.CompletedProcess:
    """本地安装 Node 依赖到 <skill>/node_modules（非全局）。

    沿用环境的 npm 配置，不介入源；镜像源由预装环境负责。
    """
    cmd = ["npm", "install", "--no-audit", "--no-fund", "--prefix", str(SKILL_DIR)]
    return subprocess.run(cmd, cwd=str(SKILL_DIR), capture_output=True, text=True)


# --- 系统二进制 ---------------------------------------------------------

def parse_system_requirements(text: str) -> list[tuple[list[str], str]]:
    """解析 system-requirements.txt。

    每行格式：``cand1[|cand2...]   # 说明``。
    - `|` 分隔可接受的多个可执行名（任一存在即视为满足，如 ``soffice|libreoffice``）。
    - `#` 后为人类可读说明（提示它属于哪个功能/组件）。
    返回 [(candidates, hint), ...]。
    """
    specs: list[tuple[list[str], str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        exe_part, _, hint = line.partition("#")
        cands = [c.strip() for c in exe_part.split("|") if c.strip()]
        if cands:
            specs.append((cands, hint.strip()))
    return specs


def find_missing_bins(specs: list[tuple[list[str], str]]) -> list[tuple[list[str], str]]:
    """返回 PATH 上找不到任一候选可执行文件的系统依赖。"""
    return [(cands, hint) for cands, hint in specs if not any(shutil.which(c) for c in cands)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="检测并兜底补装本技能的运行依赖（py/node/系统二进制）。")
    ap.add_argument("--check", action="store_true", help="只检测缺失，不安装。")
    ap.add_argument("-q", "--quiet", action="store_true", help="安静模式。")
    args = ap.parse_args(argv)

    def say(msg: str) -> None:
        if not args.quiet:
            print(msg)

    py_text = _read(REQUIREMENTS)
    py_reqs = parse_requirements(py_text)
    node_deps = read_node_deps()
    sys_text = _read(SYSTEM_MANIFEST)
    sys_specs = parse_system_requirements(sys_text)

    if not py_reqs and not node_deps and not sys_specs:
        say(f"[ensure_deps] {SKILL_NAME} 无依赖清单，跳过。")
        return 0

    # 系统二进制：始终探测、只告警（不影响退出码，不尝试安装）。
    missing_bins = find_missing_bins(sys_specs)

    def warn_bins() -> None:
        if not missing_bins:
            return
        lines = "\n".join(
            f"    - {'/'.join(cands)}{'：' + hint if hint else ''}"
            for cands, hint in missing_bins
        )
        print(
            "[ensure_deps] 缺少系统二进制（需桌面端预装环境提供，脚本不自动安装）：\n"
            f"{lines}",
            file=sys.stderr,
        )

    missing_py = find_missing(py_reqs)
    missing_node = find_missing_node(node_deps)

    if args.check:
        if missing_py:
            names = ", ".join(n for n, _ in missing_py)
            print(f"[ensure_deps] 缺失 Python 包 {len(missing_py)} 个：{names}", file=sys.stderr)
        if missing_node:
            print(f"[ensure_deps] 缺失 Node 包 {len(missing_node)} 个：{', '.join(missing_node)}", file=sys.stderr)
        warn_bins()
        return 1 if (missing_py or missing_node) else 0

    ok = True

    if missing_py:
        names = ", ".join(n for n, _ in missing_py)
        print(f"[ensure_deps] 补装缺失 Python 依赖 {names}…", file=sys.stderr)
        proc = install(missing_py)
        if proc.returncode != 0 or find_missing(py_reqs):
            print(
                "[ensure_deps] Python 依赖安装失败。\n"
                f"  缺失: {names}\n"
                f"  可手动执行: {sys.executable} -m pip install -r {REQUIREMENTS}\n"
                f"  （安装源由环境 pip 配置决定；如失败请检查预装环境的镜像/网络）\n"
                f"  pip 输出:\n{proc.stderr or proc.stdout}",
                file=sys.stderr,
            )
            ok = False

    if missing_node and ok:
        if shutil.which("npm") is None:
            print(
                "[ensure_deps] 需要 npm 安装 Node 依赖，但 PATH 上未找到 npm。\n"
                f"  缺失: {', '.join(missing_node)}\n"
                "  （Node 运行时/npm 由桌面端预装环境提供）",
                file=sys.stderr,
            )
            ok = False
        else:
            print(f"[ensure_deps] 本地补装缺失 Node 依赖 {', '.join(missing_node)}…", file=sys.stderr)
            proc = install_node()
            still = find_missing_node(node_deps)
            if proc.returncode != 0 or still:
                print(
                    "[ensure_deps] Node 依赖安装失败。\n"
                    f"  缺失: {', '.join(still or missing_node)}\n"
                    f"  可手动执行: (cd {SKILL_DIR} && npm install)\n"
                    f"  （安装源由环境 npm 配置决定；如失败请检查预装环境的镜像/网络）\n"
                    f"  npm 输出:\n{proc.stderr or proc.stdout}",
                    file=sys.stderr,
                )
                ok = False

    if ok:
        say(f"[ensure_deps] {SKILL_NAME} 依赖就绪。")
    warn_bins()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
