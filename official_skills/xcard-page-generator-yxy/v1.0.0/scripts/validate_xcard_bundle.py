#!/usr/bin/env python3
"""Validate XCard A2UI v1.0 JSONL, templates, bindings, and token overlays."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from xcard_resources import (
    DuplicateKeyError,
    catalog_functions,
    discover_resources,
    load_json,
    load_json_text,
    merge_component_catalogs,
    merge_function_catalogs,
    normalize_token_name,
    unique_paths,
)


MESSAGE_KEYS = {
    "createSurface",
    "updateComponents",
    "updateDataModel",
    "deleteSurface",
    "callRendererFunction",
    "agentFunctionResponse",
}
MESSAGE_SCHEMA_NAMES = {
    "createSurface": "CreateSurfaceMessage",
    "updateComponents": "UpdateComponentsMessage",
    "updateDataModel": "UpdateDataModelMessage",
    "deleteSurface": "DeleteSurfaceMessage",
    "callRendererFunction": "CallRendererFunctionMessage",
    "agentFunctionResponse": "AgentFunctionResponseMessage",
}
COMMON_COMPONENT_KEYS = {
    "id",
    "component",
    "catalogId",
    "accessibility",
    "metadata",
}
COLOR_STYLE_KEYS = {"color", "tint", "containerColor"}
REFERENCE_KEYS = {"child", "trigger", "content"}
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{8}$")
TOKEN_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class Issue:
    severity: str
    location: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "location": self.location,
            "message": self.message,
        }


def _is_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def _schema_errors(value: Any, schema: Any, location: str) -> list[str]:
    if not isinstance(schema, dict):
        return []
    if "$ref" in schema and len(schema) == 1:
        return []

    for keyword in ("allOf",):
        if isinstance(schema.get(keyword), list):
            errors: list[str] = []
            for branch in schema[keyword]:
                errors.extend(_schema_errors(value, branch, location))
            if errors:
                return errors

    for keyword in ("anyOf", "oneOf"):
        branches = schema.get(keyword)
        if isinstance(branches, list):
            branch_results = [
                _schema_errors(value, branch, location) for branch in branches
            ]
            if any(not result for result in branch_results):
                break
            return [
                f"{location}: value does not match any allowed {keyword} branch"
            ]

    expected_type = schema.get("type")
    if isinstance(expected_type, list):
        if not any(_is_type(value, item) for item in expected_type):
            return [f"{location}: expected one of {expected_type}"]
    elif isinstance(expected_type, str) and not _is_type(value, expected_type):
        return [f"{location}: expected {expected_type}, got {type(value).__name__}"]

    if "const" in schema and value != schema["const"]:
        return [f"{location}: expected constant {schema['const']!r}"]
    if isinstance(schema.get("enum"), list) and value not in schema["enum"]:
        return [f"{location}: {value!r} is not in {schema['enum']!r}"]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        if isinstance(minimum, (int, float)) and value < minimum:
            return [f"{location}: {value} is below minimum {minimum}"]
    if isinstance(value, str) and isinstance(schema.get("pattern"), str):
        if re.fullmatch(schema["pattern"], value) is None:
            return [
                f"{location}: {value!r} does not match {schema['pattern']!r}"
            ]

    errors: list[str] = []
    if isinstance(value, dict):
        required = schema.get("required", [])
        if isinstance(required, list):
            for key in required:
                if key not in value:
                    errors.append(f"{location}: missing required property {key!r}")

        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            properties = {}
        additional = schema.get(
            "additionalProperties",
            schema.get("unevaluatedProperties", True),
        )
        for key, item in value.items():
            if key in properties:
                errors.extend(
                    _schema_errors(item, properties[key], f"{location}.{key}")
                )
            elif additional is False:
                errors.append(f"{location}: unsupported property {key!r}")
            elif isinstance(additional, dict):
                errors.extend(
                    _schema_errors(item, additional, f"{location}.{key}")
                )

    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            errors.extend(
                _schema_errors(item, schema["items"], f"{location}[{index}]")
            )

    prohibited = schema.get("not")
    if isinstance(prohibited, dict):
        if not _schema_errors(value, prohibited, location):
            errors.append(f"{location}: matches a prohibited schema")
    return errors


def _collect_enum_strings(node: Any) -> set[str]:
    values: set[str] = set()
    if isinstance(node, dict):
        enum = node.get("enum")
        if isinstance(enum, list):
            values.update(item for item in enum if isinstance(item, str))
        for value in node.values():
            values.update(_collect_enum_strings(value))
    elif isinstance(node, list):
        for value in node:
            values.update(_collect_enum_strings(value))
    return values


def _walk(node: Any, location: str) -> Iterable[tuple[Any, str]]:
    yield node, location
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, f"{location}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, f"{location}[{index}]")


def _component_references(component: dict[str, Any]) -> set[str]:
    references: set[str] = set()
    for key in REFERENCE_KEYS:
        value = component.get(key)
        if isinstance(value, str):
            references.add(value)

    children = component.get("children")
    if isinstance(children, list):
        references.update(item for item in children if isinstance(item, str))
    elif isinstance(children, dict):
        component_id = children.get("componentId")
        if isinstance(component_id, str):
            references.add(component_id)

    tabs = component.get("tabs")
    if isinstance(tabs, list):
        for tab in tabs:
            if isinstance(tab, dict) and isinstance(tab.get("child"), str):
                references.add(tab["child"])
    return references


class BundleValidator:
    def __init__(
        self,
        resource_root: Path | None,
        repo_root: Path | None,
        allow_components: set[str],
    ) -> None:
        self.resources = discover_resources(resource_root, repo_root)
        missing = self.resources.missing_required()
        if missing:
            raise SystemExit(
                "Missing required XCard resources: "
                + ", ".join(missing)
                + ". Pass --resource-root or set XCARD_RESOURCE_ROOT."
            )

        assert self.resources.basic_catalog
        assert self.resources.xcard_catalog
        assert self.resources.tokens
        self.basic_catalog = load_json(self.resources.basic_catalog)
        self.xcard_catalog = load_json(self.resources.xcard_catalog)
        self.common_types = (
            load_json(self.resources.common_types)
            if self.resources.common_types
            else None
        )
        self.component_schemas = merge_component_catalogs(
            self.basic_catalog,
            self.xcard_catalog,
            self.common_types,
        )
        self.function_schemas = merge_function_catalogs(
            self.basic_catalog,
            self.xcard_catalog,
            self.common_types,
        )
        self.agent_schema = (
            load_json(self.resources.agent_schema)
            if self.resources.agent_schema
            else {}
        )
        self.message_schemas = self.agent_schema.get("$defs", {})
        self.allowed_components = set(self.component_schemas) | allow_components
        self.functions = catalog_functions(self.basic_catalog, self.xcard_catalog)
        self.base_tokens = load_json(self.resources.tokens)
        self.base_colors = set(self.base_tokens.get("colors", {}))
        self.base_shapes = set(self.base_tokens.get("shape", {}))
        self.base_typography = set(self.base_tokens.get("typography", {}))
        self.base_images = set(self.base_tokens.get("image", {}))
        self.colors = set(self.base_colors)
        self.shapes = set(self.base_shapes)
        self.typography = set(self.base_typography)
        self.images = set(self.base_images)
        icon_assets = self.base_tokens.get("icons", {}).get("assets", {})
        self.icons = {
            normalize_token_name(name)
            for name in set(icon_assets) | set(icon_assets.values())
        }
        basic_icon_schema = (
            self.basic_catalog.get("components", {})
            .get("Icon", {})
            .get("properties", {})
            .get("name", {})
        )
        self.icons.update(
            normalize_token_name(name)
            for name in _collect_enum_strings(basic_icon_schema)
        )
        self.issues: list[Issue] = []

    def error(self, location: str, message: str) -> None:
        self.issues.append(Issue("error", location, message))

    def warning(self, location: str, message: str) -> None:
        self.issues.append(Issue("warning", location, message))

    def _apply_overlay(self, overlay: dict[str, Any]) -> None:
        self.colors.update(set(overlay.get("colors", {})) & self.base_colors)
        self.shapes.update(set(overlay.get("shape", {})) & self.base_shapes)
        self.typography.update(
            set(overlay.get("typography", {})) & self.base_typography
        )
        self.images.update(set(overlay.get("image", {})) & self.base_images)
        icon_assets = overlay.get("icons", {}).get("assets", {})
        base_icon_assets = self.base_tokens.get("icons", {}).get("assets", {})
        self.icons.update(
            normalize_token_name(name)
            for name in (
                (set(icon_assets) & set(base_icon_assets))
                | {
                    value
                    for key, value in icon_assets.items()
                    if key in base_icon_assets
                }
            )
        )

    def _token_snapshot(
        self,
    ) -> tuple[set[str], set[str], set[str], set[str], set[str]]:
        return (
            set(self.colors),
            set(self.shapes),
            set(self.typography),
            set(self.images),
            set(self.icons),
        )

    def _restore_tokens(
        self,
        snapshot: tuple[set[str], set[str], set[str], set[str], set[str]],
    ) -> None:
        (
            self.colors,
            self.shapes,
            self.typography,
            self.images,
            self.icons,
        ) = snapshot

    def validate_token_overlay(
        self,
        path: Path,
        overlay: dict[str, Any] | None = None,
    ) -> None:
        location = str(path)
        if overlay is None:
            try:
                overlay = load_json(path)
            except (OSError, ValueError, DuplicateKeyError) as error:
                self.error(location, str(error))
                return
        if not isinstance(overlay, dict):
            self.error(location, "token overlay root must be an object")
            return

        allowed_groups = {"colors", "typography", "shape", "image", "icons"}
        for key in overlay:
            if key not in allowed_groups:
                self.error(location, f"unsupported token group {key!r}")

        colors = overlay.get("colors", {})
        if not isinstance(colors, dict):
            self.error(f"{location}.colors", "must be an object")
        else:
            for name, modes in colors.items():
                if not TOKEN_NAME_RE.fullmatch(name):
                    self.error(
                        f"{location}.colors.{name}",
                        "token name must be an identifier",
                    )
                if name not in self.base_colors:
                    self.error(
                        f"{location}.colors.{name}",
                        "overlay can only override an existing color token",
                    )
                if not isinstance(modes, dict):
                    self.error(f"{location}.colors.{name}", "must be an object")
                    continue
                for mode in ("light", "dark"):
                    value = modes.get(mode)
                    if not isinstance(value, str) or not HEX_COLOR_RE.fullmatch(value):
                        self.error(
                            f"{location}.colors.{name}.{mode}",
                            "expected #RRGGBBAA",
                        )

        typography = overlay.get("typography", {})
        if not isinstance(typography, dict):
            self.error(f"{location}.typography", "must be an object")
        else:
            known_colors = self.base_colors
            for name, value in typography.items():
                if name != name.lower():
                    self.error(
                        f"{location}.typography.{name}",
                        "typography keys must be lowercase because variants are normalized by the renderer",
                    )
                if name not in self.base_typography:
                    self.error(
                        f"{location}.typography.{name}",
                        "overlay can only override an existing typography token",
                    )
                if not isinstance(value, dict):
                    self.error(
                        f"{location}.typography.{name}",
                        "must be an object",
                    )
                    continue
                for field in ("size", "weight", "lineHeight"):
                    if field in value and (
                        not isinstance(value[field], (int, float))
                        or isinstance(value[field], bool)
                        or value[field] < 0
                    ):
                        self.error(
                            f"{location}.typography.{name}.{field}",
                            "must be a non-negative number",
                        )
                color = value.get("color")
                if isinstance(color, str) and color not in known_colors:
                    self.error(
                        f"{location}.typography.{name}.color",
                        f"unknown color token {color!r}",
                    )

        for group, base_keys in (
            ("shape", self.base_shapes),
            ("image", self.base_images),
        ):
            value = overlay.get(group, {})
            if value is not None and not isinstance(value, dict):
                self.error(f"{location}.{group}", "must be an object")
            elif isinstance(value, dict):
                for name in value:
                    if name not in base_keys:
                        self.error(
                            f"{location}.{group}.{name}",
                            f"overlay can only override an existing {group} token",
                        )

        icons = overlay.get("icons", {})
        if icons is not None and not isinstance(icons, dict):
            self.error(f"{location}.icons", "must be an object")
        elif isinstance(icons, dict):
            base_icons = self.base_tokens.get("icons", {})
            for group, values in icons.items():
                if group not in base_icons:
                    self.error(
                        f"{location}.icons.{group}",
                        "overlay can only override an existing icon group",
                    )
                    continue
                if not isinstance(values, dict):
                    self.error(
                        f"{location}.icons.{group}",
                        "must be an object",
                    )
                    continue
                base_values = base_icons.get(group, {})
                for name in values:
                    if name not in base_values:
                        self.error(
                            f"{location}.icons.{group}.{name}",
                            "overlay can only override an existing icon token",
                        )

    def _validate_binding_paths(
        self,
        component: dict[str, Any],
        location: str,
        template_mode: bool,
    ) -> None:
        for node, node_location in _walk(component, location):
            if not isinstance(node, dict) or not isinstance(node.get("path"), str):
                continue
            path = node["path"]
            if not path:
                self.error(f"{node_location}.path", "binding path must not be empty")
                continue
            if template_mode and path.startswith("/"):
                self.error(
                    f"{node_location}.path",
                    "template bindings must be relative to the template instance",
                )
            if "." in path:
                self.error(
                    f"{node_location}.path",
                    "use '/' path segments instead of dotted binding syntax",
                )

    def _validate_function_call(
        self,
        node: Any,
        location: str,
        allow_unknown: bool,
    ) -> None:
        if not isinstance(node, dict) or not isinstance(node.get("call"), str):
            self.error(location, "function call must contain a string call")
            return
        call = node["call"]
        schema = self.function_schemas.get(call)
        if schema is None:
            if not allow_unknown:
                self.error(
                    f"{location}.call",
                    f"function {call!r} is not declared by the active catalogs",
                )
                return
            unknown = set(node) - {"call", "catalogId", "args"}
            if unknown:
                self.error(
                    location,
                    f"unsupported functionCall properties: {sorted(unknown)}",
                )
            if "catalogId" in node and not isinstance(node["catalogId"], str):
                self.error(f"{location}.catalogId", "must be a string")
            if "args" in node and not isinstance(node["args"], dict):
                self.error(f"{location}.args", "must be an object")
            return
        for message in _schema_errors(node, schema, location):
            self.error(location, message.removeprefix(f"{location}: "))

    def _validate_calls(self, component: dict[str, Any], location: str) -> None:
        for node, node_location in _walk(component, location):
            if not isinstance(node, dict) or not isinstance(node.get("call"), str):
                continue
            if node_location.endswith(".action.functionCall"):
                continue
            self._validate_function_call(
                node,
                node_location,
                allow_unknown=False,
            )

    def _validate_action(self, component: dict[str, Any], location: str) -> None:
        action = component.get("action")
        if action is None:
            return
        if not isinstance(action, dict):
            self.error(f"{location}.action", "must be an object")
            return
        branches = [key for key in ("event", "functionCall") if key in action]
        if len(branches) != 1 or len(action) != 1:
            self.error(
                f"{location}.action",
                "must contain exactly one of event or functionCall",
            )
            return
        if "event" in action:
            event = action["event"]
            if not isinstance(event, dict):
                self.error(
                    f"{location}.action.event",
                    "must be an object",
                )
                return
            unknown = set(event) - {"name", "userMessage", "context"}
            if unknown:
                self.error(
                    f"{location}.action.event",
                    f"unsupported event properties: {sorted(unknown)}",
                )
            if not isinstance(event.get("name"), str) or not event["name"]:
                self.error(
                    f"{location}.action.event.name",
                    "must be a non-empty string",
                )
            if "context" in event and not isinstance(event["context"], dict):
                self.error(
                    f"{location}.action.event.context",
                    "must be an object",
                )
        else:
            function_call = action["functionCall"]
            self._validate_function_call(
                function_call,
                f"{location}.action.functionCall",
                allow_unknown=True,
            )

    def _validate_checks(self, component: dict[str, Any], location: str) -> None:
        checks = component.get("checks")
        if checks is None:
            return
        if not isinstance(checks, list):
            self.error(f"{location}.checks", "must be an array")
            return
        for index, check in enumerate(checks):
            check_location = f"{location}.checks[{index}]"
            if not isinstance(check, dict):
                self.error(check_location, "must be an object")
                continue
            unknown = set(check) - {"condition", "message"}
            if unknown:
                self.error(
                    check_location,
                    f"unsupported check properties: {sorted(unknown)}",
                )
            condition = check.get("condition")
            if not isinstance(condition, dict):
                self.error(
                    f"{check_location}.condition",
                    "must be a data binding or function call",
                )
            elif "path" in condition:
                if set(condition) != {"path"} or not isinstance(
                    condition["path"], str
                ):
                    self.error(
                        f"{check_location}.condition",
                        "data binding must contain only a string path",
                    )
            elif "call" not in condition:
                self.error(
                    f"{check_location}.condition",
                    "must contain path or call",
                )
            if "message" in check and not isinstance(check["message"], str):
                self.error(f"{check_location}.message", "must be a string")

    def _validate_style_tokens(
        self,
        component: dict[str, Any],
        location: str,
    ) -> None:
        style = component.get("style")
        if not isinstance(style, dict) or "path" in style or "call" in style:
            return
        for key in COLOR_STYLE_KEYS:
            value = style.get(key)
            if isinstance(value, str) and value not in self.colors:
                self.error(
                    f"{location}.style.{key}",
                    f"unknown color token {value!r}",
                )
        shape = style.get("shape")
        if isinstance(shape, str) and shape not in self.shapes:
            self.error(
                f"{location}.style.shape",
                f"unknown shape token {shape!r}",
            )

    def _validate_component(
        self,
        component: Any,
        location: str,
        template_mode: bool,
    ) -> None:
        if not isinstance(component, dict):
            self.error(location, "component must be an object")
            return
        component_id = component.get("id")
        component_type = component.get("component")
        if not isinstance(component_id, str) or not component_id:
            self.error(f"{location}.id", "component id must be a non-empty string")
        if not isinstance(component_type, str) or not component_type:
            self.error(
                f"{location}.component",
                "component type must be a non-empty string",
            )
            return
        if component_type not in self.allowed_components:
            self.error(
                f"{location}.component",
                f"component {component_type!r} is not declared by the active catalogs",
            )
            return

        schema = self.component_schemas.get(component_type)
        if schema:
            for message in _schema_errors(component, schema, location):
                self.error(location, message.removeprefix(f"{location}: "))
        else:
            unknown = set(component) - COMMON_COMPONENT_KEYS
            if unknown:
                self.warning(
                    location,
                    f"custom component fields were not schema-checked: {sorted(unknown)}",
                )

        self._validate_binding_paths(component, location, template_mode)
        self._validate_calls(component, location)
        self._validate_action(component, location)
        self._validate_checks(component, location)
        self._validate_style_tokens(component, location)

        if component_type in {"Button", "Clickable"}:
            if "action" not in component:
                self.error(f"{location}.action", "interactive component needs an action")
        if component_type == "A2UITemplate":
            template_id = component.get("templateId")
            version = component.get("template_version")
            if isinstance(template_id, str) and not isinstance(version, str):
                self.error(
                    f"{location}.template_version",
                    "template_version is required when templateId is literal",
                )
        if component_type == "Icon":
            name = component.get("name")
            if isinstance(name, str) and normalize_token_name(name) not in self.icons:
                self.error(
                    f"{location}.name",
                    f"unknown icon {name!r}; use a catalog or Yuanbao token icon",
                )
        if component_type == "IconButton":
            name = component.get("name")
            if isinstance(name, str) and normalize_token_name(name) not in self.icons:
                self.error(
                    f"{location}.name",
                    f"unknown icon {name!r}; use a catalog or Yuanbao token icon",
                )

    def _validate_component_set(
        self,
        components: Any,
        location: str,
        template_mode: bool,
    ) -> dict[str, dict[str, Any]]:
        if not isinstance(components, list) or not components:
            self.error(location, "components must be a non-empty array")
            return {}

        result: dict[str, dict[str, Any]] = {}
        for index, component in enumerate(components):
            component_location = f"{location}[{index}]"
            self._validate_component(component, component_location, template_mode)
            if not isinstance(component, dict):
                continue
            component_id = component.get("id")
            if not isinstance(component_id, str):
                continue
            if component_id in result:
                self.error(component_location, f"duplicate component id {component_id!r}")
            result[component_id] = component
        return result

    def _validate_final_tree(
        self,
        components: dict[str, dict[str, Any]],
        location: str,
    ) -> None:
        if "root" not in components:
            self.error(location, "final component state must contain id='root'")
        for component_id, component in components.items():
            for reference in _component_references(component):
                if reference not in components:
                    self.error(
                        f"{location}.{component_id}",
                        f"references missing child component {reference!r}",
                    )

    def _extract_template_refs(
        self,
        messages: list[dict[str, Any]],
    ) -> set[tuple[str, str]]:
        references: set[tuple[str, str]] = set()
        for message in messages:
            payload = message.get("updateComponents") or message.get("createSurface")
            if not isinstance(payload, dict):
                continue
            for component in payload.get("components", []):
                if (
                    isinstance(component, dict)
                    and component.get("component") == "A2UITemplate"
                    and isinstance(component.get("templateId"), str)
                    and isinstance(component.get("template_version"), str)
                ):
                    references.add(
                        (component["templateId"], component["template_version"])
                    )
        return references

    def _find_template(
        self,
        template_id: str,
        version: str,
        extra_roots: Iterable[Path],
    ) -> Path | None:
        roots = unique_paths((*extra_roots, *self.resources.template_dirs))
        normalized_id = normalize_token_name(template_id)
        for root in roots:
            direct = root / template_id / f"{version}.json"
            if direct.is_file():
                return direct
            for candidate_dir in root.iterdir() if root.is_dir() else ():
                if (
                    candidate_dir.is_dir()
                    and normalize_token_name(candidate_dir.name) == normalized_id
                ):
                    candidate = candidate_dir / f"{version}.json"
                    if candidate.is_file():
                        return candidate
        return None

    def validate_template(
        self,
        path: Path,
        data: dict[str, Any] | None = None,
    ) -> None:
        location = str(path)
        if data is None:
            try:
                data = load_json(path)
            except (OSError, ValueError, DuplicateKeyError) as error:
                self.error(location, str(error))
                return
        if not isinstance(data, dict):
            self.error(location, "template root must be an object")
            return
        if data.get("version") != "v1.0":
            self.error(f"{location}.version", "template version must be v1.0")
        update = data.get("updateComponents")
        if not isinstance(update, dict):
            self.error(location, "template must contain updateComponents")
            return
        if update.get("surfaceId") != "template":
            self.error(
                f"{location}.updateComponents.surfaceId",
                "template surfaceId must be 'template'",
            )
        components = self._validate_component_set(
            update.get("components"),
            f"{location}.updateComponents.components",
            template_mode=True,
        )
        self._validate_final_tree(components, location)

    def validate_jsonl(self, path: Path) -> None:
        location = str(path)
        try:
            raw_lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as error:
            self.error(location, str(error))
            return

        messages: list[dict[str, Any]] = []
        for line_number, line in enumerate(raw_lines, start=1):
            if not line.strip():
                continue
            try:
                message = load_json_text(line)
            except (ValueError, DuplicateKeyError) as error:
                self.error(f"{location}:{line_number}", str(error))
                continue
            if not isinstance(message, dict):
                self.error(
                    f"{location}:{line_number}",
                    "each JSONL line must be an object",
                )
                continue
            messages.append(message)

        if not messages:
            self.error(location, "JSONL must contain at least one message")
            return

        local_template_root = path.parent / "templates"
        if path.parent.name == "gallery":
            local_template_root = path.parent.parent / "templates"

        token_snapshot = self._token_snapshot()
        try:
            for template_id, version in self._extract_template_refs(messages):
                template_path = self._find_template(
                    template_id,
                    version,
                    (local_template_root,),
                )
                if template_path is None:
                    self.error(
                        location,
                        f"missing template {template_id}@{version}",
                    )
                    continue
                overlay_path = template_path.with_name(f"{version}.tokens.json")
                if overlay_path.is_file():
                    try:
                        overlay = load_json(overlay_path)
                    except (OSError, ValueError, DuplicateKeyError) as error:
                        self.error(str(overlay_path), str(error))
                    else:
                        self.validate_token_overlay(overlay_path, overlay)
                        self._apply_overlay(overlay)
                self.validate_template(template_path)

            created_surfaces: set[str] = set()
            surface_components: dict[str, dict[str, dict[str, Any]]] = {}

            for index, message in enumerate(messages, start=1):
                message_location = f"{location}:{index}"
                if message.get("version") != "v1.0":
                    self.error(f"{message_location}.version", "must be v1.0")
                payload_keys = [key for key in MESSAGE_KEYS if key in message]
                if len(payload_keys) != 1:
                    self.error(
                        message_location,
                        "must contain exactly one A2UI message payload",
                    )
                    continue
                if set(message) != {"version", payload_keys[0]}:
                    self.error(
                        message_location,
                        f"unsupported top-level keys: {sorted(set(message) - {'version', payload_keys[0]})}",
                    )

                message_key = payload_keys[0]
                schema_name = MESSAGE_SCHEMA_NAMES.get(message_key)
                message_schema = (
                    self.message_schemas.get(schema_name)
                    if schema_name
                    else None
                )
                if isinstance(message_schema, dict):
                    for schema_error in _schema_errors(
                        message,
                        message_schema,
                        message_location,
                    ):
                        self.error(
                            message_location,
                            schema_error.removeprefix(f"{message_location}: "),
                        )
                payload = message[message_key]
                if not isinstance(payload, dict):
                    self.error(
                        f"{message_location}.{message_key}",
                        "must be an object",
                    )
                    continue

                surface_id = payload.get("surfaceId")
                if message_key in {
                    "createSurface",
                    "updateComponents",
                    "updateDataModel",
                    "deleteSurface",
                } and (not isinstance(surface_id, str) or not surface_id):
                    self.error(
                        f"{message_location}.{message_key}.surfaceId",
                        "must be a non-empty string",
                    )
                    continue

                if message_key == "createSurface":
                    if surface_id in created_surfaces:
                        self.error(
                            message_location,
                            f"surface {surface_id!r} is created more than once",
                        )
                    created_surfaces.add(surface_id)
                    surface_components.setdefault(surface_id, {})
                    catalog_id = payload.get("catalogId")
                    known_catalog_ids = {
                        self.basic_catalog.get("catalogId"),
                        self.xcard_catalog.get("catalogId"),
                    }
                    if (
                        isinstance(catalog_id, str)
                        and catalog_id not in known_catalog_ids
                    ):
                        self.warning(
                            f"{message_location}.createSurface.catalogId",
                            f"catalog {catalog_id!r} is not one of the discovered catalogs",
                        )
                    if "components" in payload:
                        inline = self._validate_component_set(
                            payload["components"],
                            f"{message_location}.createSurface.components",
                            template_mode=False,
                        )
                        surface_components[surface_id].update(inline)

                elif message_key == "updateComponents":
                    if surface_id not in created_surfaces:
                        self.error(
                            message_location,
                            f"updateComponents precedes createSurface for {surface_id!r}",
                        )
                    updated = self._validate_component_set(
                        payload.get("components"),
                        f"{message_location}.updateComponents.components",
                        template_mode=False,
                    )
                    surface_components.setdefault(surface_id, {}).update(updated)

                elif message_key == "updateDataModel":
                    if surface_id not in created_surfaces:
                        self.error(
                            message_location,
                            f"updateDataModel precedes createSurface for {surface_id!r}",
                        )
                    if "value" not in payload:
                        self.error(
                            f"{message_location}.updateDataModel",
                            "value is required; use null to delete",
                        )
                    path_value = payload.get("path")
                    if path_value is not None and (
                        not isinstance(path_value, str)
                        or (path_value != "/" and not path_value.startswith("/"))
                    ):
                        self.error(
                            f"{message_location}.updateDataModel.path",
                            "must be '/' or an absolute JSON Pointer",
                        )

                elif message_key == "deleteSurface":
                    if surface_id not in created_surfaces:
                        self.error(
                            message_location,
                            f"deleteSurface references unknown surface {surface_id!r}",
                        )
                    created_surfaces.discard(surface_id)

            for surface_id, components in surface_components.items():
                self._validate_final_tree(
                    components,
                    f"{location} surface {surface_id}",
                )
        finally:
            self._restore_tokens(token_snapshot)

    def validate_target(self, target: Path) -> None:
        target = target.expanduser().resolve()
        if target.is_file():
            if target.name.endswith(".tokens.json"):
                self.validate_token_overlay(target)
            elif target.suffix == ".jsonl":
                self.validate_jsonl(target)
            elif target.suffix == ".json":
                token_snapshot = self._token_snapshot()
                overlay_path = target.with_name(f"{target.stem}.tokens.json")
                if overlay_path.is_file():
                    try:
                        overlay = load_json(overlay_path)
                    except (OSError, ValueError, DuplicateKeyError) as error:
                        self.error(str(overlay_path), str(error))
                    else:
                        self.validate_token_overlay(overlay_path, overlay)
                        self._apply_overlay(overlay)
                try:
                    self.validate_template(target)
                finally:
                    self._restore_tokens(token_snapshot)
            else:
                self.error(str(target), "expected .jsonl or .json")
            return

        if not target.is_dir():
            self.error(str(target), "target does not exist")
            return

        jsonl_files = sorted(target.rglob("*.jsonl"))
        template_files = sorted(
            path
            for path in target.rglob("*.json")
            if not path.name.endswith(".tokens.json")
            and "templates" in path.parts
        )
        token_files = sorted(target.rglob("*.tokens.json"))
        if not jsonl_files and not template_files and not token_files:
            self.error(str(target), "no XCard bundle files found")
            return
        for token_file in token_files:
            self.validate_token_overlay(token_file)
        for template_file in template_files:
            token_snapshot = self._token_snapshot()
            overlay_path = template_file.with_name(
                f"{template_file.stem}.tokens.json"
            )
            if overlay_path.is_file():
                try:
                    overlay = load_json(overlay_path)
                except (OSError, ValueError, DuplicateKeyError) as error:
                    self.error(str(overlay_path), str(error))
                else:
                    self._apply_overlay(overlay)
            try:
                self.validate_template(template_file)
            finally:
                self._restore_tokens(token_snapshot)
        for jsonl_file in jsonl_files:
            self.validate_jsonl(jsonl_file)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path)
    parser.add_argument("--resource-root", type=Path)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument(
        "--allow-component",
        action="append",
        default=[],
        help="Allow a host component not present in the static catalogs.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    validator = BundleValidator(
        args.resource_root,
        args.repo_root,
        set(args.allow_component),
    )
    validator.validate_target(args.target)
    errors = [issue for issue in validator.issues if issue.severity == "error"]

    if args.json:
        print(
            json.dumps(
                {
                    "ok": not errors,
                    "issues": [issue.as_dict() for issue in validator.issues],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for issue in validator.issues:
            print(
                f"{issue.severity.upper()}: {issue.location}: {issue.message}"
            )
        if errors:
            print(f"FAILED: {len(errors)} error(s)")
        else:
            print(
                f"OK: {args.target} ({len(validator.issues)} warning(s))"
            )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
