#!/usr/bin/env python3
"""Check delivery-critical DOCX requirements before returning a document."""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
AUTHOR = f"{{{W}}}author"


def normalize(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))


def relevant_parts(names: list[str]) -> list[str]:
    return [
        name
        for name in names
        if name == "word/document.xml"
        or name.startswith("word/header")
        or name.startswith("word/footer")
        or name == "word/comments.xml"
    ]


def inspect(path: Path) -> tuple[str, int, list[ET.Element], int]:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if "word/document.xml" not in names:
            raise ValueError("missing word/document.xml")

        roots: dict[str, ET.Element] = {}
        for name in relevant_parts(names):
            roots[name] = ET.fromstring(archive.read(name))

    text = "\n".join("".join(root.itertext()) for root in roots.values())
    document = roots["word/document.xml"]
    tables = len(document.findall(f".//{{{W}}}tbl"))
    revisions = document.findall(f".//{{{W}}}ins") + document.findall(f".//{{{W}}}del")
    comments = len(roots.get("word/comments.xml", ET.Element("comments")).findall(f".//{{{W}}}comment"))
    return normalize(text), tables, revisions, comments


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("docx", type=Path)
    parser.add_argument("--require", action="append", default=[], help="Required text anchor; repeatable")
    parser.add_argument("--forbid", action="append", default=[], help="Forbidden text anchor; repeatable")
    parser.add_argument("--min-tables", type=int, default=0)
    parser.add_argument("--require-revision", action="store_true")
    parser.add_argument("--revision-author")
    parser.add_argument("--min-comments", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    failures: list[str] = []
    if not args.docx.is_file():
        failures.append(f"missing output: {args.docx}")
    elif args.docx.suffix.lower() != ".docx":
        failures.append(f"not a .docx file: {args.docx}")
    else:
        try:
            text, tables, revisions, comments = inspect(args.docx)
        except (OSError, ValueError, ET.ParseError, zipfile.BadZipFile) as exc:
            failures.append(f"cannot inspect {args.docx}: {exc}")
        else:
            for anchor in args.require:
                if normalize(anchor) not in text:
                    failures.append(f"missing required anchor: {anchor}")
            for anchor in args.forbid:
                if normalize(anchor) in text:
                    failures.append(f"forbidden anchor remains: {anchor}")
            if tables < args.min_tables:
                failures.append(f"tables={tables}, expected >= {args.min_tables}")
            matching_revisions = revisions
            if args.revision_author:
                matching_revisions = [
                    revision for revision in revisions if revision.get(AUTHOR) == args.revision_author
                ]
            if args.require_revision and not matching_revisions:
                author = f" by {args.revision_author}" if args.revision_author else ""
                failures.append(f"missing tracked revision{author}")
            if comments < args.min_comments:
                failures.append(f"comments={comments}, expected >= {args.min_comments}")

    if failures:
        print("PREFLIGHT FAILED")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print("PREFLIGHT OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
