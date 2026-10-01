#!/usr/bin/env python3
"""Shared resource discovery helpers for the XCard page generator skill."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


class DuplicateKeyError(ValueError):
    """Raised when JSON contains duplicate object keys."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
    )


def load_json_text(text: str) -> Any:
    return json.loads(text, object_pairs_hook=_reject_duplicate_keys)


def unique_paths(paths: Iterable[Path | None]) -> tuple[Path, ...]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        if path is None:
            continue
        resolved = path.expanduser().resolve()
        key = str(resolved)
        if key in seen or not resolved.exists():
            continue
        seen.add(key)
        result.append(resolved)
    return tuple(result)


def find_repo_root(start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).expanduser().resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


@dataclass(frozen=True)
class ResourcePaths:
    repo_root: Path | None
    basic_catalog: Path | None
    xcard_catalog: Path | None
    common_types: Path | None
    agent_schema: Path | None
    tokens: Path | None
    gallery_dirs: tuple[Path, ...]
    template_dirs: tuple[Path, ...]
    icon_dirs: tuple[Path, ...]

    def missing_required(self) -> list[str]:
        missing: list[str] = []
        for name in ("basic_catalog", "xcard_catalog", "tokens"):
            if getattr(self, name) is None:
                missing.append(name)
        return missing


@dataclass(frozen=True)
class _Layout:
    basic_catalog: Path | None = None
    xcard_catalog: Path | None = None
    common_types: Path | None = None
    agent_schema: Path | None = None
    tokens: Path | None = None
    gallery_dirs: tuple[Path, ...] = ()
    template_dirs: tuple[Path, ...] = ()
    icon_dirs: tuple[Path, ...] = ()


def _file(path: Path) -> Path | None:
    return path if path.is_file() else None


def _dir(path: Path) -> Path | None:
    return path if path.is_dir() else None


def _first_file(*paths: Path) -> Path | None:
    return next((path for path in paths if path.is_file()), None)


def _layout_from_resource_root(root: Path) -> _Layout:
    root = root.expanduser().resolve()

    if (root / "specification" / "v1_0").is_dir():
        specification = root / "specification" / "v1_0"
        token_file = root / "yuanbao" / "tokens.json"
        gallery_dirs = unique_paths((root, root / "gallery"))
        template_dirs = unique_paths((root / "templates",))
        icon_dirs = unique_paths((root / "yuanbao" / "icons",))
    elif (root / "catalogs" / "basic" / "catalog.json").is_file():
        specification = root
        token_file = root.parent.parent / "tokens" / "yuanbao" / "tokens.json"
        gallery_dirs = ()
        template_dirs = ()
        icon_dirs = ()
    else:
        specification = root
        token_file = root / "tokens.json"
        gallery_dirs = unique_paths((root / "gallery",))
        template_dirs = unique_paths((root / "templates",))
        icon_dirs = unique_paths((root / "icons",))

    return _Layout(
        basic_catalog=_file(specification / "catalogs" / "basic" / "catalog.json"),
        xcard_catalog=_file(specification / "catalogs" / "xcard" / "catalog.json"),
        common_types=_first_file(
            specification / "json" / "common_types.json",
            specification / "common_types.json",
        ),
        agent_schema=_first_file(
            specification / "json" / "agent_to_renderer.json",
            specification / "agent_to_renderer.json",
        ),
        tokens=_file(token_file),
        gallery_dirs=gallery_dirs,
        template_dirs=template_dirs,
        icon_dirs=icon_dirs,
    )


def _layout_from_repo(repo_root: Path) -> _Layout:
    yuanbao_root = repo_root.parent
    dtmx_root = yuanbao_root / "dtmx"
    schema_root = dtmx_root / "a2ui" / "cpp" / "schemas" / "v1_0"
    ios_resources = (
        repo_root
        / "App"
        / "iOS"
        / "LocalPods"
        / "XCardDemo"
        / "DemoResources"
    )
    android_resources = (
        repo_root
        / "App"
        / "Android"
        / "module"
        / "debug"
        / "src"
        / "androidMain"
        / "assets"
    )
    token_root = dtmx_root / "a2ui" / "tokens" / "yuanbao"

    return _Layout(
        basic_catalog=_file(schema_root / "catalogs" / "basic" / "catalog.json"),
        xcard_catalog=_file(schema_root / "catalogs" / "xcard" / "catalog.json"),
        common_types=_first_file(
            schema_root / "json" / "common_types.json",
            schema_root / "common_types.json",
        ),
        agent_schema=_first_file(
            schema_root / "json" / "agent_to_renderer.json",
            schema_root / "agent_to_renderer.json",
        ),
        tokens=_file(token_root / "tokens.json"),
        gallery_dirs=unique_paths(
            (
                _dir(ios_resources / "gallery"),
                _dir(android_resources / "gallery"),
            )
        ),
        template_dirs=unique_paths(
            (
                _dir(ios_resources / "templates"),
                _dir(android_resources / "templates"),
            )
        ),
        icon_dirs=unique_paths((_dir(token_root / "icons"),)),
    )


