#!/usr/bin/env python3
"""从模板生成一个可运行的 App Skill 骨架。

生成后还需要两步才算完成：`npm install && npm run build:ui` 产出单文件 HTML，
以及把模板里的示例领域（title / notes 的增删改查）换成真实业务。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ASSET_ROOT = Path(__file__).resolve().parent.parent / "assets"
TEMPLATE_ROOT = ASSET_ROOT / "templates"
APP_ID_RE = re.compile(r"^[a-z][a-z0-9]*([-_][a-z0-9]+)*$")
IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# 两种给 skill 加界面的方式。共享模板之外，各自再叠一层。
#
# h5   —— 一份 H5 兼任卡片与全屏，形态差别由 MCP Apps 的 displayMode 表达。
# a2ui —— 卡片是 A2UI 组件树，交给端上引擎渲染；全屏仍是 H5，由卡片里的
#         open_workspace action 引过去。两者不嵌套。
UI_MODES = {
    "h5": {
        "overlay": "templates-h5",
        "source": "index.template",
        "output": "index.html",
    },
    "a2ui": {
        "overlay": "templates-a2ui",
        "source": "workspace.template",
        "output": "workspace.html",
    },
}

# 业务数据怎么落盘。两者都放持久卷 /data/user/<app-id>/（本地跑没这个挂载时退到
# ~/.one-agent/data/<app-id>/），出参形状也完全一致，所以 UI、卡片与包内测试
# 都不必区分底层用了哪种。
#
# json   —— 整份读写，几百条以内够用，也最好读懂。
# sqlite —— 行级增删改，记录会涨到几千条以上、或要按条件筛选排序时选它。
STORE_MODES = {
    "json": {"overlay": None, "suffix": "json"},
    "sqlite": {"overlay": "templates-store-sqlite", "suffix": "db"},
}


class InitError(Exception):
    pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scaffold a OneAgent App Skill (UI + app.yaml + tool handler)."
    )
    parser.add_argument("app_id", help="App id，同时是目录名、ui:// 前缀和 SKILL.md 的 name")
    parser.add_argument(
        "--path",
        default=".",
        help="生成到哪个父目录。调用方应传入当前工作区根目录；默认是进程当前目录，不是本机 ~/.one-agent",
    )
    parser.add_argument("--name", default="", help="中文展示名，默认取 app_id")
    parser.add_argument("--description", default="", help="SKILL.md description，决定何时被检索到")
    parser.add_argument("--entity", default="item", help="业务实体单数英文名，默认 item")
    parser.add_argument("--entity-plural", default="", help="实体复数，默认 <entity>s")
    parser.add_argument("--version", default="v1.0", help="app.yaml version，默认 v1.0")
    parser.add_argument(
        "--ui-mode",
        choices=sorted(UI_MODES),
        default="h5",
        help="h5：一份 H5 兼任卡片与全屏；a2ui：A2UI 卡片 + H5 全屏工作区",
    )
    parser.add_argument(
        "--store",
        choices=sorted(STORE_MODES),
        default="json",
        help="业务数据存储：json 整份读写；sqlite 行级增删改，适合量大或要条件查询",
    )
    parser.add_argument("--force", action="store_true", help="目标目录已存在时覆盖同名文件")
    args = parser.parse_args()

    try:
        target = scaffold(args)
    except InitError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"已生成 {target}")
    print("App 工具使用 python handler：默认调用与 tool.name 同名的同步函数，可用 handler.function 覆盖，stdout 给模型，返回字典给 UI。")
    print("运行前确认 sandbox app 与页面回调执行入口均支持此契约。")
    print("产物留在工作区这个目录，不要复制到 ~/.one-agent，也不要执行 register_local_app.py。")
    print("下一步：")
    print(f"  cd {target} && npm install && npm run build:ui && npm test")
    print(f"  python3 {Path(__file__).with_name('validate_app_skill.py')} {target}")
    return 0


def scaffold(args: argparse.Namespace) -> Path:
    app_id = args.app_id.strip()
    if not APP_ID_RE.match(app_id):
        # 连续下划线也在此被拒：模型面工具名用 __ 切分 app_id 与 tool 名。
        raise InitError(
            f"app_id {app_id!r} 只能用小写字母、数字，以及单个 - 或 _ 作分隔，不能有连续下划线"
        )

    entity = args.entity.strip() or "item"
    entity_plural = args.entity_plural.strip() or f"{entity}s"
    for label, value in (("entity", entity), ("entity-plural", entity_plural)):
        if not IDENTIFIER_RE.match(value):
            raise InitError(f"{label} {value!r} 必须是小写字母开头的标识符")

    mode = UI_MODES[args.ui_mode]
    store = STORE_MODES[args.store]
    store_file = f"{entity_plural}.{store['suffix']}"
    display_name = args.name.strip() or app_id
    description = args.description.strip() or (
        f"{display_name}的本地 App Skill，支持记录、查看、更新与删除，并在对话内以卡片展示。"
    )

    values = {
        "APP_ID": app_id,
        "APP_NAME": display_name,
        "APP_DESCRIPTION": description,
        "VERSION": args.version.strip() or "v1.0",
        "VERSION_SEMVER": semver(args.version.strip() or "v1.0"),
        "ENTITY": entity,
        "ENTITY_PLURAL": entity_plural,
        "RESOURCE_URI": (
            f"ai_apps.skills.{app_id.replace('-', '_')}_card_res"
            if args.ui_mode == "a2ui"
            else f"ui://{app_id}/main"
        ),
        "WORKSPACE_URI": f"ui://{app_id}/workspace",
        "UI_SOURCE": mode["source"],
        "UI_OUTPUT": mode["output"],
        "BRIDGE_GLOBAL": bridge_global(app_id),
        "ENV_PREFIX": re.sub(r"[^A-Z0-9]", "_", app_id.upper()),
        "STORE_FILE": store_file,
        "STORE_PATH": f"/data/user/{app_id}/{store_file}",
    }

    target = (Path(args.path).expanduser() / app_id).resolve()
    if target.exists() and not args.force and any(target.iterdir()):
        raise InitError(f"{target} 已存在且非空，加 --force 覆盖")

    # 先铺共享模板，再依次让 UI 模式、存储模式那层覆盖上去（同名以后者为准）。
    overlays = [mode["overlay"], store["overlay"]]
    roots = [TEMPLATE_ROOT] + [ASSET_ROOT / name for name in overlays if name]
    for root in roots:
        for source in sorted(root.rglob("*.tmpl")):
            relative = source.relative_to(root)
            destination = target / render_path(relative, values)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                render(source.read_text(encoding="utf-8"), values), encoding="utf-8"
            )

    return target


def render(text: str, values: dict[str, str]) -> str:
    def replace(match: re.Match) -> str:
        key = match.group(1)
        if key not in values:
            raise InitError(f"模板里有未知占位符：{{{{{key}}}}}")
        return values[key]

    return re.sub(r"\{\{([A-Z_]+)\}\}", replace, text)


def render_path(relative: Path, values: dict[str, str]) -> Path:
    name = render(relative.name, values)
    name = name[: -len(".tmpl")]
    if name == "gitignore":
        name = ".gitignore"
    return relative.parent / name


def bridge_global(app_id: str) -> str:
    """my-notes -> myNotesMcp。UI 通过 window.<这个名字> 访问 bridge。"""
    head, *rest = re.split(r"[-_]", app_id)
    return head + "".join(part.capitalize() for part in rest) + "Mcp"


def semver(version: str) -> str:
    cleaned = version.lstrip("v")
    if re.match(r"^\d+\.\d+\.\d+$", cleaned):
        return cleaned
    if re.match(r"^\d+\.\d+$", cleaned):
        return f"{cleaned}.0"
    return "1.0.0"


if __name__ == "__main__":
    raise SystemExit(main())
