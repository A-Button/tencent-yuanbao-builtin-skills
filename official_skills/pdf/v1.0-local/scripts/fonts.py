"""中英文混排字体注册工具。

使用边界：
- 仅用于已有 PDF 编辑流程中的中文 overlay、表单填写兜底、调试脚本。
- 不用于从 0 创建新 PDF；新建 PDF 必须走 SKILL.md 的 HTML→PDF 通路。

为 ReportLab 注册三套字体作为全局锚点：

- ``SourceHanSans`` —— 中文字体（思源黑体 / Noto Sans CJK 简体子字体）
- ``LatinSans`` —— 拉丁字体（英文/数字），优先 Inter，回退 DejaVu Sans / Helvetica
- ``MonoCJK`` —— 等宽字体（代码块），优先 JetBrains Mono，回退 DejaVu Sans Mono

设计原则：
- 面向 Linux 沙盒运行，优先使用沙盒内置字体路径。
- 找不到首选字体时**自动回退**而非抛错，最差情况退化到思源黑体（保证脚本永远能跑）。
- 通过环境变量 ``CJK_FONT_PATH`` / ``LATIN_FONT_PATH`` / ``MONO_FONT_PATH`` 可覆盖默认查找。

最常用调用::

    from fonts import register_all_fonts
    fonts = register_all_fonts()
    # fonts == {"cjk": "SourceHanSans", "latin": "LatinSans", "mono": "MonoCJK"}

注意：
- ``NotoSansCJK-Regular.ttc`` 是 TTC 合集，包含 JP/KR/SC/TC/HK 五个子字体；
  本模块默认加载索引 ``2``（简体中文）；若该索引不可用会退回到索引 ``0``。
- 如果 CJK 字体也找不到，``register_cjk_font()`` 会抛 FileNotFoundError；
  但 ``register_latin_font()`` 和 ``register_mono_font()`` 找不到时会回退到 CJK 字体。
"""

from __future__ import annotations

import os
from typing import Optional

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ---------------------------------------------------------------------------
# 字体注册名（在 ReportLab 中引用）
# ---------------------------------------------------------------------------
DEFAULT_FONT_NAME = "SourceHanSans"
DEFAULT_LATIN_NAME = "LatinSans"
DEFAULT_MONO_NAME = "MonoCJK"

# ---------------------------------------------------------------------------
# 默认字体路径（按优先级）
# ---------------------------------------------------------------------------
DEFAULT_FONT_PATH = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
# Noto Sans CJK TTC 中各子字体的常见顺序：0=JP, 1=KR, 2=SC, 3=TC, 4=HK
DEFAULT_SC_SUBFONT_INDEX = 2

# CJK 字体兜底候选（Linux 沙盒）
# wqy-microhei 是沙盒里 Noto CJK 缺失时的常见可用字体
CJK_FONT_FALLBACKS = [
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",  # Linux 沙盒兜底
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
]

