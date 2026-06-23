# Plan: Phase 3 — Data & Labeling Productionization

## Summary

Deliver the three sub-phases that transform X-AnyLabeling from a "works in the happy path" tool into a production-grade industrial data platform: **(3a)** import precheck pipeline + AssetRepository integration + QAbstractListModel-based virtual asset list with filtering; **(3b)** debounced auto-save with crash recovery + pixel-level mask brush + AI pre-labeling suggestion workflow (pending/accept/reject); **(3c)** visual tile grid preview with per-tile label inspection + build version management + manifest integrity verification + cross-split data leakage detection.

## User Story

As an industrial vision engineer working with 10k–50k real-world images (including damaged files, 32k×32k TIFFs, and mixed formats) on an offline Windows machine,
I want import to precheck files before copying, the asset list to stay responsive at scale, annotations to survive crashes, AI predictions to be reviewable before acceptance, and dataset builds to be verifiable for tile correctness and data leakage,
So that I can confidently manage production-scale industrial datasets without data loss, silent corruption, or workflow-blocking UI freezes.

## Problem → Solution

| Current State | Desired State |
|---|---|
| Import copies immediately without precheck; errors surface mid-copy | Import separates precheck (scan + validate) from execution (copy); user reviews issues before any data is moved |
| `AssetRepository` exists but is unused; 5 different inline scan implementations with inconsistent extension sets | `AssetRepository` is the single source of truth; all pages use it; extension set is unified |
| Asset list uses `QListWidget` — 10k assets = 10k QWidget items = UI freeze | `QAbstractListModel` + `QListView` with virtual rendering — 50k assets scroll smoothly |
| No filtering beyond name search | Filter by status, label presence, group, image dimensions, import batch |
| Auto-save triggers on every shape event (no debounce); no crash recovery | 500ms debounced save; recovery prompt on next open after crash |
| Mask "brush" is polygon point-sampling, not pixel-level painting | Real mask brush with adjustable size, eraser, and undo |
| AI predictions are committed directly as labels | AI predictions enter "suggestion" state; user accepts/rejects individually or in batch |
| Tile config exists but no visual preview of grid or per-tile label splits | Visual tile grid overlay on source image; click a tile to inspect its label fragments |
| No manifest integrity checks; corruption detected only on read failure | SHA-256 manifest hashing with verification on load; corruption reported proactively |
| Leakage prevention only via group_by_group_id strategy; no detection | Explicit leakage report: same-group assets in multiple splits, per-class distribution imbalance |

## Metadata

- **Complexity**: XL (3 sub-phases, 18–22 files, ~2200 lines)
- **Source PRD**: `.claude/PRPs/prds/x-anylabeling-productization.prd.md`
- **PRD Phase**: Phase 3 (pending), sub-phases 3a/3b/3c
- **Depends On**: Phase 2b (WorkflowState + ProjectSession + TaskCenterDrawer + ErrorBanner — in-progress)
- **Estimated Files**: 12 new, 8 modified

---

## UX Design

### Sub-phase 3a: Import Precheck + Virtual List

**Before:**
```
┌─ ImageImportDialog (modal) ─────────────────────────────┐
│ [Drop Zone]              [Select Files] [Select Folder]  │
│ [✓] Dedup  [✓] Group  [✓] Large detect  [ ] Annotations │
│ ┌─ Preview grid (QListWidget, all thumbnails loaded) ─┐  │
│ │ img001.jpg  img002.jpg  img003.jpg  ...              │  │
│ └──────────────────────────────────────────────────────┘  │
│ [ProgressBar (hidden)]                                   │
│ Total: 0 | Large: 0 | Duplicates: 0                      │
│                                    [Cancel] [Import]      │
└──────────────────────────────────────────────────────────┘
```

**After:**
```
┌─ Import Workspace (embedded, non-modal) ────────────────────────────────────┐
│ Sources                                                   [Add Files][Folder]│
│ ┌─ D:\data\wafer\       folder      ~10,200 files    [✕ remove] ─┐          │
│ ┌─ D:\data\product_c\   folder      ~5,400 files     [✕ remove] ─┘          │
│                                                                             │
│ Precheck Results                                            [Re-scan]        │
│ ✓ Valid: 15,420  ⚠ Damaged: 12  ⚠ Unsupported: 8  ⚠ Duplicates: 34        │
│ ⚠ Large images (>2000px): 16 (max 32,000×32,000)                            │
│ Estimated disk: 38.6 GB  |  Available: 412 GB                               │
│ [View problem files ▸]                                                      │
│                                                                             │
│ Import Rules                                                                │
│ Storage:  ● Copy to project  ○ Reference originals                          │
│ Duplicates: ● Skip  ○ Keep copies  ○ Replace                                │
│ [✓] Group by source folder    Annotations: [None ▼]                         │
│                                                       [Start Import (15,420)]│
└─────────────────────────────────────────────────────────────────────────────┘

After import — inline result (does not auto-navigate away):
┌─ Import Complete ───────────────────────────────────────────────────────────┐
│ ✓ Imported 15,408 images  |  12 skipped (damaged)  |  0 duplicates           │
│ 16 large images detected — configure tiling in Dataset Build                │
│                                                    [Continue to Task Config] │
│                                                    [View in Asset List]      │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Asset List (After — using QAbstractListModel):**
```
┌─ Assets (15,408) ───────────────────────────────────────────────────────────┐
│ [Search…] [Status: All ▼] [Group: All ▼] [Label: All ▼] [Sort: Name ▼]     │
│ ┌─ Thumbnail │ filename │ dims │ group │ status │ date ──────────────────┐  │
│ │ [img]      │ wafer_A01│ 2048 │ wafer │ ✓ annotated │ 2026-06-08        │  │
│ │ [img]      │ wafer_A02│ 2048 │ wafer │ ○ unannotated│ 2026-06-08       │  │
│ │ [img]      │ prodC_01 │ 4096 │ prod_c│ ◐ partial   │ 2026-06-08        │  │
│ │ ... virtual rendering ... only visible rows are materialized ...         │  │
│ └──────────────────────────────────────────────────────────────────────────┘  │
│ Showing 1-50 of 15,408  |  Annotated: 8,230  |  Pending Review: 142          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Sub-phase 3b: Auto-Save + Mask Brush + AI Suggestions

**Before (label save):**
- Every shape event → immediate blocking save
- Crash → all unsaved work lost
- No dirty-state indicator beyond "Save" button enabled/disabled

**After (label save):**
```
StatusBar: ● Saved  |  Last save: 2s ago  |  Auto-save: ON
           ● Saving… (debounce 500ms)
           ● Save failed — Retry  |  Recovery copy available
```

**Before (mask brush):**
- "Brush" = polygon drawing with auto-point-sampling along mouse path
- No pixel-level mask editing

**After (mask brush):**
```
Canvas toolbar adds:
  [🖌 Mask Brush]  Size: [====○====] 30px  [Eraser]  [Undo Stroke]

Drawing on canvas directly modifies the selected shape's mask bitmap.
Each stroke is an undoable operation.
```

**Before (AI predictions):**
- AI result shapes are added directly to canvas as permanent labels

**After (AI suggestions):**
```
AI predictions appear with dashed outline + confidence badge:
  ┌─ AI Suggestion (confidence: 0.87) ─┐
  │ [Accept] [Reject] [Edit & Accept]  │
  └────────────────────────────────────┘

Properties panel when AI suggestion selected:
  Source: SAM-HQ @ confidence 0.87
  Generated: 2026-06-08 14:32:15
  [Accept] [Reject] [Accept All Visible] [Reject All]
```

### Sub-phase 3c: Tile Preview + Build Versions + Manifest + Leakage

**Before (tile config):**
```
Tile width: [640]  Height: [640]  Overlap X: [0]  Y: [0]
Edge mode: [crop ▼]
Estimated tiles: 8,420  |  Estimated size: 34 GB
```

**After (tile preview):**
```
┌─ Tile Preview ──────────────────────────────────────────────────────────────┐
│ ┌─ Source image + grid overlay ──────┬─ Tile inspector ──────────────────┐  │
│ │                                    │  Tile: tile_wafer_A01_0003_0005    │  │
│ │  ┌──┬──┬──┬──┬──┐                 │  Region: (1920, 3200) 640×640     │  │
│ │  │  │  │  │  │  │                 │  Objects in tile: 3                 │  │
│ │  ├──┼──┼──┼──┼──┤                 │  ┌─ obj_002: polygon (visible) ─┐  │  │
│ │  │  │  │██│  │  │ ← selected      │  │  Fragment area: 85%           │  │
│ │  ├──┼──┼──┼──┼──┤                 │  └──────────────────────────────┘  │  │
│ │  │  │  │  │  │  │                 │  ┌─ obj_007: polygon (truncated)┐  │  │
│ │  └──┴──┴──┴──┴──┘                 │  │  Fragment area: 42% ⚠         │  │
│ │  8 cols × 12 rows = 96 tiles      │  └──────────────────────────────┘  │  │
│ │                                    │  ┌─ obj_012: bbox (visible) ────┐  │  │
│ │ Legend:                            │  │  Full contained ✓             │  │
│ │  ██ = has labels    □ = empty      │  └──────────────────────────────┘  │  │
│ │  ⚠ = truncated labels              │                                     │  │
│ └────────────────────────────────────┴─────────────────────────────────────┘  │
│ [◀ Previous Tile] [Next Tile ▶]  |  Showing tile 35/96                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Before (build management):**
- Single build directory; build completes → message box shows build ID

**After (build management):**
```
Dataset Builds:
┌─ Build History ────────────────────────────────────────────────────────────┐
│ ID                  Date        Assets   Tiles   Status    Actions           │
│ build-a1b2c3d4e5f6  2026-06-08  15,408   8,420   ✓ Ready   [Use][Inspect]   │
│ build-7890abcdef12  2026-06-07  12,100   —       ✓ Ready   [Use][Inspect]   │
│ build-fail12345678  2026-06-06  15,408   —       ✗ Failed  [View Error]     │
└─────────────────────────────────────────────────────────────────────────────┘

