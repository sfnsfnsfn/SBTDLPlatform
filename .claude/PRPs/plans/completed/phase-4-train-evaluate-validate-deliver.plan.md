# Plan: Phase 4 — Train, Evaluate, Validate, Deliver

**Source PRD**: `.claude/PRPs/prds/x-anylabeling-productization.prd.md`
**PRD Phase**: Phase 4 (pending, split 4a/4b)
**Complexity**: Large (~15 files, ~1800 lines)

## Summary

Phase 4 transforms the training→evaluation→export pipeline from "functional but opaque" into "understandable, reproducible, deliverable." Phase 4a adds a local model library, pre-training readiness checks, and run recovery. Phase 4b enhances evaluation reports with misclassification analysis, adds inference validation on project assets, and produces a verified ONNX deployment package with self-test.

## User Story

As an industrial vision engineer training models on 10k–50k images,
I want to know BEFORE training whether my data/config are valid, understand WHERE my model fails after evaluation, and deliver a verified ONNX package that I can deploy to production,
So that I iterate quickly, trust my evaluation results, and ship models with confidence.

## Problem → Solution

| Current State | Desired State |
|---|---|
| Training starts immediately — no data/config validation | Pre-flight checklist validates model↔data↔task alignment |
| Runs lost if app crashes during training | Run state persisted; recovery prompt on next app start |
| No model library — models scattered across run dirs | Browse/search trained models by task, metrics, date |
| Evaluation shows basic text metrics | Per-class confusion matrix, PR/AUC curves, misclass gallery |
| ONNX export not self-tested | Export runs 5–20 sample inferences, compares with PyTorch |
| No inference validation on project assets | Run model on project images side-by-side with ground truth |

## Metadata

- **Complexity**: Large
- **Source PRD**: `.claude/PRPs/prds/x-anylabeling-productization.prd.md`
- **PRD Phase**: Phase 4 (pending)
- **Depends On**: Phase 3 (complete)
- **Estimated Files**: 6 new, 9 modified

---

## Patterns to Mirror

### SERVICE_PATTERN
```python
# SOURCE: anylabeling/platform/application/import_service.py:35-53
class DatasetBuildService:
    def __init__(self, project_root: str | Path) -> None:
        self._project_root = Path(project_root)
    @property
    def project_root(self) -> Path:
        return self._project_root
```

### QWIDGET_PATTERN
```python
# SOURCE: anylabeling/views/platform/workspaces/import_workspace.py:75-103
class ImportWorkspace(QtWidgets.QWidget):
    import_completed = QtCore.pyqtSignal(ImportResult)
    def __init__(self, ...):
        super().__init__(parent)
        self._build_ui()
```

### ERROR_HANDLING
```python
# SOURCE: anylabeling/views/platform/workbench_window.py:888
try:
    result = service.do_work()
except Exception as exc:
    logger.exception("Operation failed")
```

### LOGGING_PATTERN
```python
# SOURCE: all platform files
import logging
logger = logging.getLogger(__name__)
```

### TEST_STRUCTURE
```python
# SOURCE: tests/platform/application/test_import_service.py
class TestImportConfig:
    def test_defaults(self):
        cfg = ImportConfig()
        assert cfg.deduplicate is True
```

---

## Files to Change

### Phase 4a — Model Library + Training Readiness + Run Recovery

| File | Action | Why |
|------|--------|-----|
| `anylabeling/views/platform/widgets/model_library.py` | CREATE | Browseable model gallery with search/filter |
| `anylabeling/views/platform/view_models/train_validation_vm.py` | CREATE | Pre-training validation state: data, config, hardware checks |
| `anylabeling/views/platform/widgets/train_readiness_widget.py` | CREATE | Pre-flight checklist widget showing pass/fail/warn per check |
| `anylabeling/platform/application/training_service.py` | UPDATE | Add `validate_training_readiness()`, `recover_run()` |
| `anylabeling/views/platform/train_workspace.py` | UPDATE | Integrate readiness widget, run recovery banner |
| `anylabeling/views/platform/workbench_window.py` | UPDATE | Wire model library access, run recovery on project open |

