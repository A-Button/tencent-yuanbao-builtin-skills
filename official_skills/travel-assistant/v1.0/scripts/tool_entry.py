#!/usr/bin/env python3
"""各 tool handler 的共用入口。"""

from __future__ import annotations

import json
import sys

sys.dont_write_bytecode = True

import provider_api
from companion import check_route_eta, check_weather, find_nearby, wrap
from emit_card import CardError, emit_card
from landing_links import prepare_landing
from proximity import check_proximity, plan_geofence
from trip_context import load_trip_context


def run(operation: str) -> int:
    raw = sys.argv[1] if len(sys.argv) > 1 else "{}"
    try:
        args = json.loads(raw)
        if not isinstance(args, dict):
            raise ValueError("请求参数必须为对象")
        if operation == "check_weather":
            result = wrap(check_weather, args)
        elif operation == "check_route_eta":
            result = wrap(check_route_eta, args)
        elif operation == "find_nearby":
            result = wrap(find_nearby, args)
        elif operation == "get_trip_context":
            result = load_trip_context()
        elif operation == "prepare_card":
            result = emit_card(args.get("card"))
        elif operation == "prepare_landing":
            result = prepare_landing(args)
        elif operation == "check_proximity":
            result = check_proximity(args)
        elif operation == "plan_geofence":
            result = plan_geofence(args)
        elif operation == "get_place_media":
            result = provider_api.resolve_place_media(args.get("city"), args.get("names") or [])
        else:
            result = {
                "ok": False,
                "phase": "error",
                "code": "UNKNOWN_TOOL",
                "message": f"不支持的工具：{operation}",
                "retryable": False,
            }
    except json.JSONDecodeError:
        result = {
            "ok": False,
            "phase": "error",
            "code": "INVALID_JSON",
            "message": "请求参数不是合法 JSON",
            "retryable": False,
        }
    except CardError as exc:
        result = {**exc.as_dict(), "phase": "error", "code": exc.rule, "retryable": False}
    except provider_api.ProviderError as exc:
        result = {**exc.as_dict(), "phase": "error", "code": exc.code}
    except Exception as exc:
        result = {
            "ok": False,
            "phase": "error",
            "code": "INTERNAL_ERROR",
            "message": str(exc) or "内部错误",
            "retryable": True,
        }
    result.setdefault("operation", operation)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0
