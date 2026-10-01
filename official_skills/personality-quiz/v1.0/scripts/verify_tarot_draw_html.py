#!/usr/bin/env python3
"""Verify a generated standalone Tarot draw page before delivery."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from delivery import HOST_ATTACH_MAX_BYTES
from tarot_deck import deck_payload

# 去图后的骨架约 392KB。低于此值说明内联牌图被抽空或模板被截断。
MIN_TAROT_HTML_BYTES = 500_000


class VerifyError(ValueError):
    pass


def embedded_json(document: str, pattern: str, label: str) -> dict[str, object]:
    match = re.search(pattern, document, re.DOTALL)
    if not match:
        raise VerifyError(f"页面缺少{label}")
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise VerifyError(f"页面{label}无效") from exc
    if not isinstance(payload, dict):
        raise VerifyError(f"页面{label}必须是对象")
    return payload


def verify(path: Path) -> dict[str, object]:
    if path.suffix.lower() != ".html":
        raise VerifyError("只能交付已生成的 .html 文件")
    try:
        document = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise VerifyError("找不到待交付页面") from exc
    size = len(document.encode("utf-8"))
    if size < MIN_TAROT_HTML_BYTES:
        raise VerifyError("塔罗页面资源体积异常偏小")
    if size > HOST_ATTACH_MAX_BYTES:
        raise VerifyError("塔罗页面超过宿主附件上限")
    required = (
        'data-standalone="true"',
        "window.__TAROT_ART__ =",
        "window.__TAROT_DECK_DATA__ =",
        "navigator.clipboard.writeText",
        'document.execCommand("copy")',
        "window.tarotLocalBridge",
        "牌面信息已复制",
        "在心中默念你的问题",
        "function wheelMarkup()",
        'data-wheel="',
        "再抽一次",
        "card-reading__orientation",
        "orientation-info__panel",
        "orientation-info__trigger",
        'orientation-info[data-open="true"]',
        "ORIENTATION_GUIDES",
        "正位的通用解读方式",
        "逆位的通用解读方式",
        "hideName",
        "复制牌面信息，粘贴到会话进一步解读",
    )
    if any(marker not in document for marker in required):
        raise VerifyError("页面缺少独立抽牌交互")
    # 下面查的是"怎么接的"，不是"用没用到"。上面那张表只能确认 writeText 和 execCommand
    # 都出现过，所以它们被写成二选一也一路绿灯——宿主用权限策略拒掉 clipboard 时，兼容
    # 路径根本走不到，用户只看到一句原始 DOMException。朝向浮层同理：z-index 写在浮层
    # 自己身上，会被入场动画建立的层叠上下文关住，牌义正文照样盖在它上面。
    for marker, reason in (
        ("Promise.resolve(navigator.clipboard.writeText(text)).catch(",
         "剪贴板兼容路径不是回退链"),
        ("handoff-manual__text", "两条复制路径都失败时没有手动兜底"),
    ):
        if marker not in document:
            raise VerifyError(f"页面复制交接不完整：{reason}")
    if not re.search(r"\.card-reading__header\s*\{[^}]*z-index:", document):
        raise VerifyError("朝向浮层的层叠上下文没有抬高，会被牌义正文盖住")
    for obsolete in (
        "open-card-detail",
        "detailMarkup",
        'role="dialog" aria-modal="true"',
        "card-reading__orientation-note",
        "card-reading__meaning-label",
        "card-reading__section-label",
        "focus_card",
    ):
        if obsolete in document:
            raise VerifyError("页面仍包含已移除的牌面详情交互")
    if re.search(r"<(?:script|link)\b[^>]*(?:src|href)\s*=", document, re.IGNORECASE):
        raise VerifyError("页面仍依赖外部脚本或样式")
    for forbidden in (
        "fetch(",
        "XMLHttpRequest",
        "WebSocket",
        "navigator.sendBeacon",
        "localStorage",
        "sessionStorage",
        "indexedDB",
        "window.App",
        "mcpApp.",
        "callServerTool(",
        "show_app",
        "myTarotMcp",
        "MCP_BOOT_START",
    ):
        if forbidden in document:
            raise VerifyError("页面不是纯离线交互")

    config = embedded_json(
        document,
        r'<script id="tarot-standalone-config" type="application/json">(.*?)</script>',
        "问题配置",
    )
    question = config.get("question")
    if config.get("generated") is not True or not isinstance(question, str) or not question.strip():
        raise VerifyError("页面没有带入用户的当前问题")
    deck = embedded_json(
        document,
        r"window\.__TAROT_DECK_DATA__\s*=\s*(\{.*?\});\s*</script>",
        "78 张牌库",
    )
    cards = deck.get("cards")
    if not isinstance(cards, list) or len(cards) != 78:
        raise VerifyError("页面牌库不是完整 78 张")
    if deck != deck_payload():
        raise VerifyError("页面内嵌牌库与 tarot_deck.py 唯一真值不一致")
    upright = {
        card.get("displayUpright")
        for card in cards
        if isinstance(card, dict) and isinstance(card.get("displayUpright"), str)
    }
    reversed_copy = {
        card.get("displayReversed")
        for card in cards
        if isinstance(card, dict) and isinstance(card.get("displayReversed"), str)
    }
    if len(upright) != 78 or len(reversed_copy) != 78:
        raise VerifyError("页面缺少 156 条逐牌展示文案")
    if document.count('"src":"data:image/webp;base64,') != 78:
        raise VerifyError("页面没有内联完整 78 张牌图")
    return {
        "ok": True,
        "path": str(path.resolve()),
        "question": question,
        "cards": 78,
        "display_sentences": 156,
        "offline": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a standalone Tarot draw HTML.")
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.path), ensure_ascii=False))
        return 0
    except VerifyError as exc:
        print(
            json.dumps(
                {"ok": False, "error": "E_TAROT_HTML_DELIVERY", "message": str(exc)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
