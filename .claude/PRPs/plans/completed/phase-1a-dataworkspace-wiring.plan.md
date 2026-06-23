# Plan: Phase 1a — DataWorkspace 接入 + AssetRepository + InferWorkspace 清理

## Summary
将 DataWorkspace 接入 IMPORT 页面栈（替换占位符），移除死代码 InferWorkspace 导入，创建最小化 AssetRepository 统一 `_scan_assets()` 逻辑，使 DataWorkspace 成为所有数据准备页面的统一资产来源。

## User Story
As a 算法工程师, I want 打开项目后从导航点击"导入"即看到真实资产列表和统计，而非占位文本, So that 我能确认项目数据已正确加载，并知晓下一步是"前往预处理"。

## Problem → Solution
IMPORT 页是占位符（DataWorkspace 已实现但 `_load_page()` 未创建）→ `_load_page()` 和 `set_project()` 中接入 DataWorkspace。资产扫描分散在 workbench_window 私有方法中 → 提取为 AssetRepository 服务。InferWorkspace 导入后从未使用 → 移除。

## Metadata
- **Complexity**: Medium (6–8 files, ~250 lines new)
- **Source PRD Phase**: 阶段 1 — 真实闭环 (子阶段 1a)
- **Depends On**: Phase 0 (complete)
- **Estimated Files**: 6 modified, 2 new

---

## UX Design

### Before
```
IMPORT 页面（PipelineStep.IMPORT = 1）：
┌──────────────────────────────┐
│ 缺少：DataWorkspace 已实现   │
│ 但未接入页面栈               │
└──────────────────────────────┘
```

### After
```
IMPORT 页面（PipelineStep.IMPORT = 1）：
┌ DataWorkspace ───────────────────────────────────────────┐
│ 资源列表（左 2/3）              统计（右 1/3）            │
│ ┌─────────────────────┐  资源：10                        │
│ │ img_0001.jpg        │  类别分布：                       │
│ │ img_0002.jpg        │    defect: 15                     │
│ │ ...                 │    scratch: 8                     │
│ │                     │  覆盖率：80.0% (8/10)              │
│ └─────────────────────┘                                  │
│                                     [前往预处理 →]        │
└──────────────────────────────────────────────────────────┘
```

### Interaction Changes
| Touchpoint | Before | After |
|---|---|---|
| IMPORT nav 内容 | 占位文本页 | 真实 DataWorkspace 小部件 |
| "前往预处理 →" 按钮 | 不可见（占位页遮挡） | 可见，点击 → `navigate_to_step.emit(PREPROCESS)` → workbench_window 切换到 PREPROCESS |
| InferWorkspace 导入 | L20: `from ...infer_workspace import InferWorkspace` | 已删除 |
| 关闭窗口 | 无特殊处理 | 无特殊处理（DataWorkspace 无后台任务） |
| 错误状态 | 资产目录缺失 → `Assets: 0` | 同左（DataWorkspace 已有） |

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `views/platform/workbench_window.py` | 20, 166–178, 257–286, 355–367, 1116–1125 | 死代码导入 + DataWorkspace 创建 + _load_page + _replace_page + _scan_assets |
| P0 | `views/platform/data_workspace.py` | 1–159 | 已实现的工作区 — 完整 API 和信号 |
| P0 | `platform/application/__init__.py` | 1–7 | 导出模式 — 显式 `__all__` |
| P1 | `platform/application/dataset_build_service.py` | 81–93 | 服务类构造函数模式 |

---

## Patterns to Mirror

### CRITICAL: Page replacement in QStackedWidget
// SOURCE: views/platform/workbench_window.py:355-367
```python
def _replace_page(self, step: PipelineStep, widget):
    idx = step.value
    old = self._pages.widget(idx)
    if old is not None and old is not widget:
        self._pages.removeWidget(old)
        old.deleteLater()
    self._pages.insertWidget(idx, widget)
    self._page_widgets[idx] = widget
    self._page_loaded[idx] = True
```

### CRITICAL: DataWorkspace creation + signal wiring in set_project()
// SOURCE: views/platform/workbench_window.py:167-178
```python
self._data_workspace = DataWorkspace()
asset_paths = self._scan_assets(project_path)
self._data_workspace.set_assets(asset_paths)
self._data_workspace.navigate_to_step.connect(
    lambda step: self._navigate_to(step)
)
```

