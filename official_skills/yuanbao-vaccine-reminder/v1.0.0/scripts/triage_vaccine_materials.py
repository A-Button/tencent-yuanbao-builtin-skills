#!/usr/bin/env python3
"""Fast first-pass triage for vaccine-book images.

The script inventories and de-duplicates uploads, runs one inexpensive OCR pass
per unique image, classifies page types, and emits the smallest page set needed
for the requested task. It deliberately does not turn OCR guesses into clinical
facts; detailed extraction and confirmation happen only on selected pages.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


PAGE_RULES = {
    "actual_record": (
        "接种记录", "接种日期", "疫苗名称", "疫苗批号", "接种部位", "接种单位",
        "生产企业", "接种医生", "疫苗种类", "vaccination record", "vaccine&dose",
        "manufacturer", "lot#", "clinic",
    ),
    "appointment_notice": (
        "预约告知", "预约通知", "温馨提示", "体检时间", "参考价格", "自费疫苗",
        "下次接种", "预约时间", "放号", "保健科", "appointment", "price",
    ),
    "program_reference": (
        "国家免疫规划", "免疫程序", "接种年（月）龄", "接种年龄", "免疫规划疫苗",
        "immunization schedule",
    ),
    "identity_page": (
        "预防接种证", "出生日期", "儿童姓名", "身份证", "家庭住址", "监护人",
        "date of birth", "birth date", "current address", "mobile phone",
    ),
}

TASK_FIELDS = {
    "history": ["vaccine_name", "dose", "actual_date"],
    "next": ["vaccine_name", "dose", "actual_date", "doctor_plan_date"],
    "report": ["vaccine_name", "dose", "actual_date", "doctor_plan_date"],
}


@dataclass(frozen=True)
class Item:
    path: Path
    sha256: str
    duplicate_of: str | None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory(paths: list[Path]) -> list[Item]:
    seen: dict[str, str] = {}
    result: list[Item] = []
    for path in paths:
        digest = sha256(path)
        duplicate_of = seen.get(digest)
        if duplicate_of is None:
            seen[digest] = path.name
        result.append(Item(path=path, sha256=digest, duplicate_of=duplicate_of))
    return result


def preprocess(source: Path, destination: Path, max_edge: int) -> None:
    """Create a lightweight grayscale OCR copy when Pillow is available."""
    try:
        from PIL import Image, ImageOps  # type: ignore
    except ImportError:
        shutil.copy2(source, destination)
        return
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image).convert("L")
        image.thumbnail((max_edge, max_edge))
        image = ImageOps.autocontrast(image, cutoff=1)
        image.save(destination, format="PNG", optimize=True)


def replay_text(image: Path, text_dir: Path) -> str:
    candidates = [text_dir / f"{image.name}.txt", text_dir / f"{image.stem}.txt"]
    for candidate in candidates:
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    raise FileNotFoundError(f"missing OCR replay text for {image.name}")


def quick_ocr(image: Path, args: argparse.Namespace, temp_dir: Path) -> tuple[str, float, str]:
    started = time.monotonic()
    if args.ocr_text_dir:
        text = replay_text(image, args.ocr_text_dir)
        return text, time.monotonic() - started, "replay"

    tesseract = shutil.which(args.tesseract)
    if not tesseract:
        return "", time.monotonic() - started, "unavailable"
    prepared = temp_dir / f"{hashlib.sha1(str(image).encode()).hexdigest()}.png"
    preprocess(image, prepared, args.max_edge)
    command = [
        tesseract, str(prepared), "stdout", "-l", args.languages,
        "--psm", str(args.psm),
    ]
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=args.timeout,
        check=False,
    )
    if completed.returncode != 0:
        return "", time.monotonic() - started, f"error:{completed.returncode}"
    return completed.stdout, time.monotonic() - started, "tesseract"


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def classify(text: str) -> tuple[str, float, dict[str, int]]:
    normalized = compact(text)
    scores = {
        page_type: sum(1 for term in terms if compact(term) in normalized)
        for page_type, terms in PAGE_RULES.items()
    }
    best_type, best_score = max(scores.items(), key=lambda pair: pair[1])
    sorted_scores = sorted(scores.values(), reverse=True)
    runner_up = sorted_scores[1] if len(sorted_scores) > 1 else 0
    if best_score == 0:
        return "unknown", 0.0, scores
    confidence = min(1.0, 0.42 + best_score * 0.12 + max(0, best_score - runner_up) * 0.08)
    if best_score == 1 and runner_up == 1:
        return "unknown", min(confidence, 0.49), scores
    return best_type, round(confidence, 2), scores


def choose_pages(pages: list[dict], task: str, need_age: bool, need_child_name: bool) -> None:
    records = [p for p in pages if p["page_type"] == "actual_record"]
    notices = [p for p in pages if p["page_type"] == "appointment_notice"]
    identities = [p for p in pages if p["page_type"] == "identity_page"]

    for page in pages:
        page["action"] = "skip"
        page["reason"] = "not needed for current task"
        if page["page_type"] == "unknown":
            page["action"] = "review_thumbnail"
            page["reason"] = "page type uncertain; inspect once before deciding"

    for page in records:
        page["action"] = "detail_ocr"
        page["reason"] = "actual record page"

    if task in {"next", "report"}:
        for page in notices:
            page["action"] = "detail_ocr"
            page["reason"] = "doctor notice or appointment context"

    if (need_age or need_child_name) and identities:
        chosen = max(identities, key=lambda page: (page["confidence"], page["scores"]["identity_page"]))
        fields = []
        if need_child_name:
            fields.append("child_name")
        if need_age:
            fields.append("date_of_birth")
        chosen["action"] = "identity_fields"
        chosen["identity_fields"] = fields
        chosen["reason"] = "one identity page selected for only the required child identity fields"

    if not records and task == "history":
        for page in pages:
            if page["page_type"] != "program_reference":
                page["action"] = "review_thumbnail"
                page["reason"] = "no record page found; inspect candidate once"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Triage vaccine-book images before detailed OCR")
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--task", choices=sorted(TASK_FIELDS), default="history")
    parser.add_argument("--need-age", action="store_true", help="select one page for birth date only")
    parser.add_argument(
        "--need-child-name", action="store_true",
        help="select one page for the child's name only when saving or disambiguating",
    )
    parser.add_argument("--include-manufacturer", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ocr-text-dir", type=Path, help="replay fixture text instead of running OCR")
    parser.add_argument("--tesseract", default="tesseract")
    parser.add_argument("--languages", default="chi_sim+eng")
    parser.add_argument("--psm", type=int, default=11)
    parser.add_argument("--max-edge", type=int, default=1400)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=30)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    missing = [str(path) for path in args.images if not path.is_file()]
    if missing:
        raise SystemExit(f"missing image(s): {', '.join(missing)}")

    started = time.monotonic()
    items = inventory(args.images)
    unique = [item for item in items if item.duplicate_of is None]
    pages: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="vaccine-triage-") as temporary:
        temp_dir = Path(temporary)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            futures = {pool.submit(quick_ocr, item.path, args, temp_dir): item for item in unique}
            for future in concurrent.futures.as_completed(futures):
                item = futures[future]
                try:
                    text, elapsed, engine = future.result()
                except subprocess.TimeoutExpired:
                    text, elapsed, engine = "", float(args.timeout), "timeout"
                page_type, confidence, scores = classify(text)
                pages.append({
                    "file": item.path.name,
                    "path": str(item.path.resolve()),
                    "sha256": item.sha256,
                    "page_type": page_type,
                    "confidence": confidence,
                    "scores": scores,
                    "quick_ocr_engine": engine,
                    "quick_ocr_seconds": round(elapsed, 3),
                    "quick_ocr_text_chars": len(text),
                })

    order = {item.path.name: index for index, item in enumerate(unique)}
    pages.sort(key=lambda page: order[page["file"]])
    choose_pages(pages, args.task, args.need_age, args.need_child_name)
    fields = list(TASK_FIELDS[args.task])
    if args.need_child_name:
        fields.append("child_name")
    if args.need_age:
        fields.append("date_of_birth")
    if args.include_manufacturer:
        fields.append("manufacturer")

    payload = {
        "schema_version": "1.0",
        "task": args.task,
        "required_fields": fields,
        "input_count": len(items),
        "unique_count": len(unique),
        "duplicate_count": len(items) - len(unique),
        "detail_ocr_count": sum(page["action"] == "detail_ocr" for page in pages),
        "review_count": sum(page["action"] == "review_thumbnail" for page in pages),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "pages": pages,
        "duplicates": [
            {"file": item.path.name, "sha256": item.sha256, "duplicate_of": item.duplicate_of}
            for item in items if item.duplicate_of is not None
        ],
        "stop_rule": (
            "Use the first detailed pass on selected pages. Retry only an ambiguous crop once; "
            "after that keep it unknown or request a clearer crop. Do not re-OCR skipped pages."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "input": payload["input_count"],
        "unique": payload["unique_count"],
        "detail_ocr": payload["detail_ocr_count"],
        "review": payload["review_count"],
        "seconds": payload["elapsed_seconds"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
