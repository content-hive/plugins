# Content Hive Plugins

Plugin registry for [Content Hive](https://github.com/content-hive/content-hive): platform parsers distributed as independent plugins.

## Layout

```
repository/
├── plugins/
│   ├── <domain>/
│   │   ├── manifest.json   # hand-written source of truth
│   │   ├── CHANGELOG.md    # generated — do not edit
│   │   └── ...
│   └── ...
├── registry.json           # generated index (target format)
├── plugins-manifest.json   # generated legacy index (dual-write)
├── CHANGELOG.md            # generated registry-level changelog
├── scripts/
│   ├── registry_lib.py     # shared logic
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

You do **not** need to run the generator locally. On the PR, CI:

- validates manifests (`check_manifests.py`; `--require-stable` when the base is `release`)
- regenerates indexes/changelogs and pushes a commit starting with `[generate]` if needed

**Prefer squash merge** so `main` / `release` get a single commit with sources and generated files. After merge, CI creates tags like `douyin/v0.1.9` for version bumps (no extra commit).

Optional local preview:

```bash
python3 scripts/check_manifests.py
python3 scripts/generate_registry.py
```

Do **not** hand-edit `registry.json`, `plugins-manifest.json`, root `CHANGELOG.md`, or `plugins/*/CHANGELOG.md`.

`plugins-manifest.json` is a temporary dual-write for Content Hive downloaders that still expect that filename. Prefer `registry.json` going forward.

## Design

See [doc.md](doc.md) for branching, SemVer, and CI details.
