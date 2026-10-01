#!/usr/bin/env python3
"""tracker CLI 启动器：把执行转到可写运行目录里那份 tracker.py。

命令行与实现体完全一致，调用方无需改：

    python3 assets/tracker.py list_members
    python3 assets/tracker.py period_current 2026-09-02

做三件事：

1. 播种运行目录 `<persist>/running_club_checkin_appskill/assets/`。
   `rules.py` / `tracker.py` 缺失才拷、之后永不覆盖，`schema.sql` /
   `persist_paths.py` 每轮对齐最新版。规则见 persist_paths.ensure_run_dir。
2. 把 TRACKER_DATA_DIR 定死成按**挂载**根算出来的正库。运行目录在持久盘上，
   若让实现体自己按 `__file__` 往上找，本地开发会解析出 `<运行目录>/data/...`
   这种旁路库；在这里 setdefault 一次，父子进程口径一致。
3. sys.path 让运行目录优先，`import rules` 拿到的是管理员改过的那份。

实现体是同目录的 `tracker_impl.py`（挂载上永远是最新版，只作为播种源）。
运行目录里那份落成 `tracker.py`，与线上 running_club_checkin 同名。
**改业务规则请改运行目录里的 rules.py，不要改挂载上的文件——挂载是只读的。**
"""

from __future__ import annotations

import os
import runpy
import sys

_MOUNT_ASSETS = os.path.dirname(os.path.abspath(__file__))
_MOUNT_ROOT = os.path.dirname(_MOUNT_ASSETS)

if _MOUNT_ASSETS not in sys.path:
    sys.path.insert(0, _MOUNT_ASSETS)

import persist_paths  # noqa: E402  # 挂载上的最新版，负责播种与路径解析


def main() -> int:
    persist_dir, _ = persist_paths.resolve_db_path(_MOUNT_ROOT)
    os.environ.setdefault("TRACKER_DATA_DIR", persist_dir)

    run_dir = persist_paths.ensure_run_dir(_MOUNT_ASSETS)
    target = os.path.join(run_dir, "tracker.py")
    if not os.path.isfile(target):
        # 播种失败（挂载缺 tracker_impl.py，或持久盘不可写）时退回挂载实现体，
        # 保证业务链路不因为副本机制本身而断掉。
        target = os.path.join(_MOUNT_ASSETS, "tracker_impl.py")
        run_dir = _MOUNT_ASSETS
    if not os.path.isfile(target):
        sys.stderr.write("error=tracker_impl_missing\n")
        return 2

    sys.path.insert(0, run_dir)
    sys.argv = [target] + sys.argv[1:]
    runpy.run_path(target, run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
