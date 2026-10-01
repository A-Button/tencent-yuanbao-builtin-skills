#!/usr/bin/env python3
"""Persist the handoff from an already displayed chart to an optional report.

This does not display UI or call a host tool. `delivered` / `presented` are
acknowledgements the host sends ONLY after the respective display succeeds.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

from engine_common import atomic_write_json

SCRIPT = Path(__file__).resolve()


def command(path: Path, event: str) -> list[str]:
    return [sys.executable, str(SCRIPT), str(path), event]


def create(chart_dir: Path, artifacts: dict, action: dict, *, omit_luck_cycle: bool = False) -> Path:
    path = chart_dir.resolve() / "post-chart.json"
    files = [artifacts["html"], *artifacts["charts"].values()]
    state = {"schema_version": "1.0.0", "id": str(uuid.uuid4()), "phase": "generated",
             "action": action, "artifacts": artifacts, "omit_luck_cycle": omit_luck_cycle,
             "fingerprints": {str(Path(p).resolve()): hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files}}
    atomic_write_json(path, state)
    return path


def save(path: Path, state: dict) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".post-chart-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def verify_sources(path: Path, state: dict) -> None:
    if state.get("schema_version") != "1.0.0":
        raise ValueError("盘后状态版本无效。")
    for filename, digest in state["fingerprints"].items():
        source = Path(filename)
        if source.is_symlink() or source.resolve().parent != path.parent or not source.is_file():
            raise ValueError("原盘路径发生变化，请使用对应的原始任务。")
        if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            raise ValueError("原盘已改变，不能续接旧报告选择。")
    referenced = [state["artifacts"]["html"], *state["artifacts"]["charts"].values()]
    if set(map(str, referenced)) != set(state["fingerprints"]):
        raise ValueError("原盘引用与冻结文件不一致。")


def report_contract(directory: Path) -> dict:
    """Resume deterministic report stages without repeating preparation."""
    import report_pipeline as pipeline
    directory = directory.resolve()
    config = pipeline.load_config(directory, stage="resume")
    if (directory / pipeline.HTML_NAME).is_file():
        return {"ok": True, "stage": "complete", "next_action": "display_html",
                "html": str(directory / pipeline.HTML_NAME), "markdown": str(directory / pipeline.REPORT_NAME)}
    if (directory / pipeline.VALIDATED_HYPOTHESES_NAME).is_file():
        return {"ok": True, "stage": "content_required", "report_dir": str(directory),
                "validated_hypotheses": str(directory / pipeline.VALIDATED_HYPOTHESES_NAME),
                "next_input": str(directory / pipeline.CONTENT_NAME),
                **pipeline.generation_contract("content", config, directory)}
    return {"ok": True, "stage": "hypotheses_required", "report_dir": str(directory),
            "analysis_chart": str(directory / pipeline.ANALYSIS_NAME),
            "next_input": str(directory / pipeline.HYPOTHESES_NAME),
            **pipeline.generation_contract("hypotheses", config, directory)}


def prepare_reports(path: Path, state: dict, topics: list[str]) -> None:
    import report_pipeline as pipeline
    # Save the selection first. A retry after an interrupted preparation uses
    # the same topics and directories, and never recalculates the birth chart.
    state.update(phase="preparing_report", topics=topics)
    save(path, state)
    reports = {}
    for system, source in state["artifacts"]["charts"].items():
        directory = path.parent / f"report-{system}"
        if directory.exists():
            config = pipeline.load_config(directory, stage="resume")
            if config["chart_system"] != system or config["topics"] != topics:
                raise ValueError("报告目录已被其他主题使用，请新建报告修订。")
        else:
            pipeline.prepare(argparse.Namespace(chart=Path(source), report_dir=directory,
                topic=topics, layout="desktop", current_luck_cycle=False,
                omit_luck_cycle=state.get("omit_luck_cycle", False)))
        reports[system] = str(directory)
    state.update(phase="report_ready", reports=reports)
    save(path, state)


def response(path: Path, state: dict) -> dict:
    result = {"ok": True, "phase": state["phase"], "session": str(path),
              "resume_command": command(path, "resume")}
    phase = state["phase"]
    if phase == "generated":
        return {**result, "next_action": "display_chart", "html": state["artifacts"]["html"],
                "after_success_command": command(path, "delivered")}
    if phase in {"awaiting_topics", "waiting_answer"}:
        action = state["action"]
        return {**result, "next_action": "ask_report_topics" if phase == "awaiting_topics" else "wait_report_topics",
                "question": {**action["question"], "id": state["id"]},
                "tool_policy": {"preferred_tool": "ask-user-question", "required_when_available": True,
                                "capability": "optional_multi_select", "fallback": "single_free_text_question",
                                "instruction": "使用宿主真实提问工具；标题引导填写多个主题，选项保留可选主题与不清楚 / 不想说，自由输入可补充。支持多选就使用多选；工具不可用才用普通消息。跳过不视为选择全部。"},
                "on_presented_command": command(path, "presented"),
                "on_answer_command": command(path, "select"),
                "on_skip_command": command(path, "skip")}
    if phase == "needs_topic_mapping":
        return {**result, "next_action": "map_known_report_topics", "question": state["action"].get("question"),
                "instruction": "用户已明确要报告；从已有问题映射主题 ID，不再询问是否需要。",
                "on_answer_command": command(path, "select")}
    if phase == "preparing_report":
        return {**result, "next_action": "resume_report_preparation", "next_command": command(path, "resume")}
    if phase == "report_ready":
        user_question = state.get("user_question") or state["action"].get("question")
        return {**result, "next_action": "continue_reports",
                "user_question": user_question,
                "reports": {system: {**report_contract(Path(folder)), "user_question": user_question}
                            for system, folder in state["reports"].items()}}
    if phase == "analysis_ready":
        return {**result, **state["action"], "analysis_charts": state["artifacts"]["analysis_charts"]}
    return {**result, "next_action": "done"}


def advance(path: Path, event: str, topics: list[str] | None = None,
            *, omit_luck_cycle: bool | None = None, question: str | None = None) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError("缺少对应的盘后状态文件。")
    path = path.resolve()
    lock_path = path.with_suffix(".lock")
    if lock_path.is_symlink():
        raise ValueError("盘后状态锁不能是符号链接。")
    with lock_path.open("a+") as lock:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        state = json.loads(path.read_text(encoding="utf-8"))
        verify_sources(path, state)
        phase = state["phase"]
        if event == "delivered" and phase == "generated":
            action = state["action"]
            next_action = action["next_action"]
            phase = {"done": "done", "read_analysis_charts": "analysis_ready", "prepare_report": "needs_topic_mapping",
                     "ask_report_topics": "awaiting_topics"}[next_action]
            state["phase"] = phase
            save(path, state)
            if next_action == "prepare_report" and action.get("topics"):
                prepare_reports(path, state, action["topics"])
        elif event == "presented":
            if phase not in {"awaiting_topics", "waiting_answer"}:
                raise ValueError("只有盘面展示后的主题入口可以记录提问。")
            state["phase"] = "waiting_answer"
            save(path, state)
        elif event == "select":
            from chart_quick import TOPICS
            selected = list(dict.fromkeys(topics or []))
            if not selected or any(topic not in TOPICS for topic in selected):
                raise ValueError("请选择至少一个有效主题；明确跳过请使用 skip。")
            if phase in {"report_ready", "preparing_report"}:
                if selected != state.get("topics"):
                    raise ValueError("已开始的报告不能改换主题；请另建报告修订。")
                if omit_luck_cycle is not None and omit_luck_cycle != state.get("omit_luck_cycle", False):
                    raise ValueError("已开始的报告不能改换大运选项；请另建报告修订。")
            elif phase not in {"awaiting_topics", "waiting_answer", "needs_topic_mapping"}:
                raise ValueError("盘面尚未展示或本次已结束，不能提前启动报告。")
            elif omit_luck_cycle is not None:
                state["omit_luck_cycle"] = omit_luck_cycle
            if question is not None:
                if not question.strip():
                    raise ValueError("--question 必须是非空的用户原问题。")
                if phase in {"report_ready", "preparing_report"} and question.strip() != state.get("user_question"):
                    raise ValueError("已开始的报告不能改换用户问题；请另建报告修订。")
                state["user_question"] = question.strip()
            if phase != "report_ready":
                prepare_reports(path, state, selected)
        elif event == "skip":
            if phase not in {"awaiting_topics", "waiting_answer", "needs_topic_mapping", "skipped"}:
                raise ValueError("当前阶段不是可跳过的主题入口。")
            state["phase"] = "skipped"
            save(path, state)
        elif event == "resume" and phase == "preparing_report":
            prepare_reports(path, state, state["topics"])
        elif event not in {"resume", "delivered"}:
            raise ValueError("未知的盘后动作。")
        return response(path, state)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path)
    parser.add_argument("event", choices=("delivered", "presented", "select", "skip", "resume"))
    parser.add_argument("--topic", action="append", default=[])
    parser.add_argument("--question", help="用户在盘后提出的具体问题；仅随 select 传入")
    parser.add_argument("--omit-luck-cycle", action="store_true", default=None,
                        help="仅在用户明确拒绝大运模块时，随 select 提交")
    args = parser.parse_args()
    try:
        if (args.omit_luck_cycle is not None or args.question is not None) and args.event != "select":
            raise ValueError("--omit-luck-cycle 和 --question 仅用于选择报告主题时。")
        result = advance(args.session, args.event, args.topic,
                         omit_luck_cycle=args.omit_luck_cycle, question=args.question)
    except (ValueError, OSError, KeyError) as exc:
        print(json.dumps({"ok": False, "next_action": "stop", "error": "E_CHART_FOLLOWUP", "message": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
