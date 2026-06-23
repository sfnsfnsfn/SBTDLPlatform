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


class FakeSignal:
    def __init__(self):
        self.calls = []

    def emit(self, *args):
        self.calls.append(args)


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

    class _MouseButton:
        NoButton = 0
        LeftButton = 1
        RightButton = 2
        MiddleButton = 4

    class _KeyboardModifier:
        NoModifier = 0
        ShiftModifier = 1
        ControlModifier = 2

    class _CursorShape:
        ArrowCursor = object()
        PointingHandCursor = object()
        CrossCursor = object()
        ClosedHandCursor = object()
        OpenHandCursor = object()

    class _FocusPolicy:
        WheelFocus = object()

    class _Orientation:
        Horizontal = object()
        Vertical = object()

    class _Qt:
        MouseButton = _MouseButton
        KeyboardModifier = _KeyboardModifier
        CursorShape = _CursorShape
        FocusPolicy = _FocusPolicy
        Orientation = _Orientation

    class QPointF:
        def __init__(self, x=0.0, y=0.0):
            self._x = float(x)
            self._y = float(y)

        def x(self):
            return self._x

        def y(self):
            return self._y

        def toPoint(self):
            return self

        def __sub__(self, other):
            return QPointF(self.x() - other.x(), self.y() - other.y())

    class QWidget:
        def size(self):
            return types.SimpleNamespace(width=self.width, height=self.height)

        def minimumSizeHint(self):
            return types.SimpleNamespace(width=lambda: 0, height=lambda: 0)

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

    qtcore.Qt = _Qt
    qtcore.QPoint = QPointF
    qtcore.QPointF = QPointF
    qtcore.QTimer = type("QTimer", (), {})
    qtcore.pyqtSignal = lambda *args, **kwargs: FakeSignal()
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
    utils_package.distance = lambda point: (
        point.x() ** 2 + point.y() ** 2
    ) ** 0.5
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
        NEAR_VERTEX = 1

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
    _load_module(
        "anylabeling.views.labeling.viewport.coordinate_map",
        VIEWPORT_DIR / "coordinate_map.py",
    )
    camera_module = _load_module(
        "anylabeling.views.labeling.viewport.camera",
        VIEWPORT_DIR / "camera.py",
    )
    viewport_package = sys.modules["anylabeling.views.labeling.viewport"]
    viewport_package.RectF = rect_module.RectF
    viewport_package.Camera2D = camera_module.Camera2D
    canvas_module = _load_module(
        "anylabeling.views.labeling.widgets.canvas",
        CANVAS_PATH,
    )
    return canvas_module, rect_module.RectF


canvas_module, RectF = _load_canvas_types()
Canvas = canvas_module.Canvas
QPointF = canvas_module.QtCore.QPointF
QPixmap = canvas_module.QtGui.QPixmap
Qt = canvas_module.QtCore.Qt


class WheelEvent:
    def __init__(self, x, y, delta_x=0, delta_y=0, modifiers=0):
        self._position = QPointF(x, y)
        self._delta = QPointF(delta_x, delta_y)
        self._modifiers = modifiers
        self.accepted = False

    def position(self):
        return self._position

    def angleDelta(self):
        return self._delta

    def modifiers(self):
        return self._modifiers

    def accept(self):
        self.accepted = True


class MouseEvent:
    def __init__(self, x, y, button=0, buttons=0, modifiers=0):
        self._position = QPointF(x, y)
        self._button = button
        self._buttons = buttons
        self._modifiers = modifiers

    def position(self):
        return self._position

    def button(self):
        return self._button

    def buttons(self):
        return self._buttons

    def modifiers(self):
        return self._modifiers


def _make_canvas(viewport_width=800, viewport_height=600):
    canvas = object.__new__(Canvas)
    canvas.camera = None
    canvas.pixmap = QPixmap(1000, 750)
    canvas.scale = 1.0
    canvas.mode = Canvas.EDIT
    canvas.selected_shapes = []
    canvas.selected_shapes_copy = []
    canvas.enable_wheel_rectangle_editing = False
    canvas.auto_highlight_shape = False
    canvas.compare_pixmap = None
    canvas.is_loading = False
    canvas.is_auto_labeling = False
    canvas.auto_decode_mode = False
    canvas.auto_decode_tracklet = []
    canvas.h_shape = None
    canvas.h_cuboid_face = None
    canvas.current = None
    canvas.prev_point = None
    canvas.prev_pan_point = QPointF()
    canvas.prev_move_point = QPointF()
    canvas._mid_pan_active = False
    canvas._mid_prev_pos = None
    canvas._pending_edge_point = None
    canvas.moving_shape = False
    canvas.is_move_editing = False
    canvas.zoom_request = FakeSignal()
    canvas.camera_view_changed = FakeSignal()
    canvas.scroll_request = FakeSignal()
    canvas.mode_changed = FakeSignal()
    canvas.shape_hover_changed = FakeSignal()
    canvas.show_shape = FakeSignal()
    canvas.repaint_calls = 0
    canvas.update_calls = 0
    canvas.width = lambda: viewport_width
    canvas.height = lambda: viewport_height
    canvas.repaint = lambda: setattr(
        canvas, "repaint_calls", canvas.repaint_calls + 1
    )
    canvas.update = lambda: setattr(
        canvas, "update_calls", canvas.update_calls + 1
    )
    canvas.override_cursor = lambda _cursor: None
    canvas.restore_cursor = lambda: None
    canvas.selected_vertex = lambda: False
    canvas.selected_cuboid_face = lambda: False
    canvas.selected_edge = lambda: False
    canvas.select_shape_point = lambda *args, **kwargs: None
    canvas.out_off_pixmap = lambda _pos: True
    canvas.init_camera_for_image(1000, 750)
    return canvas


