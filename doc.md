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
- [ ] CI 通过（`CHANGELOG.md` 由 merge 后 CI 写入，无需手改）

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
         CI 校验 + 生成 registry.json
         + 写入插件 / 根目录 CHANGELOG.md
                              ↓
                    merge 后自动提交生成物
                              ↓
                    Beta 用户（repo_ref=main）获取
```

### 8.2 Stable（`release`）

```
main 上测试完成
        ↓
merge 到 release（版本须为正式版 x.y.z）
        ↓
CI 校验 + 生成 registry.json
+ 写入插件 / 根目录 CHANGELOG.md
        ↓
merge 后自动提交生成物
        ↓
普通用户（repo_ref=release）获取
```

---

## 9. CI 自动化

### 9.1 PR 时（校验，不改写仓库）

- 各插件 `manifest.json` 是否完整、JSON 合法
- `domain` 是否与目录名一致
- `version` 是否符合 SemVer，以及是否符合目标分支规则（若 PR 指向 `release`，拒绝 `-beta`）
- `release_notes` 是否存在（升级 / 新插件应提供本版说明）
- 插件目录结构是否正确
- **重新生成** `registry.json` 后应与仓库中已有文件一致（若不一致则 fail，提示等待 merge 后由 bot 更新，或仅在生成物已过期时提示）

PR 阶段以校验为主；**不在 PR 上由人类维护** `registry.json`、各插件 `CHANGELOG.md`、以及根目录 `CHANGELOG.md`。

### 9.2 Merge 后（自动提交）

合入 `main` 或 `release` 后，CI 自动：

1. 扫描 `plugins/*/manifest.json`
2. 注入 `path` 等派生字段
3. 对比**旧** `registry.json` 与新生成结果，得出新增 / 更新 / 移除
4. 生成 / 更新根目录 `registry.json`（含各插件当前 `release_notes`）
5. 按第 10 节规则更新各 `plugins/<domain>/CHANGELOG.md`
6. 按第 10 节规则更新根目录 `CHANGELOG.md`
7. **自动提交**回当前分支（bot commit）
8. （可选）创建插件 Tag

生成文件禁止手改；唯一更新途径是 CI bot。

---

## 10. Release Notes 与 CHANGELOG

插件本版说明手写在 manifest 的 `release_notes`；插件历史与 Registry 整体变更均由 CI 维护。

### A. 根目录 CHANGELOG.md（Registry 级，CI 生成）

路径：仓库根目录 `CHANGELOG.md`。每次 merge 后，CI 对比更新前的 `registry.json` 与新生成的索引，自动归类：

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

registry.json         # merge 后 CI 生成（含各插件本版 release_notes）
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

**Phase 1 已落地（本地）：** 目录迁入 `plugins/`、分插件 `manifest.json` 纳入版本控制、`scripts/generate_registry.py` 生成 `registry.json` 并双写兼容用的 `plugins-manifest.json`。CI 自动提交与主程序改读 `registry.json` 仍待后续阶段。
