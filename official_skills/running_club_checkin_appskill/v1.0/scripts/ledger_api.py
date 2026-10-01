#!/usr/bin/env python3
"""跑团打卡卡片 App 的业务 handler（operation 路由）。

职责：把模型识别出的打卡意图变成一张可编辑卡片（draft_checkin），用户在卡片上点
确认后再落库（commit_checkin）。checkin 的写入一律经 tracker.py 子进程，本模块
不直接写 checkin 表——卡片上展示的成员名永远取 tracker 落库时的真实成员名。

输出：单个 JSON（structuredContent），phase=checkin_card 或 phase=error。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import pathname2url

import card_schema
from cli_contract import ContractError, validate_operation

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
ASSETS_DIR = os.path.join(SKILL_ROOT, "assets")

# 与 tracker.py / _run.py 共用同一解析（assets/persist_paths.py），保证只有一个 tracker.db。
if ASSETS_DIR not in sys.path:
    sys.path.insert(0, ASSETS_DIR)
import persist_paths  # noqa: E402

# 业务规则跑的是可写运行目录里那份（管理员改过的），不是挂载上的包内版本。
# 播种在这里也做一次：ledger_api 可能是本轮第一个被调到的入口。
RUN_ASSETS = persist_paths.ensure_run_dir(ASSETS_DIR)
TRACKER_PY = os.path.join(RUN_ASSETS, "tracker.py")
if not os.path.isfile(TRACKER_PY):
    TRACKER_PY = os.path.join(ASSETS_DIR, "tracker_impl.py")
if RUN_ASSETS != ASSETS_DIR:
    sys.path.insert(0, RUN_ASSETS)
import rules  # noqa: E402  # 复用 effective_km 折算，配速计算口径与 tracker.py 保持一致

_ROOT = SKILL_ROOT
PERSIST_DIR, DB_PATH = persist_paths.resolve_db_path(_ROOT)

_TZ = timezone(timedelta(hours=8))


class LedgerError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


# ---------------------------------------------------------------------------
# DB（只读 tracker.db 做查询；checkin 写入一律走 tracker.py 子进程）
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(_TZ).isoformat(timespec="seconds")


def _today() -> str:
    return datetime.now(_TZ).strftime("%Y-%m-%d")


def _connect():
    uri = "file:" + pathname2url(DB_PATH) + "?nolock=1"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = MEMORY")
    conn.execute("PRAGMA synchronous = OFF")
    return conn


def _db():
    """只读连接 tracker.db：本模块自己不建表，checkin 的建表与写入一律走 tracker.py。"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    open(DB_PATH, "a").close()
    return _connect()


def _gen_id(prefix: str, *parts: str) -> str:
    seed = "|".join([*parts, _now(), os.urandom(4).hex()])
    return f"{prefix}_{hashlib.md5(seed.encode()).hexdigest()[:10]}"


# ---------------------------------------------------------------------------
# tracker.py 子进程（不在持有本模块任何锁时调用，避免与 tracker 自身 flock 死锁）
# ---------------------------------------------------------------------------

def _run_tracker(cli_args: list[str]) -> str:
    # 强制与本模块同一库，避免子进程因漏 env 又解析到别处
    child_env = os.environ.copy()
    child_env["TRACKER_DATA_DIR"] = PERSIST_DIR
    child_env["TRACKER_DB"] = DB_PATH
    completed = subprocess.run(
        [sys.executable, TRACKER_PY, *cli_args],
        capture_output=True, text=True, check=False,
        cwd=os.path.dirname(TRACKER_PY), env=child_env,
    )
    out = (completed.stdout or "").strip()
    if completed.returncode != 0 or out.startswith("error="):
        raise LedgerError("TRACKER_ERROR", out or (completed.stderr or "tracker 执行失败").strip())
    return out


def _resolve_member(query: str) -> dict[str, Any]:
    """用 tracker find_member 解析成员，返回 {id, name, age_exempt, walk_valid}。查不到即报错。"""
    out = _run_tracker(["find_member", str(query)])
    fields = dict(re.findall(r"(\w+)=([^\s]*)", out))
    if not fields.get("id"):
        raise LedgerError("MEMBER_NOT_FOUND",
                          f"成员未找到：{query}。请先用人话请用户把这个人建成群成员，"
                          "用户明确同意后再建档。对用户禁止贴任何命令。")
    return {
        "id": fields["id"],
        "name": fields.get("name", str(query)),
        "age_exempt": int(fields.get("age_exempt") or 0),
        "walk_valid": int(fields.get("walk_valid") or 0),
    }


