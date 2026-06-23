# Plan: Phase 0 — Freeze & Baseline (冻结与基线)

## Summary
停止向平台堆砌功能，审计每个可见控件是否真正接入后端服务，禁用/隐藏所有未实现控件（消除虚假可供性），建立 8 条可重复的端到端测试数据，记录当前页面截图作为变更基线，锁定 Windows 运行与打包环境。

## User Story
As a 产品负责人, I want 正式界面中不存在"可点击但不生效"的控件，且所有可见交互都有明确的后端接线状态，So that 后续阶段可以在可信任的基线上进行整改，而非在失控的控件堆上重建。

## Problem → Solution
当前状态：WorkbenchWindow 注册 8 个页面，其中 2 个（IMPORT, CONFIG）是占位符 ("即将推出")；DataWorkspace 和 InferWorkspace 已编码但未接入页面栈，成为死代码；多个增强复选框虽有 UI 但未连接任何服务逻辑；TileCache/TileGrid 模块已实现但零消费者 → 目标状态：所有未实现控件已隐藏/禁用并有禁用说明；所有可见控件可追踪至真实信号连接或服务调用；死代码已归档或标记。

## Metadata
- **Complexity**: Medium (3–10 files, audit + cleanup only)
- **Source PRD**: `docs/superpowers/plans/X-AnyLabeling_离线深度学习平台_产品化UI整改落地方案.md`
- **PRD Phase**: 阶段 0 — 冻结与基线 (line 1240)
- **Estimated Files**: 8–12 modified, 1 new (audit report)

---

## UX Design

### Before
```
WorkbenchWindow 8-page stack:
[0] ✅ ProjectHomeWidget
[1] ❌ "(即将推出)" placeholder
[2] ❌ "(即将推出)" placeholder
[3] ✅ LabelWorkspace
[4] ✅ PreprocessWorkspace   ← augmentation checkboxes dead
[5] ✅ TrainWorkspace        ← resume checkbox dead
[6] ✅ EvaluateWorkspace
[7] ✅ ExportWorkspace

Dead: DataWorkspace (159L), InferWorkspace (206L), TileCache, TileGrid, HugeImageCanvas
```

### After
```
All ❌ controls disabled with tooltip explanation:
  - Augmentation checkboxes → disabled, tooltip "(规划中)"
  - Resume training checkbox → hidden
  - IMPORT page → missing-condition page: "DataWorkspace implemented, pending page-stack wiring"
  - CONFIG page → missing-condition page: "TaskConfigurator needs workspace refactor"
  - Dead modules → # FUTURE: / # STATUS: header comments
```

### Interaction Changes
| Touchpoint | Before | After |
|---|---|---|
| IMPORT nav | "(即将推出)" | "缺少：DataWorkspace 未接入页面栈" |
| CONFIG nav | "(即将推出)" | "缺少：TaskConfigurator 需重构为 WorkSpace" |
| Augmentation checkboxes | Clickable, no-op | Disabled, tooltip "(规划中)" |
| Resume training checkbox | Clickable, no backend | Hidden |

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `views/platform/workbench_window.py` | 230–280 | `_load_page()` placeholder logic |
| P0 | `views/platform/workbench_window.py` | 142–219 | `set_project()` service wiring |
| P1 | `views/platform/data_workspace.py` | all | Dead code — wire or archive |
| P1 | `views/platform/infer_workspace.py` | all | Dead code — wire or archive |
| P1 | `views/platform/preprocess_workspace.py` | 158–177 | Augmentation checkboxes — unwired |
| P1 | `views/platform/train_workspace.py` | 432–440 | Resume checkbox — UI only |

---

## Patterns to Mirror

### CRITICAL: No QThreadPool anywhere
// SOURCE: services/auto_labeling/model_manager.py:2297
Temporary `GenericWorker(QObject) + QThread` per invocation. `threading.Lock` for concurrency gating.

### CRITICAL: Training uses subprocess, not QThread
// SOURCE: services/auto_training/ultralytics/trainer.py:93
`subprocess.Popen` + `threading.Thread` for stdout read loop + callback notifications.

### CRITICAL: Placeholder replacement pattern
// SOURCE: views/platform/workbench_window.py:257-280
```python
def _load_page(self, step: PipelineStep):
    if step == PipelineStep.IMPORT:
        pass  # Line 265: remains placeholder
    elif step == PipelineStep.PREPROCESS:
        self._preprocess_workspace = PreprocessWorkspace()
        self._replace_page(4, self._preprocess_workspace)
```

