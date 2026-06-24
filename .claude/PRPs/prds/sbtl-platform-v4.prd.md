# SBTDL Platform V4 — 产品化架构升级

## Problem Statement

当前 SBTDL Platform 代码存在大量 bug，工程无法正常使用，不能交付客户。
根本原因：代码架构采用"文件目录扫描 + JSON/Manifest + UI 直接装配服务"的隐式耦合模式，
导致状态判断依赖目录扫描（`any(dir.iterdir())`）、UI 层直接创建 Service、多处重复维护数据源，
使 bug 修复和功能迭代异常困难。

## Evidence

- 已知 P0 bug：WorkbenchWindow 预处理页 `exts` 未定义导致崩溃
- 已知 P0 bug：`_create_train_workspace()` 不保存 `self._train_workspace` 引用
- 已知 P0 bug：AssetRepository 分组扫描不递归子目录
- 已知 P1 bug：未实现的增强配置仍可勾选并写入配置
- 代码现状：WorkbenchWindow 1837 行，TrainWorkspace 1247 行，多个 Service 超 600 行
- 架构耦合：UI 层直接扫描 `assets/runs/models` 目录判断流程状态

## Proposed Solution

不把项目改成"数据库型软件"，而是把 SQLite 作为**项目元数据索引与状态中心**：

```
文件系统：保存原图、大图切片、标注原始文件、dataset build、训练日志、模型权重、导出包
SQLite：保存资产索引、标注摘要、数据集构建状态、训练 run、job、model、评估摘要、页面状态、事件日志
ProjectContext：统一装配 Repository + Service + Query，避免 WorkbenchWindow 直接 new Service
```

同时将 UI 适配到 1920×1080 桌面窗口，通过 ECC + TDD 流程拆分 20+ 个可并行任务，
支持多 Agent 并行开发、串行合并。

## Key Hypothesis

We believe SQLite 元数据索引 + ProjectContext 统一装配 will 消除 UI 与文件系统的直接耦合
for 开发团队和终端用户.
We'll know we're right when 全量测试通过 + 旧项目可打开 + 所有 11.1 功能验收项达标.

## What We're NOT Building

- 不删除旧 JSON/manifest — 首期继续保留兼容
- 不重写 ProcessJobRunner — 首期只做 DB 镜像写入
- 不把图片/模型权重写入 SQLite — DB 只存元数据
- 不引入 SQLAlchemy ORM — 只用标准库 sqlite3
- 不大规模重构所有页面 — 只改数据源接入方式

## Success Metrics

| Metric | Target | How Measured |
|--------|--------|--------------|
| 产品可交付 | 100% | 全量功能验收通过（11 项） |
| Bug 修复 | P0/P1 清零 | pytest + 手工验收 |
| 架构解耦 | UI 不再直接扫描目录 | 代码审查 |
| 旧项目兼容 | 100% | 旧项目可打开并自动 bootstrap |
| 测试覆盖 | 每个 Task 有测试 | pytest 报告 |
| UI 适配 | 1920×1080 无重叠 | 手工截图验收 |

## Open Questions

- [ ] 旧项目 bootstrap 性能：大项目（10万+ 图片）首次索引耗时？
- [ ] WAL 模式在 Windows 下的文件锁定行为？
- [ ] TaskDrawer 动画在低配机器上的帧率？

---

## Users & Context

**Primary User**
- **Who**: 深度学习标注/训练工程师，使用桌面应用进行数据准备、标注、模型训练、评估、导出
- **Current behavior**: 当前代码无法正常使用
- **Trigger**: 需要完成一个完整的 ML 工作流（导入数据 → 标注 → 训练 → 评估 → 导出）
- **Success state**: 在 1920×1080 窗口下流畅完成全流程，无崩溃

**Job to Be Done**
When 接到一个新的计算机视觉标注/训练任务, I want to 在统一桌面平台中完成从数据导入到模型导出的完整流程, so I can 快速交付训练好的模型给下游使用.

**Non-Users**
- 云端/SaaS 用户 — 本产品是离线桌面应用
- 非技术用户 — 需要一定 ML 基础

---

## Solution Detail

### Core Capabilities (MoSCoW)