# 跑步类项目才做配速合理性校验；游泳/健走/年龄豁免走 rules 其它分支。
_PACE_CHECK_TYPES = frozenset({"outdoor_run", "treadmill", "indoor_run"})












# ---------------------------------------------------------------------------
# 台账读取（构造给 View 的全量状态）
# ---------------------------------------------------------------------------





def _to_km(distance_raw: float, unit: str) -> float:
    """只换单位，不做项目折算。优先用 rules.to_km。

    rules.py 在运行目录里是**冻结**的：老群那份可能是还没拆出 to_km 的版本，而本文件
    永远是包内最新版。硬调 rules.to_km 会在那些群上抛 AttributeError，所以这里
    getattr 兜底。凡是往 rules 里新加的函数，调用方都得按这个写法来。
    """
    fn = getattr(rules, "to_km", None)
    if fn is not None:
        return fn(distance_raw, unit)
    if unit in ("swim_m", "m"):
        return distance_raw / 1000.0
    if unit == "miles":
        return distance_raw * rules.MILES_TO_KM
    return distance_raw


def _card_pace_km(distance_raw, unit: str):
    """卡面配速用的距离：只换单位，不做游泳代跑折算。

    ×4 只属于卡面上「折算跑步」那一行；配速是「每公里游多久」，除的是真实游程。
    台账那边的达标累计照旧走 rules.effective_km，这里不影响它。
    """
    if distance_raw is None:
        return None
    return _to_km(distance_raw, unit)


def _pace_seconds(distance_km, duration_seconds) -> int | None:
    """由里程+时长算配速（秒/公里）；算不出则 None。

    卡片下发的是这个数值（card_data 里 pace 的 raw），展示文本由 card_schema 渲。
    台账那边仍要 5'25" 形态的文案，走 _fmt_pace。

    舍入必须是 half_up：内置 round() 是银行家舍入，正好 .5 时会和客户端自算
    差一秒（4km/1250s → 312.5，round() 给 312，客户端给 313）。
    """
    if not distance_km or not duration_seconds:
        return None
    try:
        dkm = float(distance_km)
        sec = int(duration_seconds)
    except (TypeError, ValueError):
        return None
    if dkm <= 0 or sec <= 0:
        return None
    return int(card_schema.round_half_up(sec / dkm, 0))


























# ---------------------------------------------------------------------------
# operations
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 卡片语义（唯一链路）：draft_checkin 出可编辑草稿卡；commit_checkin 用户确认后落库。
# 旧台账 operation（list_ledger / ingest_image / attribute / set_redeem_rules /
# redeem / delete_ledger）已下线：模型无任何直接写 checkin 的入口，落库只走卡片确认。
# ---------------------------------------------------------------------------

def _coerce_float(value) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f


def _coerce_int(value) -> int | None:
    try:
        i = int(value)
    except (TypeError, ValueError):
        return None
    return i


def _img_key_from_url(value: str) -> str:
    """从 img_id / resourceId / quote.image_url 提取归一化图片 id（与 tracker _img_key 口径一致）。"""
    text = (value or "").strip()
    if not text:
        return ""
    for prefix in ("img=", "resourceId="):
        pos = text.find(prefix)
        if pos >= 0:
            text = text[pos + len(prefix):]
    text = unquote(text.split(";")[0].split("&")[0].split("?")[0])
    m = re.match(r"[0-9a-zA-Z]{8,}", text)
    return m.group(0) if m else ""


def _build_raw_summary(args: dict) -> str:
    """把 img_id / quote.image_url / note 编成 tracker --raw（img= 落库查重用）。"""
    img = ""
    img_id = str(args.get("img_id") or "").strip()
    if img_id and img_id != "-":
        img = _img_key_from_url(img_id)
    if not img:
        quote = args.get("quote")
        if isinstance(quote, dict):
            img = _img_key_from_url(str(quote.get("image_url") or ""))
    note = str(args.get("note") or "").strip().replace("'", "").replace('"', "")
    if img:
        return f"img={img}; {note or 'card checkin'}"
    return note


