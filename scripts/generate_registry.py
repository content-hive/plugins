#!/usr/bin/env python3
"""Generate registry.json, legacy plugins-manifest.json, and CHANGELOG files.

Source of truth: plugins/<domain>/manifest.json
Run from repo root or any cwd: python scripts/generate_registry.py
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_DIR = REPO_ROOT / "plugins"
REGISTRY_PATH = REPO_ROOT / "registry.json"
LEGACY_MANIFEST_PATH = REPO_ROOT / "plugins-manifest.json"
ROOT_CHANGELOG_PATH = REPO_ROOT / "CHANGELOG.md"

REQUIRED_FIELDS = ("domain", "name", "version", "description", "author", "requirements", "config_flow", "release_notes")
STRIP_FIELDS = ("path", "enabled")
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)
VERSION_HEADING_RE = re.compile(r"^##\s+(\S+)\s*$", re.MULTILINE)


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


def validate_manifest(domain_dir: Path, data: dict) -> dict:
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

    release_notes = data["release_notes"]
    if not isinstance(release_notes, str) or not release_notes.strip():
        raise RegistryError(f"{domain_dir / 'manifest.json'}: release_notes must be a non-empty string")

    if not isinstance(data["author"], list):
        raise RegistryError(f"{domain_dir / 'manifest.json'}: author must be a list")
    if not isinstance(data["requirements"], list):
        raise RegistryError(f"{domain_dir / 'manifest.json'}: requirements must be a list")
    if not isinstance(data["config_flow"], bool):
        raise RegistryError(f"{domain_dir / 'manifest.json'}: config_flow must be a boolean")

    cleaned = {k: v for k, v in data.items() if k not in STRIP_FIELDS}
    return cleaned


def discover_plugins() -> list[dict]:
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
        plugins.append(validate_manifest(domain_dir, raw))
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


def build_legacy_entry(registry_entry: dict) -> dict:
    entry = dict(registry_entry)
    entry["enabled"] = True
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
        if end < len(text) and not new_block.endswith("\n"):
            updated += "\n"
        if end < len(text):
            remainder = text[end:]
            if not updated.endswith("\n") and remainder and not remainder.startswith("\n"):
                updated += "\n"
            updated += remainder.lstrip("\n") if updated.endswith("\n\n") else remainder
            # Normalize: ensure single blank line between blocks when needed
            if not updated.endswith("\n"):
                updated += "\n"
        else:
            if not updated.endswith("\n"):
                updated += "\n"
        path.write_text(updated, encoding="utf-8")
        return

    # Insert new version block after title (or at top)
    if text.lstrip().startswith("#"):
        lines = text.splitlines(keepends=True)
        insert_at = 0
        # Skip title line and following blank lines
        if lines:
            insert_at = 1
            while insert_at < len(lines) and lines[insert_at].strip() == "":
                insert_at += 1
        before = "".join(lines[:insert_at])
        after = "".join(lines[insert_at:])
        if before and not before.endswith("\n"):
            before += "\n"
        if before and not before.endswith("\n\n"):
            before = before.rstrip("\n") + "\n\n"
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

    # First registry.json creation: record current catalog even if versions match legacy.
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
    # Insert after title
    if text.lstrip().startswith("#"):
        lines = text.splitlines(keepends=True)
        insert_at = 1
        while insert_at < len(lines) and lines[insert_at].strip() == "":
            insert_at += 1
        before = "".join(lines[:insert_at])
        after = "".join(lines[insert_at:])
        before = before.rstrip("\n") + "\n\n"
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


def main() -> int:
    try:
        had_registry = REGISTRY_PATH.exists()
        old_registry = load_json(REGISTRY_PATH)
        if old_registry is None:
            old_registry = load_json(LEGACY_MANIFEST_PATH)
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
        legacy = {
            "version": "1.0.0",
            "repository": "github.com/content-hive/plugins",
            "plugins": [build_legacy_entry(p) for p in registry_plugins],
        }

        write_json(REGISTRY_PATH, registry)
        write_json(LEGACY_MANIFEST_PATH, legacy)

        for manifest in manifests:
            update_plugin_changelog(manifest["domain"], manifest["version"], manifest["release_notes"])

        update_root_changelog(old_index, new_index, bootstrap=not had_registry)

        print(f"Generated {REGISTRY_PATH.relative_to(REPO_ROOT)}")
        print(f"Generated {LEGACY_MANIFEST_PATH.relative_to(REPO_ROOT)} (legacy dual-write)")
        print(f"Plugins: {len(registry_plugins)}")
        return 0
    except RegistryError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
