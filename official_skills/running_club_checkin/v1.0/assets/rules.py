"""
rules.py - 跑团 tracker 业务规则函数

本文件由 coding agent 维护。修改规则时只改这个文件。
每个函数的签名（参数名、返回类型）不要变，只改函数内部的逻辑/数值。
tracker.py 不需要修改。

这些函数都是纯函数：不读数据库、不做 I/O、只做计算。
tracker.py 在写入和统计时调用它们，DB 只存原始事实。
改完规则后用 `python3 tracker.py recompute` 把派生列回填。

函数列表：
  effective_km          原始距离 + 单位 -> 折算后公里（英里换算 / 游泳代跑 ×4）
  pace_sec_per_km       公里 + 秒 -> 配速（秒/公里）
  judge_validity        运动类型 + 配速 + 豁免标记 -> (valid, note)
  is_qualified          周累计有效公里 -> 是否达标
  monday_of             任意日期 -> 该周周一（空库开第 1 期用）
  period_for_date       截图日期 + 锚点 -> 所属期次号（决定归属）
  reject_checkin_date   截图日期 + 今天 + 锚点 -> 是否拒绝录入（不读系统时钟，今天由调用方传入）
  period_bounds         期次号 + 锚点 -> (周一, 周日)
  fail_streak           达标历史（新->旧）-> 连续未达标周数
  status_streak         每期有效状态（新->旧）+ 目标态 -> 连续该状态周数（病假/恢复）
  discipline_alert      计数 -> 处罚提示（连续N周未达标 / 连续N周病假）

连续计数不落库：成员状态按期存在 period.member_status（JSON 事实流），
fail_count / sick_leave_week / recovering_week 全部由 tracker.py 现算
（喂每期派生的"是否达标 / 有效状态"给这里的纯函数）。
"""

# ---------------------------------------------------------------------------
# 可调数值（规则变更基本只动这一块）
# ---------------------------------------------------------------------------

QUALIFY_KM = 10.0           # 周累计有效距离达标线（公里）

MILES_TO_KM = 1.60934       # 英里制设备换算
SWIM_FACTOR = 4.0           # 游泳代跑：游泳 1km = 跑步 4km（达标线即游泳 ≥ 2500m）

PACE_OK_SEC = 10 * 60               # ≤ 10'00"/km 正常有效
PACE_WARN_SEC = 10 * 60 + 30        # 10'00"~10'30" 有效但提示管理员；> 10'30" 无效
PACE_TOO_FAST_SEC = 4 * 60          # < 4'00"/km 异常快，疑似数据错误

PERIOD_LENGTH_DAYS = 7              # 每期天数（每周一期）
# 期次锚点不写死：由 tracker 从 period 表最早一行读取；
# 表空时锚点 = (1, monday_of(操作日))，见 tracker._period_anchor。

BACKFILL_MAX_LAG = 0               # 允许补录到当前期之前几期：0=仅当前期，N=当前期往前 N 期

FAIL_LIMIT = 3              # 连续 N 周未达标 -> 强制退群
SICK_LIMIT = 4             # 连续 N 周病假 -> 退群休养

# tracker add_checkin / backfill_checkin 的类型/单位名单从这里读。
# 新增类型：把名字加进 ACTIVITY_TYPES，并在 effective_km、judge_validity 里补折算和有效性。
ACTIVITY_TYPES = ("outdoor_run", "treadmill", "indoor_run", "swim", "walk")
UNITS = ("km", "miles", "swim_m")
_RUN_TYPES = ("outdoor_run", "treadmill", "indoor_run")


# ---------------------------------------------------------------------------
# 单位换算 / 距离折算
# ---------------------------------------------------------------------------

def effective_km(activity_type: str, distance_raw: float, unit: str) -> float:
    """原始距离 + 单位 -> 折算后的有效公里数。

    unit: 'km'（公里）| 'miles'（英里制设备）| 'swim_m'（游泳，原始值为米）
    """
    if unit == "swim_m" or activity_type == "swim":
        return distance_raw / 1000.0 * SWIM_FACTOR
    if unit == "miles":
        return distance_raw * MILES_TO_KM
    return distance_raw


# ---------------------------------------------------------------------------
# 配速
# ---------------------------------------------------------------------------

def pace_sec_per_km(distance_km: float, duration_seconds):
    """公里 + 用时秒 -> 配速（秒/公里）。数据不全时返回 None。"""
    if not duration_seconds or not distance_km or distance_km <= 0:
        return None
    return duration_seconds / distance_km


# ---------------------------------------------------------------------------
# 有效性判定（按运动类型分流）
# ---------------------------------------------------------------------------

def judge_validity(activity_type: str, distance_km: float, duration_seconds,
                   age_exempt: bool, walk_valid: bool):
    """判定一条打卡是否计入累计。

    返回 (valid: bool, note: str)。note 是给 AI / 管理员看的提示，空串表示无提示。
    """
    # 年龄豁免（60+）：任何形式只看距离，不计配速
    if age_exempt:
        return (distance_km > 0, "")

    # 游泳代跑：全员可用，配速不限
    if activity_type == "swim":
        return (distance_km > 0, "")

    # 健走：默认无效（距离仍留档），仅「健走有效」成员有效
    if activity_type == "walk":
        if walk_valid:
            return (True, "")
        return (False, "非豁免成员健走不计入")

    # 跑步：按配速分档
    pace = pace_sec_per_km(distance_km, duration_seconds)
    if pace is None:
        # 没有用时，无法核配速：默认按距离计入，提示管理员核对
        return (distance_km > 0, "缺用时无法核配速，按距离暂计入，提示管理员核对")
    if pace < PACE_TOO_FAST_SEC:
        return (False, "配速异常快（<4'00\"/km），疑似数据错误，请上报人确认")
    if pace <= PACE_OK_SEC:
        return (True, "")
    if pace <= PACE_WARN_SEC:
        return (True, "配速略超标（10'00\"~10'30\"），提示管理员确认")
    return (False, "配速超过 10'30\"/km，不计入")


