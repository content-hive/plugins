# Content Hive Plugin Catalog

The list of plugin repositories available to [Content Hive](https://github.com/content-hive/content-hive). Plugin code lives in each plugin's own repository; this repository only lists them and publishes the generated catalog.

## Catalog

Content Hive reads a single generated file:

```
https://content-hive.github.io/plugins/catalog.json
```

It is regenerated every 4 hours, on every push to `main`, and on manual runs of the `Generate catalog` workflow. Versions and release notes come from each plugin repository's GitHub Releases.

```json
{
  "schema": 1,
  "generated_at": "2026-11-03T10:00:00Z",
  "plugins": [
    {
      "repository": "content-hive/plugin-douyin",
      "domain": "douyin",
      "name": "抖音",
      "description": "...",
      "license": "MIT",
      "min_core_version": "0.1.0",
      "requirements": ["gmssl>=3.2.2"],
      "disclaimer": "...",
      "stable": {"version": "0.1.10", "tag": "v0.1.10", "release_notes": "...", "published_at": "..."},
      "beta": null
    }
  ],
  "removed": []
}
```

| Field | Source |
|-------|--------|
| `stable` | Latest published Release that is not a pre-release |
| `beta` | Latest pre-release newer than `stable`, otherwise `null` |
| `domain`, `name`, `description`, `requirements`, `disclaimer` | `plugin/manifest.json` at the `stable` tag (the `beta` tag if there is no stable release) |
| `min_core_version` | `contenthive` in `contenthive.json` at the same tag |
| `license` | License detected by GitHub |
| `removed` | `removed.json` in this repository |

## Files

| File | Purpose |
|------|---------|
| `repositories.json` | Listed plugin repositories, as `owner/repo`, sorted alphabetically |
| `removed.json` | Repositories taken out of the catalog: `{"repository": "owner/repo", "reason": "...", "severity": "removed"}`. `severity` is `removed` (no longer offered) or `critical` (harmful) |
| `scripts/generate_catalog.py` | Builds `dist/catalog.json` |
| `scripts/validate_repositories.py` | Checks `repositories.json`, `removed.json`, and every listed repository |

## Adding a plugin

A plugin repository must:

- Be public on GitHub and have a license GitHub can detect
- Keep the plugin in `plugin/`, with `plugin/manifest.json` containing `domain`, `name`, and `version`
- Have `contenthive.json` in the root with `name`, `domain` (matching the manifest), and `contenthive` (minimum Content Hive version)
- Publish at least one GitHub Release whose tag is `v` + the manifest `version` (for example `v0.1.10`); mark beta versions as pre-releases
- Use a `domain` no other listed plugin uses

Then open a pull request that adds `owner/repo` to `repositories.json` in alphabetical order. The `Validate` workflow runs the same checks; the pull request is reviewed once it passes.

## Running locally

```bash
pip install packaging
GITHUB_TOKEN="$(gh auth token)" python3 scripts/validate_repositories.py
GITHUB_TOKEN="$(gh auth token)" python3 scripts/generate_catalog.py
```
