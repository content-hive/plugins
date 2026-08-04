#!/usr/bin/env python3
"""Generate registry.json, legacy plugins-manifest.json, and CHANGELOG files.

Source of truth: plugins/<domain>/manifest.json
Run from repo root: python3 scripts/generate_registry.py
"""

from __future__ import annotations

import sys

from registry_lib import REGISTRY_PATH, LEGACY_MANIFEST_PATH, REPO_ROOT, RegistryError, generate_registry


def main() -> int:
    try:
        count = generate_registry()
        print(f"Generated {REGISTRY_PATH.relative_to(REPO_ROOT)}")
        print(f"Generated {LEGACY_MANIFEST_PATH.relative_to(REPO_ROOT)} (legacy dual-write)")
        print(f"Plugins: {count}")
        return 0
    except RegistryError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
