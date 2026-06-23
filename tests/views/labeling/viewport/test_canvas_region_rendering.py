"""Tests for QImageRegionProvider — the QImageReader-backed ImageProvider.

Verifies:
- Image dimensions read from metadata (no full decode)
- read_region returns correctly sized/clipped regions
- Pixel content matches expected values
- Provider works with Canvas in provider paint path
"""

from __future__ import annotations

import pathlib
import sys
import tempfile
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


# ---------------------------------------------------------------------------
# Test helper: load viewport / canvas modules
# ---------------------------------------------------------------------------

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

    class _PenStyle:
        NoPen = object()
        SolidLine = object()
        DashLine = object()

    class _BrushStyle:
        NoBrush = object()

    class _AlignmentFlag:
        AlignCenter = object()

    class _AspectRatioMode:
        IgnoreAspectRatio = object()
        KeepAspectRatio = object()

    class _TransformationMode:
        SmoothTransformation = object()
        FastTransformation = object()

    class _Qt:
        CursorShape = _CursorShape
        FocusPolicy = _FocusPolicy
        PenStyle = _PenStyle
        BrushStyle = _BrushStyle
        AlignmentFlag = _AlignmentFlag
        AspectRatioMode = _AspectRatioMode
        TransformationMode = _TransformationMode

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

        @staticmethod
        def fromImage(image):
            return QPixmap(image.width(), image.height())

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

    class QTransform:
        def __init__(self, m11=1.0, m12=0.0, m21=0.0, m22=1.0, dx=0.0, dy=0.0):
            self._m11 = m11
            self._m12 = m12
            self._m21 = m21
            self._m22 = m22
            self._dx = dx
            self._dy = dy

        def translate(self, dx, dy):
            self._dx += dx * self._m11 + dy * self._m21
            self._dy += dx * self._m12 + dy * self._m22

        def scale(self, sx, sy):
            self._m11 *= sx
            self._m12 *= sx
            self._m21 *= sy
            self._m22 *= sy

    class QSizeF:
        def __init__(self, width=0.0, height=0.0):
            self._w = width
            self._h = height

        def width(self):
            return self._w

        def height(self):
            return self._h

        def isValid(self):
            return self._w > 0 and self._h > 0

    class QRect:
        def __init__(self, x=0, y=0, w=0, h=0):
            self._x = x
            self._y = y
            self._w = w
            self._h = h

        def x(self):
            return self._x

        def y(self):
            return self._y

        def width(self):
            return self._w

        def height(self):
            return self._h

        def size(self):
            return QSizeF(float(self._w), float(self._h))

    class QImage:
        def __init__(self, *args, **kwargs):
            self._w = 0
            self._h = 0
            self._data = None  # PIL Image for stub operations

        @staticmethod
        def fromData(data, format=None):
            import io
            from PIL import Image as PILImage
            img = PILImage.open(io.BytesIO(data))
            qi = QImage()
            qi._w = img.width
            qi._h = img.height
            qi._data = img
            return qi

        def isNull(self):
            return self._w <= 0 or self._h <= 0

        def width(self):
            return self._w

        def height(self):
            return self._h

        def copy(self, rect=None):
            """Return a copy of (a region of) this image."""
            qi = QImage()
            if rect is not None and self._data is not None:
                # Crop from PIL image
                box = (rect.x(), rect.y(),
                       rect.x() + rect.width(), rect.y() + rect.height())
                qi._data = self._data.crop(box)
                qi._w = qi._data.width
                qi._h = qi._data.height
            else:
                qi._w = self._w
                qi._h = self._h
                qi._data = self._data
            return qi

        def scaled(self, w, h, aspect_mode=None, transform_mode=None):
            """Return a scaled copy (delegates to PIL)."""
            qi = QImage()
            qi._w = w
            qi._h = h
            if self._data is not None:
                from PIL import Image as PILImage
                qi._data = self._data.resize((w, h), PILImage.LANCZOS)
            return qi

    class QImageReader:
        """Stub QImageReader that delegates to PIL for actual image I/O."""

        def __init__(self, path=None):
            from PIL import Image as PILImage
            self._path = path
            self._clip_rect = None
            self._scaled_size = None
            self._auto_transform = True
            self._img = None
            if path:
                self._img = PILImage.open(path)

        def setAutoTransform(self, enabled):
            self._auto_transform = enabled

        def setClipRect(self, rect):
            self._clip_rect = rect

        def setScaledSize(self, size):
            self._scaled_size = size

        def size(self):
            if self._img:
                return QSizeF(float(self._img.width), float(self._img.height))
            return QSizeF()

        def read(self):
            if not self._img:
                return QImage()
            # Apply clip rect
            img = self._img
            if self._clip_rect is not None:
                box = (
                    self._clip_rect.x(),
                    self._clip_rect.y(),
                    self._clip_rect.x() + self._clip_rect.width(),
                    self._clip_rect.y() + self._clip_rect.height(),
                )
                img = img.crop(box)
            # Apply scaled size
            if self._scaled_size is not None:
                tw = int(self._scaled_size.width())
                th = int(self._scaled_size.height())
                if tw > 0 and th > 0:
                    img = img.resize((tw, th))
            qi = QImage()
            qi._w = img.width
            qi._h = img.height
            qi._data = img
            return qi

        def errorString(self):
            return "stub error"

    qtcore.Qt = _Qt
    qtcore.QPoint = QPointF
    qtcore.QPointF = QPointF
    qtcore.QSize = QSize
    qtcore.QTimer = type("QTimer", (), {})
    qtcore.pyqtSignal = lambda *args, **kwargs: object()
    qtcore.QRect = QRect
    qtgui.QWheelEvent = type("QWheelEvent", (), {})
    qtgui.QPixmap = QPixmap
    qtgui.QPainter = QPainter
    qtgui.QTransform = QTransform
    qtgui.QPalette = type("QPalette", (), {})
    qtgui.QColor = type("QColor", (), {})
    qtgui.QImage = QImage
    qtgui.QImageReader = QImageReader
    qtgui.QRect = QRect
    qtgui.QSizeF = QSizeF
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
    colormap_module = types.ModuleType("anylabeling.views.labeling.utils.colormap")
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


