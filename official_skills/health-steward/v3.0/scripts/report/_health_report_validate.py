#!/usr/bin/env python3
"""Validate the health-report-v1.0 package and generated HTML outputs."""

from __future__ import annotations

import sys
from pathlib import Path
_scripts = Path(__file__).resolve().parents[1]
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))
import _boot
_boot.install()

import argparse
import html as html_lib
import json
import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = ROOT / "references" / "report" / "health-report-v1.0"
CASES = REPORT_ROOT / "cases"
ASSETS = ROOT / "assets" / "ui" / "report" / "health-report-v1.0"
MAX_HTML_BYTES = 5 * 1024 * 1024
FORBIDDEN_TAGS = {
    "script", "iframe", "frame", "frameset", "fencedframe", "portal",
    "object", "embed", "form", "link", "base",
    "foreignobject", "animate", "animatetransform", "animatemotion", "set",
}
URL_ATTRS = {
    "src", "href", "action", "formaction", "poster", "xlink:href",
    "background", "cite", "longdesc", "usemap", "data", "codebase", "manifest",
    "ping", "archive", "profile", "icon", "lowsrc", "dynsrc",
}


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def normalized_url(value: str) -> str:
    decoded = html_lib.unescape(value or "")
    return re.sub(r"[\x00-\x20]+", "", decoded).lower()


def unsafe_url(value: str) -> bool:
    url = normalized_url(value)
    if not url or url.startswith("#"):
        return False
    if url.startswith("//"):
        return True
    if url.startswith("data:"):
        return not bool(re.match(r"^data:image/(png|jpeg|jpg|gif|webp);base64,", url))
    if re.match(r"^[a-z][a-z0-9+.-]*:", url):
        return True
    return False


def unsafe_css(value: str) -> bool:
    css = html_lib.unescape(value or "").lower()
    if "\\" in css:
        return True
    if re.search(r"@import|expression\s*\(|-moz-binding|javascript\s*:|image-set\s*\(|-webkit-image-set\s*\(", css):
        return True
    for target in re.findall(r"url\(\s*[\"']?([^\"')]+)", css, flags=re.I):
        if unsafe_url(target):
            return True
    return False


class SafeHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.errors: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in FORBIDDEN_TAGS:
            self.errors.append(f"forbidden tag <{tag}>")
        http_equiv_values: list[str] = []
        for raw_name, raw_value in attrs:
            name = str(raw_name).lower()
            value = raw_value or ""
            if name.startswith("on"):
                self.errors.append(f"inline event attribute {name}")
            if name == "srcdoc":
                self.errors.append("srcdoc attribute")
            if name in URL_ATTRS and unsafe_url(value):
                self.errors.append(f"unsafe URL in {name}")
            if name == "srcset":
                for candidate in value.split(","):
                    if unsafe_url(candidate.strip().split(" ", 1)[0]):
                        self.errors.append("unsafe URL in srcset")
            if name == "style" and unsafe_css(value):
                self.errors.append("unsafe inline CSS")
            if name == "http-equiv":
                http_equiv_values.append(value.lower())
        if tag == "meta" and "refresh" in http_equiv_values:
            self.errors.append("meta refresh")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)


def scan_html(html: str) -> list[str]:
    parser = SafeHTMLParser()
    parser.feed(html)
    errors = list(parser.errors)
    if unsafe_css(html):
        errors.append("unsafe CSS resource or expression")
    return sorted(set(errors))


