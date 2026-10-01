#!/usr/bin/env python3
"""Agent 侧 App 结果协议适配器。

用法：
    python3 _run.py show_app '<json>'
    python3 _run.py show_app --input-file /tmp/diet-assistant/request.json

成功时 stdout 恰好两行，分工不同：
    第 1 行  从 handler 输出里摘出的 `_model` 段——精简回执，给模型看
    第 2 行  __ONEAGENT_APP_RESULT__ + 资源声明 + 一份完整 render_payload

宿主中间件把第 2 行转成一个 app.data 包，resource 与 structuredContent 同包下发。
resource 只是个 uri，前端拿它去模版平台取页面；XCard 摘要和 HTML 详情消费的是同一份
structuredContent。dataMode=keep_latest 告诉宿主只留最新一份——每次调用给的都是完整
快照，按默认的追加处理会让连续几餐攒成多份。

整份 payload 有好几 KB，不能也走给模型：卡片要的是全量数据，模型要的只是
「记进哪一餐、合计多少、核验过没过」。

失败时只输出一行错误回执，不输出 sentinel，避免宿主下发不完整数据。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from payload_schema import PayloadValidationError, validate_payload

MARKER = "__ONEAGENT_APP_RESULT__"
MODEL_VIEW_KEY = "_model"
TOOL = "show_app"
URI = "chat.chat_output.xcard_diet_res"
APP = {"id": "diet-assistant", "name": "饮食助手", "version": "v2.0"}
HANDLER = Path(__file__).with_name("diet_api.py")


def read_arguments(argv: list[str]) -> dict:
    if len(argv) > 3 and argv[2] == "--input-file":
        raw = Path(argv[3]).read_text(encoding="utf-8")
    else:
        raw = argv[2] if len(argv) > 2 else "{}"
    args = json.loads(raw)
    if not isinstance(args, dict):
        raise ValueError("参数必须是 JSON 对象")
    return args


def fail(code: str, message: str) -> int:
    print(json.dumps({"phase": "error", "code": code, "message": message}, ensure_ascii=False))
    return 2


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    if name != TOOL:
        return fail("unknown_tool", f"不支持的工具：{name}，本包只有 {TOOL}。")

    try:
        args = read_arguments(sys.argv)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return fail("invalid_argument", str(exc))

    completed = subprocess.run(
        [sys.executable, str(HANDLER), json.dumps(args, ensure_ascii=False, separators=(",", ":"))],
        capture_output=True, text=True, check=False,
    )
    if completed.stderr:
        sys.stderr.write(completed.stderr)

    output = completed.stdout.strip()
    try:
        app_view = json.loads(output)
    except json.JSONDecodeError:
        # handler 没能输出合法 JSON：原样透出去，别再补 sentinel 让宿主渲染半截数据
        print(output or "{}")
        return completed.returncode or 1

    model_view = app_view.pop(MODEL_VIEW_KEY, None) or {}
    if completed.returncode != 0 or model_view.get("phase") == "error":
        print(json.dumps(model_view, ensure_ascii=False))
        return completed.returncode or 1

    # 摘掉 _model 之后空了：当天没餐的读操作 / 删光当日被 dispatch 压掉了卡片。
    # 不发 sentinel，宿主就不会去下发 resource 和 data。
    if not app_view:
        print(json.dumps(model_view, ensure_ascii=False))
        return completed.returncode

    try:
        validate_payload(app_view)
    except PayloadValidationError as exc:
        return fail("invalid_payload", str(exc))

    print(json.dumps(model_view, ensure_ascii=False))
    record = {
        "source": "skill",
        "app": APP,
        "toolName": TOOL,
        "arguments": args,
        "status": "success",
        "resourceUri": URI,
        "resource": {
            "uri": URI,
            "name": "今日饮食记录",
            "mimeType": "application/a2ui+json",
            # 每次调用产出的是一份完整快照，不是增量。不声明的话宿主按追加处理，
            # 连记两餐会攒下两份 payload。
            "dataMode": "keep_latest",
        },
        "structuredContent": app_view,
        "content": [],
    }

    print(MARKER + " " + json.dumps(record, ensure_ascii=False, separators=(",", ":")))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