# 卡片四态：pending 待确认 / recording 待录入 / confirmed 已确认 / cancelled 已取消。
# recording 是端上点确认到模型回包的中间态，本 skill 不吐。
# 超时自动结算：字段齐全则落库打成 confirmed，校验失败则 cancelled。
STATUS_PENDING = "pending"
STATUS_RECORDING = "recording"
STATUS_CONFIRMED = "confirmed"
STATUS_CANCELLED = "cancelled"
TERMINAL_STATUSES = (STATUS_CONFIRMED, STATUS_CANCELLED)
EMITTED_STATUSES = (STATUS_PENDING, STATUS_CONFIRMED, STATUS_CANCELLED)

# 待确认卡片的存活时长。超过未操作由服务端定时任务自动结算（成功 confirmed / 失败 cancelled）。
CARD_EXPIRE_SECONDS = 300


def _expire_at(status: str) -> int:
    """只有待确认卡给倒计时；待录入/已确认/已取消一律归零。"""
    if status == STATUS_PENDING:
        return int(datetime.now(_TZ).timestamp()) + CARD_EXPIRE_SECONDS
    return 0


def _is_auto(args: dict) -> bool:
    """超时自动确认：只 update，失败不换新卡。"""
    for key in ("auto", "timeout", "auto_confirm"):
        v = args.get(key)
        if v is True or str(v).lower() in ("1", "true", "yes"):
            return True
    return False


def _checkin_missing(card_data: dict[str, Any], *, member_registered: bool,
                     age_exempt: bool = False) -> list[str]:
    """卡片落库最小字段缺失清单（供 UI 提示 / 确认门槛）。

    从 card_data 的 sections 里回读 raw 值，键名用 fieldId——这样"下发给客户端的
    那份"和"校验依据的那份"是同一份数据，客户端在编辑面板改完回传后，同一个函数
    可以直接复用来判断能不能确认落库。
    """
    missing: list[str] = []
    if not card_schema.member_name_of(card_data).strip():
        missing.append("memberName")
    elif not member_registered:
        missing.append("member_registered")
    distance = _coerce_float(card_schema.field_raw(card_data, "distance"))
    if distance is None or distance <= 0:
        missing.append("distance")
    if card_schema.field_semantic_code(card_data, "sportName") not in rules.ACTIVITY_TYPES:
        missing.append("sportName")
    if not str(card_schema.field_raw(card_data, "date") or "").strip():
        missing.append("date")
    if not age_exempt:
        duration = _coerce_int(card_schema.field_raw(card_data, "duration"))
        if duration is None or duration <= 0:
            missing.append("duration")
        pace = _coerce_int(card_schema.field_raw(card_data, "pace"))
        if pace is None or pace <= 0:
            missing.append("pace")
    return missing


def _validate_commit_pace(args: dict, member: dict[str, Any]) -> None:
    """跑步类：配速不合理则拒绝落库（不再写 valid=0 的脏行）。"""
    activity_type = args.get("activity_type")
    if activity_type not in _PACE_CHECK_TYPES:
        return
    if member.get("age_exempt"):
        return
    duration_seconds = _coerce_int(args.get("duration_seconds"))
    if duration_seconds is None or duration_seconds <= 0:
        raise LedgerError("INVALID_ARGUMENT", "duration_seconds 必须为正数")
    unit = args.get("unit") or "km"
    distance_raw = _coerce_float(args.get("distance_raw"))
    if distance_raw is None or distance_raw <= 0:
        raise LedgerError("INVALID_ARGUMENT", "distance_raw 必须为正数")
    distance_km = rules.effective_km(activity_type, distance_raw, unit)
    valid, note = rules.judge_validity(
        activity_type, distance_km, duration_seconds,
        bool(member.get("age_exempt")), bool(member.get("walk_valid")))
    if not valid and "配速" in note:
        raise LedgerError("INVALID_PACE", f"配速不合理，无法落库：{note}")


def _internal_unit(args: dict) -> dict:
    """把卡片协议单位（km / m）翻回内部单位（km / miles / swim_m）。

    下发时 _protocol_unit 把 swim_m 显示成 m，用户在卡上看到的、确认后回传的就是 m。
    这里必须翻回去：checkin 的内部 unit 不认 m，
    否则确认即落库失败、旧卡被取消重出一张单位仍是 m 的新卡，用户会一直绕圈。
    内部没有「跑步的米」这个单位，非游泳的 m 一律折成 km。
    """
    if str(args.get("unit") or "") != "m":
        return args
    args = dict(args)
    if str(args.get("activity_type") or "") == "swim":
        args["unit"] = "swim_m"
        return args
    args["unit"] = "km"
    raw = _coerce_float(args.get("distance_raw"))
    if raw is not None:
        args["distance_raw"] = raw / 1000.0
    return args


