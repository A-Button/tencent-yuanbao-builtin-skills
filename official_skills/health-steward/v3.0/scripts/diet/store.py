#!/usr/bin/env python3
"""饮食档案的读写层：挂载卷上一餐一个 JSON 对象，按用餐日分目录。

为什么不把 .db 直接放在挂载卷上跑：
    对象存储没有按字节范围写，也没有文件锁。SQLite 一调 fcntl 就报 disk I/O error，
    只能加 nolock=1 关掉；关掉之后两个进程各写各的页，落下来是页级交错，
    库结构会坏，而且写的时候不报错。

为什么也不把整个 .db 当一个对象来回同步：
    那样每次写入都在争同一个 key。两个沙箱同时开工，后推的整份盖掉先推的——
    实测同时推档十二轮丢十二轮。写之前把存档合并回来能把窗口从「整个会话」
    缩到「一次合并加一次上传」，但消不掉。

所以真相是挂载卷上的 meals/{日期}/{meal_id}.json，一餐一个对象：
    meal_id 的后缀是随机的，不靠索引推算（见 new_meal_id），所以两个沙箱各记一餐
    落的是两个 key，谁也碰不到谁。只有同一条被两边同时改，才会后写的赢——这正是
    这种情况该有的语义。日期写在路径里，查一天就是打开那一个前缀，不必把整本档案读上来。

    同天同餐次允许多条独立记录（同槽多卡）：午餐先记盖浇饭、后补水果，就是两张卡。
    并发撞上同一个餐次也不会再被「合并」消掉——本来就该是两条。

新写入只进 /data/user/diet-assistant。更早的平铺 meals/m_{日期}_*.json，以及健康管家
    旧目录 diet-assistant-in-health-steward，只在新路径没有这份对象时才读，不复制。

照片是挂载卷上的独立对象，记录里只存 photo_key。落库时就把字节拷过来
    （见 freeze_photo）：模型给的引用要么是按会话挂载的 inputs 路径、要么是有有效期的
    短链，两种都活不过这次会话，而档案是跨会话的。换图写一个新文件名，旧文件留着。

软删约定：deleted_at 非空的记录仍然留着文件和行，但不参与任何查询与统计。
"""

from __future__ import annotations

import json
import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath, Path

CST = timezone(timedelta(hours=8))

MEAL_TYPES = ["breakfast", "beverage", "lunch", "afternoon_tea", "dinner", "midnight"]
# 花名册只有早/午/晚三行，「不吃了」只允许标这三槽，不进热量合计。
SKIP_SLOTS = ("breakfast", "lunch", "dinner")

# 餐次的中文名只在这里定义，全站一个写法。以前 diet_api / a2ui / nutrition 各抄了一份，
# 加一个餐次要改四处，漏一处就是卡片上某个角落显示成英文 key。
# 统计图表曾另有一张单字缩写表（早/午/晚），已删：省那两个字换来的是同一个餐次
# 在卡片上叫「午餐」、在图表里叫「午」，两处对不上。
MEAL_LABEL = {
    "breakfast": "早餐", "beverage": "饮品", "lunch": "午餐",
    "afternoon_tea": "下午茶", "dinner": "晚餐", "midnight": "夜宵",
}
# 时间窗派生餐次。饮品单独判定，不走时间窗（见 derive_meal_type）。
_TIME_WINDOWS = [
    (5 * 60, 11 * 60, "breakfast"),
    (11 * 60, 14 * 60 + 30, "lunch"),
    (14 * 60 + 30, 17 * 60, "afternoon_tea"),
    (17 * 60, 21 * 60, "dinner"),
]

INDEX_NAME = "diet.db"
MEALS_DIRNAME = "meals"
PHOTOS_DIRNAME = "photos"
SKIPS_DIRNAME = "skips"

# 冻结照片时保留的扩展名。不在表里的一律按 .jpg 落盘——扩展名只影响前端按后缀
# 猜类型，猜错比拿一个可执行后缀安全，而这个名字会拼进路径。
PHOTO_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic"}

# 早期带灌种的版本给 mock 记录打的 user_id。见 _purge_seeded。
SEEDED_USER_ID = "u_demo"

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_MEAL_ID_DATE = re.compile(r"^m_(\d{4}-\d{2}-\d{2})_")

# 两个技能的新写入都进同一棵目录。健康管家旧目录只读，不复制。
_CANONICAL_ROOT = Path("/data/user/diet-assistant")
_LEGACY_HS_ROOT = Path("/data/user/diet-assistant-in-health-steward")

