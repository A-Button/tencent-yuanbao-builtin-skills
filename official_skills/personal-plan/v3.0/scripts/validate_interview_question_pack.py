#!/usr/bin/env python3
"""Validate a structured interview-question pack without network access.

The schema operationalizes the question contract adapted from the MIT-0
jd-interview-prep skill. It deliberately does not call an external LLM or
upload resume/JD content.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REQUIRED_FIELDS = {
    "id",
    "category",
    "competency",
    "difficulty",
    "basis",
    "question",
    "answer_structure",
    "evidence",
    "follow_ups",
    "red_flags",
    "preparation_action",
}

ALLOWED_DIFFICULTIES = {"易", "中", "难"}
CORE_CATEGORIES = {"通用必问", "简历深挖", "专业能力", "差距针对", "行为", "情景"}


def load_questions(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("questions")
    if not isinstance(data, list):
        raise ValueError("顶层必须是数组，或包含 questions 数组的对象")
    if not all(isinstance(item, dict) for item in data):
        raise ValueError("questions 中的每一项都必须是对象")
    return data


def nonempty(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    return value is not None


def validate(questions: list[dict]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if not 6 <= len(questions) <= 18:
        warnings.append(f"题量为 {len(questions)}；常规备战建议为 6—18 题")

    seen_questions: set[str] = set()
    categories: set[str] = set()

    for index, item in enumerate(questions, start=1):
        label = item.get("id") or index
        missing = sorted(REQUIRED_FIELDS - item.keys())
        if missing:
            errors.append(f"题目 {label} 缺少字段：{', '.join(missing)}")
            continue

        empty = sorted(field for field in REQUIRED_FIELDS if not nonempty(item.get(field)))
        if empty:
            errors.append(f"题目 {label} 字段为空：{', '.join(empty)}")

        difficulty = item.get("difficulty")
        if difficulty not in ALLOWED_DIFFICULTIES:
            errors.append(f"题目 {label} difficulty 必须是 易/中/难")

        category = str(item.get("category", "")).strip()
        categories.add(category)
        if category not in CORE_CATEGORIES:
            warnings.append(f"题目 {label} 使用了非标准分类：{category}")

        question = " ".join(str(item.get("question", "")).split()).lower()
        if question in seen_questions:
            errors.append(f"题目 {label} 与前文重复")
        seen_questions.add(question)

        for field in ("follow_ups", "red_flags"):
            if not isinstance(item.get(field), list):
                errors.append(f"题目 {label} 的 {field} 必须是数组")

    if len(categories & CORE_CATEGORIES) < 3:
        warnings.append("题型覆盖少于3类；检查是否过度集中在通用题")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="校验面试题包JSON的字段、题量和题型覆盖")
    parser.add_argument("input", type=Path, help="题包JSON文件")
    args = parser.parse_args()

    try:
        questions = load_questions(args.input)
        errors, warnings = validate(questions)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"校验失败：{exc}", file=sys.stderr)
        return 2

    for warning in warnings:
        print(f"警告：{warning}")
    for error in errors:
        print(f"错误：{error}", file=sys.stderr)

    if errors:
        print(f"结果：不通过，共 {len(errors)} 个错误", file=sys.stderr)
        return 1

    print(f"结果：通过，共 {len(questions)} 道题，{len(warnings)} 个警告")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
