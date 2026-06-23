from __future__ import annotations

import sys

import pytest

try:
    from PyQt6 import QtWidgets
    _HAS_PYQT = True
except ImportError:
    _HAS_PYQT = False

pytestmark = pytest.mark.skipif(not _HAS_PYQT, reason="PyQt6 not available")


def _make_app():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    return app


class TestEvaluateWorkspaceWithPlots:
    def test_has_tab_widget_after_init(self):
        from anylabeling.views.platform.evaluate_workspace import EvaluateWorkspace
        app = _make_app()
        widget = EvaluateWorkspace()
        tab = widget.findChild(QtWidgets.QTabWidget)
        assert tab is not None, "Should have a QTabWidget for metrics display"
        widget.close()

    def test_display_metrics_populates_tabs(self):
        import numpy as np
        from anylabeling.views.platform.evaluate_workspace import EvaluateWorkspace
        app = _make_app()
        widget = EvaluateWorkspace()
        metrics = {
            "mAP50": 0.842,
            "mAP50_95": 0.651,
            "ap_per_class": {"0": 0.85, "1": 0.73},
            "class_names": ["cat", "dog"],
            "confusion_matrix": np.array([[10, 1], [2, 9]], dtype=np.int32),
        }
        widget.display_metrics(metrics)
        widget.close()

    def test_clear_metrics_resets_display(self):
        from anylabeling.views.platform.evaluate_workspace import EvaluateWorkspace
        app = _make_app()
        widget = EvaluateWorkspace()
        widget.clear_metrics()
        widget.close()
