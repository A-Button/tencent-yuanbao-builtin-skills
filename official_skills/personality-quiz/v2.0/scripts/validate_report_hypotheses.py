#!/usr/bin/env python3
"""Validate a hidden pool of competing divination-report hypotheses."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TOPICS = {
    "personality",
    "career",
    "emotion",
    "family",
    "economy",
    "social",
    "talent",
    "spiritual",
    "study",
    "health",
}
GENERIC = re.compile(r"有机遇也有挑战|机遇与挑战并存|综合来看|总体而言|因人而异|扬长避短|保持平衡|顺其自然")
BANNED = re.compile(
    r"必然|注定|一定会|必定|百分百|一代传奇|开宗立派|商业帝国|财富滚滚|暴富|"
    r"确诊|患有|寿命|死亡时间|心脏|肝脏|肠胃|血压|癌症|疾病|"
    r"录取|考上|事业指数|情感指数|\d+\s*/\s*100|买入|卖出|加仓|减仓"
)
CONSULTANT_TERMS = re.compile(r"交付|复用|边界|闭环|抓手|赋能|方法论|关闭条件|价值兑现|资源配置")
MARKUP = re.compile(r"(?:^|\s)#{1,6}\s|\*\*|```|<\s*/?\s*(?:div|section|article)\b", re.I)
OVERBROAD_PATHS = {"chart", "chart.details", "chart.planets", "chart.aspects"}
ANALYSIS_MODES = {"chart_only", "date_only_stable_facts", "time_range_stable_facts"}


class ValidationError(ValueError):
    pass


def validate_analysis_mode(chart: dict[str, Any], errors: list[str]) -> str:
    mode = chart.get("analysis_mode")
    if mode not in ANALYSIS_MODES:
        errors.append("盘面 analysis_mode 必须是 chart_only、date_only_stable_facts 或 time_range_stable_facts")
        return ""
    chart_payload = chart.get("chart")
    precision = chart_payload.get("precision") if isinstance(chart_payload, dict) else None
    expected = {"date-only": "date_only_stable_facts", "time-range": "time_range_stable_facts"}.get(precision, "chart_only")
    if mode != expected:
        errors.append(f"盘面 analysis_mode 与 precision 不一致：应为 {expected}，当前为 {mode}")
    return mode


def visible_length(value: str) -> int:
    return len(re.sub(r"\s+", "", value))


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValidationError(f"找不到文件：{path}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(f"JSON 解析失败：{path} 第 {exc.lineno} 行第 {exc.colno} 列") from exc


def resolve_path(payload: Any, path: str) -> bool:
    current = payload
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return False
    return True


def require_text(
    value: Any,
    field: str,
    errors: list[str],
    warnings: list[str],
    minimum: int,
    maximum: int,
    decisive: bool = False,
    style_lint: bool = True,
) -> str:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} 必须是非空字符串")
        return ""
    text = value.strip()
    length = visible_length(text)
    if style_lint and not minimum <= length <= maximum:
        warnings.append(f"{field} 建议为 {minimum}—{maximum} 个可见字符，当前为 {length}")
    if "\n" in text or "\r" in text or MARKUP.search(text):
        errors.append(f"{field} 必须是单段纯文本，不得包含 Markdown 或布局 HTML")
    if match := BANNED.search(text):
        target = errors if style_lint else warnings
        target.append(f"{field} 含需结合语义判断的词：{match.group(0)}")
    if decisive and style_lint:
        if match := GENERIC.search(text):
            warnings.append(f"{field} 可能是无辨识度套话：{match.group(0)}")
        if len(CONSULTANT_TERMS.findall(text)) >= 2:
            warnings.append(f"{field} 堆叠咨询式抽象词，建议改成可观察的人格或行为判断")
    return text


def validate_paths(value: Any, field: str, chart: dict[str, Any], errors: list[str]) -> list[str]:
    if not isinstance(value, list) or not value:
        errors.append(f"{field} 必须包含具体盘面信号路径")
        return []
    paths: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{field}.{index} 必须是非空字符串")
            continue
        path = item.strip()
        if path in paths:
            errors.append(f"{field}.{index} 重复：{path}")
        elif path in OVERBROAD_PATHS or not path.startswith("chart."):
            errors.append(f"{field}.{index} 不是具体盘面路径：{path}")
        elif path.startswith("chart.details.luck_cycle_focus"):
            errors.append(
                f"{field}.{index} 引用了大运事实；大运只进入第二阶段 timing，不进入原局候选池：{path}"
            )
        elif chart.get("chart", {}).get("precision") == "date-only" and not path.startswith("chart.stable."):
            errors.append(f"{field}.{index} 引用了日期级初盘的不稳定字段；只能引用 chart.stable.*：{path}")
        elif (chart.get("chart", {}).get("precision") == "time-range"
              and not chart.get("chart", {}).get("pillars")
              and not path.startswith("chart.stable.")):
            errors.append(f"{field}.{index} 引用了时段范围盘的不稳定字段；只能引用 chart.stable.*：{path}")
        elif not resolve_path(chart, path):
            errors.append(f"{field}.{index} 在盘面中不存在：{path}")
        elif chart.get("chart_system") == "western" and not re.fullmatch(
            r"chart\.(?:planets\.(?:sun|moon|venus|mercury)\.sign|ascendant\.sign|stable\.ascendant\.sign|stable\.planet_signs\.(?:sun|moon|venus|mercury))", path
        ):
            errors.append(f"{field}.{index} 西占深报只引用太阳、上升、月亮、金星、水星的已确定星座：{path}")
        elif chart.get("chart_system") == "western" and not _valid_western_sign(chart, path):
            errors.append(f"{field}.{index} 不是已确定的星座：{path}")
        else:
            paths.append(path)
    return paths


def _valid_western_sign(chart: dict[str, Any], path: str) -> bool:
    from western_profile import normalize_sign
    value = chart
    for key in path.split("."):
        value = value[key]
    return normalize_sign(value) is not None


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise ValidationError(f"输出文件已存在：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_name, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def validate(payload: Any, chart: Any, expected_topics: list[str]) -> tuple[list[str], list[str], dict[str, Any]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(payload, dict) or not isinstance(chart, dict):
        return ["假设稿和盘面顶层都必须是对象"], [], {}
    validate_analysis_mode(chart, errors)
    allowed_top = {"schema_version", "chart_system", "primary_topics", "candidates", "selected_ids"}
    extras = sorted(set(payload) - allowed_top)
    if extras:
        errors.append("假设稿包含未允许字段：" + "、".join(extras))
    flexible = payload.get("schema_version") == "3.0.0"
    if payload.get("schema_version") not in {"2.0.0", "3.0.0"}:
        errors.append("schema_version 必须是 2.0.0 或 3.0.0")
    if payload.get("chart_system") != chart.get("chart_system"):
        errors.append("假设稿与盘面体系不一致")
    if payload.get("primary_topics") != expected_topics:
        errors.append(f"primary_topics 必须与用户主题及顺序一致：{expected_topics}")

    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        errors.append("candidates 必须是候选判断数组")
        candidates = []
    elif not flexible:
        recommended_min = max(8, len(expected_topics) * 2 + 2)
        recommended_max = max(12, recommended_min)
        if not recommended_min <= len(candidates) <= recommended_max:
            warnings.append(
                f"candidates 建议包含 {recommended_min}—{recommended_max} 个互相竞争的候选判断，"
                f"当前为 {len(candidates)} 个"
            )
    seen_ids: set[str] = set()
    by_id: dict[str, dict[str, Any]] = {}
    for index, candidate in enumerate(candidates):
        field = f"candidates.{index}"
        if not isinstance(candidate, dict):
            errors.append(f"{field} 必须是对象")
            continue
        allowed = {"id", "topic", "claim", "manifestation", "cost_or_contrast", "signal_paths"}
        candidate_extras = sorted(set(candidate) - allowed)
        if candidate_extras:
            errors.append(f"{field} 包含未允许字段：{'、'.join(candidate_extras)}")
        candidate_id = candidate.get("id")
        if not isinstance(candidate_id, str) or not re.fullmatch(r"h[1-9][0-9]*", candidate_id):
            errors.append(f"{field}.id 必须使用 h1、h2…格式")
            continue
        if candidate_id in seen_ids:
            errors.append(f"{field}.id 重复：{candidate_id}")
        seen_ids.add(candidate_id)
        by_id[candidate_id] = candidate
        topic = candidate.get("topic")
        if topic not in TOPICS or (topic != "personality" and topic not in expected_topics):
            errors.append(f"{field}.topic 必须是 personality 或用户已选主题")
        require_text(candidate.get("claim"), f"{field}.claim", errors, warnings, 14, 100, decisive=True, style_lint=not flexible)
        if not flexible or "manifestation" in candidate:
            require_text(candidate.get("manifestation"), f"{field}.manifestation", errors, warnings, 32, 180, style_lint=not flexible)
        contrast = candidate.get("cost_or_contrast")
        if contrast is not None:
            require_text(contrast, f"{field}.cost_or_contrast", errors, warnings, 20, 140, style_lint=not flexible)
        validate_paths(candidate.get("signal_paths"), f"{field}.signal_paths", chart, errors)

    selected_ids = payload.get("selected_ids")
    if flexible:
        if (not isinstance(selected_ids, list) or not selected_ids
                or any(not isinstance(item, str) for item in selected_ids)
                or len(selected_ids) != len(set(selected_ids))):
            errors.append("selected_ids 必须是非空、不重复的候选 ID 数组")
            selected_ids = []
        selected_topics = []
        for candidate_id in selected_ids:
            candidate = by_id.get(candidate_id)
            if not candidate:
                errors.append(f"selected_ids 引用了不存在的候选：{candidate_id}")
            else:
                selected_topics.append(candidate.get("topic"))
        for topic in expected_topics:
            if topic not in selected_topics:
                errors.append(f"入选判断未覆盖用户主题：{topic}")
        return errors, warnings, {
            "candidate_count": len(candidates), "selected_count": len(selected_ids),
            "selected_topics": selected_topics,
        }
    if len(expected_topics) <= 2:
        selected_min, selected_max = 3, 5
    else:
        selected_min = selected_max = len(expected_topics) + 1
    if (
        not isinstance(selected_ids, list)
        or not selected_min <= len(selected_ids) <= selected_max
        or len(selected_ids) != len(set(selected_ids))
    ):
        if selected_min == selected_max:
            errors.append(f"selected_ids 必须包含 {selected_min} 个不重复候选，覆盖 personality 和全部主题")
        else:
            errors.append(f"selected_ids 必须包含 {selected_min}—{selected_max} 个不重复候选")
        selected_ids = []
    selected_topics: list[str] = []
    for candidate_id in selected_ids:
        candidate = by_id.get(candidate_id)
        if not candidate:
            errors.append(f"selected_ids 引用了不存在的候选：{candidate_id}")
            continue
        selected_topics.append(str(candidate.get("topic")))
    if len(expected_topics) == 1:
        if selected_ids and selected_topics.count("personality") not in {1, 2}:
            errors.append("单主题报告应选择 1—2 条 personality")
        topic = expected_topics[0]
        if selected_ids and not 2 <= selected_topics.count(topic) <= 3:
            errors.append(f"单主题报告应为用户主题 {topic} 选择 2—3 条判断")
    elif len(expected_topics) == 2:
        if selected_ids and selected_topics.count("personality") != 1:
            errors.append("双主题报告只保留 1 条最相关的 personality 判断")
        for topic in expected_topics:
            if selected_ids and not 1 <= selected_topics.count(topic) <= 2:
                errors.append(f"双主题报告应为用户主题 {topic} 选择 1—2 条判断")
    else:
        if selected_ids and selected_topics.count("personality") != 1:
            errors.append("多主题报告只保留 1 条最相关的 personality 判断")
        for topic in expected_topics:
            if selected_ids and selected_topics.count(topic) != 1:
                errors.append(f"多主题报告应为用户主题 {topic} 选择 1 条判断")

    metrics = {
        "candidate_count": len(candidates),
        "selected_count": len(selected_ids),
        "selected_topics": selected_topics,
    }
    return errors, warnings, metrics


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate competing report hypotheses.")
    parser.add_argument("hypotheses", type=Path)
    parser.add_argument("--chart", required=True, type=Path)
    parser.add_argument("--topic", choices=sorted(TOPICS - {"personality"}), action="append", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--strict", action="store_true", help="把候选篇幅和文风建议也作为阻断错误；仅用于离线验证")
    args = parser.parse_args()
    try:
        topics = list(dict.fromkeys(args.topic))
        if not 1 <= len(topics) <= len(TOPICS - {"personality"}):
            raise ValidationError("--topic 必须包含至少一个且不超过全部可用主题")
        hypotheses = load_json(args.hypotheses)
        chart = load_json(args.chart)
        errors, warnings, metrics = validate(hypotheses, chart, topics)
        if args.strict and warnings:
            errors.extend(warnings)
        if errors:
            print(json.dumps({"ok": False, "error": "E_REPORT_HYPOTHESES", "details": errors, "warnings": warnings, "metrics": metrics}, ensure_ascii=False, indent=2))
            return 2
        validated = {
            **hypotheses,
            "validation": {
                "status": "pass",
                "validated_at": datetime.now(timezone.utc).isoformat(),
                "analysis_mode": chart["analysis_mode"],
                "warnings": warnings,
            },
        }
        atomic_write(args.output, validated)
        print(json.dumps({"ok": True, "output": str(args.output), "warnings": warnings, "metrics": metrics}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": "E_REPORT_HYPOTHESES_RUNTIME", "message": str(exc)}, ensure_ascii=False, indent=2))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
