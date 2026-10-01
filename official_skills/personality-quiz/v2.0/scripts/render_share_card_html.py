#!/usr/bin/env python3
"""Validate and render a concise, privacy-safe share card as portrait HTML."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ASSET_PATH = ROOT / "assets" / "share-card-shell.html"

TEMPLATES = {"profile", "insight", "guide"}
SOURCE_KINDS = {"bazi", "western", "ziwei", "vedic", "tarot", "entertainment"}
SENSITIVE_KEYS = {
    "birth_date", "birth_time", "birth_city", "birth_city_raw", "local_datetime",
    "lunar_datetime", "timezone", "latitude", "longitude", "name", "full_name",
    "account_id", "user_id", "chart", "analysis_chart", "signal_paths", "prompt",
    "raw_input", "anonymous_seed",
}
SUITABILITY_FLAGS = {
    "contains_birth_data", "contains_identity_data", "contains_high_impact_advice",
    "contains_third_party_inference",
}
FULL_DATE_RE = re.compile(
    r"(?<!\d)(?:18|19|20|21)\d{2}\s*(?:"
    r"[-/.]\s*(?:0?[1-9]|1[0-2])\s*[-/.]\s*(?:0?[1-9]|[12]\d|3[01])"
    r"|年\s*(?:0?[1-9]|1[0-2])\s*月\s*(?:0?[1-9]|[12]\d|3[01])\s*日?"
    r")(?!\d)"
)
BIRTH_CONTEXT_RE = re.compile(
    r"(?:出生日期|出生时间|出生地点|出生城市|出生于|生于|生日|"
    r"birth\s*(?:date|time|place|city))",
    re.IGNORECASE,
)
TIME_OF_DAY_RE = re.compile(
    r"(?<!\d)(?:[01]?\d|2[0-3])(?:[:：][0-5]\d(?:[:：][0-5]\d)?|"
    r"时[0-5]?\d分?)(?!\d)"
)
LATITUDE_VALUE_RE = re.compile(
    r"(?:纬度|latitude|lat)\s*[:：=]?\s*[-+]?\d{1,2}(?:\.\d+)?",
    re.IGNORECASE,
)
LONGITUDE_VALUE_RE = re.compile(
    r"(?:经度|longitude|lon)\s*[:：=]?\s*[-+]?\d{1,3}(?:\.\d+)?",
    re.IGNORECASE,
)
CARDINAL_COORDINATE_RE = re.compile(
    r"(?:(?:[NS]\s*\d{1,2}(?:\.\d+)?|\d{1,2}(?:\.\d+)?\s*°?\s*[NS])"
    r"\s*[,，;/\s]+"
    r"(?:[EW]\s*\d{1,3}(?:\.\d+)?|\d{1,3}(?:\.\d+)?\s*°?\s*[EW])|"
    r"(?:[EW]\s*\d{1,3}(?:\.\d+)?|\d{1,3}(?:\.\d+)?\s*°?\s*[EW])"
    r"\s*[,，;/\s]+"
    r"(?:[NS]\s*\d{1,2}(?:\.\d+)?|\d{1,2}(?:\.\d+)?\s*°?\s*[NS]))",
    re.IGNORECASE,
)
UNLABELED_COORDINATE_PAIR_RE = re.compile(
    r"(?<![\d.])([-+]?\d{1,2}(?:\.\d{3,}))\s*[,，;/]\s*"
    r"([-+]?\d{1,3}(?:\.\d{3,}))(?![\d.])"
)


class ShareCardError(ValueError):
    pass


def _text(value: Any, field: str, maximum: int, *, required: bool = True) -> str:
    if not required and (value is None or (isinstance(value, str) and not value.strip())):
        return ""
    if not isinstance(value, str) or not value.strip():
        raise ShareCardError(f"{field} 必须是非空字符串")
    normalized = " ".join(value.split())
    if len(normalized) > maximum:
        raise ShareCardError(f"{field} 超过 {maximum} 字")
    return normalized


def _find_sensitive_keys(value: Any, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            child = f"{path}.{key}"
            if str(key).lower() in SENSITIVE_KEYS:
                hits.append(child)
            hits.extend(_find_sensitive_keys(nested, child))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            hits.extend(_find_sensitive_keys(nested, f"{path}[{index}]"))
    return hits


def _text_privacy_reason(value: str) -> str | None:
    if FULL_DATE_RE.search(value):
        return "完整日期"
    if BIRTH_CONTEXT_RE.search(value) and TIME_OF_DAY_RE.search(value):
        return "出生时间"
    if LATITUDE_VALUE_RE.search(value) and LONGITUDE_VALUE_RE.search(value):
        return "经纬度"
    if CARDINAL_COORDINATE_RE.search(value):
        return "经纬度"
    for match in UNLABELED_COORDINATE_PAIR_RE.finditer(value):
        latitude, longitude = (float(part) for part in match.groups())
        if -90 <= latitude <= 90 and -180 <= longitude <= 180:
            return "疑似经纬度"
    return None


def _find_sensitive_text(value: Any, path: str = "$") -> list[str]:
    if path == "$.footer.date":
        return []
    if isinstance(value, str):
        reason = _text_privacy_reason(value)
        return [f"{path}（{reason}）"] if reason else []
    hits: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            hits.extend(_find_sensitive_text(nested, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            hits.extend(_find_sensitive_text(nested, f"{path}[{index}]"))
    return hits


def _normalize_mini_item(value: Any, field: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ShareCardError(f"{field} 必须是对象")
    return {
        "symbol": _text(value.get("symbol"), f"{field}.symbol", 4, required=False),
        "title": _text(value.get("title"), f"{field}.title", 18),
        "caption": _text(value.get("caption"), f"{field}.caption", 28, required=False),
    }


def normalize(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ShareCardError("输入必须是 JSON 对象")
    hits = _find_sensitive_keys(payload)
    if hits:
        raise ShareCardError(f"图卡输入包含禁止字段：{', '.join(hits)}")
    if payload.get("schema_version") != "1.0.0":
        raise ShareCardError("schema_version 必须为 1.0.0")
    if payload.get("product_kind") != "share_card":
        raise ShareCardError("product_kind 必须为 share_card")

    template_id = payload.get("template_id")
    source_kind = payload.get("source_kind")
    if template_id not in TEMPLATES:
        raise ShareCardError(f"不支持的 template_id：{template_id}")
    if source_kind not in SOURCE_KINDS:
        raise ShareCardError(f"不支持的 source_kind：{source_kind}")

    suitability = payload.get("suitability")
    if not isinstance(suitability, dict) or set(suitability) != SUITABILITY_FLAGS:
        raise ShareCardError("suitability 必须完整声明四个安全标记")
    unsafe = [key for key in sorted(SUITABILITY_FLAGS) if suitability.get(key) is not False]
    if unsafe:
        raise ShareCardError(f"内容不适合生成分享图卡：{', '.join(unsafe)}")

    highlight_raw = payload.get("highlight")
    highlight = _normalize_mini_item(highlight_raw, "highlight") if highlight_raw is not None else None

    keywords_raw = payload.get("keywords", [])
    if not isinstance(keywords_raw, list) or len(keywords_raw) > 3:
        raise ShareCardError("keywords 必须是最多 3 项的数组")
    keywords = [_text(value, f"keywords[{index}]", 8) for index, value in enumerate(keywords_raw)]

    items_raw = payload.get("items", [])
    if not isinstance(items_raw, list) or len(items_raw) > 4:
        raise ShareCardError("items 必须是最多 4 项的数组")
    items = [_normalize_mini_item(value, f"items[{index}]") for index, value in enumerate(items_raw)]

    sections_raw = payload.get("sections", [])
    if not isinstance(sections_raw, list) or len(sections_raw) > 3:
        raise ShareCardError("sections 必须是最多 3 项的数组")
    sections: list[dict[str, str]] = []
    for index, value in enumerate(sections_raw):
        if not isinstance(value, dict):
            raise ShareCardError(f"sections[{index}] 必须是对象")
        sections.append({
            "title": _text(value.get("title"), f"sections[{index}].title", 18),
            "body": _text(value.get("body"), f"sections[{index}].body", 140),
        })

    footer_raw = payload.get("footer", {})
    if not isinstance(footer_raw, dict):
        raise ShareCardError("footer 必须是对象")
    footer = {
        "date": _text(footer_raw.get("date"), "footer.date", 16, required=False),
        "boundary": _text(footer_raw.get("boundary"), "footer.boundary", 60),
    }

    normalized = {
        "schema_version": "1.0.0",
        "product_kind": "share_card",
        "template_id": template_id,
        "source_kind": source_kind,
        "eyebrow": _text(payload.get("eyebrow"), "eyebrow", 16, required=False),
        "title": _text(payload.get("title"), "title", 24),
        "subtitle": _text(payload.get("subtitle"), "subtitle", 40, required=False),
        "highlight": highlight,
        "keywords": keywords,
        "items": items,
        "summary": _text(payload.get("summary"), "summary", 180),
        "sections": sections,
        "footer": footer,
        "suitability": {key: False for key in sorted(SUITABILITY_FLAGS)},
    }

    text_hits = _find_sensitive_text(normalized)
    if text_hits:
        raise ShareCardError(f"图卡可见文本触发隐私闸门：{', '.join(text_hits)}")

    if template_id == "profile" and (highlight is None or not items):
        raise ShareCardError("profile 模板需要 highlight 和至少 1 个 item")
    if template_id == "insight" and (highlight is None or not keywords):
        raise ShareCardError("insight 模板需要 highlight 和至少 1 个 keyword")
    if template_id == "guide" and len(items) < 2:
        raise ShareCardError("guide 模板需要至少 2 个 item")
    return normalized


def _e(value: str) -> str:
    return html.escape(value, quote=True)


def _render_highlight(highlight: dict[str, str] | None) -> str:
    if highlight is None:
        return ""
    symbol = f'<div class="hero-symbol">{_e(highlight["symbol"] + chr(0xFE0E))}</div>' if highlight["symbol"] else ""
    caption = f'<p>{_e(highlight["caption"])}</p>' if highlight["caption"] else ""
    return f'<section class="hero">{symbol}<div><h2>{_e(highlight["title"])}</h2>{caption}</div></section>'


def _render_items(items: list[dict[str, str]]) -> str:
    if not items:
        return ""
    cards = []
    for item in items:
        symbol = f'<span class="item-symbol">{_e(item["symbol"] + chr(0xFE0E))}</span>' if item["symbol"] else ""
        caption = f'<p>{_e(item["caption"])}</p>' if item["caption"] else ""
        cards.append(f'<article class="item">{symbol}<h3>{_e(item["title"])}</h3>{caption}</article>')
    return f'<section class="items">{"".join(cards)}</section>'


def _render_keywords(keywords: list[str]) -> str:
    if not keywords:
        return ""
    return '<div class="keywords">' + "".join(f'<span>{_e(word)}</span>' for word in keywords) + "</div>"


def _render_sections(sections: list[dict[str, str]]) -> str:
    if not sections:
        return ""
    return '<section class="sections">' + "".join(
        f'<article><h3>{_e(section["title"])}</h3><p>{_e(section["body"])}</p></article>'
        for section in sections
    ) + "</section>"


def card_id_for(card: dict[str, Any]) -> str:
    canonical = json.dumps(card, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def build_document(payload: Any) -> tuple[dict[str, Any], str, str]:
    card = normalize(payload)
    shell = ASSET_PATH.read_text(encoding="utf-8")
    card_id = card_id_for(card)
    replacements = {
        "{{LANG}}": "zh-CN",
        "{{TITLE}}": _e(card["title"]),
        "{{TEMPLATE_ID}}": _e(card["template_id"]),
        "{{SOURCE_KIND}}": _e(card["source_kind"]),
        "{{EYEBROW}}": _e(card["eyebrow"]),
        "{{SUBTITLE}}": _e(card["subtitle"]),
        "{{HIGHLIGHT}}": _render_highlight(card["highlight"]),
        "{{KEYWORDS}}": _render_keywords(card["keywords"]),
        "{{ITEMS}}": _render_items(card["items"]),
        "{{SUMMARY}}": _e(card["summary"]),
        "{{SECTIONS}}": _render_sections(card["sections"]),
        "{{DATE}}": _e(card["footer"]["date"]),
        "{{BOUNDARY}}": _e(card["footer"]["boundary"]),
        "{{CARD_ID}}": card_id,
    }
    for marker, value in replacements.items():
        shell = shell.replace(marker, value)
    if re.search(r"\{\{[A-Z0-9_]+\}\}", shell):
        raise ShareCardError("生成页面仍包含模板标记")
    return card, shell, card_id


def atomic_write(path: Path, content: str) -> None:
    if path.exists():
        raise ShareCardError(f"拒绝覆盖已有文件：{path}")
    if path.suffix.lower() != ".html":
        raise ShareCardError("分享卡输出必须使用 .html 后缀")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temp_name, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a privacy-safe share card as portrait HTML.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        card, document, card_id = build_document(payload)
        atomic_write(args.output, document)
        document_bytes = document.encode("utf-8")
        print(json.dumps({
            "ok": True,
            "output": str(args.output.resolve()),
            "template_id": card["template_id"],
            "source_kind": card["source_kind"],
            "card_id": card_id,
            "bytes": len(document_bytes),
            "sha256": hashlib.sha256(document_bytes).hexdigest(),
        }, ensure_ascii=False))
        return 0
    except (OSError, json.JSONDecodeError, ShareCardError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
