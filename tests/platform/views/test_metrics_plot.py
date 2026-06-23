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


class TestMetricsPlotWidget:
    def test_creates_with_default_state(self):
        from anylabeling.views.platform.widgets.metrics_plot import MetricsPlotWidget
        app = _make_app()
        widget = MetricsPlotWidget()
        assert widget is not None
        widget.close()

    def test_plot_confusion_matrix_no_error(self):
        import numpy as np
        from anylabeling.views.platform.widgets.metrics_plot import MetricsPlotWidget
        app = _make_app()
        widget = MetricsPlotWidget()
        matrix = np.array([[45, 2, 1], [3, 38, 0], [0, 1, 50]], dtype=np.int32)
        widget.plot_confusion_matrix(matrix, ["cat", "dog", "bird"])
        widget.close()

    def test_plot_per_class_ap_no_error(self):
        from anylabeling.views.platform.widgets.metrics_plot import MetricsPlotWidget
        app = _make_app()
        widget = MetricsPlotWidget()
        widget.plot_per_class_ap({"0": 0.852, "1": 0.731, "2": 0.943}, ["cat", "dog", "bird"])
        widget.close()

    def test_empty_data_shows_placeholder(self):
        from anylabeling.views.platform.widgets.metrics_plot import MetricsPlotWidget
        app = _make_app()
        widget = MetricsPlotWidget()
        widget.plot_confusion_matrix(None, [])
        widget.plot_per_class_ap({}, [])
        widget.plot_f1_curve({}, [])
        widget.close()

    def test_clear_all_resets(self):
        from anylabeling.views.platform.widgets.metrics_plot import MetricsPlotWidget
        app = _make_app()
        widget = MetricsPlotWidget()
        widget.clear_all()
        widget.close()