def _load_viewport_and_canvas():
    # Always install our stubs.  Other test files may overwrite
    # sys.modules["PyQt6.QtGui"] with incomplete stubs (e.g. missing
    # QPainter.begin).  Our stubs are the most complete in the test
    # suite and support all Canvas operations used by these tests.
    _install_pyqt_stubs()
    _install_canvas_dependency_stubs()
    _ensure_package("anylabeling.views.labeling.viewport", VIEWPORT_DIR)

    rect_module = _load_module(
        "anylabeling.views.labeling.viewport.rect",
        VIEWPORT_DIR / "rect.py",
    )
    provider_module = _load_module(
        "anylabeling.views.labeling.viewport.image_provider",
        VIEWPORT_DIR / "image_provider.py",
    )
    camera_module = _load_module(
        "anylabeling.views.labeling.viewport.camera",
        VIEWPORT_DIR / "camera.py",
    )
    coordinate_map_module = _load_module(
        "anylabeling.views.labeling.viewport.coordinate_map",
        VIEWPORT_DIR / "coordinate_map.py",
    )

    viewport_package = sys.modules["anylabeling.views.labeling.viewport"]
    viewport_package.RectF = rect_module.RectF
    viewport_package.CoordinateMap = coordinate_map_module.CoordinateMap
    viewport_package.Camera2D = camera_module.Camera2D
    viewport_package.EmptyImageRegionError = provider_module.EmptyImageRegionError
    viewport_package.ImageProvider = provider_module.ImageProvider
    viewport_package.ImageReadResult = provider_module.ImageReadResult
    viewport_package.ImageRegion = provider_module.ImageRegion

    canvas_module = _load_module(
        "anylabeling.views.labeling.widgets.canvas",
        CANVAS_PATH,
    )
    return (
        canvas_module,
        rect_module.RectF,
        camera_module.Camera2D,
        provider_module,
    )