def _protocol_unit(unit: str) -> str:
    """把内部 unit 映射到协议允许的 km / m。

    内部 swim_m 是"游泳按米计"，对客户端只是米；miles 暂无协议取值，原样透传，
    由客户端组件按未知单位兜底展示（比静默改成 km 少一个错算风险）。
    """
    if unit == "swim_m":
        return "m"
    return unit or "km"


def _build_card(operation: str, args: dict, *, member_registered: bool,
                status: str, receipt: dict | None = None) -> dict[str, Any]:
    """把卡片字段整理成 structuredContent（draft / commit / cancel 共用回包结构）。

    工具入参名（member / occurred_at / distance_raw / unit）与下发契约解耦：入参是
    模型和 tracker CLI 的契约，card_data 是渲染契约（schema 树，见 card_schema），
    两者各自演进。信封上只留路由与状态：card_id / operate_type / status / expire_at；
    改旧卡再加 update_seq_id。渲染要用的一切都在 card_data 里。
    """
    if status not in EMITTED_STATUSES:
        raise LedgerError(
            "INVALID_ARGUMENT",
            f"skill 不吐卡片状态 {status!r}（待录入 recording 由端上本地切，"
            "只下发 pending / confirmed / cancelled）")
    unit = args.get("unit") or "km"
    distance_raw = _coerce_float(args.get("distance_raw"))
    duration_seconds = _coerce_int(args.get("duration_seconds"))
    # 运动类型缺省默认户外跑（跑团绝大多数场景）：让草稿卡片天然满足最小字段、用户直接确认；
    # 模型识图/读描述若判定为其它类型（游泳/健走/跑步机/室内跑等），须在 draft_checkin 就传对应值直接覆盖，
    # 不要留空反问用户。非空但非法的类型保持原样（会进 missing，暴露模型传参错误）。
    raw_at = str(args.get("activity_type") or "").strip()
    if raw_at in rules.ACTIVITY_TYPES:
        activity_type = raw_at
    elif raw_at == "":
        activity_type = "outdoor_run"
    else:
        activity_type = raw_at
    eff_km = (rules.effective_km(activity_type, distance_raw, unit)
              if distance_raw is not None and activity_type else None)
    act_km = (_card_pace_km(distance_raw, unit)
              if distance_raw is not None and activity_type else None)
    equiv_km = None
    equiv_factor = None
    if eff_km is not None and distance_raw is not None and activity_type:
        raw_km = rules.to_km(distance_raw, unit)
        if raw_km > 0:
            equiv_factor = rules.equivalent_factor(activity_type, distance_raw, unit)
            if equiv_factor is not None:
                equiv_km = eff_km
    # card_id 要先算出来：它既是信封的主键，也进 card_data.cardId 给客户端对卡。
    card_id = args.get("card_id") or _gen_id("card", args.get("group_id", "default"))
    # 日期缺省=当天：卡面上不留空日期，用户直接确认即可（与记账同口径）。
    occurred_date = str(args.get("occurred_at") or args.get("today") or "").strip() or _today()
    img_id = str(args.get("img_id") or "").strip()
    age_exempt = _age_exempt_for_card(args, member_registered)
    card_data = card_schema.build_card_data(
        card_id=card_id,
        member_name=args.get("member", ""),
        member_id=args.get("member_id") or None,
        occurred_date=occurred_date,
        activity_type=activity_type,
        duration_seconds=duration_seconds,
        distance=distance_raw,
        distance_unit=_protocol_unit(unit),
        pace_seconds=_pace_seconds(act_km, duration_seconds),
        location=args.get("location", "") or "",
        status=status,
        equivalent_km=equiv_km,
        equivalent_factor=equiv_factor,
        age_exempt=age_exempt,
    )
    missing = _checkin_missing(
        card_data, member_registered=member_registered, age_exempt=age_exempt)
    out = {
        "phase": "checkin_card",
        "operation": operation,
        "group_id": args.get("group_id", "default"),
        "card_id": card_id,
        # 发起人：谁触发了这次打卡。与 card_data 平级而不在卡面字段里——它不是要展示的
        # 一行，只标记这张卡的来源。注意它和「打卡对象」是两回事：A 替 B 打卡时
        # user_id 是 A，card_data 里的 memberName 是 B。
        # user_id 是这张卡的发起人。普通出卡模型填 user_N，群聊 agent 出卡前还原成真实 uid 再下发；
        # 模型漏填时服务端用本轮发言人补。确认链路用 action.user_id。
        "user_id": str(args.get("user_id") or ""),
        "status": status,
        "operate_type": "update" if status != STATUS_PENDING else "create",
        # expire_at 在信封而不在 card_data：它不是卡面上的一行，客户端拿它做本地倒计时。
        "expire_at": _expire_at(status),
        "card_data": card_data,
        # 备注与 quote 不进 card_data；img_id 在信封层供 host 写 app.env。
        "note": args.get("note", "") or "",
        "quote": args.get("quote") or {},
        "member_registered": member_registered,
        "min_ready": not missing,
        "missing": missing,
    }
    if status != STATUS_PENDING:
        # 改已有卡：update_seq_id 由群聊服务端从当前 GUI_ACTION/app.env 消息 extra 填写。
        out["update_seq_id"] = str(args.get("update_seq_id") or "")
    # 编辑模式：把 event_id 带进 structuredContent，让"修改已落盘记录"的卡片一路带到 commit。
    if args.get("event_id"):
        out["event_id"] = str(args["event_id"])
    # 纠正新卡：supersedes 指向被替代的旧 card_id。真正置灰靠同轮再吐一张 cancelled update。
    if args.get("supersedes"):
        out["supersedes"] = str(args["supersedes"])
    if receipt is not None:
        out["receipt"] = receipt
    if img_id:
        out["img_id"] = img_id
    return out


