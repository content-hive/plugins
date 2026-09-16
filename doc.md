# Content Hive 插件仓库设计

本文档为已定设计，描述插件仓库的定位、结构、分支、版本与发布流程。

---

## 1. 仓库定位

本仓库是 **插件注册中心（Plugin Registry）**，不是普通业务项目仓库。

职责：

- 保存各插件源码与元数据
- 管理插件版本
- 提供插件索引（中心清单）
- 通过分支区分 Beta / Stable 渠道

参考形态：VS Code Extension Marketplace、Homebrew Formula、Home Assistant Integration。

用户侧渠道选择（Content Hive 配置）：

| 渠道 | `repo_ref` |
|------|------------|
| Beta | `main` |
| Stable | `release` |

**不在** `registry.json` 中增加 `channel` 字段；渠道仅由分支表达。

---

## 2. 仓库结构

```
repository/
├── plugins/
│   ├── douyin/
│   │   ├── manifest.json      # 手写，唯一真相
│   │   ├── CHANGELOG.md       # CI 生成，禁止手改
│   │   ├── __init__.py
│   │   └── ...
│   ├── fxtwitter/
│   │   ├── manifest.json
│   │   ├── CHANGELOG.md
│   │   └── ...
│   └── ...
├── registry.json              # CI 生成，禁止手改
├── README.md
├── CHANGELOG.md               # Registry 级变更；CI 维护，禁止手改
├── scripts/
│   ├── registry_lib.py        # 校验 / 生成 / 打 Tag 的共享逻辑
│   ├── check_manifests.py
│   ├── generate_registry.py
│   ├── print_new_tags.py
│   └── create_plugin_tags.sh
└── .github/
    └── workflows/
        ├── validate.yml         # PR → main/release：只校验
        └── sync-registry.yml    # push / 手动：生成索引 + Tag
```

说明：

| 文件 | 职责 |
|------|------|
| `plugins/<domain>/manifest.json` | 插件元数据的唯一手写真相（含本版 `release_notes`） |
| `registry.json` | 中心索引，由 CI 从各插件 manifest 汇总生成（复制清单字段并注入 `path`） |
| `plugins/<domain>/CHANGELOG.md` | 单个插件历史；由 CI 根据 manifest 写入，禁止手改 |
| 根目录 `CHANGELOG.md` | Registry 整体变更（新增 / 更新 / 移除哪些插件）；由 CI 对比新旧 `registry.json` 写入，禁止手改 |

`path` 由 CI 按目录位置写成 `plugins/<domain>`，**不要**在分插件 manifest 里手写。若误写了 `path` 或 `enabled`，生成中心清单时会剥掉。

---

## 3. 分插件 Manifest

### 3.1 手写示例：`plugins/douyin/manifest.json`

```json
{
  "domain": "douyin",
  "name": "抖音",
  "version": "0.1.9",
  "description": "……",
  "author": ["content-hive"],
  "requirements": ["gmssl>=3.2.2"],
  "config_flow": false,
  "disclaimer": "……",
  "release_notes": "修复 Cookie 过期导致的解析失败\n- 兼容新的签名算法"
}
```

### 3.2 字段约定

CI 必填（缺一即校验失败）：

| 字段 | 说明 |
|------|------|
| `domain` | 必须与目录名一致；仅 `[a-z0-9_-]`（主程序安装时同样校验，CI 目前只检查与目录名一致） |
| `name` | 展示名 |
| `version` | Semantic Versioning；见第 6 节 |
| `description` | 插件介绍 |
| `author` | **必须是 list**，例如 `["content-hive"]` |
| `requirements` | **必须是 list**（无依赖写 `[]`） |
| `config_flow` | **必须是 bool** |
| `release_notes` | 非空字符串；**仅本版**发布说明；发新版时改写（覆盖），不在此追加历史 |

可选 / 禁止手写：

