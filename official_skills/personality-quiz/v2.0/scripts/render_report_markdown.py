#!/usr/bin/env python3
"""Deterministically assemble portable Markdown from validated report copy."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


SYSTEMS = {
    "bazi": {"title": "生辰八字", "overview": "整体解读", "patterns": "性格与做事方式"},
    "western": {"title": "天体星座", "overview": "整体解读", "patterns": "表达与互动方式"},
}
TOPIC_HEADINGS = {
    "career": "事业发展", "emotion": "情感婚恋", "family": "家庭亲情", "economy": "经济状况",
    "social": "社会关系", "talent": "天赋挖掘", "spiritual": "精神成长", "study": "学业考试", "health": "身体健康",
}
DISCLAIMER = "AI生成内容｜传统文化与自我反思，仅供参考，不是经科学验证的预测，也不构成医疗、法律、投资或其他专业建议。"
DAYUN_DATE_ONLY_BOUNDARY = "缺少出生时间，暂时无法确定起运日期和当前大运。其余分析使用已确定的原局信息。"
DAYUN_UNAVAILABLE_BOUNDARY = (
    "当前盘面没有可用的大运信息，暂不作阶段分析。"
)
DAYUN_TIME_BASIS_BOUNDARY = (
    "当前计算方式暂不支持此地的大运推算，本次不作阶段分析。"
)


class RenderError(ValueError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RenderError(f"找不到文件：{path}") from exc
    except json.JSONDecodeError as exc:
        raise RenderError(f"JSON 解析失败：第 {exc.lineno} 行第 {exc.colno} 列") from exc
    if not isinstance(payload, dict):
        raise RenderError("输入顶层必须是对象")
    if payload.get("validation", {}).get("status") != "pass":
        raise RenderError("只能渲染通过 validate_report_content.py 的文件")
    return payload


def sentence(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RenderError("报告字段缺失或不是字符串")
    text = " ".join(value.strip().split())
    if not text.endswith(("。", "！", "？", ".", "!", "?", "；")):
        text += "。"
    return text


def render_paragraph(value: Any, *, flexible: bool = False) -> str:
    if not isinstance(value, dict):
        raise RenderError("段落必须是对象")
    text = sentence(value.get("text"))
    highlights = value.get("highlights", [])
    if not isinstance(highlights, list) or (not flexible and len(highlights) > 1):
        raise RenderError("每段只能有零至一个重点")
    spans: list[tuple[int, int]] = []
    for highlight in highlights:
        if not isinstance(highlight, str) or text.count(highlight) != 1:
            raise RenderError("重点必须在段落中恰好出现一次")
        start = text.index(highlight)
        end = start + len(highlight)
        if any(start < previous_end and end > previous_start for previous_start, previous_end in spans):
            raise RenderError("重点不得重叠")
        spans.append((start, end))
    for start, end in sorted(spans, reverse=True):
        text = text[:start] + "**" + text[start:end] + "**" + text[end:]
    return text


def extend_paragraphs(blocks: list[str], values: Any) -> None:
    if not isinstance(values, list):
        raise RenderError("paragraphs 必须是数组")
    blocks.extend(render_paragraph(value) for value in values)


def render_dayun(blocks: list[str], payload: dict[str, Any]) -> None:
    context = payload.get("luck_cycle_context")
    if not isinstance(context, dict):
        raise RenderError("luck_cycle_context 必须是对象")
    if set(context) - {"status", "reason"}:
        raise RenderError("luck_cycle_context 包含未允许字段")
    status = context.get("status")
    timing = payload.get("timing")
    expected_context_keys = (
        {"status", "reason"} if status == "unavailable" else {"status"}
    )
    if set(context) != expected_context_keys:
        raise RenderError("luck_cycle_context 字段不符合状态契约")
    if status in {"available", "conditional"}:
        if not isinstance(timing, dict) or set(timing) != {"paragraphs", "signal_paths"}:
            raise RenderError(f"{status} 大运状态必须包含已校验的 timing")
        reference_date = payload.get("validation", {}).get("luck_cycle_reference_date")
        if not isinstance(reference_date, str) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}", reference_date
        ):
            raise RenderError("已校验报告缺少确定性的阶段参考日")
        try:
            datetime.strptime(reference_date, "%Y-%m-%d")
        except ValueError as exc:
            raise RenderError("阶段参考日无效") from exc
        blocks.append("## 大运与阶段分析")
        blocks.append(f"阶段参考日：{reference_date}")
        extend_paragraphs(blocks, timing["paragraphs"])
    elif status == "unavailable":
        if timing is not None:
            raise RenderError("unavailable 大运状态不得包含 timing")
        blocks.append("## 大运与阶段分析")
        reason = context.get("reason")
        if reason == "date_only":
            boundary = DAYUN_DATE_ONLY_BOUNDARY
        elif reason == "time_range":
            boundary = "本次按出生时辰核验四柱。缺少具体分钟，暂不判断起运日期和当前大运；其余分析使用已确定的原局信息。"
        elif reason == "unsupported_time_basis":
            boundary = DAYUN_TIME_BASIS_BOUNDARY
        else:
            boundary = DAYUN_UNAVAILABLE_BOUNDARY
        blocks.append(boundary)
    elif status in {"excluded", "not_applicable"}:
        if timing is not None:
            raise RenderError(f"{status} 大运状态不得包含 timing")
    else:
        raise RenderError("luck_cycle_context.status 无效")


def build_markdown(payload: dict[str, Any]) -> str:
    system = payload.get("chart_system")
    if system not in SYSTEMS:
        raise RenderError("chart_system 必须是 bazi 或 western")
    labels = SYSTEMS[system]
    if payload.get("schema_version") == "5.0.0":
        blocks = ["# " + payload.get("title", labels["title"])]
        reference_shown = False
        for section in payload["sections"]:
            if section.get("title"):
                blocks.append("## " + section["title"])
            if "signal_paths" in section and not reference_shown:
                reference_date = payload.get("validation", {}).get("luck_cycle_reference_date")
                if not isinstance(reference_date, str):
                    raise RenderError("已校验报告缺少阶段参考日")
                datetime.strptime(reference_date, "%Y-%m-%d")
                blocks.append(f"阶段参考日：{reference_date}")
                reference_shown = True
            blocks.extend(render_paragraph(value, flexible=True) for value in section["paragraphs"])
        if payload["luck_cycle_context"]["status"] == "unavailable":
            boundary: list[str] = []
            render_dayun(boundary, payload)
            blocks.extend(boundary[1:])  # A brief boundary, without an empty fixed chapter.
        blocks.append(DISCLAIMER)
        return "\n\n".join(blocks).rstrip() + "\n"
    insights = payload["insights"]
    blocks = [f"# {labels['title']}", f"## {labels['overview']}"]
    extend_paragraphs(blocks, payload["overview"]["paragraphs"])
    blocks.append(f"## {labels['patterns']}")
    for item in [entry for entry in insights if entry["topic"] == "personality"]:
        extend_paragraphs(blocks, item["paragraphs"])
    render_dayun(blocks, payload)
    blocks.append("## 关注主题")
    for topic_id in payload["primary_topics"]:
        if topic_id not in TOPIC_HEADINGS:
            raise RenderError(f"未知主题：{topic_id}")
        blocks.append(f"### {TOPIC_HEADINGS[topic_id]}")
        for item in [entry for entry in insights if entry["topic"] == topic_id]:
            extend_paragraphs(blocks, item["paragraphs"])
    blocks.append("## 观察与建议")
    blocks.append("\n".join(f"{index}. {sentence(item)}" for index, item in enumerate(payload["takeaways"], start=1)))
    blocks.append(DISCLAIMER)
    return "\n\n".join(blocks).rstrip() + "\n"


def atomic_write(path: Path, content: str) -> None:
    if path.exists():
        raise RenderError(f"输出文件已存在：{path}")
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Render validated report copy to Markdown.")
    parser.add_argument("content", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        content = build_markdown(load_json(args.content))
        atomic_write(args.output, content)
        print(json.dumps({"ok": True, "output": str(args.output)}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": "E_REPORT_RENDER", "message": str(exc)}, ensure_ascii=False, indent=2))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
