#!/usr/bin/env python3
"""统一入口：28 个工具，两套运行时，一条命令。

    python3 /data/skills/health-steward/scripts/_run.py <tool> '<args_json>'
    python3 /data/skills/health-steward/scripts/_run.py help [tool]

工具名按领域加了前缀（diet_ / workout_ / body_ / nutrition_ / report_），合并前那套旧名
（get_day / get_today …）作为别名照样能调：长程会话的历史里全是旧名，模型照着抄也得通。
``help`` 打印一行签名，模型不用再去翻 app.yaml。

本包是运动训练和饮食记录两套能力合出来的，业务实现各自独立，差异收在这里的两个
runtime 上，由 ``_routes.json`` 的 ``runtime`` 字段分派：

``workout``  训练 / 体重 / 报告 / 营养区间。handler 是 ``(args, store) -> dict`` 的函数，
            由 ``_store.execute`` 统一加锁、补全量快照、兜错误信封。快照整份给卡，
            给模型的回执由 ``_store.model_view`` 收小——整份动作库和 card_* 模型用不上。

``diet``    饮食。handler 是独立进程 ``diet_api.py``，出参里 ``_model`` 段是给模型的精简回执，
            其余是给卡的完整快照。所以这一路要摘 ``_model``、再单独校验卡片载荷。

两条路给模型的回执形状一致：成功带 ``phase``（工具名）和 ``ok: true``；失败是
``phase: "error"`` + ``code`` / ``message`` / ``retryable``，参数问题另带 ``usage`` 一行签名。

**stdout 恰好两行**（出卡的工具）：第一行业务 JSON 给模型，第二行
``__ONEAGENT_APP_RESULT__`` 信封给宿主。少了第二行不会报错，而是一次静默成功——
HTTP 200、结果里没有 structuredContent，卡面拿不到数据，用户看到的是点了没反应。

visibility 归本文件管：网关那边写明了不读本地 Registry。不在 visibility 里的 tool 拒成
``FORBIDDEN``，不认识的名字拒成 ``UNKNOWN_TOOL``；被拦下的调用只打一行错误 JSON、**不打
sentinel**——handler 根本没起，就没有旁路记录可言。字段级校验仍归 handler。

路由表读 ``_routes.json`` 而不是 ``assets/app.yaml``：沙箱里不保证装了 PyYAML。它是从
app.yaml 蒸馏出来的派生物，``tests/test_run_py.py`` 每次跑都拿 app.yaml 重新推一遍逐字段比对。
"""

from __future__ import annotations

import fcntl
import hashlib
import importlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

APP_RESULT_MARKER = "__ONEAGENT_APP_RESULT__"
MODEL_VIEW_KEY = "_model"
# 界面发起的调用调者恒为 app；模型从沙箱 bash 调时必须带 ONEAGENT_APP_CALLER=model，
# 否则日报周报这种只对模型开放的工具会被拦。沙箱里没有 `app` CLI（exit 127）。
CALLER = os.environ.get("ONEAGENT_APP_CALLER", "app")
COMMAND = "ONEAGENT_APP_CALLER=model python3 /data/skills/health-steward/scripts/_run.py"

SCRIPTS_DIR = Path(__file__).resolve().parent
import _boot
_boot.install()
ROUTES_PATH = SCRIPTS_DIR / "_routes.json"
DIET_HANDLER = SCRIPTS_DIR / "diet" / "diet_api.py"

DOMAIN_LABELS = (
    ("diet_", "饮食"),
    ("workout_", "训练"),
    ("body_", "体重围度与档案"),
    ("nutrition_", "营养区间"),
    ("report_", "日报周报"),
    ("now_", "到点提醒"),
)


def load_routes(path: Path | None = None) -> dict:
    return json.loads((path or ROUTES_PATH).read_text(encoding="utf-8"))


def resolve_name(routes: dict, name: str) -> str:
    """旧名换成现在的工具名；本来就是新名或不认识的原样返回。"""
    return (routes.get("aliases") or {}).get(name, name)