### Service injection pattern
// SOURCE: views/platform/workbench_window.py:142-219
Services created in `set_project()`, injected via `set_project_context()` on each workspace.

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `views/platform/workbench_window.py` | UPDATE | Replace placeholders with condition pages |
| `views/platform/preprocess_workspace.py` | UPDATE | Disable unwired augmentation checkboxes |
| `views/platform/train_workspace.py` | UPDATE | Hide resume checkbox |
| `views/labeling/viewport/tile_cache.py` | UPDATE | Add `# FUTURE:` comment header |
| `views/labeling/viewport/tile_grid.py` | UPDATE | Add `# FUTURE:` comment header |
| `views/labeling/widgets/huge_image_canvas.py` | UPDATE | Add `# FUTURE:` comment header |
| `views/platform/data_workspace.py` | UPDATE | Add `# STATUS:` comment header |
| `views/platform/infer_workspace.py` | UPDATE | Add `# STATUS:` comment header |
| `.claude/PRPs/audit-report.md` | **CREATE** | Full control wiring audit table |
| `tests/e2e/platform/test_fixtures.py` | UPDATE | Add 8 E2E test fixtures |

## NOT Building (Phase 0 scope)

- New features — audit/disable/hide only
- Shell UI refactor (Phase 2)
- Real augmentation pipeline (Phase 3)
- Business logic changes
- Domain model changes
- New dependencies

---

## Step-by-Step Tasks

### Task 0: Control Wiring Audit
- **ACTION**: Scan every `.py` in `views/platform/` for interactive controls and their signal connections
- **IMPLEMENT**: Compile audit table in `.claude/PRPs/audit-report.md`:
  ```
  | File:Line | Control | Type | Signal | Slot/Handler | Status |
  |---|---|---|---|---|---|
  | preprocess_workspace.py:161 | H-Flip | QCheckBox | stateChanged | (none) | ❌ DEAD |
  | train_workspace.py:542 | Start Training | QPushButton | clicked | _on_start() | ✅ WIRED |
  ```
- **VALIDATE**: Table covers 50+ controls, each marked ✅/❌/⚠️

### Task 1: Disable Unwired Controls
- **ACTION**: For every ❌ control in the audit table, add `setEnabled(False)` or `setVisible(False)` with explanatory inline comment
- **IMPLEMENT**:
  - `preprocess_workspace.py`: `setEnabled(False)` on 4 augmentation checkboxes + tooltip "(规划中)"
  - `train_workspace.py`: `setVisible(False)` on resume checkbox
- **GOTCHA**: Keep controls — do NOT remove. Later phases will wire them
- **VALIDATE**: Launch GUI — all disabled controls show tooltips, cannot be interacted with

### Task 2: Replace Placeholder Pages
- **ACTION**: Modify `_load_page()` to show specific missing-condition pages
- **IMPLEMENT**: Replace "(即将推出)" with:
  - IMPORT: "DataWorkspace implemented but not wired to page stack. See: data_workspace.py"
  - CONFIG: "TaskConfigurator exists but needs workspace refactor. See: task_configurator.py"
- **GOTCHA**: Do NOT wire DataWorkspace now — Phase 1 task
- **VALIDATE**: IMPORT/CONFIG nav shows specific conditions

### Task 3: Mark Dead Code Modules
- **ACTION**: Add `# FUTURE:` or `# STATUS:` header comments to unused modules
- **IMPLEMENT**:
  - `tile_cache.py`: `# FUTURE: Online tile-based viewport rendering. Implemented, zero consumers.`
  - `tile_grid.py`: `# FUTURE: Tile decomposition for online renderer. Implemented, zero consumers.`
  - `huge_image_canvas.py`: `# FUTURE: pyqtgraph-based canvas. Tested, not wired to main Canvas.`
  - `data_workspace.py`: `# STATUS: Implemented but not added to WorkbenchWindow page stack.`
  - `infer_workspace.py`: `# STATUS: Implemented but never instantiated.`
- **VALIDATE**: Each dead file has clear header comment

### Task 4: Create 8 E2E Test Fixtures
- **ACTION**: Create synthetic test datasets using numpy + cv2 (no binary files)
- **IMPLEMENT**: Fixtures for E2E-01 through E2E-08 (PRD section 15, line 1411)
  - E2E-01: 10 JPGs + YOLO labels (detection)
  - E2E-02: 2 TIFFs 8000×8000 + polygon labels (large-image seg)
  - E2E-03: 3 subdirs × 5 images (group isolation)
  - E2E-04: 5 defect + 5 clean (negative samples)
  - E2E-05: 3 images minimal project (crash recovery)
  - E2E-06: normal + corrupt + zero-byte + unsupported (error files)
  - E2E-07: 2 images (offline scenario)
  - E2E-08: various resolutions (high DPI)
- **VALIDATE**: `pytest tests/e2e/platform/test_fixtures.py -v` passes

### Task 5: Capture Baseline Screenshots
- **ACTION**: Script to launch app headless and screenshot all 8 platform pages
- **IMPLEMENT**: `scripts/baseline_screenshots.py` using `QT_QPA_PLATFORM=offscreen`
- **VALIDATE**: Screenshots exist in `docs/baseline/`

### Task 6: Lock Packaging Baseline
- **ACTION**: Snapshot PyInstaller specs + verify build
- **IMPLEMENT**: Record spec file paths, run trial build, record command + hash
- **VALIDATE**: Generated executable launches and loads test project

---

## Testing Strategy

