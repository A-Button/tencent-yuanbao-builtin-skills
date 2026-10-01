#!/usr/bin/env python3
"""Attach XCard display fields onto the shared diet payload's current_meal."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from store import MEAL_LABEL, PHOTOS_DIRNAME, archive_roots, inputs_photo, resolve_photo

# 绝对地址：前端不按自己的 origin 补相对路径，只能由 skill 给全。
# 代价是环境写死——测试和预发环境点开卡片也会跳到线上域名。
DETAIL_JUMP_URL = "https://yuanbao.tencent.com/e/diet-assistant?yb_top_bar=1&need_xcard_token=1"

# 用户没传图时出卡用的兜底图。只写进 structuredContent，不回写档案——
# 档案里 photo_url 仍是 null，下次有了真图不会被这张占位图卡住。
FALLBACK_PHOTO_URL = (
    "https://cdn-pro.yuanbao.tencent.com/public/pro/"
    "NTJjYzZjMDItMzI2Yy00ZjNmLWJiNDYtMmY3ZmVmZWY2NzEy.png?width=294&height=344"
)


def _text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _archive_photo(raw: str) -> str | None:
    """只认已经冻进档案 photos/ 的绝对路径。别的本地文件不当成这顿饭的图。"""
    if not raw.startswith("/") or raw.startswith("//"):
        return None
    path = Path(raw)
    try:
        resolved = path.resolve()
    except OSError:
        return None
    for root in archive_roots():
        photos = (root / PHOTOS_DIRNAME).resolve()
        try:
            resolved.relative_to(photos)
        except ValueError:
            continue
        if resolved.is_file():
            return str(path)
    return None


def _card_photo(meal: dict) -> str | None:
    """出卡用的图片引用。冻结文件在就给它的绝对路径，否则才退回还能打开的地址。

    宿主会把 /data/user/ 下的路径签成长期地址。相对 photo_key 不往卡上放，
    端上会优先拿相对路径，那就签不了。
    """
    frozen = resolve_photo(meal.get("photo_key"), meal.get("_archive_root"))
    if frozen is not None:
        return str(frozen)
    raw = _text(meal.get("photo_url")).strip()
    if raw.startswith(("https://", "http://")):
        return raw
    archived = _archive_photo(raw)
    if archived:
        return archived
    found = inputs_photo(raw)
    return str(found) if found else None


def _live_photo_url(meal: dict) -> str | None:
    """花名册缩略图。兜底图不当成这顿饭的实拍。"""
    if not isinstance(meal, dict):
        return None
    photo = _card_photo(meal)
    if not photo or photo == FALLBACK_PHOTO_URL:
        return None
    return photo


# 长的放前面。「虾」不能先于「小龙虾」，「肉」不能先于「青菜」「烤肉串」。
_FOOD_EMOJI = (
    ("小龙虾", "🦞"), ("龙虾", "🦞"), ("螃蟹", "🦀"), ("蟹", "🦀"),
    ("烤肉串", "🍖"), ("烤串", "🍖"), ("培根", "🥓"), ("香肠", "🌭"),
    ("西兰花", "🥦"), ("花椰菜", "🥦"), ("青菜", "🥬"), ("蔬菜", "🥬"), ("生菜", "🥬"),
    ("番茄", "🍅"), ("西红柿", "🍅"), ("黄瓜", "🥒"), ("土豆", "🥔"), ("红薯", "🍠"),
    ("玉米", "🌽"), ("蘑菇", "🍄"), ("茄子", "🍆"), ("胡萝卜", "🥕"),
    ("紫菜", "🥣"), ("蛋花", "🥚"), ("鸡蛋", "🥚"), ("煎蛋", "🍳"), ("蛋", "🥚"),
    ("粉条", "🍜"), ("拉面", "🍜"), ("面条", "🍜"), ("米粉", "🍜"), ("意面", "🍝"),
    ("米饭", "🍚"), ("主食", "🍚"), ("炒饭", "🍚"), ("盖饭", "🍛"), ("咖喱", "🍛"),
    ("虾", "🦐"), ("鱼", "🐟"), ("鱿鱼", "🦑"), ("牛", "🥩"), ("鸡", "🍗"), ("肉", "🥩"),
    ("豆腐", "🫘"), ("豆浆", "🥛"), ("酸奶", "🥛"), ("牛奶", "🥛"), ("奶茶", "🧋"),
    ("咖啡", "☕"), ("茶", "🍵"), ("果汁", "🧃"), ("可乐", "🥤"),
    ("粥", "🥣"), ("汤", "🍲"), ("火锅", "🍲"), ("麻辣烫", "🍲"),
    ("饺子", "🥟"), ("包子", "🥟"), ("馄饨", "🥟"), ("馒头", "🍞"), ("面包", "🍞"),
    ("沙拉", "🥗"), ("汉堡", "🍔"), ("披萨", "🍕"), ("薯条", "🍟"), ("寿司", "🍣"),
    ("苹果", "🍎"), ("香蕉", "🍌"), ("水果", "🍎"), ("蛋糕", "🍰"), ("巧克力", "🍫"),
    ("啤酒", "🍺"), ("红酒", "🍷"), ("坚果", "🥜"),
)


def default_scene(items: list) -> str:
    """没给场景速写时按桌上的食物补一句。详情页那块深色区域绑的就是这句。"""
    names = [_text(item.get("name")).strip() for item in items if isinstance(item, dict)]
    names = [name for name in names if name]
    if not names:
        return ""
    if len(names) == 1:
        return f"这一餐是{names[0]}。"
    if len(names) <= 3:
        return f"桌上有{'、'.join(names[:-1])}和{names[-1]}。"
    return f"桌上有{'、'.join(names[:3])}等{len(names)}样。"


def food_emoji(name: str) -> str:
    """按食物名挑一个 emoji。认不出再退回餐盘，避免一整桌都是同一个符号。"""
    text = name or ""
    for needle, emoji in _FOOD_EMOJI:
        if needle in text:
            return emoji
    return "🍽️"


def _fill_food_rows(meal: dict) -> None:
    """食物行绑 emoji / name / portion。没给 emoji 时按菜名补，不回写档案。"""
    rows = []
    for item in meal.get("items") or []:
        if not isinstance(item, dict):
            rows.append(item)
            continue
        row = dict(item)
        if not _text(row.get("emoji")).strip():
            row["emoji"] = food_emoji(_text(row.get("name")))
        if row.get("portion") is None:
            row["portion"] = ""
        rows.append(row)
    meal["items"] = rows


def _fill_photo_url(meal: dict, *, with_badge: bool = False) -> None:
    """出卡时 photo_url 写成冻结文件的绝对路径，没有冻结文件再用还能打开的地址。

    photo_key 从出卡这份里拿掉。端上会优先拿相对 key，相对路径签不成长期地址。
    这一步只改出卡的那份，不回写档案。
    """
    live = _card_photo(meal)
    meal["photo_url"] = live or FALLBACK_PHOTO_URL
    meal.pop("_archive_root", None)
    if "photo_key" in meal:
        meal["photo_key"] = None
    if with_badge:
        meal["photo_badge"] = "实拍" if live else "无图"


CARD_TITLE = "今日饮食记录"
EMPTY_TODAY = "今天还没有记录"
EMPTY_ARCHIVE = "还没有饮食记录"

CARD_MEAL_ORDER = (
    "breakfast", "lunch", "dinner", "beverage", "afternoon_tea", "midnight",
)

# 卡面花名册只排正餐三行。CARD_MEAL_ORDER 里另外三类（饮品、下午茶、夜宵）仍然
# 进档案，只是不占卡面的行——卡面是「这一餐记了没」的提醒位，不是全量清单。
# 要看全量走对话问，模型那边有 get_day。
MAIN_SLOTS = (("breakfast", "早餐"), ("lunch", "午餐"), ("dinner", "晚餐"))

HEADLINE_PENDING = "【{label}】吉时已到，小主用膳否？"
HEADLINE_RECORDED = "【{label}】已入膳册，小主请过目"
HEADLINE_SKIPPED = "【{label}】今日不食，小主且歇"
# 统计视图另起一句。上面两句说的都是「今天这一餐」，挂到近 N 天的统计上就成了
# 误导：用户先看到一张「该吃晚餐了 · 共记录 2 餐」，再看到一张「三餐待记录」，
# 读起来像前后矛盾，其实一个说的是近 7 天、一个说的是今天。
HEADLINE_STATS = "近 {days} 天的饮食，小主请过目"
HEADLINE_STATS_EMPTY = "近 {days} 天还没有可分析的记录"

# 一行明细最多摊开一样食物，再多折成「等 N 样」。
# 为什么是一样：餐次行跟训练卡的动作行现在是同一套盒模型（灰托盘里套白行卡），
# 嵌套下来行内可用宽度比过去窄约 60px。摊两样时「270kCal | 菜心包子 × 1个,
# 豆浆 × 一碗」会折成两行，那一行就比另外两行高，整列的节奏就塌了。
# 训练卡那边的 meta（「4组 × 12次 · 徒手」）也是单行，对齐的是这个。
SLOT_ITEM_LIMIT = 1


def _slot_detail(meals: list) -> str:
    """把一个餐次拼成「220kCal | 菜心包子 × 一份, 豆浆 × 一碗」。

    ``portion`` 是份量词（「一碗」「1个」）不是数量，所以照搬设计稿的 × 写法读出来是
    「豆浆 × 一碗」。热量取整：这行是给人扫一眼的，小数没有意义。
    """
    kcal = 0.0
    names: list[str] = []
    for meal in meals:
        kcal += float((meal.get("totals") or {}).get("kcal") or 0)
        for item in meal.get("items") or []:
            name = _text(item.get("name")).strip()
            if not name:
                continue
            portion = _text(item.get("portion")).strip()
            names.append(f"{name} × {portion}" if portion else name)
    if not names:
        return f"{kcal:.0f}kCal"
    shown = ", ".join(names[:SLOT_ITEM_LIMIT])
    if len(names) > SLOT_ITEM_LIMIT:
        shown += f" 等{len(names)}样"
    return f"{kcal:.0f}kCal | {shown}"


SLOT_EMOJI = {"早餐": "🥐", "午餐": "🍱", "晚餐": "🍲"}


def _slot_row(label: str, meals: list, *, is_current: bool, skipped: bool = False) -> dict:
    """花名册的一行。

    缩略图只认用户实拍：拿不到就把 ``no_photo`` 打开，让卡面画灰底占位块，而不是塞
    一张跟这顿饭无关的兜底图。A2UI 的 ``Visibility`` 没有取反，正反两个开关都得给。

    占位块上的 emoji 按餐次分：三行都摆同一个 🍽️ 时，一眼看过去分不出哪行是哪餐。

    行右侧是互斥的 ChoicePicker，三行写同一个 ``/card_state/selected``。点选只改
    数据模型，不发 prompt。底部按钮用 formatString 读 ``selected/0``。
    已吃或已跳过的行改成 ✓，跟训练卡完成态同一套。
    """
    recorded = bool(meals)
    skipped = bool(skipped) and not recorded
    if recorded:
        name = f"{label}（已吃）"
    elif skipped:
        name = f"{label}（已跳过）"
    else:
        name = f"{label}（待记录）"
    done = recorded or skipped
    photo = ""
    for meal in meals:
        candidate = _live_photo_url(meal) or ""
        # 花名册跑在 _fill_photo_url 之后，那一步已经把没图的餐写成了兜底图，
        # 所以这里必须把兜底图排掉：认出来它才画得成占位块，否则三行都会挂着同一张
        # 跟这顿饭无关的图。
        if candidate and candidate != FALLBACK_PHOTO_URL:
            photo = candidate
            break
    return {
        "name": name,
        "detail": _slot_detail(meals) if recorded else "",
        "has_detail": recorded,
        "has_photo": bool(photo),
        "no_photo": not photo,
        "photo_url": photo,
        "emoji": SLOT_EMOJI.get(label, "🍽️"),
        "status": "✓" if done else "○",
        "is_current": is_current,
        "not_current": not is_current,
        "done": done,
        "not_done": not done,
    }


def _card_state(app_view: dict) -> dict:
    """卡面的开关位与不随餐次变化的门面字段。

    **为什么单独一个顶层对象：** 卡片的每条绑定原来都挂在 ``/current_meal/*`` 下，
    等于假定「总有一餐可显示」。这个假定有两处不成立——当天零记录时 ``current_meal``
    是 ``{}``；``get_stats`` 在「今天没吃、本周有吃」时也是 ``{}``（统计 tab 确实有
    内容，所以有意不跳过卡片）。A2UI 取不到路径是静默不画，于是整张卡只剩个空壳，
    还会因为 ``dataMode: keep_latest`` 把上一张好卡替换掉。

    所以门面（标题、详情页地址）从 ``current_meal`` 抬到这里——它俩本来就是常量，
    跟是哪一餐无关；再加两个布尔位给 ``Visibility`` 用，让「没有餐」变成卡面上一句
    明确的话，而不是一片空白。

    **为什么三餐是三个定死的键而不是一个列表：** 卡面永远是早/午/晚三行，没有
    「第四行」这回事。规范里也找不到任何在列表模板内部用 ``Visibility`` 的例子，而
    每行要按「是不是当前餐次」切深浅两套文字——写成列表就得赌相对路径下的
    ``Visibility`` 能生效，赌输了是静默画错。三个键配绝对路径是现有卡验过的写法。

    ``empty_text`` 这一轮只剩 H5 空态标题在读，卡面不再画它（花名册三行全「待记录」
    本身就是空态）。
    """
    meal = app_view.get("current_meal")
    has_meal = isinstance(meal, dict) and bool(meal)
    grouped = (app_view.get("today") or {}).get("meals_by_type") or {}
    skipped_slots = set((app_view.get("today") or {}).get("skipped_slots") or [])
    stats = app_view.get("stats") or {}
    archive_has_records = any(
        (stats.get(period) or {}).get("meal_count") for period in ("day", "week")
    )
    # 文案只看数据，不看是哪个 operation：当天空但本周有记录时说「今天还没有记录」，
    # 全库都空才说「还没有饮食记录」。同一份数据在哪个入口看到的都是同一句。
    empty_text = EMPTY_TODAY if (any(grouped.values()) or archive_has_records) else EMPTY_ARCHIVE
    now = datetime.now().astimezone()
    current_slot = "breakfast" if now.hour < 10 else ("lunch" if now.hour < 16 else "dinner")
    slot_labels = dict(MAIN_SLOTS)
    label = slot_labels[current_slot]
    show_stats = _text(app_view.get("default_tab"), "meal") == "stats"
    if show_stats:
        period = _text(app_view.get("default_period"), "week")
        stat = stats.get(period) or {}
        days = stat.get("range_days") or (1 if period == "day" else 7)
        template = HEADLINE_STATS if stat.get("meal_count") else HEADLINE_STATS_EMPTY
        headline = template.format(days=days)
    else:
        headline = (
            HEADLINE_RECORDED if bool(grouped.get(current_slot))
            else HEADLINE_SKIPPED if current_slot in skipped_slots
            else HEADLINE_PENDING
        ).format(label=label)
    rows = {
        key: _slot_row(
            slot_labels[key], grouped.get(key) or [],
            is_current=(key == current_slot),
            skipped=key in skipped_slots,
        )
        for key, _ in MAIN_SLOTS
    }
    return {
        "has_meal": has_meal,
        "is_empty": not has_meal,
        "show_roster": not show_stats,
        "show_stats": show_stats,
        "empty_text": empty_text,
        "title": CARD_TITLE,
        "jump_url": DETAIL_JUMP_URL,
        "brand": "每日膳食",
        "headline": headline,
        # ChoicePicker 要字符串数组。服务端固定下发空数组：打开时三行都不勾。
        # 用户点选只改端上的数据模型；按钮用 formatString 读 selected/0。
        # 不能预填当前餐次——出卡会把端上的勾选冲掉，看起来像跳回第一行。
        "selected": [],
        **rows,
    }


def _clock(value: object) -> str:
    raw = _text(value)
    return raw.split("T", 1)[1][:5] if "T" in raw else ""


def _build_today_card(today: dict) -> dict:
    grouped = today.get("meals_by_type") or {}
    meals = []
    for meal_type in CARD_MEAL_ORDER:
        for meal in grouped.get(meal_type) or []:
            totals = meal.get("totals") or {}
            items = meal.get("items") or []
            names = "、".join(_text(item.get("name")) for item in items[:3] if item.get("name"))
            if len(items) > 3:
                names += f" 等{len(items)}样"
            kcal = totals.get("kcal") or 0
            meal_type_label = MEAL_LABEL.get(meal_type, "一餐")
            clock = _clock(meal.get("eaten_at"))
            title = _text(meal.get("title"), "一餐")
            meals.append({
                "heading": f"{meal_type_label} {clock} · {title}",
                "title": title,
                "foods": names or "暂无食物明细",
                "kcal": f"{kcal:g} kcal",
                "photo_url": _text(meal.get("photo_url"), FALLBACK_PHOTO_URL),
            })
    totals = today.get("totals") or {}
    return {
        "has_meals": bool(meals),
        "summary": (
            f"今天已记录 {len(meals)} 餐 · {totals.get('kcal', 0):g} kcal"
            if meals else "今天还没有记录，拍下第一餐就会出现在这里"
        ),
        "meals": meals,
    }


def _build_stats_card(stats: dict, period: str) -> dict:
    stat = stats.get(period) or {}
    avg = stat.get("avg") or {}
    days = stat.get("range_days") or (1 if period == "day" else 7)
    count = stat.get("meal_count") or 0
    return {
        "period": f"近 {days} 天",
        # 范围写进这行大字里，别只靠上面那行小灰字。用户是把两张卡上下对着看的：
        # 光写「共记录 2 餐」，跟下一张「三餐待记录」摆在一起就成了自相矛盾。
        "summary": f"近 {days} 天共 {count} 餐" if count else "还没有可分析的餐食记录",
        "avg_kcal": f"日均热量 {avg.get('kcal', 0):g} kcal",
        "avg_macros": (
            f"蛋白 {avg.get('protein_g', 0):g}g · "
            f"碳水 {avg.get('carb_g', 0):g}g · "
            f"脂肪 {avg.get('fat_g', 0):g}g"
        ),
        "regularity": f"规律度 {stat.get('regularity_score', 0)} 分",
    }


def enrich_display_fields(app_view: dict) -> dict:
    """Write XCard-bound fields onto current_meal. Mutates and returns app_view.

    The XCard binds /current_meal/* only: card_title, jump_url, title, photo_url,
    eaten_at, meal_type_display, photo_badge, foods_label, and items' emoji / name / portion.
    No second payload.
    """
    meal = app_view.get("current_meal")
    if isinstance(meal, dict) and meal:
        meal_type = _text(meal.get("meal_type"))
        meal["card_title"] = CARD_TITLE
        meal["foods_label"] = "本餐 食物"
        meal["jump_url"] = DETAIL_JUMP_URL
        meal["meal_type_display"] = MEAL_LABEL.get(meal_type, "一餐")
        _fill_food_rows(meal)
        if not _text(meal.get("scene_oneliner")).strip():
            meal["scene_oneliner"] = default_scene(meal.get("items") or [])
        _fill_photo_url(meal, with_badge=True)
        # 营养账单顶部「AI估值」。模板有的绑 /current_meal/totals/ai_price，有的绑顶层。
        price = (meal.get("totals") or {}).get("ai_price")
        if price is not None:
            meal["ai_price"] = price
            meal["ai_price_display"] = f"¥{price:g}"
        app_view["current_meal"] = meal

    # 今日食书每张卡自己决定用实拍还是兜底，不跟 current_meal 绑死。
    today = app_view.get("today")
    if isinstance(today, dict):
        grouped = today.get("meals_by_type") or {}
        if isinstance(grouped, dict):
            for meals in grouped.values():
                if not isinstance(meals, list):
                    continue
                for summary in meals:
                    if isinstance(summary, dict):
                        _fill_photo_url(summary)
        app_view["card_today"] = _build_today_card(today)

    stats = app_view.get("stats")
    period = _text(app_view.get("default_period"), "week")
    if isinstance(stats, dict):
        app_view["card_stats"] = _build_stats_card(stats, period)

    # 放最后：它要读上面算完的 current_meal / today / stats 才判得出空不空。
    app_view["card_state"] = _card_state(app_view)
    return app_view