### CRITICAL: Service class constructor pattern
// SOURCE: platform/application/dataset_build_service.py:81-93
```python
class DatasetBuildService:
    def __init__(self, project_root: str | Path) -> None:
        self._project_root = Path(project_root)
```

### Asset scanning logic to extract
// SOURCE: views/platform/workbench_window.py:1116-1125
```python
@staticmethod
def _scan_assets(project_path: str) -> list[str]:
    assets_dir = Path(project_path) / "assets"
    if not assets_dir.exists():
        return []
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
    return sorted([
        str(p) for p in assets_dir.iterdir()
        if p.is_file() and p.suffix.lower() in exts
    ])
```

### Package export pattern
// SOURCE: platform/application/__init__.py:1-7
```python
from anylabeling.platform.application.job_service import JobService
__all__ = ["JobService", ...]
```

### TEST_STRUCTURE — tmp_path + synthetic images
// SOURCE: tests/platform/application/test_dataset_build_service.py
"""
Uses tmp_path fixture; synthetic images via numpy + cv2.imwrite; AAA pattern.
"""

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `views/platform/workbench_window.py` | UPDATE | Remove InferWorkspace import; wire DataWorkspace to IMPORT; delegate _scan_assets to AssetRepository |
| `platform/application/asset_repository.py` | **CREATE** | Unified asset scanning service (5 methods) |
| `platform/application/__init__.py` | UPDATE | Export AssetRepository |
| `tests/platform/application/test_asset_repository.py` | **CREATE** | 8 unit tests for AssetRepository |
| `tests/platform/views/test_data_workspace_phase2.py` | UPDATE | Add test for IMPORT page wiring |
| `tests/views/platform/test_workbench_shell.py` | UPDATE | Add/update test for IMPORT content after project load |

## NOT Building (1a scope)

- AssetRepository with paging/manifest/SQLite/indexing (Phase 3–4)
- AssetRepository integration to Preprocess/Train/Evaluate pages (Phase 1b)
- CONFIG page wiring / TaskConfigurator refactor (Phase 1b)
- 5-domain navigation shell (Phase 2)
- ProjectSession / WorkflowState (Phase 2)
- Normal-image dataset build fix (Phase 1b)
- Evaluation metrics fix (Phase 1c)
- ONNX export self-test (Phase 1c)
- Any UI thread blocking work (Rule 16)
- Any QWidget manipulation from background threads (Rule 17)

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
| `architect` | 架构审查 | T0, T3 | AssetRepository API 契约 + IMPORT 页面接线验证 |
| `tdd-guide` | 测试驱动 | T0, T1 | 新服务类先写测试，再实现 |
| `security-reviewer` | 安全审查 | T0, T3 | 文件系统扫描 + 项目路径处理 |
| `code-reviewer` | 代码审查 | All | 每 Task 完成后强制审查 |
| `python-reviewer` | Python 审查 | All | PEP 8 合规 + 惯用法检查 |

### EXECUTION_MODE

**Sequential** — Task 串行执行：T0 → T1 → T2 → T3 → T4。

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

## Step-by-Step Tasks

### Task 0: Create AssetRepository service
- **ACTION**: Create `platform/application/asset_repository.py` with 5 public methods
- **PRECHECK_AGENTS**: `architect` (新服务 API 契约) + `tdd-guide` (新功能，测试先于实现) + `security-reviewer` (文件系统扫描、cv2 外部依赖)
- **IMPLEMENTATION_AGENT**: 主会话 — 创建 `platform/application/asset_repository.py`
- **POST_REVIEW_AGENTS**: `code-reviewer` + `python-reviewer` + `security-reviewer`
- **IMPLEMENT**:
  ```python
  class AssetRepository:
      def __init__(self, project_root: str | Path) -> None
      def scan_assets(self) -> list[str]           # all image paths, sorted
      def count_assets(self) -> int                 # len(scan_assets())
      def count_by_extension(self) -> dict[str, int]
      def find_large_images(self, min_dim=2000) -> list[str]
      def list_subdirs(self) -> list[str]           # immediate subdirs in assets/
  ```
  1. `__init__`: `self._project_root = Path(project_root)`; `self._assets_dir = self._project_root / "assets"`
  2. `scan_assets`: iterate `self._assets_dir.iterdir()`, filter by `_IMAGE_EXTS`, return sorted str paths. If dir missing → `[]`.
  3. `count_assets`: `sum(1 for _ in ...)` over filtered files
  4. `count_by_extension`: `collections.Counter(p.suffix.lower() for p in ...)`
  5. `find_large_images`: `cv2.imread(str(p))`, check `max(h,w) > min_dim`. Wrap in `try: import cv2 except ImportError: return []`
  6. `list_subdirs`: `[d.name for d in self._assets_dir.iterdir() if d.is_dir()]`
