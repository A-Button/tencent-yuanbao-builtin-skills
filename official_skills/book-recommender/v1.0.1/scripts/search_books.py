#!/usr/bin/env python3
"""search_books：按关键词搜索图书，同时匹配书名与作者。"""

import json
import sys

from _store import CATALOG, ActionError, make_result, error_envelope


def main() -> int:
    raw = sys.argv[1] if len(sys.argv) > 1 else "{}"
    try:
        args = json.loads(raw)
        query = args["query"].strip().lower()
        if not query:
            raise ActionError("INVALID_ARGUMENT", "query 不能为空")
        results = [
            b for b in CATALOG
            if query in b["title"].lower() or query in b["author"].lower()
        ]
        result = make_result("search_books", results, query=args["query"])
    except (json.JSONDecodeError, ActionError) as exc:
        code = getattr(exc, "code", "INVALID_JSON")
        message = getattr(exc, "message", "请求参数不是合法 JSON。")
        result = error_envelope(code, message)
    except KeyError:
        result = error_envelope("INVALID_ARGUMENT", "search_books 缺少参数：query")
    result.setdefault("operation", "search_books")
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())