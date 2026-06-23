# Plan: Phase 1b — 构建参数真实接线 + CONFIG 页面接入

## Summary
启用普通图（无大图）数据集构建，修复 PreprocessWorkspace Build 按钮启用条件，将 TaskConfigurator 接入 CONFIG 页面替换占位符，验证构建参数从 UI → PreprocessConfig → TilePlan → DatasetBuild 的完整传递链路。

## User Story
As a 算法工程师, I want 项目中无大图时也能构建数据集，且 CONFIG 页可真实配置任务类型和标签, So that 数据准备三步（导入→配置→预处理）均可真实操作，无需绕过任何占位页面。

## Problem → Solution
Build 按钮仅在大图>0 时可用 → 有资产即启用。CONFIG 页是占位符 → TaskConfigurator 作为独立 WorkSpace 接入 `_load_page()`。构建参数传递链路存在但未经测试验证 → 新增 E2E 测试覆盖全链路。

## Metadata
- **Complexity**: Medium (6–8 files, ~300 lines)
- **Source PRD Phase**: 阶段 1 — 真实闭环 (子阶段 1b)
- **Depends On**: Phase 1a (complete)
- **PROD Coverage**: PROD-001 (CONFIG), PROD-006, PROD-007, PROD-008
- **Estimated Files**: 6 modified, 1 new

---

## UX Design

### Before
```
CONFIG:  "TaskConfigurator exists but needs workspace refactor"
PREPROCESS: Build 按钮仅 _large_images > 0 时启用
```

### After
```
CONFIG:
┌ TaskConfigurator ───────────────────────────────────────┐
│ 任务类型 [检测(HBB) ▼]    标签 [+ 添加] [导入] [删除]   │
│ 标注规则: 最小区域[1] px²  ┌ ID |名称 |颜色          ┐  │
│                           │ 0  |defect|#FF0000       │  │
│                           └──────────────────────────┘  │
│                      [← 返回项目] [保存并进入标注 →]    │
└──────────────────────────────────────────────────────────┘

PREPROCESS: Build 按钮有资产时即启用
            大图预览区: 无大图时显示 "正常图片模式"
```

### Interaction Changes
| Touchpoint | Before | After |
|---|---|---|
| CONFIG nav | 占位文本 | TaskConfigurator 工作区 |
| "保存并进入标注 →" | 不存在 | 发射 task_configured → 保存 TaskSpec → 导航 LABEL |
| "← 返回项目" | 不存在 | 发射 back_requested → 导航 PROJECT |
| Build 按钮 | 仅大图>0 | 任何资产>0 |
| 大图预览区 | 始终可见 | 无大图时显示模式提示 |
| 后台任务 | 无 | 构建仍由 workbench_window 子进程管理（不变） |
| 关闭窗口 | 无特殊 | 检查 is_modified → 提示未保存（Phase 2 完善） |

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `views/platform/task_configurator.py` | 81–107, 531–544 | 类定义 + set_project_context() + _on_next() 信号发射 |
| P0 | `views/platform/preprocess_workspace.py` | 200–214, 227–251 | set_large_images() + _get_current_config() |
| P0 | `views/platform/workbench_window.py` | 257–286, 513–553 | _load_page CONFIG case + _load_task_specs() |
| P1 | `platform/application/dataset_build_service.py` | 95–165 | build() 完整签名和参数验证 |

---

## Patterns to Mirror

### CRITICAL: TaskConfigurator signals (3 signals)
// SOURCE: views/platform/task_configurator.py:91-93
```python
task_configured = pyqtSignal(TaskSpec)
back_requested = pyqtSignal()
next_requested = pyqtSignal()
```

### CRITICAL: _on_next() → signal emission order
// SOURCE: views/platform/task_configurator.py:531-544
```python
def _on_next(self):
    task_spec = TaskSpec(family=..., labels=tuple(self._labels))
    self.task_configured.emit(task_spec)
    self.next_requested.emit()
```

