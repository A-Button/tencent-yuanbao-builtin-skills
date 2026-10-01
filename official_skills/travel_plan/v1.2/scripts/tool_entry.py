#!/usr/bin/env python3
"""travel_plan 各业务脚本的共用入口。"""

from __future__ import annotations

import json
import sys

from travel_api import PROTOCOL_VERSION, TravelActionError, execute


def _error_result(
    code: str,
    message: str,
    *,
    retryable: bool = False,
) -> dict:
    if code in {
        "REVISION_CONFLICT", "TRIP_ID_CONFLICT",
        "DAY_SNAPSHOT_CONFLICT", "STOP_SNAPSHOT_CONFLICT",
    }:
        action = "retry_after_read"
    elif code == "INTERNAL_ERROR":
        action = "retry"
    else:
        action = "fix_request"
    return {
        "phase": "error",
        "code": code,
        "message": message,
        "retryable": retryable,
        "protocolVersion": PROTOCOL_VERSION,
        "updateMode": "error",
        "issues": [{
            "code": code,
            "severity": "error",
            "retryable": retryable,
            "action": action,
            "message": message,
        }],
    }


def execute_operation(operation: str, args: dict) -> dict:
    """执行一个领域操作，返回稳定的业务结果字典。"""
    try:
        if not isinstance(args, dict):
            raise TravelActionError("INVALID_ARGUMENT", "请求参数必须为对象。")
        result = execute(operation, args)
    except TravelActionError as exc:
        result = _error_result(
            exc.code,
            exc.message,
            retryable=bool(exc.retryable),
        )
    except Exception as exc:
        print(f"[travel_plan] unexpected {type(exc).__name__}: {exc}", file=sys.stderr)
        result = _error_result(
            "INTERNAL_ERROR",
            "行程处理出现内部错误，请稍后重试。",
            retryable=True,
        )
    result.setdefault("operation", operation)
    return result


def run(operation: str) -> int:
    raw = sys.argv[1] if len(sys.argv) > 1 else "{}"
    try:
        args = json.loads(raw)
    except json.JSONDecodeError:
        result = _error_result("INVALID_JSON", "请求参数不是合法 JSON。")
        result["operation"] = operation
    else:
        result = execute_operation(operation, args)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0