# ---------------------------------------------------------------------------
# 达标
# ---------------------------------------------------------------------------

def is_qualified(total_km: float) -> bool:
    """周累计有效公里 -> 是否达标。"""
    return total_km >= QUALIFY_KM


# ---------------------------------------------------------------------------
# 期次归属（按截图日期；锚点由调用方从 period 表或空库默认传入）
# ---------------------------------------------------------------------------

def monday_of(date_str: str) -> str:
    """任意 YYYY-MM-DD -> 该周周一（周一为一周起始）。"""
    from datetime import date
    y, m, d = (int(x) for x in date_str.split("-"))
    dt = date(y, m, d)
    return date.fromordinal(dt.toordinal() - dt.weekday()).isoformat()


def period_for_date(occurred_at: str, anchor_num: int, anchor_start: str) -> int:
    """截图日期（YYYY-MM-DD）+ 锚点 -> 所属期次号。"""
    delta = _days_between(anchor_start, occurred_at)
    if delta >= 0:
        offset = delta // PERIOD_LENGTH_DAYS
    else:
        offset = -((-delta + PERIOD_LENGTH_DAYS - 1) // PERIOD_LENGTH_DAYS)
    return anchor_num + offset


def reject_checkin_date(occurred_at: str, today: str, anchor_num: int, anchor_start: str):
    """录入日期合法性判定（不读系统时钟，today 由调用方从对话上下文传入）。

    两条规则：
      1. occurred_at 不得晚于 today —— 截图不可能来自未来；
      2. occurred_at 所属期次不得早于 today 所属期次超过 BACKFILL_MAX_LAG 期
         —— 默认 0，即「当前期以前一律不允许补录」。

    返回 (reject: bool, reason: str)。reject=False 时 reason 为空串。
    不依赖任何期次的封板状态，对从无打卡的历史空白期同样生效。
    """
    if occurred_at > today:
        return (True, f"occurred_at={occurred_at} 晚于今天 {today}，截图不可能来自未来")
    occ_period = period_for_date(occurred_at, anchor_num, anchor_start)
    today_period = period_for_date(today, anchor_num, anchor_start)
    lag = today_period - occ_period
    if lag > BACKFILL_MAX_LAG:
        return (True, f"occurred_at={occurred_at}（第{occ_period}期）比当前第{today_period}期"
                      f"早 {lag} 期，当前期以前不允许补录")
    return (False, "")


def period_bounds(num: int, anchor_num: int, anchor_start: str):
    """期次号 + 锚点 -> (start_date, end_date)，均为 YYYY-MM-DD。"""
    start_offset = (num - anchor_num) * PERIOD_LENGTH_DAYS
    start = _add_days(anchor_start, start_offset)
    end = _add_days(start, PERIOD_LENGTH_DAYS - 1)
    return (start, end)


# ---------------------------------------------------------------------------
# 连续计数：现算（不落库）
# ---------------------------------------------------------------------------

def fail_streak(qualified_recent_first: list) -> int:
    """连续未达标周数：从最近一期往回数连续未达标的期数，遇到达标即停。

    qualified_recent_first：已封板期的"是否达标"布尔列表，按期次从新到旧排列，
    且只覆盖「当前 active 状态起始期」及之后（状态一变就重置，故不会越界）。
    """
    n = 0
    for qualified in qualified_recent_first:
        if qualified:
            break
        n += 1
    return n


def status_streak(statuses_recent_first: list, target: str) -> int:
    """连续处于 target 状态的期数：从最近一期往回数连续等于 target 的期数，遇到不等即停。

    statuses_recent_first：每期有效状态（'sick_leave'/'recovering'/'active' 等），
    按期次从新到旧排列。请假/恢复连续周数即 status_streak(列表, 'sick_leave' / 'recovering')。
    """
    n = 0
    for s in statuses_recent_first:
        if s != target:
            break
        n += 1
    return n


def discipline_alert(counts: dict):
    """根据更新后的计数给出处罚提示，无触发返回 None。"""
    if counts.get("fail_count", 0) >= FAIL_LIMIT:
        return f"连续{FAIL_LIMIT}周未达标，应强制退群（修改 status=exited）"
    if counts.get("sick_leave_week", 0) >= SICK_LIMIT:
        return f"连续{SICK_LIMIT}周病假，应退群休养（修改 status=exited，可恢复后重新入群）"
    return None


# ---------------------------------------------------------------------------
# 内部：日期算术（只处理 YYYY-MM-DD，避免引入依赖）
# ---------------------------------------------------------------------------

def _to_ordinal(d: str) -> int:
    from datetime import date
    y, m, day = (int(x) for x in d.split("-"))
    return date(y, m, day).toordinal()


def _days_between(a: str, b: str) -> int:
    return _to_ordinal(b) - _to_ordinal(a)


def _add_days(d: str, n: int) -> str:
    from datetime import date
    return date.fromordinal(_to_ordinal(d) + n).isoformat()