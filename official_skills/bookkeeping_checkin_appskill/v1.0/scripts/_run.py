#!/usr/bin/env python3
"""Agent 侧 App Skill 包装器（stdout sentinel 旁路）。

用法：
    python3 /data/skills/bookkeeping_checkin_appskill/scripts/_run.py ledger_api '<json>'
    python3 /data/skills/bookkeeping_checkin_appskill/scripts/_run.py describe

职责：
  1. 读 assets/app.yaml（无 PyYAML 时用内置极简解析），按 tools[] 路由；
  2. 校验 Agent 调用（禁止调用 visibility 仅 app 的 operation）；
  3. 执行 handler 脚本，stdout 回灌模型；
  4. 追加一行 __ONEAGENT_APP_RESULT__ JSON，含 app / toolName / arguments /
     resourceUri / resource / structuredContent，供后端拆成 app.resource + app.data。
     记账卡片流是唯一链路：draft_txn 新建卡片，挂 ui://bookkeeping_checkin_appskill/card
     并把骨架 A2UI DSL 内联进 resource._meta.ui.dsl；commit_txn / cancel_txn 是状态变更，
     不挂任何资源，只回 app.data，靠 structuredContent.card_id + update_seq_id 定位到已有那张卡。
     新建卡不带 update_seq_id。
     数据在 structuredContent.card_data 里下发，客户端按骨架声明的 surfaceId / path 自行灌入。
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

# 记账卡片资源。pending 新建卡才挂（含确认失败后重出的那张）。
# commit / cancel 是终态写入，绝不挂卡片资源：骨架 DSL 只需下发一次，重复挂会让客户端
# 又建一块空 surface（表现为"等待数据…"残卡）。它们只回 app.data，
# 靠 structuredContent 里的 card_id + update_seq_id 找到已有那张卡改状态。
CARD_RESOURCE_URI = "ui://bookkeeping_checkin_appskill/card"
COMMIT_OPS = {"commit_txn"}
CARD_PHASE = "bookkeeping_card"

# ---------------------------------------------------------------------------
# A2UI DSL 模板
#
# 整套 DSL 只有一个变量：card_id，其余全是常量。所以模板放在这里由包装器统一拼——
# 服务端不认识记账业务，也不该替 skill 生成 UI 元信息；模型更不该输出 DSL
# （它只调 ledger_api 传业务参数）。
#
# 骨架 DSL 字面量，一个字段都不改。surfaceId 固定，不跟 card_id。
# catalogId / component / path 与跑团同一套；两种卡靠 app.id、
# card_data.cardType 和这份固定 surfaceId 区分。
# ---------------------------------------------------------------------------
A2UI_DSL = (
    '[{"version":"v1.0","createSurface":{"surfaceId":"runGroupCheckIn_msg_book_2001",'
    '"catalogId":"https://yuanbao.tencent.com/specification/v1_0/catalogs/custom/catalog.json"}},'
    '{"version":"v1.0","updateComponents":{"surfaceId":"runGroupCheckIn_msg_book_2001",'
    '"components":[{"id":"root","component":"RunGroupCheckIn","value":{"path":"/runGroup"}}]}}]'
)


def build_card_dsl(_card_id: str = "") -> str:
    """骨架 DSL：建 surface + 挂组件树。字段原样下发，不随 card_id 改。"""
    return A2UI_DSL


class CallValidationError(ValueError):
    pass


def find_app_yaml(root: Path) -> Path | None:
    for cand in (root / "assets" / "app.yaml", root / "app.yaml"):
        if cand.is_file():
            return cand
    return None


def _yaml_scalar(v: str):
    """解析行内标量：数字/引号串/inline flow list [a, b]/空/纯文本。"""
    v = v.strip()
    if v == "" or v == "~" or v.lower() == "null":
        return None
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        if not inner:
            return []
        return [_yaml_scalar(x) for x in inner.split(",")]
    if v == "{}":
        return {}
    if v == "[]":
        return []
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    for cast in (int, float):
        try:
            return cast(v)
        except ValueError:
            pass
    return v


def _strip_comment(line: str) -> str:
    in_s = in_d = False
    for idx, ch in enumerate(line):
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d and (idx == 0 or line[idx - 1] == " "):
            return line[:idx]
    return line


def _minimal_yaml(text: str) -> dict[str, Any]:
    """极简 YAML 子集解析（无 PyYAML 时兜底）：支持映射、块序列(- )、行内 flow list、
    以及块标量(> / |)。足以解析本包 app.yaml 的完整结构。"""
    raw = text.split("\n")
    # 预处理：把块标量 (> 或 |) 的续行折叠成同一行的引号串，去掉整行/行尾注释与空行。
    tokens: list[tuple[int, str]] = []  # (indent, content)
    i = 0
    while i < len(raw):
        line = _strip_comment(raw[i].rstrip("\n")).rstrip()
        if line.strip() == "":
            i += 1
            continue
        indent = len(line) - len(line.lstrip(" "))
        content = line.strip()
        m_val = content.split(":", 1)[1].strip() if ":" in content else ""
        if m_val in (">", "|") and ":" in content:
            key = content.split(":", 1)[0]
            parts = []
            j = i + 1
            while j < len(raw):
                nxt = raw[j].rstrip()
                if nxt.strip() == "":
                    j += 1
                    continue
                nxt_indent = len(nxt) - len(nxt.lstrip(" "))
                if nxt_indent <= indent:
                    break
                parts.append(nxt.strip())
                j += 1
            folded = " ".join(parts).replace('"', "'")
            tokens.append((indent, f'{key}: "{folded}"'))
            i = j
            continue
        tokens.append((indent, content))
        i += 1

    pos = [0]

    def parse_block(min_indent: int):
        indent, content = tokens[pos[0]]
        if content.startswith("- "):
            return parse_sequence(indent)
        return parse_mapping(indent)

    def parse_mapping(cur_indent: int) -> dict[str, Any]:
        result: dict[str, Any] = {}
        while pos[0] < len(tokens):
            indent, content = tokens[pos[0]]
            if indent < cur_indent or content.startswith("- "):
                break
            if indent > cur_indent:
                break
            key, _, val = content.partition(":")
            key = key.strip()
            val = val.strip()
            pos[0] += 1
            if val == "":
                # 嵌套块：可能是 mapping 或 sequence
                if pos[0] < len(tokens):
                    nxt_indent, nxt_content = tokens[pos[0]]
                    if nxt_indent > cur_indent or (nxt_content.startswith("- ") and nxt_indent >= cur_indent):
                        result[key] = parse_block(cur_indent + 1)
                        continue
                result[key] = None
            else:
                result[key] = _yaml_scalar(val)
        return result

    def parse_sequence(cur_indent: int) -> list[Any]:
        result: list[Any] = []
        while pos[0] < len(tokens):
            indent, content = tokens[pos[0]]
            if indent != cur_indent or not content.startswith("- "):
                break
            body = content[2:].strip()
            pos[0] += 1
            if ":" in body and not (body.startswith("[") or body.startswith("{")):
                # 序列项是一个 mapping，第一对 kv 与 "- " 同行
                item: dict[str, Any] = {}
                key, _, val = body.partition(":")
                key = key.strip()
                val = val.strip()
                if val == "":
                    if pos[0] < len(tokens) and tokens[pos[0]][0] > cur_indent:
                        item[key] = parse_block(cur_indent + 2)
                    else:
                        item[key] = None
                else:
                    item[key] = _yaml_scalar(val)
                # 该 item 的后续同缩进 kv（缩进 = "- " 后内容的列位置）
                item_indent = cur_indent + 2
                while pos[0] < len(tokens):
                    nxt_indent, nxt_content = tokens[pos[0]]
                    if nxt_indent < item_indent or nxt_content.startswith("- ") and nxt_indent <= cur_indent:
                        break
                    if nxt_indent == item_indent and not nxt_content.startswith("- "):
                        merged = parse_mapping(item_indent)
                        item.update(merged)
                    else:
                        break
                result.append(item)
            else:
                result.append(_yaml_scalar(body))
        return result

    if not tokens:
        return {}
    return parse_block(0)


def load_manifest(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(text) or {}
        if not isinstance(data, dict):
            raise CallValidationError("app.yaml 根节点必须是对象")
        return data
    except ImportError:
        data = _minimal_yaml(text)
        if not isinstance(data, dict) or not data.get("id"):
            raise CallValidationError("内置 YAML 解析失败，请在环境中安装 PyYAML")
        return data


def resolve_tool(manifest: dict[str, Any], name: str) -> dict[str, Any] | None:
    for tool in manifest.get("tools") or []:
        if not isinstance(tool, dict) or tool.get("name") != name:
            continue
        handler = tool.get("handler") or {}
        path = str(handler.get("path") or "") if isinstance(handler, dict) else ""
        if not path:
            path = str(tool.get("path") or "")
        meta = tool.get("_meta") or {}
        ui = meta.get("ui") if isinstance(meta, dict) else {}
        if not isinstance(ui, dict):
            ui = {}
        return {
            "name": name,
            "path": path,
            "resourceUri": str(tool.get("resourceUri") or ui.get("resourceUri") or ""),
            "visibility": tool.get("visibility") or ui.get("visibility") or [],
        }
    return None


def resolve_resource(manifest: dict[str, Any], uri: str) -> dict[str, Any] | None:
    if not uri:
        return None
    for item in manifest.get("resources") or []:
        if isinstance(item, dict) and item.get("uri") == uri:
            out: dict[str, Any] = {"uri": uri}
            for key in ("name", "mimeType", "description"):
                if item.get(key):
                    out[key] = item[key]
            if isinstance(item.get("_meta"), dict):
                out["_meta"] = item["_meta"]
            return out
    return {"uri": uri}


def validate_call(name: str, args_json: str, *, manifest: dict[str, Any], agent_call: bool = True) -> dict:
    tool = resolve_tool(manifest, name)
    if tool is None or not tool.get("path"):
        raise CallValidationError(f"不支持的脚本：{name}")
    try:
        args = json.loads(args_json)
    except json.JSONDecodeError as exc:
        raise CallValidationError("参数必须是合法 JSON") from exc
    if not isinstance(args, dict):
        raise CallValidationError("参数必须是对象")
    if name == "ledger_api":
        operation = args.get("operation", "")
        operation_args = {k: v for k, v in args.items() if k != "operation"}
        try:
            validate_operation(operation, operation_args, agent_call=agent_call)
        except ContractError as exc:
            raise CallValidationError(str(exc)) from exc
    return args


# 上行给客户端的 structuredContent 只允许这几个字段：协议定义了什么就发什么。
# handler 返回值里那些 phase / operation / missing / min_ready / quote / image_url /
# group_id / receipt 是给模型看的，走 stdout 第一行那份原始结果进 ForModel，
# 不从这条通道漏给客户端——两边各取所需，客户端契约里不掺业务内部字段。
CARD_PROTOCOL_FIELDS = ("card_id", "user_id", "operate_type", "update_seq_id", "status",
                        "expire_at", "card_data")


def card_structured_content(structured: dict[str, Any]) -> dict[str, Any]:
    """把 handler 输出裁成协议字段。"""
    return {key: structured[key] for key in CARD_PROTOCOL_FIELDS if key in structured}


def is_card_result(structured: Any) -> bool:
    """只有真正出卡的结果才打 sentinel。find_txn / delete_txn 只回模型，不下发 app.data。"""
    if not isinstance(structured, dict):
        return False
    if structured.get("phase") != CARD_PHASE:
        return False
    if not structured.get("card_id"):
        return False
    return isinstance(structured.get("card_data"), dict)


def resource_uri_for(structured: Any) -> str:
    """只有 pending 新卡挂资源。确认失败重出的那张也是 pending。"""
    if not is_card_result(structured):
        return ""
    if structured.get("status") == "pending":
        return CARD_RESOURCE_URI
    return ""


def emit_card_records(*, manifest, tool_name, arguments, cards: list) -> None:
    for card in cards:
        if not is_card_result(card):
            continue
        record = build_result_record(
            manifest=manifest, tool_name=tool_name, arguments=arguments,
            structured=card, resource_uri=resource_uri_for(card))
        print(APP_RESULT_MARKER + " " + json.dumps(record, ensure_ascii=False, separators=(",", ":")))


def build_result_record(*, manifest, tool_name, arguments, structured, resource_uri) -> dict[str, Any]:
    app_id = str(manifest.get("id") or SKILL_ROOT.name)
    status = "success" if isinstance(structured, dict) and structured.get("phase") != "error" else "error"
    card_id = str(structured.get("card_id") or "") if isinstance(structured, dict) else ""
    # 只有卡片结果才裁剪。查询/删除/报错那些 phase 没有客户端契约可言，原样透传，
    # 免得把错误码和提示信息一起吃掉。
    if card_id and isinstance(structured, dict) and isinstance(structured.get("card_data"), dict):
        structured_out: Any = card_structured_content(structured)
    elif isinstance(structured, dict):
        structured_out = structured
    else:
        structured_out = {"raw": structured}
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
        "structuredContent": structured_out,
        "content": [],
    }
    if resource_uri:
        record["resourceUri"] = resource_uri
        resource = resolve_resource(manifest, resource_uri)
        if resource:
            # 骨架 DSL 内联进 _meta.ui.dsl，服务端原样透传。resource 只标卡片类型，
            # 同类型的多张实例靠 structuredContent.card_id 区分。
            if card_id:
                meta = dict(resource.get("_meta") or {})
                ui = dict(meta.get("ui") or {})
                ui["dsl"] = build_card_dsl(card_id)
                meta["ui"] = ui
                resource["_meta"] = meta
            record["resource"] = resource
    # 多卡并存：把 card_id 提到 record 顶层，供后端定位与日志排查。
    if card_id:
        record["card_id"] = card_id
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

    # ONEAGENT_APP_DIRECT=1 ⇒ 页面「跳过模型」直调（POST /app/call），放开 visibility 仅 app 的
    # operation；未置该标记时按 Agent 调用校验。
    direct = os.environ.get("ONEAGENT_APP_DIRECT") == "1"

    args_json = sys.argv[2] if len(sys.argv) > 2 else "{}"
    args = None
    try:
        args = validate_call(name, args_json, manifest=manifest, agent_call=not direct)
    except CallValidationError as exc:
        # commit 校验失败仍要进 handler：用户点确认失败会 cancel+create；
        # 超时 auto=true 失败只 cancel，不能在这里直接断掉。
        if name == "ledger_api":
            try:
                peeked = json.loads(args_json)
            except json.JSONDecodeError:
                peeked = None
            if isinstance(peeked, dict) and peeked.get("operation") in COMMIT_OPS:
                args = peeked
        if args is None:
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

    # skill 装在只读目录 /data/skills/{slug}/；若外部未指定 TRACKER_DATA_DIR，
    # 兜底到可写的 /data/user_persistent_data，避免 handler 在只读目录建库写文件失败。
    child_env = os.environ.copy()
    child_env.setdefault("TRACKER_DATA_DIR", "/data/user_persistent_data")
    completed = subprocess.run(
        [sys.executable, str(script), args_json],
        capture_output=True, text=True, check=False,
        cwd=str(SKILL_ROOT), env=child_env,
    )
    if completed.stderr:
        sys.stderr.write(completed.stderr)
    output = completed.stdout.strip()
    try:
        structured = json.loads(output)
    except json.JSONDecodeError:
        print(output)
        return completed.returncode or 1

    cards = structured.get("cards") if isinstance(structured, dict) else None
    if isinstance(cards, list) and cards:
        model_view = {key: structured[key] for key in structured if key != "cards"}
        print(json.dumps(model_view, ensure_ascii=False, separators=(",", ":")))
        emit_card_records(
            manifest=manifest, tool_name=name, arguments=args, cards=cards)
        return completed.returncode

    print(output)
    if name == "ledger_api" and not is_card_result(structured):
        return completed.returncode
    if name == "ledger_api":
        resource_uri = resource_uri_for(structured)
    else:
        resource_uri = str(tool.get("resourceUri") or "")
    record = build_result_record(
        manifest=manifest, tool_name=name, arguments=args,
        structured=structured, resource_uri=resource_uri)
    print(APP_RESULT_MARKER + " " + json.dumps(record, ensure_ascii=False, separators=(",", ":")))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