def _try_resolve_member(member: str) -> tuple[bool, str, bool]:
    """非致命地判断成员是否已建档；返回 (registered, display_name, age_exempt)。"""
    member = str(member or "").strip()
    if not member:
        return False, "", False
    try:
        info = _resolve_member(member)
        return True, info["name"], bool(info.get("age_exempt"))
    except LedgerError:
        return False, member, False


def _age_exempt_for_card(args: dict, member_registered: bool) -> bool:
    """出卡/校验时判断成员是否 60+ 年龄豁免（仅已建档成员可查）。"""
    if not member_registered:
        return False
    member = str(args.get("member") or "").strip()
    if not member:
        return False
    try:
        return bool(_resolve_member(member).get("age_exempt"))
    except LedgerError:
        return False


def op_draft_checkin(conn, args) -> dict[str, Any]:
    """出可编辑打卡草稿卡片——不落库、不写表，只回显已知字段供卡片渲染。

    纠正（带 supersedes）：同轮 update 旧卡为已取消 + create 新卡。
    """
    member_registered, name, _ = _try_resolve_member(args.get("member", ""))
    if member_registered:
        args = dict(args, member=name)
    new_card = _build_card("draft_checkin", args, member_registered=member_registered,
                           status=STATUS_PENDING)
    return _with_supersede_cancel(args, new_card, member_registered)


def _with_supersede_cancel(
    args: dict, new_card: dict[str, Any], member_registered: bool,
) -> dict[str, Any]:
    """纠正未确认卡：先 update 旧卡 cancelled，再 create 新卡。"""
    old_id = str(args.get("supersedes") or "").strip()
    new_id = str(new_card.get("card_id") or "")
    if not old_id or old_id == new_id:
        return new_card
    old_card = _build_card(
        "cancel_checkin", dict(args, card_id=old_id),
        member_registered=member_registered, status=STATUS_CANCELLED)
    return {
        "phase": "checkin_card",
        "operation": "draft_checkin",
        "card_id": new_id,
        "supersedes": old_id,
        "cancelled_card_id": old_id,
        "status": STATUS_PENDING,
        "cards": [old_card, new_card],
    }


