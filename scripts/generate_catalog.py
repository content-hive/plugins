"""Generate dist/catalog.json from repositories.json and each plugin repository's GitHub Releases.

Repositories that fail inspection are skipped with a warning so one broken plugin
does not block the rest of the catalog.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

from catalog_lib import (
    REMOVED_PATH,
    REPOSITORIES_PATH,
    ROOT,
    check_removed_list,
    check_repositories_list,
    inspect_repository,
    load_json,
)

OUTPUT_PATH = ROOT / "dist" / "catalog.json"
SCHEMA_VERSION = 1


def main() -> int:
    repositories = load_json(REPOSITORIES_PATH)
    removed = load_json(REMOVED_PATH)
    format_errors = check_repositories_list(repositories) + check_removed_list(removed)
    if format_errors:
        for error in format_errors:
            print(f"::error::{error}")
        return 1

    removed_repositories = {item["repository"].lower() for item in removed}
    plugins: list[dict] = []
    domains: dict[str, str] = {}

    for repository in repositories:
        if repository.lower() in removed_repositories:
            print(f"::warning::{repository}: listed in removed.json, skipped")
            continue

        result = inspect_repository(repository)
        if result.entry is None:
            for error in result.errors:
                print(f"::warning::{repository}: {error}")
            print(f"::warning::{repository}: skipped")
            continue

        domain = result.entry["domain"]
        if domain in domains:
            print(f"::warning::{repository}: domain '{domain}' already used by {domains[domain]}, skipped")
            continue
        domains[domain] = repository
        plugins.append(result.entry)

        stable = result.entry["stable"]["version"] if result.entry["stable"] else "-"
        beta = result.entry["beta"]["version"] if result.entry["beta"] else "-"
        print(f"{repository}: {domain} stable={stable} beta={beta}")

    if repositories and not plugins:
        print("::error::No valid plugin repositories; refusing to publish an empty catalog")
        return 1

    catalog = {
        "schema": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "plugins": plugins,
        "removed": removed,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Wrote {OUTPUT_PATH.relative_to(ROOT)} with {len(plugins)} plugin(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