| 字段 | 说明 |
|------|------|
| `disclaimer` | 可选。有则原样写入 `registry.json`，供安装前展示风险说明 |
| `path` | **禁止手写**；由 CI 写入中心清单 |
| `enabled` | **不要写**；若出现，生成时剥掉（启用状态在主程序本地配置，不进仓库清单） |

`release_notes` 随 `registry.json` 下发，供前端在「有可用更新」时展示目标版本说明。完整历史见 `CHANGELOG.md`，不塞进 manifest。

命名分工：

- `release_notes` → manifest / registry 中的**本版**说明
- `CHANGELOG.md` → CI 维护的**历史**汇总

### 3.3 中心清单：`registry.json`

由 CI 生成。顶层 `version` 是**清单 schema 版本**（当前固定 `"1.0.0"`），不是某个插件的版本；`repository` 由脚本写死为 `github.com/content-hive/plugins`；`generated_at` 为 UTC。

每条插件记录 = 该插件 manifest 的清单字段 + 注入的 `path`（`disclaimer` 仅在 manifest 有该字段时出现）：

```json
{
  "version": "1.0.0",
  "repository": "github.com/content-hive/plugins",
  "generated_at": "2026-07-31T09:40:00Z",
  "plugins": [
    {
      "domain": "douyin",
      "name": "抖音",
      "version": "0.1.9",
      "description": "……",
      "author": ["content-hive"],
      "requirements": ["gmssl>=3.2.2"],
      "config_flow": false,
      "path": "plugins/douyin",
      "release_notes": "修复 Cookie 过期导致的解析失败\n- 兼容新的签名算法",
      "disclaimer": "……"
    }
  ]
}
```

主程序消费 `registry.json`（发现插件、版本对比、安装、更新说明；列表接口还会用到 `description` / `author` / `disclaimer` / `release_notes`）。安装时应拷贝插件目录内已有的 `manifest.json`；仅当源目录缺少合法且 `domain` 匹配的 manifest 时，才回退用中心清单条目生成。

---

## 4. 长期分支

不使用 Git Flow。分发渠道只有两个长期分支；**仓库默认分支为 `main`**。

| 分支 | 渠道 | 用途 |
|------|------|------|
| `main` | Beta | 最新代码、新插件、预发布版本（默认分支） |
| `release` | Stable | 面向普通用户的稳定版本（Content Hive 默认 `repo_ref`） |

`develop` **不是**分发渠道，也不再作为默认分支；若仍保留，仅作历史/过渡，不要向用户配置 `repo_ref=develop`。

```
feat/* / fix/*  ──PR──►  main (beta)
                           │
                           │ 测试通过后发版
                           ▼
                        release (stable)
```

规则：

- 日常开发（含插件修复 / 新插件）只向 `main` 开 PR
- `release` 只接受来自 `main` 的发版合并（快进或 release PR）
- 不要把未在 `main` 验证过的改动直接推进 `release`

---

## 5. 开发分支与 PR

### 5.1 临时分支命名

```
feat/*
fix/*
chore/*
docs/*
```

改插件时，分支名应带上插件 **domain**（或可读的插件名），便于一 PR 一插件、也方便扫列表：

- `feat/<domain>-…` / `fix/<domain>-…`（推荐）
- 或沿用历史风格：`plugin/<domain>`（仅当整段工作都围着该插件时）

例如：`feat/douyin-cookie-refresh`、`fix/xiaohongshu-short-link`、`chore/twitter-bump-version`。

非插件改动（CI、文档、仓库级脚本）可不带 domain，例如：`docs/update-registry-doc`、`chore/ci-sync-registry`。

流程：

- 插件开发 / 日常改动：`feature branch` → PR → **`main`**
- 发 Stable：从已验证的 `main` 开 PR → **`release`**（不要把功能 PR 直接打向 `release`）

### 5.2 原则：一 PR 尽量只改一个插件

不要把多个插件改动、文档、配置塞进同一个 PR。

推荐：

- PR #101 — `[Douyin] Add douyin plugin`
- PR #102 — `[Xiaohongshu] Update xiaohongshu plugin to v0.1.15`