### CRITICAL: WorkSpace creation + wiring pattern
// SOURCE: views/platform/workbench_window.py:282-292
```python
def _create_train_workspace(self):
    workspace = TrainWorkspace()
    workspace.set_project_context(job_service=..., training_service=...)
    return workspace
```

### Build button state management
// SOURCE: views/platform/preprocess_workspace.py:200-214
```python
def set_large_images(self, image_paths):
    self._large_images = image_paths
    count = len(image_paths)
    self._build_btn.setEnabled(count > 0)  # ← CHANGED: any asset > 0
```

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `views/platform/workbench_window.py` | UPDATE | Wire TaskConfigurator to CONFIG; add _create_config_workspace(); add _on_task_configured() handler |
| `views/platform/preprocess_workspace.py` | UPDATE | Enable Build when assets>0; add normal-image mode UI; guard tile preview for empty large_images |
| `views/platform/task_configurator.py` | UPDATE | Add is_modified dirty tracking |
| `tests/platform/views/test_task_configurator.py` | UPDATE | Add WorkSpace-mode tests (4 new) |
| `tests/platform/views/test_preprocess_workspace.py` | UPDATE | Build button enable tests for normal-image mode (file already exists with PreprocessConfig tests) |
| `tests/e2e/platform/test_fixtures.py` | UPDATE | Add parameter passthrough E2E test |

## NOT Building (1b scope)

- DatasetBuild with progress/cancel UI (Phase 3)
- Slice preview with label overlay rendering (Phase 3)
- Augmentation real pipeline wiring (Phase 3)
- 5-domain navigation (Phase 2)
- Training readiness check UI (Phase 4)
- Local model library selector (Phase 4)

---

## Agent Orchestration

> 遵循 `.claude/PRPs/agent-orchestration-rules.md` 强制编排规则。

### Core Rules (21 条铁律)

1. 主会话负责整体调度和最终决策，不得独自完成全部分析+实现+审查。
2. 每个 Task 开始前必须调用该 Task 的 PRECHECK_AGENTS。
3. 需要架构判断时调用 `architect`；新功能/Bug 修复先调用 `tdd-guide`。
4. 生产代码由主会话串行写入；`tdd-guide` 仅在 WRITE_SCOPE 授权时写测试。
5. Python 修改后 → `python-reviewer`；Task 完成后 → `code-reviewer`。
6. 文件路径/子进程/模型加载/用户输入/本地数据 → `security-reviewer`。
7. 构建失败 → `build-error-resolver`。审核 Agent 只读不修改源码。
8. 独立只读分析可并行；写入任务必须串行；禁止两个 Agent 同时修改同文件。
9. Agent 禁止 git push/merge/rebase/reset/clean；提交仅由主会话执行。
10. Auto 模式只用于权限判断，不替代 Agent 编排。
11. Implementation Report 必须增加 Agent Execution Log。

### Agent Assignment

| Agent | Role | Tasks | Scope |
|-------|------|-------|-------|
| `architect` | 架构审查 | T2, T3 | CONFIG 页面接线 + dirty-state 设计 |
| `tdd-guide` | 测试驱动 | T0, T1, T3, T4, T5 | 新功能先测试 + 测试用例设计 |
| `security-reviewer` | 安全审查 | T2, T5 | 项目路径处理 + E2E 文件操作 |
| `code-reviewer` | 代码审查 | All | 每 Task 完成后强制审查 |
| `python-reviewer` | Python 审查 | All | PEP 8 合规 + 惯用法检查 |

### EXECUTION_MODE

**Sequential** — Task 串行执行：T0 → T1 → T2 → T3 → T4 → T5。

每个 Task 内部：
- **PRECHECK** Agent 可并行调用（只读互不干扰）
- **IMPLEMENT** 由主会话串行写入（同一时间只有一个写入者）
- **POST_REVIEW** Agent 可并行调用（只读互不干扰）

