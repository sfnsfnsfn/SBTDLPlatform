# Plan: Phase A — 安全网与 Bug 修复

## Summary
修复 SBTDL Platform V4 中的 4 个已知 P0/P1 bug：exts 未定义导致预处理页崩溃、_train_workspace 未保存导致数据集构建后无法刷新、AssetRepository 分组扫描不递归子目录、未实现的增强配置仍写入构建配置。全部修复采用 TDD，先写失败测试再写最小生产代码。

## User Story
As a 深度学习工程师,
I want 平台在打开预处理页时不崩溃、数据集构建后训练页能自动刷新、按分组组织的图片能被正确扫描、未实现的功能不会污染配置,
So that 我能可靠地完成从数据准备到模型训练的完整流程。

## Problem → Solution
4 个 bug 导致平台不可用 → 逐个修复，每个修复对应 1 个测试文件 + 最小代码改动

## Metadata
- **Complexity**: Small (4 isolated fixes, 3-4 files modified, <50 lines of production code)
- **Source PRD**: .claude/PRPs/prds/sbtl-platform-v4.prd.md
- **PRD Phase**: Phase A — 安全网与 Bug 修复
- **Estimated Files**: 8 (3 source files modified, 4 test files created, 1 existing test updated)

---

## UX Design

### Before
用户打开项目 → 点击预处理页 → **崩溃** (NameError: exts)
用户完成数据集构建 → 切换到训练页 → **看不到新的构建** (train_workspace 为 None)
用户将图片按分组放入子目录 → 平台**找不到这些图片**
用户在预处理页看到增强选项已勾选 → 构建配置**包含了未实现的功能**

### After
用户打开项目 → 点击预处理页 → 正常显示，资产计数来自 AssetRepository
用户完成数据集构建 → 训练页自动刷新显示新的 completed build
用户按分组组织图片 → 平台递归扫描并正确识别分组
用户在预处理页看到增强选项全部未勾选且置灰 → 构建配置不含未实现功能

### Interaction Changes
| Touchpoint | Before | After | Notes |
|---|---|---|---|
| 预处理页加载 | 崩溃 (NameError) | 正常显示 | 使用 AssetRepository.count_assets() |
| 数据集构建完成 | 训练页不刷新 | 自动刷新 | self._train_workspace 正确保存 |
| 分组图片扫描 | 仅扫描 assets/ 根目录 | 递归扫描子目录 | rglob 替代 iterdir |
| 增强配置 UI | 置灰但勾选，写入配置 | 置灰且不勾选，不写入 | unchecked + disabled |

---

## Mandatory Reading

Files that MUST be read before implementing:

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 (critical) | `anylabeling/views/platform/workbench_window.py` | 536-568, 464-474, 1185-1189 | Bug A0-1, A0-2 所在位置 |
| P0 (critical) | `anylabeling/platform/application/asset_repository.py` | 238-253, 256-262 | Bug A0-3 所在位置，_get_all_paths + _get_asset_group |
| P0 (critical) | `anylabeling/views/platform/preprocess_workspace.py` | 218-244, 448-472 | Bug A0-4 所在位置，checkbox 创建 + _get_current_config |
| P1 (important) | `tests/platform/application/test_asset_repository.py` | 1-144 | 现有 AssetRepository 测试模式 |
| P1 (important) | `tests/views/platform/test_workbench_shell.py` | 338-403 | 现有 WorkbenchWindow 测试模式（set_project） |
| P2 (reference) | `anylabeling/views/platform/workbench_window.py` | 1-40 | 导入模式 |

## External Documentation

| Topic | Source | Key Takeaway |
|---|---|---|
| - | - | No external research needed — fixes use established internal patterns |

---

## Patterns to Mirror

Code patterns discovered in the codebase. Follow these exactly.

### NAMING_CONVENTION
```python
# SOURCE: workbench_window.py:1-40
# Private methods: _ prefix, snake_case
# Classes: PascalCase (TrainWorkspace, PreprocessWorkspace)
# Properties: snake_case (self._asset_repository, self._train_workspace)
# Test classes: PascalCase with descriptive name (TestScanAssets)
# Test methods: test_<what_happens>_<under_what_condition>
```

