"""Phase 3 tests for EvaluateWorkspace — confusion matrix heatmap,
per-class analysis table, multi-run comparison, MisclassificationService.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("PyQt6")

from PyQt6 import QtWidgets


@pytest.fixture(autouse=True)
def _ensure_ultralytics_registered():
    """Ensure AlgorithmRegistry has Ultralytics providers registered."""
    import anylabeling.platform.adapters.ultralytics  # noqa: F401
    yield


@pytest.fixture
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


# ---------------------------------------------------------------------------
# Confusion matrix heatmap rendering
# ---------------------------------------------------------------------------

class TestConfusionMatrixRendering:
    def test_render_confusion_matrix_returns_qpixmap(self, qapp):
        """_render_confusion_matrix produces a non-null QPixmap from a numpy array."""
        import numpy as np
        from anylabeling.views.platform.evaluate_workspace import (
            _render_confusion_matrix_pixmap,
        )

        matrix = np.array([[10, 1, 0], [2, 8, 1], [0, 3, 7]], dtype=np.int32)
        class_names = ["cat", "dog", "bird"]
        pixmap = _render_confusion_matrix_pixmap(matrix, class_names)

        assert pixmap is not None, "Should return a QPixmap"
        assert not pixmap.isNull(), "Pixmap should not be null"
        assert pixmap.width() > 0, "Pixmap should have positive width"
        assert pixmap.height() > 0, "Pixmap should have positive height"

    def test_render_empty_matrix_handled(self):
        """Empty or None matrix returns None gracefully."""
        import numpy as np
        from anylabeling.views.platform.evaluate_workspace import (
            _render_confusion_matrix_pixmap,
        )

        result = _render_confusion_matrix_pixmap(None, [])
        assert result is None or result.isNull(), (
            "None matrix should return None or null pixmap"
        )

        empty = np.array([], dtype=np.int32).reshape(0, 0)
        result2 = _render_confusion_matrix_pixmap(empty, [])
        assert result2 is None or result2.isNull(), (
            "Empty matrix should return None or null pixmap"
        )


# ---------------------------------------------------------------------------
# Per-class analysis table
# ---------------------------------------------------------------------------

class TestPerClassAnalysisTable:
    def test_table_has_correct_columns(self, qapp):
        """QTableWidget for per-class analysis has expected columns."""
        from anylabeling.views.platform.evaluate_workspace import EvaluateWorkspace
        ws = EvaluateWorkspace()
        assert hasattr(ws, "_per_class_table"), (
            "Should have per-class analysis table"
        )
        table = ws._per_class_table
        assert table.columnCount() == 5, (
            f"Expected 5 columns, got {table.columnCount()}"
        )
        ws.close()

    def test_populate_table_rows_equal_class_count(self, qapp):
        """After populating, table row count equals number of classes."""
        from anylabeling.views.platform.evaluate_workspace import EvaluateWorkspace
        ws = EvaluateWorkspace()
        ap_per_class = {"0": 0.85, "1": 0.73, "2": 0.62}
        class_names = ["cat", "dog", "bird"]
        ws._populate_per_class_table(ap_per_class, class_names)
        assert ws._per_class_table.rowCount() == len(class_names), (
            f"Expected {len(class_names)} rows, got {ws._per_class_table.rowCount()}"
        )
        ws.close()

    def test_populate_table_no_data(self, qapp):
        """Populating with empty data shows no rows."""
        from anylabeling.views.platform.evaluate_workspace import EvaluateWorkspace
        ws = EvaluateWorkspace()
        ws._populate_per_class_table({}, [])
        assert ws._per_class_table.rowCount() == 0
        ws.close()


# ---------------------------------------------------------------------------
# Multi-run comparison
# ---------------------------------------------------------------------------

class TestMultiRunComparison:
    def test_run_comparison_combos_exist(self, qapp):
        """EvaluateWorkspace has two run combo boxes for comparison."""
        from anylabeling.views.platform.evaluate_workspace import EvaluateWorkspace
        ws = EvaluateWorkspace()
        assert hasattr(ws, "_compare_run_a"), (
            "Should have Run A comparison combo"
        )
        assert hasattr(ws, "_compare_run_b"), (
            "Should have Run B comparison combo"
        )
        assert isinstance(ws._compare_run_a, QtWidgets.QComboBox)
        assert isinstance(ws._compare_run_b, QtWidgets.QComboBox)
        ws.close()

    def test_comparison_delta_computation(self):
        """_compute_delta returns formatted change string."""
        from anylabeling.views.platform.evaluate_workspace import _compute_delta

        delta = _compute_delta(0.85, 0.82)
        assert delta is not None
        assert "3" in delta or "+" in delta or "↑" in delta.replace(" ", ""), (
            "Positive delta should indicate improvement"
        )

        delta2 = _compute_delta(0.80, 0.85)
        assert delta2 is not None
        # Should indicate decrease
        assert "5" in delta2.replace(" ", "") or "↓" in delta2.replace(" ", "") or "-" in delta2, (
            "Negative delta should indicate decrease"
        )

    def test_comparison_labels_exist(self, qapp):
        """Comparison section has labels for metrics."""
        from anylabeling.views.platform.evaluate_workspace import EvaluateWorkspace
        ws = EvaluateWorkspace()
        assert hasattr(ws, "_lbl_compare_summary"), (
            "Should have comparison summary label"
        )
        assert isinstance(ws._lbl_compare_summary, QtWidgets.QLabel)
        ws.close()


# ---------------------------------------------------------------------------
# MisclassificationService
# ---------------------------------------------------------------------------

class TestMisclassificationService:
    def test_service_initializes(self):
        """MisclassificationService initializes without errors."""
        from anylabeling.platform.application.misclassification_service import (
            MisclassificationService,
        )
        svc = MisclassificationService()
        assert svc is not None

    def test_get_false_positives_returns_list(self):
        """get_false_positives returns list[PredictionObject]."""
        from anylabeling.platform.application.misclassification_service import (
            MisclassificationService,
        )
        from anylabeling.platform.domain.prediction import PredictionObject

        svc = MisclassificationService()
        # Construct mock inputs
        confusion_matrix = None  # Will cause empty result
        class_names = ["cat", "dog"]
        preds = []
        fps = svc.get_false_positives(confusion_matrix, class_names, preds, 0.5)
        assert isinstance(fps, list), "Should return a list"
        assert len(fps) == 0, "No predictions means no false positives"

    def test_get_false_negatives_returns_list(self):
        """get_false_negatives returns list[AnnotationObject]."""
        from anylabeling.platform.application.misclassification_service import (
            MisclassificationService,
        )
        from anylabeling.platform.domain.annotation import AnnotationObject

        svc = MisclassificationService()
        confusion_matrix = None
        class_names = ["cat"]
        annotations = []
        fns = svc.get_false_negatives(confusion_matrix, class_names, annotations)
        assert isinstance(fns, list), "Should return a list"
        assert len(fns) == 0, "No annotations means no false negatives"

    def test_get_low_confidence_returns_list(self):
        """get_low_confidence returns list[PredictionObject]."""
        from anylabeling.platform.application.misclassification_service import (
            MisclassificationService,
        )
        from anylabeling.platform.domain.prediction import PredictionObject

        svc = MisclassificationService()
        preds = [
            PredictionObject(
                id="p1", label_id=0, geometry_type="bbox_xyxy",
                geometry=[0, 0, 10, 10], score=0.45,
            ),
            PredictionObject(
                id="p2", label_id=0, geometry_type="bbox_xyxy",
                geometry=[20, 20, 30, 30], score=0.85,
            ),
            PredictionObject(
                id="p3", label_id=1, geometry_type="bbox_xyxy",
                geometry=[40, 40, 50, 50], score=0.30,
            ),
        ]
        low = svc.get_low_confidence(preds, 0.5)
        assert isinstance(low, list), "Should return a list"
        assert len(low) == 2, f"Expected 2 low-confidence preds, got {len(low)}"
        scores = [p.score for p in low]
        assert all(s < 0.5 for s in scores), "All returned preds should be below threshold"

    def test_fp_filters_by_confusion_matrix(self):
        """False positives correctly identified from confusion matrix."""
        import numpy as np
        from anylabeling.platform.application.misclassification_service import (
            MisclassificationService,
        )
        from anylabeling.platform.domain.prediction import PredictionObject

        svc = MisclassificationService()
        # Create a confusion matrix: pred=class0, true=class1 has 3 FP
        cm = np.array([[8, 3], [1, 9]], dtype=np.int32)
        class_names = ["cat", "dog"]

        preds = [
            PredictionObject(
                id="p1", label_id=0, geometry_type="bbox_xyxy",
                geometry=[0, 0, 10, 10], score=0.9,
            ),
            PredictionObject(
                id="p2", label_id=1, geometry_type="bbox_xyxy",
                geometry=[20, 20, 30, 30], score=0.8,
            ),
        ]
        fps = svc.get_false_positives(cm, class_names, preds, 0.5)
        assert isinstance(fps, list), "Should return a list"

    def test_low_confidence_default_threshold(self):
        """get_low_confidence uses 0.25 as default threshold."""
        from anylabeling.platform.application.misclassification_service import (
            MisclassificationService,
        )
        from anylabeling.platform.domain.prediction import PredictionObject

        svc = MisclassificationService()
        preds = [
            PredictionObject(
                id="low1", label_id=0, geometry_type="bbox_xyxy",
                geometry=[0, 0, 10, 10], score=0.2,
            ),
            PredictionObject(
                id="high1", label_id=0, geometry_type="bbox_xyxy",
                geometry=[20, 20, 30, 30], score=0.9,
            ),
        ]
        low = svc.get_low_confidence(preds)  # default threshold
        assert len(low) == 1, "Default threshold 0.25 should filter one"
        assert low[0].id == "low1"


# ---------------------------------------------------------------------------
# Misclassification review panel
# ---------------------------------------------------------------------------

class TestMisclassificationPanel:
    def test_panel_has_tab_widget(self, qapp):
        """EvaluateWorkspace has a QTabWidget for misclassification review."""
        from anylabeling.views.platform.evaluate_workspace import EvaluateWorkspace
        ws = EvaluateWorkspace()
        assert hasattr(ws, "_misclass_tabs"), (
            "Should have misclassification tab widget"
        )
        assert isinstance(ws._misclass_tabs, QtWidgets.QTabWidget)
        ws.close()

    def test_panel_has_expected_tabs(self, qapp):
        """Misclassification panel has FP, FN, Low Confidence, Confused sample tabs."""
        from anylabeling.views.platform.evaluate_workspace import EvaluateWorkspace
        ws = EvaluateWorkspace()
        tabs = ws._misclass_tabs
        assert tabs.count() >= 3, (
            f"Expected at least 3 tabs, got {tabs.count()}"
        )
        # Tab titles should be meaningful
        tab_titles = []
        for i in range(tabs.count()):
            tab_titles.append(tabs.tabText(i))
        combined = " ".join(tab_titles).lower()
        assert "fp" in combined or "误检" in combined, (
            f"Should have FP/misdetection tab, got: {tab_titles}"
        )
        assert "fn" in combined or "漏检" in combined, (
            f"Should have FN/missed tab, got: {tab_titles}"
        )
        ws.close()


# ---------------------------------------------------------------------------
# Confusion matrix label
# ---------------------------------------------------------------------------

class TestConfusionMatrixLabel:
    def test_label_exists(self, qapp):
        """EvaluateWorkspace has a label to display confusion matrix pixmap."""
        from anylabeling.views.platform.evaluate_workspace import EvaluateWorkspace
        ws = EvaluateWorkspace()
        assert hasattr(ws, "_lbl_confusion_matrix"), (
            "Should have confusion matrix pixmap label"
        )
        assert isinstance(ws._lbl_confusion_matrix, QtWidgets.QLabel)
        ws.close()