def _edit_checkin(event_id: str, member: dict, args: dict, activity_type: str,
                  unit: str, distance_raw: float) -> dict[str, Any]:
    """编辑模式：用卡片最新字段整体更正一条已落库 checkin（event_id 不变、引用不变）。
    在同一次 ledger_api 调用内依次 correct 各字段（对模型是"一条命令"），全部走 tracker
    通用 correct（带 reason + 审计 + 自动重算派生列），绝不新增行。"""
    exists = _run_tracker(["list_checkins", "--member", member["id"]])
    if f"event_id={event_id}" not in exists:
        raise LedgerError("CHECKIN_NOT_FOUND", f"未找到要修改的打卡记录：event_id={event_id}")
    _validate_commit_pace(args, member)
    reason = "卡片修改确认"
    fields: list[tuple[str, str]] = [
        ("member_id", member["id"]),
        ("occurred_at", str(args["occurred_at"])),
        ("activity_type", activity_type),
        ("distance_raw", str(distance_raw)),
        ("unit", unit),
    ]
    dur = _coerce_int(args.get("duration_seconds"))
    if dur and dur > 0:
        fields.append(("duration_seconds", str(dur)))
    elif not member.get("age_exempt"):
        raise LedgerError("INVALID_ARGUMENT", "duration_seconds 必须为正数")
    raw = _build_raw_summary(args)
    if raw:
        fields.append(("raw_summary", raw))
    for field, value in fields:
        _run_tracker(["correct", "checkin", event_id, field, value, "--reason", reason])
    receipt = {"event_id": event_id, "member": member["name"], "edited": True}
    return _build_card("commit_checkin", dict(args, member=member["name"]),
                       member_registered=True, status=STATUS_CONFIRMED, receipt=receipt)


def op_find_checkin(conn, args) -> dict[str, Any]:
    """只读查询已落库打卡（供"修改已落盘记录"定位 event_id + 现有字段预填卡片）。不写库、不出卡。"""
    cli = ["list_checkins"]
    if args.get("member"):
        cli += ["--member", str(args["member"])]
    if args.get("period") is not None:
        cli += ["--period", str(args["period"])]
    if args.get("date"):
        cli += ["--date", str(args["date"])]
    out = _run_tracker(cli)
    records: list[dict[str, Any]] = []
    for ln in out.splitlines():
        if not ln.startswith("event_id="):
            continue
        f = dict(re.findall(r"(\w+)=([^\s]*)", ln))
        records.append({
            "event_id": f.get("event_id", ""),
            "member": f.get("member", ""),
            "occurred_at": f.get("occurred_at", ""),
            "period": f.get("period", ""),
            "activity_type": f.get("activity", ""),
            "distance_km": f.get("distance_km", ""),
            "duration_seconds": f.get("duration", ""),
            "valid": f.get("valid", ""),
        })
    return {"phase": "checkin_list", "operation": "find_checkin",
            "group_id": args.get("group_id", "default"), "records": records}


def op_commit_checkin(conn, args) -> dict[str, Any]:
    """用户确认后落库：resolve 成员（须已建档）→ tracker add_checkin 原子落一条 checkin。
    带 event_id 时走编辑模式（整体更正已有记录，不新增）。"""
    activity_type = args.get("activity_type")
    if activity_type not in rules.ACTIVITY_TYPES:
        raise LedgerError("INVALID_ARGUMENT",
                          f"activity_type 非法：{activity_type}"
                          f"（须为 {', '.join(rules.ACTIVITY_TYPES)} 之一）")
    unit = args.get("unit") or "km"
    if unit not in rules.UNITS:
        raise LedgerError("INVALID_ARGUMENT",
                          f"unit 非法：{unit}（须为 {', '.join(rules.UNITS)} 之一）")
    distance_raw = _coerce_float(args.get("distance_raw"))
    if distance_raw is None or distance_raw <= 0:
        raise LedgerError("INVALID_ARGUMENT", "distance_raw 必须为正数")
    member = _resolve_member(args["member"])   # 未建档 → MEMBER_NOT_FOUND
    duration_seconds = _coerce_int(args.get("duration_seconds"))
    age_exempt = bool(member.get("age_exempt"))
    if (duration_seconds is None or duration_seconds <= 0) and not age_exempt:
        raise LedgerError("INVALID_ARGUMENT", "duration_seconds 必须为正数")
    _validate_commit_pace(args, member)

    event_id = str(args.get("event_id") or "").strip()
    if event_id:
        return _edit_checkin(event_id, member, args, activity_type, unit, distance_raw)

    cli = ["add_checkin", member["id"], args["occurred_at"], activity_type,
           str(distance_raw), "--today", args["today"], "--unit", unit]
    if duration_seconds and duration_seconds > 0:
        cli += ["--duration", str(duration_seconds)]
    raw = _build_raw_summary(args)
    if raw:
        cli += ["--raw", raw]
    try:
        out = _run_tracker(cli)
    except LedgerError as exc:
        if exc.code == "TRACKER_ERROR" and "duplicate_checkin" in (exc.message or ""):
            # 幂等：同一张卡重复确认 / 网络重试 → 视为已录入
            receipt = {"duplicate": True, "member": member["name"]}
            card = _build_card("commit_checkin", dict(args, member=member["name"]),
                               member_registered=True, status=STATUS_CONFIRMED,
                               receipt=receipt)
            return card
        raise
    line = next((ln for ln in out.splitlines() if ln.startswith("event_id=")), out.splitlines()[0])
    fields = dict(re.findall(r"(\w+)=([^\s]*)", line))
    receipt = {
        "event_id": fields.get("event_id", ""),
        "member": fields.get("member", member["name"]),
        "period": fields.get("period", ""),
        "distance_km": fields.get("distance_km", ""),
        "valid": fields.get("valid", ""),
        "period_total": fields.get("period_total", ""),
        "qualified": fields.get("qualified", ""),
    }
    return _build_card("commit_checkin", dict(args, member=member["name"]),
                       member_registered=True, status=STATUS_CONFIRMED, receipt=receipt)


