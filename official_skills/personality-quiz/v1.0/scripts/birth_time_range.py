"""Explicit civil-clock intervals, shared by both chart systems.

Bounds are half-open, at whole-second resolution. A named Zi belongs to the
given civil date in two pieces; an explicit overnight interval ends next day.
No guessed midpoint or unbounded 'around' time is accepted here.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta
from typing import Any

from engine_common import EngineError, resolve_local_datetime_with_metadata

BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
PERIOD = r"上午|下午|晚上|早上|凌晨|中午|清晨|傍晚|夜里"
SEPARATOR = r"[-~～—–至到]"


def _error(message: str, field: str = "time_ranges") -> EngineError:
    return EngineError("E_INVALID_INPUT", message, [field])


def clock(seconds: int) -> str:
    hour, rest = divmod(seconds, 3600)
    minute, second = divmod(rest, 60)
    return f"{hour:02d}:{minute:02d}" + (f":{second:02d}" if second else "")


def _seconds(text: str, *, end: bool = False) -> int:
    match = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", text)
    if not match:
        raise _error("时间边界必须为 HH:MM 或 HH:MM:SS。")
    hour, minute, second = (int(value or 0) for value in match.groups())
    if hour == 24 and end and minute == second == 0:
        return 86400
    if hour > 23 or minute > 59 or second > 59:
        raise _error("时间边界超出有效时钟范围。")
    return hour * 3600 + minute * 60 + second


def _natural_clock(text: str, inherited_period: str = "", *, end: bool = False) -> tuple[int, str]:
    match = re.fullmatch(rf"({PERIOD})?(\d{{1,2}})(?::(\d{{2}})(?::(\d{{2}}))?|[点时](?:(\d{{1,2}})分?)?)?", text)
    if not match:
        raise _error("请提供明确的起止时间，例如 10:00–12:00。", "birth_time")
    period = match[1] or inherited_period
    hour, minute, second = int(match[2]), int(match[3] or match[5] or 0), int(match[4] or 0)
    if period and not 0 <= hour <= 12:
        raise _error("上午/下午的小时数须为 0–12。", "birth_time")
    if period in {"下午", "晚上", "傍晚", "夜里"} and hour < 12:
        hour += 12
    elif period == "凌晨" and hour == 12:
        hour = 0
    # '中午1点' is 13:00, but '中午10点' is contradictory, not a guess.
    elif period == "中午":
        if hour in {0, 1, 2}:
            hour += 12
        elif hour not in {11, 12}:
            raise _error("中午时段与小时数不一致，请使用 24 小时制。", "birth_time")
    return _seconds(f"{hour:02d}:{minute:02d}:{second:02d}", end=end), period


def parse_text(value: str) -> list[dict[str, Any]]:
    text = re.sub(r"\s+", "", unicodedata.normalize("NFKC", value)).replace("時", "时")
    text = re.sub(r"(?:之间|间)$", "", text)
    pieces = re.split(SEPARATOR, text)
    if len(pieces) != 2:
        raise _error("请提供一组明确的起止时间。", "birth_time")
    start, period = _natural_clock(pieces[0])
    next_day = pieces[1].startswith("次日")
    end, _ = _natural_clock(pieces[1].removeprefix("次日"), "" if next_day else period, end=True)
    if period and not next_day and not re.match(rf"(?:{PERIOD})", pieces[1]) and end < start:
        raise _error("跨上午／下午或午夜的范围请写清两端时段，或使用 24 小时制。", "birth_time")
    if end == start and not next_day:
        raise _error("起止时间不能相同；全天未知请填写不清楚。", "birth_time")
    if next_day or end < start:
        end += 86400
    return normalized_ranges([(start, end)])


def normalized_ranges(ranges: list[tuple[int, int]]) -> list[dict[str, Any]]:
    result = []
    for start, end in ranges:
        if not 0 <= start < 86400 or not start < end <= start + 86400:
            raise _error("单个出生时段须大于零且不超过 24 小时。")
        item: dict[str, Any] = {"start": clock(start), "end": clock(end if end <= 86400 else end - 86400)}
        if end > 86400:
            item["end_day_offset"] = 1
        result.append(item)
    return result


def read_ranges(payload: dict[str, Any]) -> tuple[list[tuple[int, int]], list[dict[str, Any]], str]:
    precision = payload.get("time_precision")
    if not isinstance(precision, dict) or precision.get("kind") not in {"shichen", "range"}:
        raise _error("time_precision.kind 必须是 shichen 或 range。", "time_precision.kind")
    if "minutes" not in precision or precision["minutes"] is not None:
        raise _error("范围输入的 time_precision.minutes 必须是 null。", "time_precision.minutes")
    branch = payload.get("birth_time_branch")
    if precision["kind"] == "shichen":
        if not isinstance(branch, str) or len(branch) != 1 or branch not in BRANCHES:
            raise _error("birth_time_branch 必须是十二地支之一。", "birth_time_branch")
        index = BRANCHES.index(branch)
        ranges = [(0, 3600), (82800, 86400)] if index == 0 else [((2 * index - 1) * 3600, (2 * index + 1) * 3600)]
    else:
        raw = payload.get("time_ranges")
        if not isinstance(raw, list) or len(raw) != 1:
            raise _error("range 须包含一组明确的 time_ranges 起止边界。")
        item = raw[0]
        if not isinstance(item, dict) or set(item) - {"start", "end", "end_day_offset"}:
            raise _error("time_ranges 边界字段无效。")
        if not isinstance(item.get("start"), str) or not isinstance(item.get("end"), str):
            raise _error("time_ranges 必须提供 start 和 end。")
        offset = item.get("end_day_offset", 0)
        if type(offset) is not int or offset not in {0, 1}:
            raise _error("end_day_offset 必须为 0 或 1。")
        start, end = _seconds(item["start"]), _seconds(item["end"], end=True) + 86400 * offset
        ranges = [(start, end)]
    normalized = normalized_ranges(ranges)
    label = "、".join(f"{item['start']}–{'次日 ' if item.get('end_day_offset') else ''}{item['end']}" for item in normalized)
    if precision["kind"] == "shichen":
        label = f"{branch}时（{'当日 ' if branch == '子' else ''}{label}）"
    return ranges, normalized, label


def resolve_range_timezone(midnight: datetime, ranges: list[tuple[int, int]], payload: dict[str, Any]) -> tuple[timedelta, dict[str, Any]]:
    """Validate clock continuity at every represented second, without fold guesses.

    Resolve policy/provenance once, then use the resulting tzinfo for cheap UTC
    round trips. Explicit verified historical offsets are fixed-offset zones.
    """
    from datetime import timezone

    try:
        first, _, metadata = resolve_local_datetime_with_metadata(
            midnight + timedelta(seconds=ranges[0][0]), payload.get("timezone"),
            historical_utc_offset=payload.get("historical_utc_offset"),
        )
        offset = first.utcoffset()
        for start, end in ranges:
            for second in range(start, end):
                naive = midnight + timedelta(seconds=second)
                # Re-apply historical policy if a range crosses its date gate.
                if naive.date() != first.date() and second % 86400 == 0:
                    resolve_local_datetime_with_metadata(naive, payload.get("timezone"), historical_utc_offset=payload.get("historical_utc_offset"))
                for fold in (0, 1):
                    candidate = naive.replace(tzinfo=first.tzinfo, fold=fold)
                    if candidate.utcoffset() != offset or candidate.astimezone(timezone.utc).astimezone(first.tzinfo).replace(tzinfo=None) != naive:
                        raise EngineError("E_TIME_RANGE_UNSUPPORTED_TIMEZONE", "所给范围涉及时钟跳变或回拨，不能选择单一钟制。", ["birth_date", "time_ranges", "timezone"])
        return offset, {key: value for key, value in metadata.items() if key != "fold"}
    except EngineError as exc:
        code = "E_TIME_RANGE_UNSUPPORTED_TIMEZONE" if exc.code in {"E_NONEXISTENT_LOCAL_TIME", "E_AMBIGUOUS_LOCAL_TIME"} else exc.code
        raise EngineError(code, str(exc), ["birth_date" if field == "local_datetime" else field for field in exc.fields]) from exc