| Test | Input | Expected Output |
|---|---|---|
| Audit report completeness | Run `python scripts/audit_controls.py` | 50+ controls with wiring status |
| Disabled controls visible | Launch GUI, navigate each page | All disabled have tooltips |
| Placeholder pages | Click IMPORT or CONFIG nav | Specific conditions shown |

---

## Validation Commands

```bash
# Audit script
python scripts/audit_controls.py
# EXPECT: Audit table written to .claude/PRPs/audit-report.md

# E2E fixtures
pytest tests/e2e/platform/test_fixtures.py -v
# EXPECT: 8 fixture tests pass

# Regression guard
pytest tests/ -x --timeout=60 -m "not slow"
# EXPECT: All existing tests pass
```

---

## Agent Orchestration

> 遵循 `.claude/PRPs/agent-orchestration-rules.md` 强制编排规则。

### Core Rules (21 条铁律)

1. 主会话负责整体调度和最终决策，不得独自完成全部分析+实现+审查。
2. 每个 Task 开始前必须调用该 Task 的 PRECHECK_AGENTS。
3. 需要架构判断时调用 `architect`。
4. 新功能或 Bug 修复必须先调用 `tdd-guide`。
5. 生产代码默认由主会话串行写入。
6. `tdd-guide` 只有在 WRITE_SCOPE 明确包含测试文件时，才能修改测试文件。
7. 完成 Python 修改后必须调用 `python-reviewer`。
8. 每个 Task 完成后必须调用 `code-reviewer`。
9. 涉及文件路径、子进程、模型加载、用户输入和本地数据时，必须调用 `security-reviewer`。
10. 构建失败时调用对应 `build-error-resolver` 分析根因。
11. 所有专业 Agent 必须返回结构化报告。
12. 审核 Agent 默认只读，不允许直接修改源码。
13. 主会话根据专业 Agent 报告实施修复。
14. 禁止两个 Agent 同时修改同一个文件。
15. 独立只读分析可以并行；写入任务必须串行。
16. 任何 Agent 不得执行 `git push`, `merge`, `rebase`, `reset`, `clean`。
17. 提交仅由主会话在 Phase 完成后统一执行。
18. Auto 模式只用于权限自动判断，不得替代 Agent 编排。
19. 最终 Implementation Report 必须增加 Agent Execution Log。

### Agent Assignment

| Agent | Role | Tasks | Scope |
|-------|------|-------|-------|
| `security-reviewer` | 安全审查 | All | 审计报告中的路径/导入/死代码安全标记 |
| `code-reviewer` | 代码审查 | All | 审计报告完整性 + 代码清理合规 |
| `python-reviewer` | Python 审查 | All | PEP 8 + 死代码标记规范 |

### EXECUTION_MODE

**Sequential** — Task 串行执行。Phase 0 为审计阶段，无 tdd-guide/architect 需求。

每个 Task 内部：
- **PRECHECK** Agent 可并行调用（只读互不干扰）
- **IMPLEMENT** 由主会话串行写入（同一时间只有一个写入者）
- **POST_REVIEW** Agent 可并行调用（只读互不干扰）

### WRITE_SCOPE

| Agent | Permitted Files | Constraint |
|--------|-----------------|------------|
| 主会话 | `anylabeling/` 下所有源码 + `docs/` 下文档 + `scripts/` | 生产代码与文档唯一写入者 |
| `tdd-guide` | `tests/` 下测试文件 | 仅限测试文件，不得修改生产代码 |
| 审核 Agent | 只读 | 不得修改任何文件 |

### Agent Execution Log

| Task | Agent | 阶段 | 输出摘要 | 是否采纳 | 验证结果 |
|------|-------|------|----------|----------|----------|
| ... | ... | ... | ... | ... | ... |

---

## Acceptance Criteria
- [ ] Audit report covers all interactive controls in views/platform/
- [ ] All unwired controls disabled/hidden with explanation
- [ ] IMPORT and CONFIG nav show specific missing conditions
- [ ] Dead code modules have `# FUTURE:` / `# STATUS:` comments
- [ ] 8 E2E fixtures created and testable
- [ ] Baseline screenshots saved to `docs/baseline/`
- [ ] Packaging baseline recorded

## Completion Checklist
- [ ] No "clickable but dead" controls remain
- [ ] Business logic untouched
- [ ] Existing patterns reused
- [ ] No new dependencies

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Too many unwired controls discovered | High | Low | Prioritize user-visible; defer internal helpers to Phase 1 |
| Screenshot script fails in CI | Medium | Low | Use QT_QPA_PLATFORM=offscreen |
| Disabled controls confuse users | Medium | Low | Every disabled control has explanatory tooltip |

## Notes
- Phase 0 is pure audit + cleanup. No new features. No code removal.
- The most important artifact is `audit-report.md` — the ground truth for all subsequent phases.
- DataWorkspace and InferWorkspace disposition decisions deferred to Phase 1.
- 8 E2E test cases sourced from PRD section 15 (line 1411).
