#!/usr/bin/env python3
"""list_books：列出全部图书与可用类别。"""

import json
import sys

from _store import CATALOG, CATEGORIES, ActionError, make_result, error_envelope


def main() -> int:
    raw = sys.argv[1] if len(sys.argv) > 1 else "{}"
    try:
        args = json.loads(raw)
        if args:
            raise ActionError("INVALID_ARGUMENT", "list_books 不接受额外参数")
        result = make_result("list_books", CATALOG, categories=CATEGORIES)
    except (json.JSONDecodeError, ActionError) as exc:
        code = getattr(exc, "code", "INVALID_JSON")
        message = getattr(exc, "message", "请求参数不是合法 JSON。")
        result = error_envelope(code, message)
    result.setdefault("operation", "list_books")
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())