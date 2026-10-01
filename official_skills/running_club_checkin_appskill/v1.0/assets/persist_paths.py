"""统一落盘路径：tracker.db 正库 + 可写运行目录（rules.py / tracker.py 冻结处）。

## tracker.db

沙箱里模型常直接 `python3 assets/tracker.py ...` 而漏掉
`export TRACKER_DATA_DIR=/data/user_persistent_data`。若默认落到
`{skill_root}/data/user_persistent_data`，会与 `_run.py ledger_api`
（强制正库 `/data/user_persistent_data`）分裂成两个库——建档成功、占槽
member_not_found。

规则（与 scripts/_run.py 对齐）：
1. 显式 TRACKER_DATA_DIR 优先
2. 否则若沙箱正库目录可写 → 用它
3. 否则本地开发回退到 skill 下 data/user_persistent_data

## 运行目录

skill 装在只读挂载 `/data/skills/{slug}/`，管理员改不了那里的业务规则。所以
业务规则代码在可写盘留一份「运行目录」，tracker 从那份跑：

    <persist_dir>/running_club_checkin_appskill/assets/

`rules.py` / `tracker.py` **只在缺失时**从挂载拷进去，之后永不覆盖——管理员在群里
说「达标线改成 15 公里」，改的是运行目录那份，技能包再发新版也不会把它冲掉。
`schema.sql` / `persist_paths.py` 反过来**每轮对齐挂载最新版**：建表语句只向后加字段，
冻住反而挡住新字段；路径解析属于基础设施，冻住会让老群永远拿不到修复。

这与线上 running_club_checkin 的 `cp -rn` 是同一思路，区别是拷贝在 Python 里做
（模型不必执行 mkdir/cp，省一轮工具调用），且只冻这两个文件。
"""

from __future__ import annotations

import os
import shutil
import tempfile

# 与 _run.py setdefault 保持一致
SANDBOX_PERSIST_DIR = "/data/user_persistent_data"

# 运行目录名。与 skill 目录同名，便于在对象存储里一眼对上是哪个 skill 的副本；
# 刻意不与线上 running_club_checkin 的目录共用，避免两套 tracker.py 互相顶替。
RUN_DIR_NAME = "running_club_checkin_appskill"

# 首次拷入后永不覆盖：这两个文件是管理员可改的业务规则层。
FROZEN_FILES = ("rules.py", "tracker.py")

# 每轮对齐挂载最新版。
LATEST_FILES = ("schema.sql", "persist_paths.py")

# 挂载上真实实现的文件名 -> 运行目录里的文件名。
# 挂载的 assets/tracker.py 是启动器（负责播种再转发），实现体叫 tracker_impl.py；
# 运行目录里落成 tracker.py，与线上同名，管理员找文件时不用换脑子。
FROZEN_SOURCE_NAMES = {"tracker.py": "tracker_impl.py"}


def resolve_persist_dir(skill_root: str) -> str:
    env = os.environ.get("TRACKER_DATA_DIR")
    if env:
        return env
    if os.path.isdir(SANDBOX_PERSIST_DIR) and os.access(SANDBOX_PERSIST_DIR, os.W_OK):
        return SANDBOX_PERSIST_DIR
    return os.path.join(skill_root, "data", "user_persistent_data")


def resolve_db_path(skill_root: str) -> tuple[str, str]:
    """返回 (persist_dir, db_path)。TRACKER_DB 可单独覆盖库文件。"""
    persist = resolve_persist_dir(skill_root)
    db = os.environ.get("TRACKER_DB", os.path.join(persist, "tracker.db"))
    return persist, db


def resolve_run_dir(mount_assets_dir: str) -> str:
    """运行目录路径（不建目录、不拷文件）。TRACKER_RUN_DIR 可整体覆盖，供测试用。"""
    env = os.environ.get("TRACKER_RUN_DIR")
    if env:
        return env
    skill_root = os.path.dirname(os.path.abspath(mount_assets_dir))
    persist = resolve_persist_dir(skill_root)
    return os.path.join(persist, RUN_DIR_NAME, "assets")


def _copy_atomic(src: str, dst: str) -> None:
    """先写同目录临时文件再 os.replace，避免并发进程读到写了一半的模块。"""
    dst_dir = os.path.dirname(dst)
    fd, tmp = tempfile.mkstemp(dir=dst_dir, prefix=".tmp-", suffix=".py")
    os.close(fd)
    try:
        shutil.copyfile(src, tmp)
        os.replace(tmp, dst)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _same_bytes(a: str, b: str) -> bool:
    try:
        with open(a, "rb") as fa, open(b, "rb") as fb:
            return fa.read() == fb.read()
    except OSError:
        return False


def ensure_run_dir(mount_assets_dir: str) -> str:
    """播种/对齐运行目录，返回其路径。幂等，每次 tracker 调用都可以跑。

    挂载缺文件时静默跳过：本地开发和裁剪过的包都可能只有一部分文件，
    这里不该因为缺 schema.sql 就让整条业务链路失败。
    """
    mount = os.path.abspath(mount_assets_dir)
    run = resolve_run_dir(mount)
    if os.path.abspath(run) == mount:      # 挂载本身可写（本地开发）：无须副本
        return mount
    os.makedirs(run, exist_ok=True)

    for name in FROZEN_FILES:
        dst = os.path.join(run, name)
        if os.path.exists(dst):
            continue
        src = os.path.join(mount, FROZEN_SOURCE_NAMES.get(name, name))
        if os.path.isfile(src):
            _copy_atomic(src, dst)

    for name in LATEST_FILES:
        src = os.path.join(mount, name)
        dst = os.path.join(run, name)
        if os.path.isfile(src) and not _same_bytes(src, dst):
            _copy_atomic(src, dst)

    return run