# 并发测试还会给这两个赋值。索引已经不在挂载卷上同步，留下来只是别让旧用例踩空。
_index_dirty = False
_scanned = False


def data_dir() -> Path:
    """挂载卷上的档案目录。会话之间靠它保住数据。新写入只进这里。"""
    return Path(os.environ.get("DIET_DATA_DIR", "/data/user/diet-assistant"))


def work_dir() -> Path:
    """本地盘工作目录。饮食档案不再在这里放索引，路径仍留给调用方区分两个技能。"""
    return Path(os.environ.get("DIET_WORK_DIR", "/tmp/diet-assistant-in-health-steward"))


def meals_dir() -> Path:
    """真相所在：一餐一个 JSON 对象，按用餐日分目录。"""
    return data_dir() / MEALS_DIRNAME


def skips_dir() -> Path:
    """某日跳过的餐次。不是一餐记录，不进热量合计。"""
    return data_dir() / SKIPS_DIRNAME


def skip_file(date_str: str) -> Path:
    return skips_dir() / f"{date_str}.json"


def archive_roots() -> list[Path]:
    """读的顺序：当前档案目录，然后才是另外一棵旧目录。

    测试把 DIET_DATA_DIR 指到临时目录时，不去碰机器上的 /data/user，
    除非显式给了 DIET_LEGACY_DIRS。线上默认目录才会带上另一棵旧根。
    """
    primary = data_dir()
    roots = [primary]
    raw = os.environ.get("DIET_LEGACY_DIRS", "")
    if raw:
        for part in raw.split(os.pathsep):
            if not part:
                continue
            path = Path(part)
            if path not in roots:
                roots.append(path)
        return roots
    if primary in (_CANONICAL_ROOT, _LEGACY_HS_ROOT):
        for extra in (_CANONICAL_ROOT, _LEGACY_HS_ROOT):
            if extra not in roots:
                roots.append(extra)
    return roots


def _date_of_meal_id(meal_id: str) -> str | None:
    matched = _MEAL_ID_DATE.match(meal_id or "")
    return matched.group(1) if matched else None


def _eaten_day(meal: dict) -> str | None:
    raw = str(meal.get("eaten_on") or meal.get("eaten_at") or "")[:10]
    return raw if _DATE_RE.fullmatch(raw) else None


def meal_file(meal_id: str, day: str | None = None) -> Path:
    """新对象的路径。日期优先取 id 里嵌的那一段，没有再用来路参数。"""
    found = day or _date_of_meal_id(meal_id) or "undated"
    return meals_dir() / found / f"{meal_id}.json"


def index_path() -> Path:
    return work_dir() / INDEX_NAME


def index_cache_path() -> Path:
    """旧的索引副本。查询不再读它。"""
    return data_dir() / INDEX_NAME


def photo_dir() -> Path:
    """照片留在挂载卷上，按用餐日分目录。"""
    return data_dir() / PHOTOS_DIRNAME


def photo_path(key: str) -> Path:
    """把记录里的 photo_key 还原成当前档案目录下的绝对路径。"""
    return data_dir() / key


def resolve_photo(key: object, root: Path | str | None = None) -> Path | None:
    """打开 photo_key。知道这份 JSON 从哪棵根读出来，就只在那棵根下打开。

    相对 key 只允许 photos/ 开头。没带来路时才按档案根的顺序找第一份存在的文件。
    """
    raw = key.strip() if isinstance(key, str) else ""
    if not raw or raw.startswith("/") or "\\" in raw:
        return None
    parts = PurePosixPath(raw).parts
    if not parts or ".." in parts or parts[0] != PHOTOS_DIRNAME:
        return None
    roots = [Path(root)] if root else archive_roots()
    for item in roots:
        path = Path(item).joinpath(*parts)
        if path.is_file():
            return path
    return None


def sandbox_inputs_dir() -> str:
    """用户上传图在沙箱里的挂载点，末尾保证带斜杠。

    VLM 链路的 prompt 给模型的就是这底下的路径（`[user_image_path]`）。它按会话挂载，
    换一次会话就解不开了——所以落库时要 freeze_photo 拷走，不能直接存进档案。
    """
    raw = os.environ.get("DIET_INPUTS_DIR", "/data/inputs/")
    return raw if raw.endswith("/") else raw + "/"


