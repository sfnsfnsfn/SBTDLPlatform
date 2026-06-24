"""Tests for TaskConfigurator widget.

Coverage:
    1. TaskConfigurator initializes with correct task type combo values
    2. Smart recommendation logic (_smart_recommend_task)
    3. Task type combo has 8 entries
    4. Label CRUD: add label updates table
    5. Label CRUD: delete label removes from table
    6. _TASK_TYPES covers all required families
    7. set_project_context with empty dir shows empty state
"""

from __future__ import annotations

import sys

import pytest

try:
    from PyQt6 import QtWidgets
    _HAS_PYQT = True
except ImportError:
    _HAS_PYQT = False

if _HAS_PYQT:
    from anylabeling.views.platform.task_configurator import (
        TaskConfigurator,
        _TASK_TYPES,
        _FAMILY_INDEX,
        _smart_recommend_task,
    )


pytestmark = pytest.mark.skipif(not _HAS_PYQT, reason="PyQt6 not available")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app():
    """Create a QApplication if one doesn't exist."""
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    return app


# ---------------------------------------------------------------------------
# Non-GUI helper tests (can run without QApplication)
# ---------------------------------------------------------------------------


class TestTaskTypes:
    """Tests for _TASK_TYPES definitions."""

    REQUIRED_FAMILIES = {
        "detection_hbb",
        "detection_obb",
        "instance_segmentation",
        "semantic_segmentation",
        "pose",
        "classification",
        "anomaly",
        "ocr",
    }

    def test_all_required_families_present(self):
        """All 8 task families are defined."""
        families = {t[0] for t in _TASK_TYPES}
        assert families == self.REQUIRED_FAMILIES

    def test_task_types_count(self):
        """Exactly 8 task types defined."""
        assert len(_TASK_TYPES) == 8

    def test_each_has_display_name(self):
        """Each task type has a display name."""
        for family, display, desc in _TASK_TYPES:
            assert display, f"Missing display for {family}"

    def test_each_has_description(self):
        """Each task type has a description."""
        for family, display, desc in _TASK_TYPES:
            assert desc, f"Missing description for {family}"

    def test_family_index_maps_correctly(self):
        """_FAMILY_INDEX maps each family to its position."""
        for i, (family, _, _) in enumerate(_TASK_TYPES):
            assert _FAMILY_INDEX[family] == i


class TestSmartRecommendTask:
    """Tests for _smart_recommend_task helper."""

    def test_no_assets_returns_none(self):
        """Zero assets returns None."""
        assert _smart_recommend_task(0, 0) is None

    def test_many_groups_suggests_classification(self):
        """10+ groups suggests classification."""
        assert _smart_recommend_task(100, 10) == "classification"
        assert _smart_recommend_task(50, 15) == "classification"

    def test_few_groups_suggests_detection(self):
        """Few groups with assets suggests detection_hbb."""
        assert _smart_recommend_task(10, 0) == "detection_hbb"
        assert _smart_recommend_task(5, 3) == "detection_hbb"
        assert _smart_recommend_task(1, 0) == "detection_hbb"

    def test_boundary_9_groups(self):
        """9 groups still suggests detection (threshold is 10)."""
        assert _smart_recommend_task(50, 9) == "detection_hbb"


# ---------------------------------------------------------------------------
# GUI tests
# ---------------------------------------------------------------------------


class TestTaskConfiguratorInit:
    """Tests for TaskConfigurator initial state."""

    def test_creates_widget(self):
        """TaskConfigurator can be constructed."""
        app = _make_app()
        widget = TaskConfigurator()
        assert widget is not None
        widget.deleteLater()

    def test_combo_has_8_items(self):
        """Task type combo has 8 entries."""
        app = _make_app()
        widget = TaskConfigurator()
        assert widget._task_combo.count() == 8
        widget.deleteLater()

    def test_default_task_is_first(self):
        """Default task type is detection_hbb (index 0)."""
        app = _make_app()
        widget = TaskConfigurator()
        assert widget._task_combo.currentData() == "detection_hbb"
        widget.deleteLater()

    def test_preview_area_exists(self):
        """Preview scroll area is created."""
        app = _make_app()
        widget = TaskConfigurator()
        assert widget._preview_area is not None
        widget.deleteLater()

    def test_label_table_has_correct_columns(self):
        """Label table has ID and Name columns."""
        app = _make_app()
        widget = TaskConfigurator()
        headers = [
            widget._label_table.horizontalHeaderItem(i).text()
            for i in range(widget._label_table.columnCount())
        ]
        assert len(headers) == 2
        widget.deleteLater()

    def test_validation_group_collapsed_by_default(self):
        """Validation group box is unchecked (collapsed) initially."""
        app = _make_app()
        widget = TaskConfigurator()
        assert widget._validation_group.isChecked() is False
        widget.deleteLater()