Leakage Report (on build completion):
┌─ Data Leakage Report ──────────────────────────────────────────────────────┐
│ Split strategy: random_by_asset  |  Seed: 42                                 │
│ ✓ No cross-split group leakage detected                                      │
│ ⚠ Class imbalance: "small_void" has 2 samples in val (0.1% vs 10% expected) │
│ ℹ Per-class distribution: [View Full Report]                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Interaction Changes

| Touchpoint | Before | After | Notes |
|---|---|---|---|
| Import | Modal dialog, immediate copy | Embedded workspace, precheck → review → execute | Non-blocking; user can navigate away |
| Asset list | QListWidget, all items materialized | QAbstractListModel, virtual rendering | 50k assets = smooth scroll |
| Asset filtering | Name search only | Multi-facet: status, group, label, dims, date | QSortFilterProxyModel |
| Label save | Immediate on every shape event | 500ms debounced; auto-save indicator in status bar | Matches PRD spec §3.5 |
| Crash recovery | None | On project open: detect dirty state → offer recovery | Atomic .tmp → .json replace |
| Mask brush | Polygon point-sampling | Pixel-level bitmap brush + eraser | New tool; existing polygon brush preserved |
| AI predictions | Direct commit as labels | Suggestion state → accept/reject workflow | Predictions stored separately until accepted |
| Tile config | Numeric inputs + text estimate | Visual grid overlay on source image + tile inspector | Click tile to see label fragments |
| Build history | Single latest build | Version list with status, inspection, comparison | Immutable history; no overwrite |
| Manifest integrity | None | SHA-256 hash on write; verify on read | Atomic writer already exists |
| Leakage detection | group_by_group_id strategy only | Explicit leakage report on build completion | Per-class distribution + cross-split group check |

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `anylabeling/platform/application/import_service.py` | 1–210 | Core import logic to extend with precheck |
| P0 | `anylabeling/platform/application/asset_repository.py` | 1–103 | Repository to integrate across all pages |
| P0 | `anylabeling/views/platform/label_workspace.py` | 1–537 | Current asset list (QListWidget) to replace with model/view |
| P0 | `anylabeling/views/platform/image_import_dialog.py` | 1–595 | Current import UI to replace with embedded workspace |
| P0 | `anylabeling/views/labeling/label_widget.py` | 2800–2820 (set_dirty), 3475–3490 (brush toggle), 4718–4750 (save_labels) | Auto-save trigger and brush activation |
| P0 | `anylabeling/views/labeling/widgets/canvas.py` | 53–145 (class + signals), 678–694 (brush drawing), 3492–3520 (finalise) | Canvas modes, brush, shape finalization |
| P0 | `anylabeling/platform/application/dataset_build_service.py` | 1–620 | Full build pipeline: splits, tiles, manifests |
| P0 | `anylabeling/platform/tiling/tile_planner.py` | 1–50 | Tile grid generation algorithm |
| P0 | `anylabeling/platform/tiling/label_splitters/polygon.py` | 1–60 | Polygon splitter (reference for preview logic) |
| P1 | `anylabeling/views/platform/preprocess_workspace.py` | 1–340 | Current tile/split UI to extend with preview |
| P1 | `anylabeling/views/platform/workbench_window.py` | 85–320, 910–990 | Service wiring and build_requested handler |
| P1 | `anylabeling/platform/application/annotation_adapter.py` | 1–213 | Shape ↔ AnnotationObject save bridge |
| P1 | `anylabeling/views/labeling/widgets/auto_labeling/auto_labeling.py` | 76–200 | AI labeling widget integration |
| P1 | `anylabeling/views/platform/style.py` | 1–100, 455–498 | Layout constants, theme helpers |
| P2 | `anylabeling/platform/domain/asset.py` | 1–30 | Asset domain model |
| P2 | `anylabeling/platform/domain/annotation.py` | 1–50 | AnnotationDocument, AnnotationObject |
| P2 | `anylabeling/platform/domain/tile.py` | 1–40 | TilePlan, TileRecord |
| P2 | `anylabeling/platform/infrastructure/manifest_store.py` | 1–75 | JSONL manifest I/O |
| P2 | `anylabeling/platform/infrastructure/atomic_writer.py` | 1–50 | Atomic file write pattern |
| P2 | `anylabeling/views/platform/shell/error_banner.py` | 1–end | Error banner API for import/build errors |

## External Documentation

| Topic | Source | Key Takeaway |
|---|---|---|
| Qt Model/View Programming | https://doc.qt.io/qt-6/model-view-programming.html | QAbstractListModel + QSortFilterProxyModel pattern for virtual lists |
| Qt Graphics View | https://doc.qt.io/qt-6/graphicsview.html | QGraphicsScene/QGraphicsView for tile grid overlay rendering |
| Shapely (used by splitters) | https://shapely.readthedocs.io/ | `intersection()`, `make_valid()`, `area` — already used in polygon/obb splitters |

---

## Patterns to Mirror

### SERVICE_PATTERN
```python
# SOURCE: anylabeling/platform/application/dataset_build_service.py:1-50
"""DatasetBuildService — orchestrate dataset construction from assets + annotations.

Architecture constraints:
    - No PyQt6 imports.
    - No Ultralytics imports.
    - All paths use pathlib.Path.
    - All I/O uses UTF-8.
"""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path

logger = logging.getLogger(__name__)

class DatasetBuildService:
    def __init__(self, project_root: str | Path) -> None:
        self._project_root = Path(project_root)

    @property
    def project_root(self) -> Path:
        return self._project_root
```

### QWIDGET_PATTERN
```python
# SOURCE: anylabeling/views/platform/shell/page_header.py:29-52
# Shell widgets: __init__ → _build_ui() → _apply_theme()
# Public API uses set_*() methods, private state with underscore prefix
# Signals declared at class level
class PageHeader(QtWidgets.QWidget):
    primary_action_triggered = QtCore.pyqtSignal()
    breadcrumb_clicked = QtCore.pyqtSignal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._title: str = ""
        self._build_ui()
        self._apply_theme()
```

### QABSTRACTLISTMODEL_PATTERN
```python
# SOURCE: Qt Model/View pattern (not yet used in this codebase)
# Pattern to follow for AssetListModel:
class AssetListModel(QtCore.QAbstractListModel):
    """Virtual list model for assets — only visible rows are queried."""

    def rowCount(self, parent=QtCore.QModelIndex()) -> int:
        return len(self._asset_ids)

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid():
            return None
        asset = self._get_asset(index.row())  # lazy load
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return Path(asset.path).name
        # ... other roles
        return None

    def canFetchMore(self, parent) -> bool:
        return self._cursor < self._total_count

    def fetchMore(self, parent) -> None:
        # Load next batch from AssetRepository
        ...
```

### VIEWMODEL_PATTERN
```python
# SOURCE: anylabeling/views/platform/view_models/dataset_vm.py:1-60
"""DatasetViewModel — state management for dataset build configuration."""

from __future__ import annotations

class DatasetViewModel:
    """ViewModel for dataset build configuration.

    No PyQt6 imports. Pure state management with validation.
    """

    def __init__(self) -> None:
        self._tile_width: int = 640
        self._tile_height: int = 640
        # ...

    @property
    def tile_width(self) -> int:
        return self._tile_width

    @tile_width.setter
    def tile_width(self, value: int) -> None:
        if value < 64 or value > 4096:
            raise ValueError(f"Tile width must be 64–4096, got {value}")
        self._tile_width = value

    def can_build(self) -> bool:
        return self._asset_count > 0 and self._task_spec_id is not None
```

### TEST_STRUCTURE
```python
# SOURCE: tests/views/platform/test_workbench_shell.py:1-80
"""Tests for WorkbenchWindow Shell components."""

from __future__ import annotations

import pytest

def _qapp_available() -> bool:
    """Return True if QApplication can be instantiated (display available)."""
    try:
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            import os
            if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
                return True
            return False
        return True
    except ImportError:
        return False

_HAS_QAPP = _qapp_available()
skip_without_display = pytest.mark.skipif(
    not _HAS_QAPP, reason="Requires display (QApplication)"
)

class TestAssetListModel:
    @pytest.fixture
    def qapp(self):
        if not _HAS_QAPP:
            pytest.skip("Requires QApplication")
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        yield app

    def test_row_count_matches_repository(self, qapp, tmp_path):
        # Arrange
        # Act
        # Assert
        ...
```

