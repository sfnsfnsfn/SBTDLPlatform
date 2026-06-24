# V4 平台产品化 — 多 Agent 并行开发计划

> **PRD**: `.claude/PRPs/prds/sbtl-platform-v4.prd.md`
> **方案来源**: `SBTDLPlatform_最终可执行并行开发方案_1920x1080_ECC_TDD.md`
> **创建时间**: 2026-06-24
> **策略**: multi-phase-parallel (8 Phase, 20+ Task, 7 Agent)

---

## 并行执行架构

```
Phase A (Agent A) ─────────────────────────────────────────────┐
  Bug 修复 + 安全网                                            │
                                                               │
Phase B (Agent B) ──┐                                          │
  DB 基础设施         │  group-1 并行                          │
                     ├────────────────────── Phase D (Agent D) ── Phase E ── Phase F1 ── Phase F2
Phase C (C1+C2+C3) ──┘  Bootstrap/迁移       (Lead+E1+E2)    (F+Lead)    (F)
  Repository 层                          Service 写 DB      Workflow     UI+1920
                                                              │
                                                              ├── Phase G (Agent G)
                                                                  回归+文档
```

## Phase 概览

| # | Phase | Agent | 任务数 | 新建文件 | 修改文件 | 测试文件 | 依赖 |
|---|-------|-------|--------|----------|----------|----------|------|
| A | 安全网与 Bug 修复 | A | 4 | 0 | 3 | 4 | - |
| B | DB 基础设施 | B | 3 | 3 | 0 | 3 | A |
| C | Repository 层 | C1,C2,C3 | 6 | 8 | 1 | 5 | A |
| D | Bootstrap/迁移 | D | 2 | 2 | 0 | 2 | B+C |
| E | Service 接入 DB | Lead,E1,E2 | 4 | 1 | 5 | 4 | D |
| F1 | Workflow/Context | F,Lead | 2 | 0 | 2 | 2 | E |
| F2 | UI 接入 DB + 1920 | F | 4 | 0 | 5 | 4 | F1 |
| G | 回归与文档 | G | 1 | 4 | 0 | 1 | F1 |

## 关键文件保护规则

| 文件 | 保护级别 | 允许修改者 |
|------|----------|------------|
| `workbench_window.py` | 🔴 核心 | 仅 Lead (PR-00 A0 除外) |
| `project_session.py` | 🔴 核心 | 仅 Lead |
| `workflow_state.py` | 🔴 核心 | 仅 Lead (F 可改) |
| DB schema (`*.sql`) | 🔴 核心 | 仅 B Agent，migration 增量 |
| 新文件 (`sqlite_repositories/`, `project_db.py`, etc.) | 🟢 安全 | 对应 Agent 可自由创建 |
| 测试文件 | 🟢 安全 | 对应 Agent 可自由创建 |

## 合并顺序

```
PR-00  A: Bug 修复 (Agent A)                          ← 先合并
PR-01  B: DB 基础设施 (Agent B)                       ← 可与 PR-02 并行
PR-02  C: Repository 层 (Agent C1,C2,C3)              ← 可与 PR-01 并行
PR-03  D: Bootstrap (Agent D)                         ← 依赖 B+C
PR-04  E: Service 写 DB (Lead+E1+E2)                  ← 依赖 D
PR-05  F1: Workflow/Context (F+Lead)                  ← 依赖 E
PR-06  F2: UI + 1920 (F)                              ← 依赖 F1
PR-07  G: 回归与文档 (G)                              ← 可与 PR-06 并行
```

## 执行流程（每个 Task 标准化）

```
1. /ecc:plan          → 重述需求、声明 WRITE_SCOPE、确认测试文件
2. 调用 tdd-guide     → 先写失败测试
3. Red 阶段           → pytest 确认测试因功能缺失而失败
4. Green 阶段         → 最小生产代码让测试通过
5. Refactor 阶段      → 清理重复、保持接口
6. python-reviewer    → Python 代码审查
7. code-reviewer      → 通用代码审查
8. 输出完成报告       → 修改文件、新增测试、执行命令、已知风险
```

## 每 PR 验收命令

```bash
python -m compileall anylabeling
pytest tests/platform tests/views/platform -m "not slow" -q
python scripts/migrate_project_db.py <demo_project> --dry-run --rebuild-index
```

## 最小发布候选标准

- [ ] 修复全部 P0/P1 bug
- [ ] 新项目自动创建 project.sqlite
- [ ] 旧项目可 bootstrap
- [ ] ImportService / DatasetBuildService / TrainingService 写 DB
- [ ] WorkflowState 读 DB
- [ ] TrainWorkspace 只列 completed dataset_builds
- [ ] ExportWorkspace 只列 ready models
- [ ] 1920x1080 主布局无明显交互问题
- [ ] 全量测试通过
