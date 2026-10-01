#!/usr/bin/env python3
"""travel_plan 领域层。

公开卡片继续使用 ``{title,tabs,days}``。模型只写规划字段；客观事实、来源状态、
缓存时间、revision 和恢复信息保存在本地状态中，输出时剥离内部字段。
"""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import math
import os
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

import card_geo
import card_links
import poi
from cli_contract import ContractError, VALID_SOURCE_TYPES, WEB_FACT_FIELDS, validate_operation


DEFAULT_STORE_PATH = Path.home() / ".travel_plan" / "trip.json"
STORE_SCHEMA_VERSION = 4
PROTOCOL_VERSION = "travel-plan.v2.7"
OUTPUT_BUDGET_BYTES = 190 * 1024
CARD_COMPACTION_TARGET_BYTES = 170 * 1024
MAX_STORE_BYTES = 2 * 1024 * 1024
MAX_HISTORY_BYTES = 512 * 1024
MAX_HISTORY_ENTRIES = 8
# 线上最常见的失败形态：模型改完行程就直接答话，这一轮用户屏幕上没有任何卡片。
# 所以每个碰过行程的动作——写入、删除、重置、撤销，连同读到未渲染状态——都要把
# 「这轮还没完」摆到模型面前。措辞按动作定制，让它读起来是在说刚做的那件事，
# 而不是一句可以一扫而过的通用提醒。
RENDER_REQUIRED_PREFIXES = {
    "update_trip_meta": "行程信息已更新",
    "upsert_day": "这一天已写入",
    "upsert_stop": "这个景点已写入",
    "apply_verified_web_facts": "补充信息已写入",
    "delete_stop": "景点已删除",
    "delete_day": "这一天已删除",
    "reset_trip": "行程已重置",
    "undo_last_mutation": "改动已撤销",
}


def _render_required_issue(operation: str = "") -> dict[str, Any]:
    prefix = RENDER_REQUIRED_PREFIXES.get(operation, "改动已保存")
    return {
        "code": "RENDER_REQUIRED",
        "severity": "error",
        "retryable": True,
        "action": "call_render_trip",
        "message": (
            f"{prefix}，但只存进了状态，用户这一轮还看不到任何行程卡："
            "坐标、图片、评分、票价、营业状态和真实路线目前全是空的。"
            "本轮对话必须以一次成功的 render_trip 收尾：现在就调用它，"
            "拿到 rendered=true 之前不要回复用户，也不要用文字复述行程代替卡片。"
        ),
    }
MAX_DAYS = 14
MAX_STOPS_PER_DAY = 12
MAX_POLYLINE_POINTS = 600
MIN_POLYLINE_POINTS = 24
# 直线距离在这以内标步行；直线短于实走，所以比"能走多远"放宽一档。
WALK_MODE_MAX_METERS = 1000
# 每段行程都给出这四种交通方式的距离与时长：主 mode 按距离挑一个走顶层，
# 其余作为并列备选进 options，各自单独算路。顺序即备选展示顺序。
TRANSFER_MODES = ("car", "transit", "walk", "bike")
MAX_RDP_EPSILON = 0.0005
ESTIMATED_POLYLINE_POINT_BYTES = 36
ROUTE_RESPONSE_RESERVE_BYTES = 16 * 1024
DAY_EDITABLE_FIELDS = ("title", "subtitle", "city")
TONGCHENG_FIELDS = (
    "location", "title", "address", "images", "thumbnail", "businessHours",
    "openStatus", "ticketPrice", "rating", "level", "introduction",
    "ticketPurchaseData", "nearbyHotelsData",
)
TENCENT_FIELDS = ("location", "title", "address", "phone", "category")
OBJECTIVE_FIELDS = tuple(dict.fromkeys((*TONGCHENG_FIELDS, *TENCENT_FIELDS)))
ROUTE_FIELDS = ("distance", "duration", "polyline")
STOP_CARD_FIELDS = {
    "id", "name", "summary", "category", "title", "address", "phone",
    "images", "thumbnail", "businessHours", "openStatus", "ticketPrice",
    "rating", "level", "introduction", "location", "ticketPurchaseData",
    "nearbyHotelsData",
    "transferToNext",
}
DAY_CARD_FIELDS = {"title", "subtitle", "city"}
# 景点详情栏这几格必须每次都在，缺值也占位，否则栏目数量会随数据有无而变。
# `rating` 是数字，塞占位串会改掉它的类型，所以不在其列。
CARD_PLACEHOLDER = "暂无"
CARD_PLACEHOLDER_FIELDS = ("ticketPrice", "level")
# 详情栏第二格的小字取 `businessHours`、大字取 `openStatus`。要让小字固定是
# 「营业状态」，只能把这行字本身写进 `businessHours`——端上没有别的入口。
# 代价是营业时段不再上卡，这一格只讲此刻开没开。
CARD_STATUS_LABEL = "营业状态"
WEB_LABELS = {
    "introduction": "景点介绍",
    "ticketPrice": "官方票价",
    "businessHours": "开放时间",
}
FIELD_TTLS = {
    "location": timedelta(days=30),
    "title": timedelta(days=30),
    "category": timedelta(days=30),
    "level": timedelta(days=14),
    "images": timedelta(days=7),
    "thumbnail": timedelta(days=7),
    "introduction": timedelta(days=7),
    "address": timedelta(days=3),
    "phone": timedelta(days=3),
    "ticketPurchaseData": timedelta(days=1),
    "nearbyHotelsData": timedelta(days=1),
    "ticketPrice": timedelta(hours=12),
    "businessHours": timedelta(hours=12),
    "openStatus": timedelta(minutes=30),
}
ROUTE_TTL = timedelta(days=1)
NEGATIVE_TTLS = {
    "no_result": timedelta(minutes=30),
    "provider_unavailable": timedelta(seconds=15),
}


class TravelActionError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        self.code = code
        self.message = message
        self.retryable = retryable
        super().__init__(f"{code}: {message}")


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scope_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