### ERROR_HANDLING
```python
# SOURCE: anylabeling/views/platform/workbench_window.py:888,978
# Platform pattern: try/except → logger.exception → user-facing message
try:
    result = service.do_work()
except Exception as exc:
    logger.exception("Operation failed")
    self._show_error(
        title="导入失败",
        what=f"文件复制过程中发生错误",
        impact=f"{failed_count} 个文件未能导入",
        fix="检查磁盘空间和文件权限后重试",
        traceback=str(exc),
    )
```

### LOGGING_PATTERN
```python
# SOURCE: anylabeling/views/platform/label_workspace.py:18
# All platform files use module-level logger
import logging
logger = logging.getLogger(__name__)
```

### DOMAIN_DATACLASS
```python
# SOURCE: anylabeling/platform/domain/asset.py:1-30
# Domain entities use @dataclass (frozen=True for value objects)
@dataclass(frozen=True)
class Asset:
    id: str
    path: str
    width: int
    height: int
    channels: int | None = None
    bit_depth: int | None = None
    group_id: str | None = None
    sha256: str | None = None
```

---

## Files to Change

### Sub-phase 3a: Import Precheck + Virtual List + Filtering

| File | Action | Justification |
|---|---|---|
| `anylabeling/platform/application/import_service.py` | UPDATE | Add `precheck()` method that scans without copying; add progress callback support |
| `anylabeling/platform/domain/import_config.py` | UPDATE | Add `PrecheckResult` dataclass (valid, damaged, unsupported, duplicates, large, estimated_size) |
| `anylabeling/views/platform/workspaces/import_workspace.py` | CREATE | Embedded (non-modal) import page: source list, precheck results, import rules, progress, completion report |
| `anylabeling/views/platform/view_models/import_vm.py` | CREATE | ImportViewModel: source management, precheck state, import execution delegation |
| `anylabeling/views/platform/view_models/asset_list_vm.py` | CREATE | AssetListViewModel: delegates to AssetRepository, manages filter/sort state |
| `anylabeling/views/platform/widgets/asset_list_model.py` | CREATE | QAbstractListModel implementation with lazy loading via AssetRepository |
| `anylabeling/views/platform/widgets/asset_filter_bar.py` | CREATE | Filter bar widget: search, status dropdown, group dropdown, label dropdown |
| `anylabeling/views/platform/label_workspace.py` | UPDATE | Replace QListWidget with QListView + AssetListModel; integrate filter bar |
| `anylabeling/views/platform/data_workspace.py` | UPDATE | Use AssetRepository instead of inline scan for asset counts |
| `anylabeling/views/platform/workbench_window.py` | UPDATE | Route to ImportWorkspace instead of ImageImportDialog; wire AssetRepository |

### Sub-phase 3b: Auto-Save + Mask Brush + AI Suggestions

| File | Action | Justification |
|---|---|---|
| `anylabeling/views/labeling/label_widget.py` | UPDATE | Add debounced auto-save timer (500ms); add dirty-state tracking; add crash recovery on load |
| `anylabeling/views/labeling/widgets/canvas.py` | UPDATE | Add mask brush drawing mode (pixel-level bitmap editing); mask stroke undo |
| `anylabeling/views/labeling/widgets/mask_brush.py` | CREATE | MaskBrushTool: brush cursor, size, eraser mode, bitmap overlay rendering |
| `anylabeling/views/labeling/widgets/auto_labeling/auto_labeling.py` | UPDATE | Add suggestion workflow: predictions stored as "pending" with accept/reject API |
| `anylabeling/views/platform/label_workspace.py` | UPDATE | Wire AI suggestion workflow (accept/reject buttons in properties panel); status bar save indicator |
| `anylabeling/platform/application/annotation_adapter.py` | UPDATE | Add `save_draft()` for auto-save (atomic .tmp → .json); add `get_recovery_info()` for crash detection |
| `anylabeling/platform/domain/annotation.py` | UPDATE | Add `AnnotationSuggestion` dataclass (model_id, confidence, timestamp, status) |
| `anylabeling/views/platform/workspaces/label_workspace.py` | UPDATE | Add save indicator to status bar; add recovery prompt on project open |

### Sub-phase 3c: Tile Preview + Build Versions + Manifest + Leakage

| File | Action | Justification |
|---|---|---|
| `anylabeling/views/platform/widgets/tile_preview_widget.py` | CREATE | QGraphicsView-based tile grid overlay: source image + grid + per-tile label count |
| `anylabeling/views/platform/widgets/tile_inspector_panel.py` | CREATE | Per-tile detail: object list, fragment areas, truncation warnings |
| `anylabeling/views/platform/preprocess_workspace.py` | UPDATE | Add tile preview tab with TilePreviewWidget; add build history tab |
| `anylabeling/platform/application/dataset_build_service.py` | UPDATE | Add `verify_manifest_integrity()` static method; add `detect_leakage()` method |
| `anylabeling/platform/domain/dataset.py` | UPDATE | Add `LeakageReport` dataclass; add `ManifestIntegrityReport` dataclass |
| `anylabeling/platform/infrastructure/manifest_store.py` | UPDATE | Add `compute_manifest_hash()` and `verify_manifest_hash()` |
| `anylabeling/views/platform/view_models/dataset_vm.py` | UPDATE | Add build history, preview state, leakage report state |
| `anylabeling/views/platform/workbench_window.py` | UPDATE | Wire tile preview, build history, leakage report display |

### Cross-cutting

| File | Action | Justification |
|---|---|---|
| `anylabeling/views/platform/style.py` | UPDATE | Add constants: ASSET_LIST_ROW_HEIGHT, TILE_PREVIEW_MIN_SIZE, MASK_BRUSH_CURSOR_SIZE |
| `anylabeling/views/platform/i18n.py` | UPDATE | Add translation strings for all new UI text |
| `anylabeling/views/platform/shell/__init__.py` | UPDATE | Export new widgets |
| `anylabeling/views/platform/view_models/__init__.py` | UPDATE | Export new ViewModels |
| `anylabeling/views/platform/widgets/__init__.py` | CREATE | New package for reusable platform widgets |
| `anylabeling/platform/application/__init__.py` | UPDATE | Export new services/types |

---

## NOT Building

- **Online/cloud import sources** — only local filesystem import
- **Annotation format import** (YOLO/COCO/VOC parsing during import) — checkbox exists in old UI but backend not implemented; deferred to Phase 4
- **Full augmentation pipeline** — checkboxes remain disabled; Phase 4
- **New shape types** (keypoint skeleton editor, 3D cuboid editor) — existing shape types only
- **Multi-model AI ensemble pre-labeling** — single model at a time
- **Build comparison / diff** (side-by-side build version comparison) — deferred to Phase 4 evaluation comparison
- **Tile plan export/import** — tile config stays per-build
- **Real-time collaborative labeling** — offline single-user tool
- **GPU-accelerated mask brush rendering** — CPU bitmap operations sufficient for MVP
- **Auto-segmentation quality scoring** — AI suggestions show confidence only; no automated quality gate
- **Migration of all existing `QMessageBox` calls to `ErrorBanner`** — Phase 2b pattern; not in Phase 3 scope
- **Dark mode theme** — style.py theme support exists; not part of Phase 3 deliverables

---

## Step-by-Step Tasks

### TASK GROUP A: Sub-phase 3a — Import Precheck + Virtual List + Filtering

---

### Task A1: Add PrecheckResult domain model + ImportService.precheck()

- **ACTION**: UPDATE `anylabeling/platform/domain/import_config.py` and `anylabeling/platform/application/import_service.py`
- **IMPLEMENT**:
  ```python
  # In import_config.py — add:
  @dataclass(frozen=True)
  class PrecheckResult:
      """Result of scanning sources before importing."""
      total_files: int
      valid_files: list[str]          # Absolute paths
      damaged_files: list[str]        # cv2.imread failed
      unsupported_files: list[str]    # Wrong extension
      oversized_files: list[tuple[str, int, int]]  # (path, w, h) for images > large_threshold
      estimated_size_bytes: int
      errors: list[str] = field(default_factory=list)

      @property
      def ok_count(self) -> int: return len(self.valid_files)
      @property
      def damaged_count(self) -> int: return len(self.damaged_files)
      @property
      def unsupported_count(self) -> int: return len(self.unsupported_files)
      @property
      def oversized_count(self) -> int: return len(self.oversized_files)

  # In import_service.py — add:
  def precheck(
      self,
      sources: list[str],
      progress_callback: Callable[[int, int], None] | None = None,
  ) -> PrecheckResult:
      """Scan sources without copying. Returns PrecheckResult for user review.

      For each source: if file → validate single file; if directory → walk recursively.
      Validation: extension check → cv2.imread (read props only, no copy) → size check.
      """
      ...
  ```
- **MIRROR**: `ImportResult` pattern in import_config.py:30-50; `SERVICE_PATTERN` in import_service.py:41-53
- **IMPORTS**: `dataclasses.dataclass`, `dataclasses.field`, `pathlib.Path`, `cv2`, `os.walk`
- **GOTCHA**: Precheck must NOT copy any files. It only reads image headers via cv2.imread. For very large directories, progress_callback must fire periodically to keep UI responsive. Precheck is synchronous but runs in QThread via the ImportVM.
- **VALIDATE**: Unit test: precheck with valid images → ok_count matches. Precheck with damaged file → damaged_files populated. Precheck with .txt file → unsupported_files populated. Precheck with 4000×3000 image, threshold=2000 → oversized_files populated.

