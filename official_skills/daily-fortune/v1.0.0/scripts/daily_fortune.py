#!/usr/bin/env python3
"""每日运势 App Skill 的领域入口：纯 JSON 进，一行 JSON 出。

本文件只做三件事：定位 Node 运行时、把入参透传给确定性引擎、把引擎结果原样打一行。
卡片渲染全部由 assets/ui/index.html 在 iframe 内完成，这里不再产出任何 HTML。

stdout 必须恰好一行 JSON：沙箱 CLI 直接 json.loads(整段 stdout)，多打一行就会解析失败，
UI 也拿不到数据。marker 行由 CLI 自己追加，脚本不要拼。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "scripts" / "engine.mjs"

NODE_CANDIDATES = [
    os.environ.get("DAILY_FORTUNE_NODE_PATH", "").strip(),
    str(Path.home() / "Applications" / "元宝牛仔版 0.3.20.app" / "Contents" / "MacOS" / "元宝牛仔版"),
    str(Path.home() / "Applications" / "元宝牛仔版.app" / "Contents" / "MacOS" / "元宝牛仔版"),
    "/usr/bin/node",
    "/usr/local/bin/node",
    "/opt/homebrew/bin/node",
    str(Path.home() / ".workbuddy" / "binaries" / "node" / "versions" / "20.18.0" / "bin" / "node"),
    str(Path.home() / ".workbuddy" / "binaries" / "node" / "versions" / "22.22.2" / "bin" / "node"),
]


def find_node() -> str:
    for candidate in NODE_CANDIDATES:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise RuntimeError("未找到可用的 Node 运行时；可设置 DAILY_FORTUNE_NODE_PATH 指定绝对路径")


def parse_request() -> dict:
    """CLI 把入参放在 argv[1]；其余位置只是容错，正常路径不会走到。"""
    raw = sys.argv[1] if len(sys.argv) > 1 else ""
    if not raw.strip():
        raw = os.environ.get("ONEAGENT_APP_ARGUMENTS", "")
    if not raw.strip():
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("参数必须是 JSON 对象")
    return value


def error(code: str, message: str) -> dict:
    return {"phase": "error", "code": code, "message": message, "retryable": False}


def main() -> dict:
    try:
        request = parse_request()
    except Exception as exc:  # noqa: BLE001
        return error("INVALID_JSON", "参数必须是合法 JSON 对象：%s" % exc)

    try:
        node = find_node()
    except RuntimeError as exc:
        return error("RUNTIME_UNAVAILABLE", str(exc))

    env = dict(os.environ)
    if "元宝牛仔版" in node:
        env["ELECTRON_RUN_AS_NODE"] = "1"

    try:
        completed = subprocess.run(
            [node, str(ENGINE), json.dumps(request, ensure_ascii=False, separators=(",", ":"))],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return error("RUNTIME_UNAVAILABLE", "计算引擎超时")

    if completed.returncode != 0:
        return error("ENGINE_FAILED", (completed.stderr or "计算引擎执行失败").strip()[:500])

    for line in completed.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except ValueError:
            continue
    return error("INVALID_ENGINE_OUTPUT", "计算引擎返回了无效结果")


if __name__ == "__main__":
    sys.stdout.write(json.dumps(main(), ensure_ascii=False, separators=(",", ":")))
