#!/usr/bin/env python3
"""Run the deterministic parts of the two-stage report workflow."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import delivery
from bazi_dayun_facts import UNAVAILABLE_REASONS
from render_report_markdown import TOPIC_HEADINGS


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
CONFIG_NAME = "report-pipeline.json"
ANALYSIS_NAME = "analysis-chart.json"
HYPOTHESES_NAME = "report-hypotheses.json"
VALIDATED_HYPOTHESES_NAME = "report-hypotheses.validated.json"
CONTENT_NAME = "report-content.json"
VALIDATED_CONTENT_NAME = "report-content.validated.json"
REPORT_NAME = "report.md"
HTML_NAME = "report.html"
CONFIG_KEYS = {"schema_version", "chart_system", "topics", "layout", "luck_cycle"}
# The report page is delivered; its de-identified inputs stay in the report dir.
REPORT_STEMS = {"bazi": "八字深度报告", "western": "西洋占星深度报告"}
MODEL_CONTENT_KEYS = {"overview", "insights", "timing", "takeaways"}
MODEL_INSIGHT_KEYS = {"hypothesis_id", "paragraphs"}


def generation_contract(stage: str, config: dict[str, Any], report_dir: Path) -> dict[str, Any]:
    """Expose only the next semantic stage; do not make callers infer the workflow."""
    if stage == "hypotheses":
        return {
            "next_action": "generate_hypotheses",
            "next_references": [str(ROOT / "references" / name) for name in (
                f"{config['chart_system']}-report.md", "report-hypotheses.md",
            )],
            "chart_system": config["chart_system"],
            "primary_topics": config["topics"],
            "next_command": [sys.executable, str(SCRIPT_DIR / "report_pipeline.py"),
                             "validate-hypotheses", str(report_dir)],
        }
    status = config["luck_cycle"]["status"]
    timing = {"status": status, "required": status in {"available", "conditional"}}
    if status == "available":
        timing["instruction"] = (
            "timing 解释脚本选定的当前大运与原局互动；signal_paths 至少引用一条 "
            "luck_cycle_focus 派生事实和一条原局事实，不叠加流年。"
        )
    elif status == "conditional":
        timing["instruction"] = (
            "timing 对 option_a 与 option_b 两条匿名条件等量并列，不选边；"
            "signal_paths 引用两条分支及至少一条原局事实，不显示性别或顺逆依据。"
        )
    else:
        timing["instruction"] = "省略 timing；固定不可用说明或章节省略由渲染器处理。"
    if timing["required"]:
        timing["analysis_chart"] = str(report_dir / ANALYSIS_NAME)
    return {
        "next_action": "generate_content",
        "next_references": [str(ROOT / "references" / "report-content.md")],
        "timing_contract": timing,
        "next_command": [sys.executable, str(SCRIPT_DIR / "report_pipeline.py"),
                         "finalize", str(report_dir)],
    }


class PipelineError(ValueError):
    def __init__(self, message: str, *, stage: str, details: Any | None = None):
        super().__init__(message)
        self.stage = stage
        self.details = details


def load_json(path: Path, *, stage: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(f"找不到文件：{path}", stage=stage) from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(
            f"JSON 解析失败：{path} 第 {exc.lineno} 行第 {exc.colno} 列",
            stage=stage,
        ) from exc


def write_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.chmod(path, 0o600)


def parse_child_output(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = {
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    return payload if isinstance(payload, dict) else {"result": payload}


def run_script(stage: str, script: str, *arguments: object) -> dict[str, Any]:
    command = [sys.executable, str(SCRIPT_DIR / script), *(str(item) for item in arguments)]
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    payload = parse_child_output(result)
    if result.returncode != 0 or payload.get("ok") is not True:
        raise PipelineError(
            f"{script} 未通过",
            stage=stage,
            details=payload,
        )
    return payload


def normalize_report_dir(value: Path, *, must_exist: bool, stage: str) -> Path:
    path = value.expanduser().resolve()
    if must_exist:
        if not path.is_dir() or path.is_symlink():
            raise PipelineError(f"报告目录不存在或不是普通目录：{path}", stage=stage)
    elif path.exists() or path.is_symlink():
        raise PipelineError(f"报告目录必须是尚不存在的新目录：{path}", stage=stage)
    return path


def local_file(report_dir: Path, name: str, *, required: bool, stage: str) -> Path:
    path = report_dir / name
    if required:
        if not path.is_file() or path.is_symlink():
            raise PipelineError(f"缺少本阶段输入：{path}", stage=stage)
    elif path.exists() or path.is_symlink():
        raise PipelineError(f"本阶段输出已存在，拒绝覆盖：{path}", stage=stage)
    return path


def load_config(report_dir: Path, *, stage: str) -> dict[str, Any]:
    config_path = local_file(report_dir, CONFIG_NAME, required=True, stage=stage)
    config = load_json(config_path, stage=stage)
    if not isinstance(config, dict) or set(config) != CONFIG_KEYS:
        raise PipelineError("report-pipeline.json 不符合固定配置契约", stage=stage)
    if config.get("schema_version") != "1.1.0":
        raise PipelineError("report-pipeline.json schema_version 必须是 1.1.0", stage=stage)
    if config.get("chart_system") not in {"bazi", "western"}:
        raise PipelineError("report-pipeline.json chart_system 无效", stage=stage)
    topics = config.get("topics")
    if (
        not isinstance(topics, list)
        or not topics
        or len(topics) != len(set(topics))
        or any(topic not in TOPIC_HEADINGS for topic in topics)
    ):
        raise PipelineError("report-pipeline.json topics 无效", stage=stage)
    if config.get("layout") not in {"desktop", "mobile"}:
        raise PipelineError("report-pipeline.json layout 无效", stage=stage)
    luck_cycle = config.get("luck_cycle")
    if not isinstance(luck_cycle, dict):
        raise PipelineError("report-pipeline.json luck_cycle 无效", stage=stage)
    if luck_cycle.get("status") not in {
        "available",
        "conditional",
        "unavailable",
        "excluded",
        "not_applicable",
    }:
        raise PipelineError("report-pipeline.json luck_cycle.status 无效", stage=stage)
    if set(luck_cycle) - {"status", "reason"}:
        raise PipelineError("report-pipeline.json luck_cycle 含未允许字段", stage=stage)
    reason = luck_cycle.get("reason")
    if reason is not None and not isinstance(reason, str):
        raise PipelineError("report-pipeline.json luck_cycle.reason 无效", stage=stage)
    if luck_cycle["status"] == "unavailable":
        if reason not in UNAVAILABLE_REASONS:
            raise PipelineError("report-pipeline.json luck_cycle.reason 无效", stage=stage)
    elif reason is not None:
        raise PipelineError("仅 unavailable 大运状态可以携带 reason", stage=stage)
    if config["chart_system"] == "western" and luck_cycle["status"] != "not_applicable":
        raise PipelineError("西占报告 luck_cycle 必须是 not_applicable", stage=stage)
    if config["chart_system"] == "bazi" and luck_cycle["status"] == "not_applicable":
        raise PipelineError("八字报告 luck_cycle 不能是 not_applicable", stage=stage)
    return config


def topic_args(topics: list[str]) -> list[str]:
    result: list[str] = []
    for topic in topics:
        result.extend(("--topic", topic))
    return result


def assemble_report_content(
    payload: Any,
    config: dict[str, Any],
    hypotheses: Any,
    *,
    stage: str,
) -> dict[str, Any]:
    """Add deterministic envelope and candidate metadata to model-authored copy."""
    if not isinstance(payload, dict) or not isinstance(hypotheses, dict):
        raise PipelineError("report-content.json 与候选假设顶层必须是对象", stage=stage)
    extras = sorted(set(payload) - MODEL_CONTENT_KEYS)
    if extras:
        raise PipelineError(
            "report-content.json 不要抄写脚本字段，未允许字段：" + "、".join(extras),
            stage=stage,
        )
    selected_ids = hypotheses.get("selected_ids", [])
    candidate_map = {
        candidate.get("id"): candidate
        for candidate in hypotheses.get("candidates", [])
        if isinstance(candidate, dict) and candidate.get("id") in selected_ids
    }
    model_insights = payload.get("insights")
    assembled_insights: Any = model_insights
    if isinstance(model_insights, list):
        assembled_insights = []
        for index, insight in enumerate(model_insights):
            if not isinstance(insight, dict):
                assembled_insights.append(insight)
                continue
            insight_extras = sorted(set(insight) - MODEL_INSIGHT_KEYS)
            if insight_extras:
                raise PipelineError(
                    f"report-content.json insights.{index} 不要抄写候选字段，未允许字段："
                    + "、".join(insight_extras),
                    stage=stage,
                )
            candidate = candidate_map.get(insight.get("hypothesis_id"))
            assembled_insights.append(
                {
                    **insight,
                    "topic": candidate.get("topic") if candidate else None,
                }
            )
    return {
        "schema_version": "4.0.0",
        "chart_system": config["chart_system"],
        "primary_topics": config["topics"],
        "luck_cycle_context": config["luck_cycle"],
        **payload,
        "insights": assembled_insights,
    }


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    stage = "prepare"
    source = args.chart.expanduser().resolve()
    if not source.is_file() or source.is_symlink():
        raise PipelineError(f"盘面文件不存在或不是普通文件：{source}", stage=stage)
    report_dir = normalize_report_dir(args.report_dir, must_exist=False, stage=stage)
    report_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{report_dir.name}.", dir=report_dir.parent))
    os.chmod(staging, 0o700)
    try:
        analysis_path = staging / ANALYSIS_NAME
        command: list[object] = [source, "--output", analysis_path, "--western-five"]
        if args.current_luck_cycle and args.omit_luck_cycle:
            raise PipelineError(
                "--current-luck-cycle 与 --omit-luck-cycle 不能同时使用",
                stage=stage,
            )
        if args.current_luck_cycle:
            command.append("--current-luck-cycle")
        elif not args.omit_luck_cycle:
            command.append("--report-luck-cycle")
        run_script(stage, "prepare_analysis_chart.py", *command)
        analysis = load_json(analysis_path, stage=stage)
        chart_system = analysis.get("chart_system") if isinstance(analysis, dict) else None
        if chart_system not in {"bazi", "western"}:
            raise PipelineError("去身份化盘面没有有效 chart_system", stage=stage)
        if chart_system == "western":
            luck_cycle = {"status": "not_applicable"}
        elif args.omit_luck_cycle:
            luck_cycle = {"status": "excluded"}
        else:
            focus = (
                analysis.get("chart", {}).get("details", {}).get("luck_cycle_focus")
                if isinstance(analysis, dict)
                else None
            )
            if not isinstance(focus, dict) or focus.get("status") not in {
                "available",
                "conditional",
                "unavailable",
            }:
                raise PipelineError("报告大运事实层缺少有效状态", stage=stage)
            luck_cycle = {"status": focus["status"]}
            if focus.get("reason") is not None:
                luck_cycle["reason"] = focus["reason"]
        config = {
            "schema_version": "1.1.0",
            "chart_system": chart_system,
            "topics": args.topic,
            "layout": args.layout,
            "luck_cycle": luck_cycle,
        }
        write_json(staging / CONFIG_NAME, config)
        os.replace(staging, report_dir)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return {
        "ok": True,
        "stage": "hypotheses_required",
        "report_dir": str(report_dir),
        "analysis_chart": str(report_dir / ANALYSIS_NAME),
        "next_input": str(report_dir / HYPOTHESES_NAME),
        **generation_contract("hypotheses", config, report_dir),
    }


def validate_hypotheses(args: argparse.Namespace) -> dict[str, Any]:
    stage = "validate-hypotheses"
    report_dir = normalize_report_dir(args.report_dir, must_exist=True, stage=stage)
    config = load_config(report_dir, stage=stage)
    analysis = local_file(report_dir, ANALYSIS_NAME, required=True, stage=stage)
    hypotheses = local_file(report_dir, HYPOTHESES_NAME, required=True, stage=stage)
    output = local_file(report_dir, VALIDATED_HYPOTHESES_NAME, required=False, stage=stage)
    with tempfile.TemporaryDirectory(prefix=".hypotheses.", dir=report_dir) as temporary:
        staged_output = Path(temporary) / VALIDATED_HYPOTHESES_NAME
        result = run_script(
            stage,
            "validate_report_hypotheses.py",
            hypotheses,
            "--chart",
            analysis,
            *topic_args(config["topics"]),
            "--output",
            staged_output,
        )
        os.replace(staged_output, output)
    return {
        "ok": True,
        "stage": "content_required",
        "validated_hypotheses": str(output),
        "warnings": result.get("warnings", []),
        "next_input": str(report_dir / CONTENT_NAME),
        **generation_contract("content", config, report_dir),
    }


def finalize(args: argparse.Namespace) -> dict[str, Any]:
    stage = "finalize"
    report_dir = normalize_report_dir(args.report_dir, must_exist=True, stage=stage)
    config = load_config(report_dir, stage=stage)
    analysis = local_file(report_dir, ANALYSIS_NAME, required=True, stage=stage)
    hypotheses = local_file(report_dir, VALIDATED_HYPOTHESES_NAME, required=True, stage=stage)
    content = local_file(report_dir, CONTENT_NAME, required=True, stage=stage)
    assembled_content = assemble_report_content(
        load_json(content, stage=stage),
        config,
        load_json(hypotheses, stage=stage),
        stage=stage,
    )
    target_names = (VALIDATED_CONTENT_NAME, REPORT_NAME, HTML_NAME)
    targets = {
        name: local_file(report_dir, name, required=False, stage=stage)
        for name in target_names
    }
    with tempfile.TemporaryDirectory(prefix=".finalize.", dir=report_dir) as temporary:
        work = Path(temporary)
        content_validated = work / VALIDATED_CONTENT_NAME
        content_assembled = work / "report-content.assembled.json"
        report = work / REPORT_NAME
        html = work / HTML_NAME
        write_json(content_assembled, assembled_content)
        content_result = run_script(
            stage,
            "validate_report_content.py",
            content_assembled,
            "--chart",
            analysis,
            "--hypotheses",
            hypotheses,
            *topic_args(config["topics"]),
            "--layout",
            config["layout"],
            "--output",
            content_validated,
        )
        run_script(
            stage,
            "render_report_markdown.py",
            content_validated,
            "--output",
            report,
        )
        run_script(
            stage,
            "render_report_html.py",
            report,
            "--output",
            html,
            "--system",
            config["chart_system"],
        )
        for name in target_names:
            os.replace(work / name, targets[name])
    delivered_html = targets[HTML_NAME]
    workspace = delivery.resolve_workspace()
    if workspace is not None:
        delivered_html = delivery.publish(
            targets[HTML_NAME], workspace,
            REPORT_STEMS.get(config["chart_system"], "深度报告"),
        )
    payload = {
        "ok": True,
        "stage": "complete",
        "next_action": "display_html",
        "html": str(delivered_html),
        "markdown": str(targets[REPORT_NAME]),
        "warnings": content_result.get("warnings", []),
    }
    delivery.attach_delivery(
        payload,
        delivered_html,
        REPORT_STEMS.get(config["chart_system"], "深度报告"),
        success_action="display_html",
    )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Orchestrate deterministic report preparation, validation and rendering."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser(
        "prepare", help="Create a fresh report revision and identity-minimized chart."
    )
    prepare_parser.add_argument("chart", type=Path)
    prepare_parser.add_argument("--report-dir", type=Path, required=True)
    prepare_parser.add_argument(
        "--topic", choices=sorted(TOPIC_HEADINGS), action="append", required=True
    )
    prepare_parser.add_argument("--layout", choices=("desktop", "mobile"), default="desktop")
    prepare_parser.add_argument("--current-luck-cycle", action="store_true")
    prepare_parser.add_argument(
        "--omit-luck-cycle",
        action="store_true",
        help="仅在用户明确拒绝大运模块时使用",
    )
    prepare_parser.set_defaults(handler=prepare)

    hypotheses_parser = subparsers.add_parser(
        "validate-hypotheses", help="Validate and freeze the first semantic-stage JSON."
    )
    hypotheses_parser.add_argument("report_dir", type=Path)
    hypotheses_parser.set_defaults(handler=validate_hypotheses)

    finalize_parser = subparsers.add_parser(
        "finalize", help="Validate the second semantic-stage JSON and render final artifacts."
    )
    finalize_parser.add_argument("report_dir", type=Path)
    finalize_parser.set_defaults(handler=finalize)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "prepare":
        args.topic = list(dict.fromkeys(args.topic))
    try:
        payload = args.handler(args)
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    except PipelineError as exc:
        payload: dict[str, Any] = {
            "ok": False,
            "error": "E_REPORT_PIPELINE",
            "stage": exc.stage,
            "message": str(exc),
        }
        if exc.details is not None:
            payload["details"] = exc.details
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "E_REPORT_PIPELINE_RUNTIME",
                    "stage": getattr(args, "command", "unknown"),
                    "message": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
