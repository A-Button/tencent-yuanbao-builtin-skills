#!/usr/bin/env python3
"""recommend_books：推荐图书，可按类别筛选、设置数量，默认按评分选最高分的前几名。"""

import json
import random
import sys

from _store import CATALOG, ActionError, make_result, error_envelope


def main() -> int:
    raw = sys.argv[1] if len(sys.argv) > 1 else "{}"
    try:
        args = json.loads(raw)
        category = args.get("category", "").strip()
        count = args.get("count", 5)
        if not isinstance(count, int) or count <= 0:
            count = 5
        count = min(count, 20)

        pool = [b for b in CATALOG if b["category"] == category] if category else CATALOG
        if not pool:
            raise ActionError("NO_MATCH", f"没有「{category}」类别的图书")

        results = sorted(pool, key=lambda b: b["rating"], reverse=True)[:count]
        random.shuffle(results)
        result = make_result("recommend_books", results, category=category or "全部")
    except (json.JSONDecodeError, ActionError) as exc:
        code = getattr(exc, "code", "INVALID_JSON")
        message = getattr(exc, "message", "请求参数不是合法 JSON。")
        result = error_envelope(code, message)
    result.setdefault("operation", "recommend_books")
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())