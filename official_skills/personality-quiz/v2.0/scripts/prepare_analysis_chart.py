#!/usr/bin/env python3
"""Strip identity-bearing birth metadata before generative chart interpretation."""

from __future__ import annotations

import argparse
import calendar
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class PrepareError(ValueError):
    pass


_LEAF = object()
_PILLARS = {key: _LEAF for key in ("year", "month", "day", "hour")}
_PILLAR_LISTS = {key: [_LEAF] for key in ("year", "month", "day", "hour")}
_DAY_MASTER = {"stem": _LEAF, "element": _LEAF, "polarity": _LEAF}
_HIDDEN_STEM = {
    "stem": _LEAF,
    "element": _LEAF,
    "ten_god": _LEAF,
    "role": _LEAF,
}
_RELATION = {
    "type": _LEAF,
    "members": [_LEAF],
    "pillars": [_LEAF],
    "transformation_claimed": _LEAF,
}
_ELEMENT_COUNTS = {key: _LEAF for key in ("木", "火", "土", "金", "水")}
_BAZI_DETAILS = {
    "day_master": _DAY_MASTER,
    "heavenly_stems": _PILLARS,
    "earthly_branches": _PILLARS,
    "hidden_stems": {key: [_HIDDEN_STEM] for key in _PILLARS},
    "ten_gods": {
        "heavenly_stems": _PILLARS,
        "hidden_stems": _PILLAR_LISTS,
    },
    "twelve_growth_stages": _PILLARS,
    "five_elements": _PILLARS,
    "element_counts": {
        "visible_stems_and_branches_unweighted": _ELEMENT_COUNTS,
        "hidden_stems_unweighted": _ELEMENT_COUNTS,
    },
    "stem_relations": [_RELATION],
    "branch_relations": [_RELATION],
    "nayin": _PILLARS,
    "previous_jie": {"name": _LEAF},
    "next_jie": {"name": _LEAF},
    "day_boundary_policy": _LEAF,
    "solar_time_policy": _LEAF,
    "sample_count": _LEAF,
    "sample_policy": _LEAF,
    "skipped_nonexistent_local_times": _LEAF,
}
_BAZI_CHART = {
    "pillars": _PILLARS,
    "coverage": _LEAF,
    "precision": _LEAF,
    "stable": {"pillars": _PILLARS, "day_master": _DAY_MASTER},
    "possible": {"pillars": _PILLAR_LISTS},
    "details": _BAZI_DETAILS,
    "unavailable": [_LEAF],
}

_PLANET_IDS = (
    "sun",
    "moon",
    "mercury",
    "venus",
    "mars",
    "jupiter",
    "saturn",
    "uranus",
    "neptune",
    "pluto",
)
_WESTERN_PLANET = {
    # These are celestial coordinates. Geographic latitude/longitude are never allowed.
    "longitude_deg": _LEAF,
    "latitude_deg": _LEAF,
    "sign": _LEAF,
    "degree_in_sign": _LEAF,
    "frame": _LEAF,
    "status": _LEAF,
    "possible_signs": [_LEAF],
}
_WESTERN_ASPECT = {
    "body_a": _LEAF,
    "body_b": _LEAF,
    "aspect": _LEAF,
    "separation_deg": _LEAF,
    "exact_angle_deg": _LEAF,
    "orb_deg": _LEAF,
    "allowed_orb_deg": _LEAF,
}
_PLANET_SIGNS = {planet: _LEAF for planet in _PLANET_IDS}
_POSSIBLE_PLANET_SIGNS = {planet: [_LEAF] for planet in _PLANET_IDS}
_WESTERN_CHART = {
    "coverage": _LEAF,
    "precision": _LEAF,
    "zodiac": _LEAF,
    "stable": {"planet_signs": _PLANET_SIGNS, "ascendant": {"sign": _LEAF}},
    "possible": {"planet_signs": _POSSIBLE_PLANET_SIGNS, "ascendant": [_LEAF]},
    "planets": {planet: _WESTERN_PLANET for planet in _PLANET_IDS},
    "aspects": [_WESTERN_ASPECT],
    "houses": _LEAF,
    "ascendant": {
        "sign": _LEAF,
        "longitude_deg": _LEAF,
        "degree_in_sign": _LEAF,
        "frame": _LEAF,
    },
    "ascendant_status": _LEAF,
    "details": {
        "sample_count": _LEAF,
        "sample_policy": _LEAF,
        "skipped_nonexistent_local_times": _LEAF,
    },
    "unavailable": [_LEAF],
}

