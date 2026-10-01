#!/usr/bin/env python3
"""Verify the generated, offline tarot-studio page before delivery."""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import uuid
from pathlib import Path

from tarot_deck import deck_payload
from tarot_asset_policy import MAX_HTML_BYTES, FONT_WEIGHTS


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"


class VerifyError(ValueError):
    pass


def embedded_json(document: str, pattern: str, label: str) -> dict[str, object]:
    match = re.search(pattern, document, re.DOTALL)
    if not match:
        raise VerifyError(f"页面缺少{label}")
    try:
        result = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise VerifyError(f"页面{label}无效") from exc
    if not isinstance(result, dict):
        raise VerifyError(f"页面{label}必须是对象")
    return result


def verify(path: Path) -> dict[str, object]:
    if path.suffix.lower() != ".html":
        raise VerifyError("只能交付已生成的 .html 文件")
    try:
        document = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise VerifyError("找不到待交付页面") from exc
    size = len(document.encode("utf-8"))
    if size > MAX_HTML_BYTES:
        raise VerifyError("塔罗 HTML 超过 9.5 MB 体积上限")
    required = (
        'data-standalone="true"', 'data-source="tarot-studio"',
        '<meta name="viewport"', "请在心中默念你的问题", "分享结果", "复制给元宝",
        "tarot-wheel", "atmosphere", "prefers-reduced-motion",
        "window.__TAROT_ASSETS__ =", "window.__TAROT_DECK_DATA__ =",
    )
    if any(marker not in document for marker in required):
        raise VerifyError("页面缺少 tarot-studio 的三张抽牌与分享交互")
    if re.search(r"<(?:script|link)\b[^>]*(?:src|href)\s*=", document, re.IGNORECASE):
        raise VerifyError("页面仍依赖外部脚本或样式")
    style = re.search(r"<style>(.*?)</style>", document, re.DOTALL)
    if not style or re.search(r"@import\b|url\(['\"]?https?://", style.group(1), re.IGNORECASE):
        raise VerifyError("页面仍依赖在线样式或图片")

    config = embedded_json(
        document,
        r'<script id="tarot-standalone-config" type="application/json">(.*?)</script>',
        "问题配置",
    )
    question = config.get("question")
    if config.get("generated") is not True or not isinstance(question, str) or not question.strip():
        raise VerifyError("页面没有带入用户的当前问题")
    try:
        uuid.UUID(config.get("artifactId", ""))
    except (ValueError, TypeError, AttributeError) as exc:
        raise VerifyError("页面缺少独立的状态标识") from exc

    deck = embedded_json(
        document, r"window\.__TAROT_DECK_DATA__\s*=\s*(\{.*?\});</script>", "78 张牌库"
    )
    cards = deck.get("cards")
    if not isinstance(cards, list) or len(cards) != 78 or deck != deck_payload():
        raise VerifyError("页面牌库与 tarot_deck.py 唯一真值不一致")
    if len({card.get("displayUpright") for card in cards}) != 78 or len(
        {card.get("displayReversed") for card in cards}
    ) != 78:
        raise VerifyError("页面缺少 156 条逐牌正逆位文案")

    artwork = embedded_json(
        document, r"window\.__TAROT_ASSETS__\s*=\s*(\{.*?\});</script>", "离线视觉素材"
    )
    names = {f"{card['symbolId']}.webp" for card in cards}
    visuals = {"dark-back.jpg", "dark-background.jpg"}
    if set(artwork) != names | visuals:
        raise VerifyError("牌面或深色背景素材不完整")
    for name, src in artwork.items():
        prefix = "data:image/webp;base64," if name.endswith(".webp") else "data:image/jpeg;base64,"
        if not isinstance(src, str) or not src.startswith(prefix):
            raise VerifyError(f"素材格式无效：{name}")
        try:
            binary = base64.b64decode(src[len(prefix):], validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise VerifyError(f"素材无法解码：{name}") from exc
        source = (ASSETS / "tarot-original-webp" / name) if name.endswith(".webp") else (
            ASSETS / "tarot-studio-visuals" / name
        )
        if binary != source.read_bytes():
            raise VerifyError(f"内嵌素材不是原始文件：{name}")
        if name.endswith(".webp") and (binary[:4], binary[8:12]) != (b"RIFF", b"WEBP"):
            raise VerifyError(f"牌图不是 WebP 文件：{name}")
        if name.endswith(".jpg") and binary[:3] != b"\xff\xd8\xff":
            raise VerifyError(f"视觉素材不是 JPEG 文件：{name}")

    module = re.search(r'<script type="module">(.*?)</script>', document, re.DOTALL)
    if not module or module.group(1) != (ASSETS / "tarot-studio-bundle" / "app.js").read_text():
        raise VerifyError("页面交互包与 tarot-studio 构建产物不一致")
    css = (ASSETS / "tarot-studio-bundle" / "app.css").read_text()
    if css not in document:
        raise VerifyError("页面没有内联 tarot-studio 样式")
    fonts = re.findall(r"@font-face\{font-family:'Noto Serif SC';font-style:normal;font-weight:(\d+);"
                       r"font-display:swap;src:url\('data:font/woff2;base64,([^']+)'\) format\('woff2'\)\}",
                       style.group(1))
    if tuple(int(weight) for weight, _ in fonts) != FONT_WEIGHTS or document.count("data:font/woff2;base64,") != len(FONT_WEIGHTS):
        raise VerifyError("页面必须仅内联 400／500 两种宋体字重")
    for weight, encoded in fonts:
        original = ASSETS / "tarot-studio-visuals" / f"noto-serif-sc-chinese-simplified-{weight}-normal.woff2"
        if encoded != base64.b64encode(original.read_bytes()).decode("ascii"):
            raise VerifyError(f"内嵌宋体 {weight} 与原文件不一致")
    return {"ok": True, "path": str(path.resolve()), "question": question, "cards": 78,
            "display_sentences": 156, "offline": True, "source": "tarot-studio",
            "bytes": size, "max_bytes": MAX_HTML_BYTES, "font_weights": FONT_WEIGHTS}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify an offline tarot-studio Skill HTML page.")
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.path), ensure_ascii=False))
        return 0
    except (VerifyError, OSError) as exc:
        print(json.dumps({"ok": False, "error": "E_TAROT_HTML_DELIVERY", "message": str(exc)},
                         ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