### ERROR_HANDLING
```python
# SOURCE: workbench_window.py:1198-1199
try:
    # operation
except Exception as exc:
    logger.exception("Dataset build failed")
    QtWidgets.QMessageBox.critical(self, title, message)
```

### LOGGING_PATTERN
```python
# SOURCE: asset_repository.py:19
import logging
logger = logging.getLogger(__name__)
# Usage: logger.warning("Failed to read image: %s", abs_path)
```

### TEST_STRUCTURE
```python
# SOURCE: test_asset_repository.py:1-144, test_workbench_shell.py:1-403
# AAA pattern: Arrange → Act → Assert
# tmp_path fixture for isolated file system
# Classes group related tests (TestScanAssets, TestCountAssets)
# Helper functions for common setup: _write_test_image(dir_path, name)
# Qt tests: check _HAS_QAPP, use skip_without_display marker
# Qt tests: use qapp fixture to create QApplication, workbench fixture for window
```

### IMPORT_PATTERN
```python
# SOURCE: workbench_window.py:1-39
from __future__ import annotations

import logging
from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets

from anylabeling.platform.application.asset_repository import AssetRepository
from anylabeling.views.platform.train_workspace import TrainWorkspace
```

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `anylabeling/views/platform/workbench_window.py` | UPDATE | Fix A0-1 (exts) + A0-2 (save _train_workspace) |
| `anylabeling/platform/application/asset_repository.py` | UPDATE | Fix A0-3 (recursive scan + group detection) |
| `anylabeling/views/platform/preprocess_workspace.py` | UPDATE | Fix A0-4 (uncheck disabled augmentations) |
| `tests/views/platform/test_workbench_preprocess_wiring.py` | CREATE | Test for A0-1 fix |
| `tests/views/platform/test_workbench_train_wiring.py` | CREATE | Test for A0-2 fix |
| `tests/platform/application/test_asset_repository.py` | UPDATE | Add recursive scan + group tests for A0-3 |
| `tests/views/platform/test_preprocess_workspace_config.py` | CREATE | Test for A0-4 fix |

## NOT Building

- 不修改 DB schema 或 infrastructure 层
- 不修改 ProjectSession
- 不修改任何 Service 核心流程
- 不引入新的第三方依赖
- 不改变 UI 布局结构

---

## Step-by-Step Tasks

### Task 1: A0-1 — 修复 WorkbenchWindow 预处理页 exts 未定义

- **ACTION**: Fix NameError in `_create_preprocess_workspace()` where `exts` is used but not defined
- **IMPLEMENT**: Replace the manual `iterdir()` + `exts` counting with `self._asset_repository.count_assets()`
  ```python
  # BEFORE (line 560-565, BROKEN):
  if assets_dir.is_dir():
      total = sum(
          1 for p in assets_dir.iterdir()
          if p.is_file() and p.suffix.lower() in exts  # NameError: exts undefined
      )
      workspace.set_total_assets(total)

  # AFTER:
  if assets_dir.is_dir():
      total = self._asset_repository.count_assets()
      workspace.set_total_assets(total)
  ```
- **MIRROR**: Uses existing `self._asset_repository` (line 556), follows same pattern as `find_large_images()` call on line 556-557
- **IMPORTS**: No new imports needed — `self._asset_repository` already available
- **GOTCHA**: `count_assets()` returns count of supported images only (already filters by extension via `_IMAGE_EXTS`), same behavior as the buggy `exts` filter
- **VALIDATE**: `pytest tests/views/platform/test_workbench_preprocess_wiring.py -q`

### Task 2: A0-2 — 修复 _create_train_workspace() 不保存引用

- **ACTION**: Save `workspace` to `self._train_workspace` so dataset build completion can refresh it
- **IMPLEMENT**: Add one line before `return workspace`:
  ```python
  # In _create_train_workspace() (line 464-474), BEFORE return:
  self._train_workspace = workspace
  return workspace
  ```