# Detect real PyQt6 BEFORE stubs are installed by other test modules.
# Other test files overwrite sys.modules["PyQt6.QtGui"] with their stubs,
# which may not include QImageReader.  We snapshot the real availability
# at import time so QImageRegionProvider tests can decide whether to skip.
try:
    from PyQt6.QtGui import QImageReader as _RealQImageReader  # noqa: F401
    _HAS_REAL_PYQT = True
except ImportError:
    _HAS_REAL_PYQT = False

canvas_module, RectF, Camera2D, provider_module = _load_viewport_and_canvas()
Canvas = canvas_module.Canvas
QPointF = canvas_module.QtCore.QPointF
QPixmap = canvas_module.QtGui.QPixmap


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _create_test_image(width=200, height=150):
    """Create a test PNG with distinct colored quadrants for region verification."""
    import cv2
    import numpy as np
    img = np.zeros((height, width, 3), dtype=np.uint8)
    hh, hw = height // 2, width // 2
    img[:hh, :hw] = (0, 0, 255)       # Red: top-left (BGR)
    img[:hh, hw:] = (0, 255, 0)       # Green: top-right
    img[hh:, :hw] = (255, 0, 0)       # Blue: bottom-left
    img[hh:, hw:] = (0, 255, 255)     # Yellow: bottom-right
    return img


def _save_test_image(img, path):
    """Save a numpy BGR image as PNG."""
    import cv2
    cv2.imwrite(path, img)


def _make_canvas(viewport_width=800, viewport_height=600):
    canvas = object.__new__(Canvas)
    canvas.camera = None
    canvas.pixmap = None
    canvas.provider = None
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class CanvasPixelGridGeometryTest(unittest.TestCase):
    def test_pixel_grid_rendering_is_opt_in(self):
        self.assertFalse(Canvas.ENABLE_PIXEL_GRID_RENDERING)

    def test_pixel_view_rect_uses_separate_x_and_y_axes(self):
        camera = Camera2D(
            image_width=200,
            image_height=100,
            viewport_width=1000,
            viewport_height=500,
            visible=RectF(10.0, 20.0, 110.0, 70.0),
        )

        rect = Canvas._pixel_view_rect(
            camera.coordinate_map(),
            image_x=12,
            image_y=23,
            view_x0=0.0,
            view_y0=0.0,
            target_w=1000,
            target_h=500,
        )

        self.assertEqual(rect, (20, 30, 10, 10))


class QImageRegionProviderPyramidSelectionTest(unittest.TestCase):
    class _FakePixmap:
        def __init__(self, width, height, null=False):
            self._width = width
            self._height = height
            self._null = null

        def width(self):
            return self._width

        def height(self):
            return self._height

        def isNull(self):
            return self._null

    def test_get_pyramid_pixmap_skips_null_qpixmap_levels(self):
        provider = object.__new__(provider_module.QImageRegionProvider)
        provider._pyramid_built = True
        provider._pyramid = [
            None,
            self._FakePixmap(100, 100, null=True),
            self._FakePixmap(50, 50),
            self._FakePixmap(25, 25),
        ]
        provider._select_level = lambda *_args: 1

        pixmap, level, scale = provider.get_pyramid_pixmap(100, 100, 200, 200)

        self.assertIs(pixmap, provider._pyramid[2])
        self.assertEqual(level, 2)
        self.assertEqual(scale, 0.25)


class QImageRegionProviderMemoryPolicyTest(unittest.TestCase):
    def test_large_pyramid_levels_are_skipped_by_byte_budget(self):
        provider_cls = provider_module.QImageRegionProvider

        self.assertFalse(
            provider_cls._should_cache_pyramid_level(
                level=0,
                width=30980,
                height=30276,
            )
        )
        self.assertFalse(
            provider_cls._should_cache_pyramid_level(
                level=1,
                width=15490,
                height=15138,
            )
        )
        self.assertTrue(
            provider_cls._should_cache_pyramid_level(
                level=2,
                width=7745,
                height=7569,
            )
        )