---

### Task A2: Add progress callback to ImportService.import_images()

- **ACTION**: UPDATE `anylabeling/platform/application/import_service.py`
- **IMPLEMENT**:
  ```python
  def import_images(
      self,
      paths: list[str],
      deduplicate: bool = True,
      group_by_folder: bool = True,
      progress_callback: Callable[[int, int, str], None] | None = None,
      cancel_token: threading.Event | None = None,
  ) -> ImportResult:
      """Import images with optional progress reporting and cancellation.

      Args:
          progress_callback: Called with (current, total, current_filename)
          cancel_token: If set, checked before each file; raises ImportCancelledError if set
      """
      ...
      for i, src in enumerate(src_paths):
          if cancel_token and cancel_token.is_set():
              raise ImportCancelledError(f"Cancelled after {i} files")
          if progress_callback:
              progress_callback(i + 1, total, src.name)
          # ... existing logic
  ```
- **MIRROR**: Existing import_images signature at import_service.py:48-53; `threading.Event` for cancellation
- **IMPORTS**: `threading`, `typing.Callable`
- **GOTCHA**: Backward compatibility — `progress_callback` and `cancel_token` are optional keyword args. Existing callers (ImageImportDialog._ImportWorker) continue to work unchanged. `ImportCancelledError` must be a new exception class.
- **VALIDATE**: Existing import tests pass (backward compat). New test: progress_callback called N times for N files. Cancel after 5 files → ImportCancelledError raised, partial files cleaned up.

---

### Task A3: Create ImportViewModel

- **ACTION**: CREATE `anylabeling/views/platform/view_models/import_vm.py`
- **IMPLEMENT**:
  ```python
  class ImportViewModel:
      """ViewModel for import workflow — source management, precheck, execution.

      No PyQt6 imports. Pure state machine with service delegation.
      """

      STAGE_IDLE = "idle"
      STAGE_PRECHECKING = "prechecking"
      STAGE_PRECHECK_DONE = "precheck_done"
      STAGE_IMPORTING = "importing"
      STAGE_COMPLETE = "complete"

      def __init__(self, import_service: ImportService) -> None:
          self._service = import_service
          self._sources: list[str] = []
          self._precheck_result: PrecheckResult | None = None
          self._import_result: ImportResult | None = None
          self._stage: str = self.STAGE_IDLE
          self._progress: tuple[int, int] = (0, 0)
          self._cancel_token: threading.Event | None = None

      # Properties: stage, sources, precheck_result, import_result, progress
      # Methods: add_sources(), remove_source(), start_precheck(), start_import(), cancel()
      ...
  ```
- **MIRROR**: `VIEWMODEL_PATTERN` — DatasetViewModel in dataset_vm.py; RunViewModel for service injection
- **IMPORTS**: `threading`, `pathlib.Path`, `ImportService`, `PrecheckResult`, `ImportResult`
- **GOTCHA**: No PyQt6 imports. State transitions must be validated. Cancel token must be thread-safe.
- **VALIDATE**: Unit test state machine transitions. Test precheck → result populated. Test import → result populated.

---

### Task A4: Create AssetListModel (QAbstractListModel)

- **ACTION**: CREATE `anylabeling/views/platform/widgets/asset_list_model.py`
- **IMPLEMENT**:
  ```python
  class AssetListModel(QtCore.QAbstractListModel):
      """Virtual list model backed by AssetRepository.

      Roles: DisplayRole (filename), UserRole (asset_id),
             DecorationRole (thumbnail — lazy), ToolTipRole (full path)

      Only fetches asset metadata for visible rows. Uses canFetchMore/fetchMore
      for incremental loading in batches of 100.
      """

      BATCH_SIZE = 100

      def __init__(self, asset_repository: AssetRepository, parent=None):
          super().__init__(parent)
          self._repo = asset_repository
          self._asset_ids: list[str] = []
          self._asset_cache: dict[str, Asset] = {}
          self._cursor: int = 0
          self._all_loaded: bool = False
          self._refresh_ids()

      def rowCount(self, parent=QtCore.QModelIndex()) -> int:
          return len(self._asset_ids)

      def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole) -> object:
          if not index.isValid():
              return None
          asset = self._get_asset(index.row())
          if role == QtCore.Qt.ItemDataRole.DisplayRole:
              return Path(asset.path).name
          if role == QtCore.Qt.ItemDataRole.UserRole:
              return asset.id
          if role == QtCore.Qt.ItemDataRole.ToolTipRole:
              return asset.path
          return None

      def canFetchMore(self, parent) -> bool:
          return not self._all_loaded

      def fetchMore(self, parent) -> None:
          new_ids = self._repo.scan_assets(offset=self._cursor, limit=self.BATCH_SIZE)
          if len(new_ids) < self.BATCH_SIZE:
              self._all_loaded = True
          self._cursor += len(new_ids)
          # beginInsertRows + append + endInsertRows
          ...

      def _get_asset(self, row: int) -> Asset:
          """Lazy-load asset metadata if not cached."""
          aid = self._asset_ids[row]
          if aid not in self._asset_cache:
              self._asset_cache[aid] = self._repo.get_asset(aid)
          return self._asset_cache[aid]

      def refresh(self) -> None:
          """Re-scan repository and reset model."""
          self.beginResetModel()
          self._asset_ids.clear()
          self._asset_cache.clear()
          self._cursor = 0
          self._all_loaded = False
          self._refresh_ids()
          self.endResetModel()
  ```
- **MIRROR**: `QWIDGET_PATTERN` for class structure; Qt Model/View `canFetchMore`/`fetchMore` pattern
- **IMPORTS**: `PyQt6.QtCore`, `pathlib.Path`, `AssetRepository`, `Asset`
- **GOTCHA**: `AssetRepository` currently has no `get_asset()` method. Must add `get_asset(path) -> Asset`. `canFetchMore`/`fetchMore` must properly call `beginInsertRows`/`endInsertRows`. Thumbnails (DecorationRole) are expensive — generate on demand in background thread.
- **VALIDATE**: Create 1000 dummy asset files in tmp_path → model.rowCount() == 1000. Scroll → fetchMore called. Data role returns filename. Refresh after adding files → rowCount updates.

---

### Task A5: Extend AssetRepository with full query API

- **ACTION**: UPDATE `anylabeling/platform/application/asset_repository.py`
- **IMPLEMENT**: Add methods:
  ```python
  def get_asset(self, asset_path: str) -> Asset:
      """Return full Asset metadata (reads image dimensions via cv2)."""
      ...

  def scan_assets(
      self,
      offset: int = 0,
      limit: int | None = None,
      group_filter: str | None = None,
      status_filter: str | None = None,
  ) -> list[str]:
      """Scan assets with pagination and optional filters."""
      ...

  def get_asset_ids_by_status(self, status: str) -> set[str]:
      """Return asset IDs matching annotation status (annotated/unannotated/partial)."""
      ...

  def get_asset_ids_by_group(self, group_id: str) -> set[str]:
      """Return asset IDs in a group."""
      ...

  def get_groups(self) -> list[str]:
      """Return sorted list of unique group IDs."""
      ...

  def get_stats(self) -> dict:
      """Return {total, annotated, unannotated, partial, by_extension, by_group}."""
      ...

  def invalidate_cache(self) -> None:
      """Clear internal caches; force re-scan on next query."""
      ...
  ```
- **MIRROR**: Existing `AssetRepository` methods at asset_repository.py:22-103
- **IMPORTS**: `cv2`, `json`, `pathlib.Path`, `Asset`
- **GOTCHA**: `AssetRepository` scans `assets/` directory. Annotation status requires reading `annotations/` directory — need to accept optional annotations_dir. Extension set must match ImportService exactly — extract to shared constant in `domain/import_config.py`.
- **VALIDATE**: Unit test get_asset returns correct dimensions. scan_assets with offset/limit returns correct slice. get_stats returns accurate counts.

---

### Task A6: Create AssetFilterBar + AssetFilterProxyModel

- **ACTION**: CREATE `anylabeling/views/platform/widgets/asset_filter_bar.py`
- **IMPLEMENT**:
  ```python
  class AssetFilterProxyModel(QtCore.QSortFilterProxyModel):
      """Multi-facet filter for asset list."""

      def __init__(self, parent=None):
          super().__init__(parent)
          self._status_filter: str = "all"
          self._group_filter: str = "all"
          self._label_filter: str = "all"

      def filterAcceptsRow(self, source_row, source_parent) -> bool:
          # Check all active filters
          ...

      def set_status_filter(self, status: str) -> None:
          self._status_filter = status
          self.invalidateFilter()

  class AssetFilterBar(QtWidgets.QWidget):
      """Horizontal filter bar: search input + dropdowns for status/group/label."""

      filter_changed = QtCore.pyqtSignal()

      def __init__(self, asset_repository: AssetRepository, parent=None):
          super().__init__(parent)
          self._build_ui()
          self._populate_dropdowns()
  ```