### Phase 4b — Evaluation Reports + Inference Validation + Export Package

| File | Action | Why |
|------|--------|-----|
| `anylabeling/views/platform/widgets/eval_report_widget.py` | CREATE | Rich eval: confusion matrix, PR/AUC, per-class metrics |
| `anylabeling/views/platform/widgets/misclass_gallery.py` | CREATE | Misclass thumbnail gallery: pred vs ground-truth |
| `anylabeling/views/platform/evaluate_workspace.py` | UPDATE | Integrate eval report + misclass gallery widgets |
| `anylabeling/views/platform/infer_workspace.py` | UPDATE | Add inference-on-project-assets validation mode |
| `anylabeling/views/platform/export_workspace.py` | UPDATE | Add deploy package preview + self-test + verify |
| `anylabeling/platform/application/export_service.py` | UPDATE | Add `self_test_onnx()` — sample inference comparison |
| `anylabeling/platform/domain/export_config.py` | CREATE | New: `SelfTestReport`, `ExportTarget`, `CompatibilityResult` frozen dataclasses |
| `anylabeling/views/platform/shell/app_bar.py` | UPDATE | Add "Models" navigation button (flat QPushButton, follows `_task_btn` pattern) |
| `anylabeling/views/platform/shell/navigation_bar.py` | UPDATE | Add `MODELS = 8` to `PipelineStep` enum (optional entry point) |

---

## NOT Building

- TensorRT, OpenVINO, MNN export backends (Phase 5+)
- Cloud training or remote cluster support
- New algorithm development
- Automated hyperparameter tuning
- Side-by-side model comparison UI
- Python packaging (pip install) of trained models

---

## Sub-phase 4a: Model Library + Training Readiness + Run Recovery

### Task 4a.1: Create ModelLibrary widget

- **ACTION**: CREATE `anylabeling/views/platform/widgets/model_library.py`
- **IMPLEMENT**: `ModelLibrary(QtWidgets.QWidget)` — scrollable grid of model cards. Each card: task icon, model name, best metric (mAP/F1), training date, status (training/ready/failed). Search bar + filter by task family. Click → view detail (hyperparams, all metrics, run logs). Model list built by scanning `<project_root>/runs/` via `TrainingService.read_run_record()` (reuses existing `_populate_runs()` pattern from `export_workspace.py:297`).
- **MIRROR**: `QWIDGET_PATTERN` — signals at class level, `_build_ui()`
- **IMPORTS**: `PyQt6.QtCore`, `PyQt6.QtWidgets`, `TrainingService`, `style.FONT_*`, `get_theme()`, `i18n.tr`
- **GOTCHA**: Handle empty state (no trained models). Runs without valid `run.json` shown as "unknown" with tooltip.
- **VALIDATE**: `python -c "from anylabeling.views.platform.widgets.model_library import ModelLibrary; print('OK')"`

### Task 4a.2: Create training readiness validation

- **ACTION**: CREATE `anylabeling/views/platform/view_models/train_validation_vm.py` + UPDATE `training_service.py`
- **IMPLEMENT**:
  - `TrainingService.validate_training_readiness(task_spec, dataset_build) → TrainReadinessReport`
  - Checks: assets exist (count > 0), annotations coverage >= 50%, dataset build complete, model compatible with task family, disk space >= 1GB
  - `TrainReadinessReport` frozen dataclass: `ready: bool`, `checks: list[CheckResult]`, `warnings: list[str]`
  - `CheckResult` frozen dataclass: `name: str`, `passed: bool`, `detail: str`, `blocking: bool`
  - `TrainValidationViewModel` — wraps report, exposes per-check properties
- **MIRROR**: `VIEWMODEL_PATTERN` (import_vm.py), `DOMAIN_DATACLASS` (frozen=True)
- **GOTCHA**: Annotation coverage check uses `AssetRepository.get_stats()`. Disk check uses `shutil.disk_usage()`. Non-blocking warnings must not prevent training.
- **VALIDATE**: Unit test — empty project → ready=False, 2+ failed checks.

### Task 4a.3: Create TrainReadinessWidget