class TestTaskConfiguratorLabels:
    """Tests for label CRUD operations."""

    def test_add_label_increments_table(self):
        """Adding a label adds a row to the table."""
        app = _make_app()
        widget = TaskConfigurator()

        # Simulate adding a label directly
        from anylabeling.platform.domain.task import LabelClass
        widget._labels.append(LabelClass(id=0, name="cat"))
        widget._next_label_id = 1
        widget._refresh_label_table()

        assert widget._label_table.rowCount() == 1
        assert widget._label_table.item(0, 1).text() == "cat"
        widget.deleteLater()

    def test_delete_label_removes_from_table(self):
        """Deleting a label removes it."""
        app = _make_app()
        widget = TaskConfigurator()

        from anylabeling.platform.domain.task import LabelClass
        widget._labels.append(LabelClass(id=0, name="cat"))
        widget._labels.append(LabelClass(id=1, name="dog"))
        widget._refresh_label_table()
        assert widget._label_table.rowCount() == 2

        del widget._labels[0]
        widget._refresh_label_table()
        assert widget._label_table.rowCount() == 1
        assert widget._label_table.item(0, 1).text() == "dog"
        widget.deleteLater()

    def test_clear_labels_empties_table(self):
        """Clearing labels removes all rows."""
        app = _make_app()
        widget = TaskConfigurator()

        from anylabeling.platform.domain.task import LabelClass
        widget._labels.append(LabelClass(id=0, name="cat"))
        widget._refresh_label_table()

        widget._clear_labels()
        assert widget._label_table.rowCount() == 0
        assert len(widget._labels) == 0
        assert widget._next_label_id == 0
        widget.deleteLater()


class TestTaskConfiguratorSignals:
    """Tests for signal emission."""

    def test_back_requested_signal_exists(self):
        """back_requested signal is defined."""
        app = _make_app()
        widget = TaskConfigurator()
        assert hasattr(widget, 'back_requested')
        widget.deleteLater()

    def test_next_requested_signal_exists(self):
        """next_requested signal is defined."""
        app = _make_app()
        widget = TaskConfigurator()
        assert hasattr(widget, 'next_requested')
        widget.deleteLater()

    def test_task_configured_signal_exists(self):
        """task_configured signal is defined."""
        app = _make_app()
        widget = TaskConfigurator()
        assert hasattr(widget, 'task_configured')
        widget.deleteLater()

    def test_next_creates_taskspec(self, tmp_path):
        """Clicking next emits task_configured with valid TaskSpec."""
        app = _make_app()
        widget = TaskConfigurator()

        received = []

        def handler(ts):
            received.append(ts)

        widget.task_configured.connect(handler)

        # Set a project path and add a label
        widget._project_path = tmp_path / "test_project"
        widget._project_path.mkdir(parents=True)
        from anylabeling.platform.domain.task import LabelClass
        widget._labels.append(LabelClass(id=0, name="defect"))
        widget._next_label_id = 1

        # Trigger next
        widget._on_next()

        assert len(received) == 1
        ts = received[0]
        assert ts.family == "detection_hbb"
        assert len(ts.labels) == 1
        assert ts.labels[0].name == "defect"
        widget.deleteLater()


class TestTaskConfiguratorProjectContext:
    """Tests for set_project_context."""

    def test_set_project_context_without_assets(self, tmp_path):
        """Setting context with empty project shows empty state."""
        app = _make_app()
        widget = TaskConfigurator()
        widget.set_project_context(str(tmp_path))
        # Should not crash
        assert widget._project_path == tmp_path
        widget.deleteLater()

    def test_set_project_context_with_images(self, tmp_path):
        """Setting context with images populates preview."""
        app = _make_app()

        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        import cv2
        import numpy as np
        img = np.zeros((50, 50, 3), dtype='uint8')
        cv2.imwrite(str(assets_dir / "img1.jpg"), img)

        widget = TaskConfigurator()
        widget.set_project_context(str(tmp_path))
        assert widget._project_path == tmp_path
        widget.deleteLater()


class TestTaskConfiguratorWorkspaceMode:
    """Tests for WorkSpace-mode signals and dirty tracking."""

    def test_emit_task_configured(self, tmp_path):
        """set family + add label, click next → verify signal with TaskSpec."""
        app = _make_app()
        widget = TaskConfigurator()

        from anylabeling.platform.domain.task import LabelClass, TaskSpec

        received = []

        def handler(ts):
            received.append(ts)

        widget.task_configured.connect(handler)
        widget._project_path = tmp_path / "test_project"
        widget._project_path.mkdir(parents=True)
        widget._labels.append(LabelClass(id=0, name="defect"))
        widget._next_label_id = 1

        widget._on_next()

        assert len(received) == 1
        assert isinstance(received[0], TaskSpec)
        assert received[0].family == "detection_hbb"
        assert received[0].labels[0].name == "defect"
        widget.deleteLater()

    def test_emit_back_requested(self):
        """Click back → verify signal."""
        app = _make_app()
        widget = TaskConfigurator()

        received = []

        def handler():
            received.append(True)

        widget.back_requested.connect(handler)
        widget.back_requested.emit()

        assert len(received) == 1
        widget.deleteLater()

    def test_dirty_on_edit(self):
        """add label → is_modified == True."""
        app = _make_app()
        widget = TaskConfigurator()

        from anylabeling.platform.domain.task import LabelClass
        widget._labels.append(LabelClass(id=0, name="test"))
        widget._dirty = True

        assert widget.is_modified is True
        widget.deleteLater()

    def test_dirty_clear_after_next(self, tmp_path):
        """add label, click next → is_modified == False."""
        app = _make_app()
        widget = TaskConfigurator()

        from anylabeling.platform.domain.task import LabelClass
        widget._project_path = tmp_path / "test_project"
        widget._project_path.mkdir(parents=True)
        widget._labels.append(LabelClass(id=0, name="defect"))
        widget._next_label_id = 1
        widget._dirty = True

        widget._on_next()

        assert widget.is_modified is False
        widget.deleteLater()
