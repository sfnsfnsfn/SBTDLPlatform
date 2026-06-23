import math
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
    existing = sys.modules.get(name)
    if existing is not None and getattr(existing, "__file__", None) == str(path):
        return existing
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

    class QPointF:
        def __init__(self, x=0.0, y=0.0):
            self._x = float(x)
            self._y = float(y)

        def x(self):
            return self._x

        def y(self):
            return self._y

    class QWidget:
        pass

    class QApplication:
        @staticmethod
        def overrideCursor():
            return None

        @staticmethod
        def setOverrideCursor(_cursor):
            return None

        @staticmethod
        def changeOverrideCursor(_cursor):
            return None

        @staticmethod
        def restoreOverrideCursor():
            return None

    class QPixmap:
        def __init__(self, width=0, height=0):
            self._width = width
            self._height = height

        def width(self):
            return self._width

        def height(self):
            return self._height

        def isNull(self):
            return self._width <= 0 or self._height <= 0

    qtcore.Qt = _Qt
    qtcore.QPoint = QPointF
    qtcore.QPointF = QPointF
    qtcore.QTimer = type("QTimer", (), {})
    qtcore.pyqtSignal = lambda *args, **kwargs: object()
    qtgui.QWheelEvent = type("QWheelEvent", (), {})
    qtgui.QPixmap = QPixmap
    qtgui.QPainter = type("QPainter", (), {})
    qtgui.QPalette = type("QPalette", (), {})
    qtgui.QColor = type("QColor", (), {})
    qtwidgets.QWidget = QWidget
    qtwidgets.QMenu = type("QMenu", (), {})
    qtwidgets.QApplication = QApplication
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


def _load_canvas_types():
    _install_pyqt_stubs()
    _install_canvas_dependency_stubs()
    _ensure_package("anylabeling.views.labeling.viewport", VIEWPORT_DIR)
    rect_module = _load_module(
        "anylabeling.views.labeling.viewport.rect",
        VIEWPORT_DIR / "rect.py",
    )
    coordinate_map_module = _load_module(
        "anylabeling.views.labeling.viewport.coordinate_map",
        VIEWPORT_DIR / "coordinate_map.py",
    )
    camera_module = _load_module(
        "anylabeling.views.labeling.viewport.camera",
        VIEWPORT_DIR / "camera.py",
    )
    viewport_package = sys.modules["anylabeling.views.labeling.viewport"]
    viewport_package.RectF = rect_module.RectF
    viewport_package.CoordinateMap = coordinate_map_module.CoordinateMap
    viewport_package.Camera2D = camera_module.Camera2D
    canvas_module = _load_module(
        "anylabeling.views.labeling.widgets.canvas",
        CANVAS_PATH,
    )
    return canvas_module, coordinate_map_module.CoordinateMap


canvas_module, CoordinateMap = _load_canvas_types()
Canvas = canvas_module.Canvas
QPointF = canvas_module.QtCore.QPointF


def _make_canvas(viewport_width=800, viewport_height=600):
    canvas = object.__new__(Canvas)
    canvas.camera = None
    canvas.pixmap = None
    canvas.width = lambda: viewport_width
    canvas.height = lambda: viewport_height
    return canvas


class CanvasCameraStateTest(unittest.TestCase):
    def test_camera_can_be_initialized_for_image(self):
        canvas = _make_canvas(800, 400)

        camera = canvas.init_camera_for_image(1000, 500)

        self.assertIs(camera, canvas.camera)
        self.assertEqual(camera.image_width, 1000)
        self.assertEqual(camera.image_height, 500)
        self.assertEqual(camera.viewport_width, 800)
        self.assertEqual(camera.viewport_height, 400)
        self.assertGreater(camera.visible.width, 0.0)
        self.assertGreater(camera.visible.height, 0.0)

    def test_set_camera_viewport_updates_existing_camera(self):
        canvas = _make_canvas(800, 600)
        canvas.init_camera_for_image(1000, 800)
        center_x = canvas.camera.visible.center_x
        center_y = canvas.camera.visible.center_y

        camera = canvas.set_camera_viewport(400, 200)

        self.assertIs(camera, canvas.camera)
        self.assertEqual(camera.viewport_width, 400)
        self.assertEqual(camera.viewport_height, 200)
        self.assertTrue(math.isclose(camera.visible.center_x, center_x))
        self.assertTrue(math.isclose(camera.visible.center_y, center_y))
        self.assertTrue(
            math.isclose(
                camera.visible.width / camera.visible.height,
                2.0,
                abs_tol=1e-6,
            )
        )

    def test_set_camera_viewport_does_not_invent_image_world(self):
        canvas = _make_canvas(800, 600)

        camera = canvas.set_camera_viewport(400, 300)

        self.assertIsNone(camera)
        self.assertIsNone(canvas.camera)

    def test_set_camera_viewport_can_initialize_from_pixmap(self):
        canvas = _make_canvas(800, 600)
        canvas.pixmap = canvas_module.QtGui.QPixmap(1000, 750)

        camera = canvas.set_camera_viewport(400, 300)

        self.assertIs(camera, canvas.camera)
        self.assertEqual(camera.image_width, 1000)
        self.assertEqual(camera.image_height, 750)
        self.assertEqual(camera.viewport_width, 400)
        self.assertEqual(camera.viewport_height, 300)

    def test_canvas_coordinate_wrappers_match_coordinate_map(self):
        canvas = _make_canvas(800, 600)
        canvas.init_camera_for_image(1000, 750)
        coordinate_map = canvas.camera.coordinate_map()
        view_point = QPointF(250.25, 125.5)

        image_point = canvas.view_to_image_point(view_point)
        expected_image = coordinate_map.view_to_image(
            view_point.x(),
            view_point.y(),
        )

        self.assertTrue(
            math.isclose(image_point.x(), expected_image[0], abs_tol=1e-6)
        )
        self.assertTrue(
            math.isclose(image_point.y(), expected_image[1], abs_tol=1e-6)
        )

        view_round_trip = canvas.image_to_view_point(image_point)
        expected_view = coordinate_map.image_to_view(
            image_point.x(),
            image_point.y(),
        )

        self.assertTrue(
            math.isclose(view_round_trip.x(), expected_view[0], abs_tol=1e-6)
        )
        self.assertTrue(
            math.isclose(view_round_trip.y(), expected_view[1], abs_tol=1e-6)
        )


if __name__ == "__main__":
    unittest.main()
