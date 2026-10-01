"""Pure DataModel passthrough shared by the three XCard render tools."""

import json
import sys


def main() -> None:
    try:
        payload = json.loads(sys.argv[1] if len(sys.argv) > 1 else "{}")
    except json.JSONDecodeError:
        print(json.dumps({
            "phase": "error",
            "code": "INVALID_JSON",
            "message": "卡片数据不是合法 JSON",
            "retryable": False,
        }, ensure_ascii=False, separators=(",", ":")))
        return

    if not isinstance(payload, dict):
        print(json.dumps({
            "phase": "error",
            "code": "INVALID_PAYLOAD",
            "message": "卡片数据必须是对象",
            "retryable": False,
        }, ensure_ascii=False, separators=(",", ":")))
        return

    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