_CHART_SCHEMAS = {"bazi": _BAZI_CHART, "western": _WESTERN_CHART}
_SENSITIVE_KEYS = {
    "name",
    "full_name",
    "birth_date",
    "birth_time",
    "birth_place",
    "birth_city",
    "birth_city_raw",
    "local_datetime",
    "lunar_datetime",
    "timezone",
    "location",
    "coordinates",
    "latitude",
    "longitude",
    "owner",
    "profile",
    "observer",
}
_SAFE_NAME_PATHS = {
    ("details", "previous_jie", "name"),
    ("details", "next_jie", "name"),
}
_SOLAR_TERM_NAMES = {
    "小寒", "大寒", "立春", "雨水", "惊蛰", "春分", "清明", "谷雨",
    "立夏", "小满", "芒种", "夏至", "小暑", "大暑", "立秋", "处暑",
    "白露", "秋分", "寒露", "霜降", "立冬", "小雪", "大雪", "冬至",
}
_HEAVENLY_STEMS = "甲乙丙丁戊己庚辛壬癸"
_EARTHLY_BRANCHES = "子丑寅卯辰巳午未申酉戌亥"


def _allowlisted_copy(value: Any, schema: Any, path: tuple[str, ...] = ()) -> Any:
    if value is None:
        return None
    if schema is _LEAF:
        if isinstance(value, (dict, list)):
            raise PrepareError(f"chart.{'.'.join(path)} 必须是标量")
        return value
    if isinstance(schema, dict):
        if not isinstance(value, dict):
            raise PrepareError(f"chart.{'.'.join(path)} 必须是对象")
        return {
            key: _allowlisted_copy(value[key], child_schema, (*path, key))
            for key, child_schema in schema.items()
            if key in value
        }
    if isinstance(schema, list) and len(schema) == 1:
        if not isinstance(value, list):
            raise PrepareError(f"chart.{'.'.join(path)} 必须是数组")
        return [
            _allowlisted_copy(item, schema[0], (*path, str(index)))
            for index, item in enumerate(value)
        ]
    raise RuntimeError("invalid chart allowlist schema")