- **MIRROR**: `QWIDGET_PATTERN` (page_header.py, primary_navigation.py); `QSortFilterProxyModel` Qt pattern
- **IMPORTS**: `PyQt6.QtCore`, `PyQt6.QtWidgets`, `AssetRepository`, `style.*`, `i18n.tr`
- **GOTCHA**: Status filtering requires cross-referencing annotation files. Dropdown options populated from AssetRepository.get_groups() and TaskSpec labels.
- **VALIDATE**: Set status filter → only matching rows visible. Set group filter → only matching groups. Combined filters → intersection. Clear filters → all visible.

---

### Task A7: Create ImportWorkspace (replaces ImageImportDialog)

- **ACTION**: CREATE `anylabeling/views/platform/workspaces/import_workspace.py`
- **IMPLEMENT**: Full embedded import page as per UX design above:
  - `ImportWorkspace(QtWidgets.QWidget)` with signal `import_completed = QtCore.pyqtSignal(ImportResult)`
  - Source list with remove buttons
  - Precheck section: status labels for valid/damaged/unsupported/duplicates/large
  - "View problem files" expandable section
  - Import rules (storage mode, duplicate policy, group toggle, annotation format)
  - Progress bar with stage indicator
  - Cancel button during import
  - Completion report (does NOT auto-navigate away)
  - `_build_ui()` → `_apply_theme()` pattern
  - Uses `ImportViewModel` for state, `QThread` worker for precheck and import
- **MIRROR**: `QWIDGET_PATTERN` (page_header.py for structure); `PreprocessWorkspace` (preprocess_workspace.py:22-60 for layout); `ImageImportDialog` (image_import_dialog.py:98-350 for import logic reference)
- **IMPORTS**: `PyQt6.QtCore`, `PyQt6.QtWidgets`, `ImportViewModel`, `ImportService`, `style.*`, `i18n.tr`, `theme.get_theme`
- **GOTCHA**: Non-modal — user can navigate away during import. Precheck runs in QThread. Source files deleted between precheck and import → skip gracefully. "Reference originals" storage mode shows prominent risk warning.
- **VALIDATE**: Add sources → precheck runs → results displayed. Start import → progress updates. Import completes → report shown. Cancel during import → ImportCancelledError handled. Navigate away during import → import continues.

---

### Task A8: Wire ImportWorkspace + AssetRepository in WorkbenchWindow

- **ACTION**: UPDATE `anylabeling/views/platform/workbench_window.py`, `label_workspace.py`, `data_workspace.py`
- **IMPLEMENT**:
  1. In `WorkbenchWindow`: replace `ImageImportDialog` usage with `ImportWorkspace` page in the stack
  2. In `set_project()`: create `AssetRepository` and pass to all workspaces
  3. In `DataWorkspace`: use `self._asset_repository.get_stats()` instead of inline scan
  4. In `LabelWorkspace`: replace `QListWidget` + `_scan_assets()` with `QListView` + `AssetListModel` + `AssetFilterBar` + `AssetFilterProxyModel`
  5. Remove the 5 inline scan implementations
  6. Add `AssetRepository.invalidate_cache()` call after import completes
- **MIRROR**: `SERVICE_PATTERN` — existing service creation in workbench_window.py:228-237; LabelWorkspace structure in label_workspace.py:68-260
- **IMPORTS**: `ImportWorkspace`, `AssetRepository`, `AssetListModel`, `AssetFilterBar`, `AssetFilterProxyModel`
- **GOTCHA**: LabelWorkspace._scan_assets() replaced; annotation status detection moves to AssetRepository. Keep _ACTION_SHAPE_TYPE_MAP and _STATUS_ICON_MAP.
- **VALIDATE**: Open project → asset count in DataWorkspace matches AssetRepository. LabelWorkspace shows asset list via model/view. Filter by status → list updates. Import new files → refresh → new assets appear.

---

### TASK GROUP B: Sub-phase 3b — Auto-Save + Mask Brush + AI Suggestions

---

### Task B1: Add debounced auto-save timer to LabelingWidget

- **ACTION**: UPDATE `anylabeling/views/labeling/label_widget.py`
- **IMPLEMENT**:
  1. Add `self._auto_save_timer = QtCore.QTimer(self)` — single shot, 500ms interval
  2. Add `self._dirty_since: float | None = None`
  3. Modify `set_dirty()` (line 2802): start/restart timer instead of immediate save
  4. Add `_do_auto_save()` slot: save to `.tmp` file, atomic replace to `.json`
  5. Emit `auto_save_completed = QtCore.pyqtSignal(bool, str)`
  6. On load: detect `.tmp` recovery files → offer recovery
- **MIRROR**: SettingsController save timer (settings/controller.py:53-56); `save_labels()` at label_widget.py:4718; `AtomicWriter` at infrastructure/atomic_writer.py
- **IMPORTS**: `QtCore.QTimer`, `time`, `os`
- **GOTCHA**: Do NOT debounce initial save on file load. .tmp files must be cleaned up after successful atomic replace. On project open, check for orphaned .tmp files → prompt recovery.
- **VALIDATE**: Make shape change → timer starts. Second change within 500ms → timer restarted. 500ms elapsed → save called. Save failure → signal emitted with error. Rapid changes → only one save. Recovery file present → prompt on load.

---

### Task B2: Add atomic save + recovery to annotation_adapter

- **ACTION**: UPDATE `anylabeling/platform/application/annotation_adapter.py`
- **IMPLEMENT**:
  ```python
  def save_annotations_atomic(self, doc: AnnotationDocument, project_root: Path) -> bool:
      """Save annotations atomically: write .tmp → validate → replace."""
      target = project_root / "annotations" / f"{doc.asset_id}.json"
      tmp = target.with_suffix(".json.tmp")
      try:
          self.save_annotations(doc, str(tmp))
          loaded = self.load_annotations(str(tmp), doc.image_width, doc.image_height)
          if loaded.asset_id != doc.asset_id:
              raise ValueError("Validation failed: asset_id mismatch")
          os.replace(tmp, target)
          return True
      except Exception as exc:
          logger.exception(f"Atomic save failed for {doc.asset_id}")
          return False

  def find_recovery_files(self, project_root: Path) -> list[Path]:
      """Scan annotations/ for .tmp files → return recoverable paths."""
      ...

  def recover_from_tmp(self, tmp_path: Path) -> AnnotationDocument | None:
      """Attempt to load a .tmp recovery file. Returns None if unrecoverable."""
      ...
  ```
- **MIRROR**: `AtomicWriter.write_json()` at infrastructure/atomic_writer.py:1-50; Existing `save_annotations` in annotation_adapter.py
- **IMPORTS**: `os`, `pathlib.Path`
- **GOTCHA**: Named `save_annotations_atomic` to avoid breaking existing callers. Existing `save_annotations_for_asset()` should call the atomic version.
- **VALIDATE**: Save → .json created, no .tmp. Kill process mid-save → .tmp exists. Recovery scan → finds .tmp. Recover → valid AnnotationDocument loaded. Corrupted .tmp → recover returns None.

---

### Task B3: Wire auto-save status to LabelWorkspace status bar

- **ACTION**: UPDATE `anylabeling/views/platform/workspaces/label_workspace.py` and `anylabeling/views/platform/label_workspace.py`
- **IMPLEMENT**:
  1. Connect `LabelingWidget.auto_save_completed` → status bar update
  2. Add recovery check in `set_project_context()`
  3. Recovery prompt: non-modal banner showing "Found N unsaved changes from previous session. [Recover] [Discard]"
  4. Connect to `ErrorBanner` (from Phase 2b) for save failures
- **MIRROR**: `LabelWorkspace` structure (label_workspace.py:68-260); `ErrorBanner.show_warning()` from Phase 2b
- **IMPORTS**: `annotation_adapter`, `ErrorBanner`
- **GOTCHA**: Recovery prompt must appear BEFORE the labeling widget loads. If user chooses "Discard", delete .tmp files. If "Recover", load .tmp, restore, save to .json, delete .tmp.
- **VALIDATE**: Open project with .tmp files → recovery prompt shown. Click Recover → annotations restored. Click Discard → .tmp deleted. Save during editing → status shows "Saved".

---

### Task B4: Implement pixel-level mask brush tool

- **ACTION**: CREATE `anylabeling/views/labeling/widgets/mask_brush.py` and UPDATE `canvas.py`
- **IMPLEMENT**:
  ```python
  class MaskBrushTool:
      """Pixel-level mask painting tool.

      Operates on a QImage mask bitmap associated with the selected shape.
      Supports: brush (add), eraser (remove), undo per stroke.
      """

      def __init__(self, canvas: Canvas) -> None:
          self._canvas = canvas
          self._brush_size: int = 30
          self._mode: str = "brush"  # "brush" | "eraser"
          self._mask_image: QImage | None = None
          self._stroke_points: list[QPoint] = []
          self._undo_stack: list[QImage] = []

      def begin_stroke(self, canvas_pos: QPointF) -> None: ...
      def continue_stroke(self, canvas_pos: QPointF) -> None: ...
      def end_stroke(self) -> None: ...
      def undo_stroke(self) -> None: ...
      def _paint_circle(self, center: QPoint) -> None: ...
      def _render_overlay(self, painter: QPainter) -> None: ...
  ```
