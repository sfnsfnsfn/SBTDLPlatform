# Label Workspace Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建 LabelWorkspace 原生页面，将 LabelingWidget+Canvas 完整嵌入平台流水线，通过 AnnotationAdapter 桥接领域模型，实现任务驱动的标注工具筛选。

**Architecture:** 新增 LabelWorkspace（QWidget 页面）+ AnnotationAdapter（薄桥接层），修改 WorkbenchWindow 页面索引对齐 NavigationBar。原有 Canvas/Camera2D/Shape/LabelingWidget 一行不改。

**Tech Stack:** Python 3.x, PyQt6, XLabelCodec (AnnotationService)

**Source Spec:** `docs/superpowers/specs/2026-06-07-label-workspace-design.md`

---

## Key Code Context (from existing codebase)

| Item | Location | Detail |
|------|----------|--------|
| LabelingWidget.project_context | `label_widget.py:140` | Already supports `set_project_context(dict)` |
| LabelingWidget.actions | `label_widget.py:1702` | `utils.Struct` — QAction objects for all tools |
| Canvas signals | `canvas.py:64-67` | `shape_moved`, `selection_changed(list)`, `new_shape` |
| XLabelCodec | `annotation_service.py:111` | `load_annotations()` / `save_annotations()` |
| NavigationBar indices | `navigation_bar.py:17-22` | DATA=0,LABEL=1,TRAIN=2,EVALUATE=3,INFER=4,EXPORT=5 |
| Shape class | `shape.py:21` | `.shape_type`, `.points`, `.label`, `.group_id` |
| Canvas._create_mode | `canvas.py:83` | Current drawing mode string ("rectangle", "polygon", etc.) |

---

### Task 1: AnnotationAdapter — Bridge Module

**Files:**
- Create: `anylabeling/platform/application/annotation_adapter.py`

- [ ] **Step 1: Write the module with all mapping tables and conversion functions**