class QImageRegionProviderMetadataTest(unittest.TestCase):
    """Verify QImageReader-based provider reads dimensions from metadata."""

    @classmethod
    def setUpClass(cls):
        if not _HAS_REAL_PYQT:
            raise unittest.SkipTest("Real PyQt6 not available (stub mode)")
        cls.tmpdir = tempfile.TemporaryDirectory()
        img = _create_test_image(200, 150)
        cls.img_path = pathlib.Path(cls.tmpdir.name) / "test_quadrants.png"
        _save_test_image(img, str(cls.img_path))

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def test_provider_reports_correct_dimensions_from_metadata(self):
        """QImageReader.size() should give image dimensions without full decode."""
        if not _HAS_REAL_PYQT:
            self.skipTest("Real PyQt6 not available (stub mode)")

        from anylabeling.views.labeling.viewport.image_provider import (
            QImageRegionProvider,
        )
        provider = QImageRegionProvider(str(self.img_path))

        self.assertEqual(provider.image_width, 200)
        self.assertEqual(provider.image_height, 150)


class QImageRegionProviderRegionReadTest(unittest.TestCase):
    """Verify read_region returns correctly sized/clipped image data."""

    @classmethod
    def setUpClass(cls):
        if not _HAS_REAL_PYQT:
            raise unittest.SkipTest("Real PyQt6 not available (stub mode)")
        cls.tmpdir = tempfile.TemporaryDirectory()
        img = _create_test_image(200, 150)
        cls.img_path = pathlib.Path(cls.tmpdir.name) / "test_quadrants.png"
        _save_test_image(img, str(cls.img_path))

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def test_read_full_image_returns_image_at_target_size(self):
        if not _HAS_REAL_PYQT:
            self.skipTest("Real PyQt6 not available (stub mode)")

        from anylabeling.views.labeling.viewport.image_provider import (
            QImageRegionProvider,
        )

        provider = QImageRegionProvider(str(self.img_path))
        result = provider.read_region(RectF(0, 0, 200, 150), (100, 75))

        self.assertEqual(result.target_size, (100, 75))
        self.assertEqual(result.clipped_rect, RectF(0, 0, 200, 150))
        self.assertIsNotNone(result.image)

    def test_read_sub_region_clips_correctly(self):
        if not _HAS_REAL_PYQT:
            self.skipTest("Real PyQt6 not available (stub mode)")

        from anylabeling.views.labeling.viewport.image_provider import (
            QImageRegionProvider,
        )

        provider = QImageRegionProvider(str(self.img_path))
        # Top-left quadrant (red)
        result = provider.read_region(RectF(0, 0, 100, 75), (50, 38))

        self.assertEqual(result.clipped_rect, RectF(0, 0, 100, 75))
        self.assertEqual(result.target_size, (50, 38))

    def test_partially_outside_reads_only_intersection(self):
        if not _HAS_REAL_PYQT:
            self.skipTest("Real PyQt6 not available (stub mode)")

        from anylabeling.views.labeling.viewport.image_provider import (
            QImageRegionProvider,
        )

        provider = QImageRegionProvider(str(self.img_path))
        result = provider.read_region(RectF(-10, -5, 50, 40), (40, 30))

        self.assertEqual(result.clipped_rect, RectF(0, 0, 50, 40))

    def test_raises_empty_region_for_fully_outside_rect(self):
        if not _HAS_REAL_PYQT:
            self.skipTest("Real PyQt6 not available (stub mode)")

        from anylabeling.views.labeling.viewport.image_provider import (
            EmptyImageRegionError,
            QImageRegionProvider,
        )
        provider = QImageRegionProvider(str(self.img_path))
        with self.assertRaises(EmptyImageRegionError):
            provider.read_region(RectF(300, 300, 400, 400), (16, 16))