def discover_resources(
    resource_root: Path | None = None,
    repo_root: Path | None = None,
) -> ResourcePaths:
    layouts: list[_Layout] = []

    explicit_root = resource_root
    if explicit_root is None and os.environ.get("XCARD_RESOURCE_ROOT"):
        explicit_root = Path(os.environ["XCARD_RESOURCE_ROOT"])
    if explicit_root is not None:
        layouts.append(_layout_from_resource_root(explicit_root))

    resolved_repo = repo_root.expanduser().resolve() if repo_root else find_repo_root()
    if resolved_repo:
        layouts.append(_layout_from_repo(resolved_repo))

    def first(name: str) -> Path | None:
        return next(
            (
                value
                for layout in layouts
                if (value := getattr(layout, name)) is not None
            ),
            None,
        )

    return ResourcePaths(
        repo_root=resolved_repo,
        basic_catalog=first("basic_catalog"),
        xcard_catalog=first("xcard_catalog"),
        common_types=first("common_types"),
        agent_schema=first("agent_schema"),
        tokens=first("tokens"),
        gallery_dirs=unique_paths(
            path for layout in layouts for path in layout.gallery_dirs
        ),
        template_dirs=unique_paths(
            path for layout in layouts for path in layout.template_dirs
        ),
        icon_dirs=unique_paths(
            path for layout in layouts for path in layout.icon_dirs
        ),
    )


def _resolve_common_ref(
    ref: str,
    common_types: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if common_types is None or "#/$defs/" not in ref:
        return None
    definition_name = ref.rsplit("#/$defs/", 1)[1]
    definition = common_types.get("$defs", {}).get(definition_name)
    return definition if isinstance(definition, dict) else None


def _flatten_object_schema(
    schema: dict[str, Any],
    common_types: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[str]]:
    properties = dict(schema.get("properties", {}))
    required = list(schema.get("required", []))

    for branch in schema.get("allOf", []):
        if not isinstance(branch, dict):
            continue
        resolved = branch
        if isinstance(branch.get("$ref"), str):
            resolved = _resolve_common_ref(branch["$ref"], common_types) or {}
        branch_properties, branch_required = _flatten_object_schema(
            resolved,
            common_types,
        )
        properties.update(branch_properties)
        required.extend(branch_required)
    return properties, required


def merge_component_catalogs(
    basic_catalog: dict[str, Any],
    xcard_catalog: dict[str, Any],
    common_types: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    basic_components = basic_catalog.get("components", {})
    xcard_components = xcard_catalog.get("components", {})
    names = sorted(set(basic_components) | set(xcard_components))
    merged: dict[str, dict[str, Any]] = {}

    for name in names:
        properties: dict[str, Any] = {}
        required: list[str] = ["id", "component"]

        for component in (basic_components.get(name), xcard_components.get(name)):
            if not isinstance(component, dict):
                continue
            component_properties, component_required = _flatten_object_schema(
                component,
                common_types,
            )
            properties.update(component_properties)
            required.extend(component_required)

        properties["id"] = {"type": "string"}
        properties["component"] = {"const": name}
        properties.setdefault("catalogId", {"type": "string"})
        properties.setdefault("accessibility", {"type": "object"})
        properties.setdefault("metadata", {"type": "object"})

        merged[name] = {
            "type": "object",
            "properties": properties,
            "required": sorted(set(required)),
            "additionalProperties": False,
        }

    return merged


def merge_function_catalogs(
    basic_catalog: dict[str, Any],
    xcard_catalog: dict[str, Any],
    common_types: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    basic_functions = basic_catalog.get("functions", {})
    xcard_functions = xcard_catalog.get("functions", {})
    names = sorted(set(basic_functions) | set(xcard_functions))
    merged: dict[str, dict[str, Any]] = {}

    for name in names:
        definition = xcard_functions.get(name) or basic_functions.get(name) or {}
        properties, required = _flatten_object_schema(definition, common_types)
        if not properties:
            properties = {
                "call": {"const": name},
                "catalogId": {"type": "string"},
                "args": {"type": "object"},
            }
            required = ["call"]
        properties["call"] = {"const": name}
        merged[name] = {
            "type": "object",
            "properties": properties,
            "required": sorted(set(required) | {"call"}),
            "additionalProperties": False,
        }

    return merged


def catalog_functions(
    basic_catalog: dict[str, Any],
    xcard_catalog: dict[str, Any],
) -> set[str]:
    return set(basic_catalog.get("functions", {})) | set(
        xcard_catalog.get("functions", {})
    )


def normalize_token_name(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())