```python
"""AnnotationAdapter — Shape ↔ AnnotationObject bridge.

Connects the existing `views/labeling/` annotation UI with the platform
domain model without modifying either side.
"""
from __future__ import annotations

import uuid
from pathlib import Path


# ---------------------------------------------------------------------------
# Task family → allowed Canvas shape_types
# ---------------------------------------------------------------------------
_FAMILY_SHAPE_TYPE_MAP: dict[str, list[str]] = {
    "classification": [],
    "detection_hbb": ["rectangle"],
    "detection_obb": ["rotation"],
    "instance_segmentation": ["polygon"],
    "pose": ["point"],
    "semantic_segmentation": ["polygon"],
    "anomaly": ["rectangle", "polygon"],
}


def get_allowed_shape_types(family: str) -> list[str]:
    """Return Canvas shape_type strings allowed for *family*.

    Returns empty list for families that use image_labels only (e.g. classification).
    """
    return list(_FAMILY_SHAPE_TYPE_MAP.get(family, []))


# ---------------------------------------------------------------------------
# Shape type ↔ geometry_type mapping
# ---------------------------------------------------------------------------
_SHAPE_TO_GEOMETRY: dict[str, str] = {
    "rectangle": "bbox_xyxy",
    "rotation": "obb_polygon",
    "polygon": "polygon",
    "point": "keypoints",
}
_GEOMETRY_TO_SHAPE: dict[str, str] = {
    v: k for k, v in _SHAPE_TO_GEOMETRY.items()
}


def shape_type_to_geometry_type(shape_type: str) -> str:
    """Map Canvas shape_type to platform geometry_type. Unknown → "polygon"."""
    return _SHAPE_TO_GEOMETRY.get(shape_type, "polygon")


def geometry_type_to_shape_type(geometry_type: str) -> str:
    """Map platform geometry_type to Canvas shape_type. Unknown → "polygon"."""
    return _GEOMETRY_TO_SHAPE.get(geometry_type, "polygon")


# ---------------------------------------------------------------------------
# Shape ↔ AnnotationDocument conversion
# ---------------------------------------------------------------------------

def shapes_to_annotation_doc(
    shapes: list,
    asset_id: str,
    image_width: int,
    image_height: int,
    label_name_to_id: dict[str, int],
) -> "AnnotationDocument":
    """Convert LabelingWidget Shape objects → AnnotationDocument."""
    from anylabeling.platform.domain.annotation import (
        AnnotationDocument,
        AnnotationObject,
    )

    objects: list[AnnotationObject] = []
    for shape in shapes:
        shape_type = getattr(shape, "shape_type", "polygon")
        label_name = getattr(shape, "label", "")
        label_id = label_name_to_id.get(label_name, -1)

        geometry_type = shape_type_to_geometry_type(shape_type)

        points_raw = getattr(shape, "points", [])
        if geometry_type == "bbox_xyxy":
            xs = [p.x() for p in points_raw]
            ys = [p.y() for p in points_raw]
            if xs and ys:
                geometry = (min(xs), min(ys), max(xs), max(ys))
            else:
                geometry = (0.0, 0.0, 0.0, 0.0)
        elif geometry_type == "keypoints":
            geometry = [(p.x(), p.y(), 2) for p in points_raw]
        else:
            geometry = [(p.x(), p.y()) for p in points_raw]

        obj = AnnotationObject(
            id=str(uuid.uuid4()),
            label_id=label_id,
            geometry_type=geometry_type,
            geometry=geometry,
            attributes={
                "label": label_name,
                "difficult": getattr(shape, "difficult", False),
                "group_id": getattr(shape, "group_id"),
                "description": getattr(shape, "description", ""),
            },
        )
        objects.append(obj)

    return AnnotationDocument(
        asset_id=asset_id,
        image_width=image_width,
        image_height=image_height,
        objects=objects,
    )


def annotation_doc_to_shapes(doc: "AnnotationDocument") -> list[dict]:
    """Convert AnnotationDocument → list of Shape-compatible dicts.

    Each dict has: shape_type, label, points, group_id, difficult, description.
    """
    result: list[dict] = []
    for obj in doc.objects:
        shape_type = geometry_type_to_shape_type(obj.geometry_type)
        geom = obj.geometry

        if obj.geometry_type == "bbox_xyxy" and isinstance(geom, (tuple, list)) and len(geom) == 4:
            x1, y1, x2, y2 = float(geom[0]), float(geom[1]), float(geom[2]), float(geom[3])
            points = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        elif obj.geometry_type == "keypoints" and isinstance(geom, list):
            points = [(float(p[0]), float(p[1])) for p in geom]
        elif isinstance(geom, list):
            points = [(float(p[0]), float(p[1])) for p in geom]
        else:
            points = []

        result.append({
            "shape_type": shape_type,
            "label": obj.attributes.get("label", ""),
            "points": points,
            "group_id": obj.attributes.get("group_id"),
            "difficult": obj.attributes.get("difficult", False),
            "description": obj.attributes.get("description", ""),
        })

    return result


# ---------------------------------------------------------------------------
# Convenience load/save helpers
# ---------------------------------------------------------------------------

def load_annotations_for_asset(
    asset_path: str | Path,
    project_path: str | Path,
) -> list[dict] | None:
    """Load annotations for an asset. Returns Shape-compatible dicts or None."""
    asset_path = Path(asset_path)
    project_path = Path(project_path)
    ann_path = project_path / "annotations" / f"{asset_path.stem}.json"

    if not ann_path.exists():
        return None

    import cv2
    img = cv2.imread(str(asset_path))
    if img is None:
        return None
    h, w = img.shape[:2]

    from anylabeling.platform.application.annotation_service import XLabelCodec
    codec = XLabelCodec()
    doc = codec.load_annotations(ann_path, w, h)
    return annotation_doc_to_shapes(doc)


def save_annotations_for_asset(
    asset_path: str | Path,
    shapes: list,
    project_path: str | Path,
    label_name_to_id: dict[str, int],
) -> None:
    """Save annotations for an asset to project/annotations/{asset_id}.json."""
    asset_path = Path(asset_path)
    project_path = Path(project_path)
    ann_dir = project_path / "annotations"
    ann_dir.mkdir(parents=True, exist_ok=True)
    ann_path = ann_dir / f"{asset_path.stem}.json"

    import cv2
    img = cv2.imread(str(asset_path))
    if img is None:
        return
    h, w = img.shape[:2]

    doc = shapes_to_annotation_doc(shapes, asset_path.stem, w, h, label_name_to_id)

    from anylabeling.platform.application.annotation_service import XLabelCodec
    codec = XLabelCodec()
    codec.save_annotations(doc, ann_path)


__all__ = [
    "get_allowed_shape_types",
    "shape_type_to_geometry_type",
    "geometry_type_to_shape_type",
    "shapes_to_annotation_doc",
    "annotation_doc_to_shapes",
    "load_annotations_for_asset",
    "save_annotations_for_asset",
]
```