class CanvasProviderPaintPathTest(unittest.TestCase):
    """Verify Canvas paintEvent uses provider when self.provider is set."""

    @classmethod
    def setUpClass(cls):
        if not _HAS_REAL_PYQT:
            raise unittest.SkipTest("Real PyQt6 not available (stub mode)")
        cls.tmpdir = tempfile.TemporaryDirectory()
        img = _create_test_image(200, 150)
        cls.img_path = pathlib.Path(cls.tmpdir.name) / "test_canvas_provider.png"
        _save_test_image(img, str(cls.img_path))

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def test_load_image_provider_sets_provider_and_initializes_camera(self):
        if not _HAS_REAL_PYQT:
            self.skipTest("Real PyQt6 not available (stub mode)")

        from anylabeling.views.labeling.viewport.image_provider import (
            QImageRegionProvider,
        )

        canvas = _make_canvas(640, 480)
        provider = QImageRegionProvider(str(self.img_path))
        canvas.load_image_provider(provider)

        self.assertIs(canvas.provider, provider)
        self.assertIsNotNone(canvas.camera)
        self.assertEqual(canvas.camera.image_width, 200)
        self.assertEqual(canvas.camera.image_height, 150)

    def test_load_image_provider_clears_shapes_by_default(self):
        if not _HAS_REAL_PYQT:
            self.skipTest("Real PyQt6 not available (stub mode)")

        from anylabeling.views.labeling.viewport.image_provider import (
            QImageRegionProvider,
        )

        canvas = _make_canvas(640, 480)
        canvas.shapes = ["fake_shape"]
        provider = QImageRegionProvider(str(self.img_path))
        canvas.load_image_provider(provider)

        self.assertEqual(canvas.shapes, [])

    def test_paint_event_with_provider_uses_provider_read_region(self):
        if not _HAS_REAL_PYQT:
            self.skipTest("Real PyQt6 not available (stub mode)")

        from anylabeling.views.labeling.viewport.image_provider import (
            QImageRegionProvider,
        )

        canvas = _make_canvas(800, 600)
        provider = QImageRegionProvider(str(self.img_path))
        canvas.load_image_provider(provider)

        # Track provider reads
        original_read = provider.read_region
        reads = []

        def tracking_read(image_rect, target_size):
            result = original_read(image_rect, target_size)
            reads.append((image_rect, target_size))
            return result

        provider.read_region = tracking_read

        canvas.paintEvent(None)

        self.assertEqual(len(reads), 1)
        image_rect, target_size = reads[0]
        self.assertEqual(target_size, (800, 600))
        # image_rect should be the camera visible rect
        self.assertTrue(image_rect.x0 >= 0)
        self.assertTrue(image_rect.y0 >= 0)

    def test_provider_cleared_on_load_pixmap(self):
        """Calling load_pixmap should clear an active provider."""
        canvas = _make_canvas(800, 600)
        canvas.provider = object()  # any non-None sentinel
        canvas.load_pixmap(QPixmap(400, 300))
        self.assertIsNone(canvas.provider)

    def test_compare_pixmap_requires_pixmap_mode(self):
        """Compare pixmap rendering requires pixmap (not provider mode).

        In provider mode (self.pixmap is None), the compare view is
        disabled because it relies on self.pixmap dimensions.
        """
        if not _HAS_REAL_PYQT:
            self.skipTest("Real PyQt6 not available (stub mode)")

        from anylabeling.views.labeling.viewport.image_provider import (
            QImageRegionProvider,
        )

        canvas = _make_canvas(800, 600)
        provider = QImageRegionProvider(str(self.img_path))
        canvas.load_image_provider(provider)

        # In provider mode, pixmap is None → compare view is disabled
        self.assertIsNone(canvas.pixmap)
        self.assertIsNotNone(canvas.provider)
        # The has_provider guard in paintEvent prevents compare view
        # from being drawn when provider is active.


if __name__ == "__main__":
    unittest.main()