### 5.3 PR 标题与检查清单

标题须能一眼看出改的是哪个插件（或仓库级主题）。**改插件时标题带 domain / 插件名**，与分支命名同理。

推荐格式（与历史 PR 一致）：

```
[<Domain>] <摘要>
[<Domain>] Update <domain> plugin to vX.Y.Z
[CI/CD] …
[Docs] …
```

例如：`[Douyin] Fix cookie refresh`、`[Xiaohongshu] Accept xhslink.cn short links`、`[CI/CD] Guard sync-registry to channel branches`。

也可用 Conventional Commits，但仍应写出插件名：`feat(douyin): …` / `fix(xiaohongshu): …`。

**新插件：** `[<Domain>] Add <domain> plugin`

- [ ] `plugins/<domain>/manifest.json` 已添加且字段合法（见 3.2）
- [ ] `description` 完整；需要风险提示时填写 `disclaimer`
- [ ] `release_notes`（本版说明）已填写
- [ ] 第三方代码或额外许可已确认（如有则放 `LICENSE`）
- [ ] CI 通过（`validate`）
- [ ] 合入 `main` 后确认 `sync-registry` 变绿

**升级：** `[<Domain>] Update <domain> plugin to v1.2.0`（`fix` / `feat` 语义写在摘要里即可）

- [ ] 修改内容说明
- [ ] 新旧版本号
- [ ] Breaking Changes（如有）
- [ ] `manifest.json` 中 `version` 与本版 `release_notes` 已更新
- [ ] CI 通过（`validate`）；合入后确认 `sync-registry` 变绿（生成物由 push 后 CI 写入，无需手改）

---

## 6. 版本管理

插件使用 **Semantic Versioning**：`MAJOR.MINOR.PATCH`。

| 部分 | 含义 |
|------|------|
| MAJOR | 不兼容变更 |
| MINOR | 兼容的新功能 |
| PATCH | Bug 修复 |

### 6.1 按分支的版本约束

| 分支 | 允许的 version |
|------|----------------|
| `main` | 正式版 `x.y.z`，或预发布 `x.y.z-beta.n` |
| `release` | **仅**正式版 `x.y.z` |

示例：

- `main`：`douyin 0.2.0-beta.1`、`xiaohongshu 0.1.15-beta.2`
- `release`：`douyin 0.1.9`、`xiaohongshu 0.1.14`

CI 按目标分支强制校验：PR 看 `base_ref`，合入后的 `sync-registry` 看当前分支名；目标 / 当前为 `release` 时加 `--require-stable`。

---

## 7. Git Tag

不要使用裸 `v1.0.0`（多插件会冲突）。

CI 自动打的只有插件版本 Tag：

```
douyin/v0.1.9
douyin/v0.2.0-beta.1
fxtwitter/v0.1.8
```

合入对应渠道分支并完成 `sync-registry` 后打（Beta Tag 跟 `main`，Stable Tag 跟 `release`）。对比的是当前 `registry.json` 与 **`HEAD~1:registry.json`** 的 `domain → version`；某插件 version 变了（含新增插件）才打 `domain/v<version>`。若 parent 没有 `registry.json`，则**整批跳过**（避免历史空洞时误给所有插件打 Tag）。

`registry/YYYY.MM` 这类仓库里程碑 **不是 CI 流程**：需要时由维护者手工打 Tag，也不写入根目录 CHANGELOG 标题。

---

## 8. 发布流程

### 8.1 Beta（`main`）

```
开发者 → feature branch → PR → main
                              ↓
                    CI：校验 manifests（validate）
                              ↓
                    人工合入 main（merge commit）
                              ↓
         push 触发 sync-registry：生成 → bot commit → Tag
                              ↓
                    Beta 用户（repo_ref=main）获取
```

合入后须确认 `sync-registry` workflow 变绿，才算发布完成（merge 瞬间 `registry.json` 可能仍短暂落后）。

### 8.2 Stable（`release`）

