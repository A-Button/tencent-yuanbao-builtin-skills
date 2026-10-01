#!/usr/bin/env python3
"""健康助手的 facade：把训练与营养存储层收成一份对外 API。

工具脚本与 ``_run.py`` 只 import 本模块。真正的落盘、快照、retryable 规则仍在
``_workout`` / ``_nutrition``——本文件只做两件事：

1. **按 tool → 领域派发** ``execute`` / ``run``。快照是领域作用域的：每个 tool
   只带回自己那一域原来的快照形状，不把两域 merge 进一个 dict。
   报告工具走单独路径，固定按 workout → nutrition 的顺序打开存储。
2. **re-export** 工具脚本需要的符号。

判定领域靠下面这张表，与工具脚本一一对应，不靠运行期「handler 碰了哪个后端」。
"""

from __future__ import annotations

import json
import os
import sys
import traceback

import _nutrition
import _workout
from _errors import ActionError

# ── tool → domain（确定性表；改 app.yaml 加 tool 时这里也要加一行）──────────

TOOL_DOMAIN: dict[str, str] = {
    # workout
    "get_today": "workout",
    "log_readiness": "workout",
    "plan_session": "workout",
    "add_exercise": "workout",
    "complete_exercise": "workout",
    "update_exercise_setting": "workout",
    "complete_session": "workout",
    "get_exercise_detail": "workout",
    "get_month": "workout",
    "log_measurement": "workout",
    "get_measurement_trend": "workout",
    "set_body_profile": "workout",
    "get_body_profile": "workout",
    "get_expenditure": "workout",
    # nutrition
    "get_nutrition_summary": "nutrition",
    "set_nutrition_target": "nutrition",
    # 报告工具不合并领域快照。
    "get_weekly_report": "cross",
    # 跨域：workout（消耗）+ nutrition（营养推荐区间）
    "get_daily_report": "cross",
    "now_card": "cross",
    "now_setup": "cross",
}

_DOMAIN_MODULES = {
    "workout": _workout,
    "nutrition": _nutrition,
}


def domain_of(handler) -> str:
    """handler 函数名 → 领域。未知名字直接 KeyError，让调用方早暴露。"""
    return TOOL_DOMAIN[handler.__name__]


def _module_for(handler):
    domain = domain_of(handler)
    if domain == "cross":
        raise KeyError("cross-domain tools do not use a single domain module")
    return _DOMAIN_MODULES[domain]


# ── 注解用的 Store；运行时实例由各领域 execute 构造并传入 handler ──────────


class Store:
    """仅供类型注解。运行时传入的是当前领域的 Store。"""


class CrossStore:
    """报告 handler 用：同时持有训练与营养 Store。

    周报只取 workout，日报取 workout + nutrition。固定把两把锁都拿住，避免
    handler 之间出现不同锁序。
    """

    def __init__(self, workout, nutrition):
        self.workout = workout
        self.nutrition = nutrition


# ── 派发：领域作用域快照，合并序与 retryable 都沿用该领域原实现 ──────────


def _resolve_cross_paths():
    """报告工具忽略 ``HEALTH_ASSISTANT_STORE``（单文件不能表达两个存储）。

    只认 ``HEALTH_ASSISTANT_DATA_DIR`` / ``ONEAGENT_APP_DATA_DIR`` / 默认根，
    分别落到 ``workout.sqlite`` / ``nutrition.json``。
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "HEALTH_ASSISTANT_STORE"
    }
    return (
        _workout._resolve_store_path(env),
        _nutrition._resolve_store_path(env),
    )


def _execute_cross(handler, raw_args: str) -> dict:
    """两把锁固定按 workout → nutrition 的顺序拿，避免死锁。

    不合并任一域的全量快照——跨域出参形状固定，卡片只吃摘要字段。
    """
    try:
        args = json.loads(raw_args)
        if not isinstance(args, dict):
            raise ActionError("INVALID_ARGUMENT", "请求参数必须为对象。")
        workout_path, nutrition_path = _resolve_cross_paths()
        with _workout.open_store(workout_path) as workout_store:
            with _nutrition._store_lock(nutrition_path):
                store = CrossStore(
                    workout_store,
                    _nutrition.Store(nutrition_path),
                )
                return handler(args, store)
    except (json.JSONDecodeError, ActionError) as exc:
        code = getattr(exc, "code", "INVALID_JSON")
        message = getattr(exc, "message", "请求参数不是合法 JSON。")
        return error_envelope(code, message)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return error_envelope("INTERNAL_ERROR", "处理请求时发生内部错误。")


def execute(handler, raw_args: str, store_path=None) -> dict:
    if domain_of(handler) == "cross":
        return _execute_cross(handler, raw_args)
    return _module_for(handler).execute(handler, raw_args, store_path)


def run(handler, store_path=None, raw_args: str | None = None) -> int:
    if domain_of(handler) == "cross":
        if raw_args is None:
            raw_args = sys.argv[1] if len(sys.argv) > 1 else "{}"
        print(
            json.dumps(
                execute(handler, raw_args, store_path),
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 0
    return _module_for(handler).run(handler, store_path, raw_args)


# 入口 gate 码（``_run.py`` 在 handler 起跑前拦截）。统一不可重试——缺路由表 /
# 未知 tool / visibility 不匹配，重试同一次调用不会有不同结果。
GATE_CODES = frozenset(
    ("UNKNOWN_TOOL", "FORBIDDEN", "SCRIPT_MISSING", "NO_APP_YAML", "BAD_APP_YAML")
)


def error_envelope(code: str, message: str) -> dict:
    """给 ``_run.py`` 入口拦截用。业务拒绝走各领域自己的 ``error_envelope``。"""
    return {
        "phase": "error",
        "code": code,
        "message": message,
        "retryable": False,
    }


# workout
require_text = _workout.require_text
require_int = _workout.require_int
touch = _workout.touch
optional_date = _workout.optional_date
optional_number = _workout.optional_number
new_record = _workout.new_record
advice_for = _workout.advice_for
normalize_soreness = _workout.normalize_soreness
require_library_entry = _workout.require_library_entry
today_iso = _workout.today_iso
require_month = _workout.require_month
DEFAULT_TREND_WEEKS = _workout.DEFAULT_TREND_WEEKS
MAX_TREND_WEEKS = _workout.MAX_TREND_WEEKS
MIN_TREND_WEEKS = _workout.MIN_TREND_WEEKS
MEASUREMENT_PARTS = _workout.MEASUREMENT_PARTS
SEXES = _workout.SEXES
ACTIVITY_LEVELS = _workout.ACTIVITY_LEVELS
library_entry = _workout.library_entry
exercise_library = _workout.exercise_library
rep_unit_of = _workout.rep_unit_of
session_energy_inputs = _workout.session_energy_inputs
body_profile_payload = _workout.body_profile_payload
MAX_SETS = _workout.MAX_SETS
MAX_REPS = _workout.MAX_REPS
MAX_PER_SESSION = _workout.MAX_PER_SESSION
check_exercise_keys = _workout.check_exercise_keys
exercise_row = _workout.exercise_row
append_exercises = _workout.append_exercises
session_for = _workout.session_for
pick_exercises = _workout.pick_exercises
match_by_name = _workout.match_by_name
ordinal_of = _workout.ordinal_of


def model_view(tool: str, structured: dict) -> dict:
    """给模型的回执。训练域把整份快照收小；营养和报告的出参本来就只有结果，原样给。"""
    if TOOL_DOMAIN.get(tool) == "workout":
        return _workout.model_view(tool, structured)
    return structured

# nutrition