- **MIRROR**: `Canvas` brush drawing at canvas.py:678-694; `Shape` class at shape.py:21
- **IMPORTS**: `PyQt6.QtCore`, `PyQt6.QtGui` (QImage, QPainter, QPen, QBrush), `PyQt6.QtWidgets`
- **GOTCHA**: Mask resolution must match displayed image. Store mask as QImage in Shape.other_data["mask_bitmap"]. Brush cursor should be a circle at actual brush size.
- **VALIDATE**: Select polygon shape → activate mask brush → paint on canvas → mask overlay visible. Switch to eraser → paint → mask removed. Undo stroke → previous mask state restored. Zoom in/out → brush size in image coords constant.

---

### Task B5: Integrate mask brush into LabelingWidget toolbar

- **ACTION**: UPDATE `anylabeling/views/labeling/label_widget.py`
- **IMPLEMENT**:
  1. Add `actions.create_mask_brush_mode` action to toolbar
  2. Add mask brush toolbar: brush size slider (1–200px), eraser toggle, undo stroke button
  3. Add `toggle_mask_brush_mode()` method
  4. Wire canvas mouse events to MaskBrushTool for mask brush mode
  5. Mask brush only available when a polygon/segmentation shape is selected (not in CREATE mode)
- **MIRROR**: `toggle_brush_polygon_mode()` at label_widget.py:3475; Toolbar action setup at label_widget.py:1702
- **IMPORTS**: `MaskBrushTool`
- **GOTCHA**: Mask brush is an EDIT operation, not CREATE. Existing polygon brush preserved as separate CREATE tool. Mask brush toolbar only appears when polygon-type shape is selected.
- **VALIDATE**: Select polygon shape → mask brush toolbar appears. Paint on shape → mask updated. Change brush size → circle cursor size changes. Toggle eraser → removes mask. Undo stroke → reverts. Deselect shape → toolbar hides.

---

### Task B6: Add AI suggestion workflow

- **ACTION**: UPDATE `auto_labeling.py` and `label_widget.py`
- **IMPLEMENT**:
  1. Create `AnnotationSuggestion` dataclass in domain:
     ```python
     @dataclass(frozen=True)
     class AnnotationSuggestion:
         id: str
         asset_id: str
         model_id: str
         model_name: str
         confidence: float
         shapes: list[Shape]
         status: str  # "pending" | "accepted" | "rejected"
         created_at: str
     ```
  2. Modify `new_shapes_from_auto_labeling()` to store shapes as suggestions
  3. Render suggestions with dashed outline + confidence badge on canvas
  4. Add `accept_suggestion(id)`, `reject_suggestion(id)`, `accept_all_visible()`, `reject_all()` methods
  5. Add suggestion info panel to properties panel
- **MIRROR**: `AutoLabelingResult` at services/auto_labeling/types.py:7; `new_shapes_from_auto_labeling()` at label_widget.py:6655
- **IMPORTS**: `dataclasses.dataclass`, `uuid`, `datetime`
- **GOTCHA**: Suggestions survive asset switches (store in dict keyed by asset_id). Accepted shapes saved immediately. Rejected shapes recorded to prevent re-suggestion.
- **VALIDATE**: Run AI prediction → shapes appear with dashed outline + confidence. Click Accept → shape becomes normal. Click Reject → shape disappears. Switch assets and back → pending suggestions still visible.

---

### Task B7: Wire AI suggestion workflow to LabelWorkspace

- **ACTION**: UPDATE `anylabeling/views/platform/label_workspace.py`
- **IMPLEMENT**:
  1. Add suggestion info to properties panel: model/confidence/timestamp + Accept/Reject buttons
  2. Wire `ai_predict_requested` → run auto-labeling → shapes enter suggestion state
  3. Add "AI Suggestions (N pending)" label to asset list status
  4. Connect `LabelingWidget.suggestion_accepted` / `suggestion_rejected` signals
- **MIRROR**: Properties panel at label_workspace.py:186-206; AI toolbar at label_workspace.py:127-151
- **IMPORTS**: `AnnotationSuggestion`, existing auto_labeling imports
- **GOTCHA**: Model selection combo filtered by task family compatibility. Batch labeling runs as background job.
- **VALIDATE**: Select compatible model → click AI Predict → suggestions appear. Select suggestion → properties panel shows model info. Click Accept in panel → shape confirmed. Click AI Batch → background job processes all assets.

---

### TASK GROUP C: Sub-phase 3c — Tile Preview + Build Versions + Manifest + Leakage

---

### Task C1: Create TilePreviewWidget

- **ACTION**: CREATE `anylabeling/views/platform/widgets/tile_preview_widget.py`
- **IMPLEMENT**: QGraphicsView-based widget showing:
  - Source image (downsampled to fit) as background
  - Tile grid overlay (semi-transparent colored rectangles)
  - Color coding: green = has labels, gray = empty, orange = has truncated labels
  - Clickable tiles → emits `tile_selected(tile_id)`
  ```python
  class TilePreviewWidget(QtWidgets.QGraphicsView):
      tile_selected = QtCore.pyqtSignal(str)

      def __init__(self, parent=None):
          super().__init__(parent)
          self._scene = QtWidgets.QGraphicsScene(self)
          self.setScene(self._scene)

      def set_source_image(self, image_path: str) -> None: ...
      def set_tile_plan(self, plan: TilePlan) -> None: ...
      def set_tile_data(self, records, label_counts, truncated_counts) -> None: ...
      def highlight_tile(self, tile_id: str) -> None: ...
  ```
- **MIRROR**: `QWIDGET_PATTERN`; `QGraphicsView/QGraphicsScene` Qt pattern
- **IMPORTS**: `PyQt6.QtCore`, `PyQt6.QtGui`, `PyQt6.QtWidgets`, `TilePlan`, `TileRecord`
- **GOTCHA**: Large source images must be downsampled for preview. Tile grid coordinates in L0 space → transform to display coordinates. Color not sole differentiator — add text labels or patterns.
- **VALIDATE**: Set 4096×4096 image + 640×640 tile plan → grid renders correctly. Click tile → signal emitted with correct tile_id.

---

### Task C2: Create TileInspectorPanel

- **ACTION**: CREATE `anylabeling/views/platform/widgets/tile_inspector_panel.py`
- **IMPLEMENT**: Per-tile detail panel showing object fragments with area % and truncation status.
  ```python
  class TileInspectorPanel(QtWidgets.QWidget):
      accept_tile = QtCore.pyqtSignal(str)
      flag_tile = QtCore.pyqtSignal(str, str)

      def set_tile(self, tile: TileRecord, objects: list[AnnotationObject], source_image_size: tuple) -> None:
          """Display tile details and split annotation objects."""
          ...
  ```
- **MIRROR**: `QWIDGET_PATTERN`; Properties panel at label_workspace.py:186-206
- **IMPORTS**: `PyQt6.QtCore`, `PyQt6.QtWidgets`, `TileRecord`, `AnnotationObject`, `TilePlan`, label splitters
- **GOTCHA**: To compute per-tile objects, run actual label splitter logic from `platform/tiling/label_splitters/`. This is read-only preview (no PNG writing). Splitter results computed on-the-fly when tile selected.
- **VALIDATE**: Select tile → object list populated. Truncated object shows ⚠. Fully contained object shows ✓.

---

### Task C3: Integrate tile preview + inspector into PreprocessWorkspace

- **ACTION**: UPDATE `anylabeling/views/platform/preprocess_workspace.py`
- **IMPLEMENT**:
  1. Add "Preview" tab with `TilePreviewWidget` + `TileInspectorPanel` side-by-side
  2. Tab enabled when `_large_images` list is non-empty
  3. User selects large image → preview renders
  4. Tile config changes → preview updates after 300ms debounce
- **MIRROR**: Existing `PreprocessWorkspace` tab structure (preprocess_workspace.py:40-203)
- **IMPORTS**: `TilePreviewWidget`, `TileInspectorPanel`, `TilePlanner`, label splitters, `LargeImageSource`
- **GOTCHA**: Preview computation is CPU-heavy — run in background thread. Cache tile data per image+config. If no large images, preview tab shows informational message.
- **VALIDATE**: Select large image → grid overlay renders. Change tile width → preview updates after debounce. Click tile → inspector shows fragments.

---

### Task C4: Add build history to PreprocessWorkspace

- **ACTION**: UPDATE `anylabeling/views/platform/preprocess_workspace.py`
- **IMPLEMENT**:
  1. Add "History" tab listing all past builds from `dataset_builds/` directory
  2. Each row: build ID, date, asset count, tile count, status, actions
  3. Actions: "View Details", "Use Config", "Open Directory"
  4. Load from filesystem: scan `dataset_builds/` for `build.json` files
- **MIRROR**: `QWIDGET_PATTERN`; `DataWorkspace` for table layout pattern
- **IMPORTS**: `json`, `pathlib.Path`, `QtWidgets.QTableWidget`
- **GOTCHA**: Build history is additive — never delete old builds. Failed builds (no `_READY` marker) included with error info. "Use Config" reads build.json and populates current settings.
- **VALIDATE**: After build → history tab shows new entry. Failed build → shows with error status. "Use Config" → tile settings populated.

---

### Task C5: Add manifest integrity verification

