"""能量收支的纯计算：基础代谢、日常活动、训练消耗。

这个模块**不碰存储、不碰时间、不发 RPC**，全是纯函数，因此可以脱离沙箱单测。
调用方负责把档案、体重、训练记录取出来喂进来。

三项消耗的口径各不相同，混着说会得到对不上的数字：

- **基础代谢**由 Mifflin-St Jeor 公式算出，是躺着不动一天的耗能。它需要身高、
  年龄、性别、体重四项，缺一项就算不出来——不要拿「平均人」的数去补。
- **日常活动**是拿基础代谢乘一个档位系数的增量部分，`bmr * (factor - 1)`。
  它是**估算**，不是实测：档位由用户自己选，选错了整个数就偏。卡片上必须标明。
- **训练消耗**是课级 MET × 体重 × 时长。注意它**不是**逐个动作乘出来的：阻力
  训练里组间休息占大头，逐动作乘会漏掉休息、做出一个看起来比实际精确的数。

时长的来源有两种，`session_duration()` 会告诉你这次用的是哪种，卡片要如实说明：

- `logged`：由逐个动作的勾选时间戳推出。只有跨度落在合理窗口内才采信——
  用户如果练完才一次性补勾，跨度会塌成几秒；如果早上勾一个、晚上补完，跨度会
  长到十几小时。两头都不可信，落到窗口外就退回估算。
- `estimated`：按组数与次数估。每组 = 动作时间 + 固定组间休息。
"""

from __future__ import annotations

import sys
from pathlib import Path
_scripts = Path(__file__).resolve().parents[1]
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))
import _boot
_boot.install()

# Mifflin-St Jeor 的性别常数项。
_SEX_CONSTANT = {"male": 5.0, "female": -161.0}

# 活动量档位系数。取通行的 Harris-Benedict 活动因子，只收这三档：
# 再往上的「高度活跃」「运动员」对久坐办公人群是误选项，而训练消耗已经单列，
# 把它算进档位里会重复计一次。
ACTIVITY_FACTORS = {
    "sedentary": 1.2,   # 久坐：整天坐着，几乎不走动
    "light": 1.375,     # 轻度：每天有通勤步行或站立工作
    "moderate": 1.55,   # 中度：每天有明显的体力活动
}

# 时间戳推时长的可信窗口（分钟）。低于下限多半是练完一次性补勾，
# 高于上限多半是中途搁置后补完，两种都不反映真实训练时长。
DURATION_TRUST_MIN = 15.0
DURATION_TRUST_MAX = 180.0

# 估算时长用的常数。每次动作按 3 秒计，按秒计的动作直接用它的秒数；
# 每组后固定休息 60 秒。
_SECONDS_PER_REP = 3.0
_REST_SECONDS_PER_SET = 60.0


class EnergyInputError(ValueError):
    """入参不满足计算前提。调用方应转成 INVALID_ARGUMENT 之类的业务错误。"""


def basal_metabolic_rate(sex: str, weight_kg: float, height_cm: float, age: int) -> float:
    """Mifflin-St Jeor 基础代谢，单位 kcal/天。

    选它而不是 Harris-Benedict，是因为在当代人群上的实测误差更小，也是多数
    营养学教材现在给的默认式子。
    """
    if sex not in _SEX_CONSTANT:
        raise EnergyInputError("sex 只能是 male 或 female")
    if not (20 <= weight_kg <= 300):
        raise EnergyInputError("weight_kg 超出合理范围 20–300")
    if not (100 <= height_cm <= 250):
        raise EnergyInputError("height_cm 超出合理范围 100–250")
    if not (10 <= age <= 120):
        raise EnergyInputError("age 超出合理范围 10–120")
    base = 10.0 * weight_kg + 6.25 * height_cm - 5.0 * age
    return base + _SEX_CONSTANT[sex]


def daily_activity_burn(bmr: float, activity_level: str) -> float:
    """日常活动消耗 = 基础代谢 × (档位系数 − 1)，单位 kcal/天。

    减 1 是因为档位系数是**总消耗**相对基础代谢的倍数，基础代谢那部分已经
    单列了，不减会把它重复计一次。
    """
    factor = ACTIVITY_FACTORS.get(activity_level)
    if factor is None:
        raise EnergyInputError(
            "activity_level 只能是 %s" % "/".join(ACTIVITY_FACTORS)
        )
    return bmr * (factor - 1.0)