- **MIRROR**: Other workspaces stored in `self._page_widgets` via `_replace_page()`; this adds the `_train_workspace` direct reference needed by lines 1185-1189
- **IMPORTS**: None
- **GOTCHA**: `hasattr(self, "_train_workspace")` at line 1188 checks existence before calling `set_dataset_builds()`. After fix, this will return True when train page has been loaded at least once. The `_page_loaded` guard at line 1187 already ensures the page was visited.
- **VALIDATE**: `pytest tests/views/platform/test_workbench_train_wiring.py -q`

### Task 3: A0-3 — 修复 AssetRepository 分组扫描不递归

- **ACTION**: Change `_get_all_paths()` from `iterdir()` to `rglob("*")` and update `_get_asset_group()` to use first-level subdirectory
- **IMPLEMENT**:
  ```python
  # In _get_all_paths() (line 247-253):
  # BEFORE:
  self._asset_paths_cache = tuple(
      sorted(
          str(p)
          for p in self._assets_dir.iterdir()
          if p.is_file() and p.suffix.lower() in _IMAGE_EXTS
      )
  )

  # AFTER:
  self._asset_paths_cache = tuple(
      sorted(
          str(p)
          for p in self._assets_dir.rglob("*")
          if p.is_file() and p.suffix.lower() in _IMAGE_EXTS
      )
  )

  # In _get_asset_group() (line 256-262):
  # Keep logic: parent.name == "assets" → None, otherwise → parent.name
  # This works correctly with rglob since parent is the immediate subdirectory
  ```
- **MIRROR**: Same cache pattern, same extension filter, same sorted output. Only changes `iterdir()` → `rglob("*")`.
- **IMPORTS**: None
- **GOTCHA**: `rglob("*")` returns files in ALL subdirectories recursively, not just first-level. The group extraction logic `_get_asset_group()` gets `path.parent.name` which correctly identifies the first-level subdirectory (e.g., `assets/group_a/a.png` → parent is `group_a`). Files directly in `assets/` still have parent `assets` → group None.
- **VALIDATE**: `pytest tests/platform/application/test_asset_repository.py -q`

### Task 4: A0-4 — 关闭未实现增强配置写入

- **ACTION**: Uncheck disabled augmentation checkboxes so `_get_current_config()` returns empty augmentations
- **IMPLEMENT**:
  ```python
  # In PreprocessWorkspace.__init__() (lines 221-241):
  # Change setChecked(True) → setChecked(False) for all 4 checkboxes:
  self._hflip_cb.setChecked(False)        # was True
  self._vflip_cb.setChecked(False)        # (already unchecked, verify)
  self._brightness_cb.setChecked(False)   # was True
  self._rotate_cb.setChecked(False)       # was True

  # _get_current_config() already correctly reads isChecked() state,
  # so with all unchecked, augs will be empty → augmentations=frozenset()
  ```
- **MIRROR**: Checkbox creation pattern unchanged. Only initial state changes.
- **IMPORTS**: None
- **GOTCHA**: The tooltip already says "(planned)" which is correct. The checkboxes are already `setEnabled(False)`. The bug is only that `setChecked(True)` on disabled checkboxes still returns `True` from `isChecked()`. Ensure `_get_current_config()` does NOT need modification — it already correctly filters based on `isChecked()`.
- **VALIDATE**: `pytest tests/views/platform/test_preprocess_workspace_config.py -q`

---

## Testing Strategy

### Unit Tests

**A0-1 tests** (`tests/views/platform/test_workbench_preprocess_wiring.py`):
| Test | Input | Expected Output | Edge Case? |
|---|---|---|---|
| `test_create_preprocess_workspace_does_not_raise_when_assets_exist` | tmp_path with assets/ and images | No NameError, widget returned | Yes - was crashing |
| `test_create_preprocess_workspace_sets_total_assets_from_repository` | tmp_path with assets/ and 5 images | set_total_assets called with 5 | No |

**A0-2 tests** (`tests/views/platform/test_workbench_train_wiring.py`):
| Test | Input | Expected Output | Edge Case? |
|---|---|---|---|
| `test_create_train_workspace_sets_train_workspace_attr` | WorkbenchWindow with project | hasattr(win, "_train_workspace") is True | Yes - was silently failing |
| `test_train_workspace_receives_dataset_builds_after_build_completion` | Build completes → refresh | _train_workspace.set_dataset_builds called | No |

