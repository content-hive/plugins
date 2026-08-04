# Content Hive Plugins

Plugin registry for [Content Hive](https://github.com/content-hive/content-hive): platform parsers distributed as independent plugins.

## Channels

| Channel | Branch (`repo_ref`) | Audience |
|---------|---------------------|----------|
| Stable (default) | `release` | Normal users |
| Beta | `main` | Testers / early adopters |

`develop` is not a distribution channel.

## Layout

```
plugins/
├── plugins/
│   ├── <domain>/
│   │   ├── manifest.json   # hand-written source of truth
│   │   ├── CHANGELOG.md    # generated — do not edit
│   │   └── ...
│   └── ...
├── registry.json           # generated index
├── CHANGELOG.md            # generated registry-level changelog
├── scripts/
│   ├── registry_lib.py
│   ├── generate_registry.py
│   ├── check_manifests.py
│   └── print_new_tags.py
├── .github/workflows/
│   ├── validate-and-sync.yml   # PR → main/release
│   └── tag-releases.yml        # push → main/release
└── doc.md
```

## Available plugins

| Domain | Description |
|--------|-------------|
| `fxtwitter` | Twitter/X via the fxtwitter API |
| `twitter` | Twitter/X via GraphQL API |
| `xiaohongshu` | Xiaohongshu notes via page scrape |
| `douyin` | Douyin content parsing |
| `jike` | Jike posts (text, Live Photo, video) |
| `instagram` | Instagram posts/reels (session cookie) |
| `threads` | Threads posts via mobile page scrape |

## Editing a plugin

1. Change code and/or `plugins/<domain>/manifest.json`
2. When releasing: bump `version` and rewrite `release_notes` (current version only)
3. Open a PR targeting `main` (beta) or `release` (stable)

You do **not** need to run the generator locally. On the PR, CI validates manifests and regenerates indexes/changelogs (bot commit starting with `[generate]` if needed).

**Prefer squash merge.** After merge, CI creates tags like `douyin/v0.1.9` for version bumps.

Optional local preview:

```bash
python3 scripts/check_manifests.py
python3 scripts/generate_registry.py
```

Do **not** hand-edit `registry.json`, root `CHANGELOG.md`, or `plugins/*/CHANGELOG.md`.

## Design

See [doc.md](doc.md) for branching, SemVer, and CI details.
