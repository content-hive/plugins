"""Validate repositories.json, removed.json, and every listed plugin repository.

Exits with a non-zero status if any check fails.
"""

from __future__ import annotations

import sys

from catalog_lib import (
    REMOVED_PATH,
    REPOSITORIES_PATH,
    check_removed_list,
    check_repositories_list,
    inspect_repository,
    load_json,
)


def main() -> int:
    errors: list[str] = []
    try:
        repositories = load_json(REPOSITORIES_PATH)
        removed = load_json(REMOVED_PATH)
    except ValueError as e:
        print(f"::error::Invalid JSON: {e}")
        return 1

    errors += check_repositories_list(repositories)
    errors += check_removed_list(removed)
    if errors:
        for error in errors:
            print(f"::error::{error}")
        return 1

    domains: dict[str, str] = {}
    for repository in repositories:
        result = inspect_repository(repository)
        errors += [f"{repository}: {error}" for error in result.errors]
        if result.entry is None:
            continue
        domain = result.entry["domain"]
        if domain in domains:
            errors.append(f"{repository}: domain '{domain}' already used by {domains[domain]}")
        else:
            domains[domain] = repository
            print(f"{repository}: ok ({domain})")

    for error in errors:
        print(f"::error::{error}")
    if errors:
        return 1
    print(f"All {len(repositories)} repositories are valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