def _assert_identity_free(value: Any, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            child = (*path, str(key))
            if str(key).lower() in _SENSITIVE_KEYS and child not in _SAFE_NAME_PATHS:
                raise PrepareError(f"去身份化盘面仍包含禁止字段：chart.{'.'.join(child)}")
            _assert_identity_free(nested, child)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _assert_identity_free(nested, (*path, str(index)))


def sanitize_chart(chart_system: str, chart: dict[str, Any]) -> dict[str, Any]:
    sanitized = _allowlisted_copy(chart, _CHART_SCHEMAS[chart_system])
    if chart_system == "bazi":
        details = sanitized.get("details")
        if isinstance(details, dict):
            for jie_key in ("previous_jie", "next_jie"):
                jie = details.get(jie_key)
                if isinstance(jie, dict) and jie.get("name") not in _SOLAR_TERM_NAMES:
                    details.pop(jie_key, None)
        has_core_facts = any(
            isinstance(sanitized.get(key), dict) and bool(sanitized[key])
            for key in ("pillars", "stable")
        )
    else:
        has_core_facts = any(
            isinstance(sanitized.get(key), dict) and bool(sanitized[key])
            for key in ("planets", "stable")
        )
    if not has_core_facts:
        raise PrepareError("盘面不符合内置 chart schema，无法生成安全分析上下文")
    _assert_identity_free(sanitized)
    return sanitized


def current_local_moment(source: dict[str, Any]) -> datetime:
    timezone_name = source.get("input", {}).get("timezone")
    if not isinstance(timezone_name, str) or not timezone_name:
        raise PrepareError("选择当前大运需要原始盘面包含 IANA timezone")
    try:
        return datetime.now(ZoneInfo(timezone_name)).replace(tzinfo=None)
    except ZoneInfoNotFoundError as exc:
        raise PrepareError(f"无法识别原始盘面的 IANA timezone：{timezone_name}") from exc


def valid_gan_zhi(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 2
        and value[0] in _HEAVENLY_STEMS
        and value[1] in _EARTHLY_BRANCHES
        and _HEAVENLY_STEMS.index(value[0]) % 2 == _EARTHLY_BRANCHES.index(value[1]) % 2
    )


def project_luck_cycle(chart: dict[str, Any], focus_moment: datetime) -> dict[str, Any]:
    """Keep the legacy explicit-current-cycle projection contract unchanged."""
    if chart.get("precision") in {"date-only", "time-range"}:
        raise PrepareError("日期级或时辰范围盘不得投影精确大运周期")
    details = chart.get("details")
    luck = details.get("luck_cycles") if isinstance(details, dict) else None
    if not isinstance(luck, dict) or not isinstance(luck.get("cycles"), list):
        raise PrepareError("原始八字盘没有可投影的大运周期")
    if luck.get("calculation_method") != "lunar-python-yun-sect-1":
        raise PrepareError("原始八字盘的大运计算口径不受支持")
    if luck.get("direction") not in {"forward", "backward"}:
        raise PrepareError("原始八字盘的大运方向无效")
    start_value = luck.get("start_solar_datetime")
    if not isinstance(start_value, str):
        raise PrepareError("原始八字盘缺少精确起运时刻")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", start_value):
        raise PrepareError("原始八字盘的起运时刻必须精确到秒")
    try:
        first_start = datetime.strptime(start_value, "%Y-%m-%d %H:%M:%S")
    except ValueError as exc:
        raise PrepareError("原始八字盘的起运时刻无效") from exc
    if first_start.tzinfo is not None:
        raise PrepareError("原始八字盘的起运时刻必须是当地无 offset 时间")
    if len(luck["cycles"]) != 8:
        raise PrepareError("原始八字盘必须包含完整八步大运")

    def add_years(value: datetime, years: int) -> datetime:
        target_year = value.year + years
        target_day = min(value.day, calendar.monthrange(target_year, value.month)[1])
        return value.replace(year=target_year, day=target_day)

    matches: list[dict[str, Any]] = []
    seen_indices: set[int] = set()
    for item in luck["cycles"]:
        if not isinstance(item, dict):
            raise PrepareError("原始八字盘的大运周期格式无效")
        index = item.get("index")
        if isinstance(index, bool) or not isinstance(index, int) or not 1 <= index <= 8:
            raise PrepareError("原始八字盘的大运索引无效")
        if index in seen_indices:
            raise PrepareError("原始八字盘的大运索引重复")
        seen_indices.add(index)
        if not valid_gan_zhi(item.get("gan_zhi")):
            raise PrepareError("原始八字盘的大运干支无效")
        start = add_years(first_start, 10 * (index - 1))
        end = add_years(first_start, 10 * index)
        start_year = item.get("start_year")
        end_year = item.get("end_year")
        if (
            isinstance(start_year, bool)
            or isinstance(end_year, bool)
            or not isinstance(start_year, int)
            or not isinstance(end_year, int)
            or start_year != start.year
            or end_year != end.year - 1
        ):
            raise PrepareError("原始八字盘的大运年份与精确起运时刻不一致")
        if start <= focus_moment < end:
            matches.append(item)
    if seen_indices != set(range(1, 9)):
        raise PrepareError("原始八字盘的大运索引必须完整覆盖 1—8")
    if len(matches) > 1:
        raise PrepareError("当前时刻命中多个大运周期，拒绝生成解释上下文")
    active = matches[0] if matches else None
    cycle = None
    if active is not None:
        cycle = {"index": active["index"], "gan_zhi": active["gan_zhi"]}
    return {
        "as_of_local_date": focus_moment.date().isoformat(),
        "selection_precision": "local_datetime",
        "cycle": cycle,
    }


def _unavailable_dayun(reason: str) -> dict[str, Any]:
    from bazi_dayun_facts import SCHEMA_VERSION, UNAVAILABLE_REASONS

    if reason not in UNAVAILABLE_REASONS:
        reason = "invalid_chart"
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "unavailable",
        "reason": reason,
    }