def _assert_rect_close(test_case, actual, expected, abs_tol=1e-6):
    test_case.assertTrue(math.isclose(actual.x0, expected.x0, abs_tol=abs_tol))
    test_case.assertTrue(math.isclose(actual.y0, expected.y0, abs_tol=abs_tol))
    test_case.assertTrue(math.isclose(actual.x1, expected.x1, abs_tol=abs_tol))
    test_case.assertTrue(math.isclose(actual.y1, expected.y1, abs_tol=abs_tol))


class CanvasCameraInteractionsTest(unittest.TestCase):
    def test_wheel_zoom_keeps_cursor_image_coordinate_stable(self):
        canvas = _make_canvas()
        view_point = (250.25, 125.5)
        before = canvas.camera.coordinate_map().view_to_image(*view_point)

        event = WheelEvent(*view_point, delta_y=120)
        canvas.wheelEvent(event)

        after = canvas.camera.coordinate_map().view_to_image(*view_point)
        self.assertTrue(math.isclose(after[0], before[0], abs_tol=1e-6))
        self.assertTrue(math.isclose(after[1], before[1], abs_tol=1e-6))
        self.assertEqual(canvas.zoom_request.calls, [])
        self.assertEqual(len(canvas.camera_view_changed.calls), 1)
        self.assertTrue(event.accepted)

    def test_middle_drag_pan_moves_visible_without_scroll_signal(self):
        canvas = _make_canvas()
        canvas._mid_pan_active = True
        canvas._mid_prev_pos = QPointF(100.0, 100.0)
        old_visible = canvas.camera.visible

        canvas.mouseMoveEvent(MouseEvent(140.0, 70.0))

        _assert_rect_close(
            self,
            canvas.camera.visible,
            old_visible.translated(-50.0, 37.5),
        )
        self.assertEqual(canvas.scroll_request.calls, [])

    def test_blank_left_drag_pan_moves_visible_without_scroll_signal(self):
        canvas = _make_canvas()
        canvas.prev_pan_point = QPointF(100.0, 100.0)
        old_visible = canvas.camera.visible

        event = MouseEvent(
            140.0,
            70.0,
            buttons=Qt.MouseButton.LeftButton,
        )
        canvas.mouseMoveEvent(event)

        _assert_rect_close(
            self,
            canvas.camera.visible,
            old_visible.translated(-50.0, 37.5),
        )
        self.assertEqual(canvas.scroll_request.calls, [])

    def test_blank_left_drag_pan_uses_incremental_delta(self):
        canvas = _make_canvas()
        canvas.prev_pan_point = QPointF(100.0, 100.0)
        old_visible = canvas.camera.visible

        canvas.mouseMoveEvent(
            MouseEvent(140.0, 70.0, buttons=Qt.MouseButton.LeftButton)
        )
        canvas.mouseMoveEvent(
            MouseEvent(160.0, 80.0, buttons=Qt.MouseButton.LeftButton)
        )

        _assert_rect_close(
            self,
            canvas.camera.visible,
            old_visible.translated(-75.0, 25.0),
        )
        self.assertTrue(math.isclose(canvas.prev_pan_point.x(), 160.0))
        self.assertTrue(math.isclose(canvas.prev_pan_point.y(), 80.0))

    def test_ctrl_wheel_pan_moves_visible_without_scroll_signal(self):
        canvas = _make_canvas()
        old_visible = canvas.camera.visible

        event = WheelEvent(
            0.0,
            0.0,
            delta_x=40.0,
            delta_y=-20.0,
            modifiers=Qt.KeyboardModifier.ControlModifier,
        )
        canvas.wheelEvent(event)

        _assert_rect_close(
            self,
            canvas.camera.visible,
            old_visible.translated(-50.0, 25.0),
        )
        self.assertEqual(canvas.scroll_request.calls, [])
        self.assertEqual(len(canvas.camera_view_changed.calls), 1)
        self.assertTrue(event.accepted)

    def test_close_enough_uses_camera_scale_when_camera_is_active(self):
        canvas = _make_canvas()
        canvas.epsilon = 10
        canvas.scale = 1.0
        canvas.camera.set_scale_around_center(2.0)

        is_close = canvas.close_enough(QPointF(0.0, 0.0), QPointF(7.0, 0.0))

        self.assertFalse(is_close)

    def test_fit_window_visible_contains_full_image(self):
        canvas = _make_canvas(500, 500)
        canvas.camera.zoom_at_view_point(250.0, 250.0, 2.0)

        canvas.camera.fit_to_window()

        self.assertLessEqual(canvas.camera.visible.x0, 0.0)
        self.assertLessEqual(canvas.camera.visible.y0, 0.0)
        self.assertGreaterEqual(canvas.camera.visible.x1, 1000.0)
        self.assertGreaterEqual(canvas.camera.visible.y1, 750.0)


class CanvasIntersectionPointTest(unittest.TestCase):
    def test_intersection_point_uses_camera_size_without_pixmap(self):
        canvas = _make_canvas()
        canvas.pixmap = None

        point = canvas.intersection_point(
            QPointF(500.0, 375.0),
            QPointF(1200.0, 375.0),
        )

        self.assertEqual(point.x(), 999)
        self.assertEqual(point.y(), 375)

    def test_intersection_point_clamps_when_no_edge_intersection(self):
        canvas = _make_canvas()
        canvas.pixmap = None

        point = canvas.intersection_point(
            QPointF(500.0, 375.0),
            QPointF(500.0, 375.0),
        )

        self.assertEqual(point.x(), 500.0)
        self.assertEqual(point.y(), 375.0)


if __name__ == "__main__":
    unittest.main()