| Priority | Capability | Rationale |
|----------|------------|-----------|
| Must | 修复全部 P0/P1 bug | 代码无法使用，必须先行 |
| Must | SQLite 基础设施 (ProjectDb/Migration/UnitOfWork) | 所有后续任务的依赖 |
| Must | Repository 层 (Records/Ports/SQLite Repos) | 数据访问解耦核心 |
| Must | 旧项目 Bootstrap | 不能破坏已有项目 |
| Must | Service 写 DB (Import/DatasetBuild/Training/Job) | 数据流入 DB |
| Must | WorkflowState 改 DB 查询 | 消除目录扫描 |
| Must | WorkbenchWindow 接入 ProjectContext | UI-Service 解耦 |
| Must | TrainWorkspace 只列 completed builds | 训练流程正确性 |
| Must | 1920×1080 主布局适配 | 目标分辨率 |
| Should | Data/Preprocess/Evaluate/Export UI 接入 DB | 完整解耦 |
| Could | 全流程回归脚本 | 质量保障 |
| Won't | 删除旧 JSON/manifest | 首期保留兼容 |

### MVP Scope

1. 修复全部 P0/P1 bug
2. 新建项目自动创建 `project.sqlite`
3. 旧项目可 bootstrap
4. ImportService / DatasetBuildService / TrainingService 写 DB
5. WorkflowState 读 DB
6. TrainWorkspace 只列 completed dataset_builds
7. ExportWorkspace 只列 ready models
8. 1920×1080 主布局无明显交互问题
9. 全量测试通过

### User Flow

```
新建/打开项目 → 自动创建/bootstrap SQLite
  → Data: 查看资产统计（来自 DB）
  → Import: 导入图片/标注（写 DB）
  → Task Config: 配置任务类型和标签
  → Label: 标注（保留现有画布）
  → Preprocess: 数据集构建（写 DB 状态）
  → Train: 选择 completed build → 训练（写 DB 状态）
  → Evaluate: 选择 completed run → 评估（写 DB）
  → Export: 选择 ready model → 导出
```

---

## Technical Approach

**Feasibility**: HIGH — Python 标准库 `sqlite3` + WAL 模式即可实现，不引入外部依赖。

**Architecture Notes**
- DDD 分层保持：`domain → application → infrastructure → adapters`
- `ProjectContext` 作为项目级依赖装配入口，WorkbenchWindow 只消费 context
- Repository Protocol 定义在 `application/ports/`，实现在 `infrastructure/sqlite_repositories/`
- `ports.py` (44行单文件) 需转为 `ports/` 包目录
- DB schema 只通过 migration 增量演进

**Technical Risks**

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| 旧项目 bootstrap 数据量大导致慢 | M | 分批扫描 + 进度回调 |
| WAL 文件复制时遗漏导致 DB 损坏 | L | 复制前 checkpoint(truncate=True) |
| 多 Agent 并行修改冲突 | H | 硬规则：核心文件串行合并，每人明确 WRITE_SCOPE |
| UI 坐标计算错误 | M | 手工截图验收 |

---

## Implementation Phases

| # | Phase | Description | Status | Parallel | Depends | PRP Plan |
|---|-------|-------------|--------|----------|---------|----------|
| 1 | A: 安全网与 Bug 修复 | 修复 P0/P1 bug，建立基础测试 | complete | - | - | [phase-a-bug-fixes.plan.md](../plans/phase-a-bug-fixes.plan.md) |
| 2 | B: DB 基础设施 | ProjectDb + MigrationRunner + UnitOfWork | complete | with 3 | 1 | [phase-b-db-infrastructure.plan.md](../plans/phase-b-db-infrastructure.plan.md) |
| 3 | C: Repository 层 | Records/Ports + 全部 SQLite Repositories + WorkflowQuery | complete | with 2, 4 | 1 | [phase-c-repository-layer.plan.md](../plans/phase-c-repository-layer.plan.md) |
| 4 | D: Bootstrap/迁移 | 旧项目索引重建 + CLI 工具 | pending | with 3 | 2, 3 | - |
| 5 | E: Service 接入 DB | Import/DatasetBuild/Training/Job 写 DB + ProjectContext | pending | - | 4 | - |
| 6 | F1: Workflow/Context | WorkflowState 改 DB + WorkbenchWindow 接入 ProjectContext | pending | - | 5 | - |
| 7 | F2: UI 接入 DB + 1920 坐标 | 全部 Workspace 改用 DB + 坐标调整 | pending | - | 6 | - |
| 8 | G: 回归与文档 | 全流程回归脚本 + 验收文档 | pending | with 7 | 6 | - |

### Phase Details