def inputs_photo(raw: str) -> Path | None:
    """把模型给的沙箱路径收敛成 inputs 下确实存在的那个文件，拿不准返回 None。

    只放行 inputs 下的裸文件名，且文件真在：
      * 带分隔符的会跑出 inputs（`../outputs/x.png`），而 outputs 是沙箱可写的，
        放过去等于让宿主替沙箱产物签名；
      * 存在性检查是唯一能挡住模型编出来的路径的地方，也只有跑在沙箱里的脚本
        做得到——宿主拿到的只是个字符串，真假看不出来。
    """
    prefix = sandbox_inputs_dir()
    name = raw[len(prefix):] if isinstance(raw, str) and raw.startswith(prefix) else ""
    if not name or "/" in name:
        return None
    path = Path(raw)
    return path if path.is_file() else None


def freeze_photo(meal_id: str, blob: bytes, suffix: str) -> str:
    """把一张图冻结到挂载卷上，返回记录里要存的 photo_key。

    每次冻结都换一个新文件名。宿主按整条沙箱路径做对象键，同一路径再次签名
    不会重拷字节，换图必须换名。旧文件留在原地。
    """
    if suffix.lower() not in PHOTO_SUFFIXES:
        suffix = ".jpg"
    else:
        suffix = suffix.lower()
    day = _date_of_meal_id(meal_id) or now().strftime("%Y-%m-%d")
    key = f"{PHOTOS_DIRNAME}/{day}/{meal_id}_{secrets.token_hex(4)}{suffix}"
    dest = data_dir() / key
    _atomic_write_bytes(dest, blob)
    _sweep_staging(dest.parent)
    return key


def _atomic_write(dst: Path, text: str) -> os.stat_result:
    return _atomic_write_bytes(dst, text.encode("utf-8"))


