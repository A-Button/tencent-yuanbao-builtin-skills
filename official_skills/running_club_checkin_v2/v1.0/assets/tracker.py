#!/usr/bin/env python3
"""
tracker.py - 跑团 tracker CLI 工具

稳定层：SQLite CRUD + 期次/统计编排 + 周报/提醒成文。
规则变更请改 rules.py，本文件不需要修改。

所有命令在 tracker-v2/ 目录下通过 `python3 assets/tracker.py <command>` 调用。
输出为 key=value 纯文本；错误以 error=... 开头并返回非零退出码。
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from urllib.request import pathname2url

import rules

_DIR = os.path.dirname(os.path.abspath(__file__))
# 所有需要持久化的数据都放在 /data/user_persistent_data/，避免部署/升级时丢失
# 未设置 TRACKER_DATA_DIR 时默认用 harness 可写卷；本地开发可 export 覆盖
PERSIST_DIR = os.environ.get("TRACKER_DATA_DIR", "/data/user_persistent_data")
DB_PATH = os.environ.get("TRACKER_DB", os.path.join(PERSIST_DIR, "tracker.db"))
AUDIT_PATH = os.path.join(os.path.dirname(DB_PATH), "audit_log.jsonl")
SCHEMA_PATH = os.path.join(_DIR, "schema.sql")
# 跨进程锁文件：数据库在对象存储卷上不支持文件锁，但锁文件放本地 /tmp，flock 可靠。
# 用 DB_PATH 的哈希命名，保证「同一个库」的所有进程抢同一把锁，不同库互不阻塞。
LOCK_DIR = os.environ.get("TRACKER_LOCK_DIR", "/tmp")
LOCK_PATH = os.path.join(
    LOCK_DIR, "tracker-" + hashlib.md5(DB_PATH.encode("utf-8")).hexdigest() + ".lock")
LOCK_TIMEOUT = float(os.environ.get("TRACKER_LOCK_TIMEOUT", "60"))

_TZ = timezone(timedelta(hours=8))  # 北京时间


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _connect():
    """打开 SQLite 连接。持久化卷常是腾讯云 COS（fuse 对象存储），不支持文件锁，
    SQLite 默认的 fcntl 锁 + 磁盘回滚日志 + fsync 都会触发 disk I/O error，故：
      - URI 加 nolock=1：彻底关掉文件锁（本 skill 单写者，串行执行，安全）
      - journal_mode=MEMORY：回滚日志放内存，不在卷上写临时文件
      - synchronous=OFF：关闭强制刷盘
      - locking_mode=EXCLUSIVE：单连接独占，减少加锁解锁
    """
    uri = "file:" + pathname2url(DB_PATH) + "?nolock=1"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA locking_mode = EXCLUSIVE")
    conn.execute("PRAGMA journal_mode = MEMORY")
    conn.execute("PRAGMA synchronous = OFF")
    return conn


@contextmanager
def _db_lock():
    """跨进程串行化所有 DB 访问：并行 tool call 会被这把锁排成串行，杜绝并发写静默丢数据。

    数据库本身在对象存储卷（fuse）上、不支持文件锁；但锁文件落在本地 /tmp（tmpfs/本地盘），
    flock 在本地文件系统上原子可靠。flock 由内核管理：进程退出或崩溃时自动释放，
    不会留下死锁残留（这是 mkdir / O_EXCL 自旋锁做不到的）。同机的并行进程共享 /tmp，
    抢同一把锁即可互斥。
    """
    try:
        os.makedirs(LOCK_DIR, exist_ok=True)
        fd = os.open(LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o644)
    except OSError as e:
        _die(f"db_lock_open_error path={LOCK_PATH} detail={e} | 锁文件无法创建；"
             f"可用 TRACKER_LOCK_DIR 指向其它本地可写目录", 6)
    try:
        deadline = time.monotonic() + LOCK_TIMEOUT
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() > deadline:
                    _die(f"db_lock_timeout path={LOCK_PATH} timeout={LOCK_TIMEOUT}s "
                         f"| 数据库被另一进程持续占用，超时未获锁，请稍后重试", 6)
                time.sleep(0.05)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


@contextmanager
def _db():
    with _db_lock():
        try:
            os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
            # virtiofs 对 SQLite 的 O_CREAT + truncate 路径支持不完整；先 touch 文件，
            # 让 sqlite3.connect 只打开已存在的空库文件。
            open(DB_PATH, "a").close()
            conn = _connect()
            # 每次连接都跑一遍建表脚本（CREATE TABLE IF NOT EXISTS，幂等）：
            # 即使持久化卷里残留一个空的 / 旧版 tracker.db，也能自动补齐表，不会 no such table。
            with open(SCHEMA_PATH, encoding="utf-8") as f:
                conn.executescript(f.read())
            conn.commit()
            conn.execute("PRAGMA foreign_keys = ON")
        except (OSError, sqlite3.OperationalError) as e:
            _die(f"db_io_error path={DB_PATH} detail={e} | 数据库无法打开/写入。"
                 f"先删除 {DB_PATH}* 后重试；若仍失败，请把 TRACKER_DATA_DIR 指向普通本地可写目录", 6)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def _now() -> str:
    return datetime.now(_TZ).isoformat(timespec="seconds")


def _split_aliases(s):
    """把别名串按中英文分号/逗号拆成去空的列表。"""
    if not s:
        return []
    return [p.strip() for p in re.split(r"[；;，,]", s) if p.strip()]


def _join_aliases(items):
    """规整后的别名列表 -> 存储串（统一用 ； 分隔）。"""
    return "；".join(items)


def _like_escape(s):
    """转义 LIKE 通配符，避免别名里的 % _ 影响匹配。"""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _resolve(conn, query):
    """查找成员：先按 id / name / at_name 精确匹配，再按 alias 模糊（LIKE）兜底，未找到返回 None。"""
    if not query:
        return None
    row = conn.execute("SELECT * FROM member WHERE id = ?", (query,)).fetchone()
    if row:
        return row
    row = conn.execute(
        "SELECT * FROM member WHERE name = ? OR at_name = ? ORDER BY sort_order LIMIT 1",
        (query, query),
    ).fetchone()
    if row:
        return row
    # 别名是多值串、模糊匹配，可能命中多人；取 sort_order 最小者，调用方需用 find_member 复核。
    return conn.execute(
        "SELECT * FROM member WHERE alias <> '' AND alias LIKE ? ESCAPE '\\' "
        "ORDER BY sort_order LIMIT 1",
        (f"%{_like_escape(query)}%",),
    ).fetchone()


def _audit(command, target, **extra):
    os.makedirs(os.path.dirname(AUDIT_PATH), exist_ok=True)
    entry = {"ts": _now(), "command": command, "target": target}
    entry.update({k: v for k, v in extra.items() if v is not None})
    with open(AUDIT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _die(msg, code=2):
    print(f"error={msg}")
    sys.exit(code)


def _ensure_period(conn, num):
    row = conn.execute("SELECT * FROM period WHERE num = ?", (num,)).fetchone()
    if row:
        return row
    start, end = rules.period_bounds(num)
    conn.execute(
        "INSERT INTO period (num, start_date, end_date, status) VALUES (?,?,?,'in_progress')",
        (num, start, end),
    )
    _audit("period start", str(num), reason=f"{start} ~ {end}")
    return conn.execute("SELECT * FROM period WHERE num = ?", (num,)).fetchone()


# ---------------------------------------------------------------------------
# 成员状态：member.status（长期角色态）+ period.member_status（按期参与态 JSON）派生
# ---------------------------------------------------------------------------

_ROLE_STATES = ("active", "suspended", "exited", "wildcard")     # member.status 合法取值
_ROLE_OVERRIDE = ("suspended", "exited", "wildcard")             # 角色态优先于按期参与态
_LEAVE_STATES = ("sick_leave", "recovering")                     # 按期参与态（落 period JSON）


def _status_map(conn, period_num):
    """读某期参与态 JSON -> {member_id: {status, reason, occurred_at}}。期次不存在/空返回 {}。"""
    if period_num is None:
        return {}
    row = conn.execute("SELECT member_status FROM period WHERE num = ?", (period_num,)).fetchone()
    if not row or not row["member_status"]:
        return {}
    try:
        return json.loads(row["member_status"])
    except (ValueError, TypeError):
        return {}


def _effective_status(conn, m, period_num):
    """某成员第 period_num 期的有效状态：角色态(非active)优先，否则查该期 JSON，否则 active。"""
    role = m["status"]
    if role in _ROLE_OVERRIDE:
        return role
    entry = _status_map(conn, period_num).get(m["id"])
    if entry:
        return entry.get("status", "active")
    return "active"


def _set_status(conn, period_num, member_id, status, reason, occurred_at):
    """把某成员某期的参与态写进该期 JSON（读-改-写）。"""
    smap = _status_map(conn, period_num)
    smap[member_id] = {"status": status, "reason": reason or "", "occurred_at": occurred_at}
    conn.execute("UPDATE period SET member_status = ? WHERE num = ?",
                 (json.dumps(smap, ensure_ascii=False), period_num))


def _clear_status(conn, period_num, member_id):
    """销假：从某期 JSON 删除该成员，返回是否真的删了。"""
    smap = _status_map(conn, period_num)
    if member_id in smap:
        del smap[member_id]
        conn.execute("UPDATE period SET member_status = ? WHERE num = ?",
                     (json.dumps(smap, ensure_ascii=False), period_num))
        return True
    return False


def _current_period(conn, asof=None):
    """当前期：asof 传入则按其归属期；否则取最近已封板期 +1（免疫提前建出的未来期）。"""
    if asof:
        return rules.period_for_date(asof)
    mf = conn.execute("SELECT MAX(num) FROM period WHERE status = 'finalized'").fetchone()[0]
    if mf is not None:
        return mf + 1
    return conn.execute("SELECT MAX(num) FROM period").fetchone()[0]


# ---------------------------------------------------------------------------
# 成员
# ---------------------------------------------------------------------------

def _member_counts(conn, m, upto_period=None):
    """现算成员连续计数。sun_count 取存储列；三个 streak 由"每期有效状态"推出。

    upto_period：把"最近已封板期"上限到该期次（出周报传 N-1，表示进入第 N 周前的状态）；
    None = 用当前最新已封板期（成员当前实时状况）。
    回溯下限取建档期次（成员不为入群前的空白期背锅）；遇请假期会打断未达标连击。
    """
    counts = {"sun_count": m["sun_count"], "fail_count": 0,
              "sick_leave_week": 0, "recovering_week": 0}
    if m["status"] in _ROLE_OVERRIDE:
        return counts  # suspended / exited / wildcard：不计罚
    latest_fin = conn.execute(
        "SELECT MAX(num) FROM period WHERE status = 'finalized'").fetchone()[0]
    if latest_fin is None:
        return counts
    if upto_period is not None:
        latest_fin = min(latest_fin, upto_period)
    create_p = rules.period_for_date(m["created_at"][:10])
    # 最近已封板期的有效状态决定数哪种连击（与旧版按 member.status 分支同构）
    front = _effective_status(conn, m, latest_fin)
    if front in _LEAVE_STATES:
        statuses = []
        n = latest_fin
        while n >= create_p:
            st = _effective_status(conn, m, n)
            statuses.append(st)
            if st != front:
                break
            n -= 1
        key = "sick_leave_week" if front == "sick_leave" else "recovering_week"
        counts[key] = rules.status_streak(statuses, front)
    else:  # active：从最近已封板期往回数连续未达标，遇达标或请假即停
        quals = []
        n = latest_fin
        while n >= create_p and _effective_status(conn, m, n) == "active":
            quals.append(_period_total(conn, m["id"], n)[2])
            n -= 1
        counts["fail_count"] = rules.fail_streak(quals)
    return counts


def _run_ending(conn, m, end_period, target):
    """以 end_period 结尾、连续处于 target 有效状态的期数（含 end_period）。"""
    if end_period is None:
        return 0
    create_p = rules.period_for_date(m["created_at"][:10])
    n, run = end_period, 0
    while n >= create_p and _effective_status(conn, m, n) == target:
        run += 1
        n -= 1
    return run


def _status_since(conn, m, cur_period, eff, run):
    """当前连续请假段的首期周一（仅请假/恢复态有意义），否则空串。"""
    if eff not in _LEAVE_STATES or cur_period is None or run <= 0:
        return ""
    return rules.period_bounds(cur_period - run + 1)[0]


def _print_member(conn, m, asof=None):
    cur_period = _current_period(conn, asof)
    eff = _effective_status(conn, m, cur_period)
    c = _member_counts(conn, m)
    # sick / recover = 以"当前期"结尾的连续请假/恢复期数（含当周）；fail 在请假当周不计
    sick = recover = 0
    fail = c['fail_count']
    if eff == 'sick_leave':
        sick = _run_ending(conn, m, cur_period, 'sick_leave')
        fail = 0
    elif eff == 'recovering':
        recover = _run_ending(conn, m, cur_period, 'recovering')
        fail = 0
    since = _status_since(conn, m, cur_period, eff, sick or recover)
    print(f"id={m['id']} name={m['name']} at_name={m['at_name']} alias={m['alias'] or ''} "
          f"sort={m['sort_order']} "
          f"status={eff} age_exempt={m['age_exempt']} walk_valid={m['walk_valid']} "
          f"since={since} sun={c['sun_count']} fail={fail} "
          f"sick={sick} recover={recover} desc={m['description']}")


def cmd_add_member(args):
    if args.status not in _ROLE_STATES:
        _die(f"invalid_status status={args.status} | member.status 仅限角色态 "
             f"{_ROLE_STATES}；请假/恢复请用 add_status", 2)
    with _db() as conn:
        try:
            alias = _join_aliases(_split_aliases(args.alias)) if args.alias else ""
            conn.execute(
                "INSERT INTO member (id, name, at_name, alias, sort_order, status, age_exempt, "
                "walk_valid, description, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (args.id, args.name, args.at_name or "", alias, args.sort, args.status,
                 int(args.age_exempt), int(args.walk_valid), args.description or "", _now()))
        except sqlite3.IntegrityError:
            _die(f"member_exists id={args.id}", 4)
        _audit("member add", args.id)
        _print_member(conn, conn.execute("SELECT * FROM member WHERE id = ?", (args.id,)).fetchone())


def cmd_update_member(args):
    with _db() as conn:
        m = _resolve(conn, args.query)
        if not m:
            _die(f"member_not_found query={args.query}", 3)
        fields = {
            "name": args.name, "at_name": args.at_name, "sort_order": args.sort,
            "status": args.status, "description": args.description,
        }
        # --alias 为整体覆盖（传空串即清空）；追加请用 add_alias
        if args.alias is not None:
            fields["alias"] = _join_aliases(_split_aliases(args.alias))
        if args.age_exempt is not None:
            fields["age_exempt"] = int(args.age_exempt)
        if args.walk_valid is not None:
            fields["walk_valid"] = int(args.walk_valid)
        if args.status is not None and args.status not in _ROLE_STATES:
            _die(f"invalid_status status={args.status} | member.status 仅限角色态 "
                 f"{_ROLE_STATES}；请假/恢复请用 add_status", 2)
        sets = {k: v for k, v in fields.items() if v is not None}
        if not sets:
            _die("nothing_to_update", 2)
        clause = ", ".join(f"{k} = ?" for k in sets)
        conn.execute(f"UPDATE member SET {clause} WHERE id = ?", (*sets.values(), m["id"]))
        _audit("member update", m["id"], reason=", ".join(f"{k}={v}" for k, v in sets.items()))
        _print_member(conn, conn.execute("SELECT * FROM member WHERE id = ?", (m["id"],)).fetchone())


def cmd_add_alias(args):
    """给已注册成员追加别名（去重，不覆盖已有别名）。"""
    with _db() as conn:
        m = _resolve(conn, args.query)
        if not m:
            _die(f"member_not_found query={args.query}", 3)
        existing = _split_aliases(m["alias"])
        added = []
        for a in _split_aliases(args.alias):
            if a not in existing:
                existing.append(a)
                added.append(a)
        if not added:
            _die(f"no_new_alias query={args.query} | 别名已存在或为空，未改动", 2)
        conn.execute("UPDATE member SET alias = ? WHERE id = ?",
                     (_join_aliases(existing), m["id"]))
        _audit("member add_alias", m["id"], reason=f"+{_join_aliases(added)}")
        _print_member(conn, conn.execute("SELECT * FROM member WHERE id = ?", (m["id"],)).fetchone())


def cmd_find_member(args):
    with _db() as conn:
        m = _resolve(conn, args.query)
        if m:
            _print_member(conn, m, args.asof)
        else:
            _die(f"member_not_found query={args.query}", 3)


def cmd_list_members(args):
    with _db() as conn:
        rows = conn.execute("SELECT * FROM member ORDER BY sort_order, id").fetchall()
        for m in rows:
            _print_member(conn, m, args.asof)
        if not rows:
            print("(empty)")


# ---------------------------------------------------------------------------
# 打卡
# ---------------------------------------------------------------------------

def _img_id(raw):
    """从 raw_summary / --raw 里取图片 id（约定格式 `img=<id>; <原始描述>`）。

    取不到返回 None——老数据、口述数字录入的记录都没有这一段。
    """
    m = re.search(r"img=([0-9a-zA-Z]{8,})", raw or "")
    return m.group(1) if m else None


def _img_key(value):
    """把外部给的图片 id 归一成入库口径。

    附件 url 里的 resourceId 实际长 `<32位十六进制>_55` 这样，`_NN` 是清晰度变体，
    同一张图恒定。库里一律只存前 32 位，所以查重前必须先削掉后缀，
    否则拿 `<id>_55` 去 LIKE 只存了前 32 位的记录会全部漏配。
    这里同时接受裸 id、`img=<id>`、以及整条 url。
    """
    text = (value or "").strip()
    for prefix in ("img=", "resourceId="):
        pos = text.find(prefix)
        if pos >= 0:
            text = text[pos + len(prefix):]
    m = re.match(r"[0-9a-zA-Z]{8,}", text)
    return m.group(0) if m else ""


def cmd_find_by_img(args):
    """按图片 id 查已有打卡，录入前查重专用。

    以前要模型自己手写 `raw_summary LIKE '%img=..%'` 的 SQL，实测很容易
    往 SELECT 里多写一个不存在的 `activity` 列（真名是 `activity_type`），
    整条查询报 sql_error 后无输出，查重就静默失效了。
    """
    keys = []
    for raw in args.img:
        key = _img_key(raw)
        if not key:
            _die(f"bad_img_id={raw}", 5)
        if key not in keys:
            keys.append(key)
    with _db() as conn:
        clause = " OR ".join(["c.raw_summary LIKE ?"] * len(keys))
        rows = conn.execute(
            "SELECT c.*, m.name AS member_name FROM checkin c "
            "JOIN member m ON c.member_id = m.id "
            f"WHERE c.deleted_at IS NULL AND ({clause}) "
            "ORDER BY c.occurred_at, c.event_id",
            [f"%img={k}%" for k in keys]).fetchall()
    hits = {k: 0 for k in keys}
    for c in rows:
        img = _img_id(c["raw_summary"])
        if img in hits:
            hits[img] += 1
        print(f"event_id={c['event_id']} member={c['member_name']} "
              f"occurred_at={c['occurred_at']} period={c['period']} "
              f"activity={c['activity_type']} distance_km={c['distance_km']} "
              f"valid={c['valid']} img={img}")
    # 逐个 id 给结论，免得多图查询时要靠数行数反推哪张图是新的
    for k in keys:
        print(f"img={k} hits={hits[k]}")


def _derive_checkin(activity_type, distance_raw, unit, duration, member):
    """用 rules.py 算出 (distance_km, valid, note)。"""
    distance_km = rules.effective_km(activity_type, distance_raw, unit)
    valid, note = rules.judge_validity(
        activity_type, distance_km, duration,
        bool(member["age_exempt"]), bool(member["walk_valid"]))
    return distance_km, valid, note


def _period_total(conn, member_id, period):
    """某成员某期的有效累计公里 + 是否达标。"""
    row = conn.execute(
        "SELECT COALESCE(SUM(distance_km),0) AS km, COUNT(*) AS n FROM checkin "
        "WHERE member_id = ? AND period = ? AND valid = 1 AND deleted_at IS NULL",
        (member_id, period)).fetchone()
    total = row["km"] or 0.0
    return total, row["n"], rules.is_qualified(total)


def _insert_checkin(conn, args, member, period, audit_command,
                    admin_reason=None, success_prefix=""):
    _ensure_period(conn, period)

    distance_km, valid, note = _derive_checkin(
        args.activity_type, args.distance_raw, args.unit, args.duration, member)

    # 去重：同一人 + 同一天 + 同里程（折算后 distance_km）视为重复，拒绝写入。
    # 例外：两条记录明确来自不同图片时放行——同日同里程的两次真实运动是合法的，
    # 光靠人/日/里程会把它误判成重复。只有双方都带图片 id 且不同才放行，
    # 缺 id 的（老数据、口述录入）一律沿用旧口径，保持向后兼容。
    dkm = round(distance_km, 3)
    img = _img_id(args.raw)
    for row in conn.execute(
            "SELECT event_id, raw_summary FROM checkin WHERE member_id = ? AND occurred_at = ? "
            "AND deleted_at IS NULL AND ABS(distance_km - ?) < 0.001",
            (member["id"], args.occurred_at, dkm)).fetchall():
        other = _img_id(row["raw_summary"])
        if img and other and img != other:
            continue
        _die(f"duplicate_checkin member={member['name']} occurred_at={args.occurred_at} "
             f"distance_km={dkm} existing={row['event_id']} "
             f"| 同一天同一人同里程视为重复，不允许重复打卡"
             f"（两条明确来自不同图片才放行）", 4)

    # 同一张图在本期已录过：可能是重发，也可能是周汇总图的第 2..N 条明细，
    # 脚本判不了，只提示不拦截，由调用方结合图里实际有几次运动决定。
    same_img_in_period = 0
    if img:
        same_img_in_period = conn.execute(
            "SELECT COUNT(*) FROM checkin WHERE member_id = ? AND period = ? "
            "AND deleted_at IS NULL AND raw_summary LIKE ?",
            (member["id"], period, f"%img={img}%")).fetchone()[0]

    overridden = 0
    if args.override_valid is not None:
        valid = bool(args.override_valid)
        overridden = 1
        note = (note + " | 管理员覆盖 valid").strip(" |")

    event_id = args.event_id or _next_event_id(conn, member["id"], args.occurred_at)

    try:
        conn.execute(
            "INSERT INTO checkin (event_id, member_id, occurred_at, period, activity_type, "
            "distance_raw, unit, distance_km, duration_seconds, valid, valid_overridden, "
            "note, device, raw_summary, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (event_id, member["id"], args.occurred_at, period, args.activity_type,
             args.distance_raw, args.unit, round(distance_km, 3), args.duration,
             int(valid), overridden, note, args.device or "", args.raw or "", _now()))
    except sqlite3.IntegrityError:
        _die(f"checkin_exists event_id={event_id}", 4)

    audit_reason = f"{args.activity_type} {round(distance_km,2)}km valid={int(valid)}"
    if admin_reason:
        audit_reason = f"{admin_reason}: {audit_reason}"
    _audit(audit_command, event_id, reason=audit_reason)

    total, _, qualified = _period_total(conn, member["id"], period)
    shortage = max(rules.QUALIFY_KM - total, 0)
    print(f"{success_prefix}event_id={event_id} member={member['name']} "
          f"occurred_at={args.occurred_at} period={period} activity={args.activity_type} "
          f"distance_km={round(distance_km,2)} valid={int(valid)} note={note} "
          f"period_total={round(total,2)} qualified={int(qualified)} "
          f"shortage_km={round(shortage,2)}")
    if same_img_in_period:
        print(f"warn=same_image_in_period img={img} existing={same_img_in_period} "
              f"| 这张图在本期已挂了 {same_img_in_period} 条记录，"
              f"若不是周汇总图的多条明细，请核对是否重发")


def cmd_add_checkin(args):
    with _db() as conn:
        m = _resolve(conn, args.member)
        if not m:
            _die(f"member_not_found query={args.member}", 3)
        if args.distance_raw <= 0:
            _die("distance_raw must be > 0", 2)

        period = rules.period_for_date(args.occurred_at)
        # 日期合法性（不读系统时钟，today 由模型从上下文传入）：未来日期 / 当前期以前一律拒绝。
        # 这条不依赖期次封板状态，对从无打卡的历史空白期同样拦得住。
        reject, why = rules.reject_checkin_date(args.occurred_at, args.today)
        if reject:
            _die(f"checkin_date_rejected occurred_at={args.occurred_at} today={args.today} "
                 f"period={period} | {why}（新增历史补卡用 backfill_checkin；"
                 f"更正已有记录用 correct/delete_checkin）", 4)
        # 兜底：当前期若已被提前封板，仍不允许补录（正常不会触发，规则 1/2 已覆盖历史期）。
        pr = conn.execute("SELECT status FROM period WHERE num = ?", (period,)).fetchone()
        if pr and pr["status"] == "finalized":
            _die(f"period_finalized num={period} occurred_at={args.occurred_at} "
                 f"| 已截止周期不允许日常录入（新增补卡用 backfill_checkin；"
                 f"更正已有记录用 correct/delete_checkin）", 4)
        _insert_checkin(conn, args, m, period, "checkin add")

        # 收到本期打卡 ⟹ 之前未封板的期次自动按序补稿封板（不靠人记得调 finalize）。
        for r in _catch_up_finalize(conn, period):
            print(f"auto_finalized=period={r['num']} champion={r['champion'] or ''} "
                  f"champion_distance={r['champion_distance']}")
            for a in r["alerts"]:
                print(f"alert={a}")


def cmd_backfill_checkin(args):
    with _db() as conn:
        m = _resolve(conn, args.member)
        if not m:
            _die(f"member_not_found query={args.member}", 3)
        if args.distance_raw <= 0:
            _die("distance_raw must be > 0", 2)

        period = rules.period_for_date(args.occurred_at)
        if args.occurred_at > args.today:
            _die(f"checkin_date_rejected occurred_at={args.occurred_at} today={args.today} "
                 f"period={period} | occurred_at={args.occurred_at} 晚于今天 {args.today}，"
                 f"截图不可能来自未来", 4)

        # 管理员补卡：允许写入历史/已封板期，但不触发自动封板，也不重写 period 定稿字段。
        _insert_checkin(conn, args, m, period, "checkin backfill",
                        admin_reason=args.reason, success_prefix="backfilled=true ")


def _next_event_id(conn, member_id, occurred_at):
    n = conn.execute(
        "SELECT COUNT(*) FROM checkin WHERE member_id = ? AND occurred_at = ?",
        (member_id, occurred_at)).fetchone()[0]
    return f"{member_id}_{occurred_at}_{n + 1:02d}"


def cmd_list_checkins(args):
    with _db() as conn:
        sql = ("SELECT c.*, m.name AS member_name FROM checkin c "
               "JOIN member m ON c.member_id = m.id WHERE c.deleted_at IS NULL")
        params = []
        if args.member:
            m = _resolve(conn, args.member)
            if not m:
                _die(f"member_not_found query={args.member}", 3)
            sql += " AND c.member_id = ?"
            params.append(m["id"])
        if args.period is not None:
            sql += " AND c.period = ?"
            params.append(args.period)
        if args.date:
            sql += " AND c.occurred_at = ?"
            params.append(args.date)
        rows = conn.execute(sql + " ORDER BY c.occurred_at, c.event_id", params).fetchall()
    for c in rows:
        print(f"event_id={c['event_id']} member={c['member_name']} occurred_at={c['occurred_at']} "
              f"period={c['period']} activity={c['activity_type']} distance_km={c['distance_km']} "
              f"duration={c['duration_seconds'] or ''} valid={c['valid']} note={c['note']}")
    if not rows:
        print("(empty)")


def cmd_delete_checkin(args):
    with _db() as conn:
        c = conn.execute("SELECT 1 FROM checkin WHERE event_id = ? AND deleted_at IS NULL",
                         (args.event_id,)).fetchone()
        if not c:
            _die(f"checkin_not_found event_id={args.event_id}", 3)
        conn.execute("UPDATE checkin SET deleted_at = ?, deleted_reason = ? WHERE event_id = ?",
                     (_now(), args.reason, args.event_id))
        _audit("checkin delete", args.event_id, reason=args.reason)
        print(f"deleted=true event_id={args.event_id}")


# ---------------------------------------------------------------------------
# 通用校正（带 reason + 审计）
# ---------------------------------------------------------------------------

_CORRECTABLE = {
    "member": "id",
    "checkin": "event_id",
    "period": "num",
}


def cmd_correct(args):
    pk_col = _CORRECTABLE.get(args.table)
    if not pk_col:
        _die(f"table_not_correctable table={args.table}", 2)
    with _db() as conn:
        before = conn.execute(
            f"SELECT {args.field} FROM {args.table} WHERE {pk_col} = ?", (args.pk,)).fetchone()
        if before is None:
            _die(f"row_not_found {pk_col}={args.pk}", 3)
        value = _coerce(args.value)
        conn.execute(f"UPDATE {args.table} SET {args.field} = ? WHERE {pk_col} = ?",
                     (value, args.pk))
        # 直接改 checkin.valid → 标记为覆盖，recompute 不再回填
        if args.table == "checkin" and args.field == "valid":
            conn.execute("UPDATE checkin SET valid_overridden = 1 WHERE event_id = ?", (args.pk,))
        # 改了 checkin 的原始字段 → 立即重算该行派生列
        if args.table == "checkin" and args.field in (
                "distance_raw", "unit", "activity_type", "duration_seconds", "occurred_at"):
            _rederive_one(conn, args.pk)
        _audit(f"{args.table} correct", str(args.pk), field=args.field,
               before=before[0], after=value, reason=args.reason)
        print(f"corrected={args.table} {pk_col}={args.pk} {args.field}={value}")


def _coerce(v):
    for cast in (int, float):
        try:
            return cast(v)
        except ValueError:
            pass
    return v


def _rederive_one(conn, event_id):
    c = conn.execute("SELECT * FROM checkin WHERE event_id = ?", (event_id,)).fetchone()
    if not c:
        return
    m = conn.execute("SELECT * FROM member WHERE id = ?", (c["member_id"],)).fetchone()
    period = rules.period_for_date(c["occurred_at"])
    _ensure_period(conn, period)
    distance_km, valid, note = _derive_checkin(
        c["activity_type"], c["distance_raw"], c["unit"], c["duration_seconds"], m)
    if c["valid_overridden"]:
        valid = c["valid"]
    conn.execute(
        "UPDATE checkin SET period = ?, distance_km = ?, valid = ?, note = ? WHERE event_id = ?",
        (period, round(distance_km, 3), int(valid), note, event_id))


# ---------------------------------------------------------------------------
# 状态变更（直接更新 member.status 单一真相源 + 落审计）
# ---------------------------------------------------------------------------

def _reject_if_finalized(conn, period):
    """目标期已封板则拒绝（请假/销假不得改已截止周期，走 correct）。"""
    pr = conn.execute("SELECT status FROM period WHERE num = ?", (period,)).fetchone()
    if pr and pr["status"] == "finalized":
        _die(f"period_finalized num={period} | 已截止周期不允许改状态（如需更正用 correct）", 4)


def cmd_add_status(args):
    with _db() as conn:
        m = _resolve(conn, args.member)
        if not m:
            _die(f"member_not_found query={args.member}", 3)
        target = args.to_status
        period = rules.period_for_date(args.occurred_at)

        if target in _LEAVE_STATES:
            # 请假/恢复：写 occurred_at 所属期的 JSON（当前期或未来期；未来期按需建出）。
            # 不读系统时钟、不拒未来——请假是前瞻安排；仅拒已封板期。
            _reject_if_finalized(conn, period)
            _ensure_period(conn, period)
            _set_status(conn, period, m["id"], target, args.reason or "", args.occurred_at)
            _audit("member status", m["id"],
                   reason=f"-> {target} @ {args.occurred_at} (period={period}): {args.reason or ''}")
            print(f"member={m['name']} status={target} period={period} "
                  f"occurred_at={args.occurred_at}")
        elif target == "active":
            # 销假/提前恢复：删该期 JSON 项；若角色态非 active 一并归位。
            _reject_if_finalized(conn, period)
            cleared = _clear_status(conn, period, m["id"])
            if m["status"] != "active":
                conn.execute("UPDATE member SET status = 'active' WHERE id = ?", (m["id"],))
            _audit("member status", m["id"],
                   reason=f"-> active @ {args.occurred_at} (period={period}, cleared={int(cleared)})"
                          f": {args.reason or ''}")
            print(f"member={m['name']} status=active period={period} "
                  f"occurred_at={args.occurred_at} cleared={int(cleared)}")
        else:  # suspended：长期角色态，直接更新 member.status
            conn.execute("UPDATE member SET status = ? WHERE id = ?", (target, m["id"]))
            _audit("member status", m["id"],
                   reason=f"{m['status']} -> {target} @ {args.occurred_at}: {args.reason or ''}")
            print(f"member={m['name']} from={m['status']} to={target} "
                  f"occurred_at={args.occurred_at}")


# ---------------------------------------------------------------------------
# 期次
# ---------------------------------------------------------------------------

def _print_period(p):
    print(f"num={p['num']} start={p['start_date']} end={p['end_date']} status={p['status']} "
          f"champion={p['champion_id'] or ''} champion_distance={p['champion_distance'] or ''}")


def cmd_period_current(args):
    # 日期由模型传入（从对话上下文取今天），不依赖容器系统时钟。
    num = rules.period_for_date(args.date)
    with _db() as conn:
        # 自动切分周期：当前期之前所有未封板的期次按序补稿封板（与 add_checkin 同口径，
        # 不靠人记得调 finalize；空白周也照常封板）。
        for r in _catch_up_finalize(conn, num):
            print(f"auto_finalized=period={r['num']} champion={r['champion'] or ''} "
                  f"champion_distance={r['champion_distance']}")
            for a in r["alerts"]:
                print(f"alert={a}")
        _print_period(_ensure_period(conn, num))


def _finalize_one(conn, num, champion_id=None):
    """定稿单个期次（幂等核心）。champion_id 为空则自动取该期距离第一名。

    返回 dict（num/champion/champion_id/champion_distance/alerts）；
    已定稿则返回 None（不重复累加计数，重跑安全）。
    """
    p = _ensure_period(conn, num)
    if p["status"] == "finalized":
        return None

    ranked = _ranked_totals(conn, num)
    if champion_id:
        champ = _resolve(conn, champion_id)
        if not champ:
            _die(f"champion_not_found query={champion_id}", 3)
        champion_id, champ_name = champ["id"], champ["name"]
        champ_km, _, _ = _period_total(conn, champion_id, num)
    elif ranked:
        champion_id, champ_name, champ_km = ranked[0]["id"], ranked[0]["name"], ranked[0]["total"]
    else:
        champion_id, champ_name, champ_km = None, "", 0.0

    conn.execute(
        "UPDATE period SET status='finalized', champion_id=?, champion_distance=?, "
        "finalized_at=? WHERE num=?",
        (champion_id, round(champ_km, 2) if champion_id else None, _now(), num))
    if champion_id:
        conn.execute("UPDATE member SET sun_count = sun_count + 1 WHERE id = ?", (champion_id,))

    # 计数不落库：本期已 finalized，现算各成员连续计数并给处罚提示
    alerts = []
    for m in conn.execute("SELECT * FROM member").fetchall():
        alert = rules.discipline_alert(_member_counts(conn, m))
        if alert:
            alerts.append(f"{m['name']}: {alert}")

    _audit("period finalize", str(num),
           reason=f"champion={champ_name or '-'} ({round(champ_km,2)}km)")
    return {"num": num, "champion": champ_name, "champion_id": champion_id,
            "champion_distance": round(champ_km, 2), "alerts": alerts}


def _catch_up_finalize(conn, before_period):
    """把 before_period 之前所有未封板的期次按序自动封板（冠军自动取第一名）。

    起点 = 上次已封板期 +1；若从未封板，则从最早有打卡的期次开始。
    语义：收到第 P 期打卡 ⟹ P 之前的期次都已结束（grace=0，边界即封板）。
    确定性、不依赖系统时钟；空白周也照常封板（成员 fail_count+1）。
    """
    max_fin = conn.execute("SELECT MAX(num) FROM period WHERE status = 'finalized'").fetchone()[0]
    if max_fin is not None:
        start = max_fin + 1
    else:
        min_ck = conn.execute(
            "SELECT MIN(period) FROM checkin WHERE deleted_at IS NULL").fetchone()[0]
        if min_ck is None:
            return []
        start = min_ck
    results = []
    for n in range(start, before_period):
        r = _finalize_one(conn, n)
        if r:
            results.append(r)
    return results


def cmd_period_finalize(args):
    with _db() as conn:
        r = _finalize_one(conn, args.num, champion_id=args.champion)
        if r is None:
            p = conn.execute("SELECT * FROM period WHERE num = ?", (args.num,)).fetchone()
            print(f"skipped=already_finalized num={args.num} "
                  f"champion={p['champion_id'] or ''} "
                  f"champion_distance={p['champion_distance'] or ''}")
            return
        print(f"finalized=true num={r['num']} champion={r['champion'] or ''} "
              f"champion_distance={r['champion_distance']}")
        for a in r["alerts"]:
            print(f"alert={a}")


# ---------------------------------------------------------------------------
# 统计 calc
# ---------------------------------------------------------------------------

def cmd_calc(args):
    with _db() as conn:
        if args.member:
            m = _resolve(conn, args.member)
            if not m:
                _die(f"member_not_found query={args.member}", 3)
            _calc_member(conn, m, args)
        else:
            _calc_ranking(conn, args)


def _calc_member(conn, m, args):
    sql = ("SELECT * FROM checkin WHERE member_id = ? AND valid = 1 AND deleted_at IS NULL")
    params = [m["id"]]
    if args.period is not None:
        sql += " AND period = ?"
        params.append(args.period)
    if getattr(args, "from"):
        sql += " AND occurred_at >= ?"
        params.append(getattr(args, "from"))
    if args.to:
        sql += " AND occurred_at <= ?"
        params.append(args.to)
    rows = conn.execute(sql + " ORDER BY occurred_at", params).fetchall()
    print("[detail]")
    total = 0.0
    for c in rows:
        pace = rules.pace_sec_per_km(c["distance_km"], c["duration_seconds"])
        print(f"event_id={c['event_id']} date={c['occurred_at']} activity={c['activity_type']} "
              f"distance_km={c['distance_km']} pace={_fmt_pace(pace)}")
        total += c["distance_km"]
    qualified = rules.is_qualified(total)
    shortage = max(rules.QUALIFY_KM - total, 0)
    print("[total]")
    print(f"member={m['name']} total_km={round(total,2)} count={len(rows)} "
          f"qualified={int(qualified)} shortage_km={round(shortage,2)}")


def _calc_ranking(conn, args):
    if args.period is None:
        _die("ranking requires --period N", 2)
    print("[ranking]")
    rank = 1
    for row in _ranked_totals(conn, args.period):
        print(f"rank={rank} member={row['name']} total_km={round(row['total'],2)} "
              f"count={row['count']} qualified={int(row['qualified'])}")
        rank += 1


def _ranked_totals(conn, period):
    """返回该期所有有打卡成员的累计，按公里降序。"""
    rows = conn.execute(
        "SELECT m.id, m.name, COALESCE(SUM(c.distance_km),0) AS total, COUNT(c.event_id) AS count "
        "FROM member m JOIN checkin c ON c.member_id = m.id "
        "WHERE c.period = ? AND c.valid = 1 AND c.deleted_at IS NULL "
        "GROUP BY m.id, m.name ORDER BY total DESC", (period,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["qualified"] = rules.is_qualified(d["total"])
        out.append(d)
    return out


def _fmt_pace(pace):
    if pace is None:
        return ""
    sec = int(round(pace))
    return f"{sec // 60}'{sec % 60:02d}\"/km"


# ---------------------------------------------------------------------------
# 周报 / 提醒成文（高频群消息，确定性生成）
# ---------------------------------------------------------------------------

def _km_trim(value):
    s = f"{float(value):.2f}".rstrip("0").rstrip(".")
    return s or "0"


def _keycap_num(value):
    return "".join(f"{char}\u20e3" if char.isdigit() else char for char in str(value))


def _cn_num(value):
    n = int(value)
    digits = "零一二三四五六七八九"
    if n < 0:
        return "负" + _cn_num(-n)
    if n < 10:
        return digits[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        prefix = "" if tens == 1 else digits[tens]
        return prefix + "十" + (digits[ones] if ones else "")
    if n < 1000:
        hundreds, remainder = divmod(n, 100)
        suffix = ("零" if 0 < remainder < 10 else "") + (_cn_num(remainder) if remainder else "")
        return digits[hundreds] + "百" + suffix
    if n < 10000:
        thousands, remainder = divmod(n, 1000)
        suffix = ("零" if 0 < remainder < 100 else "") + (_cn_num(remainder) if remainder else "")
        return digits[thousands] + "千" + suffix
    return str(n)


def _disp_w(text):
    """估算微信等宽展示宽度：全角/宽字符计 2，其余计 1。"""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def _center_line(text, width=None):
    """相对标题「不一班乐跑团打卡成绩」做半角空格居中。"""
    if width is None:
        width = _disp_w("不一班乐跑团打卡成绩")
    pad = max(0, (width - _disp_w(text)) // 2)
    return (" " * pad) + text


def _name_pad(name):
    return name[0] + "    " + name[1] if len(name) == 2 else name


def _remark_cont(text):
    """备注续行：与首行「备注：」后的符号列对齐。"""
    return (" " * _disp_w("备注：")) + text


def _score_label():
    """「成绩：」与「本周距离冠军：」等宽对齐（空格插在成/绩之间）。"""
    gap = _disp_w("本周距离冠军：") - _disp_w("成") - _disp_w("绩：")
    return "成" + (" " * max(0, gap)) + "绩："


def _rocket_record(conn):
    """取 period 表中 champion_distance 最大的一期，作为 🚀 保持者记录。"""
    row = conn.execute(
        "SELECT p.num AS period, p.champion_id AS id, m.name AS name, "
        "p.champion_distance AS distance "
        "FROM period p JOIN member m ON m.id = p.champion_id "
        "WHERE p.champion_id IS NOT NULL AND p.champion_distance IS NOT NULL "
        "ORDER BY p.champion_distance DESC, p.num ASC "
        "LIMIT 1"
    ).fetchone()
    if not row:
        return {"id": "", "name": "", "distance": 0.0, "period": None}
    return {
        "id": row["id"],
        "name": row["name"],
        "distance": float(row["distance"]),
        "period": row["period"],
    }


def cmd_report(args):
    with _db() as conn:
        p = conn.execute("SELECT * FROM period WHERE num = ?", (args.num,)).fetchone()
        if not p:
            _die(f"period_not_found num={args.num}", 3)
        rocket = _rocket_record(conn)
        members = conn.execute(
            "SELECT * FROM member WHERE status NOT IN ('exited','wildcard','suspended') "
            "ORDER BY sort_order, id").fetchall()
        ranked = _ranked_totals(conn, args.num)
        champion = ranked[0] if ranked else None

        lines = ["不一班乐跑团打卡成绩",
                 _center_line(f"总第{_keycap_num(p['num'])}期"),
                 _center_line(f"{p['start_date'][:4]}年"),
                 _center_line(f"{_md(p['start_date'])} 至 {_md(p['end_date'])}"),
                 "  🐎🐎🐎🐎🐎🐎🐎🐎🐎",
                 "  ☀️☀️☀️☀️☀️☀️☀️☀️☀️"]
        report_counts = {}
        for m in members:
            total, _, qualified = _period_total(conn, m["id"], args.num)
            # 计数现算到第 N-1 期（进入第 N 周前的状态），模板再 +1 表示当前在跑的第 N 周
            counts = _member_counts(conn, m, upto_period=args.num - 1)
            eff = _effective_status(conn, m, args.num)
            # 成员行只用库里已落定的 sun_count，不带未封板预览 +1（仅改行内展示）
            lines.append(_report_line(m, eff, total, qualified, rocket, counts))
            # 未定稿：第一名预览太阳 +1；已定稿：直接用库里的 sun_count（finalize 已加过）
            # 以下与原脚本一致，仅供页脚「本周距离冠军」使用
            if p["status"] != "finalized" and champion and m["id"] == champion["id"]:
                counts = dict(counts)
                counts["sun_count"] = m["sun_count"] + 1
            report_counts[m["id"]] = counts
        lines += [
            "备注：☀️代表周冠军次数",
            _remark_cont("💎代表周冠军过100周"),
            _remark_cont(f"🚀代表本群周内最远距离【{_km_trim(rocket.get('distance', 0))}】公里"),
            f"保持者：{rocket.get('name', '')}",
            "乐跑大满贯次数：🏃x33",
        ]
        if champion:
            champion_suns = report_counts.get(champion["id"], {}).get("sun_count", 0)
            lines += [f"本周距离冠军：{champion['name']}x{champion_suns}🏆☀️",
                      f"{_score_label()}{_km_trim(champion['total'])}公里"]
        lines += ["     🐎🐎🐎🐎🐎🐎🐎🐎🐎",
                  "     🌹🌹🌹🌹🌹🌹🌹🌹🌹"]
        out = "\n".join(lines)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out + "\n")
        print(f"wrote={args.out}")
    else:
        print(out)


def _honor_suffix(counts):
    """冠军荣誉后缀：☀️x次数（+💎满100周）。达标 / 病假 / 恢复 / 未达标行一律共用。
    传入的 sun_count 应为库内已落定值（调用方在未封板预览 +1 之前取），不把当期未封板冠军算进来。"""
    n = counts.get("sun_count", 0)
    if not n:
        return ""
    return f"☀️x{n}" + ("💎" if n >= 100 else "")


def _report_line(m, eff, total, qualified, rocket, counts):
    name = _name_pad(m["name"])
    honor = _honor_suffix(counts)
    if eff == "sick_leave":
        # 病假仍是本群成员，历史周冠军次数照常挂出，不因请假归零。
        return f"{name}：病假第{_cn_num(counts['sick_leave_week'] + 1)}周{honor}"
    if eff == "recovering":
        return f"{name}：恢复期第{_cn_num(counts['recovering_week'] + 1)}周{honor}"
    if qualified:
        rk = "🚀" if m["id"] == rocket.get("id") else ""
        return f"{name}：{_km_trim(total)}{honor}{rk}"
    # 未达标：区分「跑了但不足达标线」与「本周确无有效记录」。
    fail_no = _cn_num(counts["fail_count"] + 1)
    if total > 0:
        # 已完成公里照实展示（本期累计）、绝不抹平归零；冠军次数同样照常显示。
        return f"{name}：未达标（本期累计{_km_trim(total)}），累计未达标第{fail_no}次{honor}"
    return f"{name}：未录入有效成绩，总数累计第{fail_no}次{honor}"


def cmd_reminder(args):
    with _db() as conn:
        p = conn.execute("SELECT * FROM period WHERE num = ?", (args.num,)).fetchone()
        if not p:
            _die(f"period_not_found num={args.num}", 3)
        members = conn.execute(
            "SELECT * FROM member WHERE status NOT IN ('exited','wildcard','suspended') "
            "ORDER BY sort_order, id").fetchall()
        has_check, no_check, sick = [], [], []
        for m in members:
            eff = _effective_status(conn, m, args.num)
            if eff == "sick_leave":
                sick.append(m)          # 本期病假 → 列入"早日康复"
                continue
            if eff != "active":          # recovering 等：本期不催、也不列康复
                continue
            total, _, qualified = _period_total(conn, m["id"], args.num)
            if qualified:
                continue
            (no_check if total <= 0 else has_check).append((m, total))
        has_check.sort(key=lambda x: rules.QUALIFY_KM - x[1])  # 差额从小到大

        lines = ["不一班跑团周日提醒", f"第{p['num']}期（{_md(p['end_date'])}）"]
        idx = 1
        for m, total in has_check:
            who = f"@{m['at_name']}" if m["at_name"] else m["name"]
            lines.append(f"{idx}.{who} 尚差{_km_trim(rules.QUALIFY_KM - total)}公里")
            idx += 1
        if no_check:
            who = "　　".join(f"@{m['at_name']}" if m["at_name"] else m["name"]
                             for m, _ in no_check)
            lines.append(f"{idx}.{who} @尚差{_km_trim(rules.QUALIFY_KM)}公里")
            idx += 1
        for s in sick:
            who = f"@{s['at_name']}" if s["at_name"] else s["name"]
            lines.append(f"{idx}.㊗{who} 早日康复[玫瑰][玫瑰][玫瑰]")
            idx += 1
        lines += ["周成绩统计截止时间为周日24:00（北京时间）",
                  "🐎🐎🐎🐎🐎🐎🐎🐎🐎",
                  "[拳头][拳头][拳头][拳头][拳头][拳头][拳头][拳头][拳头]"]
        print("\n".join(lines))


def _md(date_str):
    """YYYY-MM-DD -> M月D日"""
    _, m, d = date_str.split("-")
    return f"{int(m)}月{int(d)}日"


# ---------------------------------------------------------------------------
# 自由查询（只读）
# ---------------------------------------------------------------------------

_DENY = ("INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "ATTACH",
         "REPLACE", "PRAGMA", "VACUUM")


def cmd_query(args):
    sql = args.sql.strip().rstrip(";")
    head = sql.split(None, 1)[0].upper() if sql else ""
    if head not in ("SELECT", "WITH", "EXPLAIN"):
        _die("only SELECT/WITH/EXPLAIN allowed", 5)
    upper = sql.upper()
    for kw in _DENY:
        if f" {kw} " in f" {upper} " or upper.startswith(kw):
            _die(f"forbidden_keyword={kw}", 5)
    with _db() as conn:
        try:
            rows = conn.execute(sql).fetchall()
        except sqlite3.Error as e:
            _die(f"sql_error={e}", 5)
    for r in rows:
        print(" ".join(f"{k}={r[k]}" for k in r.keys()))
    if not rows:
        print("(empty)")


# ---------------------------------------------------------------------------
# 改规则后回填派生列
# ---------------------------------------------------------------------------

def cmd_recompute(args):
    with _db() as conn:
        sql = "SELECT event_id FROM checkin WHERE deleted_at IS NULL"
        params = []
        if args.period is not None:
            sql += " AND period = ?"
            params.append(args.period)
        ids = [r["event_id"] for r in conn.execute(sql, params).fetchall()]
        for event_id in ids:
            _rederive_one(conn, event_id)
        print(f"recomputed={len(ids)}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser():
    p = argparse.ArgumentParser(prog="tracker.py", description="跑团 tracker CLI 工具")
    s = p.add_subparsers(dest="command")

    a = s.add_parser("add_member")
    a.add_argument("id")
    a.add_argument("name")
    a.add_argument("--at-name", dest="at_name")
    a.add_argument("--alias", help="别名/外号，多值用；或，分隔（仅供查找）")
    a.add_argument("--sort", type=int, default=0)
    a.add_argument("--status", default="active")
    a.add_argument("--age-exempt", dest="age_exempt", type=int, default=0, choices=[0, 1])
    a.add_argument("--walk-valid", dest="walk_valid", type=int, default=0, choices=[0, 1])
    a.add_argument("--description")

    a = s.add_parser("update_member")
    a.add_argument("query")
    a.add_argument("--name")
    a.add_argument("--at-name", dest="at_name")
    a.add_argument("--alias", help="整体覆盖别名（传空串清空）；追加请用 add_alias")
    a.add_argument("--sort", type=int)
    a.add_argument("--status", help="角色态：active/suspended/exited/wildcard；请假/恢复请用 add_status")
    a.add_argument("--age-exempt", dest="age_exempt", type=int, choices=[0, 1])
    a.add_argument("--walk-valid", dest="walk_valid", type=int, choices=[0, 1])
    a.add_argument("--description")

    a = s.add_parser("add_alias")
    a.add_argument("query")
    a.add_argument("alias", help="要追加的别名，多值用；或，分隔（去重，不覆盖已有）")

    a = s.add_parser("find_member")
    a.add_argument("query")
    a.add_argument("--asof", help="按该日期所属期查有效状态 YYYY-MM-DD（可未来；默认当前期）")

    a = s.add_parser("list_members")
    a.add_argument("--asof", help="按该日期所属期查有效状态 YYYY-MM-DD（可未来；默认当前期）")

    a = s.add_parser("find_by_img")
    a.add_argument("img", nargs="+",
                   help="图片 id，可给裸 id / img=<id> / 整条 url；"
                        "自动削掉 _NN 后缀，多张一次传完")

    a = s.add_parser("add_checkin")
    a.add_argument("member")
    a.add_argument("occurred_at")
    a.add_argument("activity_type", choices=["outdoor_run", "treadmill", "indoor_run",
                                             "swim", "walk"])
    a.add_argument("distance_raw", type=float)
    a.add_argument("--today", dest="today", required=True,
                   help="今天的日期 YYYY-MM-DD（模型从上下文传入，不读系统时钟）；"
                        "用于拒绝未来日期与当前期以前的补录")
    a.add_argument("--unit", default="km", choices=["km", "miles", "swim_m"])
    a.add_argument("--duration", type=int, dest="duration")
    a.add_argument("--device")
    a.add_argument("--raw")
    a.add_argument("--override-valid", dest="override_valid", type=int, choices=[0, 1])
    a.add_argument("--event-id", dest="event_id")

    a = s.add_parser("backfill_checkin")
    a.add_argument("member")
    a.add_argument("occurred_at")
    a.add_argument("activity_type", choices=["outdoor_run", "treadmill", "indoor_run",
                                             "swim", "walk"])
    a.add_argument("distance_raw", type=float)
    a.add_argument("--today", dest="today", required=True,
                   help="今天的日期 YYYY-MM-DD；管理员补卡只用它拒绝未来日期")
    a.add_argument("--unit", default="km", choices=["km", "miles", "swim_m"])
    a.add_argument("--duration", type=int, dest="duration")
    a.add_argument("--device")
    a.add_argument("--raw")
    a.add_argument("--override-valid", dest="override_valid", type=int, choices=[0, 1])
    a.add_argument("--event-id", dest="event_id")
    a.add_argument("--reason", required=True)

    a = s.add_parser("list_checkins")
    a.add_argument("--member")
    a.add_argument("--period", type=int)
    a.add_argument("--date")

    a = s.add_parser("delete_checkin")
    a.add_argument("event_id")
    a.add_argument("--reason", required=True)

    a = s.add_parser("correct")
    a.add_argument("table", choices=list(_CORRECTABLE))
    a.add_argument("pk")
    a.add_argument("field")
    a.add_argument("value")
    a.add_argument("--reason", required=True)

    a = s.add_parser("add_status")
    a.add_argument("member")
    a.add_argument("occurred_at")
    a.add_argument("to_status", choices=["active", "sick_leave", "recovering", "suspended"])
    a.add_argument("--reason")

    a = s.add_parser("period_current")
    a.add_argument("date", help="今天的日期 YYYY-MM-DD（模型从上下文传入，不取系统时钟）")

    a = s.add_parser("period_finalize")
    a.add_argument("--num", type=int, required=True)
    a.add_argument("--champion")  # 可选；省略则自动取该期距离第一名

    a = s.add_parser("calc")
    a.add_argument("--member")
    a.add_argument("--period", type=int)
    a.add_argument("--from", dest="from")
    a.add_argument("--to")

    a = s.add_parser("report")
    a.add_argument("--num", type=int, required=True)
    a.add_argument("--rocket", help='JSON: {"id":"..","name":"..","distance":N}')
    a.add_argument("--grandslam", type=int, default=33)  # 已固定为 33，保留参数兼容旧调用
    a.add_argument("--out")

    a = s.add_parser("reminder")
    a.add_argument("--num", type=int, required=True)

    a = s.add_parser("query")
    a.add_argument("--sql", required=True)

    a = s.add_parser("recompute")
    a.add_argument("--period", type=int)

    return p


_DISPATCH = {
    "add_member": cmd_add_member, "update_member": cmd_update_member,
    "add_alias": cmd_add_alias,
    "find_member": cmd_find_member, "list_members": cmd_list_members,
    "find_by_img": cmd_find_by_img,
    "add_checkin": cmd_add_checkin, "backfill_checkin": cmd_backfill_checkin,
    "list_checkins": cmd_list_checkins,
    "delete_checkin": cmd_delete_checkin, "correct": cmd_correct,
    "add_status": cmd_add_status, "period_current": cmd_period_current,
    "period_finalize": cmd_period_finalize,
    "calc": cmd_calc, "report": cmd_report, "reminder": cmd_reminder,
    "query": cmd_query, "recompute": cmd_recompute,
}


def main():
    p = _build_parser()
    args = p.parse_args()
    handler = _DISPATCH.get(args.command)
    if handler:
        handler(args)
    else:
        p.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