def op_delete_checkin(conn, args) -> dict[str, Any]:
    """删除一条【已落库】checkin（软删 deleted_at）。不出卡、不改动前端已完成的卡片，
    仅回文本回执 + 该成员当期最新累计（period_total/qualified/shortage_km）。
    只按 event_id 删除（由 find_checkin 先定位）；指令模糊时应先 find_checkin 让用户确认，不要走到这里。"""
    event_id = str(args.get("event_id") or "").strip()
    if not event_id:
        raise LedgerError("INVALID_ARGUMENT", "delete_checkin 必须提供 event_id（先用 find_checkin 定位目标记录）。")
    reason = str(args.get("reason") or "").strip() or "用户要求删除打卡记录"
    try:
        out = _run_tracker(["delete_checkin", event_id, "--reason", reason])
    except LedgerError as exc:
        if exc.code == "TRACKER_ERROR" and "checkin_not_found" in (exc.message or ""):
            raise LedgerError("CHECKIN_NOT_FOUND",
                              f"未找到要删除的打卡记录：event_id={event_id}（可能已删除，请用 find_checkin 重新确认）")
        raise
    fields = dict(re.findall(r"(\w+)=([^\s]*)", out))
    receipt = {
        "deleted": True,
        "event_id": event_id,
        "member": fields.get("member", ""),
        "period": fields.get("period", ""),
        "period_total": fields.get("period_total", ""),
        "qualified": fields.get("qualified", ""),
        "shortage_km": fields.get("shortage_km", ""),
    }
    # phase 非 checkin_card ⇒ _run.py 不挂 UI 资源 ⇒ 不出卡，仅由元宝文字回复。
    return {"phase": "checkin_deleted", "operation": "delete_checkin",
            "group_id": args.get("group_id", "default"),
            "event_id": event_id, "receipt": receipt}


def op_cancel_checkin(conn, args) -> dict[str, Any]:
    """用户在卡片上点取消：只把卡片打成 cancelled 终态，不写库、不产生任何 checkin。

    与 delete_checkin 的区别是这张卡从来没落过库，所以没有 event_id 可删，
    也不需要回累计数据——纯粹是把待确认的草稿卡收掉。
    """
    member_registered, name, _ = _try_resolve_member(args.get("member", ""))
    if member_registered:
        args = dict(args, member=name)
    return _build_card("cancel_checkin", args, member_registered=member_registered,
                       status=STATUS_CANCELLED)