- **ACTION**: UPDATE `anylabeling/platform/infrastructure/manifest_store.py` and `dataset_build_service.py`
- **IMPLEMENT**:
  ```python
  # manifest_store.py:
  def compute_manifest_hash(path: Path) -> str:
      """Compute SHA-256 of a JSONL file (deterministic, line-by-line)."""
      ...

  def verify_manifest_hash(path: Path, expected_hash: str) -> bool:
      """Verify manifest integrity against expected hash."""
      ...

  # dataset_build_service.py:
  @staticmethod
  def verify_build_integrity(build_dir: Path) -> ManifestIntegrityReport:
      """Verify all manifests in a build directory are intact."""
      ...
  ```
- **MIRROR**: `compute_sha256()` at infrastructure/checksum.py; `ManifestStore` at manifest_store.py:1-75
- **IMPORTS**: `hashlib`, `pathlib.Path`
- **GOTCHA**: Hash raw bytes as-written (order is significant). Hash stored in build.json at build time. Report all mismatches.
- **VALIDATE**: Build dataset → build.json contains hashes. Verify → matches. Corrupt one line → verify fails.

---

### Task C6: Add data leakage detection

- **ACTION**: UPDATE `dataset_build_service.py` and `dataset.py`
- **IMPLEMENT**:
  ```python
  # dataset.py:
  @dataclass(frozen=True)
  class LeakageReport:
      build_id: str
      split_strategy: str
      has_cross_split_groups: bool
      cross_split_groups: list[str]
      per_class_distribution: dict[str, dict[str, int]]
      class_imbalance_warnings: list[str]
      passed: bool

  # dataset_build_service.py:
  def detect_leakage(self, build_dir: Path, task_spec: TaskSpec) -> LeakageReport:
      """Analyze a completed build for data leakage and class imbalance."""
      ...
  ```
- **MIRROR**: `_assign_splits()` at dataset_build_service.py:316
- **IMPORTS**: `json`, `pathlib.Path`, `collections.Counter`
- **GOTCHA**: Post-build analysis (does not block build). Imbalance threshold: any class with <max(1, 1% of split) samples. Report is informational.
- **VALIDATE**: Build with group_by_group_id → no cross-split leakage. Build with random_by_asset + same group → flags leakage. Build with rare class → shows imbalance warning.

---

### Task C7: Wire build history, integrity, and leakage to WorkbenchWindow

- **ACTION**: UPDATE `anylabeling/views/platform/workbench_window.py`
- **IMPLEMENT**:
  1. After build completes: run `detect_leakage()` → display report inline
  2. Compute and store manifest hashes in build.json
  3. On project open: run `verify_build_integrity()` for all past builds → report via ErrorBanner
  4. Wire build history tab in PreprocessWorkspace
- **MIRROR**: `_on_preprocess_build_requested()` at workbench_window.py:910-990; `ErrorBanner` from Phase 2b
- **IMPORTS**: `LeakageReport`, `ManifestIntegrityReport`, `verify_build_integrity`, `detect_leakage`
- **GOTCHA**: Integrity verification on project open is non-blocking (background thread). If corruption detected, show ErrorBanner.
- **VALIDATE**: Build completes → leakage report displayed. Corrupted manifest → ErrorBanner on project open.

---

### Task C8: Write comprehensive tests

- **ACTION**: CREATE 11 test files:
  1. `tests/platform/application/test_import_precheck.py`
  2. `tests/platform/application/test_asset_repository_extended.py`
  3. `tests/platform/application/test_manifest_integrity.py`
  4. `tests/platform/application/test_leakage_detection.py`
  5. `tests/views/platform/widgets/test_asset_list_model.py`
  6. `tests/views/platform/widgets/test_asset_filter.py`
  7. `tests/views/platform/widgets/test_tile_preview.py`
  8. `tests/views/platform/test_import_workspace.py`
  9. `tests/views/labeling/test_mask_brush.py`
  10. `tests/views/labeling/test_auto_save.py`
  11. `tests/views/labeling/test_ai_suggestions.py`
- **MIRROR**: `TEST_STRUCTURE` from tests/views/platform/test_workbench_shell.py and tests/platform/application/test_import_service.py
- **GOTCHA**: GUI tests need `skip_without_display`. Mask brush tests need QApplication. Tile preview tests use MemoryImageSource. Auto-save tests use tmp_path fixtures.
- **VALIDATE**: `pytest tests/platform/application/ tests/views/platform/widgets/ tests/views/labeling/ -v -m "not slow"`

---

## Testing Strategy

### Unit Tests

| Test | Input | Expected Output | Edge Case? |
|---|---|---|---|
| PrecheckResult: valid images | 3 valid JPEG paths | ok_count=3, damaged=0, unsupported=0 | No |
| PrecheckResult: mixed files | 2 valid + 1 .txt + 1 corrupt | ok=2, damaged=1, unsupported=1 | Yes |
| ImportService.precheck() | Directory with 100 images | Returns PrecheckResult with correct counts | No |
| ImportService with progress callback | 50 files + callback | Callback called 50 times with correct args | No |
| ImportService with cancel | Cancel after 10/50 files | ImportCancelledError, partial cleanup | Yes |
| AssetListModel.rowCount | Repository with 500 assets | 500 | No |
| AssetListModel.fetchMore | Batch size 100, 250 total | 3 fetchMore calls, all_loaded=True after 3rd | No |
| AssetFilterProxyModel: combined | Status + group filter | Intersection of both | Yes |
| AssetRepository.get_asset | Known asset path | Returns Asset with correct dims | No |
| AssetRepository.get_stats | Repository with known assets | Correct counts by status/group/ext | No |
| Auto-save debounce | 3 rapid changes within 500ms | Save called once | Yes |
| Auto-save atomic | Save during process kill simulation | .tmp file exists, .json unchanged | Yes |
| Recovery detection | .tmp file in annotations/ | find_recovery_files returns path | No |
| Recovery corrupted | Invalid .tmp content | recover_from_tmp returns None | Yes |
| Mask brush: paint stroke | Brush size 30, line from (0,0) to (100,0) | Mask bitmap has painted pixels along line | No |
| Mask brush: eraser | Paint then erase over same area | Mask pixels removed | No |
| Mask brush: undo | Paint stroke → undo | Mask reverts to pre-stroke state | No |
| AI suggestion: create | Model predicts 3 shapes | 3 AnnotationSuggestions with status="pending" | No |
| AI suggestion: accept | Accept 1 of 3 suggestions | Shape added to canvas, suggestion removed | No |
| AI suggestion: reject | Reject 1 suggestion | Suggestion removed, shape not added | No |
| TilePreviewWidget: grid | 4096×4096 image, 640×640 tile | 7×7=49 tiles rendered | No |
| TilePreviewWidget: click | Click tile at row=2, col=3 | tile_selected signal with correct tile_id | No |
| TileInspectorPanel: truncation | Object with 30% visibility | ⚠ indicator displayed | Yes |
| Manifest integrity: verify | Unmodified manifest | Hash matches | No |
| Manifest integrity: tamper | One line modified | Hash mismatch detected | Yes |
| Leakage detection: clean | group_by_group_id split | passed=True, no cross-split groups | No |
| Leakage detection: leak | random_by_asset, same group in train+val | passed=False, cross_split_groups populated | Yes |
| Leakage detection: imbalance | Rare class <1% in val | class_imbalance_warnings populated | Yes |

### Edge Cases Checklist
- [x] Empty source list → PrecheckResult with all zeros
- [x] All files damaged → PrecheckResult with ok_count=0
- [x] Import with no precheck → import_images works standalone (backward compat)
- [x] Asset repository with empty assets/ → all methods return empty/zero
- [x] Model with 50k assets → fetchMore batches correctly, no UI freeze
- [x] Rapid filter changes → only last filter applied (no race condition)
- [x] Auto-save on read-only directory → save fails gracefully, recovery copy created
- [x] Auto-save during asset switch → current asset saved before switch
- [x] Mask brush on non-polygon shape → tool disabled
- [x] Mask brush bitmap larger than image → clamp to image bounds
- [x] AI suggestion with zero confidence shapes → still shown as suggestions
- [x] Tile preview with 1×1 tile → single tile grid
- [x] Tile preview with tile larger than image → single tile covering whole image
- [x] Build integrity check on missing build directory → graceful error
- [x] Leakage detection with no annotations → empty report, no crash

---

## Validation Commands

### Static Analysis
```bash
python -c "from anylabeling.platform.domain.import_config import PrecheckResult; print('OK')"
python -c "from anylabeling.views.platform.widgets.asset_list_model import AssetListModel; print('OK')"
python -c "from anylabeling.views.platform.widgets.asset_filter_bar import AssetFilterBar, AssetFilterProxyModel; print('OK')"
python -c "from anylabeling.views.platform.widgets.tile_preview_widget import TilePreviewWidget; print('OK')"
python -c "from anylabeling.views.platform.workspaces.import_workspace import ImportWorkspace; print('OK')"
python -c "from anylabeling.views.platform.view_models.import_vm import ImportViewModel; print('OK')"
python -c "from anylabeling.views.labeling.widgets.mask_brush import MaskBrushTool; print('OK')"
python -c "from anylabeling.platform.domain.dataset import LeakageReport, ManifestIntegrityReport; print('OK')"
```
EXPECT: All imports succeed, no ImportError