# 沙盒本身按会话分配，单一固定 store 即是会话级状态。路径绝不能由会话类环境变量
# 派生：模型一旦自行导出一个每次都变的标识，同一轮的多次写入就会落到不同文件。
def _resolve_store_path(environ: dict[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    override = _text(env.get("MY_TRAVEL_STORE"))
    return Path(override) if override else DEFAULT_STORE_PATH


def _state_scope(path: Path) -> str:
    return "store-" + _scope_digest(str(path.expanduser().resolve()))


def _content_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def _event_id(
    state_scope: str,
    trip_id: str,
    revision: int,
    update_mode: str,
    content_hash: str,
) -> str:
    return _content_hash([state_scope, trip_id, revision, update_mode, content_hash])


@contextmanager
def _store_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _validate_store_trip(trip: object) -> dict[str, Any] | None:
    if trip is None:
        return None
    if not isinstance(trip, dict):
        raise TravelActionError("STORE_CORRUPTED", "本地行程 trip 必须是对象。")
    internal = trip.get("_internal")
    if internal is not None:
        if not isinstance(internal, dict):
            raise TravelActionError("STORE_CORRUPTED", "本地行程 _internal 必须是对象。")
        for key in ("revision", "planRevision", "renderedPlanRevision"):
            revision = internal.get(key, 0)
            if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
                raise TravelActionError("STORE_CORRUPTED", f"本地行程 {key} 无效。")
    days = trip.get("days", {})
    if not isinstance(days, dict):
        raise TravelActionError("STORE_CORRUPTED", "本地行程 days 必须是对象。")
    for day_id, day in days.items():
        if not isinstance(day_id, str) or not isinstance(day, dict):
            raise TravelActionError("STORE_CORRUPTED", "本地行程包含无效 day 节点。")
        stops = day.get("stops", [])
        if not isinstance(stops, list) or any(not isinstance(stop, dict) for stop in stops):
            raise TravelActionError("STORE_CORRUPTED", f"{day_id}.stops 格式错误。")
    return trip


def _validate_history(value: object) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TravelActionError("STORE_CORRUPTED", "本地行程 history 必须是数组。")
    history: list[dict[str, Any]] = []
    for entry in value:
        if not isinstance(entry, dict):
            raise TravelActionError("STORE_CORRUPTED", "本地行程 history 包含无效条目。")
        unknown = set(entry) - {"revision", "operation", "savedAt", "trip"}
        if unknown or "trip" not in entry:
            raise TravelActionError("STORE_CORRUPTED", "本地行程 history 条目格式错误。")
        revision = entry.get("revision")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
            raise TravelActionError("STORE_CORRUPTED", "本地行程 history revision 无效。")
        _validate_store_trip(entry.get("trip"))
        history.append(copy.deepcopy(entry))
    return history


def _legacy_trip_id(trip: dict[str, Any]) -> str:
    planning = {
        "createdAt": trip.get("createdAt"),
        "title": trip.get("title"),
        "destination": trip.get("destination"),
        "days": trip.get("days"),
    }
    canonical = json.dumps(planning, ensure_ascii=False, sort_keys=True, default=str)
    return "trip-legacy-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _migrate_trip(trip: dict[str, Any] | None, root_revision: int) -> dict[str, Any] | None:
    if trip is None:
        return None
    if not _text(trip.get("tripId")):
        trip["tripId"] = _legacy_trip_id(trip)
    internal = _internal(trip)
    legacy_revision = internal.pop("revision", 0)
    if not isinstance(legacy_revision, int) or isinstance(legacy_revision, bool):
        legacy_revision = 0
    if not isinstance(internal.get("planRevision"), int):
        internal["planRevision"] = max(root_revision, legacy_revision, 1)
    if not isinstance(internal.get("renderedPlanRevision"), int):
        internal["renderedPlanRevision"] = (
            0 if internal.get("dirty", True) else internal["planRevision"]
        )
    return trip


def _read_envelope(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            raise TravelActionError("STORE_CORRUPTED", "本地行程文件为空，未进行自动覆盖。")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise TravelActionError("STORE_CORRUPTED", "本地行程数据损坏，未进行自动覆盖。") from exc
    if not isinstance(data, dict):
        raise TravelActionError("STORE_CORRUPTED", "本地行程根节点格式错误。")
    if "trip" not in data:
        raise TravelActionError("STORE_CORRUPTED", "本地行程缺少 trip 信封，未进行自动覆盖。")
    unknown = set(data) - {"schemaVersion", "revision", "history", "trip"}
    if unknown:
        raise TravelActionError("STORE_VERSION_UNSUPPORTED", "本地行程包含未知顶层字段，已拒绝覆盖。")
    version = data.get("schemaVersion", 1)
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise TravelActionError("STORE_CORRUPTED", "本地行程 schemaVersion 无效。")
    if version > STORE_SCHEMA_VERSION:
        raise TravelActionError(
            "STORE_VERSION_UNSUPPORTED",
            f"本地行程版本 {version} 高于当前支持版本 {STORE_SCHEMA_VERSION}，已拒绝覆盖。",
        )
    root_revision = data.get("revision")
    if root_revision is not None and (
        not isinstance(root_revision, int) or isinstance(root_revision, bool) or root_revision < 0
    ):
        raise TravelActionError("STORE_CORRUPTED", "本地行程根 revision 无效。")
    trip = _validate_store_trip(data.get("trip"))
    history = _validate_history(data.get("history"))
    normalized_revision = root_revision if isinstance(root_revision, int) else _revision(trip)
    return {
        "schemaVersion": version,
        "revision": normalized_revision,
        "history": history,
        "trip": _migrate_trip(copy.deepcopy(trip), normalized_revision),
    }


def _load(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    data = _read_envelope(path)
    return _validate_store_trip(data.get("trip"))


def _load_state(path: Path) -> tuple[dict[str, Any] | None, int]:
    if not path.exists():
        return None, 0
    envelope = _read_envelope(path)
    return _validate_store_trip(envelope.get("trip")), int(envelope["revision"])


def _revision(trip: dict[str, Any] | None) -> int:
    """仅用于迁移 schema v1/v2；运行时 revision 只认信封根字段。"""
    internal = trip.get("_internal") if isinstance(trip, dict) else None
    value = internal.get("revision") if isinstance(internal, dict) else 0
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _disk_revision(path: Path) -> int:
    if not path.exists():
        return 0
    data = _read_envelope(path)
    return int(data["revision"])


def _planning_snapshot(trip: dict[str, Any] | None) -> dict[str, Any] | None:
    if trip is None:
        return None
    snapshot: dict[str, Any] = {
        "tripId": _text(trip.get("tripId")) or _legacy_trip_id(trip),
        "title": _text(trip.get("title")),
        "destination": _text(trip.get("destination")),
        "createdAt": _text(trip.get("createdAt")) or _now_iso(),
        "days": {},
        "_internal": {
            "dirty": True,
            "dirtyAt": _now_iso(),
            "planRevision": _plan_revision(trip),
            "renderedPlanRevision": 0,
        },
    }
    for day_id, day in (trip.get("days") or {}).items():
        if not isinstance(day_id, str) or not isinstance(day, dict):
            continue
        day_copy: dict[str, Any] = {
            key: copy.deepcopy(day[key])
            for key in ("label", "title", "subtitle", "city")
            if day.get(key) not in (None, "")
        }
        day_copy["stops"] = []
        for stop in day.get("stops") or []:
            if not isinstance(stop, dict):
                continue
            item = {
                "id": _text(stop.get("id")) or _new_id("stop"),
                "name": _text(stop.get("name")),
                "summary": _text(stop.get("summary")),
                "category": "景点",
            }
            day_copy["stops"].append(item)
        snapshot["days"][day_id] = day_copy
    return snapshot


def _trim_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trimmed = copy.deepcopy(history[-MAX_HISTORY_ENTRIES:])
    while trimmed:
        size = len(json.dumps(trimmed, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        if size <= MAX_HISTORY_BYTES:
            break
        trimmed.pop(0)
    return trimmed


def _save(
    path: Path,
    trip: dict[str, Any] | None,
    expected_revision: int,
    *,
    operation: str = "",
    record_history: bool = False,
    history_override: list[dict[str, Any]] | None = None,
    card_preview: dict[str, Any] | None = None,
) -> int:
    envelope = (
        _read_envelope(path)
        if path.exists()
        else {"schemaVersion": STORE_SCHEMA_VERSION, "revision": 0, "history": [], "trip": None}
    )
    current = int(envelope["revision"])
    if current != expected_revision:
        raise TravelActionError(
            "REVISION_CONFLICT",
            "行程在本次操作期间被其他写入修改，请重新执行一次当前动作。",
            retryable=True,
        )
    if trip is not None:
        _ensure_recoverable_state(trip, card_preview=card_preview)
        _internal(trip).pop("revision", None)
    history = copy.deepcopy(history_override if history_override is not None else envelope.get("history", []))
    if record_history:
        history.append({
            "revision": current,
            "operation": operation,
            "savedAt": _now_iso(),
            "trip": _planning_snapshot(envelope.get("trip")),
        })
    history = _trim_history(history)
    payload = {
        "schemaVersion": STORE_SCHEMA_VERSION,
        "revision": expected_revision + 1,
        "history": history,
        "trip": trip,
    }
    raw_size = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    while history and raw_size > MAX_STORE_BYTES:
        history.pop(0)
        payload["history"] = history
        raw_size = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if raw_size > MAX_STORE_BYTES:
        raise TravelActionError("STATE_TOO_LARGE", "行程状态超过安全存储上限，请减少天数或景点文案。")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
    return expected_revision + 1


def _internal(trip: dict[str, Any]) -> dict[str, Any]:
    value = trip.setdefault("_internal", {})
    if not isinstance(value, dict):
        value = {}
        trip["_internal"] = value
    return value


def _plan_revision(trip: dict[str, Any]) -> int:
    value = _internal(trip).get("planRevision", 0)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _fact_meta(stop: dict[str, Any]) -> dict[str, Any]:
    value = stop.setdefault("_factMeta", {})
    if not isinstance(value, dict):
        value = {}
        stop["_factMeta"] = value
    for key in ("fields", "providers", "web"):
        if not isinstance(value.get(key), dict):
            value[key] = {}
    return value


def _mark_dirty(trip: dict[str, Any], *, plan_changed: bool = True) -> None:
    internal = _internal(trip)
    if plan_changed:
        internal["planRevision"] = _plan_revision(trip) + 1
    internal["dirty"] = True
    internal["dirtyAt"] = _now_iso()


def _mark_rendered(trip: dict[str, Any]) -> None:
    internal = _internal(trip)
    internal["dirty"] = False
    internal["renderedAt"] = _now_iso()
    internal["renderedPlanRevision"] = _plan_revision(trip)


def _field_source(stop: dict[str, Any], field: str) -> str:
    meta = stop.get("_factMeta")
    fields = meta.get("fields") if isinstance(meta, dict) else None
    record = fields.get(field) if isinstance(fields, dict) else None
    return _text(record.get("source")) if isinstance(record, dict) else ""


def _tencent_poi_id(stop: dict[str, Any]) -> str:
    # touid 只在坐标同样来自腾讯时才给：坐标换了源，引导点就会和坐标对不上而失效
    if not isinstance(stop, dict) or _field_source(stop, "location") != "tencent":
        return ""
    meta = stop.get("_factMeta")
    providers = meta.get("providers") if isinstance(meta, dict) else None
    record = providers.get("tencent") if isinstance(providers, dict) else None
    detail = record.get("meta") if isinstance(record, dict) else None
    return _text(detail.get("providerId")) if isinstance(detail, dict) else ""


def _parse_timestamp(value: object) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _record_fresh(record: dict[str, Any], ttl: timedelta) -> bool:
    fetched = _parse_timestamp(record.get("fetchedAt"))
    return bool(fetched and datetime.now(timezone.utc) - fetched <= ttl)


def _provider_needs_refresh(
    stop: dict[str, Any],
    provider: str,
    fields: tuple[str, ...],
    city: str,
) -> bool:
    meta = _fact_meta(stop)
    providers = meta.get("providers") if isinstance(meta.get("providers"), dict) else {}
    record = providers.get(provider) if isinstance(providers.get(provider), dict) else None
    if not isinstance(record, dict):
        return True
    if _text(record.get("queryName")) != _text(stop.get("name")):
        return True
    if _text(record.get("queryCity")) != city:
        return True
    status = _text(record.get("status"))
    negative_ttl = NEGATIVE_TTLS.get(status)
    if status == "no_result" and record.get("batchEmpty") is True:
        # 整批零结果更像数据源异常而不是「确实查不到」，不能按半小时负缓存锁住重试
        negative_ttl = NEGATIVE_TTLS["provider_unavailable"]
    if negative_ttl is not None:
        return not _record_fresh(record, negative_ttl)
    reported_fields = record.get("fields") if isinstance(record.get("fields"), dict) else {}
    field_records = meta.get("fields") if isinstance(meta.get("fields"), dict) else {}
    for field in fields:
        ttl = FIELD_TTLS.get(field, timedelta(days=1))
        field_record = field_records.get(field) if isinstance(field_records.get(field), dict) else {}
        if (
            _field_source(stop, field) == provider
            and stop.get(field) not in (None, "", [], {})
            and _record_fresh(field_record, ttl)
        ):
            continue
        if reported_fields.get(field) in {"present", "not_returned", "confirmed_missing"} and _record_fresh(record, ttl):
            continue
        return True
    return False


def _record_provider(stop: dict[str, Any], provider: str, report: dict[str, Any], city: str) -> None:
    safe: dict[str, Any] = {
        "status": _text(report.get("status")) or "unknown",
        "fetchedAt": _now_iso(),
        "queryName": _text(stop.get("name")),
        "queryCity": city,
    }
    for key in (
        "fields",
        "meta",
        "error",
        "candidates",
        "selectionRequired",
        "relayQuery",
        "batchEmpty",
    ):
        value = report.get(key)
        if isinstance(value, (bool, dict, int, float, str, list)):
            safe[key] = copy.deepcopy(value)
    values = report.get("values") if isinstance(report.get("values"), dict) else {}
    safe["entity"] = {
        key: copy.deepcopy(values[key])
        for key in ("title", "location", "address")
        if values.get(key) not in (None, "", [], {})
    }
    _fact_meta(stop)["providers"][provider] = safe


def _set_fact(stop: dict[str, Any], field: str, value: Any, source: str) -> None:
    if value in (None, "", [], {}):
        return
    stop[field] = copy.deepcopy(value)
    _fact_meta(stop)["fields"][field] = {
        "source": source,
        "status": "present",
        "fetchedAt": _now_iso(),
    }


def _clear_fact(
    stop: dict[str, Any],
    field: str,
    providers: set[str],
    *,
    status: str = "not_returned",
) -> None:
    source = _field_source(stop, field)
    if source in providers or not source:
        stop.pop(field, None)
        _fact_meta(stop)["fields"][field] = {
            "source": next(iter(providers)) if len(providers) == 1 else "",
            "status": status,
            "fetchedAt": _now_iso(),
        }


def _clear_objective_facts(stop: dict[str, Any]) -> None:
    for field in OBJECTIVE_FIELDS:
        stop.pop(field, None)
    stop.pop("_factMeta", None)
    stop["category"] = "景点"


def _purge_unattributed_facts(days: dict[str, Any]) -> bool:
    """旧版本没有来源元数据，无法区分模型值和 API 值；首次新渲染时安全清理。"""
    purged = False
    for day in days.values():
        if not isinstance(day, dict):
            continue
        if "location" in day:
            day.pop("location", None)
            purged = True
        for stop in day.get("stops") or []:
            if not isinstance(stop, dict):
                continue
            for field in OBJECTIVE_FIELDS:
                if field == "category":
                    continue
                if field in stop and not _field_source(stop, field):
                    stop.pop(field, None)
                    purged = True
            stop["category"] = "景点"
    return purged


def _clear_route_target(target: dict[str, Any]) -> None:
    for field in ROUTE_FIELDS:
        target.pop(field, None)
    target.pop("_routeMeta", None)
    for option in target.get("options") or []:
        if isinstance(option, dict):
            for field in ROUTE_FIELDS:
                option.pop(field, None)
            option.pop("_routeMeta", None)


def _invalidate_day_routes(day: dict[str, Any], stop_index: int | None = None) -> None:
    day.pop("routeToNext", None)
    stops = day.get("stops") or []
    indexes = range(len(stops)) if stop_index is None else {stop_index - 1, stop_index}
    for index in indexes:
        if not isinstance(index, int) or index < 0 or index >= len(stops):
            continue
        stop = stops[index]
        if not isinstance(stop, dict):
            continue
        transfer = stop.get("transferToNext")
        if isinstance(transfer, dict):
            _clear_route_target(transfer)


def _invalidate_routes(days: dict[str, Any]) -> None:
    for day in days.values():
        if isinstance(day, dict):
            _invalidate_day_routes(day)


def _stable_id(name: str, taken: set[str] | None = None) -> str:
    base = "stop-" + hashlib.md5(name.encode("utf-8")).hexdigest()[:8]
    if not taken or base not in taken:
        return base
    index = 2
    while f"{base}-{index}" in taken:
        index += 1
    return f"{base}-{index}"


def _taken_ids(days: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for day in days.values():
        if not isinstance(day, dict):
            continue
        for stop in day.get("stops") or []:
            if isinstance(stop, dict) and _text(stop.get("id")):
                result.add(_text(stop["id"]))
    return result


def _new_stop(value: dict[str, Any], taken: set[str], stop_id: str = "") -> dict[str, Any]:
    name = _text(value.get("name"))
    summary = _text(value.get("summary"))
    if not name:
        raise TravelActionError("INVALID_ARGUMENT", "景点必须带 name")
    if not summary:
        raise TravelActionError("INVALID_ARGUMENT", f"景点「{name}」必须带规划型 summary")
    identifier = stop_id or _stable_id(name, taken)
    return {"id": identifier, "name": name, "summary": summary, "category": "景点"}


def _normalize_stops(raw_stops: object, taken: set[str]) -> list[dict[str, Any]]:
    if not isinstance(raw_stops, list) or not raw_stops:
        raise TravelActionError("INVALID_ARGUMENT", "每天至少需要一个景点。")
    if len(raw_stops) > MAX_STOPS_PER_DAY:
        raise TravelActionError("INVALID_ARGUMENT", f"每天最多 {MAX_STOPS_PER_DAY} 个景点。")
    stops = []
    for item in raw_stops:
        if not isinstance(item, dict):
            raise TravelActionError("INVALID_ARGUMENT", "stops 中每一项必须是对象。")
        stop = _new_stop(item, taken)
        taken.add(stop["id"])
        stops.append(stop)
    return stops


def _location(value: object) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    if isinstance(value.get("lat"), bool) or isinstance(value.get("lng"), bool):
        return None
    try:
        lat, lng = float(value["lat"]), float(value["lng"])
    except (KeyError, TypeError, ValueError):
        return None
    if not math.isfinite(lat) or not math.isfinite(lng):
        return None
    if not -90 <= lat <= 90 or not -180 <= lng <= 180:
        return None
    return {"lat": lat, "lng": lng}


def _day_city(day: dict[str, Any], destination: str) -> str:
    return _text(day.get("city")) or destination


def _apply_provider_fields(
    stop: dict[str, Any],
    report: dict[str, Any],
    provider: str,
    fields: tuple[str, ...],
) -> None:
    status = _text(report.get("status"))
    values = report.get("values") if isinstance(report.get("values"), dict) else {}
    field_statuses = report.get("fields") if isinstance(report.get("fields"), dict) else {}
    if status in {"present", "partial"}:
        for field in fields:
            if values.get(field) not in (None, "", [], {}):
                _set_fact(stop, field, values[field], provider)
            elif field_statuses.get(field) == "confirmed_missing":
                _clear_fact(stop, field, {provider})


def _provider_batches(
    days: dict[str, Any],
    destination: str,
    provider: str,
    fields: tuple[str, ...],
) -> dict[str, list[str]]:
    batches: dict[str, list[str]] = {}
    for day in days.values():
        if not isinstance(day, dict):
            continue
        city = _day_city(day, destination)
        names = batches.setdefault(city, [])
        for stop in day.get("stops") or []:
            if not isinstance(stop, dict):
                continue
            name = _text(stop.get("name"))
            if name and name not in names and _provider_needs_refresh(stop, provider, fields, city):
                names.append(name)
    return {city: names for city, names in batches.items() if names}


def _batch_failure(names: list[str], provider: str, exc: Exception) -> dict[str, Any]:
    error = {
        "code": "INTERNAL_PROVIDER_ERROR",
        "provider": provider,
        "message": str(exc)[:300],
        "retryable": True,
    }
    return {
        "items": {},
        "reports": {
            name: {"status": "provider_unavailable", "error": error}
            for name in names
        },
    }


def _fetch_tongcheng_batches(
    batches: dict[str, list[str]],
    *,
    defer_hotels: bool = False,
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for city, names in batches.items():
        try:
            results[city] = poi.resolve_with_status(city, names, defer_hotels=defer_hotels)
        except Exception as exc:
            results[city] = _batch_failure(names, "tongcheng", exc)
    return results


def _finish_tongcheng_hotels(
    days: dict[str, Any],
    destination: str,
    results: dict[str, dict[str, Any]],
) -> None:
    """收口延后的酒店查询，并把晚到的 nearbyHotelsData 补写进景点与来源记录。"""
    for response in results.values():
        finish = response.get("finishHotels") if isinstance(response, dict) else None
        if callable(finish):
            try:
                finish()
            except Exception:  # 酒店入口缺失不该影响已经渲染好的行程
                pass
            response.pop("finishHotels", None)
    for day in days.values():
        if not isinstance(day, dict):
            continue
        city = _day_city(day, destination)
        response = results.get(city)
        items = response.get("items") if isinstance(response, dict) else None
        if not isinstance(items, dict):
            continue
        for stop in day.get("stops") or []:
            if not isinstance(stop, dict):
                continue
            values = items.get(_text(stop.get("name")))
            nearby = values.get("nearbyHotelsData") if isinstance(values, dict) else None
            if not nearby:
                continue
            _set_fact(stop, "nearbyHotelsData", nearby, "tongcheng")
            # 来源记录是在酒店结果之前存下的，这里要同步，否则下一次渲染会
            # 认为这个字段从没拿到过而重查。
            record = _provider_record(stop, "tongcheng")
            fields = record.get("fields") if isinstance(record, dict) else None
            if isinstance(fields, dict):
                fields["nearbyHotelsData"] = "present"


def _fetch_tencent_batches(batches: dict[str, list[str]]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for city, names in batches.items():
        try:
            results[city] = card_geo.resolve_places_with_status(names, city)
        except Exception as exc:
            results[city] = _batch_failure(names, "tencent", exc)
    return results


def _issue(
    code: str,
    message: str,
    *,
    provider: str = "",
    retryable: bool = False,
    action: str = "none",
    scope: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "code": code,
        "severity": "warning",
        "provider": provider,
        "retryable": retryable,
        "action": action,
        "message": message,
    }
    if scope:
        value["scope"] = copy.deepcopy(scope)
    value.update(copy.deepcopy(extra))
    return value


def _result_report(
    results: dict[str, dict[str, Any]],
    city: str,
    name: str,
) -> dict[str, Any]:
    response = results.get(city)
    reports = response.get("reports") if isinstance(response, dict) else None
    report = reports.get(name) if isinstance(reports, dict) else None
    return report if isinstance(report, dict) else {}


def _report_official_name(report: dict[str, Any], fallback: str) -> str:
    candidates = report.get("candidates")
    if isinstance(candidates, list):
        for candidate in candidates:
            if isinstance(candidate, dict) and _text(candidate.get("name")):
                return _text(candidate["name"])
    values = report.get("values") if isinstance(report.get("values"), dict) else {}
    entity = report.get("entity") if isinstance(report.get("entity"), dict) else {}
    return _text(values.get("title")) or _text(entity.get("title")) or fallback


def _merge_relay_result(
    target: dict[str, dict[str, Any]],
    city: str,
    original_name: str,
    relay_name: str,
    relay_response: dict[str, Any],
) -> bool:
    reports = relay_response.get("reports") if isinstance(relay_response.get("reports"), dict) else {}
    report = reports.get(relay_name) if isinstance(reports.get(relay_name), dict) else None
    if not isinstance(report, dict) or _text(report.get("status")) != "present":
        current = _result_report(target, city, original_name)
        if current:
            current["relayQuery"] = relay_name
        return False
    destination = target.setdefault(city, {"items": {}, "reports": {}})
    destination_reports = destination.setdefault("reports", {})
    destination_items = destination.setdefault("items", {})
    copied_report = copy.deepcopy(report)
    copied_report["relayQuery"] = relay_name
    destination_reports[original_name] = copied_report
    relay_items = relay_response.get("items") if isinstance(relay_response.get("items"), dict) else {}
    if isinstance(relay_items.get(relay_name), dict):
        destination_items[original_name] = copy.deepcopy(relay_items[relay_name])
    return True


def _relay_missing_provider_results(
    days: dict[str, Any],
    destination: str,
    tongcheng_results: dict[str, dict[str, Any]],
    tencent_results: dict[str, dict[str, Any]],
    tongcheng_batches: dict[str, list[str]],
    tencent_batches: dict[str, list[str]],
) -> dict[str, int]:
    """用另一数据源给出的官方名重查零候选源，不维护任何别名规则。"""
    tc_relay: dict[str, dict[str, str]] = {}
    tx_relay: dict[str, dict[str, str]] = {}
    for day in days.values():
        if not isinstance(day, dict):
            continue
        city = _day_city(day, destination)
        for stop in day.get("stops") or []:
            if not isinstance(stop, dict):
                continue
            name = _text(stop.get("name"))
            if not name:
                continue
            tc_report = _result_report(tongcheng_results, city, name)
            tx_report = _result_report(tencent_results, city, name)
            tc_counterpart = tc_report or _provider_record(stop, "tongcheng") or {}
            tx_counterpart = tx_report or _provider_record(stop, "tencent") or {}
            if (
                name in tongcheng_batches.get(city, [])
                and _text(tc_report.get("status")) == "no_result"
                and _text(tx_counterpart.get("status")) == "present"
            ):
                alias = _report_official_name(tx_counterpart, name)
                if alias and alias != name:
                    tc_relay.setdefault(city, {})[name] = alias
            if (
                name in tencent_batches.get(city, [])
                and _text(tx_report.get("status")) == "no_result"
                and _text(tc_counterpart.get("status")) == "present"
            ):
                alias = _report_official_name(tc_counterpart, name)
                if alias and alias != name:
                    tx_relay.setdefault(city, {})[name] = alias

    stats = {"tongcheng": 0, "tencent": 0}
    for city, mappings in tc_relay.items():
        aliases = list(dict.fromkeys(mappings.values()))
        try:
            response = poi.resolve_with_status(city, aliases)
        except Exception as exc:
            response = _batch_failure(aliases, "tongcheng", exc)
        stats["tongcheng"] += len(aliases)
        for original, alias in mappings.items():
            _merge_relay_result(tongcheng_results, city, original, alias, response)
    for city, mappings in tx_relay.items():
        aliases = list(dict.fromkeys(mappings.values()))
        try:
            response = card_geo.resolve_places_with_status(aliases, city)
        except Exception as exc:
            response = _batch_failure(aliases, "tencent", exc)
        stats["tencent"] += len(aliases)
        for original, alias in mappings.items():
            _merge_relay_result(tencent_results, city, original, alias, response)
    return stats


def _append_candidate_issue(
    issues: list[dict[str, Any]],
    warnings: list[str],
    report: dict[str, Any],
    provider: str,
    day_id: str,
    stop: dict[str, Any],
) -> None:
    candidates = report.get("candidates")
    if report.get("selectionRequired") is not True or not isinstance(candidates, list):
        return
    name = _text(stop.get("name"))
    message = (
        f"{provider} 对「{name}」没有唯一同名实体，已先填入排序第一的候选；"
        "请根据 candidates 核对，必要时用官方名修改景点。"
    )
    warnings.append(message)
    issues.append(
        _issue(
            "POI_CANDIDATE_AMBIGUOUS",
            message,
            provider=provider,
            action="rename_stop",
            scope={"dayId": day_id, "stopId": _text(stop.get("id"))},
            candidates=copy.deepcopy(candidates[:5]),
        )
    )


def _fill_tongcheng_details(
    days: dict[str, Any],
    destination: str,
    warnings: list[str],
    issues: list[dict[str, Any]],
    prefetched: dict[str, dict[str, Any]] | None = None,
) -> None:
    unavailable: list[str] = []
    # 同程零结果会让介绍、图片、票价、开放时间整体留空，必须上报而不是静默通过
    not_found: list[tuple[str, str, str]] = []
    empty_cities: dict[str, list[tuple[str, str, str]]] = {}
    grouped: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for day_id, day in days.items():
        city = _day_city(day, destination)
        grouped.setdefault(city, []).extend(
            (day_id, stop)
            for stop in day.get("stops") or []
            if isinstance(stop, dict)
        )
    for city, entries in grouped.items():
        names = [
            _text(stop.get("name"))
            for _, stop in entries
            if _provider_needs_refresh(stop, "tongcheng", TONGCHENG_FIELDS, city)
        ]
        names = list(dict.fromkeys(name for name in names if name))
        if names:
            response = (
                prefetched.get(city, {"items": {}, "reports": {}})
                if prefetched is not None
                else poi.resolve_with_status(city, names)
            )
        else:
            response = {"items": {}, "reports": {}}
        items = response.get("items") if isinstance(response.get("items"), dict) else {}
        reports = response.get("reports") if isinstance(response.get("reports"), dict) else {}
        queried = set(names)
        for day_id, stop in entries:
            name = _text(stop.get("name"))
            if name in queried:
                report = reports.get(name) if isinstance(reports.get(name), dict) else {"status": "provider_unavailable"}
                if name in items:
                    report = {**report, "values": items[name]}
                _record_provider(stop, "tongcheng", report, city)
                _apply_provider_fields(stop, report, "tongcheng", TONGCHENG_FIELDS)
                _append_candidate_issue(issues, warnings, report, "tongcheng", day_id, stop)
            else:
                # 命中负缓存而跳过查询的站点也要照旧上报，否则卡片空着回包却一片干净
                report = _provider_record(stop, "tongcheng") or {}
            status = _text(report.get("status"))
            if status == "provider_unavailable":
                unavailable.append(f"{day_id}/{name}")
            elif status == "no_result":
                entry = (day_id, _text(stop.get("id")), name)
                if report.get("batchEmpty") is True:
                    empty_cities.setdefault(city, []).append(entry)
                else:
                    not_found.append(entry)
    if unavailable:
        warnings.append("同程暂不可用，已保留上次有效缓存（如有）；受影响：" + "、".join(unavailable))
    for city, entries in empty_cities.items():
        message = (
            f"同程对「{city}」的 {len(entries)} 个景点全部返回零结果，"
            "景点介绍、图片、票价与开放时间都会留空。整批为空通常是同程数据源异常，"
            "可重新 render_trip 重试一次。"
        )
        warnings.append(message)
        issues.append(
            _issue(
                "PROVIDER_EMPTY_BATCH",
                message,
                provider="tongcheng",
                retryable=True,
                action="retry_render",
                scopes=[{"dayId": day_id, "stopId": stop_id} for day_id, stop_id, _ in entries],
            )
        )
    if not_found:
        message = (
            "同程未收录这些景点，其介绍、图片与票价会留空："
            + "、".join(name for _, _, name in not_found)
            + "；可换成更规范的官方名后重新 render_trip。"
        )
        warnings.append(message)
        issues.append(
            _issue(
                "PROVIDER_NO_RESULT",
                message,
                provider="tongcheng",
                action="rename_stop",
                scopes=[{"dayId": day_id, "stopId": stop_id} for day_id, stop_id, _ in not_found],
            )
        )


def _fill_tencent_places(
    days: dict[str, Any],
    destination: str,
    warnings: list[str],
    issues: list[dict[str, Any]],
    prefetched: dict[str, dict[str, Any]] | None = None,
) -> None:
    unavailable: list[str] = []
    grouped: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for day_id, day in days.items():
        city = _day_city(day, destination)
        grouped.setdefault(city, []).extend(
            (day_id, stop)
            for stop in day.get("stops") or []
            if isinstance(stop, dict)
        )
    for city, entries in grouped.items():
        names = [
            _text(stop.get("name"))
            for _, stop in entries
            if _provider_needs_refresh(stop, "tencent", TENCENT_FIELDS, city)
        ]
        names = list(dict.fromkeys(name for name in names if name))
        response = (
            prefetched.get(city, {"reports": {}})
            if prefetched is not None
            else (card_geo.resolve_places_with_status(names, city) if names else {"reports": {}})
        )
        reports = response.get("reports") if isinstance(response.get("reports"), dict) else {}
        queried = set(names)
        for day_id, stop in entries:
            name = _text(stop.get("name"))
            if name not in queried:
                _set_fact(stop, "category", "景点", "script")
                continue
            report = reports.get(name) if isinstance(reports.get(name), dict) else {"status": "provider_unavailable"}
            _record_provider(stop, "tencent", report, city)
            _apply_provider_fields(stop, report, "tencent", TENCENT_FIELDS)
            _set_fact(stop, "category", "景点", "script")
            _append_candidate_issue(issues, warnings, report, "tencent", day_id, stop)
            status = _text(report.get("status"))
            if status == "provider_unavailable":
                unavailable.append(f"{day_id}/{name}")
    if unavailable:
        warnings.append("腾讯地点服务暂不可用，已保留上次有效缓存（如有）；受影响：" + "、".join(unavailable))


def _fill_missing_locations(
    days: dict[str, Any],
    destination: str,
    warnings: list[str],
    issues: list[dict[str, Any]],
) -> int:
    entries: list[tuple[str, str, dict[str, Any]]] = []
    for day_id, day in days.items():
        city = _day_city(day, destination)
        for stop in day.get("stops") or []:
            if isinstance(stop, dict) and not _location(stop.get("location")):
                entries.append((day_id, city, stop))
    if not entries:
        return 0

    def fetch(entry: tuple[str, str, dict[str, Any]]) -> dict[str, Any]:
        _, city, stop = entry
        query_name = _text(stop.get("title")) or _text(stop.get("name"))
        try:
            return card_geo.resolve_location_by_address(query_name, city)
        except Exception as exc:
            return {
                "status": "provider_unavailable",
                "error": {
                    "code": "INTERNAL_PROVIDER_ERROR",
                    "provider": "tencent-geocode",
                    "message": str(exc)[:300],
                    "retryable": True,
                },
            }

    with ThreadPoolExecutor(max_workers=min(card_geo.MAX_WORKERS, len(entries))) as pool:
        reports = list(pool.map(fetch, entries))

    for (day_id, city, stop), report in zip(entries, reports):
        _record_provider(stop, "tencent-geocode", report, city)
        values = report.get("values") if isinstance(report.get("values"), dict) else {}
        location = _location(values.get("location"))
        scope = {"dayId": day_id, "stopId": _text(stop.get("id"))}
        name = _text(stop.get("name"))
        if _text(report.get("status")) == "present" and location:
            _set_fact(stop, "location", location, "tencent-geocode")
            message = f"「{name}」的坐标由腾讯地址解析兜底获得。"
            warnings.append(message)
            issues.append(
                _issue(
                    "LOCATION_FROM_GEOCODE",
                    message,
                    provider="tencent-geocode",
                    action="none",
                    scope=scope,
                )
            )
            continue
        message = f"「{name}」在跨源接力与地址解析后仍没有可确认坐标。"
        warnings.append(message)
        issues.append(
            _issue(
                "LOCATION_UNRESOLVED",
                message,
                provider="tencent",
                action="rename_or_replace_stop",
                scope=scope,
            )
        )
    return len(entries)


def _entity_city(value: object) -> str:
    text = _text(value)
    for suffix in ("特别行政区", "自治区", "自治州", "地区", "市"):
        if text.endswith(suffix) and len(text) > len(suffix):
            return text[:-len(suffix)]
    return text


def _entity_regions(meta: dict[str, Any]) -> set[str]:
    return {
        region
        for region in (
            _entity_city(meta.get("city")),
            _entity_city(meta.get("district")),
        )
        if region
    }


def _provider_record(stop: dict[str, Any], provider: str) -> dict[str, Any] | None:
    providers = _fact_meta(stop).get("providers")
    value = providers.get(provider) if isinstance(providers, dict) else None
    return value if isinstance(value, dict) else None


def _same_provider_entity(
    stop: dict[str, Any],
    tongcheng: dict[str, Any],
    tencent: dict[str, Any],
) -> tuple[bool, str]:
    del stop
    tc_meta = tongcheng.get("meta") if isinstance(tongcheng.get("meta"), dict) else {}
    tx_meta = tencent.get("meta") if isinstance(tencent.get("meta"), dict) else {}
    tc_regions, tx_regions = _entity_regions(tc_meta), _entity_regions(tx_meta)
    same_region = any(
        left == right or left in right or right in left
        for left in tc_regions
        for right in tx_regions
    )
    if tc_regions and tx_regions and not same_region:
        return False, "city_mismatch"
    tc_adcode, tx_adcode = _text(tc_meta.get("adcode")), _text(tx_meta.get("adcode"))
    if tc_adcode and tx_adcode and tc_adcode != tx_adcode:
        return False, "adcode_mismatch"
    return True, "verified"


def _reconcile_provider_entities(
    days: dict[str, Any],
    warnings: list[str],
    issues: list[dict[str, Any]],
) -> None:
    conflicts: list[str] = []
    for day_id, day in days.items():
        for stop in day.get("stops") or []:
            if not isinstance(stop, dict):
                continue
            tongcheng = _provider_record(stop, "tongcheng")
            tencent = _provider_record(stop, "tencent")
            if not tongcheng or not tencent:
                continue
            if _text(tongcheng.get("status")) not in {"present", "partial"}:
                continue
            if _text(tencent.get("status")) not in {"present", "partial"}:
                continue
            same, reason = _same_provider_entity(stop, tongcheng, tencent)
            _fact_meta(stop)["entityResolution"] = {
                "status": "verified" if same else "conflict",
                "reason": reason,
                "checkedAt": _now_iso(),
                "providers": ["tongcheng", "tencent"],
            }
            if same:
                continue
            _set_fact(stop, "category", "景点", "script")
            conflicts.append(f"{day_id}/{stop.get('id')}/{stop.get('name')}({reason})")
            issues.append(
                _issue(
                    "ENTITY_CONFLICT",
                    f"「{stop.get('name')}」的跨源行政区信息不一致（{reason}），"
                    "已保留腾讯坐标与现有客观详情供候选核对。",
                    action="rename_or_replace_stop",
                    scope={"dayId": day_id, "stopId": _text(stop.get("id"))},
                )
            )
    if conflicts:
        warnings.append("跨数据源行政区信息不一致，已保留详情并标记核对：" + "、".join(conflicts))


def _apply_web_fallbacks(days: dict[str, Any]) -> None:
    for day in days.values():
        for stop in day.get("stops") or []:
            if not isinstance(stop, dict):
                continue
            meta = _fact_meta(stop)
            web = meta.get("web") if isinstance(meta.get("web"), dict) else {}
            for field in WEB_FACT_FIELDS:
                record = web.get(field) if isinstance(web.get(field), dict) else None
                if stop.get(field) in (None, "", [], {}) and record:
                    value = _text(record.get("value"))
                    if value:
                        _set_fact(stop, field, value, "web")


def _transfer_mode(origin_stop: dict[str, Any], destination_stop: dict[str, Any]) -> str:
    """按直线距离挑这一段的首选交通方式（步行或驾车），其余方式由 _fill_modes 补进 options。

    用直线而非路网距离，是因为模式要在算路之前定下来——它决定调哪个路线接口。
    直线总比实走短，所以阈值取得比"能走多远"宽松一档。拿不到坐标时按驾车走：
    驾车算路在零结果时还能退回步行/骑行几何，反过来不行。
    """
    origin = _location(origin_stop.get("location"))
    destination = _location(destination_stop.get("location"))
    if not origin or not destination:
        return "car"
    return "walk" if card_geo.straight_distance(origin, destination) <= WALK_MODE_MAX_METERS else "car"


def _fill_modes(days: dict[str, Any]) -> None:
    for day in days.values():
        stops = day.get("stops") or []
        for index, stop in enumerate(stops[:-1]):
            transfer = stop.get("transferToNext")
            if not isinstance(transfer, dict):
                transfer = {}
                stop["transferToNext"] = transfer
            primary = _transfer_mode(stop, stops[index + 1])
            transfer["mode"] = primary
            # 四种交通方式全部保留：主 mode 走顶层，其余三种进 options，
            # 每种都会在 _fill_routes 里各自算出距离与时长。复用同 mode 的旧
            # option 以带上路线缓存（_routeMeta），坐标未变时就不重复请求。
            existing = {
                _text(option.get("mode")): option
                for option in (transfer.get("options") or [])
                if isinstance(option, dict)
            }
            options = []
            for mode in TRANSFER_MODES:
                if mode == primary:
                    continue
                option = existing.get(mode)
                if not isinstance(option, dict):
                    option = {}
                option["mode"] = mode
                options.append(option)
            transfer["options"] = options
        if stops:
            stops[-1].pop("transferToNext", None)


def _centroid(stops: list[dict[str, Any]]) -> dict[str, float] | None:
    points = [_location(stop.get("location")) for stop in stops]
    points = [point for point in points if point]
    if not points:
        return None
    return {
        "lat": sum(point["lat"] for point in points) / len(points),
        "lng": sum(point["lng"] for point in points) / len(points),
    }


def _remove_legacy_day_routes(days: dict[str, Any]) -> None:
    # 卡片协议不消费跨天路线；以每日首尾点中心算路也没有明确出行语义。
    for day in days.values():
        if isinstance(day, dict):
            day.pop("routeToNext", None)


def _route_signature(origin: dict[str, float], destination: dict[str, float], mode: str) -> str:
    raw = json.dumps(
        [
            round(origin["lat"], 6), round(origin["lng"], 6),
            round(destination["lat"], 6), round(destination["lng"], 6), mode,
        ],
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _prepare_route_target(
    target: dict[str, Any],
    origin: dict[str, float],
    destination: dict[str, float],
    mode: str,
) -> str:
    signature = _route_signature(origin, destination, mode)
    meta = target.get("_routeMeta") if isinstance(target.get("_routeMeta"), dict) else {}
    if meta.get("signature") != signature:
        for field in ROUTE_FIELDS:
            target.pop(field, None)
        target.pop("_routeMeta", None)
    return signature


def _route_cache_fresh(target: dict[str, Any], signature: str) -> bool:
    meta = target.get("_routeMeta") if isinstance(target.get("_routeMeta"), dict) else {}
    if meta.get("signature") != signature:
        return False
    status = _text(meta.get("status"))
    if status in {"present", "partial"} and _record_fresh(meta, ROUTE_TTL):
        return True
    failure = {"fetchedAt": meta.get("lastFailureAt")}
    return _record_fresh(failure, NEGATIVE_TTLS["provider_unavailable"])


def _route_targets(
    days: dict[str, Any],
) -> tuple[list[tuple], dict[Any, dict[str, Any]], dict[Any, str]]:
    segments: list[tuple] = []
    targets: dict[Any, dict[str, Any]] = {}
    signatures: dict[Any, str] = {}
    for day_id, day in days.items():
        stops = day.get("stops") or []
        for index, stop in enumerate(stops[:-1]):
            transfer = stop.get("transferToNext")
            origin, destination = _location(stop.get("location")), _location(stops[index + 1].get("location"))
            if not isinstance(transfer, dict) or not origin or not destination:
                continue
            key = (day_id, _text(stop.get("id")), "main", _text(transfer.get("mode")))
            signatures[key] = _prepare_route_target(transfer, origin, destination, transfer["mode"])
            targets[key] = transfer
            if not _route_cache_fresh(transfer, signatures[key]):
                segments.append((key, origin, destination, transfer["mode"], True))
            for option_index, option in enumerate(transfer.get("options") or []):
                if not isinstance(option, dict):
                    continue
                key = (day_id, _text(stop.get("id")), f"option{option_index}", _text(option.get("mode")))
                signatures[key] = _prepare_route_target(option, origin, destination, option["mode"])
                targets[key] = option
                if not _route_cache_fresh(option, signatures[key]):
                    # 备选方式的折线在下面会被丢弃，所以不必调 direction 取几何。
                    segments.append((key, origin, destination, option["mode"], False))
    return segments, targets, signatures


def _point_distance(point: dict[str, float], start: dict[str, float], end: dict[str, float]) -> float:
    x, y = point["lng"], point["lat"]
    x1, y1 = start["lng"], start["lat"]
    x2, y2 = end["lng"], end["lat"]
    if x1 == x2 and y1 == y2:
        return math.hypot(x - x1, y - y1)
    numerator = abs((y2 - y1) * x - (x2 - x1) * y + x2 * y1 - y2 * x1)
    return numerator / math.hypot(y2 - y1, x2 - x1)


def _rdp(points: list[dict[str, float]], epsilon: float) -> list[dict[str, float]]:
    if len(points) <= 2:
        return points
    best_index, best_distance = 0, 0.0
    for index in range(1, len(points) - 1):
        distance = _point_distance(points[index], points[0], points[-1])
        if distance > best_distance:
            best_index, best_distance = index, distance
    if best_distance <= epsilon:
        return [points[0], points[-1]]
    left = _rdp(points[:best_index + 1], epsilon)
    right = _rdp(points[best_index:], epsilon)
    return left[:-1] + right


def _resample_polyline(
    points: list[dict[str, float]],
    max_points: int,
) -> list[dict[str, float]]:
    """沿已有折线等距取样，保留首尾且不引入偏离路网的捷径点。"""
    if len(points) <= max_points:
        return points
    max_points = max(2, max_points)
    cumulative = [0.0]
    for previous, current in zip(points, points[1:]):
        cumulative.append(
            cumulative[-1]
            + math.hypot(
                current["lat"] - previous["lat"],
                current["lng"] - previous["lng"],
            )
        )
    total = cumulative[-1]
    if total <= 0:
        return [points[0], points[-1]]
    sampled = [points[0]]
    segment = 1
    for index in range(1, max_points - 1):
        target = total * index / (max_points - 1)
        while segment < len(cumulative) - 1 and cumulative[segment] < target:
            segment += 1
        left_distance, right_distance = cumulative[segment - 1], cumulative[segment]
        ratio = (
            0.0
            if right_distance == left_distance
            else (target - left_distance) / (right_distance - left_distance)
        )
        left, right = points[segment - 1], points[segment]
        sampled.append(
            {
                "lat": round(left["lat"] + (right["lat"] - left["lat"]) * ratio, 5),
                "lng": round(left["lng"] + (right["lng"] - left["lng"]) * ratio, 5),
            }
        )
    sampled.append(points[-1])
    return sampled


def _simplify_polyline(
    points: object,
    max_points: int = MAX_POLYLINE_POINTS,
) -> list[dict[str, float]]:
    if not isinstance(points, list):
        return []
    valid = [_location(point) for point in points]
    if any(point is None for point in valid):
        return []
    line: list[dict[str, float]] = []
    for point in valid:
        if not point:
            continue
        rounded = {"lat": round(point["lat"], 5), "lng": round(point["lng"], 5)}
        if not line or rounded != line[-1]:
            line.append(rounded)
    if len(line) < 2:
        return []
    epsilon = 0.000005
    simplified = line
    while len(simplified) > max_points and epsilon <= MAX_RDP_EPSILON:
        simplified = _rdp(line, epsilon)
        epsilon *= 1.8
    if len(simplified) > max_points:
        simplified = _resample_polyline(simplified, max_points)
    return simplified


def _route_polyline_limit(
    days: dict[str, Any],
    targets: dict[Any, dict[str, Any]],
) -> int:
    main_count = sum(1 for key in targets if key[2] == "main")
    if not main_count:
        return MAX_POLYLINE_POINTS
    preview_days = {
        day_id: _day_card(day, "")
        for day_id, day in days.items()
        if isinstance(day, dict)
    }
    for day in preview_days.values():
        for stop in day.get("stops") or []:
            transfer = stop.get("transferToNext") if isinstance(stop, dict) else None
            if isinstance(transfer, dict):
                transfer.pop("polyline", None)
    occupied = len(
        json.dumps(
            {"tabs": [], "days": preview_days},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    available = max(
        0,
        CARD_COMPACTION_TARGET_BYTES - ROUTE_RESPONSE_RESERVE_BYTES - occupied,
    )
    calculated = available // main_count // ESTIMATED_POLYLINE_POINT_BYTES
    return max(MIN_POLYLINE_POINTS, min(MAX_POLYLINE_POINTS, calculated))


def _fill_routes(
    days: dict[str, Any],
    warnings: list[str],
    issues: list[dict[str, Any]],
) -> dict[str, int]:
    segments, targets, signatures = _route_targets(days)
    response = card_geo.resolve_routes_with_status(segments) if segments else {"reports": {}}
    reports = response.get("reports") if isinstance(response.get("reports"), dict) else {}
    queried_keys = {segment[0] for segment in segments}
    point_limit = _route_polyline_limit(days, targets)
    for day in days.values():
        day["_routeReports"] = {}
    for key, target in targets.items():
        if key not in queried_keys:
            continue
        report = reports.get(key) if isinstance(reports.get(key), dict) else {"status": "provider_unavailable"}
        report_record = {
            field: copy.deepcopy(report[field])
            for field in ("status", "fields", "meta", "error")
            if field in report
        }
        owner = key[0]
        if owner in days:
            days[owner]["_routeReports"]["|".join(map(str, key))] = report_record
        status = _text(report.get("status"))
        values = report.get("values") if isinstance(report.get("values"), dict) else {}
        if status in ("present", "partial"):
            for field in ROUTE_FIELDS:
                target.pop(field, None)
            for field in ("distance", "duration"):
                if _text(values.get(field)):
                    target[field] = _text(values[field])
            polyline = _simplify_polyline(values.get("polyline"), point_limit)
            if polyline and key[2] == "main":
                target["polyline"] = polyline
            report_meta = report.get("meta") if isinstance(report.get("meta"), dict) else {}
            target["_routeMeta"] = {
                "provider": "tencent",
                "signature": signatures[key],
                "fetchedAt": _now_iso(),
                "status": status,
                "fields": copy.deepcopy(report.get("fields") or {}),
                "geometryMode": _text(report_meta.get("geometryMode")) or "driving",
            }
        elif status == "provider_unavailable":
            meta = target.get("_routeMeta") if isinstance(target.get("_routeMeta"), dict) else {}
            cached_complete = meta.get("signature") == signatures[key] and all(target.get(field) for field in ROUTE_FIELDS)
            meta.update({
                "provider": "tencent",
                "signature": signatures[key],
                "status": meta.get("status") if cached_complete else status,
                "lastFailureAt": _now_iso(),
            })
            if not cached_complete:
                meta["fetchedAt"] = _now_iso()
                meta["fields"] = copy.deepcopy(report.get("fields") or {})
            target["_routeMeta"] = meta
            if cached_complete:
                warnings.append("腾讯算路暂不可用，已保留同端点同方式的上次有效路线缓存。")
        elif status not in ("provider_unavailable",):
            for field in ROUTE_FIELDS:
                target.pop(field, None)
            target["_routeMeta"] = {
                "provider": "tencent",
                "signature": signatures[key],
                "status": status or "unresolved",
                "fetchedAt": _now_iso(),
                "fields": copy.deepcopy(report.get("fields") or {}),
            }

    for key, target in targets.items():
        if key[2] == "main" and isinstance(target.get("polyline"), list):
            target["polyline"] = _simplify_polyline(target["polyline"], point_limit)

    for day_id, day in days.items():
        stops = day.get("stops") or []
        for index, stop in enumerate(stops[:-1]):
            transfer = stop.get("transferToNext")
            if not isinstance(transfer, dict):
                continue
            missing = [field for field in ROUTE_FIELDS if transfer.get(field) in (None, "", [], {})]
            if missing:
                message = (
                    f"{day_id}「{stop.get('name')}→{stops[index + 1].get('name')}」真实路线缺少"
                    + "、".join(missing)
                    + "；缺失折线时该段不绘制。"
                )
                warnings.append(message)
                issues.append(
                    _issue(
                        "ROUTE_INCOMPLETE",
                        message,
                        provider="tencent",
                        retryable=True,
                        action="retry_render",
                        scope={
                            "dayId": day_id,
                            "fromStopId": _text(stop.get("id")),
                            "toStopId": _text(stops[index + 1].get("id")),
                        },
                        missingFields=missing,
                    )
                )
    return {
        "requested": len(segments),
        "cacheHits": max(0, len(targets) - len(segments)),
        "pointLimit": point_limit,
    }


def _schema_item(value: object) -> str:
    raw = value.get("schema") if isinstance(value, dict) else None
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    text = _text(raw)
    if text.startswith(("weixin://dl/business/", "tctclient://", "ly://")):
        return text
    return ""


def _safe_link(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    link = _text(value.get("link"))
    if link:
        parsed = urlparse(link)
        if parsed.scheme != "https" or not parsed.netloc:
            link = ""
    schema = _schema_item(value)
    result: dict[str, Any] = {}
    if link:
        result["link"] = link
    if schema:
        result["schema"] = schema
    for key in ("label", "icon"):
        text = _text(value.get(key))
        if text:
            result[key] = text
    return result or None


def _transfer_card(transfer: dict[str, Any], stop: dict[str, Any], next_stop: dict[str, Any] | None) -> dict[str, Any]:
    card = {
        key: copy.deepcopy(value)
        for key, value in transfer.items()
        if not str(key).startswith("_")
        and key in ("mode", "label", "distance", "duration", "polyline", "options")
    }
    card["label"] = card_links.mode_label(_text(card.get("mode")))
    target = _location(next_stop.get("location")) if isinstance(next_stop, dict) else None
    if isinstance(next_stop, dict):
        card["from"] = _text(stop.get("name"))
        card["to"] = _text(next_stop.get("title")) or _text(next_stop.get("name"))
    route_endpoints = {
        "to_name": _text(card.get("to")),
        "from_name": _text(card.get("from")),
        "from_location": _location(stop.get("location")),
        "poi_id": _tencent_poi_id(next_stop) if isinstance(next_stop, dict) else "",
    }
    if target:
        navigation = card_links.route_navigation(
            _text(card.get("mode")), target, **route_endpoints
        )
        if navigation:
            card["navigationData"] = navigation
    # 交通信息面板只渲染 options，顶层那份 mode/distance/duration 只喂列表行和地图折线。
    # 所以首选也要作为第一条并列方案进 options，否则点开面板永远缺一种——缺的正是
    # 列表行上显示的那种。放第一位是为了让面板默认选中项与列表行一致。
    options = []
    seen_modes = set()
    primary_mode = _text(card.get("mode"))
    if primary_mode:
        primary = {"mode": primary_mode}
        for field in ("distance", "duration"):
            value = _text(card.get(field))
            if value:
                primary[field] = value
        primary["label"] = card["label"]
        if card.get("navigationData"):
            primary["navigationData"] = copy.deepcopy(card["navigationData"])
        options.append(primary)
        seen_modes.add(primary_mode)
    for option in card.get("options") or []:
        if not isinstance(option, dict):
            continue
        item = {key: value for key, value in option.items() if key in ("mode", "distance", "duration")}
        mode = _text(item.get("mode"))
        if mode in seen_modes:
            continue
        seen_modes.add(mode)
        item["label"] = card_links.mode_label(mode)
        if target:
            navigation = card_links.route_navigation(
                mode, target, **route_endpoints
            )
            if navigation:
                item["navigationData"] = navigation
        options.append(item)
    if options:
        card["options"] = options
    else:
        card.pop("options", None)
    return card


def _stop_card(stop: dict[str, Any], next_stop: dict[str, Any] | None) -> dict[str, Any]:
    card = {
        key: copy.deepcopy(value)
        for key, value in stop.items()
        if key in STOP_CARD_FIELDS
    }
    card["category"] = "景点"
    # 详情栏按"字段存在与否"决定画不画那一格，于是同一个页面时而三格时而四格。
    # 出卡时统一补上占位，让这几格恒定存在。只补在卡片副本上：写回行程状态会让
    # `_apply_web_fallbacks` 以为字段已有值，官网补充和缺字段提醒就都不触发了。
    for field in CARD_PLACEHOLDER_FIELDS:
        if _text(card.get(field)) == "":
            card[field] = CARD_PLACEHOLDER
    # 第二格固定成「营业状态 / 营业中」这样一对。`openStatus` 也必须始终有值：
    # 它空着时端上会退回「营业时间」那套写法，小字就变回时段了。
    card["openStatus"] = _text(card.get("openStatus")) or CARD_PLACEHOLDER
    card["businessHours"] = CARD_STATUS_LABEL
    location = _location(card.get("location"))
    if location:
        card["location"] = location
        card["navigationData"] = card_links.stop_navigation(
            location,
            name=_text(card.get("title")) or _text(card.get("name")),
            poi_id=_tencent_poi_id(stop),
        )
    else:
        card.pop("location", None)
    nearby_hotels = _safe_link(card.get("nearbyHotelsData"))
    if nearby_hotels:
        card["nearbyHotelsData"] = nearby_hotels
    else:
        card.pop("nearbyHotelsData", None)
    if _text(card.get("ticketPrice")) == "免费":
        card.pop("ticketPurchaseData", None)
    else:
        ticket = _safe_link(card.get("ticketPurchaseData"))
        if ticket:
            card["ticketPurchaseData"] = ticket
        else:
            card.pop("ticketPurchaseData", None)
    transfer = card.get("transferToNext")
    if isinstance(transfer, dict):
        card["transferToNext"] = _transfer_card(transfer, card, next_stop)
    return card


def _day_card(day: dict[str, Any], destination: str) -> dict[str, Any]:
    raw_stops = [stop for stop in day.get("stops") or [] if isinstance(stop, dict)]
    stops = [
        _stop_card(stop, raw_stops[index + 1] if index + 1 < len(raw_stops) else None)
        for index, stop in enumerate(raw_stops)
    ]
    card = {
        key: copy.deepcopy(value)
        for key, value in day.items()
        if key in DAY_CARD_FIELDS
    }
    card["city"] = _day_city(day, destination)
    card["stops"] = stops
    location = _location(day.get("location")) or _centroid(stops)
    if location:
        card["location"] = location
    return card


def _all_polyline_containers(card: dict[str, Any]) -> list[dict[str, Any]]:
    containers = []
    for day in (card.get("days") or {}).values():
        if not isinstance(day, dict):
            continue
        for stop in day.get("stops") or []:
            transfer = stop.get("transferToNext") if isinstance(stop, dict) else None
            if isinstance(transfer, dict) and isinstance(transfer.get("polyline"), list):
                containers.append(transfer)
    return containers


def _all_transfer_cards(card: dict[str, Any]) -> list[dict[str, Any]]:
    transfers = []
    for day in (card.get("days") or {}).values():
        if not isinstance(day, dict):
            continue
        for stop in day.get("stops") or []:
            transfer = stop.get("transferToNext") if isinstance(stop, dict) else None
            if isinstance(transfer, dict):
                transfers.append(transfer)
    return transfers


def _strip_option_navigation(card: dict[str, Any], *, keep_primary: bool) -> bool:
    """丢掉交通方案里的导航串。

    四种方式的 `link` 只差一个 type 参数、`schema` 完全相同，是回包里最大的一块
    重复内容。丢掉后四种方式的距离与时长仍然齐全，面板照样列得全；顶层
    `navigationData` 也还在，所以至少首选那段的导航按钮不会失效。
    """
    changed = False
    for transfer in _all_transfer_cards(card):
        options = transfer.get("options")
        if not isinstance(options, list):
            continue
        for index, option in enumerate(options):
            if not isinstance(option, dict) or "navigationData" not in option:
                continue
            if keep_primary and index == 0:
                continue
            option.pop("navigationData")
            changed = True
    return changed


def _strip_alternative_options(card: dict[str, Any]) -> bool:
    """只留首选那一条交通方案。压到这一步说明行程已经大到装不下四种方式。"""
    changed = False
    for transfer in _all_transfer_cards(card):
        options = transfer.get("options")
        if isinstance(options, list) and len(options) > 1:
            transfer["options"] = options[:1]
            changed = True
    return changed


def _compact_card(
    card: dict[str, Any],
    target_bytes: int = CARD_COMPACTION_TARGET_BYTES,
) -> list[str]:
    """把卡片压回预算，返回实际用过的手段。手段按信息损失从小到大排。"""
    applied: list[str] = []
    while True:
        current_size = len(
            json.dumps(card, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
        if current_size <= target_bytes:
            break
        changed = False
        ratio = max(0.25, min(0.9, target_bytes / max(current_size, 1)))
        for container in _all_polyline_containers(card):
            line = container.get("polyline")
            if isinstance(line, list) and len(line) > 2:
                target_points = max(2, min(len(line) - 1, int(len(line) * ratio)))
                container["polyline"] = _resample_polyline(line, target_points)
                changed = True
                if "polyline" not in applied:
                    applied.append("polyline")
        if not changed:
            break
    # 折线抽到最短仍超预算时（14 天 × 12 景点会这样），交通方案是剩下唯一可压的部分。
    # 顺序是先丢备选方案的导航串、再丢首选的、最后才丢备选方案本身：
    # 面板少几个按钮、极端行程只剩首选方式，都比整张卡直接渲染失败要好。
    for measure, strip in (
        ("option_navigation", lambda: _strip_option_navigation(card, keep_primary=True)),
        ("transfer_navigation", lambda: _strip_option_navigation(card, keep_primary=False)),
        ("alternative_options", lambda: _strip_alternative_options(card)),
    ):
        if _encoded_size(card) <= target_bytes:
            break
        if strip():
            applied.append(measure)
    return applied


def _ensure_recoverable_state(
    trip: dict[str, Any],
    *,
    card_preview: dict[str, Any] | None = None,
) -> None:
    raw_size = len(json.dumps(trip, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if raw_size > MAX_STORE_BYTES:
        raise TravelActionError(
            "STATE_TOO_LARGE",
            f"行程内部状态 {raw_size} 字节，超过 {MAX_STORE_BYTES} 字节限制。",
        )
    card = copy.deepcopy(card_preview) if isinstance(card_preview, dict) else _build_card(trip)
    _compact_card(card)
    preview = {
        "operation": "get_trip",
        "phase": "partial",
        **card,
        "hasTrip": True,
        "revision": 0,
    }
    size = len(json.dumps(preview, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if size > OUTPUT_BUDGET_BYTES:
        raise TravelActionError(
            "STATE_TOO_LARGE",
            f"当前内容会生成 {size} 字节卡片，超过安全预算；请缩短摘要或减少景点。",
        )


def _build_card(trip: dict[str, Any] | None) -> dict[str, Any]:
    if trip is None:
        return {"title": "", "tabs": [], "days": {}}
    destination = _text(trip.get("destination") or trip.get("city"))
    raw_days = trip.get("days") if isinstance(trip.get("days"), dict) else {}
    tabs, days = [], {}
    for index, (day_id, day) in enumerate(raw_days.items(), start=1):
        if not isinstance(day, dict):
            continue
        tabs.append({"id": day_id, "label": _text(day.get("label")) or f"第{index}天"})
        days[day_id] = _day_card(day, destination)
    return {
        "title": _text(trip.get("title")),
        "tabs": tabs,
        "days": days,
    }


def _quality_errors(trip: dict[str, Any]) -> list[str]:
    errors = []
    if not _text(trip.get("title")):
        errors.append("缺少标题")
    if not _text(trip.get("destination") or trip.get("city")):
        errors.append("缺少目的地")
    days = trip.get("days")
    if not isinstance(days, dict) or not days:
        errors.append("至少需要一天")
        return errors
    seen: set[str] = set()
    for day_id, day in days.items():
        stops = day.get("stops") if isinstance(day, dict) else None
        if not isinstance(stops, list) or not stops:
            errors.append(f"{day_id} 至少需要一个景点")
            continue
        for stop in stops:
            if not isinstance(stop, dict):
                errors.append(f"{day_id} 包含无效景点节点")
                continue
            name, summary, identifier = _text(stop.get("name")), _text(stop.get("summary")), _text(stop.get("id"))
            if not name or not summary:
                errors.append(f"{day_id} 存在缺 name/summary 的景点")
            if not identifier:
                errors.append(f"{day_id}「{name}」缺 id")
            elif identifier in seen:
                errors.append(f"景点 id 重复：{identifier}")
            seen.add(identifier)
    return errors


def _web_missing_warnings(
    days: dict[str, Any],
    issues: list[dict[str, Any]],
) -> list[str]:
    warnings = []
    for day_id, day in days.items():
        for stop in day.get("stops") or []:
            if not isinstance(stop, dict):
                continue
            missing_fields = [
                field
                for field in WEB_FACT_FIELDS
                if stop.get(field) in (None, "", [], {})
            ]
            if missing_fields:
                labels = [WEB_LABELS[field] for field in missing_fields]
                message = (
                    f"「{stop.get('name')}」（{day_id}/{stop.get('id')}）API 未提供"
                    + "、".join(labels)
                    + "；如需补齐，请 web_search 官方来源后调用 apply_verified_web_facts；"
                    "仍无官方信息时卡片显示“暂无”。"
                )
                warnings.append(message)
                issues.append(
                    _issue(
                        "WEB_FACT_ELIGIBLE",
                        message,
                        action="search_official_source",
                        scope={"dayId": day_id, "stopId": _text(stop.get("id"))},
                        missingFields=missing_fields,
                    )
                )
    return warnings


def _structured_issues(
    trip: dict[str, Any] | None = None,
    direct_issues: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    issues = [copy.deepcopy(issue) for issue in (direct_issues or []) if isinstance(issue, dict)]
    if isinstance(trip, dict):
        for day_id, day in (trip.get("days") or {}).items():
            if not isinstance(day, dict):
                continue
            for stop in day.get("stops") or []:
                if not isinstance(stop, dict):
                    continue
                providers = _fact_meta(stop).get("providers")
                for provider, record in (providers.items() if isinstance(providers, dict) else []):
                    if not isinstance(record, dict) or _text(record.get("status")) != "provider_unavailable":
                        continue
                    error = record.get("error") if isinstance(record.get("error"), dict) else {}
                    retryable = bool(error.get("retryable"))
                    issues.append({
                        "code": _text(error.get("code")) or "PROVIDER_UNAVAILABLE",
                        "severity": "warning",
                        "provider": provider,
                        "retryable": retryable,
                        "action": "retry_render" if retryable else "check_provider_configuration_or_quota",
                        "scope": {"dayId": day_id, "stopId": _text(stop.get("id"))},
                        "message": _text(error.get("message")) or f"{provider} 暂不可用",
                    })
            reports = day.get("_routeReports")
            for key, record in (reports.items() if isinstance(reports, dict) else []):
                if not isinstance(record, dict):
                    continue
                error = record.get("error") if isinstance(record.get("error"), dict) else {}
                if not error:
                    continue
                retryable = bool(error.get("retryable"))
                issues.append({
                    "code": _text(error.get("code")) or "ROUTE_PROVIDER_UNAVAILABLE",
                    "severity": "warning",
                    "provider": _text(error.get("provider")) or "tencent",
                    "retryable": retryable,
                    "action": "retry_render" if retryable else "check_provider_configuration_or_quota",
                    "scope": {"dayId": day_id, "segment": str(key)},
                    "message": _text(error.get("message")) or "路线服务暂不可用",
                })
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for issue in issues:
        issue.setdefault("code", "DATA_INCOMPLETE")
        issue.setdefault("severity", "warning")
        issue.setdefault("provider", "")
        issue.setdefault("retryable", False)
        issue.setdefault("action", "none")
        issue.setdefault("message", "")
        fingerprint = json.dumps(issue, ensure_ascii=False, sort_keys=True, default=str)
        if fingerprint not in seen:
            seen.add(fingerprint)
            normalized.append(issue)
    return normalized


def _encoded_size(value: object) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    )


def _compact_result_diagnostics(
    result: dict[str, Any],
    target_bytes: int = OUTPUT_BUDGET_BYTES,
) -> bool:
    """只在极端回包下压缩重复诊断；完整候选仍保存在内部事实元数据。"""
    if _encoded_size(result) <= target_bytes:
        return False
    compacted = False
    warnings = result.get("warnings")
    if isinstance(warnings, list) and len(warnings) > 8:
        result["warnings"] = [
            *warnings[:8],
            f"另有 {len(warnings) - 8} 条诊断已汇总到 issues。",
        ]
        compacted = True

    issues = result.get("issues")
    if isinstance(issues, list):
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            candidates = issue.get("candidates")
            if isinstance(candidates, list):
                cleaned = [
                    {
                        key: value
                        for key, value in candidate.items()
                        if value not in (None, "", [], {})
                    }
                    for candidate in candidates[:3]
                    if isinstance(candidate, dict)
                ]
                if cleaned != candidates:
                    issue["candidateCount"] = len(candidates)
                    issue["candidates"] = cleaned
                    compacted = True
            code = _text(issue.get("code"))
            short_messages = {
                "POI_CANDIDATE_AMBIGUOUS": "景点候选需核对。",
                "WEB_FACT_ELIGIBLE": "API 未提供可由官方网页补充的字段。",
                "LOCATION_FROM_GEOCODE": "坐标来自腾讯地址解析兜底。",
                "ROUTE_INCOMPLETE": "真实路线字段不完整。",
                "PROVIDER_EMPTY_BATCH": "数据源整批返回零结果，客观详情留空。",
                "PROVIDER_NO_RESULT": "数据源未收录该景点，客观详情留空。",
            }
            if code in short_messages and issue.get("message") != short_messages[code]:
                issue["message"] = short_messages[code]
                compacted = True

    if _encoded_size(result) > target_bytes and isinstance(issues, list):
        for issue in issues:
            candidates = issue.get("candidates") if isinstance(issue, dict) else None
            if isinstance(candidates, list) and len(candidates) > 1:
                issue["candidateCount"] = max(
                    int(issue.get("candidateCount") or 0),
                    len(candidates),
                )
                issue["candidates"] = candidates[:1]
                compacted = True

    if _encoded_size(result) > target_bytes and isinstance(issues, list):
        web_issues = [
            issue
            for issue in issues
            if isinstance(issue, dict) and issue.get("code") == "WEB_FACT_ELIGIBLE"
        ]
        if len(web_issues) > 1:
            scopes = [
                issue["scope"]
                for issue in web_issues
                if isinstance(issue.get("scope"), dict)
            ]
            missing_fields = sorted(
                {
                    field
                    for issue in web_issues
                    for field in (
                        issue.get("missingFields")
                        if isinstance(issue.get("missingFields"), list)
                        else []
                    )
                    if isinstance(field, str)
                }
            )
            batch_issue = _issue(
                "WEB_FACT_ELIGIBLE",
                f"{len(web_issues)} 个景点有可由官方网页补充的字段。",
                action="search_official_source",
                scopes=scopes,
                missingFields=missing_fields,
            )
            first_index = issues.index(web_issues[0])
            issues[:] = [
                issue for issue in issues if issue not in web_issues
            ]
            issues.insert(first_index, batch_issue)
            compacted = True

    if _encoded_size(result) > target_bytes:
        measures = _compact_card(result, max(1024, target_bytes - 1024))
        if measures:
            compacted = True
            if "polyline" in measures and isinstance(issues, list) and not any(
                isinstance(issue, dict) and issue.get("code") == "POLYLINE_COMPACTED"
                for issue in issues
            ):
                issues.append(
                    _issue(
                        "POLYLINE_COMPACTED",
                        "路线折线已按总回包预算保形抽稀。",
                    )
                )
    return compacted


def _result(
    operation: str,
    trip: dict[str, Any] | None,
    *,
    phase: str = "ready",
    warnings: list[str] | None = None,
    issues: list[dict[str, Any]] | None = None,
    card_override: dict[str, Any] | None = None,
    include_card: bool = True,
    **extra: Any,
) -> dict[str, Any]:
    card = copy.deepcopy(card_override) if isinstance(card_override, dict) else _build_card(trip)
    measures = _compact_card(card)
    all_warnings = list(warnings or [])
    all_issues = _structured_issues(trip, issues)
    if "polyline" in measures:
        message = "路线折线已按回包字节预算保形抽稀，仍为真实路网。"
        all_warnings.append(message)
        all_issues.append(
            _issue(
                "POLYLINE_COMPACTED",
                message,
                action="none",
            )
        )
    if any(measure.endswith("navigation") for measure in measures):
        all_warnings.append(
            "回包接近预算上限，部分交通方案省略了导航跳转串；四种方式的距离与时长仍完整。"
        )
    if "alternative_options" in measures:
        all_warnings.append(
            "回包已达预算上限，交通信息只保留了首选方式；缩短行程天数或减少景点可恢复四种方式。"
        )
    # revision 只用于内部去重（eventId）与渲染提交时的 CAS，不回给模型：并发由 flock 串行化，
    # 让模型逐轮传递 revision 只会增加负担和 REVISION_CONFLICT 类失败。
    revision = extra.pop("revision", None)
    revision = revision if isinstance(revision, int) and not isinstance(revision, bool) else 0
    extra.pop("planRevision", None)
    extra.pop("renderedPlanRevision", None)
    trip_id = _text(extra.get("tripId")) or (_text(trip.get("tripId")) if isinstance(trip, dict) else "")
    state_scope = _text(extra.get("stateScope"))
    update_mode = _text(extra.get("updateMode")) or ("snapshot" if trip is not None else "tombstone")
    content_hash = _content_hash(card)
    result = {
        "operation": operation,
        "phase": phase,
        # 只有挂载 iframe 的动作才回完整卡片；写入与轻量读取回 planDays 骨架，
        # 避免 polyline 和客观详情把模型上下文撑爆（实测占回包 90%+）。
        **(card if include_card else {}),
        "hasTrip": trip is not None,
        "tripId": trip_id,
        "stateScope": state_scope,
        "protocolVersion": PROTOCOL_VERSION,
        "updateMode": update_mode,
        "contentHash": content_hash,
        "eventId": _event_id(state_scope, trip_id, revision, update_mode, content_hash),
        **extra,
    }
    if all_warnings:
        result["warnings"] = list(dict.fromkeys(all_warnings))
    result["issues"] = _structured_issues(None, all_issues)
    _compact_result_diagnostics(result)
    encoded_size = _encoded_size(result)
    if encoded_size > OUTPUT_BUDGET_BYTES:
        raise TravelActionError(
            "RESPONSE_TOO_LARGE",
            f"行程卡回包 {encoded_size} 字节，超过 {OUTPUT_BUDGET_BYTES} 字节安全预算；"
            "请减少单次行程天数或景点数量。",
        )
    return result


def _ack(
    operation: str,
    trip: dict[str, Any] | None,
    *,
    revision: int,
    path: Path,
    changed: bool = True,
    **extra: Any,
) -> dict[str, Any]:
    # 写入动作不挂载 iframe，卡片端不消费它们的回包，因此这里不回完整卡片，
    # 只回 planDays 骨架：结构、id 和名称齐全，summary 一律省略成 “…”。
    days = trip.get("days") if isinstance(trip, dict) and isinstance(trip.get("days"), dict) else {}
    internal = trip.get("_internal") if isinstance(trip, dict) else None
    pending_render = (
        bool(internal.get("dirty")) if isinstance(internal, dict) else isinstance(trip, dict)
    )
    outline = (
        _plan_projection(trip, 0)
        if isinstance(trip, dict)
        else {"title": "", "destination": "", "planDays": []}
    )
    # 调用方显式传入的字段优先于骨架里的同名字段。
    outline.update(extra)
    result = _result(
        operation,
        trip,
        phase=("partial" if pending_render else "ready") if trip is not None else "empty",
        include_card=False,
        revision=revision,
        stateScope=_state_scope(path),
        tripId=_text(trip.get("tripId")) if isinstance(trip, dict) else "",
        dayIds=list(days),
        planRevision=_plan_revision(trip) if isinstance(trip, dict) else 0,
        changed=changed,
        **outline,
    )
    result["rendered"] = not pending_render
    result["nextAction"] = "render_trip" if pending_render else "none"
    if pending_render:
        result["issues"] = [_render_required_issue(operation), *(result.get("issues") or [])]
    return result


def _plan_projection(trip: dict[str, Any], summary_limit: int) -> dict[str, Any]:
    days = []
    for day_id, day in (trip.get("days") or {}).items():
        if not isinstance(day, dict):
            continue
        item: dict[str, Any] = {
            "dayId": day_id,
            "label": _text(day.get("label")),
            "title": _text(day.get("title")),
            "subtitle": _text(day.get("subtitle")),
            "city": _day_city(day, _text(trip.get("destination"))),
            "stops": [],
        }
        for stop in day.get("stops") or []:
            if not isinstance(stop, dict):
                continue
            summary = _text(stop.get("summary"))
            if summary_limit >= 0 and len(summary) > summary_limit:
                summary = summary[:summary_limit].rstrip() + "…"
            item["stops"].append({
                "stopId": _text(stop.get("id")),
                "name": _text(stop.get("name")),
                "summary": summary,
            })
        item["stopIds"] = [stop["stopId"] for stop in item["stops"]]
        days.append(item)
    return {
        "title": _text(trip.get("title")),
        "destination": _text(trip.get("destination")),
        # 不能叫 days：卡片协议的 days 是以 dayId 为键的对象，同名会撞类型。
        "planDays": days,
    }


def _require_trip(trip: dict[str, Any] | None) -> dict[str, Any]:
    if trip is None:
        raise TravelActionError("NO_TRIP", "还没有行程，请先创建卡片。")
    return trip


def _require_day(trip: dict[str, Any], day_id: str) -> dict[str, Any]:
    days = trip.get("days")
    day = days.get(day_id) if isinstance(days, dict) else None
    if not isinstance(day, dict):
        raise TravelActionError("NOT_FOUND", f"未找到该天：{day_id}")
    return day


def _find_stop_index(stops: list[Any], stop_id: str) -> int | None:
    for index, stop in enumerate(stops):
        if isinstance(stop, dict) and _text(stop.get("id")) == stop_id:
            return index
    return None


def _require_trip_identity(args: dict[str, Any], trip: dict[str, Any]) -> None:
    expected = _text(args.get("expectedTripId"))
    current = _text(trip.get("tripId"))
    if not expected:
        raise TravelActionError("TRIP_ID_REQUIRED", "破坏性操作必须提供 get_plan_state 返回的 expectedTripId。")
    if expected != current:
        raise TravelActionError(
            "TRIP_ID_CONFLICT",
            f"目标旅行已变化（期望 {expected}，当前 {current}），请重新读取后再确认。",
            retryable=True,
        )


def _stop_ids(day: dict[str, Any]) -> list[str]:
    return [
        _text(stop.get("id"))
        for stop in (day.get("stops") or [])
        if isinstance(stop, dict)
    ]


def _require_stop_snapshot(args: dict[str, Any], day: dict[str, Any]) -> None:
    supplied = args.get("expectedStopIds")
    current = _stop_ids(day)
    if not isinstance(supplied, list) or supplied != current:
        raise TravelActionError(
            "DAY_SNAPSHOT_CONFLICT",
            "整天景点列表与读取时不一致，已拒绝替换；请重新 get_plan_state。",
            retryable=True,
        )


def _render_trip(args: dict, trip: dict | None, path: Path, expected_revision: int) -> dict[str, Any]:
    started_at = time.monotonic()
    trip = copy.deepcopy(_require_trip(trip))
    errors = _quality_errors(trip)
    if errors:
        raise TravelActionError("INCOMPLETE_TRIP", "；".join(errors))
    days = trip["days"]
    destination = _text(trip.get("destination") or trip.get("city"))
    warnings: list[str] = []
    issues: list[dict[str, Any]] = []
    if _purge_unattributed_facts(days):
        warnings.append("已清理旧版本中无法确认来源的客观字段，并按当前 API 重新补全。")
    tongcheng_batches = _provider_batches(days, destination, "tongcheng", TONGCHENG_FIELDS)
    tencent_batches = _provider_batches(days, destination, "tencent", TENCENT_FIELDS)
    with ThreadPoolExecutor(max_workers=2) as pool:
        tongcheng_future = pool.submit(
            _fetch_tongcheng_batches, tongcheng_batches, defer_hotels=True
        )
        tencent_future = pool.submit(_fetch_tencent_batches, tencent_batches)
        tongcheng_results = tongcheng_future.result()
        tencent_results = tencent_future.result()
    relay_stats = _relay_missing_provider_results(
        days,
        destination,
        tongcheng_results,
        tencent_results,
        tongcheng_batches,
        tencent_batches,
    )
    _fill_tongcheng_details(days, destination, warnings, issues, tongcheng_results)
    _fill_tencent_places(days, destination, warnings, issues, tencent_results)
    geocode_requests = _fill_missing_locations(days, destination, warnings, issues)
    _reconcile_provider_entities(days, warnings, issues)
    _apply_web_fallbacks(days)
    _fill_modes(days)
    _remove_legacy_day_routes(days)
    route_stats = _fill_routes(days, warnings, issues)
    _finish_tongcheng_hotels(days, destination, tongcheng_results)
    warnings.extend(_web_missing_warnings(days, issues))
    trip["updated_at"] = _now_iso()
    phase = "partial" if warnings else "ready"
    structured_issues = _structured_issues(trip, issues)
    _internal(trip)["lastRender"] = {
        "phase": phase,
        "warnings": list(dict.fromkeys(warnings)),
        "issues": structured_issues,
        "renderedAt": _now_iso(),
        "metrics": {
            "tongchengRequests": (
                sum(len(names) for names in tongcheng_batches.values())
                + relay_stats["tongcheng"]
            ),
            "tencentPlaceRequests": (
                sum(len(names) for names in tencent_batches.values())
                + relay_stats["tencent"]
            ),
            "geocodeRequests": geocode_requests,
            "routeRequests": route_stats["requested"],
            "routeCacheHits": route_stats["cacheHits"],
            "routePointLimit": route_stats["pointLimit"],
            "elapsedMs": round((time.monotonic() - started_at) * 1000),
        },
    }
    _mark_rendered(trip)
    next_revision = expected_revision + 1
    card = _build_card(trip)
    result = _result(
        "render_trip",
        trip,
        phase=phase,
        warnings=warnings,
        issues=structured_issues,
        revision=next_revision,
        tripId=_text(trip.get("tripId")),
        stateScope=_state_scope(path),
        planRevision=_plan_revision(trip),
        card_override=card,
        rendered=True,
        nextAction="none",
    )
    with _store_lock(path):
        _save(
            path,
            trip,
            expected_revision,
            operation="render_trip",
            card_preview=card,
        )
    return result


def _get_trip(args: dict, trip: dict | None, path: Path, expected_revision: int) -> dict[str, Any]:
    if trip is None:
        return _result(
            "get_trip",
            None,
            phase="empty",
            revision=expected_revision,
            tripId="",
            stateScope=_state_scope(path),
            planRevision=0,
        )
    internal = trip.get("_internal") if isinstance(trip.get("_internal"), dict) else {}
    last = internal.get("lastRender") if isinstance(internal.get("lastRender"), dict) else {}
    warnings = list(last.get("warnings") or [])
    issues = list(last.get("issues") or [])
    phase = _text(last.get("phase")) or "partial"
    pending_render = bool(internal.get("dirty"))
    extra: dict[str, Any] = {
        "revision": expected_revision,
        "tripId": _text(trip.get("tripId")),
        "stateScope": _state_scope(path),
        "planRevision": _plan_revision(trip),
        # 和写入 ACK、get_plan_state 用同一对字段表达"这轮完没完"，
        # 省得模型在不同动作之间猜哪个信号算数。
        "rendered": not pending_render,
        "nextAction": "render_trip" if pending_render else "none",
    }
    if pending_render:
        # 读也要提醒：模型常在改完之后拿它复核结果，看到数据齐全就以为这轮做完了。
        phase = "partial"
        warnings.append("行程已修改但尚未重新 render_trip，当前显示可能缺少最新详情或路线。")
        issues = [_render_required_issue(), *issues]
    try:
        return _result(
            "get_trip",
            trip,
            phase=phase,
            warnings=warnings,
            issues=issues,
            **extra,
        )
    except TravelActionError as exc:
        if exc.code != "RESPONSE_TOO_LARGE":
            raise
        return {
            "operation": "get_trip",
            "phase": "error",
            "code": exc.code,
            "message": exc.message,
            "retryable": False,
            "hasTrip": True,
            "tripId": _text(trip.get("tripId")),
            "stateScope": _state_scope(path),
        }


def _get_plan_state(args: dict, trip: dict | None, path: Path, expected_revision: int) -> dict[str, Any]:
    card = _build_card(trip)
    common: dict[str, Any] = {
        "revision": expected_revision,
        "stateScope": _state_scope(path),
        "tripId": _text(trip.get("tripId")) if isinstance(trip, dict) else "",
        "planRevision": _plan_revision(trip) if isinstance(trip, dict) else 0,
        "renderedPlanRevision": (
            _internal(trip).get("renderedPlanRevision", 0) if isinstance(trip, dict) else 0
        ),
    }
    if trip is None:
        return _result(
            "get_plan_state",
            None,
            phase="empty",
            card_override=card,
            include_card=False,
            title="",
            destination="",
            planDays=[],
            summaryLimit=0,
            rendered=True,
            nextAction="none",
            **common,
        )
    pending_render = bool(_internal(trip).get("dirty"))
    for summary_limit in (400, 240, 120, 0):
        try:
            result = _result(
                "get_plan_state",
                trip,
                phase="partial" if pending_render else "ready",
                card_override=card,
                # 轻量编辑状态只回 planDays；完整卡片由 render_trip 推给卡片端。
                include_card=False,
                summaryLimit=summary_limit,
                rendered=not pending_render,
                nextAction="render_trip" if pending_render else "none",
                **_plan_projection(trip, summary_limit),
                **common,
            )
        except TravelActionError as exc:
            if exc.code != "RESPONSE_TOO_LARGE":
                raise
            continue
        if pending_render:
            result["issues"] = [_render_required_issue(), *(result.get("issues") or [])]
        return result
    raise TravelActionError("PLAN_STATE_TOO_LARGE", "轻量编辑状态超过回包预算，请减少行程规模。")


def _update_trip_meta(args: dict, trip: dict | None, path: Path, expected_revision: int) -> dict[str, Any]:
    new_trip = bool(args.get("newTrip"))
    if trip is None and not new_trip:
        raise TravelActionError(
            "NEW_TRIP_REQUIRED",
            "当前没有行程；创建行程必须显式传 newTrip=true。",
        )
    if new_trip and trip is not None:
        raise TravelActionError(
            "TRIP_ALREADY_EXISTS",
            "当前已有行程，newTrip=true 可能清空已有内容，已拒绝执行。"
            "修改景点请先 get_plan_state，再用 upsert_stop；若用户明确要新建另一趟行程，"
            "请确认后先调用 reset_trip。",
        )
    if trip is None:
        title = _text(args.get("title"))
        destination = _text(args.get("destination") or args.get("city"))
        if not title or not destination:
            raise TravelActionError("INVALID_ARGUMENT", "新旅行需要 title 和 destination。")
        trip = {
            "tripId": "trip-" + uuid.uuid4().hex[:20],
            "title": title,
            "destination": destination,
            "days": {},
            "created_at": _now_iso(),
            "_internal": {
                "planRevision": 0,
                "renderedPlanRevision": 0,
            },
        }
        changed = True
    else:
        trip = copy.deepcopy(trip)
        changed = False
        if "title" in args:
            title = _text(args["title"])
            if title != _text(trip.get("title")):
                trip["title"] = title
                changed = True
        if "destination" in args or "city" in args:
            destination = _text(args.get("destination") or args.get("city"))
            if destination != _text(trip.get("destination") or trip.get("city")):
                trip["destination"] = destination
                trip.pop("city", None)
                changed = True
                for day in (trip.get("days") or {}).values():
                    if not isinstance(day, dict) or _text(day.get("city")):
                        continue
                    for stop in day.get("stops") or []:
                        if isinstance(stop, dict):
                            _clear_objective_facts(stop)
                    _invalidate_day_routes(day)
    if not changed:
        return _ack(
            "update_trip_meta",
            trip,
            revision=expected_revision,
            path=path,
            changed=False,
            title=trip["title"],
            destination=trip["destination"],
        )
    _mark_dirty(trip)
    trip["updated_at"] = _now_iso()
    next_revision = _save(
        path,
        trip,
        expected_revision,
        operation="update_trip_meta",
        record_history=True,
    )
    return _ack(
        "update_trip_meta",
        trip,
        revision=next_revision,
        path=path,
        title=trip["title"],
        destination=trip["destination"],
    )


def _next_day_id(days: dict[str, Any]) -> str:
    index = len(days) + 1
    while f"day{index}" in days:
        index += 1
    return f"day{index}"


def _upsert_day(args: dict, trip: dict | None, path: Path, expected_revision: int) -> dict[str, Any]:
    trip = copy.deepcopy(_require_trip(trip))
    days = trip.get("days")
    if not isinstance(days, dict):
        raise TravelActionError("STORE_CORRUPTED", "days 不是对象。")
    day_id = _text(args.get("dayId"))
    is_new = not day_id
    day = copy.deepcopy(_require_day(trip, day_id)) if not is_new else {"stops": []}
    original_day = copy.deepcopy(day)
    if is_new:
        if len(days) >= MAX_DAYS:
            raise TravelActionError("INVALID_ARGUMENT", f"一张卡最多 {MAX_DAYS} 天。")
        day_id = _next_day_id(days)
    old_city = _day_city(day, _text(trip.get("destination")))
    if "label" in args:
        day["label"] = _text(args["label"])
    for field in DAY_EDITABLE_FIELDS:
        if field in args:
            value = _text(args[field])
            if value:
                day[field] = value
            else:
                day.pop(field, None)
    city_changed = old_city != _day_city(day, _text(trip.get("destination")))
    if "stops" in args:
        if not is_new:
            if args.get("replaceStops") is not True:
                raise TravelActionError(
                    "FULL_DAY_REPLACE_CONFIRMATION_REQUIRED",
                    "已有天的 stops 是整段替换；必须传 replaceStops=true 和当前 expectedStopIds。",
                )
            _require_stop_snapshot(args, original_day)
        other_days = {key: value for key, value in days.items() if key != day_id}
        day["stops"] = _normalize_stops(args["stops"], _taken_ids(other_days))
    elif is_new or not day.get("stops"):
        raise TravelActionError("INVALID_ARGUMENT", "新增一天必须提供非空 stops。")
    elif city_changed:
        for stop in day.get("stops") or []:
            if isinstance(stop, dict):
                _clear_objective_facts(stop)
    if not is_new and day == original_day:
        return _ack(
            "upsert_day",
            trip,
            revision=expected_revision,
            path=path,
            changed=False,
            dayId=day_id,
            stopCount=len(day.get("stops") or []),
        )
    days[day_id] = day
    if city_changed or "stops" in args:
        _invalidate_day_routes(day)
    _mark_dirty(trip)
    trip["updated_at"] = _now_iso()
    next_revision = _save(
        path,
        trip,
        expected_revision,
        operation="upsert_day",
        record_history=True,
    )
    return _ack(
        "upsert_day",
        trip,
        revision=next_revision,
        path=path,
        dayId=day_id,
        stopCount=len(day["stops"]),
    )


def _upsert_stop(args: dict, trip: dict | None, path: Path, expected_revision: int) -> dict[str, Any]:
    trip = copy.deepcopy(_require_trip(trip))
    day_id, stop_id = _text(args["dayId"]), _text(args.get("stopId"))
    day = copy.deepcopy(_require_day(trip, day_id))
    stops = list(day.get("stops") or [])
    route_index: int | None = None
    if stop_id:
        index = _find_stop_index(stops, stop_id)
        if index is None:
            raise TravelActionError("NOT_FOUND", f"未找到景点：{stop_id}")
        stop = copy.deepcopy(stops[index])
        original_stop = copy.deepcopy(stop)
        old_name = _text(stop.get("name"))
        if "name" in args:
            name = _text(args["name"])
            stop["name"] = name
        if "summary" in args:
            stop["summary"] = _text(args["summary"])
        if _text(stop.get("name")) != old_name:
            _clear_objective_facts(stop)
            route_index = index
        if stop == original_stop:
            return _ack(
                "upsert_stop",
                trip,
                revision=expected_revision,
                path=path,
                changed=False,
                dayId=day_id,
                stopId=stop_id,
                stopCount=len(stops),
            )
        stops[index] = stop
    else:
        if len(stops) >= MAX_STOPS_PER_DAY:
            raise TravelActionError("INVALID_ARGUMENT", f"每天最多 {MAX_STOPS_PER_DAY} 个景点。")
        stop = _new_stop(args, _taken_ids(trip["days"]))
        stops.append(stop)
        route_index = len(stops) - 1
    day["stops"] = stops
    trip["days"][day_id] = day
    if route_index is not None:
        _invalidate_day_routes(day, route_index)
    _mark_dirty(trip)
    trip["updated_at"] = _now_iso()
    next_revision = _save(
        path,
        trip,
        expected_revision,
        operation="upsert_stop",
        record_history=True,
    )
    return _ack(
        "upsert_stop",
        trip,
        revision=next_revision,
        path=path,
        dayId=day_id,
        stopId=stop["id"],
        stopCount=len(stops),
    )


def _normalize_web_value(field: str, value: str) -> str:
    text = _text(value)
    if field == "ticketPrice":
        text = text.replace("￥", "¥")
        if text in ("0", "0.0"):
            return "免费"
        if re.fullmatch(r"\d+(?:\.\d+)?", text):
            return "¥" + text
    if field == "businessHours":
        # 同程来的时段已在 poi 侧归一化，模型从官网抄来的也要过同一道，
        # 否则卡片上这一格一半是「08:30-17:00」一半是整段说明文字。
        normalized = poi.normalize_business_hours(text)
        if normalized:
            return normalized
        if len(text) > poi._HOURS_MAX_CHARS:
            raise TravelActionError(
                "INVALID_ARGUMENT",
                "开放时间只写时段本身，如 08:30-17:00 或 全天开放；"
                f"当前值过长且解析不出时段（限 {poi._HOURS_MAX_CHARS} 字）。",
            )
    return text


def _apply_verified_web_facts(
    args: dict,
    trip: dict | None,
    path: Path,
    expected_revision: int,
) -> dict[str, Any]:
    trip = copy.deepcopy(_require_trip(trip))
    day_id, stop_id = _text(args["dayId"]), _text(args["stopId"])
    day = _require_day(trip, day_id)
    stops = day.get("stops") or []
    index = _find_stop_index(stops, stop_id)
    if index is None:
        raise TravelActionError("NOT_FOUND", f"未找到景点：{stop_id}")
    stop = stops[index]
    source_url = _text(args["sourceUrl"])
    source_type = _text(args["sourceType"])
    if source_type not in VALID_SOURCE_TYPES:
        raise TravelActionError("INVALID_ARGUMENT", "sourceType 不是允许的官方来源类型。")
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise TravelActionError("INVALID_ARGUMENT", "sourceUrl 必须是 HTTPS 官方来源。")
    web = _fact_meta(stop)["web"]
    applied, skipped = [], []
    for field, value in args["facts"].items():
        if field not in WEB_FACT_FIELDS:
            raise TravelActionError("INVALID_ARGUMENT", f"网页补充禁止写入 {field}。")
        if stop.get(field) not in (None, "", [], {}) and _field_source(stop, field) in ("tongcheng", "tencent"):
            skipped.append(field)
            continue
        normalized = _normalize_web_value(field, value)
        web[field] = {
            "value": normalized,
            "sourceUrl": source_url,
            "sourceType": source_type,
            "retrievedAt": _text(args["retrievedAt"]),
            "evidence": _text(args["evidence"]),
        }
        _set_fact(stop, field, normalized, "web")
        applied.append(field)
    if not applied and skipped:
        raise TravelActionError("API_VALUE_PRESENT", "API 已提供这些字段，拒绝网页覆盖：" + "、".join(skipped))
    _mark_dirty(trip, plan_changed=False)
    trip["updated_at"] = _now_iso()
    next_revision = _save(
        path,
        trip,
        expected_revision,
        operation="apply_verified_web_facts",
    )
    return _ack(
        "apply_verified_web_facts",
        trip,
        revision=next_revision,
        path=path,
        dayId=day_id,
        stopId=stop_id,
        applied=applied,
        skipped=skipped,
    )


def _delete_day(args: dict, trip: dict | None, path: Path, expected_revision: int) -> dict[str, Any]:
    trip = copy.deepcopy(_require_trip(trip))
    _require_trip_identity(args, trip)
    day_id = _text(args["dayId"])
    day = _require_day(trip, day_id)
    _require_stop_snapshot(args, day)
    trip["days"].pop(day_id)
    _mark_dirty(trip)
    trip["updated_at"] = _now_iso()
    next_revision = _save(
        path,
        trip,
        expected_revision,
        operation="delete_day",
        record_history=True,
    )
    return _ack(
        "delete_day",
        trip,
        revision=next_revision,
        path=path,
        dayId=day_id,
        deleted=True,
    )


def _delete_stop(args: dict, trip: dict | None, path: Path, expected_revision: int) -> dict[str, Any]:
    trip = copy.deepcopy(_require_trip(trip))
    _require_trip_identity(args, trip)
    day_id, stop_id = _text(args["dayId"]), _text(args["stopId"])
    day = copy.deepcopy(_require_day(trip, day_id))
    stops = list(day.get("stops") or [])
    index = _find_stop_index(stops, stop_id)
    if index is None:
        raise TravelActionError("NOT_FOUND", f"未找到景点：{stop_id}")
    expected_name = _text(args.get("expectedStopName"))
    current_name = _text(stops[index].get("name"))
    if not expected_name or expected_name != current_name:
        raise TravelActionError(
            "STOP_SNAPSHOT_CONFLICT",
            "目标景点名称与读取时不一致，已拒绝删除；请重新 get_plan_state。",
            retryable=True,
        )
    removed = stops.pop(index)
    if not stops:
        raise TravelActionError("INCOMPLETE_DAY", "删除后当天将没有景点；请删除整天或先添加替代景点。")
    day["stops"] = stops
    trip["days"][day_id] = day
    _invalidate_day_routes(day, index)
    _mark_dirty(trip)
    trip["updated_at"] = _now_iso()
    next_revision = _save(
        path,
        trip,
        expected_revision,
        operation="delete_stop",
        record_history=True,
    )
    return _ack(
        "delete_stop",
        trip,
        revision=next_revision,
        path=path,
        dayId=day_id,
        stopId=stop_id,
        deleted=True,
        name=removed.get("name"),
    )


def _reset_trip(args: dict, trip: dict | None, path: Path, expected_revision: int) -> dict[str, Any]:
    trip = _require_trip(trip)
    _require_trip_identity(args, trip)
    old_trip_id = _text(trip.get("tripId"))
    next_revision = _save(
        path,
        None,
        expected_revision,
        operation="reset_trip",
        record_history=True,
    )
    return _ack(
        "reset_trip",
        None,
        revision=next_revision,
        path=path,
        reset=True,
        deletedTripId=old_trip_id,
    )


def _undo_last_mutation(
    args: dict,
    trip: dict | None,
    path: Path,
    expected_revision: int,
) -> dict[str, Any]:
    envelope = _read_envelope(path) if path.exists() else {"history": []}
    history = list(envelope.get("history") or [])
    if not history:
        raise TravelActionError("NOTHING_TO_UNDO", "没有可撤销的最近一次规划修改。")
    entry = history.pop()
    restored = copy.deepcopy(entry.get("trip"))
    target_trip_id = _text(args.get("expectedTripId"))
    current_trip_id = _text(trip.get("tripId")) if isinstance(trip, dict) else ""
    restored_trip_id = _text(restored.get("tripId")) if isinstance(restored, dict) else ""
    if not target_trip_id or target_trip_id not in {current_trip_id, restored_trip_id}:
        raise TravelActionError(
            "TRIP_ID_CONFLICT",
            "撤销目标与当前/最近历史旅行不一致，请重新读取状态。",
            retryable=True,
        )
    if isinstance(restored, dict):
        current_plan_revision = _plan_revision(trip) if isinstance(trip, dict) else 0
        restored_internal = _internal(restored)
        restored_internal["planRevision"] = max(
            current_plan_revision,
            _plan_revision(restored),
        ) + 1
        restored_internal["renderedPlanRevision"] = 0
        restored_internal["dirty"] = True
        restored_internal["dirtyAt"] = _now_iso()
        restored["updated_at"] = _now_iso()
    next_revision = _save(
        path,
        restored,
        expected_revision,
        operation="undo_last_mutation",
        history_override=history,
    )
    return _ack(
        "undo_last_mutation",
        restored,
        revision=next_revision,
        path=path,
        undoneOperation=_text(entry.get("operation")),
    )


ACTIONS = {
    "render_trip": _render_trip,
    "get_trip": _get_trip,
    "get_plan_state": _get_plan_state,
    "update_trip_meta": _update_trip_meta,
    "upsert_day": _upsert_day,
    "upsert_stop": _upsert_stop,
    "apply_verified_web_facts": _apply_verified_web_facts,
    "delete_day": _delete_day,
    "delete_stop": _delete_stop,
    "reset_trip": _reset_trip,
    "undo_last_mutation": _undo_last_mutation,
}

def execute(operation: str, args: dict, store_path: Path | None = None) -> dict[str, Any]:
    if not isinstance(args, dict):
        raise TravelActionError("INVALID_ARGUMENT", "请求参数必须为对象。")
    try:
        validated = validate_operation(operation, args)
    except ContractError as exc:
        raise TravelActionError("INVALID_ARGUMENT", str(exc)) from exc
    action = ACTIONS.get(operation)
    if action is None:
        raise TravelActionError("UNKNOWN_OPERATION", f"不支持的操作：{operation}")
    path = store_path or _resolve_store_path()
    if operation == "render_trip":
        # 网络补全在锁外完成；提交时由 _render_trip 用根 revision 做一次 CAS。
        with _store_lock(path):
            trip, current_revision = _load_state(path)
        return action(validated, trip, path, current_revision)
    # 读-改-写整段持锁，跨进程串行；revision 由锁内现读现用，模型无需传递。
    with _store_lock(path):
        trip, current_revision = _load_state(path)
        return action(validated, trip, path, current_revision)
