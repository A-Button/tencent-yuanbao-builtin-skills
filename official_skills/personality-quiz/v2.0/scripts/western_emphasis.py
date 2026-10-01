"""Render one curated emphasis span without changing or interpreting preset copy."""

from __future__ import annotations

import html
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from western_profile import ORDER, SIGNS, normalize_sign

HIGHLIGHTS_PATH = Path(__file__).with_name("western_highlights.json")


@lru_cache(maxsize=1)
def catalog() -> dict[str, dict[str, str]]:
    payload = json.loads(HIGHLIGHTS_PATH.read_text(encoding="utf-8"))
    highlights = payload.get("highlights", {})
    if payload.get("schema_version") != "1.0.0" or set(highlights) != set(ORDER):
        raise ValueError("星座重点清单必须覆盖指定五项。")
    for entries in highlights.values():
        if not isinstance(entries, dict) or set(entries) != set(SIGNS):
            raise ValueError("星座重点清单必须覆盖十二星座。")
        if any(not isinstance(span, str) or not 6 <= len(span) <= 28 for span in entries.values()):
            raise ValueError("每项重点必须是 6—28 字的短语。")
    return highlights


def paragraph_html(item: dict[str, Any], part: str | None = None) -> str:
    """Unknown or revised copy stays plain; never guess another matching emphasis."""
    if part not in {None, "summary", "detail"}:
        raise ValueError("西占文案只能选择 summary 或 detail。")
    text = (item["summary"] + (item["detail"] or "")) if part is None else (item[part] or "")
    sign = normalize_sign(item.get("sign"))
    key = item.get("key")
    if item.get("status") != "available" or sign is None or key not in ORDER:
        return html.escape(text, quote=True)
    span = catalog()[key][sign]
    if text.count(span) != 1 or len(span) > len(text) * 0.45:
        return html.escape(text, quote=True)
    before, _, after = text.partition(span)
    return (
        html.escape(before, quote=True)
        + "<strong>" + html.escape(span, quote=True) + "</strong>"
        + html.escape(after, quote=True)
    )