- **ACTION**: CREATE `anylabeling/views/platform/widgets/train_readiness_widget.py`
- **IMPLEMENT**: Vertical checklist: green ✓ / red ✗ / yellow ⚠ per check. "Start Training" button enabled only when all blocking checks pass. Embedded in TrainWorkspace above the hyperparameter form.
- **MIRROR**: `QWIDGET_PATTERN`
- **VALIDATE**: Unit test — all pass = button enabled. One blocking fail = button disabled.

### Task 4a.4: Add run recovery

- **ACTION**: UPDATE `training_service.py` + `train_workspace.py`
- **IMPLEMENT**: `TrainingService.find_orphaned_runs()` — scan `<project_root>/runs/` for `run.json` records with `status == "running"`. TrainWorkspace: on `set_project_context()`, if orphaned run found, show ErrorBanner "发现未完成的训练运行 [恢复] [丢弃]". Recovery re-queues the job. Discard marks it as "cancelled".
- **MIRROR**: Phase 3b recovery pattern in `label_workspace.py:_check_and_prompt_recovery()`
- **GOTCHA**: Only works if `<project_root>/runs/<run_id>/run.json` exists with `"status": "running"`. Run records are written by `TrainingService.create_run_record()` via `AtomicWriter.write_json()`.
- **VALIDATE**: Create mock orphaned run → project open → recovery prompt appears.

### Task 4a.5: Wire model library into WorkbenchWindow

- **ACTION**: UPDATE `workbench_window.py`
- **IMPLEMENT**: Add ModelLibrary accessible from AppBar "Models" button or as a side panel. `model_selected` signal → navigate to Evaluate/Export with pre-selected model.
- **MIRROR**: Existing `_replace_page()` wiring for LabelWorkspace
- **VALIDATE**: Open project → access model library → trained models listed.

---

## Sub-phase 4b: Evaluation Reports + Inference Validation + Export Package

### Task 4b.1: Create EvalReportWidget

- **ACTION**: CREATE `anylabeling/views/platform/widgets/eval_report_widget.py`
- **IMPLEMENT**: Tabbed report widget:
  - "Overview": mAP@0.5, mAP@0.5:0.95, Precision, Recall, F1 — large numbers
  - "Per-Class": QTableWidget — class, instances, P/R/mAP. Sortable. Color-coded cells
  - "Confusion Matrix": matplotlib figure via `FigureCanvasQTAgg`
  - "PR Curve": matplotlib figure with per-class curves
- **MIRROR**: Existing `MetricsPlot` widget for matplotlib embedding
- **GOTCHA**: matplotlib is a hard dependency (pyproject.toml:92). Metrics format follows Ultralytics output. Use existing `MetricsPlotWidget` from `widgets/metrics_plot.py` for confusion matrix and per-class AP plots.
- **VALIDATE**: Load mock metrics → each tab renders without crash.

### Task 4b.2: Create MisclassGallery

- **ACTION**: CREATE `anylabeling/views/platform/widgets/misclass_gallery.py`
- **IMPLEMENT**: Horizontal scrollable thumbnail cards. Each: image (150x150), "Pred: X / GT: Y" label, confidence. Click → full image with prediction vs ground-truth overlay. Data from evaluation FP/FN lists.
- **MIRROR**: `QWIDGET_PATTERN`
- **GOTCHA**: If evaluation doesn't save per-image results, show "Misclassification images not available for this run."
- **VALIDATE**: Empty result → graceful empty state message.

### Task 4b.3: Integrate into EvaluateWorkspace

- **ACTION**: UPDATE `anylabeling/views/platform/evaluate_workspace.py`
- **IMPLEMENT**: Replace simple QTextEdit with EvalReportWidget + MisclassGallery below. Keep run selector + "Start Evaluation" button. Add "Re-evaluate" for existing runs.
- **MIRROR**: Existing EvaluateWorkspace structure
- **GOTCHA**: Evaluation is job-based. Show progress in JobConsole, not blocking dialog.
- **VALIDATE**: Run evaluation → switch tabs → data renders without crash.

### Task 4b.4: Add inference validation to InferWorkspace

