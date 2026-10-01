#!/usr/bin/env python3
"""校验一个 App Skill 包的结构一致性。

覆盖的是「装进去才发现」的那类问题：id 三处不一致、resourceUri 指向未声明的资源、
字段写在后端读不到的位置、构建产物过期或残留外链。它不验证业务正确性。

用法：
    python3 validate_app_skill.py <app-dir> [<app-dir> ...]
"""

from __future__ import annotations

import argparse
import ast
import json
import keyword
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

MIME_TYPE = "text/html;profile=mcp-app"
# A2UI 卡片走端上引擎渲染，H5 走 iframe。mimeType 是宿主分派引擎的唯一依据，
# 所以这里按它区分后续校验：A2UI 资源没有 bridge、也没有构建产物一说。
A2UI_MIME_TYPE = "application/a2ui+json"
KNOWN_MIME_TYPES = {MIME_TYPE, A2UI_MIME_TYPE}
# 卡片引向全屏工作区的保留 action name，与宿主约定一致。
OPEN_WORKSPACE_ACTION = "open_workspace"
VALID_VISIBILITY = {"model", "app"}
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", re.S)
PLACEHOLDER_RE = re.compile(r"\{\{[A-Z_]+\}\}|/\*__[A-Z_]+__\*/")
# 只查会被 CSP 拦掉的子资源加载。<a href> 是普通跳转，不在此列。
EXTERNAL_REF_RE = re.compile(
    r"""<(?:script|link|img|iframe|source|video|audio|embed|object)\b[^>]*?"""
    r"""\b(?:src|href|data)\s*=\s*["']https?://""",
    re.I | re.S,
)
LEGACY_VISIBILITY = {"agent": "model", "ui": "app"}


class Report:
    def __init__(self, root: Path):
        self.root = root
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def emit(self) -> bool:
        for message in self.errors:
            print(f"  ✗ {message}")
        for message in self.warnings:
            print(f"  ! {message}")
        if not self.errors and not self.warnings:
            print("  ✓ 通过")
        elif not self.errors:
            print("  ✓ 通过（有告警）")
        return not self.errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate OneAgent App Skill packages.")
    parser.add_argument("targets", nargs="+", help="App Skill 目录")
    args = parser.parse_args()

    if yaml is None:
        print("error: 需要 PyYAML（pip install pyyaml）", file=sys.stderr)
        return 2

    ok = True
    for raw in args.targets:
        root = Path(raw).expanduser().resolve()
        print(f"{root}")
        ok = validate(root).emit() and ok
    return 0 if ok else 1


