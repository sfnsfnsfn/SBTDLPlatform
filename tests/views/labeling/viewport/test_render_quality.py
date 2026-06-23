import pathlib
import sys
import types
import unittest
from importlib import util as importlib_util

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
VIEWPORT_DIR = REPO_ROOT / "anylabeling" / "views" / "labeling" / "viewport"
CANVAS_PATH = (
    REPO_ROOT
    / "anylabeling"
    / "views"
    / "labeling"
    / "widgets"
    / "canvas.py"
)


def _ensure_package(name, path=None):
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        sys.modules[name] = module
    module.__path__ = [] if path is None else [str(path)]
    return module


def _load_module(name, path):
    spec = importlib_util.spec_from_file_location(name, path)
    module = importlib_util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _install_pyqt_stubs():
    pyqt6 = types.ModuleType("PyQt6")
    qtcore = types.ModuleType("PyQt6.QtCore")
    qtgui = types.ModuleType("PyQt6.QtGui")
    qtwidgets = types.ModuleType("PyQt6.QtWidgets")

    class _CursorShape:
        ArrowCursor = object()
        PointingHandCursor = object()
        CrossCursor = object()
        ClosedHandCursor = object()
        OpenHandCursor = object()

    class _FocusPolicy:
        WheelFocus = object()

    class _Qt:
        CursorShape = _CursorShape
        FocusPolicy = _FocusPolicy

    class QPainter:
        class RenderHint:
            Antialiasing = "antialiasing"
            SmoothPixmapTransform = "smooth-pixmap-transform"

    qtcore.Qt = _Qt
    qtcore.QPoint = type("QPoint", (), {})
    qtcore.QPointF = type("QPointF", (), {})
    qtcore.QTimer = type("QTimer", (), {})
    qtcore.pyqtSignal = lambda *args, **kwargs: object()
    qtgui.QWheelEvent = type("QWheelEvent", (), {})
    qtgui.QPixmap = type("QPixmap", (), {})
    qtgui.QPainter = QPainter
    qtgui.QPalette = type("QPalette", (), {})
    qtgui.QColor = type("QColor", (), {})
    qtwidgets.QWidget = type("QWidget", (), {})
    qtwidgets.QMenu = type("QMenu", (), {})
    qtwidgets.QApplication = type("QApplication", (), {})
    pyqt6.QtCore = qtcore
    pyqt6.QtGui = qtgui
    pyqt6.QtWidgets = qtwidgets
    sys.modules["PyQt6"] = pyqt6
    sys.modules["PyQt6.QtCore"] = qtcore
    sys.modules["PyQt6.QtGui"] = qtgui
    sys.modules["PyQt6.QtWidgets"] = qtwidgets


def _install_canvas_dependency_stubs():
    _ensure_package("anylabeling")
    _ensure_package("anylabeling.services")
    _ensure_package("anylabeling.services.auto_labeling")
    types_module = types.ModuleType("anylabeling.services.auto_labeling.types")
    types_module.AutoLabelingMode = type("AutoLabelingMode", (), {})
    sys.modules["anylabeling.services.auto_labeling.types"] = types_module

    _ensure_package("anylabeling.views")
    _ensure_package("anylabeling.views.labeling")
    _ensure_package("anylabeling.views.labeling.widgets")
    utils_package = _ensure_package("anylabeling.views.labeling.utils")
    colormap_module = types.ModuleType(
        "anylabeling.views.labeling.utils.colormap"
    )
    colormap_module.label_colormap = lambda: []
    theme_module = types.ModuleType("anylabeling.views.labeling.utils.theme")
    theme_module.get_theme = lambda: {"background": "#000000"}
    sys.modules["anylabeling.views.labeling.utils.colormap"] = colormap_module
    sys.modules["anylabeling.views.labeling.utils.theme"] = theme_module
    sys.modules["anylabeling.views.labeling.utils"] = utils_package

    shape_module = types.ModuleType("anylabeling.views.labeling.shape")

    class Shape:
        CUBOID_FRONT_LEFT_EDGE_CENTER = 0
        CUBOID_FRONT_RIGHT_EDGE_CENTER = 1
        CUBOID_FRONT_TOP_EDGE_CENTER = 2
        CUBOID_FRONT_BOTTOM_EDGE_CENTER = 3
        CUBOID_BACK_LEFT_EDGE_CENTER = 4
        CUBOID_BACK_RIGHT_EDGE_CENTER = 5

    shape_module.Shape = Shape
    sys.modules["anylabeling.views.labeling.shape"] = shape_module


def _load_render_quality():
    _install_pyqt_stubs()
    _install_canvas_dependency_stubs()
    _ensure_package("anylabeling.views.labeling.viewport", VIEWPORT_DIR)
    return _load_module(
        "anylabeling.views.labeling.viewport.render_quality",
        VIEWPORT_DIR / "render_quality.py",
    )


def _load_canvas_module():
    render_quality_module = _load_render_quality()
    _load_module(
        "anylabeling.views.labeling.viewport.rect",
        VIEWPORT_DIR / "rect.py",
    )
    _load_module(
        "anylabeling.views.labeling.viewport.coordinate_map",
        VIEWPORT_DIR / "coordinate_map.py",
    )
    camera_module = _load_module(
        "anylabeling.views.labeling.viewport.camera",
        VIEWPORT_DIR / "camera.py",
    )
    viewport_package = sys.modules["anylabeling.views.labeling.viewport"]
    viewport_package.Camera2D = camera_module.Camera2D
    viewport_package.RenderQuality = render_quality_module.RenderQuality
    viewport_package.apply_render_quality = (
        render_quality_module.apply_render_quality
    )
    return _load_module(
        "anylabeling.views.labeling.widgets.canvas",
        CANVAS_PATH,
    )


class FakePainter:
    class RenderHint:
        SmoothPixmapTransform = "smooth-pixmap-transform"

    def __init__(self):
        self.render_hints = []

    def setRenderHint(self, hint, enabled=True):
        self.render_hints.append((hint, enabled))


class RenderQualityTest(unittest.TestCase):
    def test_nearest_disables_smooth_pixmap_transform(self):
        module = _load_render_quality()
        painter = FakePainter()

        module.apply_render_quality(painter, module.RenderQuality.NEAREST)

        self.assertEqual(
            painter.render_hints,
            [(FakePainter.RenderHint.SmoothPixmapTransform, False)],
        )

    def test_smooth_and_high_enable_smooth_pixmap_transform(self):
        module = _load_render_quality()

        for quality in (module.RenderQuality.SMOOTH, module.RenderQuality.HIGH):
            with self.subTest(quality=quality):
                painter = FakePainter()

                module.apply_render_quality(painter, quality)

                self.assertEqual(
                    painter.render_hints,
                    [(FakePainter.RenderHint.SmoothPixmapTransform, True)],
                )

    def test_canvas_default_render_quality_is_smooth(self):
        canvas_module = _load_canvas_module()

        self.assertIs(
            canvas_module.Canvas.DEFAULT_RENDER_QUALITY,
            canvas_module.RenderQuality.SMOOTH,
        )


if __name__ == "__main__":
    unittest.main()