def check_package() -> None:
    required = [
        ROOT / "SKILL.md",
        ASSETS / "daily_template.html",
        ASSETS / "weekly_template.html",
        # 模块原作者的生成规则和调试说明（daily-rules / weekly-rules / test-cases）是开发文档，
        # 门控和模板已经落在脚本里，模型用不到，移到了包外的 dev/。
        REPORT_ROOT / "api_reference.md",
        CASES / "01_daily_complete.json",
        CASES / "02_daily_partial.json",
        CASES / "03_weekly_complete.json",
        CASES / "04_weekly_sparse.json",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        fail("missing files: " + ", ".join(missing))
    for path in ROOT.rglob("*"):
        if path.is_symlink():
            fail(f"package contains symbolic link: {path.relative_to(ROOT)}")
        if path.is_file() and path.stat().st_size > MAX_HTML_BYTES:
            fail(f"package file exceeds 5 MB: {path.relative_to(ROOT)}")

    expected_types = {
        "01_daily_complete.json": "daily",
        "02_daily_partial.json": "daily",
        "03_weekly_complete.json": "weekly",
        "04_weekly_sparse.json": "weekly",
    }
    for name, report_type in expected_types.items():
        data = json.loads((CASES / name).read_text(encoding="utf-8"))
        if data.get("report_type") != report_type:
            fail(f"{name} report_type must be {report_type}")

    daily = (ASSETS / "daily_template.html").read_text(encoding="utf-8")
    weekly = (ASSETS / "weekly_template.html").read_text(encoding="utf-8")
    if "{{MEAL_CARDS_HTML}}" not in daily or "{{EXERCISE_CARDS_HTML}}" not in daily:
        fail("daily template is missing required placeholders")
    weekly_placeholders = {
        "{{OVERALL_SHEETS_HTML}}",
        "{{DIET_MATRIX_HTML}}",
        "{{SPORT_MATRIX_HTML}}",
        "{{PLAN_MATRIX_HTML}}",
    }
    found = set(re.findall(r"\{\{[^{}]+\}\}", weekly))
    if not weekly_placeholders.issubset(found):
        fail("weekly template is missing required placeholders")
    if weekly.count('class="matrix-wrap') != 3:
        fail("weekly template must contain three scrollable matrices")
    if "要不要一键帮你同步到日历" in weekly:
        fail("calendar prompt must stay outside HTML")
    if re.search(r"一掌|一拳|半拳|两拳", weekly):
        fail("weekly template contains forbidden body-based portions")
    if re.search(r"09/14|16,100|\+400", weekly):
        fail("weekly template still contains demo health data")
    for name, template in {"daily": daily, "weekly": weekly}.items():
        errors = scan_html(template)
        if errors:
            fail(f"unsafe {name} template: {', '.join(errors)}")

    print("PASS: package structure, four cases, safe placeholder templates")


def check_output(path: Path, report_type: str) -> None:
    path = path.expanduser()
    if path.is_symlink():
        fail("refuse to validate symbolic links")
    path = path.resolve()
    if path.suffix.lower() not in {".html", ".htm"}:
        fail("output must be an HTML file")
    if not path.is_file():
        fail(f"output not found: {path}")
    if path.stat().st_size > MAX_HTML_BYTES:
        fail("output exceeds 5 MB")

    html = path.read_text(encoding="utf-8")
    errors = scan_html(html)
    if errors:
        fail("unsafe HTML: " + ", ".join(errors))
    if "<button" in html.lower():
        fail("output must not contain buttons")
    if re.search(r"\{\{[^{}]+\}\}", html):
        fail("output contains unresolved placeholders")
    if re.search(r"一掌|一拳|半拳|两拳", html):
        fail("output contains forbidden body-based portions")
    if "要不要一键帮你同步到日历" in html:
        fail("calendar prompt must stay outside HTML")

    if report_type == "weekly":
        if html.count('class="matrix-wrap') != 3:
            fail("weekly output must contain three scrollable matrices")
        if "overflow-x:auto" not in html:
            fail("weekly output must enable internal horizontal scrolling")
        if "暂无记录" not in html:
            fail("weekly output must render missing historical cells as 暂无记录")
    print(f"PASS: {report_type} output {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-package", action="store_true")
    parser.add_argument("--check-output", type=Path)
    parser.add_argument("--type", choices=["daily", "weekly"])
    args = parser.parse_args()

    if args.check_package:
        check_package()
    elif args.check_output and args.type:
        check_output(args.check_output, args.type)
    else:
        parser.error("use --check-package or --check-output PATH --type daily|weekly")


if __name__ == "__main__":
    main()
