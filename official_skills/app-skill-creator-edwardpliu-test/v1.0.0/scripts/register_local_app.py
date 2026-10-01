#!/usr/bin/env python3
"""Install a built OneAgent App Skill into ~/.one-agent/skills and register it."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

SKILL_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
IGNORE_NAMES = {
    ".DS_Store",
    ".git",
    ".meta",
    ".one-agent-registration.json",
    ".venv",
    "__pycache__",
    "node_modules",
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copy a built App Skill into the OneAgent skill root and register it."
    )
    parser.add_argument("source", help="Built skill directory (must contain SKILL.md and assets/app.yaml)")
    parser.add_argument(
        "--skill-root",
        default="",
        help="Override skill root. Default: $ONE_AGENT_SKILL_PATH or ~/.one-agent/skills",
    )
    args = parser.parse_args()

    source = Path(args.source).expanduser().resolve()
    skill_root = resolve_skill_root(args.skill_root)
    one_agent_root = skill_root.parent

    try:
        result = register(source, skill_root, one_agent_root)
    except RegisterError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


class RegisterError(Exception):
    pass


def resolve_skill_root(override: str) -> Path:
    if override.strip():
        return Path(override).expanduser().resolve()
    env = os.environ.get("ONE_AGENT_SKILL_PATH", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    home_env = os.environ.get("ONE_AGENT_HOME", "").strip()
    root = Path(home_env).expanduser() if home_env else Path.home() / ".one-agent"
    return (root / "skills").resolve()


def register(source: Path, skill_root: Path, one_agent_root: Path) -> dict[str, object]:
    skill_md = find_skill_md(source)
    app_yaml = source / "assets" / "app.yaml"
    if not skill_md:
        raise RegisterError(f"{source} is missing top-level SKILL.md")
    if not app_yaml.is_file():
        raise RegisterError(f"{source} is missing assets/app.yaml")

    frontmatter = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    manifest_text = app_yaml.read_text(encoding="utf-8")
    app_id = yaml_field(manifest_text, "id")
    version = (
        yaml_field(manifest_text, "version")
        or frontmatter.get("version")
        or "local"
    )
    name = frontmatter.get("name") or app_id
    description = frontmatter.get("description") or yaml_field(manifest_text, "description")
    if not app_id:
        raise RegisterError("assets/app.yaml is missing id")
    if name != app_id:
        raise RegisterError(f"SKILL.md name {name!r} must equal app.yaml id {app_id!r}")
    if not SKILL_NAME_RE.match(app_id) or app_id in {".", ".."}:
        raise RegisterError(f"invalid app id {app_id!r}")

    missing_paths = missing_declared_paths(source, manifest_text)
    if missing_paths:
        raise RegisterError("app.yaml declared path missing: " + ", ".join(missing_paths))

    destination = skill_root / app_id
    guard_existing(destination, app_id)
    source_id = f"imported:{sha256_text(str(source))}"
    registered_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    in_place = destination.exists() and destination.samefile(source)

    if in_place:
        checksum = directory_checksum(destination)
        write_markers(
            destination,
            destination,
            app_id,
            description,
            version,
            source_id,
            source,
            registered_at,
            checksum,
        )
    else:
        skill_root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".register-{app_id}-", dir=skill_root))
        try:
            copy_skill(source, staging)
            checksum = directory_checksum(staging)
            write_markers(
                staging,
                destination,
                app_id,
                description,
                version,
                source_id,
                source,
                registered_at,
                checksum,
            )
            replace_directory(staging, destination)
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    package_plugin(
        destination,
        one_agent_root,
        app_id,
        description,
        version,
        source_id,
        source,
        registered_at,
    )
    return {
        "name": app_id,
        "version": version,
        "skillPath": str(destination),
        "registration": str(destination / ".one-agent-registration.json"),
        "marketplace": str(one_agent_root / ".claude-plugin" / "marketplace.json"),
    }


def find_skill_md(root: Path) -> Path | None:
    for entry in root.iterdir():
        if entry.is_file() and entry.name.lower() == "skill.md":
            return entry
    return None


def guard_existing(destination: Path, app_id: str) -> None:
    if not destination.exists():
        return
    if not destination.is_dir():
        raise RegisterError(f"{destination} exists and is not a directory")
    existing_yaml = destination / "assets" / "app.yaml"
    if existing_yaml.is_file():
        existing_id = yaml_field(existing_yaml.read_text(encoding="utf-8"), "id")
        if existing_id and existing_id != app_id:
            raise RegisterError(
                f"{destination} already holds a different app id {existing_id!r}"
            )
    registration = read_json(destination / ".one-agent-registration.json")
    if registration and registration.get("name") not in {None, app_id}:
        raise RegisterError(
            f"{destination} is already registered as {registration.get('name')!r}"
        )


def copy_skill(source: Path, destination: Path) -> None:
    shutil.copytree(
        source,
        destination,
        dirs_exist_ok=True,
        ignore=lambda _dir, names: [name for name in names if name in IGNORE_NAMES],
        symlinks=False,
    )


def write_markers(
    root: Path,
    final_destination: Path,
    name: str,
    description: str,
    version: str,
    source_id: str,
    source: Path,
    registered_at: str,
    checksum: str,
) -> None:
    digest = checksum
    home = Path.home()
    target = display_path(final_destination, home)
    (root / ".meta").write_text(
        json.dumps(
            {
                "name": name,
                "version": version,
                "checksum": f"sha256:{digest}",
                "extract_time": registered_at,
                "source": "local-registration",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / ".one-agent-registration.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "enabled": True,
                "name": name,
                "sourceSkillId": source_id,
                "source": "imported",
                "sourceLabel": "构建导入",
                "sourceLocation": f"{source.name}/SKILL.md",
                "targetLocation": target,
                **({"description": description} if description else {}),
                "version": version,
                "checksum": digest,
                "registeredAt": registered_at,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def package_plugin(
    skill_dir: Path,
    one_agent_root: Path,
    name: str,
    description: str,
    version: str,
    source_id: str,
    source: Path,
    registered_at: str,
) -> None:
    plugin_root = one_agent_root / "plugins" / name
    staging_parent = one_agent_root / "plugins"
    staging_parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".plugin-{name}-", dir=staging_parent))
    checksum = directory_checksum(skill_dir)
    plugin = {
        "schemaVersion": 1,
        "name": name,
        "displayName": name,
        "description": description or f"OneAgent local Skill {name}",
        "version": semantic_version(version, checksum),
        "kind": "skill",
        "sourceId": source_id,
        "sourceLabel": "构建导入",
        "sourceLocation": f"{source.name}/SKILL.md",
        "location": display_path(plugin_root, Path.home()),
        "componentNames": [name],
        "checksum": checksum,
        "registeredAt": registered_at,
    }
    try:
        skill_dest = staging / "skills" / name
        skill_dest.parent.mkdir(parents=True, exist_ok=True)
        copy_skill(skill_dir, skill_dest)
        (staging / ".one-agent-plugin.json").write_text(
            json.dumps(plugin, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        claude_dir = staging / ".claude-plugin"
        claude_dir.mkdir(parents=True, exist_ok=True)
        (claude_dir / "plugin.json").write_text(
            json.dumps(
                {
                    "$schema": "https://json.schemastore.org/claude-code-plugin-manifest.json",
                    "name": name,
                    "displayName": name,
                    "version": plugin["version"],
                    "description": plugin["description"],
                    "author": {"name": "OneAgent"},
                    "keywords": ["one-agent", "local-skill"],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        replace_directory(staging, plugin_root)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    rebuild_marketplace(one_agent_root)


def rebuild_marketplace(one_agent_root: Path) -> None:
    plugins_root = one_agent_root / "plugins"
    plugins: list[dict[str, object]] = []
    if plugins_root.is_dir():
        for entry in sorted(plugins_root.iterdir(), key=lambda item: item.name):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            marker = read_json(entry / ".one-agent-plugin.json")
            if not marker or marker.get("name") != entry.name:
                continue
            plugins.append(marker)
    plugins.sort(key=lambda item: (str(item.get("kind") or ""), str(item.get("displayName") or "")))
    manifest_dir = one_agent_root / ".claude-plugin"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "marketplace.json").write_text(
        json.dumps(
            {
                "name": "one-agent-local",
                "owner": {"name": "OneAgent"},
                "description": "Portable local Skills and MCP plugins registered by OneAgent",
                "plugins": [
                    {
                        "name": plugin["name"],
                        "source": f"./plugins/{plugin['name']}",
                        "description": plugin.get("description") or "",
                        "version": plugin.get("version") or "0.0.0-local",
                        "category": "skills" if plugin.get("kind") == "skill" else "mcp",
                        "tags": ["one-agent", "local", plugin.get("kind") or "skill"],
                    }
                    for plugin in plugins
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def missing_declared_paths(source: Path, manifest_text: str) -> list[str]:
    """检查 app.yaml 里每个 path:（UI 资源与 tool handler 都在内）在包里真实存在。"""
    missing: list[str] = []
    for match in re.finditer(r"^\s*path:\s*(.+)$", manifest_text, re.M):
        rel = match.group(1).strip().strip("'\"")
        if not rel or rel.startswith("{") or ":" in rel:
            continue
        if not (source / rel).is_file():
            missing.append(rel)
    return missing


def parse_frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"^---\s*\n([\s\S]*?)\n---(?:\s*\n|$)", text)
    if not match:
        return {}
    body = match.group(1)
    values: dict[str, str] = {}
    key = ""
    chunks: list[str] = []
    for line in body.splitlines():
        if re.match(r"^[A-Za-z0-9_-]+:", line):
            if key:
                values[key] = " ".join(chunks).strip().strip("'\"")
            name, rest = line.split(":", 1)
            key = name.strip()
            chunks = [rest.strip()]
        elif key and (line.startswith(" ") or line.startswith("\t")):
            chunks.append(line.strip())
    if key:
        values[key] = " ".join(chunks).strip().strip("'\"")
    return values


def yaml_field(text: str, field: str) -> str:
    match = re.search(rf"^{re.escape(field)}:\s*(.+)$", text, re.M)
    return match.group(1).strip().strip("'\"") if match else ""


def directory_checksum(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(walk_files(root)):
        rel = path.relative_to(root).as_posix()
        digest.update(f"file\0{rel}\0".encode())
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def walk_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in IGNORE_NAMES]
        for name in filenames:
            if name in IGNORE_NAMES:
                continue
            files.append(Path(current) / name)
    return files


def replace_directory(staging: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if destination.exists():
        backup = destination.with_name(f"{destination.name}.backup-{uuid.uuid4().hex}")
        destination.rename(backup)
    try:
        staging.rename(destination)
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)
    except Exception:
        if backup is not None and not destination.exists():
            backup.rename(destination)
        raise


def read_json(path: Path) -> dict[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def display_path(path: Path, home: Path) -> str:
    resolved = path.resolve()
    home_resolved = home.resolve()
    if resolved == home_resolved:
        return "~"
    try:
        return "~/" + resolved.relative_to(home_resolved).as_posix()
    except ValueError:
        return str(resolved)


def semantic_version(version: str, checksum: str) -> str:
    cleaned = version.strip().lstrip("v")
    if re.match(r"^\d+\.\d+\.\d+", cleaned):
        return cleaned
    return f"0.0.0-local.{checksum[:12]}"


if __name__ == "__main__":
    sys.exit(main())
