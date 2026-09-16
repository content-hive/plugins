#!/usr/bin/env bash
# Create and push plugin version tags for domains whose version changed since HEAD~1.
set -euo pipefail

tags="$(python3 scripts/print_new_tags.py)"
if [[ -z "$tags" ]]; then
  echo "No new plugin tags"
  exit 0
fi

while IFS= read -r tag; do
  [[ -z "$tag" ]] && continue
  if git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
    echo "Tag already exists: $tag"
    continue
  fi
  git tag "$tag"
  git push origin "$tag"
  echo "Created tag: $tag"
done <<< "$tags"
