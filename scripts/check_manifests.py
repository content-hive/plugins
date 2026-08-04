#!/usr/bin/env python3
"""Validate plugin manifests without writing generated files.

Usage:
  python3 scripts/check_manifests.py
  python3 scripts/check_manifests.py --require-stable
"""

from __future__ import annotations

import argparse
import sys

from registry_lib import RegistryError, check_manifests


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate plugin manifests")
    parser.add_argument(
        "--require-stable",
        action="store_true",
        help="Reject pre-release versions (e.g. -beta.n)",
    )
    args = parser.parse_args()
    try:
        count = check_manifests(require_stable=args.require_stable)
        print(f"OK: {count} plugin manifest(s) valid")
        return 0
    except RegistryError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