### WRITE_SCOPE

| Agent | Permitted Files | Constraint |
|--------|-----------------|------------|
| 主会话 | `anylabeling/` 下所有源码 | 生产代码唯一写入者 |
| `tdd-guide` | `tests/` 下测试文件 | 仅限测试文件，不得修改生产代码 |
| 审核 Agent | 只读 | 不得修改任何文件 |

### Agent Execution Log

| Task | Agent | 阶段 | 输出摘要 | 是否采纳 | 验证结果 |
|------|-------|------|----------|----------|----------|
| ... | ... | ... | ... | ... | ... |

---

## Hard Blockers

### HB-3: TaskConfigurator persistence
- **Question**: TaskConfigurator doesn't save to ProjectFileStore. Who handles persistence?
- **Assumption**: workbench_window's `_on_task_configured` handler calls `ProjectFileStore.save_task_spec()`. This follows the existing pattern where WorkbenchWindow owns service orchestration.
- **Risk**: If `ProjectFileStore.save_task_spec()` doesn't exist, we add it as a thin wrapper around JSON write.

### HB-4: Normal image build — image_sources requirement verified
- **Finding**: `_collect_build_inputs()` (workbench_window.py:1191-1258) already creates `FileImageSource` for all assets and passes them to build. **No code change needed** — only UI enable condition.
- **Resolution**: UI-only fix. Verified by code audit.

---

## Step-by-Step Tasks

### Task 0: Enable normal image build in PreprocessWorkspace
- **ACTION**: Modify `set_large_images()` to enable Build when any assets present
- **PRECHECK_AGENTS**: `tdd-guide` (UI 行为变更，先定义测试期望)
- **IMPLEMENTATION_AGENT**: 主会话 — 修改 `preprocess_workspace.py`
- **POST_REVIEW_AGENTS**: `code-reviewer` + `python-reviewer`
- **IMPLEMENT**:
  1. Add `self._total_assets = 0` in `__init__`
  2. In `set_large_images()`: `self._total_assets = len(image_paths)`; change line 213 to `self._build_btn.setEnabled(self._total_assets > 0)`
  3. When `self._large_images` is empty and `self._total_assets > 0`: set `_large_image_label` to "正常图片模式 (Normal image mode)"
  4. In `_on_tile_params_changed()`: add `if not self._large_images: return` early guard to avoid stale estimates
  5. Hide `_tile_preview_label` when `_large_images` is empty
- **MIRROR**: `set_large_images()` at `preprocess_workspace.py:200-214`
- **IMPORTS**: None
- **GOTCHA**: build handler at workbench_window.py:651 already checks `if config.tile_width and config.tile_height:` before creating TilePlan — no change needed
- **VALIDATE**: `python -m pytest tests/views/platform/test_preprocess_workspace.py -v`

### Task 1: Write PreprocessWorkspace build button tests
- **ACTION**: Add 4 tests to existing `tests/platform/views/test_preprocess_workspace.py`
- **PRECHECK_AGENTS**: `tdd-guide` (测试用例设计 + QWidget 测试模式)
- **IMPLEMENTATION_AGENT**: `tdd-guide` (测试文件写入) + 主会话 (QApplication fixture 验证)
- **POST_REVIEW_AGENTS**: `code-reviewer` + `python-reviewer`
- **IMPLEMENT**: 4 tests using PreprocessWorkspace instance:
  1. `test_build_enabled_with_normal_images` — 5 assets, 0 large → isEnabled() == True
  2. `test_build_disabled_with_no_assets` — 0 assets → isEnabled() == False
  3. `test_build_enabled_with_large_images` — 1 large + 4 normal → isEnabled() == True
  4. `test_normal_mode_label_shown` — 0 large, 5 total → label contains "正常图片"
