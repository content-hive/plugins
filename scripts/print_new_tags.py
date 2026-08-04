#!/usr/bin/env python3
"""Print plugin tags for domains whose version changed since HEAD~1.

Each line: {domain}/v{version}
Exit 0 even when the list is empty.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from registry_lib import REPO_ROOT, RegistryError, compute_new_tags


def has_parent() -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD~1"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def has_parent_registry(parent_ref: str) -> bool:
    result = subprocess.run(
        ["git", "show", f"{parent_ref}:registry.json"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Print new plugin tags since parent commit")
    parser.add_argument(
        "--parent",
        default="HEAD~1",
        help="Git ref to compare against (default: HEAD~1)",
    )
    args = parser.parse_args()
    try:
        if args.parent == "HEAD~1" and not has_parent():
            print("No parent commit; skipping tags", file=sys.stderr)
            return 0
        if not has_parent_registry(args.parent):
            print(
                f"No {args.parent}:registry.json; skipping tags",
                file=sys.stderr,
            )
            return 0
        for tag in compute_new_tags(parent_ref=args.parent):
            print(tag)
        return 0
    except RegistryError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
