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
│   │   ├── CHANGELOG.md
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
└── .github/
    └── workflows/
        └── ...
```

说明：

| 文件 | 职责 |
|------|------|
| `plugins/<domain>/manifest.json` | 插件元数据的唯一手写真相（含本版 `release_notes`） |
| `registry.json` | 中心索引，由 CI 从各插件 manifest 汇总生成 |
| `plugins/<domain>/CHANGELOG.md` | 单个插件历史；由 CI 根据 manifest 写入，禁止手改 |
| 根目录 `CHANGELOG.md` | Registry 整体变更（新增 / 更新 / 移除哪些插件）；由 CI 对比新旧 `registry.json` 写入，禁止手改 |

`path` 字段由 CI 按目录位置自动注入，**不要**在分插件 manifest 里手写。

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

| 字段 | 说明 |
|------|------|
| `domain` | 必须与目录名一致 |
| `version` | Semantic Versioning；见第 6 节 |
| `release_notes` | **仅本版**发布说明；发新版时改写（覆盖），不在此追加历史 |
| `path` | **禁止手写**；由 CI 写入中心清单 |

`release_notes` 随 `registry.json` 下发，供前端在「有可用更新」时展示目标版本说明。完整历史见 `CHANGELOG.md`，不塞进 manifest。

命名分工：

- `release_notes` → manifest / registry 中的**本版**说明
- `CHANGELOG.md` → CI 维护的**历史**汇总

### 3.3 中心清单：`registry.json`

由 CI 生成，示例形态：

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
      "path": "plugins/douyin",
      "release_notes": "修复 Cookie 过期导致的解析失败\n- 兼容新的签名算法"
    }
  ]
}
```

主程序消费 `registry.json`（发现插件、版本对比、安装、更新说明）。安装时应拷贝插件目录内已有的 `manifest.json`；中心清单做索引，并携带各插件当前 `release_notes`。

---

## 4. 长期分支

不使用 Git Flow。仅两个长期分支：

| 分支 | 渠道 | 用途 |
|------|------|------|
| `main` | Beta | 最新代码、新插件、预发布版本 |
| `release` | Stable | 面向普通用户的稳定版本 |

```
feat/* / fix/*  ──PR──►  main (beta)
                           │
                           │ 测试通过后发版
                           ▼
                        release (stable)
```

规则：

- 日常开发只向 `main` 合入
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

例如：`feat/add-camera-plugin`、`fix/weather-crash`、`chore/update-registry`。

流程：`feature branch` → PR → `main`。

### 5.2 原则：一 PR 尽量只改一个插件

不要把多个插件改动、文档、配置塞进同一个 PR。

推荐：

- PR #101 — 新增 camera 插件
- PR #102 — 升级 weather 插件

### 5.3 PR 标题与检查清单

**新插件：** `feat: add xxx plugin`

- [ ] 插件介绍完整
- [ ] `plugins/<domain>/manifest.json` 已添加且字段合法
- [ ] `release_notes`（本版说明）已填写
- [ ] README 已完善
- [ ] License 已确认
- [ ] CI 通过

**升级：** `fix: update xxx plugin to v1.2.0` / `feat: update xxx plugin to v1.2.0`

- [ ] 修改内容说明
- [ ] 新旧版本号
- [ ] Breaking Changes（如有）
- [ ] `manifest.json` 中 `version` 与本版 `release_notes` 已更新
- [ ] CI 通过（生成物由 PR 上 CI 回写，无需手改）

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

- `main`：`camera 2.0.0-beta.1`、`weather 1.5.0-beta.2`
- `release`：`camera 1.8.3`、`weather 1.4.5`

CI 按目标分支强制校验上述规则。

---

## 7. Git Tag

不要使用裸 `v1.0.0`（多插件会冲突）。

推荐：

```
# 插件
douyin/v0.1.9
douyin/v0.2.0-beta.1
fxtwitter/v0.1.8

# 仓库 / Registry 里程碑（可选）
registry/2026.08
```

Tag 在合入对应渠道分支后打（Beta Tag 跟 `main`，Stable Tag 跟 `release`）。

---

## 8. 发布流程

### 8.1 Beta（`main`）

```
开发者 → feature branch → PR → main
                              ↓
         CI：校验 + 生成并回写 PR（[generate]）
                              ↓
                    squash merge → main
                              ↓
                    CI：打插件 Tag（无新 commit）
                              ↓
                    Beta 用户（repo_ref=main）获取
```

### 8.2 Stable（`release`）

```
main 上测试完成
        ↓
PR → release（版本须为正式版 x.y.z）
        ↓
CI：校验（--require-stable）+ 生成并回写 PR
        ↓
squash merge → release
        ↓
CI：打插件 Tag（无新 commit）
        ↓
普通用户（repo_ref=release）获取
```

---

## 9. CI 自动化

