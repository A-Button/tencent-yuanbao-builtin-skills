#!/usr/bin/env python3
"""Agent-side App Skill 包装器（临时：stdout sentinel 旁路，后续换成 sandbox CLI）。

用法：
    python3 /data/skills/my-coffee/scripts/_run.py coffee_api '<json>'
    python3 /data/skills/my-coffee/scripts/_run.py describe

职责：
  1. 读 assets/app.yaml（兼容根目录 app.yaml），按 tools[]（或旧 scripts[]）路由；
  2. 执行 handler 脚本，stdout 回灌模型；
  3. 追加一行 __ONEAGENT_APP_RESULT__ JSON，含 app / toolName / arguments /
     resourceUri / resource / structuredContent，供 agent 拆成 app.resource + app.data。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from cli_contract import ContractError, describe_contract, validate_operation

APP_RESULT_MARKER = "__ONEAGENT_APP_RESULT__"
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent


class CallValidationError(ValueError):
    pass


def find_app_yaml(root: Path) -> Path | None:
    for cand in (root / "assets" / "app.yaml", root / "app.yaml"):
        if cand.is_file():
            return cand
    return None


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError:
        yaml = None
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        data = yaml.safe_load(text) or {}
        if not isinstance(data, dict):
            raise CallValidationError("app.yaml 根节点必须是对象")
        return data
    # 无 PyYAML 时：仅支持本包固定结构的极简解析不够稳，直接失败提示。
    raise CallValidationError("sandbox 缺少 PyYAML，无法解析 app.yaml")


def resolve_tool(manifest: dict[str, Any], name: str) -> dict[str, Any] | None:
    """从 tools[]（新）或 scripts[]（旧）解析工具执行绑定与 UI 绑定。"""
    for tool in manifest.get("tools") or []:
        if not isinstance(tool, dict) or tool.get("name") != name:
            continue
        handler = tool.get("handler") or {}
        path = ""
        if isinstance(handler, dict):
            path = str(handler.get("path") or "")
        if not path:
            path = str(tool.get("path") or "")
        meta = tool.get("_meta") or {}
        ui = meta.get("ui") if isinstance(meta, dict) else {}
        if not isinstance(ui, dict):
            ui = {}
        resource_uri = str(tool.get("resourceUri") or ui.get("resourceUri") or "")
        visibility = tool.get("visibility") or ui.get("visibility") or []
        return {
            "name": name,
            "path": path,
            "resourceUri": resource_uri,
            "visibility": visibility,
        }

    for script in manifest.get("scripts") or []:
        if not isinstance(script, dict) or script.get("name") != name:
            continue
        return {
            "name": name,
            "path": str(script.get("path") or ""),
            "resourceUri": str(script.get("resourceUri") or ""),
            "visibility": script.get("visibility") or [],
        }
    return None


def resolve_resource(manifest: dict[str, Any], uri: str) -> dict[str, Any] | None:
    if not uri:
        return None
    resources = manifest.get("resources")
    if isinstance(resources, list):
        for item in resources:
            if isinstance(item, dict) and item.get("uri") == uri:
                out: dict[str, Any] = {"uri": uri}
                for key in ("name", "mimeType", "description"):
                    if item.get(key):
                        out[key] = item[key]
                if isinstance(item.get("_meta"), dict):
                    out["_meta"] = item["_meta"]
                return out
    return {"uri": uri}


def validate_call(name: str, args_json: str, *, manifest: dict[str, Any] | None = None) -> dict:
    """校验工具名 + 参数；coffee_api 仍走 cli_contract 的 Agent 白名单。"""
    if manifest is None:
        yaml_path = find_app_yaml(SKILL_ROOT)
        if not yaml_path:
            raise CallValidationError("app.yaml not found")
        manifest = load_manifest(yaml_path)
    tool = resolve_tool(manifest, name)
    if tool is None or not tool.get("path"):
        raise CallValidationError(f"不支持的脚本：{name}")
    try:
        args = json.loads(args_json)
    except json.JSONDecodeError as exc:
        raise CallValidationError("参数必须是合法 JSON") from exc
    if not isinstance(args, dict):
        raise CallValidationError("参数必须是对象")
    if name == "coffee_api":
        operation = args.get("operation", "")
        operation_args = {key: value for key, value in args.items() if key != "operation"}
        try:
            validate_operation(operation, operation_args, agent_call=True)
        except ContractError as exc:
            raise CallValidationError(str(exc)) from exc
    return args


def build_result_record(
    *,
    manifest: dict[str, Any],
    tool_name: str,
    arguments: dict[str, Any],
    structured: Any,
    resource_uri: str,
) -> dict[str, Any]:
    app_id = str(manifest.get("id") or SKILL_ROOT.name)
    status = "error"
    if isinstance(structured, dict) and structured.get("phase") != "error":
        status = "success"
    record: dict[str, Any] = {
        "source": "skill",
        "app": {
            "id": app_id,
            "name": str(manifest.get("name") or app_id),
            "version": str(manifest.get("version") or ""),
        },
        "toolName": tool_name,
        "arguments": arguments,
        "status": status,
        "structuredContent": structured if isinstance(structured, dict) else {"raw": structured},
        "content": [],
    }
    desc = manifest.get("description")
    if desc:
        record["app"]["description"] = desc
    if resource_uri:
        record["resourceUri"] = resource_uri
        resource = resolve_resource(manifest, resource_uri)
        if resource:
            record["resource"] = resource
    return record


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    if name == "describe":
        print(json.dumps(describe_contract(), ensure_ascii=False, separators=(",", ":")))
        return 0

    yaml_path = find_app_yaml(SKILL_ROOT)
    if not yaml_path:
        print(json.dumps({"phase": "error", "code": "NO_APP_YAML", "message": "app.yaml not found"},
                         ensure_ascii=False))
        return 2

    try:
        manifest = load_manifest(yaml_path)
    except CallValidationError as exc:
        print(json.dumps({"phase": "error", "code": "BAD_APP_YAML", "message": str(exc)},
                         ensure_ascii=False))
        return 2

    args_json = sys.argv[2] if len(sys.argv) > 2 else "{}"
    try:
        args = validate_call(name, args_json, manifest=manifest)
    except CallValidationError as exc:
        print(json.dumps({"phase": "error", "code": "INVALID_AGENT_CALL", "message": str(exc)},
                         ensure_ascii=False))
        return 2

    tool = resolve_tool(manifest, name)
    assert tool is not None
    script = (SKILL_ROOT / tool["path"]).resolve()
    if not script.is_file():
        print(json.dumps({"phase": "error", "code": "SCRIPT_MISSING",
                          "message": f"脚本不存在：{tool['path']}"}, ensure_ascii=False))
        return 2

    completed = subprocess.run(
        [sys.executable, str(script), args_json],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(SKILL_ROOT),
        env=os.environ.copy(),
    )
    if completed.stderr:
        sys.stderr.write(completed.stderr)
    output = completed.stdout.strip()
    print(output)
    try:
        structured = json.loads(output)
    except json.JSONDecodeError:
        return completed.returncode or 1

    record = build_result_record(
        manifest=manifest,
        tool_name=name,
        arguments=args,
        structured=structured,
        resource_uri=str(tool.get("resourceUri") or ""),
    )
    print(APP_RESULT_MARKER + " " + json.dumps(record, ensure_ascii=False, separators=(",", ":")))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