- **MIRROR**: `DatasetBuildService.__init__` at `dataset_build_service.py:81-93`
- **IMPORTS**: `from pathlib import Path`; `from collections import Counter`; try/except for cv2
- **GOTCHA**:
  - cv2 may not be available on import — `find_large_images` must catch ImportError at call time
  - Do NOT recursively walk subdirs in `scan_assets()` — only immediate files
  - Extension filter must match existing set: `.jpg, .jpeg, .png, .bmp, .tif, .tiff`
  - `_assets_dir` may not exist — all methods must handle gracefully (return empty)
- **VALIDATE**: `python -m pytest tests/platform/application/test_asset_repository.py -v`

### Task 1: Write AssetRepository unit tests (8 tests)
- **ACTION**: Create `tests/platform/application/test_asset_repository.py`
- **PRECHECK_AGENTS**: `tdd-guide` (测试用例设计 + AAA 结构验证)
- **IMPLEMENTATION_AGENT**: `tdd-guide` (测试文件写入) + 主会话 (最终审查合并)
- **POST_REVIEW_AGENTS**: `code-reviewer` + `python-reviewer`
- **IMPLEMENT**: All tests use `tmp_path`. Create synthetic images via `np.random.default_rng(42).integers(0,255,(h,w,3)).astype(np.uint8)` + `cv2.imwrite`.
  1. `test_scan_assets_returns_images_only` — 3 .jpg + 2 .png + 1 .txt → returns 5 image paths, no .txt
  2. `test_scan_assets_empty_dir` — assets dir exists, no files → returns []
  3. `test_scan_assets_no_assets_dir` — no assets/ dir at all → returns []
  4. `test_count_assets` — 5 images → returns 5
  5. `test_count_by_extension` — 3 jpg + 2 png → `{"jpg": 3, "png": 2}`
  6. `test_find_large_images_detects` — 1×3000×3000 + 3×640×480 → returns 1 path
  7. `test_find_large_images_none` — all 640×480 → returns []
  8. `test_list_subdirs` — 3 dirs + 2 files → returns 3 dir names
- **MIRROR**: `tests/platform/application/test_dataset_build_service.py`
- **IMPORTS**: `pytest`, `numpy as np`, `cv2`, `AssetRepository`
- **GOTCHA**: Large image test (3000×3000) is 9M pixels — acceptable for one test. Use `min_dim=2000` to match default.
- **VALIDATE**: All 8 tests pass

### Task 2: Remove dead InferWorkspace import
- **ACTION**: Delete line 20 from `workbench_window.py`
- **PRECHECK_AGENTS**: (none — 单行删除，无需架构或安全审查)
- **IMPLEMENTATION_AGENT**: 主会话 — 从 `workbench_window.py` 删除死导入
- **POST_REVIEW_AGENTS**: `code-reviewer` + `python-reviewer` (验证无残留引用)
- **IMPLEMENT**: Delete `from anylabeling.views.platform.infer_workspace import InferWorkspace`
- **MIRROR**: N/A
- **IMPORTS**: None
- **GOTCHA**: The file `infer_workspace.py` itself is preserved (has `# STATUS:` from Phase 0). Check tests that may import InferWorkspace from workbench_window.
- **VALIDATE**: `python -m pytest tests/views/platform/test_workbench_shell.py -v`