def _regeneration_input(source: dict[str, Any], gender: str) -> dict[str, Any]:
    """Rebuild only the deterministic engine input needed for report-only Dayun."""
    source_input = source.get("input")
    if not isinstance(source_input, dict):
        raise PrepareError("原始盘面缺少可复算的大运输入")
    required = ("local_datetime", "timezone", "location", "time_precision")
    if any(key not in source_input for key in required):
        raise PrepareError("原始盘面缺少可复算的大运输入")
    payload: dict[str, Any] = {
        "calendar": "gregorian",
        "local_datetime": source_input["local_datetime"],
        "timezone": source_input["timezone"],
        "location": source_input["location"],
        "time_precision": source_input["time_precision"],
        "day_boundary_policy": source_input.get("day_boundary_policy", "civil-midnight"),
        "solar_time_policy": source_input.get("solar_time_policy", "civil"),
        "gender_for_bazi": gender,
    }
    for key in ("fold", "historical_utc_offset"):
        if source_input.get(key) is not None:
            payload[key] = source_input[key]
    return payload


def _conditional_luck_cycles(source: dict[str, Any]) -> dict[str, dict[str, Any]] | None:
    """Calculate both traditional directions privately without choosing one."""
    try:
        import bazi_engine

        alternatives: dict[str, dict[str, Any]] = {}
        for gender in ("male", "female"):
            regenerated = bazi_engine.generate(_regeneration_input(source, gender))
            if regenerated.get("chart", {}).get("pillars") != source.get("chart", {}).get("pillars"):
                raise PrepareError("报告专用复算与已验证四柱不一致")
            luck = regenerated.get("chart", {}).get("details", {}).get("luck_cycles")
            direction = luck.get("direction") if isinstance(luck, dict) else None
            if direction not in {"forward", "backward"} or direction in alternatives:
                raise PrepareError("报告专用复算没有形成两个互斥排运分支")
            alternatives[direction] = luck
        return alternatives if set(alternatives) == {"forward", "backward"} else None
    except Exception:
        return None


def project_report_luck_cycle(
    source: dict[str, Any], focus_moment: datetime | None
) -> dict[str, Any]:
    """Best-effort Dayun facts for a deep report; never blocks the report."""
    from bazi_dayun_facts import project_dayun_facts

    chart = source.get("chart")
    if not isinstance(chart, dict):
        return _unavailable_dayun("invalid_chart")
    if chart.get("precision") in {"date-only", "time-range"}:
        return project_dayun_facts(chart, focus_moment or datetime.min)
    source_input = source.get("input")
    if not isinstance(source_input, dict):
        return _unavailable_dayun("invalid_chart")
    # The vendored solar-term implementation is currently fixed to UTC+8.
    # Refuse to turn that known limitation into a confident report claim.
    if source_input.get("resolved_utc_offset") != "+08:00":
        return _unavailable_dayun("unsupported_time_basis")
    if focus_moment is None:
        return _unavailable_dayun("invalid_focus_moment")
    embedded = chart.get("details", {}).get("luck_cycles")
    alternatives = None if isinstance(embedded, dict) else _conditional_luck_cycles(source)
    return project_dayun_facts(
        chart,
        focus_moment,
        conditional_luck_cycles=alternatives,
    )