def visible_to_app(tool: dict, caller: str | None = None) -> bool:
    """没声明 visibility 就是对模型和页面全开放。"""
    who = CALLER if caller is None else caller
    visibility = tool.get("visibility") or []
    return not visibility or who in visibility


def impl_name(tool: dict) -> str:
    """handler 脚本的文件名即实现名：训练侧是函数名，饮食侧是 diet_api 的 operation。"""
    return Path(tool.get("handler") or "").stem


def build_result_record(routes: dict, tool_name: str, tool: dict,
                        arguments: dict, structured: dict) -> dict:
    """``__ONEAGENT_APP_RESULT__`` 那行的载荷。

    没绑 ``resourceUri`` 的 tool，``resourceUri`` 与 ``resource`` 这两个键不存在
    （不是空值）：后端 ``app_result_emit`` 的 ``resourceURIOf`` 取不到 uri 就把这条丢掉。
    """
    record = {
        "source": "skill",
        "app": routes["app"],
        "toolName": tool_name,
        "arguments": arguments,
        "status": "error" if structured.get("phase") == "error" else "success",
    }
    uri = tool.get("resourceUri") or ""
    if uri:
        record["resourceUri"] = uri
        record["resource"] = (routes.get("resources") or {}).get(uri) or {"uri": uri}
    record["structuredContent"] = structured
    record["content"] = []
    return record


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


# 饮食分析的 XCard 与 Now show_widget 不混用。这里只守饮食分析那张卡：
# 有宿主轮次键时，各轮独立 first-card-wins；没有轮次键时，用短窗口挡住同一次工具循环里
# 的第二张卡。窗口不能盖住下一句用户消息：Now「去记录」先出过卡，用户几十秒内补图，
# 60 秒窗口会把带图的那张卡吞掉。
_CARD_SLOT = Path(
    os.environ.get("ONEAGENT_CARD_SLOT")
    or Path(tempfile.gettempdir()) / "oneagent-health-card-slot"
)
_CARD_SLOT_LOCK_SUFFIX = ".lock"
_COMPAT_WINDOW_SECONDS = 15.0
_TURN_MARKER_TTL_SECONDS = 24 * 60 * 60
_TURN_ID_ENVS = ("ONEAGENT_RESPONSE_ID", "ONEAGENT_TURN_ID", "WORKBUDDY_TURN_ID")


def _turn_key() -> str | None:
    for name in _TURN_ID_ENVS:
        value = (os.environ.get(name) or "").strip()
        if value:
            return hashlib.sha256(value.encode("utf-8")).hexdigest()
    return None


