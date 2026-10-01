#!/usr/bin/env python3
"""绑定行程卡 UI 的 render_trip handler。"""

from __future__ import annotations

import json

from tool_entry import execute_operation


MODEL_STATUS_FIELDS = ("operation", "phase", "rendered", "nextAction")
MODEL_ERROR_FIELDS = ("code", "message", "retryable")


def render_trip(args: dict) -> dict:
    """stdout 给模型执行摘要，返回值给 UI 完整行程快照。"""
    result = execute_operation("render_trip", args)
    model_result = {
        key: result[key]
        for key in MODEL_STATUS_FIELDS
        if key in result
    }
    if result.get("phase") == "error":
        model_result.update({
            key: result[key]
            for key in MODEL_ERROR_FIELDS
            if key in result
        })
    for key in ("warnings", "issues"):
        if result.get(key):
            model_result[key] = result[key]
    print(json.dumps(model_result, ensure_ascii=False, separators=(",", ":")))
    return result


if __name__ == "__main__":
    # 不认 handler.type=python 的 CLI 会把本文件当普通脚本执行，那条链路上 stdout
    # 既是模型输入也是卡片数据源，只能整份输出，否则卡片拿不到行程快照。
    from tool_entry import run

    raise SystemExit(run("render_trip"))