def _reissue_after_commit_fail(conn, args: dict, exc: BaseException) -> dict[str, Any]:
    """确认链路校验/落库失败：旧卡取消 + 新出一张待确认卡。

    用户已经点了确认，旧卡不能再停在 pending。失败原因写给模型，两张卡的
    structuredContent 由 _run.py 拆成两条 sentinel 下发。
    """
    code = getattr(exc, "code", type(exc).__name__)
    message = getattr(exc, "message", str(exc))
    old_id = str(args.get("card_id") or "").strip()
    cards: list[dict[str, Any]] = []
    if old_id:
        cancel_args = dict(args, card_id=old_id)
        member_registered, name, _ = _try_resolve_member(cancel_args.get("member", ""))
        if member_registered:
            cancel_args = dict(cancel_args, member=name)
        cards.append(_build_card(
            "cancel_checkin", cancel_args,
            member_registered=member_registered, status=STATUS_CANCELLED))
    new_id = _gen_id("card", str(args.get("group_id") or "default"), old_id or "reissue")
    draft_args = dict(args, card_id=new_id)
    if old_id:
        draft_args["supersedes"] = old_id
    member_registered, name, _ = _try_resolve_member(draft_args.get("member", ""))
    if member_registered:
        draft_args = dict(draft_args, member=name)
    cards.append(_build_card(
        "draft_checkin", draft_args,
        member_registered=member_registered, status=STATUS_PENDING))
    old_hint = f"（{old_id}）" if old_id else ""
    return {
        "phase": "error",
        "code": code,
        "message": (
            f"落库失败：{message}。旧卡已取消{old_hint}，已新出一张待确认卡 {new_id}。"
            "请让用户在新卡上核对/补齐后再点确认；不要对旧卡再 commit，也不要再自己 draft。"
        ),
        "reissued": True,
        "cancelled_card_id": old_id,
        "new_card_id": new_id,
        "cards": cards,
    }


def _cancel_after_timeout_fail(conn, args: dict, exc: BaseException) -> dict[str, Any]:
    """超时自动结算校验/落库失败：只取消旧卡，不再出新卡。

    过期确认只落到 confirmed（写库成功）或 cancelled（写库失败）两种终态。
    """
    code = getattr(exc, "code", type(exc).__name__)
    message = getattr(exc, "message", str(exc))
    old_id = str(args.get("card_id") or "").strip()
    cards: list[dict[str, Any]] = []
    if old_id:
        cancel_args = dict(args, card_id=old_id)
        member_registered, name, _ = _try_resolve_member(cancel_args.get("member", ""))
        if member_registered:
            cancel_args = dict(cancel_args, member=name)
        cards.append(_build_card(
            "cancel_checkin", cancel_args,
            member_registered=member_registered, status=STATUS_CANCELLED))
    return {
        "phase": "error",
        "code": code,
        "message": f"超时结算未落库：{message}。",
        "reissued": False,
        "cancelled_card_id": old_id,
        "cards": cards,
    }


_OPS = {
    "draft_checkin": op_draft_checkin,
    "commit_checkin": op_commit_checkin,
    "cancel_checkin": op_cancel_checkin,
    "find_checkin": op_find_checkin,
    "delete_checkin": op_delete_checkin,
}


def execute(operation: str, args: dict, *, agent_call: bool = False) -> dict[str, Any]:
    # 用校验后的返回值（而不是原始 args）——validate_operation 会把 "2.01" 这类
    # 数字型字段的字符串笔误安全转换成真正的 number，不接住的话下游落库
    # 等环节拿到的还是原始字符串，白做了这层兼容。
    raw_args = _internal_unit(args)
    conn = _db()
    try:
        try:
            coerced_args = _internal_unit(
                validate_operation(operation, raw_args, agent_call=agent_call))
            return _OPS[operation](conn, coerced_args)
        except (ContractError, LedgerError) as exc:
            if operation == "commit_checkin":
                if _is_auto(raw_args):
                    return _cancel_after_timeout_fail(conn, raw_args, exc)
                return _reissue_after_commit_fail(conn, raw_args, exc)
            raise
    finally:
        conn.close()


def main() -> int:
    raw = sys.argv[1] if len(sys.argv) > 1 else "{}"
    operation = ""
    try:
        args = json.loads(raw)
        if not isinstance(args, dict):
            raise LedgerError("INVALID_ARGUMENT", "请求参数必须为对象。")
        operation = args.pop("operation", "")
        result = execute(operation, args)
    except (json.JSONDecodeError, ContractError, LedgerError) as exc:
        code = getattr(exc, "code", "INVALID_JSON")
        message = getattr(exc, "message", str(exc))
        result = {"phase": "error", "code": code, "message": message}
    result.setdefault("operation", operation)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