- [ ] **Step 2: Verify syntax**

Run: `python -c "import ast; ast.parse(open('anylabeling/platform/application/annotation_adapter.py').read()); print('OK')"`
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add anylabeling/platform/application/annotation_adapter.py
git commit -m "feat: add AnnotationAdapter — Shape ↔ AnnotationObject bridge layer

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: AnnotationAdapter Unit Tests

**Files:**
- Create: `tests/platform/application/test_annotation_adapter.py`

- [ ] **Step 1: Write tests**

```python
"""Tests for annotation_adapter."""
import pytest
from anylabeling.platform.application.annotation_adapter import (
    get_allowed_shape_types,
    shape_type_to_geometry_type,
    geometry_type_to_shape_type,
    shapes_to_annotation_doc,
    annotation_doc_to_shapes,
)
from anylabeling.platform.domain.annotation import AnnotationDocument, AnnotationObject


class TestTaskFamilyMapping:
    def test_detection_hbb_allows_rectangle(self):
        assert get_allowed_shape_types("detection_hbb") == ["rectangle"]

    def test_detection_obb_allows_rotation(self):
        assert get_allowed_shape_types("detection_obb") == ["rotation"]

    def test_instance_segmentation_allows_polygon(self):
        assert get_allowed_shape_types("instance_segmentation") == ["polygon"]

    def test_pose_allows_point(self):
        assert get_allowed_shape_types("pose") == ["point"]

    def test_classification_allows_nothing(self):
        assert get_allowed_shape_types("classification") == []

    def test_anomaly_allows_rect_and_poly(self):
        assert get_allowed_shape_types("anomaly") == ["rectangle", "polygon"]

    def test_unknown_family_empty(self):
        assert get_allowed_shape_types("nonexistent") == []


class TestShapeTypeMapping:
    def test_rectangle_to_bbox_xyxy(self):
        assert shape_type_to_geometry_type("rectangle") == "bbox_xyxy"

    def test_rotation_to_obb_polygon(self):
        assert shape_type_to_geometry_type("rotation") == "obb_polygon"

    def test_point_to_keypoints(self):
        assert shape_type_to_geometry_type("point") == "keypoints"

    def test_polygon_roundtrip(self):
        assert shape_type_to_geometry_type("polygon") == "polygon"

    def test_bbox_xyxy_reverse(self):
        assert geometry_type_to_shape_type("bbox_xyxy") == "rectangle"

    def test_obb_polygon_reverse(self):
        assert geometry_type_to_shape_type("obb_polygon") == "rotation"

    def test_unknown_defaults_to_polygon(self):
        assert shape_type_to_geometry_type("cuboid") == "polygon"


class MockQPointF:
    def __init__(self, x, y):
        self._x = float(x)
        self._y = float(y)
    def x(self):
        return self._x
    def y(self):
        return self._y


class MockShape:
    def __init__(self, shape_type, label, points, group_id=None,
                 difficult=False, description=""):
        self.shape_type = shape_type
        self.label = label
        self.points = points
        self.group_id = group_id
        self.difficult = difficult
        self.description = description


class TestConversionRoundtrip:
    def test_rectangle(self):
        shapes = [
            MockShape("rectangle", "person",
                      [MockQPointF(10, 20), MockQPointF(100, 20),
                       MockQPointF(100, 200), MockQPointF(10, 200)])
        ]
        doc = shapes_to_annotation_doc(shapes, "img1", 640, 480, {"person": 0})
        assert len(doc.objects) == 1
        assert doc.objects[0].geometry_type == "bbox_xyxy"
        assert doc.objects[0].geometry == (10, 20, 100, 200)

        result = annotation_doc_to_shapes(doc)
        assert len(result) == 1
        assert result[0]["shape_type"] == "rectangle"
        assert result[0]["label"] == "person"
        assert result[0]["points"] == [(10, 20), (100, 20), (100, 200), (10, 200)]

    def test_polygon(self):
        shapes = [
            MockShape("polygon", "region",
                      [MockQPointF(1, 2), MockQPointF(3, 4), MockQPointF(5, 6)])
        ]
        doc = shapes_to_annotation_doc(shapes, "img2", 100, 100, {"region": 0})
        assert doc.objects[0].geometry_type == "polygon"
        assert doc.objects[0].geometry == [(1, 2), (3, 4), (5, 6)]

    def test_empty_shapes(self):
        doc = shapes_to_annotation_doc([], "img3", 100, 100, {})
        assert doc.objects == []

    def test_empty_doc_roundtrip(self):
        doc = AnnotationDocument(asset_id="img4", image_width=100, image_height=100, objects=[])
        result = annotation_doc_to_shapes(doc)
        assert result == []
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/platform/application/test_annotation_adapter.py -v`
Expected: all tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/platform/application/test_annotation_adapter.py
git commit -m "test: add AnnotationAdapter unit tests

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: LabelWorkspace — Page Widget

