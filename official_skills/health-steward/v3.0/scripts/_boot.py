"""把饮食、训练、日报、Now 四个目录加进导入路径。

入口脚本在 import 业务模块之前调用。模型仍然只跑 scripts/_run.py。
"""

from __future__ import annotations

import sys
from pathlib import Path

MODULES = ("diet", "training", "report", "now")


def scripts_dir() -> Path:
    return Path(__file__).resolve().parent


def install() -> Path:
    scripts = scripts_dir()
    ordered = [scripts, *[scripts / name for name in MODULES]]
    for path in reversed(ordered):
        text = str(path)
        while text in sys.path:
            sys.path.remove(text)
        sys.path.insert(0, text)
    return scripts


def script(name: str) -> Path:
    """按文件名找到分目录之后的工具脚本。name 不带 .py。"""
    scripts = scripts_dir()
    for folder in MODULES:
        path = scripts / folder / f"{name}.py"
        if path.is_file():
            return path
    return scripts / f"{name}.py"
