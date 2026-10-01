#!/usr/bin/env python3
"""沙箱入口：build_card '<json>' 或 build_card --input /path/to.json。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

APP_RESULT_MARKER = "__ONEAGENT_APP_RESULT__"
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
APP_ID = "service-entry-finder"
RESOURCE_URI = "ai_apps.skills.service_entry_entry_res"
TOOLS = {
    "build_card": {
        "path": "scripts/build_card.py",
        "resourceUri": RESOURCE_URI,
    }
}


def _load_json(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("参数必须是合法 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("参数必须是对象")
    return value


def _parse_build_card_argv(extra: list[str]) -> tuple[dict[str, Any], str]:
    if len(extra) >= 2 and extra[0] == "--input":
        path = Path(extra[1]).expanduser()
        if not path.is_file():
            raise ValueError(f"文件不存在：{path}")
        payload = path.read_text(encoding="utf-8").strip()
        return _load_json(payload), payload
    raw = extra[0] if extra else "{}"
    return _load_json(raw), raw


def _model_line(structured: dict[str, Any]) -> str:
    if structured.get("ok"):
        return json.dumps(
            {
                "ok": True,
                "result": "card_emitted",
                "name": structured.get("name", ""),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    return json.dumps(structured, ensure_ascii=False, separators=(",", ":"))


def _resource() -> dict[str, str]:
    card_path = SKILL_ROOT / "assets" / "ui" / "card.json"
    out = {
        "uri": RESOURCE_URI,
        "name": "小程序入口卡",
        "mimeType": "application/a2ui+json",
        "description": "单卡展示首选小程序入口。",
    }
    if card_path.is_file():
        out["content"] = card_path.read_text(encoding="utf-8")
    return out


def _record(
    tool_name: str,
    arguments: dict[str, Any],
    structured: dict[str, Any],
) -> dict[str, Any]:
    ok = bool(structured.get("ok"))
    if ok:
        structured = dict(structured)
        basic = arguments.get("basic_info")
        if isinstance(basic, dict) and "basic_info" not in structured:
            structured["basic_info"] = basic
    record: dict[str, Any] = {
        "source": "skill",
        "app": {
            "id": APP_ID,
            "name": "小程序入口",
            "version": "v1.0.0",
            "description": "经核对的小程序首页入口。",
        },
        "toolName": tool_name,
        "arguments": arguments,
        "status": "success" if ok else "error",
        "structuredContent": structured,
        "content": [],
    }
    if ok:
        record["resourceUri"] = RESOURCE_URI
        record["resource"] = _resource()
    return record


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    tool = TOOLS.get(name)
    if tool is None:
        print(
            json.dumps(
                {"ok": False, "error": "unknown_tool", "message": f"不支持的脚本：{name}"},
                ensure_ascii=False,
            )
        )
        return 2

    try:
        arguments, payload_json = _parse_build_card_argv(sys.argv[2:])
    except ValueError as exc:
        print(
            json.dumps(
                {"ok": False, "error": "bad_json", "message": str(exc)},
                ensure_ascii=False,
            )
        )
        return 2

    script = (SKILL_ROOT / tool["path"]).resolve()
    completed = subprocess.run(
        [sys.executable, str(script), payload_json],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(SKILL_ROOT),
        env=os.environ.copy(),
    )
    if completed.stderr:
        sys.stderr.write(completed.stderr)
    output = completed.stdout.strip()
    try:
        structured = json.loads(output)
    except json.JSONDecodeError:
        if output:
            print(output)
        return completed.returncode or 1
    if not isinstance(structured, dict):
        print(output)
        return completed.returncode or 1

    print(_model_line(structured))
    print(
        APP_RESULT_MARKER
        + " "
        + json.dumps(
            _record(name, arguments, structured),
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0 if structured.get("ok") else (completed.returncode or 2)


if __name__ == "__main__":
    raise SystemExit(main())
