from __future__ import annotations

import os
import sys
import tempfile

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


def _create_test_image() -> str:
    import numpy as np
    import cv2
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    img[20:40, 20:40] = [255, 0, 0]
    tdir = tempfile.mkdtemp()
    path = os.path.join(tdir, "test.png")
    cv2.imwrite(path, img)
    return path


class TestInferenceViewerWidget:
    def test_creates_with_placeholder(self):
        from anylabeling.views.platform.widgets.inference_viewer import InferenceViewerWidget
        app = _make_app()
        widget = InferenceViewerWidget()
        assert widget is not None
        widget.close()

    def test_load_image_no_error(self):
        from anylabeling.views.platform.widgets.inference_viewer import InferenceViewerWidget
        app = _make_app()
        widget = InferenceViewerWidget()
        img_path = _create_test_image()
        widget.load_image(img_path)
        widget.close()

    def test_draw_detections_no_error(self):
        from anylabeling.views.platform.widgets.inference_viewer import InferenceViewerWidget
        app = _make_app()
        widget = InferenceViewerWidget()
        img_path = _create_test_image()
        widget.load_image(img_path)
        detections = [
            {"bbox": [10.0, 10.0, 50.0, 50.0], "class": 0, "conf": 0.95},
            {"bbox": [40.0, 40.0, 90.0, 90.0], "class": 1, "conf": 0.72},
        ]
        widget.draw_detections(detections, ["cat", "dog"])
        widget.close()

    def test_clear_resets(self):
        from anylabeling.views.platform.widgets.inference_viewer import InferenceViewerWidget
        app = _make_app()
        widget = InferenceViewerWidget()
        widget.clear()
        widget.close()
