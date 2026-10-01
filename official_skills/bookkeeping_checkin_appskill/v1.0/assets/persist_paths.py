"""统一 bookkeeping.db 落盘路径。

沙箱里模型常直接 `python3 assets/tracker.py ...` 而漏掉
`export TRACKER_DATA_DIR=/data/user_persistent_data`。若默认落到
`{skill_root}/data/user_persistent_data`，会与 `_run.py ledger_api`
（强制正库 `/data/user_persistent_data`）分裂成两个库——记进去一条、
查出来没有。

**库文件名不能叫 tracker.db**：跑团打卡技能用的就是那个名字，两个技能在同一个
沙箱里共享 `/data/user_persistent_data/`，同名会让两套 schema 挤进同一个文件。
表名虽然不冲突（member/period/checkin vs txn），但两个技能各自的建表脚本会在
对方的库上反复执行，出问题时也分不清是谁写坏的。所以记账单独用 bookkeeping.db。

规则（与 scripts/_run.py 对齐）：
1. 显式 TRACKER_DATA_DIR 优先
2. 否则若沙箱正库目录可写 → 用它
3. 否则本地开发回退到 skill 下 data/user_persistent_data
"""

from __future__ import annotations

import os

# 与 _run.py setdefault 保持一致
SANDBOX_PERSIST_DIR = "/data/user_persistent_data"

DB_FILENAME = "bookkeeping.db"


def resolve_persist_dir(skill_root: str) -> str:
    env = os.environ.get("TRACKER_DATA_DIR")
    if env:
        return env
    if os.path.isdir(SANDBOX_PERSIST_DIR) and os.access(SANDBOX_PERSIST_DIR, os.W_OK):
        return SANDBOX_PERSIST_DIR
    return os.path.join(skill_root, "data", "user_persistent_data")


def resolve_db_path(skill_root: str) -> tuple[str, str]:
    """返回 (persist_dir, db_path)。BOOKKEEPING_DB 可单独覆盖库文件。"""
    persist = resolve_persist_dir(skill_root)
    db = os.environ.get("BOOKKEEPING_DB", os.path.join(persist, DB_FILENAME))
    return persist, db