**Files:**
- Create: `anylabeling/views/platform/label_workspace.py`

- [ ] **Step 1: Write the complete LabelWorkspace module**

```python
"""LabelWorkspace — platform-native labeling page with task-aware tool filtering."""
from __future__ import annotations

import logging
from pathlib import Path

from PyQt6 import QtCore, QtWidgets

from anylabeling.views.platform.i18n import tr
from anylabeling.views.platform.style import (
    FONT_FAMILY,
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
    get_list_widget_style,
)
from anylabeling.views.labeling.utils.theme import get_theme

logger = logging.getLogger(__name__)

# LabelingWidget action name → Canvas shape_type
_ACTION_SHAPE_TYPE_MAP: dict[str, str] = {
    "create_mode":            "polygon",
    "create_rectangle_mode":  "rectangle",
    "create_rotation_mode":   "rotation",
    "create_point_mode":      "point",
    "create_line_mode":       "line",
    "create_line_strip_mode": "linestrip",
    "create_circle_mode":     "circle",
    "create_cuboid_mode":     "cuboid",
    "create_quadrilateral_mode": "quadrilateral",
}


class AssetListItem(QtWidgets.QListWidgetItem):
    """List item representing an image asset with annotation status."""

    STATUS_UNANNOTATED = "unannotated"
    STATUS_PARTIAL = "partial"
    STATUS_COMPLETE = "complete"

    def __init__(self, asset_path: str, status: str = STATUS_UNANNOTATED):
        super().__init__()
        self.asset_path = asset_path
        self.annotation_status = status
        self._refresh_display()

    def _refresh_display(self):
        icons = {
            self.STATUS_COMPLETE: "✅",
            self.STATUS_PARTIAL: "🔄",
            self.STATUS_UNANNOTATED: "⭕",
        }
        icon = icons.get(self.annotation_status, "⭕")
        self.setText(f"{icon} {Path(self.asset_path).name}")
        self.setData(QtCore.Qt.ItemDataRole.UserRole, self.asset_path)

    def set_status(self, status: str):
        self.annotation_status = status
        self._refresh_display()


class LabelWorkspace(QtWidgets.QWidget):
    """Platform-native labeling workspace.

    Embeds the existing LabelingWidget + Canvas unchanged, adding:
    - Asset list with annotation status
    - Task-aware tool filtering (hides incompatible shape tools)
    - Auto-save to project/annotations/
    - Inspector panel for shape attributes
    """

    asset_changed = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_path: str | None = None
        self._task_spec = None
        self._labeling_widget = None
        self._current_asset: str | None = None
        self._label_name_to_id: dict[str, int] = {}
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)

        t = get_theme()

        # -- Left: Asset List --
        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)

        header = QtWidgets.QLabel(tr("📁 资产列表", "📁 Assets"))
        header.setStyleSheet(
            f"font-family: {FONT_FAMILY}; font-size: {FONT_SIZE_BODY}px;"
            f"font-weight: bold; padding: 6px 8px; color: {t['text']};"
        )
        left_layout.addWidget(header)

        self._search_bar = QtWidgets.QLineEdit()
        self._search_bar.setPlaceholderText(tr("搜索...", "Search..."))
        self._search_bar.textChanged.connect(self._on_search)
        left_layout.addWidget(self._search_bar)

        self._asset_list = QtWidgets.QListWidget()
        self._asset_list.setStyleSheet(get_list_widget_style())
        self._asset_list.currentItemChanged.connect(self._on_asset_selected)
        left_layout.addWidget(self._asset_list)

        self._progress_label = QtWidgets.QLabel()
        self._progress_label.setStyleSheet(
            f"font-family: {FONT_FAMILY}; font-size: {FONT_SIZE_CAPTION}px;"
            f"color: {t['text_secondary']}; padding: 4px 8px;"
        )
        left_layout.addWidget(self._progress_label)

        left.setLayout(left_layout)
        splitter.addWidget(left)

        # -- Center: Canvas container --
        self._canvas_container = QtWidgets.QWidget()
        self._canvas_layout = QtWidgets.QVBoxLayout()
        self._canvas_layout.setContentsMargins(0, 0, 0, 0)
        placeholder = QtWidgets.QLabel(tr(
            "选择一个资产开始标注", "Select an asset to start labeling"
        ))
        placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._canvas_layout.addWidget(placeholder)
        self._canvas_container.setLayout(self._canvas_layout)
        splitter.addWidget(self._canvas_container)

        # -- Right: Inspector --
        self._inspector = QtWidgets.QTextEdit()
        self._inspector.setReadOnly(True)
        self._inspector.setMaximumWidth(240)
        self._inspector.setMinimumWidth(140)
        self._inspector.setPlaceholderText(tr(
            "检查器\n\n选择画布上的形状\n以查看其属性",
            "Inspector\n\nSelect a shape on the\ncanvas to inspect its\nproperties."
        ))
        self._inspector.setStyleSheet(f"""
            QTextEdit {{
                border: 1px solid {t['border']};
                background-color: {t['surface']};
                font-size: {FONT_SIZE_BODY}px;
                color: {t['text']};
                font-family: {FONT_FAMILY};
                border-radius: 6px;
                padding: 8px;
            }}
        """)
        splitter.addWidget(self._inspector)

        splitter.setSizes([200, 700, 220])

        main = QtWidgets.QVBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.addWidget(splitter)
        self.setLayout(main)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_project_context(self, project_path: str, task_spec) -> None:
        """Initialize with project and task spec. Called by WorkbenchWindow."""
        self._project_path = project_path
        self._task_spec = task_spec
        self._label_name_to_id = {
            lb.name: lb.id for lb in task_spec.labels
        }
        self._scan_assets()
        self._apply_task_tool_filter()

    # ------------------------------------------------------------------
    # Asset management
    # ------------------------------------------------------------------

    def _scan_assets(self):
        self._asset_list.blockSignals(True)
        self._asset_list.clear()

        assets_dir = Path(self._project_path) / "assets" if self._project_path else None
        if not assets_dir or not assets_dir.is_dir():
            self._asset_list.blockSignals(False)
            return

        exts = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
        annotated = 0
        total = 0

        for p in sorted(assets_dir.iterdir()):
            if not p.is_file() or p.suffix.lower() not in exts:
                continue
            total += 1

            ann_path = Path(self._project_path) / "annotations" / f"{p.stem}.json"
            status = AssetListItem.STATUS_UNANNOTATED
            if ann_path.exists():
                try:
                    import json
                    ann_data = json.loads(ann_path.read_text(encoding="utf-8"))
                    if ann_data.get("shapes"):
                        status = AssetListItem.STATUS_COMPLETE
                        annotated += 1
                except Exception:
                    pass

            self._asset_list.addItem(AssetListItem(str(p), status))

        self._asset_list.blockSignals(False)
        self._update_progress(annotated, total)

    def _on_search(self, text: str):
        for i in range(self._asset_list.count()):
            item = self._asset_list.item(i)
            if isinstance(item, AssetListItem):
                name = Path(item.asset_path).name.lower()
                item.setHidden(text.lower() not in name)

    def _update_progress(self, annotated: int, total: int):
        pct = (annotated / total * 100) if total > 0 else 0
        self._progress_label.setText(tr(
            f"总计: {total} | 已标注: {annotated} | 进度: {pct:.0f}%",
            f"Total: {total} | Annotated: {annotated} | Progress: {pct:.0f}%"
        ))

    # ------------------------------------------------------------------
    # Asset selection & annotation loading
    # ------------------------------------------------------------------

    def _on_asset_selected(self, current: AssetListItem, previous):
        if current is None:
            return

        asset_path = getattr(current, "asset_path", None)
        if not asset_path or not Path(asset_path).is_file():
            return

        self._current_asset = asset_path

        if self._labeling_widget is None:
            self._create_labeling_widget()

        if self._labeling_widget is not None:
            self._labeling_widget.loadFile(asset_path)
            self._load_existing_annotations(asset_path)
            self.asset_changed.emit(asset_path)

    def _load_existing_annotations(self, asset_path: str):
        from anylabeling.platform.application.annotation_adapter import (
            load_annotations_for_asset,
        )
        from anylabeling.views.labeling.shape import Shape
        from PyQt6.QtCore import QPointF

        shape_dicts = load_annotations_for_asset(asset_path, self._project_path)
        if shape_dicts is None:
            canvas = self._labeling_widget.canvas
            canvas.shapes = []
            canvas.update()
            return

        shapes = []
        for sd in shape_dicts:
            shape = Shape(
                label=sd["label"],
                shape_type=sd["shape_type"],
                group_id=sd.get("group_id"),
                description=sd.get("description", ""),
                difficult=sd.get("difficult", False),
            )
            for px, py in sd["points"]:
                shape.add_point(QPointF(px, py))
            shape.close()
            shapes.append(shape)

        canvas = self._labeling_widget.canvas
        canvas.shapes = shapes
        canvas.update()

    # ------------------------------------------------------------------
    # Annotation save
    # ------------------------------------------------------------------

    def _on_annotation_changed(self):
        if not self._current_asset or not self._project_path:
            return

        from anylabeling.platform.application.annotation_adapter import (
            save_annotations_for_asset,
        )

        canvas = self._labeling_widget.canvas
        save_annotations_for_asset(
            self._current_asset, canvas.shapes,
            self._project_path, self._label_name_to_id,
        )

        self._update_asset_status(self._current_asset, canvas.shapes)

    def _update_asset_status(self, asset_path: str, shapes: list):
        for i in range(self._asset_list.count()):
            item = self._asset_list.item(i)
            if isinstance(item, AssetListItem) and item.asset_path == asset_path:
                status = (
                    AssetListItem.STATUS_COMPLETE if shapes
                    else AssetListItem.STATUS_UNANNOTATED
                )
                item.set_status(status)
                break
        self._recount_progress()

    def _recount_progress(self):
        total = self._asset_list.count()
        annotated = sum(
            1 for i in range(total)
            if isinstance(self._asset_list.item(i), AssetListItem)
            and self._asset_list.item(i).annotation_status == AssetListItem.STATUS_COMPLETE
        )
        self._update_progress(annotated, total)

    # ------------------------------------------------------------------
    # LabelingWidget creation
    # ------------------------------------------------------------------

    def _create_labeling_widget(self):
        from anylabeling.views.labeling.label_widget import LabelingWidget

        while self._canvas_layout.count():
            item = self._canvas_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        labeling = LabelingWidget(parent=self, config=None, filename=self._current_asset)
        labeling.set_project_context({
            "project_path": self._project_path,
            "assets_dir": str(Path(self._project_path) / "assets") if self._project_path else "",
            "annotations_dir": str(Path(self._project_path) / "annotations") if self._project_path else "",
        })

        labeling.canvas.shape_moved.connect(self._on_annotation_changed)
        labeling.canvas.new_shape.connect(self._on_annotation_changed)
        labeling.canvas.selection_changed.connect(self._on_inspector_update)

        self._canvas_layout.addWidget(labeling)
        self._labeling_widget = labeling
        self._apply_task_tool_filter()

    # ------------------------------------------------------------------
    # Task-aware tool filtering
    # ------------------------------------------------------------------

    def _apply_task_tool_filter(self):
        if self._task_spec is None:
            return
        if self._labeling_widget is None:
            return

        from anylabeling.platform.application.annotation_adapter import (
            get_allowed_shape_types,
        )

        allowed = get_allowed_shape_types(self._task_spec.family)
        actions = self._labeling_widget.actions

        for action_name, shape_type in _ACTION_SHAPE_TYPE_MAP.items():
            action = getattr(actions, action_name, None)
            if action is not None:
                action.setVisible(shape_type in allowed)

        if allowed:
            self._labeling_widget.canvas._create_mode = allowed[0]

    # ------------------------------------------------------------------
    # Inspector
    # ------------------------------------------------------------------

    def _on_inspector_update(self, selected_shapes):
        if not selected_shapes:
            self._inspector.clear()
            self._inspector.setPlaceholderText(tr(
                "检查器\n\n选择画布上的形状\n以查看其属性",
                "Inspector\n\nSelect a shape on the\ncanvas to inspect its\nproperties."
            ))
            return

        shape = selected_shapes[0]
        lines = [
            f"<b>{tr('标签', 'Label')}:</b> {shape.label}",
            f"<b>{tr('类型', 'Type')}:</b> {shape.shape_type}",
            f"<b>{tr('顶点数', 'Vertices')}:</b> {len(shape.points)}",
            f"<b>{tr('困难', 'Difficult')}:</b> {getattr(shape, 'difficult', False)}",
        ]
        if getattr(shape, 'group_id', None) is not None:
            lines.append(f"<b>{tr('组ID', 'Group')}:</b> {shape.group_id}")
        if getattr(shape, 'description', ''):
            lines.append(f"<b>{tr('描述', 'Desc')}:</b> {shape.description}")

        self._inspector.setHtml("<br>".join(lines))
```

