#!/usr/bin/env python3
"""饮食档案的读写层：挂载卷上一餐一个 JSON 对象，本地盘上一个 SQLite 索引。

为什么不把 .db 直接放在挂载卷上跑：
    对象存储没有按字节范围写，也没有文件锁。SQLite 一调 fcntl 就报 disk I/O error，
    只能加 nolock=1 关掉；关掉之后两个进程各写各的页，落下来是页级交错，
    库结构会坏，而且写的时候不报错。

为什么也不把整个 .db 当一个对象来回同步：
    那样每次写入都在争同一个 key。两个沙箱同时开工，后推的整份盖掉先推的——
    实测同时推档十二轮丢十二轮。写之前把存档合并回来能把窗口从「整个会话」
    缩到「一次合并加一次上传」，但消不掉。

所以真相是挂载卷上的 meals/{meal_id}.json，一餐一个对象：
    meal_id 的后缀是随机的，不靠索引推算（见 new_meal_id），所以两个沙箱各记一餐
    落的是两个 key，谁也碰不到谁。只有同一条被两边同时改，才会后写的赢——这正是
    这种情况该有的语义。

    同天同餐次允许多条独立记录（同槽多卡）：午餐先记盖浇饭、后补水果，就是两张卡。
    并发撞上同一个餐次也不会再被「合并」消掉——本来就该是两条。

.db 只是派生索引，放在本地盘（DIET_WORK_DIR），全套锁和 journal 都留着，
    用来跑日期范围查询和聚合。它随时可以删掉重建，所以推送失败、
    推到一半被杀、文件损坏都不会丢数据，最多下次开工慢一点。
    挂载卷上留一份索引副本纯粹是省掉冷启动时的全量扫描。

照片不进索引，是挂载卷上的独立对象，记录里只存 photo_key。落库时就把字节拷过来
    （见 freeze_photo）：模型给的引用要么是按会话挂载的 inputs 路径、要么是有有效期的
    短链，两种都活不过这次会话，而档案是跨会话的。

软删约定：deleted_at 非空的记录仍然留着文件和行，但不参与任何查询与统计。
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

CST = timezone(timedelta(hours=8))

MEAL_TYPES = ["breakfast", "beverage", "lunch", "afternoon_tea", "dinner", "midnight"]

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

# 冻结照片时保留的扩展名。不在表里的一律按 .jpg 落盘——扩展名只影响前端按后缀
# 猜类型，猜错比拿一个可执行后缀安全，而这个名字会拼进路径。
PHOTO_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic"}

# 早期带灌种的版本给 mock 记录打的 user_id。见 _purge_seeded。
SEEDED_USER_ID = "u_demo"

SCHEMA = """
CREATE TABLE IF NOT EXISTS meals (
    meal_id      TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    eaten_at     TEXT NOT NULL,
    eaten_on     TEXT NOT NULL,
    meal_type    TEXT NOT NULL,
    title        TEXT NOT NULL,
    kcal         REAL NOT NULL DEFAULT 0,
    protein_g    REAL NOT NULL DEFAULT 0,
    fat_g        REAL NOT NULL DEFAULT 0,
    carb_g       REAL NOT NULL DEFAULT 0,
    sodium_mg    REAL NOT NULL DEFAULT 0,
    is_favorited INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    deleted_at   TEXT,
    payload      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_meals_day ON meals(eaten_on);
CREATE INDEX IF NOT EXISTS idx_meals_live ON meals(eaten_at) WHERE deleted_at IS NULL;

-- 索引里每条记录对应的那个对象的大小和 mtime，用来判断要不要重新读。
CREATE TABLE IF NOT EXISTS sources (
    meal_id  TEXT PRIMARY KEY,
    size     INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL
);
"""

# 提到列上的字段用于查询和聚合；其余整条记录序列化进 payload。
_COLUMNS = (
    "meal_id", "user_id", "eaten_at", "eaten_on", "meal_type", "title",
    "kcal", "protein_g", "fat_g", "carb_g", "sodium_mg",
    "is_favorited", "created_at", "updated_at", "deleted_at", "payload",
)

_index_dirty = False   # 本次会话改过索引，退出时值得推一份副本上去
_scanned = False       # 本进程已经跟挂载卷对过账


def data_dir() -> Path:
    """挂载卷上的档案目录。会话之间靠它保住数据。"""
    return Path(os.environ.get("DIET_DATA_DIR", "/data/user/diet-assistant"))


def work_dir() -> Path:
    """本地盘工作目录。索引在这里跑，锁和 journal 才是真的。"""
    return Path(os.environ.get("DIET_WORK_DIR", "/tmp/diet-assistant"))


def meals_dir() -> Path:
    """真相所在：一餐一个 JSON 对象。"""
    return data_dir() / MEALS_DIRNAME


def meal_file(meal_id: str) -> Path:
    return meals_dir() / f"{meal_id}.json"


def index_path() -> Path:
    return work_dir() / INDEX_NAME


def index_cache_path() -> Path:
    """挂载卷上的索引副本。丢了只是慢，不是错。"""
    return data_dir() / INDEX_NAME


def photo_dir() -> Path:
    """照片留在挂载卷上，不进索引。"""
    return data_dir() / PHOTOS_DIRNAME


def photo_path(key: str) -> Path:
    """把记录里的 photo_key 还原成挂载卷上的绝对路径。"""
    return data_dir() / key


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
    name = raw[len(prefix):] if raw.startswith(prefix) else ""
    if not name or "/" in name:
        return None
    path = Path(raw)
    return path if path.is_file() else None


def freeze_photo(meal_id: str, blob: bytes, suffix: str) -> str:
    """把一张图冻结到挂载卷上，返回记录里要存的 photo_key。

    冻结是为了让引用活过会话。用户上传的图落在按会话挂载的 inputs 下，短链也有
    自己的有效期，而档案是跨会话的——直接存那两种引用，换个会话就只剩兜底图。
    拷一份到档案自己的卷上，photo_key 在任何会话里都解得开同一张图。
    """
    if suffix.lower() not in PHOTO_SUFFIXES:
        suffix = ".jpg"
    key = f"{PHOTOS_DIRNAME}/{meal_id}{suffix.lower()}"
    _atomic_write_bytes(photo_path(key), blob)
    return key


# ---------------------------------------------------------------- 落对象

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


def _write_meal_object(meal: dict) -> os.stat_result:
    return _atomic_write(meal_file(meal["meal_id"]), json.dumps(meal, ensure_ascii=False))


# ---------------------------------------------------------------- 索引同步

def _open_index() -> sqlite3.Connection:
    """打开本地索引。副本能用就先拉下来省掉全量扫描，不能用就从零重建。"""
    local, cached = index_path(), index_cache_path()
    local.parent.mkdir(parents=True, exist_ok=True)
    if not local.is_file() and cached.is_file():
        try:
            shutil.copyfile(cached, local)
        except OSError:
            pass
    for attempt in (1, 2):
        conn = sqlite3.connect(local, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            # 本地盘支持文件锁，所以这里不关任何安全机制。
            # DELETE 而非 WAL：干净关闭后只剩一个文件，拷贝副本时一次 cp 就够。
            conn.execute("PRAGMA journal_mode = DELETE")
            conn.execute("PRAGMA synchronous = FULL")
            conn.executescript(SCHEMA)
            return conn
        except sqlite3.DatabaseError:
            conn.close()
            if attempt == 2:
                raise
            local.unlink(missing_ok=True)  # 副本是坏的，扔掉重建
    raise AssertionError("unreachable")


def _scan_objects(conn: sqlite3.Connection) -> tuple[int, int]:
    """拿挂载卷上的对象对一遍索引，返回（重读条数，剔除条数）。

    只比 size 和 mtime，没变的不读。一年一千条记录也就是一次 listdir，
    真正的读只发生在别的沙箱确实改过东西的时候。
    """
    root = meals_dir()
    if not root.is_dir():
        return 0, 0
    known = {r["meal_id"]: (r["size"], r["mtime_ns"])
             for r in conn.execute("SELECT meal_id, size, mtime_ns FROM sources")}
    seen, reloaded = set(), 0
    for path in root.glob("*.json"):
        meal_id = path.stem
        seen.add(meal_id)
        try:
            st = path.stat()
        except OSError:
            continue
        if known.get(meal_id) == (st.st_size, st.st_mtime_ns):
            continue
        try:
            meal = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue  # 单个对象坏了就跳过，不能让整个档案读不出来
        if not isinstance(meal, dict) or meal.get("meal_id") != meal_id:
            continue
        if meal.get("user_id") == SEEDED_USER_ID:
            path.unlink(missing_ok=True)
            seen.discard(meal_id)  # 不留在 seen 里，下面会把索引行一并删掉
            continue
        _upsert(conn, meal)
        _remember(conn, meal_id, st)
        reloaded += 1
    dropped = set(known) - seen
    for meal_id in dropped:
        conn.execute("DELETE FROM meals WHERE meal_id = ?", (meal_id,))
        conn.execute("DELETE FROM sources WHERE meal_id = ?", (meal_id,))
    purged = _purge_seeded(conn)
    _sweep_staging(root)
    return reloaded, len(dropped) + purged


def _purge_seeded(conn: sqlite3.Connection) -> int:
    """清掉早期版本灌进来的演示记录，索引行和对象一起删。

    有一版带 `ensure_seeded()` 的包跑过之后，把 mock 落成了真对象留在卷上。
    灌种写的 user_id 是 u_demo，而现在的写入路径只会写 u_local 或调用方传的
    真实 userId，所以拿这个标记来筛不会碰到用户自己记的餐。

    上面的扫描循环只读 size/mtime 变过的对象，没变的那些漏不到；这里补一遍
    按索引删，两条路合起来才覆盖得全。
    """
    ids = [r["meal_id"] for r in
           conn.execute("SELECT meal_id FROM meals WHERE user_id = ?", (SEEDED_USER_ID,))]
    for meal_id in ids:
        meal_file(meal_id).unlink(missing_ok=True)
        conn.execute("DELETE FROM meals WHERE meal_id = ?", (meal_id,))
        conn.execute("DELETE FROM sources WHERE meal_id = ?", (meal_id,))
    return len(ids)


def _sweep_staging(root: Path) -> None:
    """清掉写到一半被杀留下的临时文件。留一小时是为了不误删别的沙箱正在写的。

    照片目录一起扫：一张图几百 KB，攒下来比一条废记录占地方。
    """
    cutoff = time.time() - 3600
    for directory in (root, photo_dir()):
        if not directory.is_dir():
            continue
        for path in directory.glob(".*.tmp"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
            except OSError:
                pass


def _remember(conn: sqlite3.Connection, meal_id: str, st: os.stat_result) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO sources (meal_id, size, mtime_ns) VALUES (?, ?, ?)",
        (meal_id, st.st_size, st.st_mtime_ns),
    )


def publish() -> bool:
    """把索引副本推回挂载卷。纯缓存，失败了不影响正确性。"""
    global _index_dirty
    if not _index_dirty:
        return False
    local = index_path()
    if not local.is_file():
        return False
    try:
        _atomic_write_binary(index_cache_path(), local)
    except OSError:
        return False
    _index_dirty = False
    return True


def _atomic_write_binary(dst: Path, src: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    staging = dst.parent / f".{dst.name}.{os.getpid()}.tmp"
    try:
        shutil.copyfile(src, staging)
        os.replace(staging, dst)
    except OSError:
        staging.unlink(missing_ok=True)
        raise


@contextmanager
def _db(write: bool = False):
    global _index_dirty, _scanned
    conn = _open_index()
    try:
        if not _scanned:
            _scanned = True
            reloaded, dropped = _scan_objects(conn)
            conn.commit()
            # 只在对账真的改动了索引时才值得重传。纯读的会话对不出差异，
            # 无条件标脏的话每次打开卡片都要把整个索引再推一遍。
            if reloaded or dropped:
                _index_dirty = True
        yield conn
        if write:
            conn.commit()
            _index_dirty = True
    finally:
        conn.close()


# ---------------------------------------------------------------- 行 <-> 记录

def _to_row(meal: dict) -> tuple:
    totals = meal.get("totals") or {}
    return (
        meal.get("meal_id"),
        meal.get("user_id") or "",
        meal.get("eaten_at") or "",
        str(meal.get("eaten_at") or "")[:10],
        meal.get("meal_type") or "midnight",
        meal.get("title") or "",
        float(totals.get("kcal") or 0),
        float(totals.get("protein_g") or 0),
        float(totals.get("fat_g") or 0),
        float(totals.get("carb_g") or 0),
        float(totals.get("sodium_mg") or 0),
        1 if meal.get("is_favorited") else 0,
        meal.get("created_at") or "",
        meal.get("updated_at") or "",
        meal.get("deleted_at"),
        json.dumps(meal, ensure_ascii=False),
    )


def _to_meal(row: sqlite3.Row) -> dict | None:
    try:
        meal = json.loads(row["payload"])
    except json.JSONDecodeError:
        return None  # 坏行跳过，不能因为一条脏数据让整个档案读不出来
    return meal if isinstance(meal, dict) else None


def _upsert(conn: sqlite3.Connection, meal: dict) -> None:
    placeholders = ", ".join("?" * len(_COLUMNS))
    conn.execute(
        f"INSERT OR REPLACE INTO meals ({', '.join(_COLUMNS)}) VALUES ({placeholders})",
        _to_row(meal),
    )


# ---------------------------------------------------------------- 时间

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


# ---------------------------------------------------------------- 查询

def load_meals(include_deleted: bool = False) -> list[dict]:
    where = "" if include_deleted else " WHERE deleted_at IS NULL"
    with _db() as conn:
        rows = conn.execute(f"SELECT payload FROM meals{where} ORDER BY eaten_at").fetchall()
    return [m for m in (_to_meal(r) for r in rows) if m is not None]


def load_meals_between(start_date: str, end_date: str) -> list[dict]:
    """按日历日闭区间取未删记录。统计只需要窗口内的数据，不必整表拉出来。"""
    with _db() as conn:
        rows = conn.execute(
            "SELECT payload FROM meals WHERE deleted_at IS NULL"
            " AND eaten_on BETWEEN ? AND ? ORDER BY eaten_at",
            (start_date, end_date),
        ).fetchall()
    return [m for m in (_to_meal(r) for r in rows) if m is not None]


def day_kcal(start_date: str, end_date: str) -> dict[str, float]:
    """窗口内每天的热量合计，直接走 SQL 聚合。"""
    with _db() as conn:
        rows = conn.execute(
            "SELECT eaten_on, SUM(kcal) AS kcal FROM meals WHERE deleted_at IS NULL"
            " AND eaten_on BETWEEN ? AND ? GROUP BY eaten_on",
            (start_date, end_date),
        ).fetchall()
    return {r["eaten_on"]: r["kcal"] or 0.0 for r in rows}


def find_meal(meal_id: str, include_deleted: bool = False) -> dict | None:
    clause = "" if include_deleted else " AND deleted_at IS NULL"
    with _db() as conn:
        row = conn.execute(
            f"SELECT payload FROM meals WHERE meal_id = ?{clause}", (meal_id,)
        ).fetchone()
    return _to_meal(row) if row else None


def find_open_meal(date_str: str, meal_type: str) -> dict | None:
    """同天同餐次最早的一条未删记录。

    同槽已改为多卡（每次 record 新建），落库路径不再调用本函数。
    仍保留给排查 / 旧测读用。
    """
    with _db() as conn:
        row = conn.execute(
            "SELECT payload FROM meals WHERE deleted_at IS NULL AND eaten_on = ?"
            " AND meal_type = ? ORDER BY eaten_at LIMIT 1",
            (date_str, meal_type),
        ).fetchone()
    return _to_meal(row) if row else None


# ---------------------------------------------------------------- 写入

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


def append_meal(meal: dict) -> None:
    """先落对象再更索引。反过来的话进程中途挂掉会留下一条查得到、读不出的记录。"""
    st = _write_meal_object(meal)
    with _db(write=True) as conn:
        _upsert(conn, meal)
        _remember(conn, meal["meal_id"], st)


def replace_meal(meal_id: str, updated: dict) -> bool:
    """整条替换。找不到 meal_id 返回 False，不新建。"""
    with _db() as conn:
        exists = conn.execute("SELECT 1 FROM meals WHERE meal_id = ?", (meal_id,)).fetchone()
    if not exists:
        return False
    new_id = updated.get("meal_id")
    st = _write_meal_object(updated)
    if new_id != meal_id:
        # 换 id 相当于改名，旧对象没有保留价值；软删走的是同 id 写 deleted_at。
        meal_file(meal_id).unlink(missing_ok=True)
    with _db(write=True) as conn:
        if new_id != meal_id:
            conn.execute("DELETE FROM meals WHERE meal_id = ?", (meal_id,))
            conn.execute("DELETE FROM sources WHERE meal_id = ?", (meal_id,))
        _upsert(conn, updated)
        _remember(conn, new_id, st)
    return True
