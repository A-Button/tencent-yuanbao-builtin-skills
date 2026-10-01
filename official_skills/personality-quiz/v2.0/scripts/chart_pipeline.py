#!/usr/bin/env python3
"""Run a fresh deterministic chart build from normalized interaction state.

This first pipeline version intentionally supports only ``chart_revision=0`` and
commits a new revision-1 artifact directory atomically.  It does not parse user
language. Common bundled city aliases are resolved locally; misses remain an
internal host-resolution task rather than becoming technical user questions.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import city_timezone_resolver
import render_chart_html
from engine_common import EngineError, atomic_write_json, load_json


PIPELINE_NAME = "personality-quiz-chart-pipeline"
PIPELINE_VERSION = "1.5.0"
STATE_SCHEMA_VERSION = "1.4.0"
MODES = {"bazi", "western", "combined"}
ARTIFACTS = {"chart", "conclusion", "analysis", "report", None}
INLINE_ANALYSIS_ARTIFACTS = {"conclusion", "analysis"}
DATE_ONLY_KINDS = {"approximate", "range", "unknown", "withheld"}
ENGINE_AMBIGUITIES = {
    "E_AMBIGUOUS_LOCAL_TIME": "dst_fold_required",
    "E_NONEXISTENT_LOCAL_TIME": "nonexistent_local_time",
    "E_HISTORICAL_TIMEZONE_OFFSET_REQUIRED": "historical_offset_required",
}

# Keep question planning deterministic once a normalized state reaches this
# pipeline. In particular, schema, filesystem, timezone-dataset, and other
# technical failures must not become requests for internal fields such as IANA
# timezone names or coordinates.
AMBIGUITY_NEXT_ACTIONS = {
    # The pipeline has no trustworthy city candidate list. The host must call
    # its location resolver before it can present any choices to the user.
    "ambiguous_city": "resolve_internally",
    "timezone_unresolved": "ask_text",
    "dst_fold_required": "ask_choice",
    "nonexistent_local_time": "ask_text",
    "xinjiang_clock_required": "ask_choice",
    "historical_offset_required": "degrade",
    "lunar_leap_month_required": "ask_choice",
    "western_requires_gregorian": "resolve_internally",
    "combined_lunar_conversion_required": "resolve_internally",
}

ERROR_NEXT_ACTIONS = {
    # Recoverable implementation/state issues; never ask the user for these
    # field names directly.
    "E_PIPELINE_STATE": "resolve_internally",
    "E_REVISION_UNSUPPORTED": "resolve_internally",
    "E_OUTPUT_EXISTS": "resolve_internally",
    "E_OUTPUT_PATH": "resolve_internally",
    "E_PIPELINE_IO": "resolve_internally",
    "E_INVALID_INPUT": "resolve_internally",
    "E_INVALID_JSON": "resolve_internally",
    "E_FILE_NOT_FOUND": "resolve_internally",
    "E_INVALID_TIMEZONE": "resolve_internally",
    "E_INVALID_LOCATION": "resolve_internally",
    "E_INVALID_HISTORICAL_UTC_OFFSET": "resolve_internally",
    "E_CITY_RESOLUTION_REQUIRED": "resolve_internally",
    # A malformed or impossible lunar date can be corrected only from the
    # user's original calendar input.
    "E_CALENDAR_CONVERSION": "ask_text",
    # A useful lower-precision result remains available for these cases.
    "E_HISTORICAL_TIMEZONE_OFFSET_REQUIRED": "degrade",
    "E_TIME_UNCERTAINTY": "degrade",
    # Known capability limits and unknown failures should fail closed.
    "E_DATE_ONLY_NO_VALID_SAMPLES": "stop",
    "E_EPHEMERIS_RANGE": "stop",
    "E_UNSUPPORTED_SOLAR_TIME": "stop",
    "E_TIME_RANGE_UNSUPPORTED_TIMEZONE": "stop",
    "E_PIPELINE_INTERNAL": "stop",
}

AMBIGUITY_USER_MESSAGES = {
    "ambiguous_city": "出生城市需要由位置服务进一步核对。",
    "timezone_unresolved": "请补充出生城市所在的国家或省州。",
    "dst_fold_required": "这个当地时间当天出现过两次，请选择出生记录对应较早的一次还是较晚的一次。",
    "nonexistent_local_time": "这个当地时间在当地时钟调整中不存在；请核对出生时间，或选择按日期生成初盘。",
    "xinjiang_clock_required": "请确认出生记录使用北京时间还是新疆时间。",
    "historical_offset_required": "当前缺少可核验的历史时间资料，将省略受影响的盘面部分。",
    "lunar_leap_month_required": "请确认该农历月份是否为闰月。",
    "western_requires_gregorian": "正在转换为该体系所需的历法日期。",
    "combined_lunar_conversion_required": "正在转换组合排盘所需的历法日期。",
}

ERROR_USER_MESSAGES = {
    "E_CITY_RESOLUTION_REQUIRED": "出生城市需要由位置服务进一步核对。",
    "E_CALENDAR_CONVERSION": "这个农历日期无法确认，请核对日期以及是否为闰月。",
    "E_HISTORICAL_TIMEZONE_OFFSET_REQUIRED": "当前缺少可核验的历史时间资料，将省略受影响的盘面部分。",
    "E_TIME_UNCERTAINTY": "出生时间不足以生成精确盘面，将改为按日期生成初盘。",
    "E_DATE_ONLY_NO_VALID_SAMPLES": "当前日期无法生成可靠盘面，本次已停止。",
    "E_EPHEMERIS_RANGE": "出生日期超出当前西洋星盘引擎的支持范围，本次无法生成该盘面。",
    "E_UNSUPPORTED_SOLAR_TIME": "当前排盘方式不支持所请求的时间校正口径。",
    "E_TIME_RANGE_UNSUPPORTED_TIMEZONE": "已识别所给时段，但该范围涉及当前不支持的地区钟制或时钟跳变，本次未生成范围盘，也没有扩大为日期级计算。",
    "E_PIPELINE_INTERNAL": "排盘未能安全完成，本次已停止；没有生成可交付结果。",
}

DEFAULT_RECOVERABLE_MESSAGE = "排盘准备数据需要内部重新解析，本次不会要求你填写技术字段。"
DEFAULT_STOP_MESSAGE = "排盘未能安全完成，本次已停止；没有生成可交付结果。"

AMBIGUITY_DEGRADE_TARGETS = {
    "historical_offset_required": "omit-affected-system",
}

ERROR_DEGRADE_TARGETS = {
    "E_TIME_UNCERTAINTY": "date-only",
    "E_HISTORICAL_TIMEZONE_OFFSET_REQUIRED": "omit-affected-system",
}


class PipelineError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        fields: list[str] | None = None,
        ambiguity_code: str | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.fields = fields or []
        self.ambiguity_code = ambiguity_code


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PipelineError("E_PIPELINE_STATE", f"{field} 必须是对象。", [field])
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PipelineError("E_PIPELINE_STATE", f"{field} 必须是非空字符串。", [field])
    return value.strip()


def _calendar(intake: dict[str, Any]) -> str:
    calendar = intake.get("calendar") or "gregorian"
    if calendar not in {"gregorian", "lunar"}:
        raise PipelineError(
            "E_PIPELINE_STATE",
            "intake.calendar 必须是 gregorian 或 lunar。",
            ["intake.calendar"],
        )
    return calendar


def _precision(intake: dict[str, Any], resolved: dict[str, Any]) -> str:
    declared = resolved.get("chart_precision")
    if declared not in {None, "exact", "date-only", "time-range"}:
        raise PipelineError(
            "E_PIPELINE_STATE",
            "resolved.chart_precision 必须是 exact、date-only、time-range 或 null。",
            ["resolved.chart_precision"],
        )

    accuracy = intake.get("time_accuracy")
    birth_time = intake.get("birth_time")
    time_prompted = intake.get("time_prompted")
    if not isinstance(time_prompted, bool):
        raise PipelineError(
            "E_PIPELINE_STATE",
            "intake.time_prompted 必须是布尔值。",
            ["intake.time_prompted"],
        )
    has_birth_time = isinstance(birth_time, str) and bool(birth_time.strip())
    has_exact_time = accuracy == "exact" and has_birth_time
    if accuracy is None and not time_prompted:
        raise PipelineError(
            "E_PIPELINE_STATE",
            "ready_for_chart 前必须完成一次可选出生时间采集。",
            ["intake.time_accuracy", "intake.time_prompted"],
        )
    if accuracy is None and has_birth_time:
        raise PipelineError(
            "E_PIPELINE_STATE",
            "已提供 birth_time 时必须归类 time_accuracy。",
            ["intake.birth_time", "intake.time_accuracy"],
        )
    if accuracy == "exact" and not has_exact_time:
        raise PipelineError(
            "E_PIPELINE_STATE",
            "time_accuracy=exact 时必须提供 birth_time。",
            ["intake.birth_time", "intake.time_accuracy"],
        )
    if accuracy not in {None, "exact", "shichen", *DATE_ONLY_KINDS}:
        raise PipelineError(
            "E_PIPELINE_STATE",
            "intake.time_accuracy 不受支持。",
            ["intake.time_accuracy"],
        )
    if accuracy in {"unknown", "withheld"} and has_birth_time:
        raise PipelineError(
            "E_PIPELINE_STATE",
            "不知道或不提供出生时间时，birth_time 必须为空。",
            ["intake.birth_time", "intake.time_accuracy"],
        )

    if accuracy == "shichen" and birth_time not in tuple("子丑寅卯辰巳午未申酉戌亥"):
        raise PipelineError("E_PIPELINE_STATE", "时辰必须为十二地支之一。", ["intake.birth_time"])
    if accuracy == "range":
        from birth_time_range import parse_text
        if not has_birth_time:
            raise PipelineError("E_PIPELINE_STATE", "范围输入必须保留明确起止时间。", ["intake.birth_time"])
        parse_text(birth_time)
    inferred = "time-range" if accuracy in {"shichen", "range"} else ("exact" if has_exact_time else "date-only")
    if declared is not None and declared != inferred:
        raise PipelineError(
            "E_PIPELINE_STATE",
            "resolved.chart_precision 与出生时间状态不一致。",
            ["resolved.chart_precision", "intake.birth_time", "intake.time_accuracy"],
        )
    return declared or inferred


def _common_resolved(resolved: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "timezone": _text(resolved.get("timezone"), "resolved.timezone"),
        "location": _object(resolved.get("location"), "resolved.location"),
    }
    fold = resolved.get("fold")
    if fold is not None:
        if isinstance(fold, bool) or fold not in {0, 1}:
            raise PipelineError(
                "E_PIPELINE_STATE",
                "resolved.fold 必须是 0、1 或 null。",
                ["resolved.fold"],
            )
        result["fold"] = fold
    historical_offset = resolved.get("historical_utc_offset")
    if historical_offset is not None:
        result["historical_utc_offset"] = historical_offset
    return result


def _resolved_with_city_fastpath(
    intake: dict[str, Any], resolved: dict[str, Any]
) -> dict[str, Any]:
    """Fill missing timezone/location from the immutable bundled city table.

    Already complete host-resolved data wins. A partial result may be completed
    only when it agrees with the bundled timezone. Xinjiang is never assigned a
    clock convention implicitly.
    """
    timezone_missing = resolved.get("timezone") is None
    location_missing = resolved.get("location") is None
    if not timezone_missing and not location_missing:
        return resolved

    result = city_timezone_resolver.resolve_city(intake.get("birth_city_raw"))
    status = result.get("status")
    if status == "needs-user-choice":
        existing_timezone = resolved.get("timezone")
        choice_timezones = {
            choice.get("timezone")
            for choice in result.get("choices", [])
            if isinstance(choice, dict)
        }
        if existing_timezone in choice_timezones:
            enriched = dict(resolved)
            if location_missing:
                enriched["location"] = result["location"]
            return enriched
        raise PipelineError(
            "E_AMBIGUITY_UNRESOLVED",
            "出生城市存在真实钟制歧义，必须先确认记录采用的当地时间口径。",
            ["intake.birth_city_raw"],
            str(result.get("ambiguity_code") or "xinjiang_clock_required"),
        )

    if result.get("ok") is not True:
        error = result.get("error")
        error_code = error.get("code") if isinstance(error, dict) else None
        if error_code == "E_INVALID_CITY_QUERY":
            raise PipelineError(
                "E_PIPELINE_STATE",
                "ready_for_chart 前必须提供出生城市。",
                ["intake.birth_city_raw"],
            )
        raise PipelineError(
            "E_CITY_RESOLUTION_REQUIRED",
            "内置城市表未命中，需要宿主位置服务在内部完成解析。",
            ["intake.birth_city_raw"],
        )

    matched_timezone = result.get("timezone")
    existing_timezone = resolved.get("timezone")
    if existing_timezone is not None and existing_timezone != matched_timezone:
        raise PipelineError(
            "E_PIPELINE_STATE",
            "已解析时区与内置城市表结果不一致。",
            ["resolved.timezone", "intake.birth_city_raw"],
        )

    enriched = dict(resolved)
    if timezone_missing:
        enriched["timezone"] = matched_timezone
    if location_missing:
        enriched["location"] = result["location"]
    return enriched


def _lunar_leap_month(intake: dict[str, Any]) -> bool:
    value = intake.get("lunar_is_leap_month")
    if not isinstance(value, bool):
        raise PipelineError(
            "E_PIPELINE_STATE",
            "农历输入必须明确 lunar_is_leap_month。",
            ["intake.lunar_is_leap_month"],
            "lunar_leap_month_required",
        )
    return value


def _exact_inputs(
    mode: str,
    intake: dict[str, Any],
    resolved: dict[str, Any],
    request: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    calendar = _calendar(intake)
    common = {
        **_common_resolved(resolved),
        "time_precision": {"kind": "exact", "minutes": 0},
    }
    inputs: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []

    if mode in {"bazi", "combined"}:
        bazi: dict[str, Any] = {
            **common,
            "calendar": calendar,
            "day_boundary_policy": "civil-midnight",
            "solar_time_policy": "civil",
        }
        if calendar == "gregorian":
            bazi["local_datetime"] = _text(
                resolved.get("local_datetime"), "resolved.local_datetime"
            )
        else:
            bazi["lunar_datetime"] = _text(
                resolved.get("lunar_datetime"), "resolved.lunar_datetime"
            )
            bazi["lunar_is_leap_month"] = _lunar_leap_month(intake)

        explicit_luck = request.get("include_luck_cycles") is True
        # A deep-report request authorizes preparing deterministic Dayun input
        # when the traditional parameter was already supplied.  It never turns
        # a missing parameter into another user question; report preparation
        # can safely project two anonymous conditional branches instead.
        include_luck = explicit_luck or request.get("artifact") == "report"
        gender = request.get("gender_for_bazi")
        if include_luck and gender in {"male", "female"}:
            bazi["gender_for_bazi"] = gender
        elif explicit_luck:
            warnings.append("传统排运参数不可用；本次基础八字盘不生成大运。")
        inputs["bazi"] = bazi

    if mode in {"western", "combined"}:
        inputs["western"] = {
            **common,
            "calendar": "gregorian",
            "local_datetime": _text(
                resolved.get("local_datetime"), "resolved.local_datetime"
            ),
        }
    return inputs, warnings


def _date_only_inputs(
    mode: str,
    intake: dict[str, Any],
    resolved: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    calendar = _calendar(intake)
    accuracy = intake.get("time_accuracy")
    if accuracy in DATE_ONLY_KINDS:
        precision_kind = accuracy
    elif accuracy is None and intake.get("time_prompted") is True:
        precision_kind = "unspecified"
    else:
        raise PipelineError(
            "E_PIPELINE_STATE",
            "日期级初盘需要已归类的时间状态或已完成一次可选时间采集。",
            ["intake.time_accuracy", "intake.time_prompted"],
        )
    common = {
        **_common_resolved(resolved),
        "calendar": calendar,
        "time_precision": {"kind": precision_kind, "minutes": None},
    }
    if calendar == "lunar":
        birth_date = _text(intake.get("birth_date"), "intake.birth_date")
        common["lunar_is_leap_month"] = _lunar_leap_month(intake)
    else:
        birth_date = _text(
            resolved.get("local_date") or intake.get("birth_date"),
            "resolved.local_date",
        )
    common["birth_date"] = birth_date

    inputs: dict[str, dict[str, Any]] = {}
    if mode in {"bazi", "combined"}:
        inputs["bazi"] = {
            **common,
            "day_boundary_policy": "civil-midnight",
            "solar_time_policy": "civil",
        }
    if mode in {"western", "combined"}:
        # date_only_chart performs the deterministic lunar-to-solar conversion
        # before calling the Western engine when calendar=lunar.
        inputs["western"] = dict(common)
    return inputs, []


def project_inputs(
    state: dict[str, Any],
) -> tuple[str, str, dict[str, dict[str, Any]], list[str]]:
    if state.get("schema_version") != STATE_SCHEMA_VERSION:
        raise PipelineError(
            "E_PIPELINE_STATE",
            f"schema_version 必须为 {STATE_SCHEMA_VERSION}。",
            ["schema_version"],
        )
    if state.get("interaction_variant") != "dynamic-guided":
        raise PipelineError(
            "E_PIPELINE_STATE",
            "interaction_variant 必须为 dynamic-guided。",
            ["interaction_variant"],
        )
    if state.get("state") != "ready_for_chart":
        raise PipelineError(
            "E_PIPELINE_STATE",
            "只有 ready_for_chart 状态可以启动排盘流水线。",
            ["state"],
        )
    missing_fields = state.get("missing_fields", [])
    if not isinstance(missing_fields, list) or missing_fields:
        raise PipelineError(
            "E_PIPELINE_STATE",
            "ready_for_chart 状态不得保留 missing_fields。",
            ["missing_fields"],
        )
    revision = state.get("chart_revision")
    if isinstance(revision, bool) or revision != 0:
        raise PipelineError(
            "E_REVISION_UNSUPPORTED",
            "当前流水线只接受 chart_revision=0，并生成不可变 revision 1。",
            ["chart_revision"],
        )
    mode = state.get("mode")
    if mode not in MODES:
        raise PipelineError(
            "E_PIPELINE_STATE",
            "mode 必须是 bazi、western 或 combined。",
            ["mode"],
        )

    intake = _object(state.get("intake"), "intake")
    resolved = _object(state.get("resolved"), "resolved")
    request = _object(state.get("request", {}), "request")
    artifact = request.get("artifact")
    if artifact not in ARTIFACTS:
        raise PipelineError(
            "E_PIPELINE_STATE",
            "request.artifact 不受支持。",
            ["request.artifact"],
        )
    ambiguity = resolved.get("ambiguity_code")
    if ambiguity is not None:
        raise PipelineError(
            "E_AMBIGUITY_UNRESOLVED",
            "位置或时间歧义尚未解决，不能启动排盘。",
            ["resolved.ambiguity_code"],
            str(ambiguity),
        )

    resolved = _resolved_with_city_fastpath(intake, resolved)
    precision = _precision(intake, resolved)
    if precision == "time-range":
        from birth_time_range import parse_text
        calendar = _calendar(intake)
        common = {
            **_common_resolved(resolved),
            "time_precision": {"kind": intake["time_accuracy"], "minutes": None},
        }
        if intake["time_accuracy"] == "shichen":
            common["birth_time_branch"] = intake["birth_time"]
        else:
            common["time_ranges"] = parse_text(intake["birth_time"])
        inputs, warnings = {}, []
        if mode in {"bazi", "combined"}:
            bazi = {**common, "calendar": calendar,
                    "birth_date": _text(intake.get("birth_date"), "intake.birth_date"),
                    "day_boundary_policy": "civil-midnight", "solar_time_policy": "civil"}
            if calendar == "lunar":
                bazi["lunar_is_leap_month"] = _lunar_leap_month(intake)
            inputs["bazi"] = bazi
        if mode in {"western", "combined"}:
            inputs["western"] = {**common, "calendar": "gregorian",
                "birth_date": _text(resolved.get("local_date") or (intake.get("birth_date") if calendar == "gregorian" else None), "resolved.local_date"),
                "location": city_timezone_resolver.with_western_coordinates(common["location"])}
    elif precision == "exact":
        inputs, warnings = _exact_inputs(mode, intake, resolved, request)
        if "western" in inputs:
            inputs["western"]["location"] = city_timezone_resolver.with_western_coordinates(
                inputs["western"]["location"]
            )
    else:
        inputs, warnings = _date_only_inputs(mode, intake, resolved)
    return mode, precision, inputs, warnings


def _generate(
    precision: str, inputs: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    if precision == "time-range":
        if "bazi" in inputs:
            import bazi_time_range
            results["bazi"] = bazi_time_range.generate(inputs["bazi"])
        if "western" in inputs:
            import western_time_range
            results["western"] = western_time_range.generate(inputs["western"])
    elif precision == "exact":
        # Avoid loading the other calculation stack for a single-system chart.
        if "bazi" in inputs:
            import bazi_engine

            results["bazi"] = bazi_engine.generate(inputs["bazi"])
        if "western" in inputs:
            import western_engine

            results["western"] = western_engine.generate(inputs["western"])
    else:
        import date_only_chart

        if "bazi" in inputs:
            results["bazi"] = date_only_chart.generate_bazi(inputs["bazi"])
        if "western" in inputs:
            results["western"] = date_only_chart.generate_western(inputs["western"])
    return results


def _artifact_paths(
    output_dir: Path,
    systems: list[str],
    analysis_systems: list[str],
) -> dict[str, Any]:
    return {
        "inputs": {
            system: str((output_dir / f"chart-input-{system}.json").resolve())
            for system in systems
        },
        "charts": {
            system: str((output_dir / f"{system}.json").resolve())
            for system in systems
        },
        "analysis_charts": {
            system: str((output_dir / f"analysis-{system}.json").resolve())
            for system in analysis_systems
        },
        "html": str((output_dir / "chart.html").resolve()),
        "manifest": str((output_dir / "chart-manifest.json").resolve()),
    }


def _unique_warnings(
    pipeline_warnings: list[str], results: dict[str, dict[str, Any]]
) -> list[str]:
    merged = list(pipeline_warnings)
    for result in results.values():
        warnings = result.get("warnings")
        if isinstance(warnings, list):
            merged.extend(item for item in warnings if isinstance(item, str))
    return list(dict.fromkeys(merged))


def run_pipeline(state: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    mode, precision, inputs, pipeline_warnings = project_inputs(state)
    raw_target = output_dir.expanduser()
    if raw_target.exists() or raw_target.is_symlink():
        raise PipelineError(
            "E_OUTPUT_EXISTS",
            "输出目录必须尚不存在；当前版本只提交全新的 revision 1 目录。",
            ["output_dir"],
        )
    if not raw_target.name or raw_target.name in {".", ".."}:
        raise PipelineError("E_OUTPUT_PATH", "输出目录名称无效。", ["output_dir"])
    parent = raw_target.parent.resolve()
    if not parent.is_dir() or parent.is_symlink():
        raise PipelineError(
            "E_OUTPUT_PATH", "输出目录的父目录必须是已存在的普通目录。", ["output_dir"]
        )
    target = parent / raw_target.name

    # Complete all calculation and rendering in memory before touching the
    # destination.  Engine failure therefore cannot leave a partial revision.
    results = _generate(precision, inputs)
    document = render_chart_html.render_document(
        results.get("bazi"), results.get("western")
    )
    systems = [system for system in ("bazi", "western") if system in results]
    request = _object(state.get("request", {}), "request")
    prepare_inline_analysis = (
        request.get("artifact") in INLINE_ANALYSIS_ARTIFACTS
        or (request.get("artifact") in {None, "chart"} and request.get("include_summary", True))
    )
    analysis_results: dict[str, dict[str, Any]] = {}
    analysis_warnings: list[str] = []
    if prepare_inline_analysis:
        import prepare_analysis_chart

        for system in systems:
            try:
                analysis_results[system] = prepare_analysis_chart.prepare_payload(
                    results[system]
                )
            except Exception:
                analysis_warnings.append(
                    f"{system} 去身份化分析上下文准备失败；盘面仍可交付，本轮不生成该体系解释。"
                )
    analysis_systems = [system for system in systems if system in analysis_results]
    artifacts = _artifact_paths(target, systems, analysis_systems)
    manifest = {
        "schema_version": "1.0.0",
        "pipeline": {"name": PIPELINE_NAME, "version": PIPELINE_VERSION},
        # Generation and delivery are deliberately separate.  This pipeline
        # can prove that the immutable bundle exists, but only the host can
        # prove that its presentation/attachment tool returned successfully.
        "status": "chart_generated",
        "mode": mode,
        "chart_precision": precision,
        "chart_revision": 1,
        "source_chart_revision": 0,
        "systems": systems,
        "artifacts": artifacts,
        "engines": {
            system: results[system].get("engine", {}) for system in systems
        },
        "warnings": _unique_warnings(
            [*pipeline_warnings, *analysis_warnings], results
        ),
        "state_patch": {"state": "chart_generated", "chart_revision": 1},
        "delivery_patch": {"state": "chart_ready", "chart_revision": 1},
    }

    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=parent))
    os.chmod(staging, 0o700)
    try:
        for system in systems:
            atomic_write_json(staging / f"chart-input-{system}.json", inputs[system])
            atomic_write_json(staging / f"{system}.json", results[system])
        for system in analysis_systems:
            atomic_write_json(
                staging / f"analysis-{system}.json", analysis_results[system]
            )
        render_chart_html.atomic_write(staging / "chart.html", document)
        atomic_write_json(staging / "chart-manifest.json", manifest)
        if target.exists() or target.is_symlink():
            raise PipelineError(
                "E_OUTPUT_EXISTS",
                "提交前检测到同名输出目录，已取消本次 revision。",
                ["output_dir"],
            )
        os.replace(staging, target)
        os.chmod(target, 0o700)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return manifest


def next_action_for_error(code: str, ambiguity_code: str | None) -> str:
    """Return the caller action without exposing internal fields as questions."""
    if ambiguity_code is not None:
        return AMBIGUITY_NEXT_ACTIONS.get(ambiguity_code, "stop")
    return ERROR_NEXT_ACTIONS.get(code, "stop")


def recovery_for_error(
    code: str, ambiguity_code: str | None, next_action: str
) -> dict[str, Any]:
    """Build stable, user-safe recovery metadata for the host."""
    if ambiguity_code is not None:
        message = AMBIGUITY_USER_MESSAGES.get(ambiguity_code)
    else:
        message = ERROR_USER_MESSAGES.get(code)
    if message is None:
        message = (
            DEFAULT_STOP_MESSAGE if next_action == "stop" else DEFAULT_RECOVERABLE_MESSAGE
        )

    recovery: dict[str, Any] = {
        "user_message": message,
        # The host tracks attempts by error.code. A repeated code after this
        # one permitted recovery must be treated as stop.
        "max_attempts": 0 if next_action == "stop" else 1,
    }
    if next_action == "degrade":
        target = (
            AMBIGUITY_DEGRADE_TARGETS.get(ambiguity_code)
            if ambiguity_code is not None
            else ERROR_DEGRADE_TARGETS.get(code)
        )
        if target is None:
            # A newly added degrade action must declare its safe target first.
            recovery["user_message"] = DEFAULT_STOP_MESSAGE
            recovery["max_attempts"] = 0
        else:
            recovery["target"] = target
    return recovery


def error_payload(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, PipelineError):
        code = exc.code
        fields = exc.fields
        ambiguity = exc.ambiguity_code
    elif isinstance(exc, EngineError):
        code = exc.code
        fields = exc.fields
        ambiguity = ENGINE_AMBIGUITIES.get(exc.code)
    elif isinstance(exc, OSError):
        code = "E_PIPELINE_IO"
        fields = ["output_dir"]
        ambiguity = None
    else:
        code = "E_PIPELINE_INTERNAL"
        fields = []
        ambiguity = None
    next_action = next_action_for_error(code, ambiguity)
    recovery = recovery_for_error(code, ambiguity, next_action)
    if next_action == "degrade" and "target" not in recovery:
        next_action = "stop"
    return {
        "ok": False,
        "error": {"code": code, "message": str(exc), "fields": fields},
        "ambiguity_code": ambiguity,
        "next_action": next_action,
        "recovery": recovery,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build an immutable revision-1 chart bundle from normalized interaction state."
    )
    parser.add_argument("state", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        state = load_json(args.state)
        manifest = run_pipeline(state, args.output_dir)
        print(
            json.dumps(
                {
                    "ok": True,
                    "manifest": manifest["artifacts"]["manifest"],
                    "chart": manifest["artifacts"]["html"],
                    "analysis_charts": manifest["artifacts"]["analysis_charts"],
                    "mode": manifest["mode"],
                    "chart_precision": manifest["chart_precision"],
                    "chart_revision": manifest["chart_revision"],
                    "status": manifest["status"],
                    "state_patch": manifest["state_patch"],
                    "delivery_patch": manifest["delivery_patch"],
                    "warnings": manifest["warnings"],
                },
                ensure_ascii=False,
            )
        )
        return 0
    except Exception as exc:
        print(json.dumps(error_payload(exc), ensure_ascii=False))
        return 2 if isinstance(exc, (PipelineError, EngineError)) else 3


if __name__ == "__main__":
    raise SystemExit(main())