- **MIRROR**: `tests/views/platform/test_data_workspace_phase2.py`
- **IMPORTS**: `PreprocessWorkspace`, `pytest`
- **GOTCHA**: PreprocessWorkspace is a QWidget — tests need QApplication for signal/slot behavior
- **VALIDATE**: All 4 tests pass

### Task 2: Wire TaskConfigurator to CONFIG page
- **ACTION**: Add `_create_config_workspace()` method + CONFIG case in `_load_page()`
- **PRECHECK_AGENTS**: `architect` (页面栈接线 + TaskSpec 持久化设计) + `security-reviewer` (项目路径传递给 TaskConfigurator)
- **IMPLEMENTATION_AGENT**: 主会话 — 修改 `workbench_window.py`
- **POST_REVIEW_AGENTS**: `code-reviewer` + `python-reviewer` + `security-reviewer`
- **IMPLEMENT**:
  1. In `_load_page()`: add `elif step == PipelineStep.CONFIG: widget = self._create_config_workspace()`
  2. Create method:
     ```python
     def _create_config_workspace(self):
         from anylabeling.views.platform.task_configurator import TaskConfigurator
         configurator = TaskConfigurator()
         if self._project_path:
             configurator.set_project_context(self._project_path)
         configurator.task_configured.connect(self._on_task_configured)
         configurator.back_requested.connect(
             lambda: self._navigate_to(PipelineStep.PROJECT))
         configurator.next_requested.connect(
             lambda: self._navigate_to(PipelineStep.LABEL))
         self._config_workspace = configurator
         return configurator
     ```
  3. Add `_on_task_configured(self, task_spec)` handler — save via ProjectFileStore, set `self._pending_task_specs = [task_spec]`
  4. In `set_project()`: replace CONFIG page with `self._replace_page(PipelineStep.CONFIG, self._config_workspace)` after task specs loaded
- **MIRROR**: `_create_train_workspace()` at `workbench_window.py:282-292`; `_replace_page()` at `workbench_window.py:355-367`
- **IMPORTS**: `TaskConfigurator` via local import (avoid top-level import for lazy loading)
- **GOTCHA**: `set_project_context()` needs `self._project_path` — only call if project is already loaded. The `if self._project_path:` guard handles unopened-project case.
- **VALIDATE**: `python -m pytest tests/platform/views/test_task_configurator.py -v`

### Task 3: Add TaskConfigurator dirty tracking
- **ACTION**: Add `is_modified` property and dirty flag
- **PRECHECK_AGENTS**: `architect` (dirty-state 模式 — UI-local vs persisted compare) + `tdd-guide` (新功能，测试先于实现)
- **IMPLEMENTATION_AGENT**: 主会话 — 修改 `task_configurator.py`
- **POST_REVIEW_AGENTS**: `code-reviewer` + `python-reviewer`
- **IMPLEMENT**:
  1. `self._dirty = False` in `__init__`
  2. `self._dirty = True` in `_on_add_label`, `_on_delete_label`, `_on_task_changed`
  3. `self._dirty = False` in `_on_next` after task_configured emit
  4. Add `@property is_modified(self) -> bool: return self._dirty`
- **MIRROR**: label_workspace.py documentChanged pattern
- **IMPORTS**: None
- **GOTCHA**: Dirty state is UI-local only — no comparison with persisted TaskSpec. Full dirty-vs-saved comparison deferred to Phase 2.
- **VALIDATE**: `python -m pytest tests/platform/views/test_task_configurator.py -v`

### Task 4: Add TaskConfigurator WorkSpace-mode tests
- **ACTION**: 4 new tests in existing test file
- **PRECHECK_AGENTS**: `tdd-guide` (信号测试模式 + QApplication fixture)
- **IMPLEMENTATION_AGENT**: `tdd-guide` (测试文件写入) + 主会话 (最终审查)
- **POST_REVIEW_AGENTS**: `code-reviewer` + `python-reviewer`
- **IMPLEMENT**:
  1. `test_emit_task_configured` — set family + add label, click next → verify signal with TaskSpec
  2. `test_emit_back_requested` — click back → verify signal
  3. `test_dirty_on_edit` — add label → is_modified == True
  4. `test_dirty_clear_after_next` — add label, click next → is_modified == False