def _atomic_write_bytes(dst: Path, blob: bytes) -> os.stat_result:
    """写临时文件再改名。带 pid 是因为两个进程可能同时写同一条记录，
    共用一个临时名的话，一方改名之后另一方会对着消失的路径 os.replace。"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    staging = dst.parent / f".{dst.name}.{os.getpid()}.tmp"
    try:
        staging.write_bytes(blob)
        os.replace(staging, dst)
    except OSError:
        staging.unlink(missing_ok=True)
        raise
    return dst.stat()


def _write_meal_object(meal: dict) -> Path:
    day = _date_of_meal_id(str(meal.get("meal_id") or "")) or _eaten_day(meal)
    dest = meal_file(str(meal.get("meal_id") or ""), day)
    stored = {key: value for key, value in meal.items() if not str(key).startswith("_")}
    _atomic_write(dest, json.dumps(stored, ensure_ascii=False))
    _sweep_staging(dest.parent)
    if day:
        _sweep_staging(photo_dir() / day)
    return dest


def _sweep_staging(root: Path) -> None:
    """清掉写到一半被杀留下的临时文件。留一小时是为了不误删别的沙箱正在写的。"""
    if not root.is_dir():
        return
    cutoff = time.time() - 3600
    for path in root.glob(".*.tmp"):
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            pass


def publish() -> bool:
    """索引副本已不再使用。留下这个函数是因为入口和并发测试还会调用它。"""
    return False


def _read_meal(path: Path, root: Path) -> dict | None:
    try:
        meal = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(meal, dict):
        return None
    if meal.get("user_id") == SEEDED_USER_ID:
        path.unlink(missing_ok=True)
        return None
    meal["_archive_root"] = str(root)
    return meal


def _day_paths(root: Path, date_str: str):
    """一天的对象：先日期目录，再旧的平铺文件。不列别的日子。"""
    meals = root / MEALS_DIRNAME
    dated = meals / date_str
    if dated.is_dir():
        for path in sorted(dated.glob("*.json")):
            if path.is_file() and not path.name.startswith("."):
                yield path
    if meals.is_dir():
        for path in sorted(meals.glob(f"m_{date_str}_*.json")):
            if path.is_file():
                yield path


def _collect_day(date_str: str, meals: list[dict], seen: set[str], include_deleted: bool) -> None:
    for root in archive_roots():
        for path in _day_paths(root, date_str):
            meal = _read_meal(path, root)
            if meal is None:
                continue
            meal_id = str(meal.get("meal_id") or path.stem)
            if meal_id in seen:
                continue
            seen.add(meal_id)
            if not include_deleted and meal.get("deleted_at"):
                continue
            meals.append(meal)


def _dates_inclusive(start_date: str, end_date: str) -> list[str]:
    try:
        cursor = datetime.strptime(start_date, "%Y-%m-%d").date()
        last = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        return []
    days = []
    while cursor <= last:
        days.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return days


def _known_days() -> list[str]:
    days: set[str] = set()
    for root in archive_roots():
        meals = root / MEALS_DIRNAME
        if not meals.is_dir():
            continue
        for child in meals.iterdir():
            if child.name.startswith("."):
                continue
            if child.is_dir() and _DATE_RE.fullmatch(child.name):
                days.add(child.name)
            elif child.is_file():
                found = _date_of_meal_id(child.stem)
                if found:
                    days.add(found)
    return sorted(days)


def _root_of(path: Path) -> Path:
    """从一餐文件往上找到 meals/ 的上一层，也就是这份 JSON 所在的档案根。"""
    current = path.parent
    while current.name != MEALS_DIRNAME and current.parent != current:
        current = current.parent
    return current.parent


def _locate_path(meal_id: str) -> Path | None:
    """按 id 直接 stat。有日期的 id 不列目录。"""
    day = _date_of_meal_id(meal_id)
    for root in archive_roots():
        meals = root / MEALS_DIRNAME
        candidates = []
        if day:
            candidates.append(meals / day / f"{meal_id}.json")
        candidates.append(meals / f"{meal_id}.json")
        for path in candidates:
            if path.is_file():
                return path
    if day:
        return None
    for root in archive_roots():
        meals = root / MEALS_DIRNAME
        if not meals.is_dir():
            continue
        for child in meals.iterdir():
            if not child.is_dir() or child.name.startswith("."):
                continue
            path = child / f"{meal_id}.json"
            if path.is_file():
                return path
    return None


def now() -> datetime:
    return datetime.now(CST)


def now_iso() -> str:
    return now().replace(microsecond=0).isoformat()


def parse_time(value: str) -> datetime:
    """解析 eaten_at。缺时区的按东八区补齐，解析不了的抛 ValueError。"""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.replace(tzinfo=CST) if dt.tzinfo is None else dt.astimezone(CST)


def derive_meal_type(eaten_at: datetime, beverage_only: bool = False) -> str:
    """纯饮品直接归 beverage，不并入任何一餐；其余按时间窗。"""
    if beverage_only:
        return "beverage"
    minutes = eaten_at.hour * 60 + eaten_at.minute
    for start, end, name in _TIME_WINDOWS:
        if start <= minutes < end:
            return name
    return "midnight"


def load_meals(include_deleted: bool = False) -> list[dict]:
    meals: list[dict] = []
    seen: set[str] = set()
    for day in _known_days():
        _collect_day(day, meals, seen, include_deleted)
    meals.sort(key=lambda meal: meal.get("eaten_at") or "")
    return meals


def load_meals_between(start_date: str, end_date: str) -> list[dict]:
    """按日历日闭区间取未删记录。只打开这个窗口里的日期前缀。"""
    meals: list[dict] = []
    seen: set[str] = set()
    for day in _dates_inclusive(start_date, end_date):
        _collect_day(day, meals, seen, include_deleted=False)
    meals.sort(key=lambda meal: meal.get("eaten_at") or "")
    return meals


def day_kcal(start_date: str, end_date: str) -> dict[str, float]:
    """窗口内每天的热量合计。"""
    totals: dict[str, float] = {}
    for meal in load_meals_between(start_date, end_date):
        day = str(meal.get("eaten_at") or "")[:10]
        kcal = float((meal.get("totals") or {}).get("kcal") or 0)
        totals[day] = totals.get(day, 0.0) + kcal
    return totals


def find_meal(meal_id: str, include_deleted: bool = False) -> dict | None:
    day = _date_of_meal_id(meal_id)
    if day:
        meals: list[dict] = []
        _collect_day(day, meals, set(), include_deleted=True)
        for meal in meals:
            if meal.get("meal_id") != meal_id:
                continue
            if not include_deleted and meal.get("deleted_at"):
                return None
            return meal
        return None
    path = _locate_path(meal_id)
    if path is None:
        return None
    meal = _read_meal(path, _root_of(path))
    if meal is None:
        return None
    if not include_deleted and meal.get("deleted_at"):
        return None
    return meal


def find_open_meal(date_str: str, meal_type: str) -> dict | None:
    """同天同餐次最早的一条未删记录。

    同槽已改为多卡（每次 record 新建），落库路径不再调用本函数。
    仍保留给排查 / 旧测读用。
    """
    found = [
        meal for meal in load_meals_between(date_str, date_str)
        if meal.get("meal_type") == meal_type
    ]
    return found[0] if found else None


def new_meal_id(date_str: str, meal_type: str) -> str:
    """给新的一餐分配 id。后缀是随机的，不是序号。

    序号得先知道「这个前缀底下已经有哪些」，而唯一问得到的是本地索引。别的沙箱
    刚落下的对象还没扫到，两边就会各自算出同一个序号，往同一个 key 上写，
    后写的静默盖掉先写的——两顿不同的餐丢一顿，还不报错。

    随机后缀不用问任何人，也不要求挂载层提供任何原子性：O_EXCL 那种「撞了就加一」
    的写法依赖文件系统原子地检查存在再创建，而对象存储上它被拆成 HEAD 再 PUT，
    两步之间的窗口跟这里要解决的正是同一个窗口。

    十六进制八位（约 43 亿）：短到能跟在正文回执后面让用户指认某一条。撞上只在同一个
    date + meal_type 前缀底下才算撞。同槽多卡后同一前缀下条数会比以前多，
    按生日界 n²/2N 算，哪怕堆到五十条也是 1e-7 量级。
    余量留够是因为撞了的后果正是这个函数要消掉的那个：静默覆盖，不报错。
    """
    return f"m_{date_str}_{meal_type}_{secrets.token_hex(4)}"


def _parse_slots(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    raw = data.get("slots") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return []
    found = {item for item in raw if item in SKIP_SLOTS}
    return [slot for slot in SKIP_SLOTS if slot in found]


def _skip_paths(date_str: str) -> list[Path]:
    return [root / SKIPS_DIRNAME / f"{date_str}.json" for root in archive_roots()]


def skipped_slots(date_str: str) -> list[str]:
    """当天被标成跳过的餐次，按 SKIP_SLOTS 顺序。新文件在就不再读旧文件。"""
    for path in _skip_paths(date_str):
        if path.is_file():
            return _parse_slots(path)
    return []


def _write_skip(date_str: str, ordered: list[str]) -> None:
    """跳过标记只写当前档案目录。空了仍留一份空名单，避免回退把旧跳过又读出来。"""
    path = skip_file(date_str)
    legacy = [item for item in _skip_paths(date_str) if item != path and item.is_file()]
    if not ordered and not legacy and not path.is_file():
        return
    if not ordered and not legacy:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"slots": ordered}, ensure_ascii=False), encoding="utf-8")


def mark_skip(date_str: str, meal_type: str) -> list[str]:
    """把某一餐次标成跳过。已跳过再标一次仍成功。"""
    if meal_type not in SKIP_SLOTS:
        raise ValueError(f"只能跳过早/午/晚：{meal_type}")
    slots = set(skipped_slots(date_str))
    slots.add(meal_type)
    ordered = [slot for slot in SKIP_SLOTS if slot in slots]
    _write_skip(date_str, ordered)
    return ordered


def clear_skip(date_str: str, meal_type: str) -> None:
    """真的记了一餐，跳过标记就失效。新旧两份文件都清掉这一槽。"""
    ordered = [slot for slot in skipped_slots(date_str) if slot != meal_type]
    _write_skip(date_str, ordered)
    for path in _skip_paths(date_str):
        if path == skip_file(date_str) or not path.is_file():
            continue
        remaining = [slot for slot in _parse_slots(path) if slot != meal_type]
        if remaining:
            path.write_text(json.dumps({"slots": remaining}, ensure_ascii=False), encoding="utf-8")
        else:
            path.unlink(missing_ok=True)


def append_meal(meal: dict) -> None:
    """先落对象。查得到的就是文件本身，不再维护一份会落后的索引。"""
    _write_meal_object(meal)
    eaten_on = str(meal.get("eaten_on") or meal.get("eaten_at") or "")[:10]
    meal_type = meal.get("meal_type")
    if eaten_on and meal_type in SKIP_SLOTS:
        clear_skip(eaten_on, meal_type)


def replace_meal(meal_id: str, updated: dict) -> bool:
    """整条替换。找不到 meal_id 返回 False，不新建。

    同一条记录改到新路径时，旧文件留着。读的时候新路径优先。
    换了 meal_id 才删旧对象，否则新旧两个 id 会同时出现在同一天里。
    """
    previous = _locate_path(meal_id)
    if previous is None:
        return False
    _write_meal_object(updated)
    new_id = updated.get("meal_id")
    if new_id != meal_id:
        previous.unlink(missing_ok=True)
    return True
