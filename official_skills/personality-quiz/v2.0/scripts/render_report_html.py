#!/usr/bin/env python3
"""Render validated report Markdown into the bundled single-container HTML shell."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import tempfile
from pathlib import Path


ASSET_PATH = Path(__file__).resolve().parent.parent / "assets" / "report-shell.html"
WESTERN_THEME_PATH = ASSET_PATH.with_name("report-western-theme.css")
RAW_HTML = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")


def inline_markup(value: str) -> str:
    escaped = html.escape(value.strip(), quote=True)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(
        r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
        r'<a href="\2" rel="noopener noreferrer">\1</a>',
        escaped,
    )
    return escaped


def markdown_to_html(content: str) -> tuple[str, str]:
    if RAW_HTML.search(content):
        raise ValueError("Markdown 中不得包含原始 HTML。")
    lines = content.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    blocks: list[str] = []
    paragraph: list[str] = []
    list_type: str | None = None
    title = "报告"

    def flush_paragraph() -> None:
        if not paragraph:
            return
        text = " ".join(item.strip() for item in paragraph)
        class_name = ' class="disclaimer"' if text.startswith("AI生成内容｜") else ""
        blocks.append(f"<p{class_name}>{inline_markup(text)}</p>")
        paragraph.clear()

    def close_list() -> None:
        nonlocal list_type
        if list_type:
            blocks.append(f"</{list_type}>")
            list_type = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            close_list()
            continue
        heading = re.match(r"^(#{1,3})\s+(.+?)\s*$", line)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))
            value = heading.group(2).strip()
            if level == 1:
                title = value
            blocks.append(f"<h{level}>{inline_markup(value)}</h{level}>")
            continue
        if re.match(r"^\s*(?:---+|\*\*\*+)\s*$", line):
            flush_paragraph()
            close_list()
            blocks.append("<hr>")
            continue
        quote = re.match(r"^>\s?(.+)$", line)
        if quote:
            flush_paragraph()
            close_list()
            blocks.append(f"<blockquote>{inline_markup(quote.group(1))}</blockquote>")
            continue
        unordered = re.match(r"^\s*[-*]\s+(.+)$", line)
        ordered = re.match(r"^\s*\d+[.)]\s+(.+)$", line)
        if unordered or ordered:
            flush_paragraph()
            wanted = "ul" if unordered else "ol"
            if list_type != wanted:
                close_list()
                list_type = wanted
                blocks.append(f"<{wanted}>")
            match = unordered or ordered
            assert match is not None
            blocks.append(f"<li>{inline_markup(match.group(1))}</li>")
            continue
        close_list()
        paragraph.append(line)

    flush_paragraph()
    close_list()
    return title, "\n".join("    " + block for block in blocks)


def atomic_write(path: Path, content: str) -> None:
    if path.exists():
        raise FileExistsError(f"输出文件已存在：{path}")
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


def render_document(content: str, system: str = "bazi") -> str:
    if system not in {"bazi", "western"}:
        raise ValueError("报告体系必须是 bazi 或 western。")
    title, body = markdown_to_html(content)
    template = ASSET_PATH.read_text(encoding="utf-8")
    for placeholder in ("DOCUMENT_TITLE", "REPORT_BODY", "CHART_SYSTEM", "SYSTEM_THEME"):
        if "{{" + placeholder + "}}" not in template:
            raise ValueError("报告 HTML 模板缺少必要占位符。")
    theme = WESTERN_THEME_PATH.read_text(encoding="utf-8") if system == "western" else ""
    return (template.replace("{{DOCUMENT_TITLE}}", html.escape(title, quote=True))
            .replace("{{CHART_SYSTEM}}", system).replace("{{SYSTEM_THEME}}", theme)
            .replace("{{REPORT_BODY}}", body))


def main() -> int:
    parser = argparse.ArgumentParser(description="Render report Markdown as single-container HTML.")
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--system", choices=("bazi", "western"), default="bazi")
    args = parser.parse_args()
    try:
        content = args.report.read_text(encoding="utf-8")
        document = render_document(content, args.system)
        atomic_write(args.output, document)
        print(json.dumps({"ok": True, "output": str(args.output)}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": "E_REPORT_HTML", "message": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
