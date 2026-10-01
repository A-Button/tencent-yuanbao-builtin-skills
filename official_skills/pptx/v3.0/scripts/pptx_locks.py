#!/usr/bin/env python3
"""PPTX 解包树并发写锁：跨任务 / 同任务多 case 并行时保护共享文件。

锁粒度：
- slide_lock(N)：slideN.xml 与其 .rels（换图 cover、表格、版式、备注关系）
- path_lock(path)：任意独立 OOXML 部件（如 chart1.xml）
- meta_lock()：journal / [Content_Types].xml 等全局元数据

约定：需要同时持有 slide + meta 时，先 slide 再 meta，避免死锁。
"""

from __future__ import annotations

import threading
from pathlib import Path

_guard = threading.Lock()
_slide_locks: dict[int, threading.Lock] = {}
_path_locks: dict[str, threading.Lock] = {}
_meta = threading.Lock()


def slide_lock(slide: int) -> threading.Lock:
    with _guard:
        lock = _slide_locks.get(slide)
        if lock is None:
            lock = threading.Lock()
            _slide_locks[slide] = lock
        return lock


def path_lock(path: Path | str) -> threading.Lock:
    key = str(path)
    with _guard:
        lock = _path_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _path_locks[key] = lock
        return lock


def meta_lock() -> threading.Lock:
    return _meta