脚本分工（共享逻辑在 `scripts/registry_lib.py`）：

| 脚本 | 职责 |
|------|------|
| `scripts/check_manifests.py` | 校验 manifest（`--require-stable` 拒预发布） |
| `scripts/generate_registry.py` | 生成 `registry.json`、legacy、两处 CHANGELOG |
| `scripts/print_new_tags.py` | 对比 `HEAD~1` 输出待打 Tag |

### 9.1 PR：`validate-and-sync`（同一 workflow，不拆）

触发：PR → `main` / `release`。

1. 仅支持同仓 PR（需向 PR 分支 push 生成物）
2. 若最新 commit message **以 `[generate]` 开头** → 跳过（避免 bot 回写死循环）
3. `check_manifests.py`（目标为 `release` 时加 `--require-stable`）
4. `generate_registry.py`；若有变更 → bot commit/push：`[generate] regenerate registry`

开发者不必本地跑生成脚本；生成物由 CI 写回 PR。合并请用 **squash merge**，使 `main`/`release` 上一次提交包含源改动与生成物。

### 9.2 合入后：`tag-releases`（只打 Tag，不 commit）

触发：push → `main` / `release`。

1. `print_new_tags.py` 找出 version 变化（含新增）的插件
2. 创建并推送 `{domain}/v{version}`；已存在则跳过
3. **不**修改工作区、**不**新增 commit

---

## 10. Release Notes 与 CHANGELOG

插件本版说明手写在 manifest 的 `release_notes`；插件历史与 Registry 整体变更均由 CI 维护。

### A. 根目录 CHANGELOG.md（Registry 级，CI 生成）

路径：仓库根目录 `CHANGELOG.md`。PR 上 CI 生成时对比更新前的 `registry.json` 与新生成的索引，自动归类：

| 对比结果 | 归入 |
|----------|------|
| 旧索引无、新索引有该 `domain` | **新增（Added）** |
| 同 `domain` 且 `version` 变化 | **更新（Updated）** |
| 旧索引有、新索引无该 `domain` | **移除（Removed）** |
| `domain` 与 `version` 均未变 | 不写入本轮条目 |

若本轮没有任何新增 / 更新 / 移除，则不追加新的 Registry 条目。

示例格式：

```markdown
# Changelog

## 2026-07-31

### Added
- camera 0.1.0

### Updated
- weather 1.4.5 → 1.5.0
- player 2.0.0-beta.1 → 2.0.0-beta.2

### Removed
- old_sensor
```

写入规则：

| 情况 | 行为 |
|------|------|
| 本轮有变更 | 在文件顶部（标题下）**追加**一个以日期（或可选 `registry/YYYY.MM` 里程碑）为标题的块 |
| 同一天内多次 merge 且需合并展示 | 可合并进当天已有块，或始终追加带时间的独立块（实施时二选一，保持一致即可） |
| Updated 条目 | 建议写出旧版 → 新版，便于扫一眼 |

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
| `CHANGELOG.md` 中**尚无**该 `version` 标题 | **追加**新的 `## <version>` 块（通常插在最新版本之上） |
| 已存在相同 `version` | **覆盖**该版本块内容（同一版本上反复修正 `release_notes` 时） |
| `version` 未变化 | 若仅其它文件变更、manifest 的 version 未变，则不新增条目；若同 version 下 `release_notes` 文案变了，则按上行覆盖该块 |

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

registry.json         # PR 上 CI 生成并回写（含各插件本版 release_notes）
CHANGELOG.md          # CI：对比 registry，记录 Added / Updated / Removed

Tags:
  douyin/v0.2.0-beta.1        # 跟 main
  douyin/v0.2.0               # 跟 release
  registry/2026.08            # 可选里程碑
```

---

## 12. 与主程序的约定

- 中心索引文件名为 `registry.json`（实施时同步修改主程序下载器；当前代码仍使用 `plugins-manifest.json`）
- 用户通过 `plugins.repo_ref` 选择 `main` 或 `release`，无需协议层 `channel` 字段
- 检查更新时，可将远程条目中的 `release_notes` 一并返回给前端，用于展示目标版本说明
- 后续若增加 `min_core_version` / `api_version` 等兼容字段，写在分插件 `manifest.json` 中，由 CI 一并汇总

---

## 实施状态

**Phase 1 已落地：** 目录迁入 `plugins/`、分插件 `manifest.json` 纳入版本控制、本地 `scripts/generate_registry.py` 生成索引并双写 `plugins-manifest.json`。

**Phase 2 已落地：** `validate-and-sync`（PR 校验 + CI 回写生成物）、`tag-releases`（合入 `main`/`release` 后打插件 Tag）；脚本拆为 `registry_lib` / `generate_registry` / `check_manifests` / `print_new_tags`。主程序改读 `registry.json` 仍待后续阶段。
