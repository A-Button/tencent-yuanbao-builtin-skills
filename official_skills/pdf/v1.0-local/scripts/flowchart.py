"""Graphviz 流程图封装 + ReportLab PDF 嵌入。

使用边界：
- `render_flowchart()` 可生成 PNG/SVG，供 HTML→PDF 创建流程插入 HTML。
- `embed_flowchart_in_pdf()` 仅用于已有 PDF 编辑流程中的 overlay/调试，不用于从 0 创建新 PDF。

解决问题 3：流程图样式不美观。

设计要点：
- 用 ``graphviz`` Python 包（pip install graphviz）+ ``dot`` 二进制（apt-get install graphviz）。
- 提供三套主题（``clean`` / ``business`` / ``minimal``），开箱即用。
- 默认 ``splines=ortho``（直角折线），比贝塞尔曲线更工整。
- 节点用圆角矩形 + 浅灰填充 + 蓝色边框，思源黑体，中英文混排正常。
- ``embed_flowchart_in_pdf()`` 自动按 PDF 内容区宽度等比缩放，避免 LLM 算缩放出错。

最常用调用::

    from flowchart import embed_flowchart_in_pdf

    nodes = [
        {"id": "start", "label": "开始", "shape": "ellipse"},
        {"id": "check", "label": "材料齐全？", "shape": "diamond"},
        {"id": "review", "label": "进入审核"},
        {"id": "end", "label": "完成", "shape": "ellipse"},
    ]
    edges = [
        {"from": "start", "to": "check"},
        {"from": "check", "to": "review", "label": "是"},
        {"from": "check", "to": "start", "label": "否"},
        {"from": "review", "to": "end"},
    ]
    embed_flowchart_in_pdf(story, nodes, edges, theme="clean")

依赖检查：模块导入时不强制要求 graphviz，但 ``render_flowchart()`` 调用时会抛
明确的错误并提示安装方式。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional

# 三套主题预设（dot 属性）
THEMES = {
    "clean": {
        "graph": {
            "rankdir": "TB",
            "splines": "ortho",
            "nodesep": "0.5",
            "ranksep": "0.6",
            "bgcolor": "transparent",
            "fontname": "SourceHanSans",
        },
        "node": {
            "shape": "box",
            "style": "rounded,filled",
            "fillcolor": "#f8fafc",
            "color": "#2563eb",
            "fontname": "SourceHanSans",
            "fontsize": "11",
            "fontcolor": "#1e293b",
            "margin": "0.25,0.12",
            "penwidth": "1.2",
            "height": "0.5",
        },
        "edge": {
            "color": "#64748b",
            "fontname": "SourceHanSans",
            "fontsize": "9",
            "fontcolor": "#475569",
            "arrowsize": "0.7",
            "penwidth": "1.0",
        },
    },
    "business": {
        "graph": {
            "rankdir": "TB",
            "splines": "ortho",
            "nodesep": "0.6",
            "ranksep": "0.7",
            "bgcolor": "transparent",
            "fontname": "SourceHanSans",
        },
        "node": {
            "shape": "box",
            "style": "rounded,filled",
            "fillcolor": "#1e3a8a",
            "color": "#1e40af",
            "fontname": "SourceHanSans",
            "fontsize": "11",
            "fontcolor": "#ffffff",
            "margin": "0.3,0.15",
            "penwidth": "1.5",
        },
        "edge": {
            "color": "#1e3a8a",
            "fontname": "SourceHanSans",
            "fontsize": "9",
            "fontcolor": "#1e3a8a",
            "arrowsize": "0.8",
            "penwidth": "1.2",
        },
    },
    "minimal": {
        "graph": {
            "rankdir": "TB",
            "splines": "ortho",
            "nodesep": "0.4",
            "ranksep": "0.5",
            "bgcolor": "transparent",
            "fontname": "SourceHanSans",
        },
        "node": {
            "shape": "box",
            "style": "rounded",
            "color": "#000000",
            "fontname": "SourceHanSans",
            "fontsize": "10",
            "fontcolor": "#000000",
            "margin": "0.2,0.1",
            "penwidth": "0.8",
        },
        "edge": {
            "color": "#000000",
            "fontname": "SourceHanSans",
            "fontsize": "9",
            "fontcolor": "#000000",
            "arrowsize": "0.6",
            "penwidth": "0.8",
        },
    },
}

# 不同主题下，特殊形状（菱形、椭圆、平行四边形）的填色覆盖
SHAPE_OVERRIDES = {
    "clean": {
        "ellipse": {"fillcolor": "#dbeafe", "color": "#1d4ed8"},   # 起止节点
        "diamond": {"fillcolor": "#fef3c7", "color": "#d97706"},   # 判定
        "parallelogram": {"fillcolor": "#dcfce7", "color": "#16a34a"},  # 输入输出
    },
    "business": {
        "ellipse": {"fillcolor": "#0c1e3e", "color": "#0c1e3e"},
        "diamond": {"fillcolor": "#1e3a8a", "color": "#1e3a8a"},
        "parallelogram": {"fillcolor": "#1e40af", "color": "#1e40af"},
    },
    "minimal": {},  # 极简主题不区分形状颜色
}


def _check_graphviz_available() -> None:
    """模块调用时检查 graphviz 依赖是否齐全。"""
    if shutil.which("dot") is None:
        raise RuntimeError(
            "未找到 'dot' 命令。请先安装 graphviz：\n"
            "  apt-get install graphviz\n"
            "然后再 pip install graphviz"
        )
    try:
        import graphviz  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            "未安装 graphviz Python 包。请运行：pip install graphviz"
        ) from e


def render_flowchart(
    nodes: list[dict],
    edges: list[dict],
    output_path: str,
    *,
    direction: str = "TB",
    theme: str = "clean",
    fmt: str = "png",
    dpi: int = 200,
) -> str:
    """渲染流程图为 PNG/SVG 文件。

    Args:
        nodes: 节点列表，每项是 ``{"id": str, "label": str, "shape": str?}``。
            shape 可选 ``box``/``ellipse``/``diamond``/``parallelogram``，缺省 box。
        edges: 边列表，每项是 ``{"from": str, "to": str, "label": str?}``。
        output_path: 输出文件完整路径（含扩展名，graphviz 实际写到不带扩展名 + .{fmt}）。
        direction: ``TB`` 上下 / ``LR`` 左右 / ``BT`` 下上 / ``RL`` 右左。
        theme: ``clean`` / ``business`` / ``minimal``。
        fmt: ``png`` / ``svg`` / ``pdf``。
        dpi: 渲染 DPI（仅 png 有效）。

    Returns:
        实际生成的文件路径。
    """
    _check_graphviz_available()
    import graphviz

    if theme not in THEMES:
        raise ValueError(f"未知主题: {theme}，可选: {list(THEMES.keys())}")

    theme_cfg = THEMES[theme]
    shape_overrides = SHAPE_OVERRIDES.get(theme, {})

    # 构建 Digraph
    g = graphviz.Digraph(format=fmt)
    graph_attrs = dict(theme_cfg["graph"])
    graph_attrs["rankdir"] = direction
    if fmt == "png":
        graph_attrs["dpi"] = str(dpi)
    g.attr(**graph_attrs)
    g.attr("node", **theme_cfg["node"])
    g.attr("edge", **theme_cfg["edge"])

    # 添加节点
    for node in nodes:
        node_id = node["id"]
        label = node.get("label", node_id)
        shape = node.get("shape", "box")
        attrs = {"shape": shape, "label": label}
        # 特殊形状的颜色覆盖
        if shape in shape_overrides:
            attrs.update(shape_overrides[shape])
        # 用户自定义属性
        for k in ("fillcolor", "color", "fontcolor", "style"):
            if k in node:
                attrs[k] = node[k]
        g.node(node_id, **attrs)

    # 添加边
    for edge in edges:
        attrs = {}
        if "label" in edge:
            attrs["label"] = edge["label"]
        for k in ("color", "style", "arrowhead"):
            if k in edge:
                attrs[k] = edge[k]
        g.edge(edge["from"], edge["to"], **attrs)

    # 渲染
    base, ext = os.path.splitext(output_path)
    if ext.lstrip(".") and ext.lstrip(".") != fmt:
        # 用户传的扩展名和 fmt 不一致，以 fmt 为准
        pass
    g.render(filename=base, format=fmt, cleanup=True)
    actual = base + "." + fmt
    return actual


def embed_flowchart_in_pdf(
    story: list,
    nodes: list[dict],
    edges: list[dict],
    *,
    direction: str = "TB",
    theme: str = "clean",
    width_pt: Optional[float] = None,
    max_width_pt: float = 480,   # A4 内容区典型宽度（页边距 50 后约 495）
    tmp_dir: str = "/tmp",
    caption: Optional[str] = None,
) -> None:
    """渲染流程图并以 ``Image`` 形式追加到 ReportLab story。

    会自动按图片真实尺寸等比缩放：
    - 若 ``width_pt`` 给定，强制宽度
    - 否则按真实像素宽度（DPI=200）换算成 pt，超出 ``max_width_pt`` 时缩到 max
    - 高度按等比

    Args:
        story: ReportLab Platypus story 列表（会被 append）。
        nodes/edges: 同 render_flowchart。
        width_pt: 指定输出宽度（pt）。
        max_width_pt: 自动缩放时的上限（默认 480pt，A4 内容区）。
        tmp_dir: 临时图片目录。
        caption: 可选图说，附在图片下方（用 Caption 样式）。
    """
    from reportlab.platypus import Image, Spacer
    from PIL import Image as PILImage

    # 渲染到 tmp
    out_path = os.path.join(tmp_dir, f"flowchart_{os.getpid()}_{id(nodes)}.png")
    render_flowchart(nodes, edges, out_path, direction=direction, theme=theme, fmt="png", dpi=200)

    # 探测真实尺寸
    with PILImage.open(out_path) as im:
        px_w, px_h = im.size

    # 200 DPI 换算：1 inch = 72 pt = 200 px → 1 px = 72/200 pt = 0.36 pt
    pt_per_px = 72.0 / 200.0
    natural_w_pt = px_w * pt_per_px
    natural_h_pt = px_h * pt_per_px

    if width_pt is None:
        width_pt = min(natural_w_pt, max_width_pt)
    height_pt = width_pt * (natural_h_pt / natural_w_pt)

    story.append(Spacer(1, 6))
    story.append(Image(out_path, width=width_pt, height=height_pt))

    if caption:
        from cjk_styles import make_cjk_styles, cjk_paragraph
        styles = make_cjk_styles()
        story.append(cjk_paragraph(caption, styles["Caption"]))
    else:
        story.append(Spacer(1, 6))


__all__ = ["render_flowchart", "embed_flowchart_in_pdf", "THEMES"]


if __name__ == "__main__":
    # 烟测：渲染一张样图
    nodes = [
        {"id": "start", "label": "用户提交申请", "shape": "ellipse"},
        {"id": "check", "label": "材料齐全？", "shape": "diamond"},
        {"id": "review", "label": "进入审核"},
        {"id": "reject", "label": "退回补充"},
        {"id": "end", "label": "审批完成", "shape": "ellipse"},
    ]
    edges = [
        {"from": "start", "to": "check"},
        {"from": "check", "to": "review", "label": "是"},
        {"from": "check", "to": "reject", "label": "否"},
        {"from": "reject", "to": "start"},
        {"from": "review", "to": "end"},
    ]
    out = render_flowchart(nodes, edges, "/tmp/flowchart_smoke.png", theme="clean")
    print(f"已渲染: {out}")