- [ ] **Step 2: Verify syntax**

Run: `python -c "import ast; ast.parse(open('anylabeling/views/platform/label_workspace.py').read()); print('OK')"`
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add anylabeling/views/platform/label_workspace.py
git commit -m "feat: add LabelWorkspace — native labeling page with task-aware tools

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: WorkbenchWindow — Page Reordering & LabelWorkspace Integration

**Files:**
- Modify: `anylabeling/views/platform/workbench_window.py`

**Current page layout (broken):**
```
Page 0: ProjectHomeWidget
Page 1: DataWorkspace    ← NavigationBar LABEL=1 points here (wrong)
Page 2: TrainWorkspace
Page 3: EvaluateWorkspace
Page 4: InferWorkspace
Page 5: ExportWorkspace
```

**Target page layout (correct):**
```
Page 0: DataWorkspace       ← NAV DATA=0
Page 1: LabelWorkspace      ← NAV LABEL=1 (NEW)
Page 2: TrainWorkspace      ← NAV TRAIN=2
Page 3: EvaluateWorkspace   ← NAV EVALUATE=3
Page 4: InferWorkspace      ← NAV INFER=4
Page 5: ExportWorkspace     ← NAV EXPORT=5
Page 6: ProjectHomeWidget   ← shown before project opens
```