# 拉丁字体候选（按优先级，第一个找到的胜出）
LATIN_FONT_CANDIDATES = [
    # Linux 沙盒
    "/usr/share/fonts/truetype/inter/Inter-Regular.ttf",
    "/usr/share/fonts/opentype/inter/Inter-Regular.otf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]

# 等宽字体候选（按优先级）
MONO_FONT_CANDIDATES = [
    # Linux
    "/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
]

_registered_cjk: Optional[str] = None
_registered_latin: Optional[str] = None
_registered_mono: Optional[str] = None


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------
# 已知 TTC 文件的子字体索引（关键字小写匹配文件名）
# 默认顺序 (0, 1, 2, ...) 适用于绝大多数 TTC（idx=0 通常是 Regular）；
# Noto Sans CJK / 思源黑体例外，简体在 idx=2。
TTC_SUBFONT_PREFERENCES = {
    "notosanscjk": (2, 0, 1, 3, 4),    # 0=JP, 1=KR, 2=SC, 3=TC, 4=HK -> 取 SC
    "sourcehansans": (2, 0, 1, 3, 4),
    "stheiti": (1, 0),                  # 0=TC, 1=SC -> 取 SC
}


def _ttc_index_order(path: str) -> tuple:
    """根据 TTC 文件名返回优先尝试的子字体索引顺序。"""
    base = os.path.basename(path).lower().replace(" ", "").replace("-", "")
    for key, order in TTC_SUBFONT_PREFERENCES.items():
        if key in base:
            return order
    # 默认：从 0 开始（绝大多数 TTC 的 idx=0 是 Regular）
    return (0, 1, 2, 3, 4, 5)


def _try_register_ttc(name: str, path: str, prefer_indices=None) -> bool:
    """尝试注册一个 TTC 合集，按优先级选择子字体。

    若未传 prefer_indices，自动根据文件名查表（见 TTC_SUBFONT_PREFERENCES）。
    """
    if prefer_indices is None:
        prefer_indices = _ttc_index_order(path)

    seen = set()
    for idx in prefer_indices:
        if idx in seen:
            continue
        seen.add(idx)
        try:
            pdfmetrics.registerFont(TTFont(name, path, subfontIndex=idx))
            return True
        except Exception:
            continue
    return False


def _try_register_any(name: str, path: str) -> bool:
    """尝试注册任意字体文件（自动判 ttc/ttf/otf）。"""
    if not path or not os.path.isfile(path):
        return False
    if path.lower().endswith(".ttc"):
        return _try_register_ttc(name, path)
    try:
        pdfmetrics.registerFont(TTFont(name, path))
        return True
    except Exception:
        return False


def _register_first_available(name: str, env_var: str, candidates: list) -> Optional[str]:
    """按优先级尝试候选路径，注册第一个成功的字体。返回路径或 None。"""
    paths = []
    env_path = os.environ.get(env_var)
    if env_path:
        paths.append(env_path)
    paths.extend(candidates)

    for path in paths:
        if _try_register_any(name, path):
            return path
    return None


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------
def register_cjk_font(name: str = DEFAULT_FONT_NAME) -> str:
    """注册思源黑体/Noto Sans CJK 并返回可在 ReportLab 中使用的字体名。

    查找顺序：
    1. 环境变量 ``CJK_FONT_PATH``
    2. ``/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc``（沙盒）

    全部找不到时抛 ``FileNotFoundError`` —— CJK 是底线，必须有。
    """
    global _registered_cjk
    if _registered_cjk == name:
        return name

    candidates = []
    env_path = os.environ.get("CJK_FONT_PATH")
    if env_path:
        candidates.append(env_path)
    candidates.append(DEFAULT_FONT_PATH)
    candidates.extend(CJK_FONT_FALLBACKS)

    for path in candidates:
        if _try_register_any(name, path):
            _registered_cjk = name
            return name

    raise FileNotFoundError(
        f"未找到可用的中文字体。请确认 {DEFAULT_FONT_PATH} 存在，"
        "或通过 CJK_FONT_PATH 环境变量指向一个可用的 TTF/TTC 文件。"
        f"沙盒兜底也均未找到: {CJK_FONT_FALLBACKS}"
    )


def register_latin_font(name: str = DEFAULT_LATIN_NAME) -> str:
    """注册一款精致的拉丁字体（英文/数字），返回字体名。

    找不到时**回退到 CJK 字体**（思源黑体），确保上层调用永远拿得到一个可用名字。
    回退后 ``LatinSans`` 实际指向 ``SourceHanSans`` —— 排版逻辑无需改变。
    """
    global _registered_latin
    if _registered_latin == name:
        return name

    found = _register_first_available(name, "LATIN_FONT_PATH", LATIN_FONT_CANDIDATES)
    if found:
        _registered_latin = name
        return name

    # 回退：让 LatinSans 指向 CJK 字体
    cjk = register_cjk_font()
    if name != cjk:
        # 用 CJK 字体的同一个文件再注册一次，使用别名 LatinSans
        cjk_path = os.environ.get("CJK_FONT_PATH", DEFAULT_FONT_PATH)
        if _try_register_any(name, cjk_path):
            _registered_latin = name
            return name
    # 最坏情况：返回 CJK 名，让上层用 CJK_FONT
    _registered_latin = cjk
    return cjk


def register_mono_font(name: str = DEFAULT_MONO_NAME) -> str:
    """注册一款等宽字体（代码块），返回字体名。

    找不到时回退到 CJK 字体（思源黑体不是等宽，但保证中文不变方块）。
    """
    global _registered_mono
    if _registered_mono == name:
        return name

    found = _register_first_available(name, "MONO_FONT_PATH", MONO_FONT_CANDIDATES)
    if found:
        _registered_mono = name
        return name

    # 回退到 CJK 字体（牺牲等宽换"中文不变方块"）
    cjk = register_cjk_font()
    if name != cjk:
        cjk_path = os.environ.get("CJK_FONT_PATH", DEFAULT_FONT_PATH)
        if _try_register_any(name, cjk_path):
            _registered_mono = name
            return name
    _registered_mono = cjk
    return cjk


def register_all_fonts() -> dict:
    """一次注册三套字体，返回 {'cjk': ..., 'latin': ..., 'mono': ...}。

    这是最推荐的调用方式 —— 上层只用关心 ``fonts['cjk']`` / ``fonts['latin']``
    / ``fonts['mono']`` 这三个键。
    """
    return {
        "cjk": register_cjk_font(),
        "latin": register_latin_font(),
        "mono": register_mono_font(),
    }


if __name__ == "__main__":
    fonts = register_all_fonts()
    print("已注册字体:")
    for role, font_name in fonts.items():
        print(f"  {role:<6} -> {font_name}")
