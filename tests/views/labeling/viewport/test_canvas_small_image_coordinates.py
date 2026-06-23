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
    if (
        existing is not None
        and getattr(existing, "__file__", None) == str(path)
        and name != "anylabeling.views.labeling.widgets.canvas"
    ):
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

    class _PenStyle:
        NoPen = object()
        SolidLine = object()
        DashLine = object()

    class _BrushStyle:
        NoBrush = object()

    class _AlignmentFlag:
        AlignCenter = object()

    class _Qt:
        CursorShape = _CursorShape
        FocusPolicy = _FocusPolicy
        PenStyle = _PenStyle
        BrushStyle = _BrushStyle
        AlignmentFlag = _AlignmentFlag

    class QSize:
        def __init__(self, width=0, height=0):
            self._width = int(width)
            self._height = int(height)

        def width(self):
            return self._width

        def height(self):
            return self._height

        def __mul__(self, factor):
            return QSize(round(self._width * factor), round(self._height * factor))

        __rmul__ = __mul__

    class QPointF:
        def __init__(self, x=0.0, y=0.0):
            self._x = float(x)
            self._y = float(y)

        def x(self):
            return self._x

        def y(self):
            return self._y

    class QWidget:
        def size(self):
            return QSize(self.width(), self.height())

        def minimumSizeHint(self):
            return QSize(0, 0)

        def paintEvent(self, _event):
            return None

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
            self._width = int(width)
            self._height = int(height)

        def width(self):
            return self._width

        def height(self):
            return self._height

        def isNull(self):
            return self._width <= 0 or self._height <= 0

        def size(self):
            return QSize(self._width, self._height)

    class QPainter:
        class RenderHint:
            Antialiasing = object()
            SmoothPixmapTransform = object()

        def __init__(self):
            self.transforms = []
            self.scale_calls = []
            self.translate_calls = []
            self.draw_pixmap_calls = []
            self.ended = False

        def begin(self, _device):
            return True

        def setRenderHint(self, *args):
            return None

        def setTransform(self, transform):
            self.transforms.append(transform)

        def scale(self, *args):
            self.scale_calls.append(args)

        def translate(self, *args):
            self.translate_calls.append(args)

        def drawPixmap(self, *args):
            self.draw_pixmap_calls.append(args)

        def end(self):
            self.ended = True

    qtcore.Qt = _Qt
    qtcore.QPoint = QPointF
    qtcore.QPointF = QPointF
    qtcore.QSize = QSize
    qtcore.QTimer = type("QTimer", (), {})
    qtcore.pyqtSignal = lambda *args, **kwargs: object()
    qtgui.QWheelEvent = type("QWheelEvent", (), {})
    qtgui.QPixmap = QPixmap
    qtgui.QPainter = QPainter
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
        scale = 1.0

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
QPixmap = canvas_module.QtGui.QPixmap
Shape = canvas_module.Shape


def _make_canvas(viewport_width=800, viewport_height=600):
    canvas = object.__new__(Canvas)
    canvas.camera = None
    canvas.pixmap = None
    canvas.compare_pixmap = None
    canvas.scale = 3.0
    canvas.shapes = []
    canvas.current = None
    canvas.selected_shapes_copy = []
    canvas.line = None
    canvas._painter = canvas_module.QtGui.QPainter()
    canvas.is_loading = False
    canvas.show_groups = False
    canvas.show_linking = False
    canvas.show_masks = False
    canvas.show_texts = False
    canvas.show_labels = False
    canvas.show_attributes = False
    canvas.show_degrees = False
    canvas.cross_line_show = False
    canvas.split_position = 0.5
    canvas._hide_backround = False
    canvas.h_shape = None
    canvas.width = lambda: viewport_width
    canvas.height = lambda: viewport_height
    canvas.update = lambda: None
    canvas.fill_drawing = lambda: False
    canvas.is_visible = lambda _shape: True
    return canvas


class CanvasSmallImageCoordinatesTest(unittest.TestCase):
    def test_load_pixmap_initializes_camera_from_pixmap_size(self):
        canvas = _make_canvas(640, 480)
        pixmap = QPixmap(320, 240)

        canvas.load_pixmap(pixmap)

        self.assertIsNotNone(canvas.camera)
        self.assertEqual(canvas.camera.image_width, 320)
        self.assertEqual(canvas.camera.image_height, 240)
        self.assertEqual(canvas.camera.viewport_width, 640)
        self.assertEqual(canvas.camera.viewport_height, 480)

    def test_transform_pos_uses_camera_view_to_image_point(self):
        canvas = _make_canvas(800, 600)
        canvas.init_camera_for_image(1000, 750)
        view_point = QPointF(250.25, 125.5)

        transformed = canvas.transform_pos(view_point)
        expected = canvas.view_to_image_point(view_point)

        self.assertTrue(math.isclose(transformed.x(), expected.x(), abs_tol=1e-6))
        self.assertTrue(math.isclose(transformed.y(), expected.y(), abs_tol=1e-6))

    def test_camera_size_hints_do_not_use_scaled_pixmap_size(self):
        canvas = _make_canvas(640, 480)
        canvas.pixmap = QPixmap(320, 240)
        canvas.scale = 5.0
        canvas.init_camera_for_image(320, 240)

        size_hint = canvas.sizeHint()
        minimum_size_hint = canvas.minimumSizeHint()

        self.assertEqual(size_hint.width(), 640)
        self.assertEqual(size_hint.height(), 480)
        self.assertNotEqual(minimum_size_hint.width(), 1600)
        self.assertNotEqual(minimum_size_hint.height(), 1200)

    def test_paint_event_uses_coordinate_map_transform_and_scale(self):
        canvas = _make_canvas(800, 600)
        canvas.pixmap = QPixmap(400, 300)
        canvas.init_camera_for_image(400, 300)
        sentinel_transform = object()
        original = CoordinateMap.image_to_view_qtransform
        CoordinateMap.image_to_view_qtransform = lambda _self: sentinel_transform

        try:
            canvas.paintEvent(None)
        finally:
            CoordinateMap.image_to_view_qtransform = original

        painter = canvas._painter
        self.assertEqual(painter.transforms, [sentinel_transform])
        self.assertEqual(painter.scale_calls, [])
        self.assertEqual(painter.translate_calls, [])
        self.assertEqual(len(painter.draw_pixmap_calls), 1)
        self.assertTrue(
            math.isclose(
                Shape.scale,
                canvas.camera.coordinate_map().scale,
                abs_tol=1e-6,
            )
        )
        self.assertTrue(painter.ended)


if __name__ == "__main__":
    unittest.main()
