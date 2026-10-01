"""travel_plan 的模型入参契约。

模型只负责行程结构、景点选择与规划摘要。坐标、图片、评分、等级、票价、营业信息、
POI 详情和路线均由 API/脚本写入。官方网页补充走独立动作并携带来源。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from difflib import get_close_matches
import ipaddress
import os
from typing import Any
from urllib.parse import urlparse


class ContractError(ValueError):
    pass


CONTRACT_VERSION = "v2.7"
VALID_SOURCE_TYPES = ("official_site", "government", "official_ticket", "official_account")
WEB_FACT_FIELDS = ("introduction", "ticketPrice", "businessHours")
STOP_INPUT_FIELDS = ("name", "summary")
MAX_STOPS_PER_DAY = 12
FIELD_LIMITS = {
    "title": 120,
    "destination": 80,
    "city": 80,
    "dayId": 80,
    "stopId": 80,
    "expectedTripId": 80,
    "expectedStopName": 80,
    "label": 40,
    "subtitle": 300,
    "name": 80,
    "summary": 800,
    "sourceUrl": 2048,
    "retrievedAt": 64,
    "evidence": 2000,
}
WEB_FACT_LIMITS = {
    "introduction": 2000,
    "ticketPrice": 300,
    "businessHours": 300,
}
NON_OFFICIAL_HOSTS = (
    "xiaohongshu.com", "dianping.com", "mafengwo.cn", "ctrip.com",
    "trip.com", "zhihu.com", "weibo.com", "douyin.com", "baidu.com",
)


def _host_matches(hostname: str, allowed: set[str]) -> bool:
    return any(hostname == host or hostname.endswith("." + host) for host in allowed)


def _configured_official_hosts() -> set[str]:
    return {
        host.strip().lower().rstrip(".")
        for host in os.environ.get("MY_TRAVEL_OFFICIAL_DOMAINS", "").split(",")
        if host.strip()
    }

OPERATIONS: dict[str, dict[str, Any]] = {
    "render_trip": {"required": [], "optional": [], "types": {}},
    "get_trip": {"required": [], "optional": [], "types": {}},
    "get_plan_state": {"required": [], "optional": [], "types": {}},
    "update_trip_meta": {
        "required": [],
        "optional": ["title", "destination", "city", "newTrip"],
        "types": {
            "title": "string",
            "destination": "string",
            "city": "string",
            "newTrip": "boolean",
        },
    },
    "upsert_day": {
        "required": [],
        "optional": [
            "dayId", "label", "title", "subtitle", "city", "stops",
            "replaceStops", "expectedStopIds",
        ],
        "types": {
            "dayId": "string",
            "label": "string",
            "title": "string",
            "subtitle": "string",
            "city": "string",
            "stops": "array",
            "replaceStops": "boolean",
            "expectedStopIds": "array",
        },
    },
    "upsert_stop": {
        "required": ["dayId"],
        "optional": ["stopId", "name", "summary"],
        "types": {
            "dayId": "string",
            "stopId": "string",
            "name": "string",
            "summary": "string",
        },
    },
    "apply_verified_web_facts": {
        "required": [
            "dayId", "stopId", "facts", "sourceUrl",
            "sourceType", "retrievedAt", "evidence",
        ],
        "optional": [],
        "types": {
            "dayId": "string",
            "stopId": "string",
            "facts": "object",
            "sourceUrl": "string",
            "sourceType": "string",
            "retrievedAt": "string",
            "evidence": "string",
        },
    },
    "delete_day": {
        "required": ["dayId", "expectedTripId", "expectedStopIds"],
        "optional": [],
        "types": {
            "dayId": "string",
            "expectedTripId": "string",
            "expectedStopIds": "array",
        },
    },
    "delete_stop": {
        "required": ["dayId", "stopId", "expectedTripId", "expectedStopName"],
        "optional": [],
        "types": {
            "dayId": "string",
            "stopId": "string",
            "expectedTripId": "string",
            "expectedStopName": "string",
        },
    },
    "reset_trip": {
        "required": ["expectedTripId"],
        "optional": [],
        "types": {"expectedTripId": "string"},
    },
    "undo_last_mutation": {
        "required": ["expectedTripId"],
        "optional": [],
        "types": {"expectedTripId": "string"},
    },
}

AUTO_FILLED_FIELDS = {
    "location": "由同程/腾讯地点查询",
    "thumbnail": "由同程景点图片生成",
    "images": "由同程景点图片生成",
    "rating": "由同程评分生成",
    "businessHours": "由同程或受控官方网页补充",
    "openStatus": "由明确营业状态生成",
    "ticketPrice": "由同程或受控官方网页补充",
    "level": "由同程官方等级生成",
    "introduction": "由同程或受控官方网页补充",
    "title": "卡片/天标题可写；景点官方标题由 API 生成",
    "address": "由地点 API 生成",
    "phone": "由地点 API 生成",
    "category": "固定为景点",
    "transferToNext": "由脚本选择方式并按真实路网生成",
    "navigationData": "按坐标生成",
    "ticketPurchaseData": "由同程绑定链接生成",
    "nearbyHotelsData": "由同程酒店列表链接与列表页小程序 Scheme 生成",
    "distance": "按真实路网生成",
    "duration": "按真实路网生成",
    "polyline": "按真实路网生成",
    "routeToNext": "卡片协议不消费跨天路线，已停用",
}

RETIRED_FIELDS = {
    "tripFile": "整张卡不再走文件",
    "planFile": "整张卡不再走文件",
    "trip": "整张卡不再一次提交",
    "plan": "整张卡不再一次提交",
    "card": "整张卡不再一次提交",
    "days": "按天调用 upsert_day",
}

FIELD_SUGGESTIONS = {
    "itemId": "stopId",
    "item": "stopId",
    "day": "dayId",
    "date": "dayId",
    "note": "summary",
    "notes": "summary",
    "desc": "summary",
    "description": "summary",
}


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    return False


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _check_length(name: str, value: object, limit: int) -> None:
    if isinstance(value, str) and len(value.strip()) > limit:
        raise ContractError(f"{name} 最多 {limit} 个字符")


def _explain_field(name: str, allowed: set[str]) -> str:
    if name in RETIRED_FIELDS:
        return f"{name}（{RETIRED_FIELDS[name]}）"
    if name in AUTO_FILLED_FIELDS:
        return f"{name}（{AUTO_FILLED_FIELDS[name]}，模型不要写）"
    mapped = FIELD_SUGGESTIONS.get(name)
    suggestion = [mapped] if mapped in allowed else get_close_matches(name, sorted(allowed), n=1, cutoff=0.45)
    return f"{name} 是否应为 {suggestion[0]}" if suggestion else name


def _validate_stop(stop: object, path: str) -> None:
    if not isinstance(stop, dict):
        raise ContractError(f"{path} 必须是对象")
    unknown = sorted(set(stop) - set(STOP_INPUT_FIELDS))
    if unknown:
        raise ContractError(
            f"{path} 不允许字段："
            + ", ".join(_explain_field(name, set(STOP_INPUT_FIELDS)) for name in unknown)
        )
    for key in STOP_INPUT_FIELDS:
        if not _nonempty_string(stop.get(key)):
            raise ContractError(f"{path}.{key} 必须是非空字符串")
        _check_length(f"{path}.{key}", stop[key], FIELD_LIMITS[key])


def _validate_web_facts(args: dict[str, Any]) -> None:
    facts = args["facts"]
    unknown = sorted(set(facts) - set(WEB_FACT_FIELDS))
    if unknown:
        raise ContractError("facts 只允许 introduction、ticketPrice、businessHours")
    if not facts:
        raise ContractError("facts 至少包含一个可补充字段")
    for key, value in facts.items():
        if not _nonempty_string(value):
            raise ContractError(f"facts.{key} 必须是非空字符串")
        if value.strip() in ("暂无", "未知", "无", "待确认"):
            raise ContractError(f"facts.{key} 不能写占位词；无官方信息时保持缺失")
        _check_length(f"facts.{key}", value, WEB_FACT_LIMITS[key])
    if args["sourceType"] not in VALID_SOURCE_TYPES:
        raise ContractError("sourceType 必须是官方站点、政府、官方售票或官方账号")
    parsed = urlparse(args["sourceUrl"])
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ContractError("sourceUrl 必须是完整 HTTPS 官方来源")
    hostname = parsed.hostname.lower().rstrip(".")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise ContractError("sourceUrl 不允许 IP 地址")
    if _host_matches(hostname, set(NON_OFFICIAL_HOSTS)):
        raise ContractError("sourceUrl 不是允许的官方来源域名")
    configured = _configured_official_hosts()
    if args["sourceType"] == "government" and not (
        hostname == "gov.cn" or hostname.endswith(".gov.cn")
    ):
        raise ContractError("government 来源必须使用 gov.cn 官方域名")
    if args["sourceType"] == "official_account" and hostname != "mp.weixin.qq.com":
        raise ContractError("official_account 当前仅接受微信官方账号文章")
    if args["sourceType"] == "official_ticket" and not _host_matches(hostname, configured | {"ly.com"}):
        raise ContractError("official_ticket 来源域名不被信任，改用 gov.cn 官方页面或让该字段保持缺失")
    if args["sourceType"] == "official_site" and not _host_matches(hostname, configured):
        raise ContractError("official_site 来源域名不被信任，改用 gov.cn 官方页面或让该字段保持缺失")
    try:
        retrieved = datetime.fromisoformat(args["retrievedAt"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError("retrievedAt 必须是 ISO 8601 时间") from exc
    if retrieved.tzinfo is None:
        raise ContractError("retrievedAt 必须带时区")
    if retrieved.astimezone(timezone.utc) > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ContractError("retrievedAt 不能是未来时间")
    if len(args["evidence"].strip()) < 8:
        raise ContractError("evidence 至少 8 个字符，需包含支持该事实的原文摘要")


def validate_operation(operation: str, args: dict[str, Any]) -> dict[str, Any]:
    spec = OPERATIONS.get(operation)
    if spec is None:
        raise ContractError(f"不支持的 operation：{operation}")
    if not isinstance(args, dict):
        raise ContractError("参数必须是对象")

    allowed = set(spec["required"]) | set(spec["optional"])
    unknown = sorted(set(args) - allowed)
    if unknown:
        raise ContractError("不允许字段：" + ", ".join(_explain_field(name, allowed) for name in unknown))
    missing = [name for name in spec["required"] if args.get(name) in (None, "", [], {})]
    if missing:
        raise ContractError("缺少参数：" + ", ".join(missing))
    for name, value in args.items():
        expected = spec["types"].get(name)
        if expected and not _matches_type(value, expected):
            raise ContractError(f"{name} 必须是 {expected}")
        if name in FIELD_LIMITS:
            _check_length(name, value, FIELD_LIMITS[name])

    if operation == "update_trip_meta":
        for name in ("title", "destination", "city"):
            if name in args and not _nonempty_string(args[name]):
                raise ContractError(f"{name} 不能为空")
        if args.get("newTrip"):
            if not _nonempty_string(args.get("title")):
                raise ContractError("新旅行必须提供 title")
            if not (_nonempty_string(args.get("destination")) or _nonempty_string(args.get("city"))):
                raise ContractError("新旅行必须提供 destination 或 city")
    elif operation == "upsert_day":
        for name in ("dayId", "label", "city"):
            if name in args and not _nonempty_string(args[name]):
                raise ContractError(f"{name} 必须是非空字符串")
        if not args.get("dayId") and "stops" not in args:
            raise ContractError("新增一天必须提供非空 stops")
        if "stops" in args:
            if not args["stops"]:
                raise ContractError("stops 不能为空；删除整天请使用 delete_day")
            if len(args["stops"]) > MAX_STOPS_PER_DAY:
                raise ContractError(f"每天最多 {MAX_STOPS_PER_DAY} 个景点")
            for index, stop in enumerate(args["stops"]):
                _validate_stop(stop, f"stops[{index}]")
        if args.get("dayId") and "stops" in args:
            if args.get("replaceStops") is not True:
                raise ContractError("已有天整段替换 stops 必须显式传 replaceStops=true")
            if not isinstance(args.get("expectedStopIds"), list):
                raise ContractError("已有天整段替换 stops 必须提供 expectedStopIds 快照")
        if "expectedStopIds" in args:
            identifiers = args["expectedStopIds"]
            if len(identifiers) > MAX_STOPS_PER_DAY:
                raise ContractError(f"expectedStopIds 最多 {MAX_STOPS_PER_DAY} 项")
            if any(not _nonempty_string(value) for value in identifiers):
                raise ContractError("expectedStopIds 必须是非空字符串数组")
            if len(set(value.strip() for value in identifiers)) != len(identifiers):
                raise ContractError("expectedStopIds 不允许重复")
    elif operation == "upsert_stop":
        if not args.get("stopId"):
            for name in STOP_INPUT_FIELDS:
                if not _nonempty_string(args.get(name)):
                    raise ContractError(f"新增景点必须提供 {name}")
        elif not any(name in args for name in STOP_INPUT_FIELDS):
            raise ContractError("编辑景点至少提供 name 或 summary")
        for name in STOP_INPUT_FIELDS:
            if name in args and not _nonempty_string(args[name]):
                raise ContractError(f"{name} 必须是非空字符串")
    elif operation == "apply_verified_web_facts":
        _validate_web_facts(args)
    elif operation == "delete_day":
        identifiers = args["expectedStopIds"]
        if len(identifiers) > MAX_STOPS_PER_DAY:
            raise ContractError(f"expectedStopIds 最多 {MAX_STOPS_PER_DAY} 项")
        if any(not _nonempty_string(value) for value in identifiers):
            raise ContractError("expectedStopIds 必须是非空字符串数组")
        if len(set(value.strip() for value in identifiers)) != len(identifiers):
            raise ContractError("expectedStopIds 不允许重复")

    for name in ("expectedTripId", "expectedStopName"):
        if name in args and not _nonempty_string(args[name]):
            raise ContractError(f"{name} 必须是非空字符串")

    return dict(args)


def describe_contract() -> dict[str, Any]:
    return {
        "app": "travel_plan",
        "version": CONTRACT_VERSION,
        "invocation": "app travel_plan <tool> '<json>'",
        "tools": {
            name: {**spec, "example": {}}
            for name, spec in OPERATIONS.items()
        },
    }
