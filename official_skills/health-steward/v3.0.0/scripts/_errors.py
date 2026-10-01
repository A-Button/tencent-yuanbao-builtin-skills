#!/usr/bin/env python3
"""业务拒绝的异常类型。零依赖的叶子模块，谁都能引、它谁也不引。

运动和营养模块共享同一个 ``ActionError``；各领域的 ``execute()`` 靠
``except ActionError`` 把它翻成统一错误信封。
"""

from __future__ import annotations


class ActionError(RuntimeError):
    """业务拒绝。各领域的 ``execute()`` 把它翻成统一错误信封，handler 直接抛就行。"""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")