def load_chart(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PrepareError(f"找不到文件：{path}") from exc
    except json.JSONDecodeError as exc:
        raise PrepareError(f"JSON 解析失败：第 {exc.lineno} 行第 {exc.colno} 列") from exc
    if not isinstance(payload, dict):
        raise PrepareError("盘面顶层必须是对象")
    if payload.get("chart_system") not in {"bazi", "western"}:
        raise PrepareError("chart_system 必须是 bazi 或 western")
    if not isinstance(payload.get("chart"), dict):
        raise PrepareError("盘面缺少 chart 对象")
    return payload


def prepare_payload(
    source: dict[str, Any], *, current_luck_cycle: bool = False,
    report_luck_cycle: bool = False, western_five: bool = False,
) -> dict[str, Any]:
    """Build the identity-minimized payload used by all generative stages."""
    if not isinstance(source, dict):
        raise PrepareError("盘面顶层必须是对象")
    chart_system = source.get("chart_system")
    if chart_system not in {"bazi", "western"}:
        raise PrepareError("chart_system 必须是 bazi 或 western")
    if not isinstance(source.get("chart"), dict):
        raise PrepareError("盘面缺少 chart 对象")

    chart = sanitize_chart(chart_system, source["chart"])
    if western_five and chart_system == "western":
        # Deep reports use exactly the same verified five placements as the
        # quick chart, never its preset prose or unrelated technical fields.
        from western_profile import build_profile
        profile = build_profile(source, include_copy=False)
        chart = {"precision": profile["precision"]}
        planets = {}
        unavailable = []
        for item in profile["items"]:
            key = item["key"]
            if item["status"] != "available" or (key == "ascendant" and source["chart"].get("ascendant_status") not in (None, "available")):
                unavailable.append(key)
                continue
            if key == "ascendant":
                if profile["precision"] == "time-range":
                    chart.setdefault("stable", {})["ascendant"] = {"sign": item["sign"]}
                else:
                    chart["ascendant"] = {"sign": item["sign"]}
            else:
                planets[key] = item["sign"]
        if profile["precision"] in {"date-only", "time-range"}:
            chart.setdefault("stable", {})["planet_signs"] = planets
        else:
            chart["planets"] = {key: {"sign": sign} for key, sign in planets.items()}
        if unavailable:
            chart["unavailable"] = unavailable
    if current_luck_cycle and report_luck_cycle:
        raise PrepareError("current_luck_cycle 与 report_luck_cycle 不能同时启用")
    if current_luck_cycle:
        if chart_system != "bazi":
            raise PrepareError("--current-luck-cycle 只适用于八字盘")
        focus_moment = current_local_moment(source)
        details = chart.setdefault("details", {})
        details["luck_cycle_focus"] = project_luck_cycle(source["chart"], focus_moment)
        _assert_identity_free(chart)
    elif report_luck_cycle and chart_system == "bazi":
        try:
            focus_moment = current_local_moment(source)
        except PrepareError:
            focus_moment = None
        details = chart.setdefault("details", {})
        details["luck_cycle_focus"] = project_report_luck_cycle(source, focus_moment)
        _assert_identity_free(chart)

    if chart_system == "bazi" and chart.get("precision") in {"date-only", "time-range"}:
        possible_pillars = chart.get("possible", {}).get("pillars", {})
        if isinstance(possible_pillars, dict):
            candidate_counts = {
                key: len(values)
                for key, values in possible_pillars.items()
                if isinstance(values, list) and values
            }
            if candidate_counts:
                chart["uncertainty"] = {
                    "variable_pillars": list(candidate_counts),
                    "candidate_counts": candidate_counts,
                }
        # Values from possible branches are useful to the deterministic HTML,
        # but the model only needs to know which pillars are unstable.  Removing
        # the candidates prevents an interpretation stage from choosing one.
        chart.pop("possible", None)
        _assert_identity_free(chart)

    prepared = {
        "schema_version": "1.0.0",
        "analysis_mode": "chart_only",
        "chart_system": chart_system,
        "chart": chart,
    }
    if chart.get("precision") == "date-only":
        prepared["analysis_mode"] = "date_only_stable_facts"
    elif chart.get("precision") == "time-range":
        prepared["analysis_mode"] = "time_range_stable_facts"
    return prepared


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise PrepareError(f"输出文件已存在：{path}")
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare identity-minimized chart context for interpretation.")
    parser.add_argument("chart", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--western-five", action="store_true",
        help="西占深报只投影太阳、上升、月亮、金星、水星的已确定星座",
    )
    parser.add_argument(
        "--current-luck-cycle",
        action="store_true",
        help="仅在用户明确要求当前阶段分析时投影此刻所在的大运",
    )
    parser.add_argument(
        "--report-luck-cycle",
        action="store_true",
        help="深度报告默认的大运事实层；不可用时安全降级而不阻断报告",
    )
    args = parser.parse_args()
    try:
        source = load_chart(args.chart)
        sanitized = prepare_payload(
            source,
            current_luck_cycle=args.current_luck_cycle,
            report_luck_cycle=args.report_luck_cycle,
            western_five=args.western_five,
        )
        atomic_write(args.output, sanitized)
        print(json.dumps({"ok": True, "output": str(args.output)}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": "E_ANALYSIS_CHART", "message": str(exc)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