def _read_card_slot_state(now: float) -> dict:
    try:
        raw = json.loads(_CARD_SLOT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    turns = raw.get("turns") if isinstance(raw.get("turns"), dict) else {}
    fresh_turns = {}
    for key, stamp in turns.items():
        try:
            stamp_n = float(stamp)
        except (TypeError, ValueError):
            continue
        if 0 <= now - stamp_n < _TURN_MARKER_TTL_SECONDS:
            fresh_turns[str(key)] = stamp_n
    try:
        fallback = float(raw.get("fallback"))
    except (TypeError, ValueError):
        fallback = 0.0
    if now - fallback >= _COMPAT_WINDOW_SECONDS or fallback > now:
        fallback = 0.0
    return {"turns": fresh_turns, "fallback": fallback}


def _claim_card_slot(uri: str = "") -> bool:
    """原子领取本轮唯一卡槽；URI 不参与判定，同一 URI 连发也只允许第一次。"""
    del uri
    now = time.time()
    turn_key = _turn_key()
    lock_path = Path(str(_CARD_SLOT) + _CARD_SLOT_LOCK_SUFFIX)
    try:
        _CARD_SLOT.parent.mkdir(parents=True, exist_ok=True)
        with open(lock_path, "a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                state = _read_card_slot_state(now)
                if turn_key:
                    if turn_key in state["turns"]:
                        return False
                    state["turns"][turn_key] = now
                else:
                    if state["fallback"]:
                        return False
                    state["fallback"] = now
                temp_path = _CARD_SLOT.with_name(f"{_CARD_SLOT.name}.{os.getpid()}.tmp")
                temp_path.write_text(
                    json.dumps(state, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8",
                )
                os.replace(temp_path, _CARD_SLOT)
                return True
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        # 守卫存储不可用时保留原有可用性：业务仍成功，卡片照常尝试下发。
        return True


def _reject(code: str, message: str) -> int:
    """入口层拦下：只打一行错误 JSON，不打 sentinel。

    形状跟 ``_store.error_envelope`` 一致（含 ``retryable``），这里不 import 它——
    饮食那条 runtime 整条链路都用不到 ``_store``，为一个四键字典把它拖进来不值。
    两处形状由 ``tests/test_run_py.py`` 钉住。
    """
    _print_json({"phase": "error", "code": code, "message": message, "retryable": False})
    return 2


def _finish_model_view(name: str, tool: dict, view: dict) -> dict:
    """两条 runtime 给模型的回执收成同一个形状。"""
    if view.get("phase") == "error":
        if view.get("code") == "INVALID_ARGUMENT" and tool.get("usage"):
            view = {**view, "usage": tool["usage"]}
        return view
    rest = {key: value for key, value in view.items() if key not in ("phase", "ok")}
    return {"phase": name, "ok": True, **rest}


# 日报周报自己不出 XCard。成功之后占住本轮卡槽，只能挡住之后才调的饮食工具。
# 先调 diet_day / diet_record / diet_estimate 时卡已经发出，这里收不回来。
_REPORT_TOOLS = frozenset(("report_daily", "report_weekly"))


def _emit(routes: dict, name: str, tool: dict, arguments: dict,
          model_view: dict, card_payload: dict | None) -> int:
    """打业务行，够条件再打 sentinel。``card_payload`` 为 None 表示这次不出卡。"""
    finished = _finish_model_view(name, tool, model_view)
    _print_json(finished)
    if name in _REPORT_TOOLS and finished.get("ok"):
        _claim_card_slot()
    uri = tool.get("resourceUri")
    if os.environ.get("ONEAGENT_SUPPRESS_CARD") == "1":
        return 0
    if not uri or card_payload is None:
        return 0
    if not _claim_card_slot(uri):
        return 0
    print(APP_RESULT_MARKER + " " + json.dumps(
        build_result_record(routes, name, tool, arguments, card_payload),
        ensure_ascii=False, separators=(",", ":")))
    return 0


def run_workout(routes: dict, name: str, tool: dict, raw_args: str, arguments: dict) -> int:
    """训练侧：快照整份给卡，模型拿收小后的回执。"""
    import _store

    impl = impl_name(tool)
    try:
        module = importlib.import_module(impl)
        handler = getattr(module, impl)
    except (ImportError, AttributeError):
        # 只报路径，不带异常原文：那里面可能夹着调用方传进来的内容。
        return _reject("SCRIPT_MISSING", f"handler 起不来：{tool['handler']}")

    structured = _store.execute(handler, raw_args)
    # 业务失败时不出卡。错误信封只有 phase/code/message/retryable，拿它当卡片数据发下去，
    # 卡面每一条绑定都取不到值，端上画出来是一张只剩按钮的空壳——2026-09-23 线上就是
    # 这么出的（plan_session 撞 SESSION_EXISTS，用户看到一张空卡）。
    # 更糟的是资源声明 dataMode=keep_latest，这张空壳会把上一张好卡顶掉。
    card = None if structured.get("phase") == "error" else structured
    return _emit(routes, name, tool, arguments, _store.model_view(impl, structured), card)


def run_diet(routes: dict, name: str, tool: dict, raw_args: str, arguments: dict) -> int:
    """饮食侧：摘掉 ``_model`` 给模型，剩下的整份给卡。"""
    from payload_schema import PayloadValidationError, validate_payload

    # operation 由工具定，不从入参读——app.yaml 里每个 tool 的 schema 都没有这个字段。
    payload = {**arguments, "operation": impl_name(tool)}
    completed = subprocess.run(
        [sys.executable, str(DIET_HANDLER),
         json.dumps(payload, ensure_ascii=False, separators=(",", ":"))],
        capture_output=True, text=True, check=False,
    )
    if completed.stderr:
        sys.stderr.write(completed.stderr)

    output = completed.stdout.strip()
    try:
        app_view = json.loads(output)
    except json.JSONDecodeError:
        # handler 没能输出合法 JSON：原样透出去，别再补 sentinel 让宿主渲染半截数据。
        print(output or "{}")
        return completed.returncode or 1

    model_view = app_view.pop(MODEL_VIEW_KEY, None) or {}
    if completed.returncode != 0 or model_view.get("phase") == "error":
        _print_json(_finish_model_view(name, tool, model_view))
        return completed.returncode or 1

    # 摘掉 _model 之后空了：当天没餐的读操作、或删光当日被 dispatch 压掉了卡片。
    if not app_view:
        _print_json(_finish_model_view(name, tool, model_view))
        return completed.returncode

    try:
        validate_payload(app_view)
    except PayloadValidationError as exc:
        return _reject("INVALID_PAYLOAD", str(exc))

    # XCard 只画 current_meal。没有这一餐时不出卡，空绑定会把上一张卡顶掉。
    meal = app_view.get("current_meal")
    card = app_view if isinstance(meal, dict) and meal.get("meal_id") else None
    return _emit(routes, name, tool, arguments, model_view, card)


RUNTIMES = {"workout": run_workout, "diet": run_diet}


def print_help(routes: dict, topic: str = "") -> int:
    """``help`` 打全部工具的一行签名；``help <tool>`` 打那一个的签名和用途。"""
    tools = routes.get("tools") or {}
    if topic:
        name = resolve_name(routes, topic)
        tool = tools.get(name)
        if tool is None:
            return _reject("UNKNOWN_TOOL", f"没有这个工具：{topic}")
        lines = [tool.get("usage") or name, tool.get("summary") or ""]
        if tool.get("aliases"):
            lines.append(f"旧名：{'、'.join(tool['aliases'])}")
        print("\n".join(line for line in lines if line))
        return 0

    print(f"调用：{COMMAND} <工具名> '<JSON>'（? 为可选）")
    for prefix, label in DOMAIN_LABELS:
        rows = [tool for key, tool in tools.items() if key.startswith(prefix) and not tool.get("hidden")]
        if not rows:
            continue
        print(f"{label}")
        for tool in rows:
            print(f"  {tool.get('usage')}  —— {tool.get('summary')}")
    return 0


def main(argv: list[str]) -> int:
    tool_name = argv[1] if len(argv) > 1 else ""
    raw_args = argv[2] if len(argv) > 2 else "{}"

    try:
        routes = load_routes()
    except OSError:
        return _reject("NO_APP_YAML", f"路由表读不出来：{ROUTES_PATH.name}")
    except json.JSONDecodeError:
        return _reject("BAD_APP_YAML", f"路由表不是合法 JSON：{ROUTES_PATH.name}")

    if tool_name in ("help", "--help", "-h"):
        return print_help(routes, argv[2] if len(argv) > 2 else "")

    name = resolve_name(routes, tool_name)
    tool = (routes.get("tools") or {}).get(name)
    if tool is None:
        return _reject("UNKNOWN_TOOL", f"没有这个工具：{tool_name}。跑 _run.py help 看全部工具。")
    if not visible_to_app(tool):
        return _reject("FORBIDDEN", f"{name} 不对页面开放。")

    # 入参怎么解析、坏了算哪种错，归各自的 runtime；这里只把调用方原样传来的载荷
    # 回显进信封，解不出对象就回显空对象。
    try:
        arguments = json.loads(raw_args)
    except json.JSONDecodeError:
        arguments = {}
    if not isinstance(arguments, dict):
        arguments = {}

    runtime = RUNTIMES.get(tool.get("runtime", ""))
    if runtime is None:
        return _reject("BAD_APP_YAML", f"{name} 没声明合法的 runtime。")
    return runtime(routes, name, tool, raw_args, arguments)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