```
main 上测试完成
        ↓
从 main 开 PR → release（版本须为正式版 x.y.z）
        ↓
CI：校验 manifests（--require-stable）
        ↓
人工合入 release（merge commit）
        ↓
push 触发 sync-registry：生成 → bot commit → Tag
        ↓
普通用户（repo_ref=release）获取
```

---

## 9. CI 自动化

脚本分工（共享逻辑在 `scripts/registry_lib.py`）：

| 脚本 | 职责 |
|------|------|
| `scripts/check_manifests.py` | 校验 manifest（`--require-stable` 拒预发布） |
| `scripts/generate_registry.py` | 生成 `registry.json`、两处 CHANGELOG |
| `scripts/print_new_tags.py` | 对比 `HEAD~1:registry.json` 输出待打 Tag |
| `scripts/create_plugin_tags.sh` | 创建并推送 `print_new_tags.py` 列出的 Tag（已存在则跳过） |

### 9.1 PR：`validate`（只校验）

触发：PR → `main` / `release`。

1. 仅支持同仓 PR
2. `check_manifests.py`（目标为 `release` 时加 `--require-stable`）
3. **不**生成、**不**回写 PR 分支

### 9.2 合入后：`sync-registry`（生成 + Tag）

触发：

- push → `main` / `release`（正常发版）
- `workflow_dispatch`（手动）：`full` 或 `tags-only`；**必须选择 `main` 或 `release`**（job 有 `if: ref_name == main || release`；选其它分支会 skip。`push.branches` 不限制手动触发）

正常 push 路径：

1. `check_manifests.py`（当前分支为 `release` 时 `--require-stable`）
2. `generate_registry.py`；若有变更 → commit/push：`[CI/CD] Sync plugin registry`（使用 `GITHUB_TOKEN`，**不会**再触发新的 workflow run）
3. 在 tip 上运行 `create_plugin_tags.sh`（对比 `HEAD~1` 的 `registry.json` 打 `domain/vX.Y.Z`）；**任一步失败则 job 失败**

开发者不必本地跑生成脚本。可用网页或 `gh` 正常合入 PR；**以 `sync-registry` 成功为准** 才算渠道索引已更新。同一 ref 使用 concurrency group，避免并行 generate 互相覆盖。

**不要依赖「generate push 再跑一次 workflow」来补救**：默认 `GITHUB_TOKEN` 推送不会创建新的 workflow run。

若 **生成已 push、打 tag 失败**：

1. **不要** Re-run 那次失败的 push job（仍按旧 event SHA checkout，再 push 常会 non-fast-forward）
2. **在 tip 仍停在那次 generate commit 时**，于 Actions → **Sync registry** → Run workflow：选 **`main` 或 `release`**，mode = **`tags-only`**
3. 该模式**不再 generate**，只把当前 tip 的 `registry.json` 与 **`HEAD~1:registry.json`** 的版本差打成 `domain/vX.Y.Z`；本地或远端已存在的 tag 会跳过

`tags-only` **不能**补打更早 commit 漏掉的 tag。若 generate 成功、tag 失败之后又合入了新的 PR，需要维护者按当时漏掉的 `domain/vX.Y.Z` 手工补打，或把 tip 重置到那次 generate commit 再跑 `tags-only`。

若启用 Branch protection 且禁止默认 `GITHUB_TOKEN` 直推，需另行配置允许 Actions 写入的 PAT / GitHub App。

---

## 10. Release Notes 与 CHANGELOG

插件本版说明手写在 manifest 的 `release_notes`；插件历史与 Registry 整体变更均由 CI 维护。

### A. 根目录 CHANGELOG.md（Registry 级，CI 生成）

路径：仓库根目录 `CHANGELOG.md`。`sync-registry` 生成时对比更新前的 `registry.json` 与新生成的索引，自动归类：

| 对比结果 | 归入 |
|----------|------|
| 旧索引无、新索引有该 `domain` | **新增（Added）** |
| 同 `domain` 且 `version` 变化 | **更新（Updated）** |
| 旧索引有、新索引无该 `domain` | **移除（Removed）** |
| `domain` 与 `version` 均未变 | 不写入本轮条目 |

