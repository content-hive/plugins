"""Shared helpers for plugin registry generation, validation, and tagging."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_DIR = REPO_ROOT / "plugins"
REGISTRY_PATH = REPO_ROOT / "registry.json"
ROOT_CHANGELOG_PATH = REPO_ROOT / "CHANGELOG.md"

REQUIRED_FIELDS = (
    "domain",
    "name",
    "version",
    "description",
    "author",
    "requirements",
    "config_flow",
    "release_notes",
)
STRIP_FIELDS = ("path", "enabled")
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)
VERSION_HEADING_RE = re.compile(r"^##\s+(\S+)\s*$", re.MULTILINE)
DATE_HEADING_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE)
PRE_RELEASE_RE = re.compile(r"-")


class RegistryError(Exception):
    """Validation or generation failure."""


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise RegistryError(f"Invalid JSON in {path}: {e}") from e
    if not isinstance(data, dict):
        raise RegistryError(f"Expected object at root of {path}")
    return data


def load_json_text(text: str, *, source: str) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise RegistryError(f"Invalid JSON from {source}: {e}") from e
    if not isinstance(data, dict):
        raise RegistryError(f"Expected object at root from {source}")
    return data


def plugin_index_from_registry(data: dict | None) -> dict[str, str]:
    """Map domain -> version from a registry or legacy manifest."""
    if not data:
        return {}
    result: dict[str, str] = {}
    for entry in data.get("plugins", []):
        if not isinstance(entry, dict):
            continue
        domain = entry.get("domain")
        version = entry.get("version")
        if isinstance(domain, str) and isinstance(version, str):
            result[domain] = version
    return result


def validate_manifest(domain_dir: Path, data: dict, *, require_stable: bool = False) -> dict:
    domain = domain_dir.name
    for field in REQUIRED_FIELDS:
        if field not in data:
            raise RegistryError(f"{domain_dir / 'manifest.json'}: missing required field '{field}'")

    if data["domain"] != domain:
        raise RegistryError(
            f"{domain_dir / 'manifest.json'}: domain '{data['domain']}' does not match directory '{domain}'"
        )

    version = data["version"]
    if not isinstance(version, str) or not SEMVER_RE.match(version):
        raise RegistryError(f"{domain_dir / 'manifest.json'}: invalid SemVer '{version}'")

    if require_stable and PRE_RELEASE_RE.search(version):
        raise RegistryError(
            f"{domain_dir / 'manifest.json'}: pre-release version '{version}' is not allowed on stable channel"
        )

    release_notes = data["release_notes"]
    if not isinstance(release_notes, str) or not release_notes.strip():
        raise RegistryError(f"{domain_dir / 'manifest.json'}: release_notes must be a non-empty string")

    if not isinstance(data["author"], list):
        raise RegistryError(f"{domain_dir / 'manifest.json'}: author must be a list")
    if not isinstance(data["requirements"], list):
        raise RegistryError(f"{domain_dir / 'manifest.json'}: requirements must be a list")
    if not isinstance(data["config_flow"], bool):
        raise RegistryError(f"{domain_dir / 'manifest.json'}: config_flow must be a boolean")

    return {k: v for k, v in data.items() if k not in STRIP_FIELDS}


def discover_plugins(*, require_stable: bool = False) -> list[dict]:
    if not PLUGINS_DIR.is_dir():
        raise RegistryError(f"Plugins directory not found: {PLUGINS_DIR}")

    plugins: list[dict] = []
    for domain_dir in sorted(PLUGINS_DIR.iterdir(), key=lambda p: p.name):
        if not domain_dir.is_dir() or domain_dir.name.startswith("."):
            continue
        manifest_path = domain_dir / "manifest.json"
        if not manifest_path.exists():
            raise RegistryError(f"Missing manifest: {manifest_path}")
        raw = load_json(manifest_path)
        if raw is None:
            raise RegistryError(f"Empty or missing manifest: {manifest_path}")
        plugins.append(validate_manifest(domain_dir, raw, require_stable=require_stable))
    if not plugins:
        raise RegistryError(f"No plugins found under {PLUGINS_DIR}")
    return plugins


def build_registry_entry(manifest: dict) -> dict:
    domain = manifest["domain"]
    entry = {
        "domain": domain,
        "name": manifest["name"],
        "version": manifest["version"],
        "description": manifest["description"],
        "author": manifest["author"],
        "requirements": manifest["requirements"],
        "config_flow": manifest["config_flow"],
        "path": f"plugins/{domain}",
        "release_notes": manifest["release_notes"],
    }
    if "disclaimer" in manifest:
        entry["disclaimer"] = manifest["disclaimer"]
    return entry


def update_plugin_changelog(domain: str, version: str, release_notes: str) -> None:
    path = PLUGINS_DIR / domain / "CHANGELOG.md"
    notes = release_notes.strip()
    new_block = f"## {version}\n\n{notes}\n"

    if not path.exists():
        path.write_text(f"# Changelog\n\n{new_block}", encoding="utf-8")
        return

    text = path.read_text(encoding="utf-8")
    matches = list(VERSION_HEADING_RE.finditer(text))

    for i, match in enumerate(matches):
        if match.group(1) != version:
            continue
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        updated = text[:start] + new_block
        if end < len(text):
            remainder = text[end:]
            if not updated.endswith("\n") and remainder and not remainder.startswith("\n"):
                updated += "\n"
            updated += remainder.lstrip("\n") if updated.endswith("\n\n") else remainder
            if not updated.endswith("\n"):
                updated += "\n"
        else:
            if not updated.endswith("\n"):
                updated += "\n"
        path.write_text(updated, encoding="utf-8")
        return

    if text.lstrip().startswith("#"):
        lines = text.splitlines(keepends=True)
        insert_at = 1 if lines else 0
        while insert_at < len(lines) and lines[insert_at].strip() == "":
            insert_at += 1
        before = "".join(lines[:insert_at]).rstrip("\n") + "\n\n"
        after = "".join(lines[insert_at:])
        updated = before + new_block
        if after:
            if not updated.endswith("\n"):
                updated += "\n"
            if not after.startswith("\n") and not updated.endswith("\n\n"):
                updated += "\n"
            updated += after.lstrip("\n")
            if not updated.endswith("\n"):
                updated += "\n"
        path.write_text(updated, encoding="utf-8")
    else:
        path.write_text(f"# Changelog\n\n{new_block}\n{text.lstrip()}", encoding="utf-8")


def format_root_changelog_section(
    date_str: str,
    added: list[tuple[str, str]],
    updated: list[tuple[str, str, str]],
    removed: list[str],
) -> str:
    lines = [f"## {date_str}", ""]
    if added:
        lines.append("### Added")
        for domain, version in added:
            lines.append(f"- {domain} {version}")
        lines.append("")
    if updated:
        lines.append("### Updated")
        for domain, old_v, new_v in updated:
            lines.append(f"- {domain} {old_v} → {new_v}")
        lines.append("")
    if removed:
        lines.append("### Removed")
        for domain in removed:
            lines.append(f"- {domain}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _format_root_changelog_from_bullets(
    date_str: str,
    added: list[str],
    updated: list[str],
    removed: list[str],
) -> str:
    lines = [f"## {date_str}", ""]
    if added:
        lines.append("### Added")
        for bullet in added:
            lines.append(f"- {bullet}")
        lines.append("")
    if updated:
        lines.append("### Updated")
        for bullet in updated:
            lines.append(f"- {bullet}")
        lines.append("")
    if removed:
        lines.append("### Removed")
        for bullet in removed:
            lines.append(f"- {bullet}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _parse_section_bullets(section: str) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {"Added": [], "Updated": [], "Removed": []}
    current: str | None = None
    for line in section.splitlines():
        if line.startswith("### "):
            name = line[4:].strip()
            current = name if name in groups else None
            continue
        if current and line.startswith("- "):
            bullet = line[2:].strip()
            if bullet and bullet not in groups[current]:
                groups[current].append(bullet)
    return groups


def update_root_changelog(
    old_index: dict[str, str],
    new_index: dict[str, str],
    *,
    bootstrap: bool = False,
) -> None:
    added = sorted((d, new_index[d]) for d in new_index.keys() - old_index.keys())
    removed = sorted(old_index.keys() - new_index.keys())
    updated = sorted(
        (d, old_index[d], new_index[d])
        for d in old_index.keys() & new_index.keys()
        if old_index[d] != new_index[d]
    )

    if bootstrap and not added and not updated and not removed and new_index:
        added = sorted((d, new_index[d]) for d in new_index)

    if not added and not updated and not removed:
        if not ROOT_CHANGELOG_PATH.exists():
            ROOT_CHANGELOG_PATH.write_text("# Changelog\n", encoding="utf-8")
        return

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    section = format_root_changelog_section(date_str, added, updated, removed)

    if not ROOT_CHANGELOG_PATH.exists():
        ROOT_CHANGELOG_PATH.write_text(f"# Changelog\n\n{section}", encoding="utf-8")
        return

    text = ROOT_CHANGELOG_PATH.read_text(encoding="utf-8")
    matches = list(DATE_HEADING_RE.finditer(text))
    if matches and matches[0].group(1) == date_str:
        start = matches[0].start()
        end = matches[1].start() if len(matches) > 1 else len(text)
        existing_groups = _parse_section_bullets(text[start:end])
        new_groups = _parse_section_bullets(section)
        for key in existing_groups:
            for bullet in new_groups[key]:
                if bullet not in existing_groups[key]:
                    existing_groups[key].append(bullet)
        merged = _format_root_changelog_from_bullets(
            date_str,
            existing_groups["Added"],
            existing_groups["Updated"],
            existing_groups["Removed"],
        )
        updated_text = text[:start] + merged
        if end < len(text):
            remainder = text[end:]
            if not updated_text.endswith("\n"):
                updated_text += "\n"
            updated_text += remainder.lstrip("\n")
            if not updated_text.endswith("\n"):
                updated_text += "\n"
        ROOT_CHANGELOG_PATH.write_text(updated_text, encoding="utf-8")
        return

    if text.lstrip().startswith("#"):
        lines = text.splitlines(keepends=True)
        insert_at = 1
        while insert_at < len(lines) and lines[insert_at].strip() == "":
            insert_at += 1
        before = "".join(lines[:insert_at]).rstrip("\n") + "\n\n"
        after = "".join(lines[insert_at:])
        updated_text = before + section
        if after:
            if not after.startswith("\n"):
                updated_text += "\n"
            updated_text += after.lstrip("\n")
            if not updated_text.endswith("\n"):
                updated_text += "\n"
        ROOT_CHANGELOG_PATH.write_text(updated_text, encoding="utf-8")
    else:
        ROOT_CHANGELOG_PATH.write_text(f"# Changelog\n\n{section}\n{text.lstrip()}", encoding="utf-8")


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def generate_registry() -> int:
    """Write registry artifacts. Returns number of plugins."""
    had_registry = REGISTRY_PATH.exists()
    old_registry = load_json(REGISTRY_PATH)
    old_index = plugin_index_from_registry(old_registry)

    manifests = discover_plugins()
    registry_plugins = [build_registry_entry(m) for m in manifests]
    new_index = {p["domain"]: p["version"] for p in registry_plugins}

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    registry = {
        "version": "1.0.0",
        "repository": "github.com/content-hive/plugins",
        "generated_at": generated_at,
        "plugins": registry_plugins,
    }

    write_json(REGISTRY_PATH, registry)

    for manifest in manifests:
        update_plugin_changelog(manifest["domain"], manifest["version"], manifest["release_notes"])

    update_root_changelog(old_index, new_index, bootstrap=not had_registry)
    return len(registry_plugins)


def check_manifests(*, require_stable: bool = False) -> int:
    """Validate all plugin manifests. Returns plugin count."""
    return len(discover_plugins(require_stable=require_stable))


def _git_show(path: str, ref: str = "HEAD~1") -> str | None:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def compute_new_tags(*, parent_ref: str = "HEAD~1") -> list[str]:
    """Return tag names for domains whose version changed since parent_ref.

    If parent_ref has no registry.json, return [] (explicit skip) instead of
    treating every plugin as new — that would mass-tag on history gaps.
    """
    current = load_json(REGISTRY_PATH)
    if current is None:
        raise RegistryError(f"Missing {REGISTRY_PATH}")

    parent_text = _git_show("registry.json", parent_ref)
    if parent_text is None:
        return []

    old_index = plugin_index_from_registry(
        load_json_text(parent_text, source=f"{parent_ref}:registry.json")
    )
    new_index = plugin_index_from_registry(current)
    tags: list[str] = []
    for domain, version in sorted(new_index.items()):
        if old_index.get(domain) != version:
            tags.append(f"{domain}/v{version}")
    return tags
