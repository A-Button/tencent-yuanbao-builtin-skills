#!/usr/bin/env python3
"""Agent 侧 App 结果协议适配器（牛仔宿主用）。

用法：
    python3 /data/skills/stock-watch/scripts/_run.py <tool> '<json>'

成功时 stdout 恰好两行：
    第 1 行  handler 的业务 JSON，回给模型
    第 2 行  __ONEAGENT_APP_RESULT__ + resource + structuredContent

标准宿主有 `app <skill> <tool>` 这条 CLI 会自己补第 2 行；牛仔宿主里没有 `app`，
所以由本文件补。**resource.uri 必须写进信封**：app_result_emit 对没有 resource.uri
的 app.data 一律丢弃（日志 `drop app.data without resource uri`），上游不会按
app.yaml 帮你补。trace 91934b0a 就是这样：工具跑成功了，卡没出来。

信封字段与 release/0923 的标准 App CLI 对齐：必须回显 ``arguments``，``resource``
使用 manifest 中对应资源的真实 name / mimeType / dataMode；服务端再把业务字段提升到
顶层，其余字段放进 ``_metadata``。

命令必须单独一行，禁止 `| head`、`| python`、`>/dev/null`。管走第 2 行，
中间件就收不到信封。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
APP_RESULT_MARKER = "__ONEAGENT_APP_RESULT__"
MIME = "application/a2ui+json"


def _fail(code: str, message: str) -> int:
    print(json.dumps({"phase": "error", "code": code, "message": message}, ensure_ascii=False))
    return 2


def _manifest_path() -> str | None:
    for candidate in (
        os.path.join(SKILL_ROOT, "assets", "app.yaml"),
        os.path.join(SKILL_ROOT, "app.yaml"),
    ):
        if os.path.exists(candidate):
            return candidate
    return None


def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    try:
        import yaml
    except ImportError:
        return _mini_yaml(text)
    return yaml.safe_load(text) or {}


def _mini_yaml(text: str) -> dict:
    """沙箱里没有 PyYAML 时的兜底：只取出卡信封需要的 manifest 字段。

    只认本包 app.yaml 的固定缩进，不实现通用 YAML；这仍比复制一份静态路由表可靠。
    """
    manifest: dict = {"resources": [], "tools": []}
    section = ""
    current_resource: dict | None = None
    current_tool: dict | None = None
    in_handler = False

    def scalar(value: str) -> str:
        return value.strip().strip("\"'")

    tools: list[dict] = []
    for raw in text.splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        line = raw.strip()
        if indent == 0:
            current_resource = None
            current_tool = None
            in_handler = False
            if line == "resources:":
                section = "resources"
            elif line == "tools:":
                section = "tools"
            elif ":" in line:
                key, _, value = line.partition(":")
                manifest[key.strip()] = scalar(value)
            continue

        if section == "resources":
            if indent == 2 and line.startswith("- "):
                current_resource = {}
                manifest["resources"].append(current_resource)
                line = line[2:].strip()
            if current_resource is not None and ":" in line:
                key, _, value = line.partition(":")
                key, value = key.strip(), scalar(value)
                if key in {"uri", "name", "description", "mimeType", "dataMode"}:
                    current_resource[key] = value
            continue

        if section != "tools":
            continue
        if indent == 2 and line.startswith("- "):
            current_tool = {}
            tools.append(current_tool)
            in_handler = False
            line = line[2:].strip()
        if current_tool is None or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), scalar(value)
        if indent == 2 and key == "name":
            current_tool["name"] = value
        elif indent == 4 and key == "handler":
            in_handler = True
        elif indent == 6 and key == "path" and in_handler:
            current_tool["path"] = value
            in_handler = False
        elif key == "resourceUri":
            current_tool["resourceUri"] = value
    manifest["tools"] = tools
    return manifest


def _app_info(manifest: dict) -> dict:
    app_id = str(manifest.get("id") or os.path.basename(SKILL_ROOT))
    app = {
        "id": app_id,
        "name": str(manifest.get("name") or app_id),
        "version": str(manifest.get("version") or ""),
    }
    if manifest.get("description"):
        app["description"] = str(manifest["description"])
    return app


def _resource(manifest: dict, uri: str, app: dict) -> dict:
    """按 URI 回显标准 App CLI 的 resource 元信息，不把沙箱 path 泄露给宿主。"""
    for item in manifest.get("resources") or []:
        if item.get("uri") != uri:
            continue
        resource = {
            key: item[key]
            for key in ("uri", "name", "description", "mimeType", "dataMode", "_meta")
            if item.get(key) not in (None, "")
        }
        return resource
    return {"uri": uri, "name": app["name"], "mimeType": MIME}


def _route(manifest: dict, tool: str) -> tuple[str, str]:
    """返回 (handler 相对路径, resourceUri)。

    三张卡（单标的 / 建议列表 / 资讯列表）是三份 A2UI 资源，所以 URI **必须按
    tool 查**，不能写死一个。写死的后果是宿主拿着 main 的组件树去渲染资讯出参，
    绑定全落空，卡面一片空白——而且不报错。
    """
    for entry in manifest.get("tools") or []:
        if entry.get("name") != tool:
            continue
        handler = entry.get("handler")
        path = handler.get("path") if isinstance(handler, dict) else entry.get("path")
        meta = entry.get("_meta")
        if isinstance(meta, dict):
            uri = ((meta.get("ui") or {}) if isinstance(meta.get("ui"), dict) else {}).get(
                "resourceUri", ""
            )
        else:
            uri = entry.get("resourceUri", "")
        return str(path or ""), str(uri or "")
    return "", ""


def main() -> int:
    if len(sys.argv) < 2:
        return _fail("USAGE", "usage: _run.py <tool> '<json>'")
    tool = sys.argv[1]
    arguments = sys.argv[2] if len(sys.argv) > 2 else "{}"

    manifest_path = _manifest_path()
    if not manifest_path:
        return _fail("NO_MANIFEST", f"app.yaml not found under {SKILL_ROOT}")
    manifest = _load(manifest_path)
    relative, uri = _route(manifest, tool)
    if not relative:
        return _fail("UNKNOWN_TOOL", f"tool not declared in app.yaml: {tool}")
    if not uri:
        return _fail("NO_RESOURCE_URI", f"tool has no _meta.ui.resourceUri: {tool}")

    completed = subprocess.run(
        [sys.executable, os.path.join(SKILL_ROOT, relative), arguments],
        capture_output=True,
        text=True,
    )
    if completed.stderr:
        sys.stderr.write(completed.stderr)

    try:
        structured = json.loads((completed.stdout or "").strip())
    except ValueError:
        sys.stdout.write(completed.stdout or "{}\n")
        return completed.returncode or 1

    print(json.dumps(structured, ensure_ascii=False, separators=(",", ":")))
    # 错误信封不带 sentinel，否则宿主会照着它画一张坏卡。
    if isinstance(structured, dict) and structured.get("phase") == "error":
        return completed.returncode or 1

    try:
        parsed_arguments = json.loads(arguments)
    except ValueError:
        parsed_arguments = {}
    if not isinstance(parsed_arguments, dict):
        parsed_arguments = {}
    app = _app_info(manifest)
    record = {
        "source": "skill",
        "app": app,
        "toolName": tool,
        "arguments": parsed_arguments,
        "status": "success",
        "resourceUri": uri,
        "resource": _resource(manifest, uri, app),
        "structuredContent": structured,
        "content": [],
    }
    print(APP_RESULT_MARKER + " " + json.dumps(record, ensure_ascii=False, separators=(",", ":")))
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