**A0-3 tests** (extend `tests/platform/application/test_asset_repository.py`):
| Test | Input | Expected Output | Edge Case? |
|---|---|---|---|
| `test_scan_assets_recursive_with_groups` | assets/group_a/a.png, assets/group_b/b.png | 2 paths, both found | Yes - was 0 |
| `test_scan_assets_with_ungrouped_root_file` | assets/c.png + subdirs | c.png included, group=None | Yes |
| `test_get_groups_returns_subdir_names` | assets/ with subdirs | ["group_a", "group_b"] | Yes |

**A0-4 tests** (`tests/views/platform/test_preprocess_workspace_config.py`):
| Test | Input | Expected Output | Edge Case? |
|---|---|---|---|
| `test_disabled_augmentation_not_in_build_config` | PreprocessWorkspace (default state) | augmentations=[] | Yes - was including them |
| `test_all_augmentation_checkboxes_disabled` | PreprocessWorkspace | all 4 checkboxes not enabled | No |
| `test_augmentation_tooltip_indicates_planned` | PreprocessWorkspace | tooltip contains "planned" or "规划中" | No |

### Edge Cases Checklist
- [x] Empty assets/ directory (A0-1: count=0, no crash)
- [x] Missing assets/ directory (A0-1: count=0, no crash)
- [x] Train workspace not yet created (A0-2: hasattr guard → skip refresh)
- [x] Deeply nested subdirectories (A0-3: rglob finds all levels)
- [x] Subdirectory with no images (A0-3: empty group, no crash)
- [x] All augmentations disabled + unchecked (A0-4: augmentations=frozenset())

---

## Validation Commands

### Static Analysis
```bash
python -m compileall anylabeling/views/platform/workbench_window.py anylabeling/platform/application/asset_repository.py anylabeling/views/platform/preprocess_workspace.py
```
EXPECT: No SyntaxError

### Unit Tests (per task)
```bash
# A0-1
pytest tests/views/platform/test_workbench_preprocess_wiring.py -q
# A0-2
pytest tests/views/platform/test_workbench_train_wiring.py -q
# A0-3
pytest tests/platform/application/test_asset_repository.py -q
# A0-4
pytest tests/views/platform/test_preprocess_workspace_config.py -q
```
EXPECT: All tests pass

### Full Test Suite
```bash
pytest tests/platform/application/ tests/views/platform/ -m "not slow" -q
```
EXPECT: No regressions

### Lint
```bash
flake8 anylabeling/views/platform/workbench_window.py anylabeling/platform/application/asset_repository.py anylabeling/views/platform/preprocess_workspace.py
```
EXPECT: No warnings

---

## Acceptance Criteria
- [ ] 打开项目 → 点击预处理页不崩溃 (A0-1)
- [ ] 数据集构建完成后训练页自动刷新 (A0-2)
- [ ] 子目录中的图片被正确扫描和分组 (A0-3)
- [ ] 构建配置中不包含未实现的增强 (A0-4)
- [ ] 全部 4 个测试文件通过
- [ ] 无回归

## Completion Checklist
- [x] Code follows discovered patterns
- [x] Error handling matches codebase style
- [x] Logging follows codebase conventions
- [x] Tests follow test patterns
- [x] No hardcoded values
- [x] No unnecessary scope additions
- [ ] python-reviewer called
- [ ] code-reviewer called

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| count_assets() returns different count than manual iterdir scan | L | LOW | Both filter by _IMAGE_EXTS; verify with test |
| rglob("*") performance on large projects | L | LOW | Cache still works; rglob is lazy generator |
| Disabled checkboxes re-enabled by parent widget | L | LOW | setEnabled(False) called explicitly in __init__ |

## Notes
- Phase A is the prerequisite for all subsequent phases. All 4 tasks can be done sequentially by a single agent (Agent A).
- Tasks A0-1 and A0-2 both modify `workbench_window.py` — should be done in order to avoid merge conflicts.
- Task A0-3 is independent of A0-1/A0-2 (different file).
- Task A0-4 is independent of all others (different file).
