#!/usr/bin/env python3
"""Validate a small birth request, plan one question or build a chart in one call.

The CLI reads JSON on stdin (or from a private file); personal data never needs
to be placed in command arguments. The large legacy interaction state is an
internal adapter, not a model-facing contract.
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any

import delivery
from engine_common import EngineError, atomic_write_json, load_json

SCHEMA_PATH = Path(__file__).with_name("chart-request.schema.json")
# The chart page is delivered; the birth facts behind it stay in the private run dir.
CHART_STEMS = {"bazi": "八字命盘", "western": "西洋星盘", "combined": "命盘"}
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
TOPICS = dict(zip(
    ("career", "emotion", "family", "economy", "social", "talent", "spiritual", "study", "health"),
    ("事业发展", "情感婚恋", "家庭亲情", "经济状况", "社会关系", "天赋挖掘", "精神成长", "学业考试", "身体健康"),
))


def validate_schema(value: Any, schema: dict[str, Any], path: str = "request") -> None:
    """Validate the JSON Schema keywords used by our bundled contract, offline."""
    types = schema.get("type", [])
    if isinstance(types, str):
        types = [types]
    checks = {
        "object": isinstance(value, dict), "array": isinstance(value, list),
        "string": isinstance(value, str), "null": value is None,
        "boolean": isinstance(value, bool),
        "number": isinstance(value, (float, int)) and not isinstance(value, bool),
    }
    enum = schema.get("enum")
    enum_valid = enum is None or any(type(value) is type(item) and value == item for item in enum)
    if (types and not any(checks.get(kind, False) for kind in types)) or not enum_valid:
        raise EngineError("E_REQUEST_SCHEMA", "输入字段的类型或枚举值无效。", [path])
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            raise EngineError("E_REQUEST_SCHEMA", "输入含未声明字段。", [path])
        for key in schema.get("required", []):
            if key not in value:
                raise EngineError("E_REQUEST_SCHEMA", "输入缺少结构字段。", [f"{path}.{key}"])
        for key, item in value.items():
            if key in properties:
                validate_schema(item, properties[key], f"{path}.{key}")
    elif isinstance(value, list):
        for item in value:
            validate_schema(item, schema.get("items", {}), path)
    elif isinstance(value, str):
        if len(value) > schema.get("maxLength", 100000) or (
            "pattern" in schema and re.search(schema["pattern"], value) is None
        ):
            raise EngineError("E_REQUEST_SCHEMA", "输入字段格式无效。", [path])


def parse_time(value: str | None) -> tuple[str | None, str | None]:
    """Return accuracy and a clock/branch; never synthesize a midpoint."""
    if value is None or not value.strip():
        return None, None
    text = re.sub(r"\s+", "", unicodedata.normalize("NFKC", value)).replace("時", "时")
    if text in {"不知道", "不清楚", "未知", "不记得", "我不清楚具体的出生时间", "不清楚/不想说"}:
        return "unknown", None
    if text in {"保密", "不提供", "不想提供", "不愿提供", "不想说"}:
        return "withheld", None
    match = re.fullmatch(r"([子丑寅卯辰巳午未申酉戌亥])(?:时)?", text)
    if match:
        return "shichen", match[1]
    if re.search(r"大约|大概|左右|前后|约", text):
        return "approximate", text
    if re.search(r"[-~～—–至到]", text):
        from birth_time_range import parse_text
        parse_text(text)  # Reject malformed bounds instead of widening to a day.
        return "range", text
    if re.search(r"上午|下午|晚上|早上|凌晨|中午|清晨|傍晚|夜里", text):
        return "approximate", text
    match = re.fullmatch(r"(\d{1,2}):(\d{2})(?::00)?", text)
    if match is None:
        match = re.fullmatch(r"(\d{1,2})点(?:(\d{1,2})分?)?", text)
    if match:
        hour, minute = int(match[1]), int(match[2] or 0)
        if hour < 24 and minute < 60:
            return "exact", f"{hour:02d}:{minute:02d}"
    raise EngineError("E_BIRTH_TIME", "出生时间无法解析。", ["birth_time"])


def question_result(request: dict[str, Any], fields: list[str], prompt: str,
                    *, choices: list[dict[str, Any]] | None = None,
                    optional_time: bool = False) -> dict[str, Any]:
    resume = dict(request)
    if "birth_time" in fields or optional_time:
        resume["time_prompted"] = True
    return {
        "ok": True, "status": "needs_input", "next_action": "ask",
        "question": {"kind": "choice" if choices else "text", "prompt": prompt,
                     "fields": fields, "choices": choices or [],
                     "optional_time": optional_time},
        "resume_request": resume,
    }


def _date_parts(value: str) -> tuple[int, int, int]:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("date format")
    return tuple(map(int, value.split("-")))


def plan(request: dict[str, Any]) -> dict[str, Any]:
    validate_schema(request, json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    request = dict(request)
    mode = request.get("mode", "bazi")
    if mode == "western":
        request.pop("gender_for_bazi", None)
        request.pop("include_luck_cycles", None)
    for field in ("birth_date", "birth_city", "birth_time"):
        if isinstance(request.get(field), str):
            request[field] = request[field].strip() or None
    missing = [field for field in ("birth_date", "birth_city") if not request.get(field)]
    issues: list[str] = []
    try:
        accuracy, time_value = parse_time(request.get("birth_time"))
    except EngineError:
        accuracy, time_value = None, None
        missing.append("birth_time")
        issues.append("出生时间请写为 01:30、10:00–12:00、丑时或不清楚")
    calendar = request.get("calendar", "gregorian")
    solar_date = request.get("birth_date")
    leap_needed = False
    if solar_date:
        try:
            year, month, day = _date_parts(solar_date)
            if calendar == "gregorian":
                solar_date = date(year, month, day).isoformat()
            else:
                # Import only for lunar requests; the missing-input fast path
                # does not load either calculation engine or the HTML renderer.
                from vendor.lunar_python import Lunar, LunarYear
                if not (1 <= year <= 9999 and 1 <= month <= 12 and 1 <= day <= 30):
                    raise ValueError("invalid lunar date")
                leap_month = LunarYear.fromYear(year).getLeapMonth()
                leap = request.get("lunar_is_leap_month")
                flags = [False, True] if leap is None and month == leap_month else [bool(leap)]
                valid_dates = {}
                for flag in flags:
                    try:
                        valid_dates[flag] = Lunar.fromYmd(year, -month if flag else month, day).getSolar().toYmd()
                    except Exception:
                        pass  # Invalid lunar month/day, including nonexistent leap months.
                if not valid_dates:
                    raise ValueError("invalid lunar date")
                leap_needed = len(valid_dates) == 2
                if not leap_needed:
                    request["lunar_is_leap_month"] = next(iter(valid_dates))
                solar_date = next(iter(valid_dates.values()))
        except Exception:
            missing.append("birth_date")
            issues.append("请核对出生日期（所选历法中的有效 YYYY-MM-DD）")
            solar_date = None
    offer_time = accuracy is None and not request.get("time_prompted", False)
    if missing:
        labels = {"birth_date": "出生日期", "birth_city": "出生城市", "birth_time": "出生时间"}
        fields = list(dict.fromkeys(missing))
        prompt = "请补充" + "、".join(labels[field] for field in fields) + "。"
        if issues:
            prompt += "；".join(issues) + "。"
        if offer_time and "birth_time" not in fields:
            prompt += "知道出生时间也可一起填写（如 01:30 或丑时）；不清楚可以留空。"
        if leap_needed:
            fields.append("lunar_is_leap_month")
            prompt += "另请注明该农历月是否为闰月。"
        return question_result(request, fields, prompt, optional_time=offer_time)
    if leap_needed:
        if offer_time:
            return question_result(request, ["lunar_is_leap_month", "birth_time"],
                                   "请注明这个农历月份是闰月还是非闰月；知道出生时间也可一起填写（如 01:30 或丑时），时间不清楚可以留空。",
                                   optional_time=True)
        return question_result(request, ["lunar_is_leap_month"], "这个农历月份是闰月还是非闰月？", choices=[
            {"label": "非闰月", "patch": {"lunar_is_leap_month": False}},
            {"label": "闰月", "patch": {"lunar_is_leap_month": True}},
        ])
    if offer_time:
        return question_result(request, ["birth_time"],
                               "如果知道出生时间，请填写钟表时间或时辰（如 01:30、丑时）；不清楚可以跳过。",
                               optional_time=True)

    import city_timezone_resolver
    resolution = dict(request.get("resolution", {}))
    if not (resolution.get("timezone") and resolution.get("location")):
        city = city_timezone_resolver.resolve_city(request["birth_city"])
        if city.get("status") == "needs-user-choice" and not resolution.get("timezone"):
            choices = [{"label": choice["label"],
                        "patch": {"resolution": {**resolution, "timezone": choice["timezone"],
                                                 "location": city["location"]}}}
                       for choice in city["choices"]]
            return question_result(request, ["clock_convention"],
                                   "出生记录用的是北京时间还是新疆时间？", choices=choices)
        if city.get("ok") is True or city.get("status") == "needs-user-choice":
            if not resolution.get("timezone"):
                resolution["timezone"] = city["timezone"]
            resolution.setdefault("location", city["location"])
        else:
            return {"ok": True, "status": "needs_resolution", "next_action": "resolve_city",
                    "query": request["birth_city"], "resume_request": request,
                    "resolution_fields": ["timezone", "location"], "max_attempts": 1}

    local_datetime = f"{solar_date}T{time_value}:00" if accuracy == "exact" else None
    state = {
        "schema_version": "1.4.0", "interaction_variant": "dynamic-guided", "mode": mode,
        "intake": {"calendar": calendar, "birth_date": request["birth_date"],
                   "birth_city_raw": request["birth_city"], "birth_time": time_value,
                   "time_accuracy": accuracy, "time_prompted": request.get("time_prompted", False),
                   "lunar_is_leap_month": request.get("lunar_is_leap_month")},
        "resolved": {**resolution, "local_date": solar_date, "local_datetime": local_datetime,
                     "lunar_datetime": f"{request['birth_date']}T{time_value}:00" if accuracy == "exact" and calendar == "lunar" else None,
                     "ambiguity_code": None, "chart_precision": None},
        "request": {"artifact": request.get("artifact", "chart"), "question": request.get("question"),
                    "include_summary": request.get("include_summary", True),
                    "topics": list(dict.fromkeys(request.get("topics", []))),
                    "include_luck_cycles": request.get("include_luck_cycles", False),
                    "gender_for_bazi": request.get("gender_for_bazi"),
                    "layout": "desktop", "share_card": "forbidden"},
        "state": "ready_for_chart", "missing_fields": [], "warnings": [], "chart_revision": 0,
    }
    if mode == "western":
        state["request"].pop("gender_for_bazi", None)
        state["request"].pop("include_luck_cycles", None)
    return {"ok": True, "status": "ready", "state": state, "request": request}


def _after_delivery(request: dict[str, Any]) -> dict[str, Any]:
    artifact = request.get("artifact", "chart")
    if artifact in {"conclusion", "analysis"}:
        # The requested text is now written before the attachment, once.
        return {"next_action": "done"}
    if artifact == "report":
        if request.get("topics") or request.get("question"):
            return {"next_action": "prepare_report", "topics": request.get("topics", []),
                    "question": request.get("question")}
    if not request.get("offer_report", True) and artifact != "report":
        return {"next_action": "done"}
    return {"next_action": "ask_report_topics", "question": {
        "kind": "multi_select", "optional": True, "max_selections": len(TOPICS),
        "prompt": "盘面已生成。深度报告想看哪些方面？可多选，也可跳过。",
        "choices": [{"id": key, "label": value} for key, value in TOPICS.items()],
    }}


def before_delivery(request: dict[str, Any], analysis_charts: dict[str, str]) -> dict[str, Any] | None:
    """Expose already prepared, de-identified facts for the reply body."""
    artifact = request.get("artifact", "chart")
    if artifact == "report" or (artifact == "chart" and not request.get("include_summary", True)):
        return None
    if not analysis_charts:
        return None
    systems = set(analysis_charts)
    instruction = (
        "先用已核验分析盘写命局概要与简要分析（或用户要求的结论／分析），"
        "再原样附 media_info；整份草稿通过 verify_command 后发出。已回答内容不在交付后重复生成。"
    )
    if systems == {"bazi"} and artifact == "chart":
        instruction = (
            "先据已核验四柱写出这张盘的主要结构：月令与日主的生扶、透藏十神的耗泄克制"
            "如何共同支持一个具体判断，再简要回应用户所问；不要把判断缩成反复自省或零碎行动建议。"
            "然后原样附 media_info，整份草稿通过 verify_command 后发出；交付后不重复已回答内容。"
        )
    if systems == {"western"}:
        instruction = (
            "星盘 HTML 只展示已核验的位置事实，解读须在本次回复正文由模型完成。"
            "先读 analysis_charts.western，按用户原问题直接给出简要结论或所需分析；"
            "选择相关的已确定配置，说明天体主题、星座表达及它们的分工、配合或张力，"
            "落到问题情境与判断条件。有两项相关稳定配置时，普通概要也至少解释一条配置关系；"
            "证据只有一项时缩小结论。日期／范围盘只用稳定项，不挑候选；"
            "未知上升、宫位、相位和行运不补算。正文后原样附 media_info，"
            "整份草稿通过 verify_command 后作为同一回复发出，不在交付后另起一次解读。"
        )
    elif "western" in systems:
        instruction += (
            "西占部分按已确定配置解释它们与用户问题的关系，日期／范围盘只用稳定项；"
            "西占 HTML 只呈现位置事实，模型在本次回复正文中完成解读；"
            "不补算未知上升、宫位、相位或行运。"
        )
    return {
        "next_action": "interpret_analysis_charts",
        "artifact": "summary" if artifact == "chart" else artifact,
        "user_question": request.get("question"),
        "analysis_charts": analysis_charts,
        "references": [str(Path(__file__).resolve().parents[1] / "references" / f"{system}-report.md")
                       for system in analysis_charts],
        "instruction": instruction,
    }


def _recover(response: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    """Turn known engine questions into the same small interaction protocol."""
    ambiguity = response.get("ambiguity_code")
    if ambiguity == "dst_fold_required":
        resolution = request.get("resolution", {})
        return question_result(request, ["clock_occurrence"], response["recovery"]["user_message"], choices=[
            {"label": "回拨前第一次", "patch": {"resolution": {**resolution, "fold": 0}}},
            {"label": "回拨后第二次", "patch": {"resolution": {**resolution, "fold": 1}}},
            {"label": "不确定，按日期出盘", "patch": {"birth_time": "不清楚", "time_prompted": True}},
        ])
    if ambiguity == "nonexistent_local_time":
        return question_result(request, ["birth_time"], response["recovery"]["user_message"], optional_time=True)
    if response.get("error", {}).get("code") == "E_CALENDAR_CONVERSION":
        return question_result(request, ["birth_date", "lunar_is_leap_month"], response["recovery"]["user_message"])
    return {**response, "resume_request": request}


def run(request: dict[str, Any], output_dir: Path | None = None, *, compact: bool = True) -> dict[str, Any]:
    started = time.perf_counter()
    planned = plan(request)
    if planned["status"] != "ready":
        planned["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
        return planned
    import chart_pipeline
    import secure_run_dir
    run_dir = secure_run_dir.create_run_dir() if output_dir is None else None
    destination = run_dir / "chart" if run_dir else output_dir
    try:
        manifest = chart_pipeline.run_pipeline(planned["state"], destination)
    except Exception as exc:
        if run_dir:
            secure_run_dir.cleanup_run_dir(run_dir)
        response = _recover(chart_pipeline.error_payload(exc), planned["request"])
        response["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
        return response
    state = {**planned["state"], **manifest["state_patch"]}
    state_path = destination / "interaction-state.json"
    atomic_write_json(state_path, state)
    result = {"ok": True,
              **{key: manifest[key] for key in ("status", "mode", "chart_precision", "warnings", "delivery_patch")},
              "artifacts": {key: manifest["artifacts"][key] for key in ("html", "charts", "analysis_charts", "manifest")},
              "next_action": "display_chart",
              "interaction_state": str(state_path.resolve()),
              "after_delivery": _after_delivery(planned["request"]),
              "elapsed_ms": round((time.perf_counter() - started) * 1000, 1)}
    # Persist the post-delivery handoff so HTML delivery is not accidentally
    # treated as the end of a chart-only request. No report is prepared here.
    import chart_followup
    followup_path = chart_followup.create(
        destination, result["artifacts"], result["after_delivery"],
        omit_luck_cycle=planned["request"].get("omit_luck_cycle", False),
    )
    result["after_delivery"]["next_command"] = chart_followup.command(followup_path, "delivered")
    result["followup_session"] = str(followup_path)
    # The fingerprints above cover the private chart facts, so the workspace copy is
    # published once that integrity set is frozen.
    workspace = delivery.resolve_workspace()
    if workspace is not None:
        result["artifacts"]["html"] = str(delivery.publish(
            Path(manifest["artifacts"]["html"]), workspace,
            CHART_STEMS.get(manifest["mode"], "命盘"),
        ))
    html_path = result["artifacts"]["html"]
    delivery.attach_delivery(
        result,
        html_path,
        CHART_STEMS.get(manifest["mode"], "命盘"),
        success_action="display_chart",
    )
    if result["delivery"]["ok"]:
        interpretation = before_delivery(planned["request"], result["artifacts"]["analysis_charts"])
        if interpretation:
            result["before_delivery"] = interpretation
    if result["next_action"] == "display_chart":
        result["delivery_instruction"] = (
            str(result["delivery_instruction"])
            + " 草稿校验通过并输出 media_info 之后，必须执行 after_delivery.next_command，"
            "再按顶层 next_action 继续，不能在只发出盘面后提前结束。"
        )
    result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
    if run_dir:
        result["cleanup_command"] = "python3 scripts/secure_run_dir.py cleanup --path " + shlex.quote(str(run_dir))
    if not compact:
        return {**manifest, **result, "artifacts": manifest["artifacts"]}
    return result


def main(*, compact: bool = True) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", default="-", help="Private JSON file or - for stdin")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--schema", action="store_true")
    args = parser.parse_args()
    if args.schema:
        print(SCHEMA_PATH.read_text(encoding="utf-8"))
        return 0
    try:
        request = json.load(sys.stdin) if args.input == "-" else load_json(Path(args.input))
        result = run(request, args.output_dir, compact=compact)
    except (EngineError, ValueError, OSError) as exc:
        result = {"ok": False, "status": "invalid_request", "next_action": "repair_request",
                  "error": {"code": getattr(exc, "code", "E_REQUEST_JSON"),
                            "fields": getattr(exc, "fields", [])}, "max_attempts": 1}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