- [ ] **Step 1: Add LabelWorkspace import**

Insert after line 21 (`from ...infer_workspace import InferWorkspace`):
```python
from anylabeling.views.platform.label_workspace import LabelWorkspace
```

- [ ] **Step 2: Rewrite `_create_pages()` (replaces lines 256-276)**

```python
    def _create_pages(self):
        # Page indices must match NavigationBar constants:
        #   DATA=0, LABEL=1, TRAIN=2, EVALUATE=3, INFER=4, EXPORT=5

        # Page 0 (DATA): Data Workspace
        self._data_workspace = DataWorkspace()
        self._pages.addWidget(self._data_workspace)

        # Page 1 (LABEL): Label Workspace
        self._label_workspace = LabelWorkspace()
        self._pages.addWidget(self._label_workspace)

        # Page 2 (TRAIN): Train Workspace
        self._train_workspace = TrainWorkspace()
        self._pages.addWidget(self._train_workspace)

        # Page 3 (EVALUATE): Evaluate Workspace
        self._evaluate_workspace = EvaluateWorkspace()
        self._pages.addWidget(self._evaluate_workspace)

        # Page 4 (INFER): Infer Workspace
        self._infer_workspace = InferWorkspace()
        self._pages.addWidget(self._infer_workspace)

        # Page 5 (EXPORT): Export Workspace
        self._export_workspace = ExportWorkspace()
        self._pages.addWidget(self._export_workspace)

        # Page 6: Project Home (shown only before project opens)
        self._project_home = ProjectHomeWidget()
        self._project_home.project_opened.connect(self.set_project)
        self._pages.addWidget(self._project_home)

        self._label_page_widget = None
```

