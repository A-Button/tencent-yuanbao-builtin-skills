import json
import sys

# (起始月, 起始日, 星座名, 日期区间展示文案, emoji)，按起始日期升序排列。
# 判定规则：取"小于等于目标日期"的最后一条边界，即为所属星座
# （摩羯座跨年，1月1日-1月19日落不到任何边界，默认兜底为摩羯座）。
ZODIAC_TABLE = [
    (1, 20, "水瓶座", "1月20日-2月18日", "🏺"),
    (2, 19, "双鱼座", "2月19日-3月20日", "🐟"),
    (3, 21, "白羊座", "3月21日-4月19日", "🐏"),
    (4, 20, "金牛座", "4月20日-5月20日", "🐂"),
    (5, 21, "双子座", "5月21日-6月21日", "👯"),
    (6, 22, "巨蟹座", "6月22日-7月22日", "🦀"),
    (7, 23, "狮子座", "7月23日-8月22日", "🦁"),
    (8, 23, "处女座", "8月23日-9月22日", "🌾"),
    (9, 23, "天秤座", "9月23日-10月23日", "⚖️"),
    (10, 24, "天蝎座", "10月24日-11月22日", "🦂"),
    (11, 23, "射手座", "11月23日-12月21日", "🏹"),
    (12, 22, "摩羯座", "12月22日-1月19日", "🐐"),
]


def zodiac_of(month, day):
    result = ZODIAC_TABLE[-1]
    for entry in ZODIAC_TABLE:
        start_month, start_day = entry[0], entry[1]
        if (month, day) >= (start_month, start_day):
            result = entry
    return result


def parse_month_day(args):
    month, day = args.get("birth_month"), args.get("birth_day")
    if month is not None and day is not None:
        return int(month), int(day)
    birth_date = args.get("birth_date") or args.get("birthDate") or ""
    parts = str(birth_date).split("-")
    if len(parts) >= 3:
        return int(parts[1]), int(parts[2])
    raise ValueError("缺少 birth_month/birth_day 或 birth_date 参数")


args = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
try:
    month, day = parse_month_day(args)
    _, _, name, date_range, emoji = zodiac_of(month, day)
    print(json.dumps({
        "zodiac": name,
        "emoji": emoji,
        "date_range": date_range,
        "birth_month": month,
        "birth_day": day,
    }, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"error": str(e)}, ensure_ascii=False))
