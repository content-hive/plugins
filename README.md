# Content Hive Plugins

Plugin registry for [Content Hive](https://github.com/content-hive/content-hive): platform parsers distributed as independent plugins.

## Layout

```
plugins/
├── plugins/
│   ├── <domain>/
│   │   ├── manifest.json   # hand-written source of truth
│   │   ├── CHANGELOG.md    # generated — do not edit
│   │   └── ...
│   └── ...
├── registry.json           # generated index (target format)
├── plugins-manifest.json   # generated legacy index (dual-write for current Content Hive)
├── CHANGELOG.md            # generated registry-level changelog
├── scripts/generate_registry.py
└── doc.md                  # repository design
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
3. Regenerate indexes locally:

```bash
python3 scripts/generate_registry.py
```

Do **not** hand-edit `registry.json`, `plugins-manifest.json`, root `CHANGELOG.md`, or `plugins/*/CHANGELOG.md`.

`plugins-manifest.json` is a temporary dual-write for Content Hive downloaders that still expect that filename. Prefer `registry.json` going forward.

## Design

See [doc.md](doc.md) for branching, SemVer, and CI plans.