def validate(root: Path) -> Report:
    report = Report(root)
    if not root.is_dir():
        report.error("目录不存在")
        return report

    skill_md = root / "SKILL.md"
    app_yaml = root / "assets" / "app.yaml"
    if not skill_md.is_file():
        report.error("缺少 SKILL.md")
    if not app_yaml.is_file():
        report.error("缺少 assets/app.yaml")
    if report.errors:
        return report

    try:
        manifest = yaml.safe_load(app_yaml.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        report.error(f"app.yaml 解析失败：{exc}")
        return report
    if not isinstance(manifest, dict):
        report.error("app.yaml 根节点必须是对象")
        return report

    app_id = str(manifest.get("id") or "")
    check_identity(report, root, skill_md, app_id)
    resources = check_resources(report, root, manifest, app_id)
    tools = check_tools(report, root, manifest, resources)
    check_built_ui(report, root, resources)
    check_a2ui_cards(report, root, resources)
    check_skill_md(report, skill_md, app_id, tools)
    return report


def check_identity(report: Report, root: Path, skill_md: Path, app_id: str) -> None:
    if not app_id:
        report.error("app.yaml 缺少 id")
        return
    if "__" in app_id:
        report.error(f"id {app_id!r} 不能含连续下划线：模型面工具名用 __ 切分 app_id 与 tool 名")
    if app_id != root.name:
        report.error(f"app.yaml id {app_id!r} 与目录名 {root.name!r} 不一致")

    frontmatter, parse_error = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    if parse_error:
        report.error(f"SKILL.md frontmatter 不是合法 YAML：{parse_error}")
        return

    name = frontmatter.get("name", "")
    if not name:
        report.error("SKILL.md frontmatter 缺少 name")
    elif name != app_id:
        report.error(f"SKILL.md name {name!r} 与 app.yaml id {app_id!r} 不一致")
    if not frontmatter.get("description"):
        report.error("SKILL.md frontmatter 缺少 description，技能无法被正确检索")


def check_resources(report: Report, root: Path, manifest: dict, app_id: str) -> dict[str, dict]:
    raw = manifest.get("resources")
    if not isinstance(raw, list) or not raw:
        report.error("app.yaml 未声明 resources[]，UI 无法挂载")
        return {}

    resources: dict[str, dict] = {}
    for index, resource in enumerate(raw):
        label = f"resources[{index}]"
        if not isinstance(resource, dict):
            report.error(f"{label} 必须是对象")
            continue
        uri = str(resource.get("uri") or "")
        if not uri:
            report.error(f"{label} 缺少 uri")
            continue
        mime = resource.get("mimeType")
        if mime == A2UI_MIME_TYPE:
            skill_name = app_id.replace("-", "_")
            # 默认页可省略页面名；具名页面使用小写 snake_case。
            pattern = rf"ai_apps\.skills\.{re.escape(skill_name)}(?:_[a-z][a-z0-9]*(?:_[a-z0-9]+)*)?_res"
            if not re.fullmatch(pattern, uri):
                report.error(
                    f"{label} A2UI uri {uri!r} 应形如 ai_apps.skills.{skill_name}_<页面名>_res"
                    f"（默认页可用 ai_apps.skills.{skill_name}_res）"
                )
        elif mime == MIME_TYPE and not uri.startswith(f"ui://{app_id}/"):
            report.error(f"{label} H5 uri {uri!r} 应形如 ui://{app_id}/<view>")
        if mime not in KNOWN_MIME_TYPES:
            report.error(
                f"{label} mimeType 必须是 {MIME_TYPE}（H5）或 {A2UI_MIME_TYPE}（A2UI 卡片）"
            )
        path = str(resource.get("path") or "")
        if not path:
            report.error(f"{label} 缺少 path")
        elif not (root / path).is_file():
            if has_ui_source(root / path):
                report.error(f"{label} 的 {path} 尚未构建，请先 npm run build:ui")
            else:
                report.error(f"{label} path 不存在：{path}")
        resources[uri] = resource
    return resources


def has_ui_source(built: Path) -> bool:
    """构建产物缺失时，判断是「还没构建」还是「path 写错了」。"""
    return built.with_suffix(".template").is_file() or built.with_name(
        built.stem + ".source.html"
    ).is_file()


# 用一个参数分派动作时的常见命名。这几个词当业务字段名几乎讲不通，配上多值 enum
# 基本可以断定是把若干操作塞进了同一个 tool。
DISPATCH_PARAMETERS = ("operation", "action", "method", "command")


def check_dispatch_parameter(report: Report, label: str, schema: dict) -> None:
    """一个操作一个 tool，不要在一个 tool 里用 operation 参数分派动作。

    合成一个 tool 会让 inputSchema 退化成所有操作字段的并集：required 只能要求
    operation 自己，additionalProperties 拦不住「delete 传了 title」，按操作变化的
    必填又没法写（CLI 不实现 if/then、oneOf），于是校验只能整块塞回 handler。
    """
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return
    for name in DISPATCH_PARAMETERS:
        field = properties.get(name)
        if not isinstance(field, dict):
            continue
        values = field.get("enum")
        if isinstance(values, list) and len(values) > 1:
            actions = "、".join(str(item) for item in values)
            report.error(
                f"{label} 用 {name} 参数分派动作（{actions}），"
                f"应拆成 {len(values)} 个 tool，每个各自声明 required 与字段白名单"
            )
            return


def check_tools(report: Report, root: Path, manifest: dict, resources: dict) -> list[dict]:
    raw = manifest.get("tools")
    if not isinstance(raw, list) or not raw:
        # toolBindings 是 MCP 后端 App 的形态：工具来自 MCP server，app.yaml 只绑资源。
        # 那类包不归本校验器管，报错只会制造噪音。
        for legacy in ("toolBindings", "scripts"):
            if manifest.get(legacy):
                report.warn(f"app.yaml 用的是 {legacy}[] 而非 tools[]，跳过工具校验")
                return []
        report.error("app.yaml 未声明 tools[]")
        return []

    tools: list[dict] = []
    model_visible = False
    for index, tool in enumerate(raw):
        label = f"tools[{index}]"
        if not isinstance(tool, dict):
            report.error(f"{label} 必须是对象")
            continue
        name = str(tool.get("name") or "")
        if not name:
            report.error(f"{label} 缺少 name")
            continue
        label = f"tool {name!r}"
        tools.append(tool)

        handler = tool.get("handler")
        if not isinstance(handler, dict) or not handler.get("path"):
            report.error(f"{label} 缺少 handler.path")
        else:
            handler_type = handler.get("type") or "script"
            if handler_type not in ("script", "python"):
                report.error(f"{label} handler.type={handler_type!r}，只支持 script / python")
            handler_path = root / str(handler["path"])
            if not handler_path.is_file():
                report.error(f"{label} handler.path 不存在：{handler['path']}")
            elif handler_type == "python":
                if "entrypoint" in handler:
                    report.error(f"{label} python handler 不支持 entrypoint，请使用 function")
                function = handler["function"] if "function" in handler else tool.get("name")
                if not isinstance(function, str) or not function.isidentifier() or keyword.iskeyword(function):
                    if "function" in handler:
                        report.error(f"{label} handler.function 必须是非空 Python 简单标识符，不能是关键字或点分路径")
                    else:
                        report.error(f"{label} 默认函数名不是有效 Python 标识符，请显式配置合法的 handler.function")
                else:
                    check_python_handler(report, label, handler_path, function)

        # 后端 manifest 解析只读 _meta.ui.resourceUri / visibility；写在顶层会被静默忽略。
        if tool.get("resourceUri") or tool.get("visibility"):
            report.error(
                f"{label} 的 resourceUri/visibility 写在了顶层，必须放到 _meta.ui 下，否则后端读不到"
            )
        ui_meta = ((tool.get("_meta") or {}).get("ui") or {}) if isinstance(tool.get("_meta"), dict) else {}
        resource_uri = str(ui_meta.get("resourceUri") or "")
        if not resource_uri:
            report.warn(f"{label} 未绑定 _meta.ui.resourceUri，调用它不会挂载 UI")
        elif resource_uri not in resources:
            report.error(f"{label} 绑定的 {resource_uri!r} 不在 resources[] 中")

        visibility = ui_meta.get("visibility")
        if visibility is None:
            report.warn(f"{label} 未声明 visibility，将默认对模型和页面全开放")
            model_visible = True
        elif not isinstance(visibility, list) or not visibility:
            report.error(f"{label} visibility 必须是非空数组，实际 {visibility!r}")
        else:
            legacy = sorted(set(visibility) & set(LEGACY_VISIBILITY))
            unknown = sorted(set(visibility) - VALID_VISIBILITY - set(LEGACY_VISIBILITY))
            if legacy:
                hints = "、".join(f"{old} → {LEGACY_VISIBILITY[old]}" for old in legacy)
                report.warn(f"{label} visibility 用了旧取值（{hints}），建议改用 MCP Apps 原生取值")
            if unknown:
                report.error(f"{label} visibility 含无效取值 {unknown}，只能取 model / app")
            # 旧取值 agent 与 model 等价，判定模型可见性时一并算上。
            if {"model", "agent"} & set(visibility):
                model_visible = True

        schema = tool.get("inputSchema")
        if not isinstance(schema, dict):
            report.error(f"{label} 缺少 inputSchema，CLI 无法校验入参")
        elif schema.get("type") != "object":
            report.error(f"{label} inputSchema.type 必须是 object")
        else:
            check_dispatch_parameter(report, label, schema)

    if tools and not model_visible:
        report.error("没有任何 tool 对模型可见，Agent 无法触发 UI 挂载")
    return tools


def check_python_handler(report: Report, label: str, path: Path, function: str) -> None:
    """静态检查函数入口，不执行或导入业务模块。返回内容由运行时验证。"""
    try:
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        report.error(f"{label} Python 文件无法解析：{exc}")
        return
    entries = [
        node for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function
    ]
    if not entries:
        report.error(f"{label} 缺少声明的同步函数 {function}(args)")
        return
    entry = entries[-1]
    if isinstance(entry, ast.AsyncFunctionDef):
        report.error(f"{label} {function}(args) 必须是同步函数，不支持 async")
        return
    args = entry.args
    positional = args.posonlyargs + args.args
    required_positional = len(positional) - len(args.defaults)
    required_keywords = any(default is None for default in args.kw_defaults)
    if required_positional > 1 or (not positional and args.vararg is None) or required_keywords:
        report.error(f"{label} {function} 必须能以一个位置参数调用：{function}(args)")


def check_built_ui(report: Report, root: Path, resources: dict) -> None:
    for uri, resource in resources.items():
        if resource.get("mimeType") == A2UI_MIME_TYPE:
            continue
        path = str(resource.get("path") or "")
        built = root / path
        if not built.is_file():
            continue
        html = built.read_text(encoding="utf-8", errors="replace")

        leftover = PLACEHOLDER_RE.search(html)
        if leftover:
            report.error(f"{path} 残留未替换的占位符 {leftover.group(0)}，请重新构建")
        if "ui/initialize" not in html:
            report.error(f"{path} 未内联 MCP bridge（找不到 ui/initialize），请先构建 UI")
        external = EXTERNAL_REF_RE.search(html)
        if external:
            snippet = re.sub(r"\s+", " ", external.group(0))
            report.error(f"{path} 从外部加载子资源：{snippet}…，iframe 的 CSP 会拦掉它")


def check_a2ui_cards(report: Report, root: Path, resources: dict) -> None:
    """A2UI 卡片的结构自检。

    只查在这里查得准、且错了会静默失败的几类：引擎对多数问题不报错，而是画出
    一张缺了内容的卡片，作者会以为是样式没写对。真正的协议校验交给工坊调试台，
    那里跑的就是端上同一个引擎。
    """
    declared = set(resources)
    for uri, resource in resources.items():
        if resource.get("mimeType") != A2UI_MIME_TYPE:
            continue
        path = str(resource.get("path") or "")
        card = root / path
        if not card.is_file():
            continue
        label = f"{path}"
        try:
            parsed = json.loads(card.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            report.error(f"{label} 不是合法 JSON：{error}")
            continue

        components = parsed.get("components") if isinstance(parsed, dict) else parsed
        if not isinstance(components, list) or not components:
            report.error(f'{label} 缺少非空的 components 数组，期望 {{"components": [ ... ]}}')
            continue
        # 顶层不该是完整的 A2UI 消息：surfaceId 与 catalogId 由宿主合成，
        # 作者写进来只会和宿主的值打架。
        if isinstance(parsed, dict):
            for key in ("version", "createSurface", "updateComponents", "updateDataModel", "messages"):
                if key in parsed:
                    report.error(f"{label} 顶层不该有 {key}：这份文件只放 components，其余由宿主合成")

        ids: set[str] = set()
        for index, component in enumerate(components):
            if not isinstance(component, dict):
                report.error(f"{label} components[{index}] 必须是对象")
                continue
            cid = str(component.get("id") or "")
            if not cid:
                report.error(f"{label} components[{index}] 缺少 id")
            elif cid in ids:
                report.error(f"{label} 组件 id 重复：{cid}")
            else:
                ids.add(cid)
            if not component.get("component"):
                report.error(f"{label} 组件 {cid or index} 缺少 component 类型")
        if "root" not in ids:
            report.error(f'{label} 没有 id 为 "root" 的组件，引擎从它开始渲染')

        # child / children 引用必须能解析，否则那一支会静默不画。
        for component in components:
            if not isinstance(component, dict):
                continue
            cid = component.get("id")
            referenced: list[str] = []
            child = component.get("child")
            if isinstance(child, str):
                referenced.append(child)
            children = component.get("children")
            if isinstance(children, list):
                referenced.extend(item for item in children if isinstance(item, str))
            elif isinstance(children, dict):
                # 动态列表：{"path": "/items", "componentId": "row"}
                item_id = children.get("componentId")
                if isinstance(item_id, str):
                    referenced.append(item_id)
                if not children.get("path"):
                    report.error(f"{label} 组件 {cid} 的 children 缺少 path，列表不会有数据")
            for target in referenced:
                if target not in ids:
                    report.error(f"{label} 组件 {cid} 引用了不存在的 {target}")

        # 转场目标必须在 resources 里声明过，否则宿主拿到 uri 也找不到文件。
        for component in components:
            if not isinstance(component, dict):
                continue
            event = (component.get("action") or {}).get("event") or {}
            if event.get("name") != OPEN_WORKSPACE_ACTION:
                continue
            target = (event.get("context") or {}).get("resourceUri")
            if not isinstance(target, str) or not target:
                # 写成数据绑定时静态查不出来，交给运行时，不误报。
                continue
            if target not in declared:
                report.error(
                    f"{label} 的 {OPEN_WORKSPACE_ACTION} 指向未声明的资源 {target}，"
                    "请在 app.yaml 的 resources[] 里补上"
                )
            elif resources[target].get("mimeType") == A2UI_MIME_TYPE:
                report.error(f"{label} 的 {OPEN_WORKSPACE_ACTION} 指向了另一张 A2UI 卡片，全屏工作区应当是 H5")


def check_skill_md(report: Report, skill_md: Path, app_id: str, tools: list[dict]) -> None:
    text = skill_md.read_text(encoding="utf-8")
    # 调用方式允许写在 references/ 里，SKILL.md 只做路由。
    docs = text + "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in sorted((skill_md.parent / "references").glob("*.md"))
    )

    if f"app {app_id} describe" not in docs:
        report.error(f"未告诉 Agent 用 `app {app_id} describe` 查 schema")

    for tool in tools:
        name = str(tool.get("name") or "")
        visibility = ((tool.get("_meta") or {}).get("ui") or {}).get("visibility")
        if visibility is not None and not {"model", "agent"} & set(visibility):
            continue
        if f"app {app_id} {name}" not in docs:
            report.error(f"未说明模型可见工具 {name!r} 的调用方式")

    handlers = [
        Path(str((tool.get("handler") or {}).get("path") or "")).name
        for tool in tools
        if isinstance(tool.get("handler"), dict)
    ]
    for handler in handlers:
        if not handler:
            continue
        # 直跑 handler 不经 CLI，UI 拿不到数据、不会刷新。
        if re.search(rf"python3[^\n]*{re.escape(handler)}", docs):
            report.error(f"文档里教了直接执行 {handler}，绕过 CLI 后 UI 不会刷新")


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """返回 (字段表, 解析错误)。区分两者是为了不把 YAML 语法错误报成「缺少 name」。"""
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, "缺少 --- 包裹的 frontmatter"
    try:
        data = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        return {}, str(exc).replace("\n", " ")
    if not isinstance(data, dict):
        return {}, "frontmatter 根节点必须是对象"
    return (
        {key: str(value) for key, value in data.items() if isinstance(value, (str, int, float))},
        "",
    )


if __name__ == "__main__":
    raise SystemExit(main())
