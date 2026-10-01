#!/usr/bin/env python3
"""Build a question-scoped, self-contained Tarot draw HTML file."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSET_PATH = ROOT / "assets" / "tarot-draw-shell.html"
CONFIG_TOKEN = '<script id="tarot-standalone-config" type="application/json">{"question":""}</script>'


class BuildError(ValueError):
    pass


def normalize_question(value: str) -> str:
    question = " ".join(str(value or "").split())
    if not question:
        raise BuildError("塔罗 HTML 必须带入用户刚刚选择或输入的问题")
    if len(question) > 200:
        raise BuildError("塔罗问题不得超过 200 字")
    return question


def safe_script_json(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return (
        encoded.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def atomic_write(path: Path, content: str) -> None:
    if path.suffix.lower() != ".html":
        raise BuildError("输出文件必须使用 .html 后缀")
    if path.exists():
        raise BuildError(f"输出文件已存在：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def build(question: str) -> str:
    template = ASSET_PATH.read_text(encoding="utf-8")
    if template.count(CONFIG_TOKEN) != 1:
        raise BuildError("塔罗 HTML 模板配置标记无效")
    config = safe_script_json({"question": normalize_question(question), "generated": True})
    document = template.replace(
        CONFIG_TOKEN,
        f'<script id="tarot-standalone-config" type="application/json">{config}</script>',
    )
    required = (
        'data-standalone="true"',
        "window.__TAROT_ART__ =",
        "window.__TAROT_DECK_DATA__ =",
        "复制牌面信息，粘贴到会话进一步解读",
        "navigator.clipboard.writeText",
    )
    if any(marker not in document for marker in required):
        raise BuildError("塔罗 HTML 缺少独立交互所需的完整资源")
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a self-contained Tarot draw HTML.")
    parser.add_argument("--question", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        question = normalize_question(args.question)
        document = build(question)
        atomic_write(args.output, document)
        print(
            json.dumps(
                {
                    "ok": True,
                    "output": str(args.output),
                    "question": question,
                    "deck_size": 78,
                    "offline": True,
                },
                ensure_ascii=False,
            )
        )
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {"ok": False, "error": "E_TAROT_DRAW_HTML", "message": str(exc)},
                ensure_ascii=False,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