### Task 3: Wire DataWorkspace to IMPORT page
- **ACTION**: Modify `_load_page()` and `set_project()` in workbench_window.py
- **PRECHECK_AGENTS**: `architect` (页面栈接线验证 + set_project 生命周期) + `security-reviewer` (项目路径传递给 UI 组件)
- **IMPLEMENTATION_AGENT**: 主会话 — 修改 `workbench_window.py`
- **POST_REVIEW_AGENTS**: `code-reviewer` + `python-reviewer` + `security-reviewer`
- **IMPLEMENT**:
  1. In `_load_page()` IMPORT case (line 264), replace placeholder creation with:
     ```python
     if step == PipelineStep.IMPORT:
         if hasattr(self, "_data_workspace") and self._data_workspace is not None:
             widget = self._data_workspace
     ```
     Falls through to None if no project → IMPORT shows placeholder (correct).
  2. In `set_project()`, after DataWorkspace population (after line 178):
     ```python
     self._replace_page(PipelineStep.IMPORT, self._data_workspace)
     ```
     Mirrors LabelWorkspace replacement at line 185.
- **MIRROR**: `_replace_page()` at `workbench_window.py:355-367`; DataWorkspace creation at `workbench_window.py:167-178`
- **IMPORTS**: None (DataWorkspace already imported at line 16)
- **GOTCHA**:
  - `set_project()` runs before `_load_page()` — `self._data_workspace` must be set before the hasattr check
  - When user closes project and opens another, `set_project()` creates new DataWorkspace — must call `_replace_page` again
  - `_page_loaded` dict handles the lazy-load guard correctly (page is marked loaded after _replace_page)
- **VALIDATE**: `python -m pytest tests/views/platform/test_data_workspace_phase2.py -v`

### Task 4: Export AssetRepository from application package
- **ACTION**: Update `platform/application/__init__.py`
- **PRECHECK_AGENTS**: (none — 包导出注册，无架构或安全风险)
- **IMPLEMENTATION_AGENT**: 主会话 — 修改 `platform/application/__init__.py`
- **POST_REVIEW_AGENTS**: `code-reviewer` + `python-reviewer` (验证无循环导入)
- **IMPLEMENT**: Add `from anylabeling.platform.application.asset_repository import AssetRepository` and add `"AssetRepository"` to `__all__`
- **MIRROR**: `platform/application/__init__.py:1-7`
- **IMPORTS**: `AssetRepository`
- **GOTCHA**: AssetRepository only depends on pathlib — no risk of circular import with other platform modules
- **VALIDATE**: `python -c "from anylabeling.platform.application import AssetRepository; print(type(AssetRepository))"`

---

## Testing Strategy

| Test | Input | Expected |
|---|---|---|
| scan_assets mixed dir | 3 JPG + 2 PNG + 1 TXT | 5 paths |
| scan_assets empty | no files | [] |
| count_by_extension | 3 JPG + 2 PNG | {"jpg": 3, "png": 2} |
| find_large_images | 1×3000² + 3×640² | 1 path |
| find_large_images none | all 640² | [] |
| list_subdirs | 3 dirs + 2 files | ["d1","d2","d3"] |
| DataWorkspace at IMPORT index | set_project + verify page content | isinstance(page, DataWorkspace) |

---

## Validation Commands

```bash
# AssetRepository tests
python -m pytest tests/platform/application/test_asset_repository.py -v
# EXPECT: 8 passed

# Import verification
python -c "from anylabeling.platform.application import AssetRepository; print('OK')"

# DataWorkspace + Workbench tests
python -m pytest tests/platform/views/test_data_workspace_phase2.py tests/views/platform/test_workbench_shell.py -v -k "not test_format_metric"

# Full regression
python -m pytest tests/ -x -m "not slow" -k "not test_format_metric"
# EXPECT: No regressions
```

## Acceptance Criteria
- [ ] IMPORT 页面显示 DataWorkspace（非占位文本）
- [ ] DataWorkspace 显示资产数量、类别分布、覆盖率
- [ ] "前往预处理 →" 按钮可见可点击，导航到 PREPROCESS 步骤
- [ ] InferWorkspace 导入已从 workbench_window.py 移除
- [ ] AssetRepository 8 个单元测试通过
- [ ] 所有已有测试无回归

## Notes
- 无后台任务（DataWorkspace 是纯展示层）
- 无取消流程（无异步操作）
- 关闭窗口无特殊处理（DataWorkspace 无需要清理的资源）
