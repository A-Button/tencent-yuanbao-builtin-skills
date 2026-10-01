#!/usr/bin/env python3
"""卡面上那些「图形」的服务端实现：进度条与迷你走势。

为什么不是真组件：A2UI 的 ``style`` 只吃字面量，绑不了数据（全仓卡片里 ``style``
内部从没出现过 ``path``，文档也只讲 ``text`` / ``children`` 能绑）。比例条的填充
长度天然来自数据，所以用 ``Box`` 拼色块画不出比例；catalog 里也没有任何图表组件。
块字符条塞进 ``Text`` 是唯一一条「一定画得出来」的路——``Text`` + ``path`` 绑定
是卡片里已经跑通的机制。

要换成真组件的前提是 ``style`` 支持绑定，或者 catalog 补进度条/图表组件。在那之前
这两个函数就是卡面的图形层，改宽度和字符只动这里。
"""

from __future__ import annotations

BAR_FILLED = "█"
BAR_EMPTY = "░"
BAR_WIDTH = 10

# 低到高八级。用于近几周的体重走势，点与点之间只表达相对高低。
SPARK_LEVELS = "▁▂▃▄▅▆▇█"


def progress_bar(fill_percent, width: int = BAR_WIDTH) -> str:
    """按百分比画一条定宽块字符进度条。

    ``fill_percent`` 为 None 时返回空串——「算不出来」要留白，画成 0% 会被看成
    「今天一口没吃」。超过 100 画满，不溢出。
    """
    if fill_percent is None:
        return ""
    percent = max(0.0, min(100.0, float(fill_percent)))
    filled = round(percent / 100.0 * width)
    return BAR_FILLED * filled + BAR_EMPTY * (width - filled)


def sparkline(values: list) -> str:
    """把一串数值画成迷你走势。

    少于 2 个点返回空串：一个点没有走势可言，画出来只会让人以为是真趋势。
    全部相等时统一取中间一级，避免除零也避免画成一路走高。
    """
    numbers = [float(value) for value in values if value is not None]
    if len(numbers) < 2:
        return ""
    low, high = min(numbers), max(numbers)
    if high == low:
        middle = SPARK_LEVELS[len(SPARK_LEVELS) // 2]
        return middle * len(numbers)
    span = high - low
    top = len(SPARK_LEVELS) - 1
    return "".join(SPARK_LEVELS[round((n - low) / span * top)] for n in numbers)
