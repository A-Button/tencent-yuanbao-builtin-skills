"""
rules.py - 个人记账规则（唯一建议修改的文件）

分类别名、预算区间、日报文案与轻提示都在这里。
改规则后无需改 ledger.py。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

_TZ = timezone(timedelta(hours=8))

# 标准分类（可增删；改后旧数据仍保留原 category 字符串）
CATEGORIES = (
    "餐饮",
    "奶茶咖啡",
    "交通",
    "日用",
    "娱乐",
    "住房",
    "工资收入",
    "其它",
)

# 口语/品牌 → 标准分类（小写匹配前会先原样再 lower）
CATEGORY_ALIASES = {
    "午饭": "餐饮",
    "晚饭": "餐饮",
    "早饭": "餐饮",
    "早餐": "餐饮",
    "午餐": "餐饮",
    "晚餐": "餐饮",
    "外卖": "餐饮",
    "吃饭": "餐饮",
    "饭": "餐饮",
    "食堂": "餐饮",
    "奶茶": "奶茶咖啡",
    "咖啡": "奶茶咖啡",
    "喜茶": "奶茶咖啡",
    "瑞幸": "奶茶咖啡",
    "星巴克": "奶茶咖啡",
    "茶颜": "奶茶咖啡",
    "霸王茶姬": "奶茶咖啡",
    "打车": "交通",
    "地铁": "交通",
    "公交": "交通",
    "滴滴": "交通",
    "加油": "交通",
    "超市": "日用",
    "日用品": "日用",
    "电影": "娱乐",
    "游戏": "娱乐",
    "房租": "住房",
    "水电": "住房",
    "工资": "工资收入",
    "薪水": "工资收入",
    "奖金": "工资收入",
}

TIP_ENABLED = True  # 日报末尾一句轻提示；不想要就改 False

# 分类行前缀表情（未命中用 💸）
CATEGORY_EMOJI = {
    "餐饮": "🍜",
    "奶茶咖啡": "🧋",
    "交通": "🚗",
    "日用": "🛒",
    "娱乐": "🎬",
    "住房": "🏠",
    "工资收入": "💰",
    "其它": "📦",
}

_REPORT_TOP = ("💸💸💸💸💸💸💸💸💸", "🧋🧋🧋🧋🧋🧋🧋🧋🧋")
_REPORT_BOTTOM = ("💸💸💸💸💸💸💸💸💸", "✨✨✨✨✨✨✨✨✨")


def now_bj() -> datetime:
    return datetime.now(_TZ)


def parse_dt(value: str) -> datetime:
    """解析 YYYY-MM-DD 或 YYYY-MM-DD HH:MM / HH:MM:SS；日期-only 按当天 12:00。"""
    value = (value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(value, fmt)
            if fmt == "%Y-%m-%d":
                dt = dt.replace(hour=12, minute=0, second=0)
            return dt.replace(tzinfo=_TZ)
        except ValueError:
            continue
    raise ValueError(f"bad_datetime value={value}")


def normalize_category(raw: str | None) -> str:
    """用户说法 → 标准/自定义分类。

    顺序：标准类 → 别名表 → 短自定义名原样保留（≤12 字，建议 2～6 字）→ 其它。
    模型侧若已能归到标准类，应直接传标准类名，不必把长描述塞进 category。
    """
    s = (raw or "").strip()
    if not s:
        return "其它"
    if s in CATEGORIES:
        return s
    mapped = CATEGORY_ALIASES.get(s) or CATEGORY_ALIASES.get(s.lower())
    if mapped:
        return mapped
    # 合理自定义类：短名原样落库；过长或笼统词 → 其它
    if len(s) <= 12 and s not in ("支出", "收入", "花费", "开销"):
        return s
    return "其它"


def week_range(asof: datetime) -> tuple[str, str]:
    """自然周：周一 00:00 ~ 周日（含）。返回 (start_date, end_date) YYYY-MM-DD。"""
    monday = asof.date() - timedelta(days=asof.weekday())
    sunday = monday + timedelta(days=6)
    return monday.isoformat(), sunday.isoformat()


def month_range(asof: datetime) -> tuple[str, str]:
    start = asof.date().replace(day=1)
    if start.month == 12:
        nxt = start.replace(year=start.year + 1, month=1, day=1)
    else:
        nxt = start.replace(month=start.month + 1, day=1)
    end = nxt - timedelta(days=1)
    return start.isoformat(), end.isoformat()


def day_range(asof: datetime) -> tuple[str, str]:
    d = asof.date().isoformat()
    return d, d


def period_range(period: str, asof: datetime) -> tuple[str, str]:
    if period == "day":
        return day_range(asof)
    if period == "week":
        return week_range(asof)
    if period == "month":
        return month_range(asof)
    raise ValueError(f"bad_period value={period}")


def money(v: float) -> str:
    """金额展示：整数不带小数，否则最多 2 位去尾零。"""
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return f"{v:.2f}".rstrip("0").rstrip(".")


def tip_line(expense_total: float, budget_remaining: float | None,
             milk_tea_count: int) -> str:
    if not TIP_ENABLED:
        return ""
    if budget_remaining is not None:
        if budget_remaining < 0:
            return "💬 轻提示：预算超了，奶茶可以悠着点 🧋"
        if budget_remaining > 0 and expense_total > 0:
            return "💬 轻提示：预算还有余粮，这周还挺稳 👍"
    if milk_tea_count >= 3:
        return f"💬 轻提示：今天奶茶咖啡已经 {milk_tea_count} 笔啦 🧋x{milk_tea_count}"
    return ""


def _cat_emoji(cat: str) -> str:
    return CATEGORY_EMOJI.get(cat, "💸")


def _member_key(row: dict) -> str:
    return (row.get("recorded_for") or "").strip() or "未署名"


def _group_by_member(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(_member_key(r), []).append(r)
    return out


def _expense_sum(rows: list[dict]) -> float:
    return sum(float(r["amount"]) for r in rows if r.get("direction") == "expense")


def _income_sum(rows: list[dict]) -> float:
    return sum(float(r["amount"]) for r in rows if r.get("direction") == "income")


def _append_cat_lines(lines: list[str], rows: list[dict], indent: str = "") -> int:
    """按分类追加明细行；返回奶茶笔数。"""
    by_cat: dict[str, float] = {}
    milk = 0
    for r in rows:
        if r.get("direction") != "expense":
            continue
        cat = r.get("category") or "其它"
        by_cat[cat] = by_cat.get(cat, 0.0) + float(r["amount"])
        if cat == "奶茶咖啡":
            milk += 1
    for cat, amt in sorted(by_cat.items(), key=lambda x: -x[1]):
        emoji = _cat_emoji(cat)
        notes = [r.get("note") or "" for r in rows
                 if r.get("direction") == "expense"
                 and (r.get("category") or "其它") == cat]
        notes = [n for n in notes if n]
        if len(notes) == 1:
            lines.append(f"{indent}{emoji} {cat} {money(amt)}（{notes[0]}）")
        elif notes:
            lines.append(f"{indent}{emoji} {cat} {money(amt)}（{'；'.join(notes[:3])}）")
        else:
            lines.append(f"{indent}{emoji} {cat} {money(amt)}")
    return milk


def format_period_report(
    title: str,
    subtitle: str,
    rows: list[dict],
    budget: dict | None,
    *,
    empty_text: str = "本期间无记录 🕊️",
    foot_prefix: str = "期间累计支出",
) -> str:
    """
    通用日报/周报/月报模板。
    **始终按成员分段**（含仅 1 人），账单必须能看出是谁的钱；禁止无归属扁平列表。
    rows: [{direction, amount, category, note, recorded_for}, ...]
    """
    expense = _expense_sum(rows)
    income = _income_sum(rows)
    n_expense = sum(1 for r in rows if r.get("direction") == "expense")
    by_member = _group_by_member(rows)

    lines = [title, f"　{subtitle}", "", *_REPORT_TOP]
    if not rows:
        lines.append(empty_text)
        milk = 0
    else:
        lines.append(f"合计支出 {money(expense)} 元 · {n_expense} 笔 💸")
        if income > 0:
            lines.append(f"合计收入 {money(income)} 元 💰")
        lines.append("")
        milk = 0
        # 先成员小计，再每人明细（不排行，按名字排序；单人也必须带 👤）
        lines.append("👥 按成员")
        for name, mrows in sorted(by_member.items(), key=lambda x: x[0]):
            me = _expense_sum(mrows)
            mc = sum(1 for r in mrows if r.get("direction") == "expense")
            lines.append(f"· {name}：{money(me)} 元 / {mc} 笔")
        lines.append("")
        for name, mrows in sorted(by_member.items(), key=lambda x: x[0]):
            me = _expense_sum(mrows)
            lines.append(f"👤 {name} · {money(me)} 元")
            milk += _append_cat_lines(lines, mrows, indent="  ")
            lines.append("")
        if lines[-1] == "":
            lines.pop()

    lines.append("")
    foot = f"{foot_prefix} {money(expense)} 元 📊"
    rem = None
    if budget:
        rem = float(budget["remaining"])
        label = {"day": "日", "week": "周", "month": "月"}.get(budget["period"], budget["period"])
        cat_s = f"（{budget['category']}）" if budget.get("category") else ""
        if rem < 0:
            foot += f"（{label}预算{cat_s} {money(float(budget['amount']))}，超支 {money(-rem)} ⚠️）"
        else:
            foot += f"（{label}预算{cat_s} {money(float(budget['amount']))}，剩余 {money(rem)} ✅）"
    lines.append(foot)

    tip = tip_line(expense, rem, milk)
    if tip:
        lines.append(tip)
    lines += ["", *_REPORT_BOTTOM]
    return "\n".join(lines)


def format_daily_report(
    date: str,
    rows: list[dict],
    week_expense: float,
    budget: dict | None,
) -> str:
    """日报：按成员分段（有署名时）+ 脚注本周累计。"""
    text = format_period_report(
        "一起记账小本本",
        date,
        rows,
        None,  # 预算放脚注和本周一起处理
        empty_text="今日无记录 🕊️",
        foot_prefix="今日累计支出",
    )
    # 去掉 format_period_report 自带的无预算脚注行，改成今日+本周+预算
    parts = text.split("\n")
    # 去掉底部装饰前的「今日累计…」行，后面重写脚注
    body: list[str] = []
    i = 0
    while i < len(parts):
        if parts[i].startswith("今日累计支出"):
            i += 1
            continue
        if parts[i] in _REPORT_BOTTOM:
            break
        body.append(parts[i])
        i += 1
    while body and body[-1] == "":
        body.pop()

    expense = _expense_sum(rows)
    rem = float(budget["remaining"]) if budget else None
    milk = sum(1 for r in rows if r.get("direction") == "expense"
               and (r.get("category") or "") == "奶茶咖啡")

    body.append("")
    body.append(f"今日累计支出 {money(expense)} 元 📊")
    body.append(f"本周累计支出 {money(week_expense)} 元 📊")
    if budget:
        label = {"day": "日", "week": "周", "month": "月"}.get(budget["period"], budget["period"])
        cat_s = f"（{budget['category']}）" if budget.get("category") else ""
        if rem is not None and rem < 0:
            body.append(
                f"{label}预算{cat_s} {money(float(budget['amount']))}，超支 {money(-rem)} ⚠️"
            )
        else:
            body.append(
                f"{label}预算{cat_s} {money(float(budget['amount']))}，剩余 {money(rem)} ✅"
            )
    tip = tip_line(expense, rem, milk)
    if tip:
        body.append(tip)
    body += ["", *_REPORT_BOTTOM]
    return "\n".join(body)
