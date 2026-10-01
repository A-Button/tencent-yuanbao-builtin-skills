#!/usr/bin/env python3
"""Build the offline Skill shell from the tarot-studio bundle and original art."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from tarot_deck import deck_payload
from tarot_asset_policy import MAX_HTML_BYTES, CONFIG_RESERVE_BYTES, FONT_WEIGHTS


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
VISUALS = ASSETS / "tarot-studio-visuals"
ORIGINAL_ART = ASSETS / "tarot-original-webp"
BUNDLE = ASSETS / "tarot-studio-bundle"
OUTPUT = ASSETS / "tarot-draw-shell.html"
CONFIG_TOKEN = '<script id="tarot-standalone-config" type="application/json">{"question":""}</script>'


def data_url(path: Path, mime: str) -> str:
    if not path.is_file():
        raise ValueError(f"缺少塔罗素材：{path}")
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def make_shell() -> str:
    deck = deck_payload()
    symbols = [card["symbolId"] for card in deck["cards"]]
    if len(symbols) != 78 or len(set(symbols)) != 78:
        raise ValueError("牌组不是 78 张独立牌")
    artwork = {f"{symbol}.webp": data_url(ORIGINAL_ART / f"{symbol}.webp", "image/webp")
               for symbol in symbols}
    for name in ("dark-back.jpg", "dark-background.jpg"):
        artwork[name] = data_url(VISUALS / name, "image/jpeg")

    font_css = "\n".join(
        "@font-face{font-family:'Noto Serif SC';font-style:normal;font-weight:%d;"
        "font-display:swap;src:url('%s') format('woff2')}" %
        (weight, data_url(VISUALS / f"noto-serif-sc-chinese-simplified-{weight}-normal.woff2", "font/woff2"))
        for weight in FONT_WEIGHTS
    )
    css = (BUNDLE / "app.css").read_text(encoding="utf-8")
    js = (BUNDLE / "app.js").read_text(encoding="utf-8")
    if "import(" in js or "/assets/" in js:
        raise ValueError("应用包仍依赖外部运行资源")
    if "</script" in js.lower():
        js = js.replace("</script", "<\\/script").replace("</SCRIPT", "<\\/SCRIPT")
    asset_json = json.dumps(artwork, ensure_ascii=True, separators=(",", ":"))
    deck_json = json.dumps(deck, ensure_ascii=False, separators=(",", ":"))
    return "\n".join((
        "<!doctype html>",
        '<html lang="zh-CN" data-standalone="true" data-source="tarot-studio">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">',
        '<meta name="theme-color" content="#0c0d0c">',
        "<title>观照 · 塔罗手记</title>",
        "<style>" + font_css + "\n" + css + "</style>",
        "</head>",
        '<body><div id="root"></div>',
        CONFIG_TOKEN,
        "<script>window.__TAROT_DECK_DATA__ = " + deck_json + ";</script>",
        "<script>window.__TAROT_ASSETS__ = " + asset_json + ";</script>",
        '<script type="module">' + js + "</script>",
        "</body></html>",
    ))


if __name__ == "__main__":
    document = make_shell()
    if len(document.encode("utf-8")) > MAX_HTML_BYTES - CONFIG_RESERVE_BYTES:
        raise ValueError("塔罗模板超过 9.5 MB 预算（含问题配置预留空间）")
    OUTPUT.write_text(document, encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(OUTPUT), "bytes": len(document.encode()),
                      "cards": 78, "offline": True}, ensure_ascii=False))