- [ ] **Step 3: Update `__init__` initial page to ProjectHome**

Replace:
```python
        self._navigation.set_current_step(DATA)
        self._pages.setCurrentIndex(DATA)
```
With:
```python
        self._pages.setCurrentIndex(6)  # ProjectHome
```

- [ ] **Step 4: In `set_project()`, add LabelWorkspace initialization**

After `self._data_workspace.build_requested.connect(...)`, insert:
```python
        # --- Label Workspace: initialize with task spec ---
        if task_specs:
            self._label_workspace.set_project_context(project_path, task_specs[0])
```

- [ ] **Step 5: Simplify `add_label_workspace()` to backward-compat no-op**

Replace the existing `add_label_workspace()` method body:
```python
    def add_label_workspace(self, labeling_widget: QtWidgets.QWidget) -> None:
        """Deprecated — LabelWorkspace is now native. Kept for API compat."""
        logger.warning(
            "add_label_workspace() called but LabelWorkspace is now native."
        )
```

- [ ] **Step 6: Verify syntax**

Run: `python -c "import ast; ast.parse(open('anylabeling/views/platform/workbench_window.py').read()); print('OK')"`
Expected: OK

- [ ] **Step 7: Commit**

```bash
git add anylabeling/views/platform/workbench_window.py
git commit -m "fix: reorder pages to align with NavigationBar, integrate LabelWorkspace

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Export LabelWorkspace

**Files:**
- Modify: `anylabeling/views/platform/__init__.py`

- [ ] **Step 1: Add import and export**

Add import:
```python
from anylabeling.views.platform.label_workspace import LabelWorkspace
```

Add `"LabelWorkspace"` to `__all__`.

- [ ] **Step 2: Commit**

```bash
git add anylabeling/views/platform/__init__.py
git commit -m "chore: export LabelWorkspace from platform views

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: LabelWorkspace Tests