若本轮没有任何新增 / 更新 / 移除，则不追加新的 Registry 条目。日期标题使用 **UTC** 的 `YYYY-MM-DD`。

示例格式：

```markdown
# Changelog

## 2026-07-31

### Added
- douyin 0.1.9

### Updated
- xiaohongshu 0.1.14 → 0.1.15
- twitter 0.1.1 → 0.1.2-beta.1

### Removed
- old_parser
```

写入规则：

| 情况 | 行为 |
|------|------|
| 本轮有变更，且当天（UTC）尚无块 | 在文件顶部（`# Changelog` 下）插入 `## YYYY-MM-DD` 块 |
| 本轮有变更，且当天已有块 | **合并进当天已有块**（同类 bullet 去重追加）；不另开带时刻的独立块 |
| Updated 条目 | 写成 `domain 旧版 → 新版` |

人类不直接编辑此文件。

### B. 本版 `release_notes`（手写，在 manifest）

`manifest.json` 的 `release_notes` **只描述当前 `version`**。发新版时：

1. 更新 `version`
2. **改写** `release_notes` 为本版内容（覆盖，不在此字段追加旧版）

前端展示更新时，读取 `registry.json` 中该插件的 `release_notes`（即远程目标版本说明）。跨多个中间版本时，只展示最新远程版说明，不展开每一版。

### C. Plugin CHANGELOG.md（CI 生成）

路径：`plugins/<domain>/CHANGELOG.md`。合并后 CI 根据该插件 manifest 的 `version` + `release_notes` 写入，格式约定如下：

```markdown
# Changelog

## 0.1.9

修复 Cookie 过期导致的解析失败
- 兼容新的签名算法

## 0.1.8

- 初始支持短链解析
```

写入规则：

| 情况 | 行为 |
|------|------|
| `CHANGELOG.md` 中**尚无**该 `version` 标题 | **追加**新的 `## <version>` 块（插在标题下、已有版本之上） |
| 已存在相同 `version` | **覆盖**该版本块内容（同一版本上反复修正 `release_notes` 时） |
| `version` 未变化 | 不新增条目；若同 version 下 `release_notes` 文案变了，则按上行覆盖该块 |

人类不直接编辑此文件；完整历史以 CI 维护的插件 `CHANGELOG.md` 为准，机器/前端更新提示以 manifest / `registry.json` 的本版 `release_notes` 为准。

---

## 11. 架构总览

```
                 Plugin Repository

                       |
        +--------------+--------------+
        |                             |
      main                        release
      Beta                         Stable
   repo_ref=main              repo_ref=release
        |                             |
   feature PR                   从 main 发版


plugins/
 ├── douyin/
 │     ├── manifest.json      # 手写真相（含本版 release_notes）
 │     └── CHANGELOG.md       # CI：按 version 追加 / 同 version 覆盖
 └── fxtwitter/
       └── ...

registry.json         # sync-registry 在合入后生成并 push（清单字段 + path）
CHANGELOG.md          # sync-registry：对比 registry，记录 Added / Updated / Removed

Tags（CI）:
  douyin/v0.2.0-beta.1        # 跟 main
  douyin/v0.2.0               # 跟 release
```

---

## 12. 与主程序的约定

- 中心索引文件名为 `registry.json`；schema 版本在顶层 `version`，当前为 `1.0.0`
- 用户通过 `plugins.repo_ref` 选择渠道：`release` = Stable（默认），`main` = Beta；无需协议层 `channel` 字段
- 检查更新时，远程条目中的 `release_notes` 一并返回给前端，用于展示目标版本说明
- 可用插件列表还会用到远程条目中的 `description`、`author`、`disclaimer`
- `domain` 须匹配 `[a-z0-9_-]`，否则主程序拒绝安装
- 后续若增加 `min_core_version` / `api_version` 等兼容字段，写在分插件 `manifest.json` 中，由 CI 一并汇总
