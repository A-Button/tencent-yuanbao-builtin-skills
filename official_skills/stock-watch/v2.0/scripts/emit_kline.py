#!/usr/bin/env python3
"""Emit a cowboy-host App result for stock-kline.

当前 stock-watch 的 SKILL.md 禁止调用本脚本：宿主还画不出这张渲染卡。
等渲染通路可用后再打开。现在跑它等于出一张空卡/坏卡。

Cloud stock-kline may print only the business JSON. Cowboy Things recover the
widget from a `__ONEAGENT_APP_RESULT__` marker and bind the stable App ID.
This wrapper always prints exactly one marker with app.id=stock-kline.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


APP_ID = "stock-kline"
APP_NAME = "股票 K 线"
URI = "ui://stock-kline/main"
MARKER = "__ONEAGENT_APP_RESULT__"
MIME = "text/html;profile=mcp-app"


def _runner() -> Path:
    configured = (os.environ.get("STOCK_KLINE_RUN") or "").strip()
    if configured:
        return Path(configured)
    here = Path(__file__).resolve()
    candidates = [
        Path("/data/skills/stock-kline/scripts/_run.py"),
        here.parents[4] / "third_party/app-skills/stock-kline/scripts/_run.py",
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError("stock-kline/_run.py not found")


def _read_request() -> dict[str, Any]:
    raw = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("参数必须是合法 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("参数必须是对象")
    return payload


def _first_object(stdout: str) -> dict[str, Any]:
    for line in stdout.splitlines():
        text = line.strip()
        if not text.startswith("{"):
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("stock-kline 未返回 JSON 对象")


def _without_candles(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    compact = {key: item for key, item in value.items() if key != "candles"}
    chart = compact.get("chart")
    if isinstance(chart, dict):
        compact["chart"] = _without_candles(chart)
    return compact


def _slim_structured(result: dict[str, Any]) -> dict[str, Any]:
    # The widget treats any `chart` as renderable. A candle-less chart paints
    # "行情数据不足" over the default waiting state. Keep identity on the host
    # marker; the preceding business JSON still carries the full candles.
    slim = {key: item for key, item in result.items() if key != "chart"}
    chart = result.get("chart")
    if isinstance(chart, dict):
        candles = chart.get("candles")
        if isinstance(candles, list) and candles:
            slim["candleCount"] = len(candles)
            last = candles[-1]
            if isinstance(last, dict):
                slim["last"] = last
        symbol = chart.get("symbol")
        if isinstance(symbol, str) and symbol.strip():
            slim["symbol"] = symbol
    return slim


def emit(arguments: dict[str, Any], result: dict[str, Any]) -> None:
    envelope = {
        "source": "skill",
        "app": {"id": APP_ID, "name": APP_NAME},
        "toolName": "stock_kline",
        "arguments": _without_candles(arguments),
        "status": "error" if result.get("phase") == "error" else "success",
        "resourceUri": URI,
        "resource": {"uri": URI, "name": APP_NAME, "mimeType": MIME},
        "structuredContent": _slim_structured(result),
        "content": [],
    }
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    print(MARKER + " " + json.dumps(envelope, ensure_ascii=False, separators=(",", ":")))


def main() -> int:
    try:
        arguments = _read_request()
        completed = subprocess.run(
            [sys.executable, str(_runner()), json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.stderr:
            sys.stderr.write(completed.stderr)
        result = _first_object(completed.stdout)
        emit(arguments, result)
        if completed.returncode != 0:
            return completed.returncode
        return 0 if result.get("phase") != "error" else 2
    except (FileNotFoundError, ValueError) as exc:
        emit({}, {"phase": "error", "code": "EMIT_KLINE_FAILED", "message": str(exc), "retryable": False})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