### Lint Check
```bash
flake8 anylabeling/views/platform/widgets/
flake8 anylabeling/views/platform/workspaces/import_workspace.py
flake8 anylabeling/views/labeling/widgets/mask_brush.py
flake8 anylabeling/platform/application/import_service.py
flake8 anylabeling/platform/application/asset_repository.py
```
EXPECT: Zero lint errors (max complexity 18)

### Unit Tests (New)
```bash
pytest tests/platform/application/test_import_precheck.py -v
pytest tests/platform/application/test_asset_repository_extended.py -v
pytest tests/platform/application/test_manifest_integrity.py -v
pytest tests/platform/application/test_leakage_detection.py -v
pytest tests/views/platform/widgets/ -v
pytest tests/views/labeling/test_mask_brush.py -v
pytest tests/views/labeling/test_auto_save.py -v
pytest tests/views/labeling/test_ai_suggestions.py -v
```
EXPECT: All tests pass

### Full Test Suite (Regression)
```bash
pytest tests/ -x -m "not slow"
```
EXPECT: No regressions from existing ~884 tests

### Performance Smoke Test
```bash
python -c "
from pathlib import Path
from anylabeling.platform.application.asset_repository import AssetRepository
import time, tempfile
with tempfile.TemporaryDirectory() as d:
    assets = Path(d) / 'assets'; assets.mkdir()
    for i in range(10000):
        (assets / f'img_{i:05d}.jpg').touch()
    repo = AssetRepository(d)
    t0 = time.perf_counter()
    ids = repo.scan_assets()
    t1 = time.perf_counter()
    print(f'Scanned {len(ids)} assets in {(t1-t0)*1000:.1f}ms')
    assert len(ids) == 10000
    assert (t1 - t0) < 2.0
    print('PASS')
"
```
EXPECT: 10k assets scanned in <2 seconds

### Manual Validation
- [ ] Import 1000 images with 5 damaged → precheck shows 995 valid + 5 damaged
- [ ] Exclude damaged files → import proceeds with 995
- [ ] Import completes → asset list shows 995 assets via model/view
- [ ] Scroll asset list to bottom → fetchMore loads remaining batches
- [ ] Filter by "unannotated" → only unannotated shown
- [ ] Annotate 5 images → auto-save triggers after 500ms idle
- [ ] Kill app during edit → restart → recovery prompt appears
- [ ] Select polygon shape → mask brush toolbar visible
- [ ] Paint on shape → mask bitmap updated
- [ ] Run AI prediction → dashed shapes appear with confidence
- [ ] Accept suggestion → shape becomes normal, saved
- [ ] Import 32k×32k TIFF → tile preview shows grid overlay
- [ ] Click tile → inspector shows label fragments
- [ ] Build dataset → build appears in history tab
- [ ] Leakage report displayed after build
- [ ] Manifest integrity verified on project open

---

## Acceptance Criteria

### Sub-phase 3a
- [ ] Import precheck separates scan from copy; user reviews issues before any data is moved
- [ ] Import progress callback fires for each file; cancel stops import cleanly
- [ ] AssetRepository is the single source of truth for asset queries across all pages
- [ ] Asset list uses QAbstractListModel + QListView; 10k assets scroll smoothly
- [ ] Filter bar supports status, group, label, and search filters
- [ ] All 5 inline scan implementations replaced with AssetRepository calls
- [ ] Extension set unified between ImportService and AssetRepository

### Sub-phase 3b
- [ ] Auto-save uses 500ms debounce timer; multiple rapid edits produce single save
- [ ] Atomic save (tmp → validate → replace) prevents corruption on crash
- [ ] Recovery prompt appears on project open if .tmp files exist
- [ ] Mask brush tool supports pixel-level painting and erasing on polygon shapes
- [ ] Mask brush undo per stroke
- [ ] AI predictions enter "pending" suggestion state with dashed rendering + confidence
- [ ] Accept/reject workflow: individual, all visible, batch operations
- [ ] AI suggestion info (model, confidence, timestamp) visible in properties panel

### Sub-phase 3c
- [ ] Tile preview shows visual grid overlay on source image
- [ ] Tiles color-coded: has labels, empty, has truncated labels
- [ ] Tile inspector shows per-tile label fragments with area % and truncation warnings
- [ ] Build history tab lists all past builds with status and actions
- [ ] Manifest integrity hashes computed at build time, verified on project open
- [ ] Leakage detection identifies cross-split groups and class imbalance
- [ ] Leakage report displayed inline after build completion
- [ ] Corrupted manifests flagged via ErrorBanner

### Cross-cutting
- [ ] All tasks completed
- [ ] All validation commands pass
- [ ] Tests written and passing (11 test files)
- [ ] No flake8 errors (max complexity 18)
- [ ] No regression in existing ~884 tests
- [ ] No PyQt6 imports in application/domain layers
- [ ] No Ultralytics imports in application/domain layers

## Completion Checklist
- [ ] Code follows discovered patterns (SERVICE_PATTERN, QWIDGET_PATTERN, VIEWMODEL_PATTERN, DOMAIN_DATACLASS)
- [ ] Error handling matches codebase style (logger.exception + user-facing message)
- [ ] Logging follows codebase conventions (logging.getLogger(__name__))
- [ ] Tests follow test patterns (pytest fixtures, skip_without_display, AAA)
- [ ] No hardcoded values (use style.py constants or domain defaults)
- [ ] Domain models use @dataclass(frozen=True) where possible
- [ ] All paths use pathlib.Path
- [ ] All I/O uses UTF-8
- [ ] Atomic writes for all persistent state
- [ ] AssetRepository extension set matches ImportService
- [ ] No unnecessary scope additions
- [ ] Self-contained — no questions needed during implementation

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| AssetRepository integration breaks backward compat with existing page scans | Medium | High | Add new methods alongside existing ones; deprecate old scan paths; update callers incrementally |
| QAbstractListModel performance worse than QListWidget for <1000 assets | Low | Low | Model/view is strictly better at scale. Benchmark both approaches. |
| Mask brush bitmap memory: 32k×32k mask = 1 GB | Medium | Medium | Store mask at working resolution, not L0. Upsample on save. Limit brush to selected region. |
| Tile preview computation too slow for large images + many objects | Medium | Medium | Run in background thread; cache results per image+config combination |
| Auto-save debounce conflicts with explicit "Save" action | Low | Low | Explicit save cancels pending timer and saves immediately |
| Leakage detection O(n²) with many assets | Low | Medium | Use set operations for group membership check; batch label parsing |
| Phase 2b not yet complete → ProjectSession may not be available | High | Medium | Phase 3 services can be wired directly; wrapped by ProjectSession later |

## Decisions Log

| Decision | Choice | Alternatives | Rationale |
|---|---|---|---|
| Asset list tech | QAbstractListModel + QListView | (A) Keep QListWidget; (B) QTableView; (C) QAbstractListModel | (C) is Qt's documented pattern for large lists. Model/view separates data from presentation. |
| Mask storage | QImage bitmap in Shape.other_data | (A) Convert to polygon contour; (B) Run-length encoding; (C) QImage bitmap | (A) is lossy; (B) adds complexity; (C) simple, matches existing QImage rendering |
| Import precheck | New PrecheckResult dataclass + precheck() method | (A) Extend ImportResult; (B) Separate PrecheckService | Precheck is natural part of ImportService. New dataclass avoids overloading ImportResult. |
| AI suggestions | New AnnotationSuggestion domain model | (A) Reuse AnnotationObject with status flag; (B) Separate suggestion model | (B) keeps suggestion lifecycle cleanly separated from annotation data. |
| Recovery mechanism | .tmp files detected on project open | (A) In-memory undo log; (B) SQLite WAL; (C) .tmp files | (C) simplest, matches existing AtomicWriter pattern, survives process kill. |
| Tile preview rendering | QGraphicsView + QGraphicsRectItem overlay | (A) Custom paintEvent; (B) QGraphicsView; (C) Matplotlib | (B) provides built-in zoom/pan, item selection, tooltips. |
| Leakage detection timing | Post-build analysis (non-blocking) | (A) Pre-build check; (B) During-build enforcement | Post-build allows user review. Leakage is a quality warning, not a blocker. |

## Notes

- **Phase 2b dependency**: This plan assumes Phase 2b is complete (ProjectSession, ErrorBanner, TaskCenterDrawer available). If not, direct service wiring from current WorkbenchWindow can be used as fallback.
- **AssetRepository centralization**: The biggest architectural change in 3a is making AssetRepository the single source of truth. The repository already exists with the right API shape — it just needs integration and a few new methods.
- **Mask brush scope**: Edit tool for polygon shapes (instance segmentation masks). Does NOT support semantic segmentation (pixel-level classification of entire image).
- **AI suggestion persistence**: Suggestions are in-memory and lost on app close. Persistent suggestions deferred to future phase.
- **Tile preview scope**: Uses existing TilePlanner and label splitters. Read-only preview — no PNG materialization until build.
- **Performance targets**: 10k assets in 5s interactive, asset filtering in 300ms, page navigation in 200ms.
- **Incremental delivery**: Sub-phases can be delivered incrementally — 3a first (unblocks data management), then 3b (labeling quality), then 3c (build verification).
- **Test file count**: 11 new test files = ~40–60 new test functions.