- **MIRROR**: 现有 `tests/platform/views/test_task_configurator.py`
- **IMPORTS**: `TaskSpec`, `LabelClass`
- **GOTCHA**: Tests require QApplication instance. Use `@pytest.fixture(scope="module")` for QApplication setup.
- **VALIDATE**: 4 new tests pass

### Task 5: Add E2E parameter passthrough test
- **ACTION**: New test in test_fixtures.py verifying UI config → build output
- **PRECHECK_AGENTS**: `tdd-guide` (E2E 测试设计) + `security-reviewer` (构建产物写入本地文件系统)
- **IMPLEMENTATION_AGENT**: `tdd-guide` (测试文件写入) + 主会话 (E2E fixture 验证)
- **POST_REVIEW_AGENTS**: `code-reviewer` + `python-reviewer` + `security-reviewer`
- **IMPLEMENT**:
  1. Create 5 synthetic images via existing `_make_synthetic_image` helper
  2. Create PreprocessConfig(tile_width=512, tile_height=512, train_ratio=0.6, val_ratio=0.3, test_ratio=0.1)
  3. Call `DatasetBuildService.build()` with matching params
  4. Read build.json from output → verify tile_plan values match
  5. Read split_manifest.json → verify split counts match ratios (±1 tolerance)
- **MIRROR**: `tests/e2e/platform/test_fixtures.py` existing E2E pattern
- **IMPORTS**: `PreprocessConfig`, `DatasetBuildService`, `TaskSpec`, `LabelClass`, `Asset`, `AnnotationDocument`, `FileImageSource`
- **GOTCHA**: Need to create image_sources dict for non-tiling builds. Create `FileImageSource(str(img_path))` for each asset.
- **VALIDATE**: Test passes

---

## Testing Strategy

| Test | Input | Expected |
|---|---|---|
| Build enabled normal images | 5 assets, 0 large | isEnabled() == True |
| Build disabled no assets | 0 assets | isEnabled() == False |
| Normal mode label | 0 large, 5 total | label contains "正常图片" |
| TaskConfigurator task_configured | set labels, click next | signal emitted |
| TaskConfigurator dirty flag | add label | is_modified == True |
| Split ratios in manifest | (0.6, 0.3, 0.1) | split_manifest.json matches |

---

## Validation Commands

```bash
# PreprocessWorkspace tests (4 new tests)
python -m pytest tests/platform/views/test_preprocess_workspace.py -v

# TaskConfigurator tests
python -m pytest tests/platform/views/test_task_configurator.py -v

# E2E parameter passthrough
python -m pytest tests/e2e/platform/test_fixtures.py -v -k "passthrough"

# Full regression
python -m pytest tests/ -x -m "not slow" -k "not test_format_metric"
```

---

## Acceptance Criteria
- [ ] Build 按钮在有资产时即启用（无需大图）
- [ ] 无大图时显示 "正常图片模式"
- [ ] CONFIG 页面显示真实 TaskConfigurator（非占位文本）
- [ ] 可配置任务类型和标签 → 保存 → 导航到 LABEL
- [ ] TaskSpec 保存到项目存储
- [ ] 构建参数从 UI 到 build.json 完整传递（E2E 测试验证）
- [ ] 所有已有测试无回归

## Notes
- `_import_label_btn` 保持禁用（Phase 0 审计标记）
- 构建子进程管理不变（workbench_window._on_preprocess_build_requested）
- TaskSpec 持久化：先检查 `ProjectFileStore` 是否已有 save 方法；若无则新增 `save_task_spec(project_path, task_spec)`