**Phase 1: A — 安全网与 Bug 修复**
- **Goal**: 消除已知 P0/P1 bug，代码达到基本可用状态
- **Scope**: Task A0-1 ~ A0-4（4 个 bug 修复）
- **Success signal**: 4 个 bug 全部修复 + 对应测试通过

**Phase 2: B — DB 基础设施**
- **Goal**: 建立 SQLite 连接、迁移、事务基础
- **Scope**: Task B1-1 ~ B1-3（ProjectDb, MigrationRunner, UnitOfWork）
- **Success signal**: DB 可打开/关闭/查询/事务/迁移

**Phase 3: C — Repository 层**
- **Goal**: 定义数据访问抽象并实现全部 SQLite Repository
- **Scope**: Task C1-1 ~ C3-1（Records, Ports, 7 个 SQLite Repos, WorkflowQuery）
- **Success signal**: 所有 Repository 通过契约测试

**Phase 4: D — Bootstrap/迁移**
- **Goal**: 旧项目自动索引重建 + CLI 迁移工具
- **Scope**: Task D1-1 ~ D1-2（Bootstrap + migrate_project_db.py）
- **Success signal**: 旧项目目录可成功 bootstrap 到 SQLite

**Phase 5: E — Service 接入 DB**
- **Goal**: 核心 Service 写入 DB，保留原有文件写入
- **Scope**: Task E1-1 ~ E2-3（ProjectContext 装配 + 4 个 Service 写 DB）
- **Success signal**: 导入/构建/训练流程数据正确写入 SQLite

**Phase 6: F1 — Workflow/Context**
- **Goal**: 流程状态从目录扫描切换为 DB 查询
- **Scope**: Task F1-1 ~ F1-2（WorkflowState 改 DB + WorkbenchWindow 接入）
- **Success signal**: 流程状态判断不再依赖目录扫描

**Phase 7: F2 — UI 接入 DB + 1920 坐标**
- **Goal**: 全部 Workspace 通过 ProjectContext 获取数据，UI 适配 1920×1080
- **Scope**: Task F2-1 ~ F2-4（5 个 Workspace）
- **Success signal**: 所有页面数据来自 DB，UI 坐标正确

**Phase 8: G — 回归与文档**
- **Goal**: 全流程验收 + 迁移文档
- **Scope**: Task G1-1（回归脚本、验收文档）
- **Success signal**: 全量验收通过

### Parallelism Notes

- Phase 2 (B) 和 Phase 3 (C) 可并行：B 建 DB 层，C 建 Repository 抽象，互不依赖
- Phase 3 (C) 和 Phase 4 (D) 可部分并行：D 依赖 C 的 Ports 定义，不依赖具体实现
- Phase 7 (F2) 和 Phase 8 (G) 可并行：UI 调整和回归脚本互不冲突
- Phase 内部：C 组 3 个子任务可并行，E 组 3 个子任务可并行

---

## Decisions Log

| Decision | Choice | Alternatives | Rationale |
|----------|--------|--------------|-----------|
| DB 方案 | Python sqlite3 + WAL | SQLAlchemy, aiosqlite | 零依赖，离线可用，WAL 支持并发读 |
| 大对象存储 | 文件系统 | SQLite BLOB | 图片/模型太大，DB 存路径更高效 |
| 旧项目兼容 | 自动 bootstrap | 强制迁移 | 不破坏已有项目 |
| ports.py | 转为 ports/ 包 | 新建独立文件 | 保持 DDD 分层结构 |
| UI 分辨率 | 1920×1080 | 响应式/多分辨率 | 目标客户统一配置 |

---

## Research Summary

**Technical Context**
- Python 标准库 `sqlite3` 完全满足需求，无需额外依赖
- WAL 模式支持读写并发，适合长时间训练任务的后台更新
- `PRAGMA foreign_keys=ON` 需每次连接设置
- 现有 `ports.py` (44行) 是单文件，需转为 `ports/` 包目录
- 现有 `shell/` 是目录（8 文件），非方案中提到的 `shell.py` 单文件

**Codebase Context**
- 需新建 ~15 个源文件，修改 ~15 个源文件
- 需新建 ~25 个测试文件（当前仅 1 个存在）
- 最大源文件：workbench_window.py (1837行), train_workspace.py (1247行)
- 方案未提及的页面：infer_workspace.py, label_workspace.py, import_workspace.py（需保持兼容）

---

*Generated: 2026-06-24*
*Status: DRAFT — ready for implementation planning*
