#!/usr/bin/env python3
"""把报告 HTML 落到沙箱工作区。

**为什么这两个报告不出卡。** 报告主体是逐餐明细、周历和趋势图，A2UI 的组件目录里
没有表格也没有图表，用 Text 拼只能拼出一行方块字符。所以这两个工具不发
``__ONEAGENT_APP_RESULT__``，改为在 ``/data/workspace/`` 下写一份 HTML——平台会把
工作区里的文件当产物下发，用户点开就是整页报告。训练卡和饮食卡不受影响，照旧出卡。

**产物必须自带全部内容。** 它要发到用户浏览器里，外链 CDN 和字体在他那边不一定通，
本地 PNG 又得走一趟 COS 转存。所以图表一律内联 SVG，样式内联 style，离线也打得开。

这个模块以前还管着旧版报告的模板渲染（``render`` / ``charts_block`` / 两个 SVG
柱状图生成器）。旧版通道撤掉之后那些全成了死代码，一并删了——留着的代价不是占空间，
是下一个人看到现成的 ``render`` 就又把旧壳套回去，而这正是「产物不是新模板」的成因。
现在排版归 ``_health_report_v1``，这里只剩「写到哪」。
"""

from __future__ import annotations

import sys
from pathlib import Path
_scripts = Path(__file__).resolve().parents[1]
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))
import _boot
_boot.install()

import os
from pathlib import Path

# 平台扫这个目录取产物。``business_packer/asset`` 里的 scan 也认这个前缀。
WORKSPACE_DIR = "/data/workspace"
WORKSPACE_ENV = "HEALTH_ASSISTANT_WORKSPACE_DIR"


def _report_family(filename: str) -> str:
    """``health-daily-*.html`` / ``health-weekly-*.html`` 各算一类。别的文件不动。"""
    for family in ("health-daily", "health-weekly"):
        if filename.startswith(family + "-") and filename.endswith(".html"):
            return family
    return ""


def _drop_other_reports(directory: Path, filename: str) -> None:
    """写下这一份之前，清掉同类里其余的 HTML。

    平台扫工作区，把里面的 HTML 都当产物。留下上一份带时间戳的日报，
    这一轮就会同时出现两份。周报同理，只清周报，不动日报。
    """
    family = _report_family(filename)
    if not family:
        return
    for old in directory.glob(family + "-*.html"):
        if old.name != filename and old.is_file():
            old.unlink()


def write(html_text: str, filename: str) -> str:
    """写进工作区，返回绝对路径。

    目录不存在（本地跑测试、或沙箱还没挂上）就退回临时目录：报告本身算得出来，
    不该因为落不了盘把整个工具判失败。同一类报告只留这一份，后写的覆盖先写的。
    """
    target = Path(os.environ.get(WORKSPACE_ENV) or WORKSPACE_DIR)
    try:
        target.mkdir(parents=True, exist_ok=True)
        _drop_other_reports(target, filename)
        path = target / filename
        path.write_text(html_text, encoding="utf-8")
    except OSError:
        path = Path("/tmp") / filename
        path.write_text(html_text, encoding="utf-8")
    return str(path)