**Files:**
- Create: `tests/platform/views/test_label_workspace.py`

- [ ] **Step 1: Write tests**

```python
"""Tests for LabelWorkspace components."""
import sys
import pytest

pytest.importorskip("PyQt6")


class TestAssetListItem:
    """AssetListItem — annotation status display."""

    def test_create_unannotated(self):
        from anylabeling.views.platform.label_workspace import AssetListItem
        item = AssetListItem("/fake/path/image.jpg")
        assert item.asset_path == "/fake/path/image.jpg"
        assert item.annotation_status == AssetListItem.STATUS_UNANNOTATED
        assert "⭕" in item.text()

    def test_create_complete(self):
        from anylabeling.views.platform.label_workspace import AssetListItem
        item = AssetListItem("/fake/path/image.jpg", AssetListItem.STATUS_COMPLETE)
        assert "✅" in item.text()

    def test_set_status_updates_display(self):
        from anylabeling.views.platform.label_workspace import AssetListItem
        item = AssetListItem("/fake/path/image.jpg")
        item.set_status(AssetListItem.STATUS_COMPLETE)
        assert "✅" in item.text()

    def test_user_role_data(self):
        from anylabeling.views.platform.label_workspace import AssetListItem
        from PyQt6.QtCore import Qt
        item = AssetListItem("/fake/path/img.png")
        assert item.data(Qt.ItemDataRole.UserRole) == "/fake/path/img.png"


@pytest.fixture
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


class TestLabelWorkspaceCreation:
    """Smoke tests for LabelWorkspace instantiation."""

    def test_create_widget(self, qapp):
        from anylabeling.views.platform.label_workspace import LabelWorkspace
        workspace = LabelWorkspace()
        assert workspace is not None
        assert workspace._asset_list is not None
        assert workspace._search_bar is not None
        assert workspace._inspector is not None
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/platform/views/test_label_workspace.py -v`
Expected: 5 tests PASS

- [ ] **Step 3: Run existing tests — verify no regressions**

Run: `pytest tests/platform/ -v -q`
Expected: no unexpected failures

- [ ] **Step 4: Commit**

```bash
git add tests/platform/views/test_label_workspace.py
git commit -m "test: add LabelWorkspace unit tests

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Validation

```bash
# 1. Syntax checks
python -c "import ast; ast.parse(open('anylabeling/platform/application/annotation_adapter.py').read()); print('OK')"
python -c "import ast; ast.parse(open('anylabeling/views/platform/label_workspace.py').read()); print('OK')"
python -c "import ast; ast.parse(open('anylabeling/views/platform/workbench_window.py').read()); print('OK')"

# 2. New tests
pytest tests/platform/application/test_annotation_adapter.py -v
pytest tests/platform/views/test_label_workspace.py -v

# 3. Existing tests — no regressions
pytest tests/platform/ -v -q
```

## Acceptance

- [ ] `detection_hbb` 项目：标注工具栏仅显示矩形按钮
- [ ] `pose` 项目：标注工具栏仅显示关键点按钮
- [ ] Canvas 缩放/平移/polygon 跟随鼠标 全部正常
- [ ] 新增/删除/修改标注 → 自动保存到 `annotations/{asset_id}.json`
- [ ] 资产列表标注状态图标随标注变化更新
- [ ] 其他 5 个 workspace 不受影响
- [ ] 所有测试通过