- **ACTION**: UPDATE `anylabeling/views/platform/infer_workspace.py`
- **IMPLEMENT**: Add "Validate on Project Assets" mode. Select trained model + N assets. Run inference, display predictions side-by-side with ground truth (if annotations exist). Show per-image confidence stats.
- **MIRROR**: Existing InferWorkspace + InferenceViewerWidget
- **GOTCHA**: Inference runs on CPU (ONNX). Large images may need tiling.
- **VALIDATE**: Select model + 5 assets → validation → predictions render with overlay.

### Task 4b.5: Add ONNX self-test to ExportWorkspace + ExportService

- **ACTION**: UPDATE `export_workspace.py` + `export_service.py` + `export_config.py`
- **IMPLEMENT**:
  - `ExportService.self_test_onnx(onnx_path, sample_count=10)` — run inference on N samples, compare with PyTorch output (tolerance: 1e-3 relative). Return `SelfTestReport`.
  - `SelfTestReport` frozen dataclass: `passed: bool`, `samples_tested: int`, `max_deviation: float`, `failures: list[str]`
  - ExportWorkspace: "Self-Test" section — progress bar, pass/fail report, "Package for Deployment" button → zip (ONNX + config + labels.txt + self-test report)
- **MIRROR**: `SERVICE_PATTERN`, existing ExportService
- **GOTCHA**: ONNX session created fresh per self-test. Sample selection seeded for reproducibility.
- **VALIDATE**: Export model → self-test → check report → package downloads.

### Task 4b.6: Refactor test_export_workspace_phase4.py to align with PRD

- **ACTION**: REFACTOR `tests/platform/views/test_export_workspace_phase4.py` (existing 559 lines → ~650 lines)
- **IMPLEMENT**: Replace multi-format tests with PRD-aligned ONNX-only export tests:
  1. **REMOVE** `TestFormatCheckboxesFromProvider` (lines 62-124) — tests 15 formats; PRD says ONNX only
  2. **REMOVE** `TestExportServiceMultiFormat` (lines 462-557) — tests OpenVINO/TensorRT/CoreML
  3. **REMOVE** `TestExportOptions.test_encrypt_shows_password_input` (lines 227-253) — encryption not in PRD
  4. **MODIFY** `TestDeployPreviewTree` (lines 132-183) — update expected files from `preprocess.yaml`/`inference.py`/`requirements.txt` to PRD-specified `preprocess.json`/`postprocess.json`/`model_manifest.json`/`checksum.sha256`/`validation_report.json`/`sample/`/`README_部署说明.md`
  5. **KEEP** `TestModelRegistryService` (lines 283-454) — fully aligned with PRD "注册为预标注模型"
  6. **KEEP** `TestAutoRegisterCheckbox` (lines 260-275) — aligned, adjust label to match PRD
  7. **KEEP** `TestExportOptions` (lines 191-253, minus encrypt) — labels/preprocess checkboxes retained
  8. **ADD** `TestTargetEnvironmentSelection` — target env selector (通用 ONNX / Windows CPU / 本平台预标注 / 自定义), default ONNX selected
  9. **ADD** `TestCompatibilityCheck` — per-check pass/fail UI: task support, weight integrity, input size, labels, pre/post processing
  10. **ADD** `TestONNXSelfTest` — `ExportService.self_test_onnx()` mock: N samples passed/failed, max deviation, report generation
  11. **ADD** `TestSelfTestReport` — `SelfTestReport` frozen dataclass: `passed`, `samples_tested`, `max_deviation`, `failures`, `created_at`
  12. **ADD** `TestDeliveryPackageStructure` — verify all 10 files in PRD spec present in deploy tree
  13. **ADD** `TestCompletionPage` — export success state: location displayed, ONNX check status, sample self-test count (e.g., "20/20 通过"), checksum present, action buttons enabled
- **MIRROR**: `TEST_STRUCTURE` from existing tests, AAA pattern, `_make_app()` fixture for QWidget tests
- **GOTCHA**: Do NOT import or reference OpenVINO/TensorRT/CoreML formats; use `Formats.ONNX` or literal `"onnx"` only. Deploy tree items must match PRD §7.10 delivery package structure exactly.
- **VALIDATE**: `pytest tests/platform/views/test_export_workspace_phase4.py -v` — all tests pass