def session_met(exercises: list[dict]) -> float:
    """整节课的代谢当量，由各动作的 met 按组数加权平均。

    加权用组数而不是动作个数：4 组的深蹲对整节课强度的贡献本来就该比 1 组的
    侧平举大。组数缺失或非正数的按 1 组计，不让一条脏数据把整节课的权重吃掉。
    """
    if not exercises:
        raise EnergyInputError("exercises 不能为空")
    total_weight = 0.0
    weighted = 0.0
    for item in exercises:
        met = item.get("met")
        if met is None:
            raise EnergyInputError("动作 %s 缺 met" % item.get("exercise_key", "?"))
        sets = item.get("sets") or 1
        if sets <= 0:
            sets = 1
        weighted += float(met) * sets
        total_weight += sets
    return weighted / total_weight


def estimated_duration_minutes(exercises: list[dict]) -> float:
    """按组数与次数估训练时长，单位分钟。

    每组 = 动作时间 + 固定组间休息。动作时间按 rep_unit 分开算：按秒计的动作
    （平板支撑那类）直接用秒数，按次计的每次折 3 秒。
    """
    if not exercises:
        raise EnergyInputError("exercises 不能为空")
    seconds = 0.0
    for item in exercises:
        sets = item.get("sets") or 1
        if sets <= 0:
            sets = 1
        reps = item.get("reps") or 0
        if item.get("rep_unit") == "秒":
            work = float(reps)
        else:
            work = float(reps) * _SECONDS_PER_REP
        seconds += sets * (work + _REST_SECONDS_PER_SET)
    return seconds / 60.0


def session_duration(
    exercises: list[dict], span_minutes: float | None
) -> tuple[float, str]:
    """定下这节课按多长时间算，并说明用的是哪种口径。

    返回 ``(分钟, method)``，method 是 ``logged`` 或 ``estimated``。调用方必须把
    method 透传到卡片上——「实测 42 分钟」和「估算 42 分钟」对用户是两回事。
    """
    if span_minutes is not None and DURATION_TRUST_MIN <= span_minutes <= DURATION_TRUST_MAX:
        return span_minutes, "logged"
    return estimated_duration_minutes(exercises), "estimated"


def training_burn(met: float, weight_kg: float, duration_minutes: float) -> float:
    """训练消耗 = MET × 体重(kg) × 时长(小时)，单位 kcal。"""
    if met <= 0:
        raise EnergyInputError("met 必须为正")
    if not (20 <= weight_kg <= 300):
        raise EnergyInputError("weight_kg 超出合理范围 20–300")
    if duration_minutes < 0:
        raise EnergyInputError("duration_minutes 不能为负")
    return met * weight_kg * (duration_minutes / 60.0)


def expenditure(
    profile: dict | None,
    weight_kg: float | None,
    exercises: list[dict] | None,
    span_minutes: float | None = None,
) -> dict:
    """把三项消耗汇成一份结果，缺什么就在 ``missing`` 里说清楚。

    **缺数不补默认值。** 没有档案就没有基础代谢，没有基础代谢就没有能量余额——
    这时候返回的 ``total`` 是 ``None`` 而不是 0，调用方据此决定卡片降级成什么样子。
    返回 0 会让「算不出来」看起来像「今天没消耗」，那是两回事。
    """
    missing: list[str] = []
    bmr = None
    activity = None
    training = None
    duration_method = None

    if not profile:
        missing.append("body_profile")
    elif weight_kg is None:
        missing.append("weight")
    else:
        bmr = basal_metabolic_rate(
            profile["sex"], weight_kg, profile["height_cm"], profile["age"]
        )
        activity = daily_activity_burn(bmr, profile["activity_level"])

    if not exercises:
        # 今天没练不是缺数，是真的没有，记 0 而不是 None。
        training = 0.0
    elif weight_kg is None:
        missing.append("weight")
        training = None
    else:
        minutes, duration_method = session_duration(exercises, span_minutes)
        training = training_burn(session_met(exercises), weight_kg, minutes)

    # 先各自取整再相加，**顺序不能反**。拿未取整的三项求和再取整，会出现
    # 三个分项显示值加起来不等于总数显示值的情况（各差半个 kcal 就能凑出 1）。
    # 日报正要把这四个数并排摆出来，对不上用户一眼就看见了。
    parts = [_round_kcal(bmr), _round_kcal(activity), _round_kcal(training)]
    total = sum(parts) if all(p is not None for p in parts) else None

    return {
        "bmr": parts[0],
        "daily_activity": parts[1],
        "training": parts[2],
        "total": total,
        # 日常活动永远是档位估的，训练时长可能是实测也可能是估的。
        "daily_activity_estimated": activity is not None,
        "training_duration_method": duration_method,
        "missing": sorted(set(missing)),
    }


def energy_balance(intake_kcal: float | None, expenditure_kcal: float | None):
    """能量余额 = 摄入 − 消耗。任意一边缺就返回 None，不拿 0 顶替。"""
    if intake_kcal is None or expenditure_kcal is None:
        return None
    return round(intake_kcal - expenditure_kcal)


def _round_kcal(value):
    return None if value is None else round(value)
