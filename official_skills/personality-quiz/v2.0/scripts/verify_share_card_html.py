#!/usr/bin/env python3
"""Verify that a share-card HTML is complete and byte-bound to its input JSON."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from render_share_card_html import ASSET_PATH, ShareCardError, build_document


MAX_HTML_BYTES = 256_000


class VerificationError(ValueError):
    pass


def load_payload(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise VerificationError(f"找不到分享卡输入：{path}") from exc
    except json.JSONDecodeError as exc:
        raise VerificationError(f"分享卡输入 JSON 解析失败：第 {exc.lineno} 行第 {exc.colno} 列") from exc
    if not isinstance(payload, dict):
        raise VerificationError("分享卡输入顶层必须是对象")
    return payload


def verify(html_path: Path, input_path: Path) -> dict[str, object]:
    if html_path.suffix.lower() != ".html":
        raise VerificationError("待交付文件必须使用 .html 后缀")
    if html_path.resolve() == ASSET_PATH.resolve():
        raise VerificationError("不能交付内部分享卡模板")
    if not html_path.is_file():
        raise VerificationError(f"找不到分享卡 HTML：{html_path}")

    actual_bytes = html_path.read_bytes()
    if not actual_bytes or len(actual_bytes) > MAX_HTML_BYTES:
        raise VerificationError("分享卡 HTML 为空或大小异常")
    try:
        actual = actual_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise VerificationError("分享卡 HTML 不是有效 UTF-8") from exc

    card, expected, card_id = build_document(load_payload(input_path))
    if actual_bytes != expected.encode("utf-8"):
        raise VerificationError("分享卡 HTML 与输入 JSON 或当前模板不一致")
    if re.search(r"\{\{[A-Z0-9_]+\}\}", actual):
        raise VerificationError("分享卡 HTML 仍包含模板标记")
    if actual.count('data-product-kind="share_card"') != 1:
        raise VerificationError("分享卡 HTML 缺少唯一产品标记")
    if actual.count(f'data-card-id="{card_id}"') != 1:
        raise VerificationError("分享卡 HTML 的 card_id 无效")
    if f"template-{card['template_id']}" not in actual or f"source-{card['source_kind']}" not in actual:
        raise VerificationError("分享卡 HTML 的模板或来源类型不一致")
    if re.search(r"<(?:script|iframe|object|embed|form)\b", actual, re.IGNORECASE):
        raise VerificationError("分享卡 HTML 含有不允许的交互或嵌入内容")
    if re.search(r"\son[a-z]+\s*=", actual, re.IGNORECASE):
        raise VerificationError("分享卡 HTML 含有事件处理属性")
    if re.search(
        r"(?:src|href)\s*=\s*['\"](?:https?:)?//|url\(\s*['\"]?(?:https?:)?//",
        actual,
        re.IGNORECASE,
    ):
        raise VerificationError("分享卡 HTML 含有外部网络依赖")

    return {
        "ok": True,
        "output": str(html_path.resolve()),
        "card_id": card_id,
        "template_id": card["template_id"],
        "source_kind": card["source_kind"],
        "bytes": len(actual_bytes),
        "sha256": hashlib.sha256(actual_bytes).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a rendered share-card HTML before delivery.")
    parser.add_argument("html", type=Path)
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.html, args.input), ensure_ascii=False))
        return 0
    except (OSError, ShareCardError, VerificationError) as exc:
        print(
            json.dumps(
                {"ok": False, "error": "E_SHARE_CARD_DELIVERY", "message": str(exc)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
