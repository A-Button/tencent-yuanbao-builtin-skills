"""中文字体（思源黑体 / Noto Sans CJK）注册工具。

为 ReportLab 注册一个支持中文的 TrueType 字体，默认注册名为 `SourceHanSans`。

沙盒中安装的是 Google 的 **Noto Sans CJK**，它与 Adobe 的 **Source Han Sans（思源黑体）**
字形完全一致（同一套母带，只是品牌不同）；本技能统一使用注册名 `SourceHanSans` 作为
语义锚点，实际加载的是 Noto Sans CJK TTC 的简体中文（SC）子字体。

查找顺序：
1. 环境变量 `CJK_FONT_PATH`（用于自定义覆盖）
2. `/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc`

使用方法::

    from fonts import register_cjk_font
    font_name = register_cjk_font()  # 返回 "SourceHanSans"
    # 之后即可在 ReportLab 中以 font_name 引用该字体

注意：
- `NotoSansCJK-Regular.ttc` 是一个 TTC 合集，包含 JP/KR/SC/TC/HK 五个子字体；
  本模块默认加载索引 `2`（简体中文）；若该索引不可用会退回到索引 `0`。
- 如果环境变量指向的文件不可用且默认路径也不存在，会抛出 FileNotFoundError。
"""

from __future__ import annotations

import os
from typing import Optional

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

DEFAULT_FONT_NAME = "SourceHanSans"
DEFAULT_FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
# Noto Sans CJK TTC 中各子字体的常见顺序：0=JP, 1=KR, 2=SC, 3=TC, 4=HK
DEFAULT_SC_SUBFONT_INDEX = 2

_registered_name: Optional[str] = None


def _try_register(name: str, path: str) -> bool:
    if path.lower().endswith(".ttc"):
        # 优先加载简体中文子字体；若索引不对再退回到第一个子字体
        for idx in (DEFAULT_SC_SUBFONT_INDEX, 0):
            try:
                pdfmetrics.registerFont(TTFont(name, path, subfontIndex=idx))
                return True
            except Exception:
                continue
        return False
    try:
        pdfmetrics.registerFont(TTFont(name, path))
        return True
    except Exception:
        return False


def register_cjk_font(name: str = DEFAULT_FONT_NAME) -> str:
    """注册思源黑体/Noto Sans CJK 并返回可在 ReportLab 中使用的字体名。"""
    global _registered_name
    if _registered_name == name:
        return name

    candidates = []
    env_path = os.environ.get("CJK_FONT_PATH")
    if env_path:
        candidates.append(env_path)
    candidates.append(DEFAULT_FONT_PATH)

    for path in candidates:
        if path and os.path.isfile(path) and _try_register(name, path):
            _registered_name = name
            return name

    raise FileNotFoundError(
        f"未找到可用的中文字体。期望路径: {DEFAULT_FONT_PATH}，"
        "或通过 CJK_FONT_PATH 环境变量指向一个可用的 TTF/TTC 文件。"
    )


if __name__ == "__main__":
    print(f"已注册字体: {register_cjk_font()}")