### Task 4b.7: Write new Phase 4 test files

- **ACTION**: CREATE test files:
  1. `tests/platform/application/test_training_readiness.py` (8 tests)
  2. `tests/platform/application/test_onnx_selftest.py` (6 tests)
- **MIRROR**: `TEST_STRUCTURE` from existing tests
- **VALIDATE**: `pytest tests/platform/ -q` — 371+new tests pass

---

## Testing Strategy

### Export Workspace (refactored from existing `test_export_workspace_phase4.py`)

| Test | Input | Expected Output |
|------|-------|----------------|
| Target env: default ONNX | Widget init | ONNX env selected by default |
| Target env: switch to Windows CPU | Click "Windows CPU" | Format pre-filtered, options adjusted |
| Compatibility: all pass | Mock provider, valid run | All 5 checks green, export button enabled |
| Compatibility: missing labels | Run with no labels.json | Labels check red, export button disabled |
| Deploy preview: PRD structure | Widget init | 10 items match PRD §7.10 exactly |
| ONNX self-test: all pass | Mock 20 samples, deviation < 1e-3 | `SelfTestReport(passed=True, samples_tested=20)` |
| ONNX self-test: failures | Mock 5 failures | `SelfTestReport(passed=False, failures=[...])` |
| Completion: success state | Export completed | Location, ONNX check, "20/20 通过", checksum |
| Auto-register: default checked | Widget init | Checkbox checked, label matches PRD |

### Training Readiness & ONNX Self-Test (new files)

| Test | Input | Expected Output |
|------|-------|----------------|
| Readiness: empty project | 0 assets | ready=False |
| Readiness: valid project | 100 assets, 80 annotated | ready=True |
| Readiness: disk space | <1GB free | Warning, not blocking |
| ONNX self-test: matching | Same input ONNX vs PyTorch | deviation < 1e-3, pass |
| ONNX self-test: mismatched | Different architectures | deviation > threshold, fail |
| Run recovery: orphaned | Run status "running" | Recovery prompt shown |
| Run recovery: clean | No orphaned runs | No prompt |

---

## Validation Commands

```bash
# Import verification
python -c "from anylabeling.views.platform.widgets.model_library import ModelLibrary; print('OK')"
python -c "from anylabeling.views.platform.widgets.train_readiness_widget import TrainReadinessWidget; print('OK')"
python -c "from anylabeling.views.platform.widgets.eval_report_widget import EvalReportWidget; print('OK')"
python -c "from anylabeling.views.platform.widgets.misclass_gallery import MisclassGallery; print('OK')"
python -c "from anylabeling.platform.domain.export_config import SelfTestReport, ExportTarget, CompatibilityResult; print('OK')"

# Unit tests — new files
pytest tests/platform/application/test_training_readiness.py -v
pytest tests/platform/application/test_onnx_selftest.py -v

# Unit tests — refactored
pytest tests/platform/views/test_export_workspace_phase4.py -v

# Regression
pytest tests/platform/ -q
```

---

## Acceptance Criteria

- [ ] Training readiness check validates data, annotations, model, disk before training
- [ ] Recovery prompt appears on project open if orphaned training job exists
- [ ] Model library shows all trained models with metrics, searchable/filterable
- [ ] Evaluation report shows per-class metrics, confusion matrix, PR curves
- [ ] Misclassification gallery shows FP/FN examples with thumbnails
- [ ] ONNX self-test runs 5–20 samples with pass/fail report
- [ ] Self-test report included in deploy package
- [ ] Inference on project assets validates model quality visually
- [ ] All tests pass, zero regressions (371+)

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| matplotlib import fails on some Windows installs | Medium | Medium | Lazy import, fallback to text metrics table |
| ONNX/PyTorch version mismatch | Low | High | Version check before self-test, clear error |
| Run format changes break model library scan | Low | Medium | Schema version check, graceful skip |
| Large eval JSON causes UI freeze | Low | Medium | Background thread load with spinner |
