import math
import pathlib
import sys
import tempfile
import types
import unittest
from importlib import util as importlib_util

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
LABELING_DIR = REPO_ROOT / "anylabeling" / "views" / "labeling"
VIEWPORT_DIR = LABELING_DIR / "viewport"


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

    class QPointF:
        def __init__(self, x=0.0, y=0.0):
            self._x = float(x)
            self._y = float(y)

        def x(self):
            return self._x

        def y(self):
            return self._y

        def __eq__(self, other):
            return self.x() == other.x() and self.y() == other.y()

        def __add__(self, other):
            return QPointF(self.x() + other.x(), self.y() + other.y())

        def __sub__(self, other):
            return QPointF(self.x() - other.x(), self.y() - other.y())

    class QColor:
        def __init__(self, *args):
            self.args = args

        def red(self):
            return self.args[0] if len(self.args) > 0 else 0

        def green(self):
            return self.args[1] if len(self.args) > 1 else 0

        def blue(self):
            return self.args[2] if len(self.args) > 2 else 0

    qtcore.QPointF = QPointF
    qtgui.QColor = QColor
    qtgui.QPainter = type("QPainter", (), {})
    qtgui.QPainterPath = type("QPainterPath", (), {})
    pyqt6.QtCore = qtcore
    pyqt6.QtGui = qtgui
    sys.modules["PyQt6"] = pyqt6
    sys.modules["PyQt6.QtCore"] = qtcore
    sys.modules["PyQt6.QtGui"] = qtgui


def _install_label_file_dependency_stubs():
    pil_module = types.ModuleType("PIL")
    pil_image_module = types.ModuleType("PIL.Image")
    pil_image_file_module = types.ModuleType("PIL.ImageFile")
    pil_image_module.MAX_IMAGE_PIXELS = None
    pil_image_file_module.LOAD_TRUNCATED_IMAGES = False
    pil_module.Image = pil_image_module
    pil_module.ImageFile = pil_image_file_module
    sys.modules["PIL"] = pil_module
    sys.modules["PIL.Image"] = pil_image_module
    sys.modules["PIL.ImageFile"] = pil_image_file_module

    _ensure_package("anylabeling")
    app_info = types.ModuleType("anylabeling.app_info")
    app_info.__version__ = "test"
    sys.modules["anylabeling.app_info"] = app_info

    _ensure_package("anylabeling.views")
    _ensure_package("anylabeling.views.labeling", LABELING_DIR)

    logger_module = types.ModuleType("anylabeling.views.labeling.logger")

    class Logger:
        def warning(self, *_args, **_kwargs):
            return None

        def error(self, *_args, **_kwargs):
            return None

    logger_module.logger = Logger()
    sys.modules["anylabeling.views.labeling.logger"] = logger_module

    schema_module = types.ModuleType("anylabeling.views.labeling.schema")
    schema_module.XLABEL_BASIC_FIELDS = [
        "version",
        "flags",
        "checked",
        "shapes",
        "imagePath",
        "imageData",
        "imageHeight",
        "imageWidth",
    ]

    def create_xlabel_template(
        version="test",
        flags=None,
        checked=False,
        shapes=None,
        image_path="",
        image_data=None,
        image_height=-1,
        image_width=-1,
    ):
        return {
            "version": version,
            "flags": flags if flags is not None else {},
            "checked": checked,
            "shapes": shapes if shapes is not None else [],
            "imagePath": image_path,
            "imageData": image_data,
            "imageHeight": image_height,
            "imageWidth": image_width,
        }

    schema_module.create_xlabel_template = create_xlabel_template
    sys.modules["anylabeling.views.labeling.schema"] = schema_module

    utils_module = types.ModuleType("anylabeling.views.labeling.utils")
    utils_module.io_open = open

    class ImageArray:
        shape = (720, 1280, 3)

    utils_module.img_b64_to_arr = lambda _data: ImageArray()

    def rectangle_from_diagonal(points):
        (x0, y0), (x1, y1) = points
        return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]

    utils_module.rectangle_from_diagonal = rectangle_from_diagonal
    sys.modules["anylabeling.views.labeling.utils"] = utils_module

    converter_module = types.ModuleType(
        "anylabeling.views.labeling.label_converter"
    )

    class LabelConverter:
        @staticmethod
        def calculate_bounding_box(poly):
            x_values, y_values = zip(*poly)
            return min(x_values), min(y_values), max(x_values), max(y_values)

    converter_module.LabelConverter = LabelConverter
    sys.modules["anylabeling.views.labeling.label_converter"] = converter_module


def _load_types():
    _install_pyqt_stubs()
    _install_label_file_dependency_stubs()
    _ensure_package("anylabeling.views.labeling.viewport", VIEWPORT_DIR)
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
    shape_module = _load_module(
        "anylabeling.views.labeling.shape",
        LABELING_DIR / "shape.py",
    )
    label_file_module = _load_module(
        "anylabeling.views.labeling.label_file",
        LABELING_DIR / "label_file.py",
    )
    return (
        camera_module.Camera2D,
        shape_module.Shape,
        label_file_module.LabelFile,
        sys.modules["PyQt6.QtCore"].QPointF,
    )


Camera2D, Shape, LabelFile, QPointF = _load_types()


def _make_shape(label, shape_type, points):
    shape = Shape(label=label, shape_type=shape_type)
    for x, y in points:
        shape.add_point(QPointF(x, y))
    if shape_type in {"rectangle", "polygon"}:
        shape.close()
    return shape


def _shape_points(shape):
    return [(point.x(), point.y()) for point in shape.points]


def _assert_points_close(test_case, actual, expected, abs_tol=1e-6):
    test_case.assertEqual(len(actual), len(expected))
    for actual_point, expected_point in zip(actual, expected):
        test_case.assertTrue(
            math.isclose(actual_point[0], expected_point[0], abs_tol=abs_tol)
        )
        test_case.assertTrue(
            math.isclose(actual_point[1], expected_point[1], abs_tol=abs_tol)
        )


def _simulate_camera_operations():
    camera = Camera2D(1280, 720, 640, 360)
    camera.fit_to_window()
    camera.zoom_at_view_point(321.25, 120.5, 1.1)
    camera.pan_by_view_delta(80.0, -35.0)
    camera.resize_viewport(800, 600, keep_center=True)
    camera.zoom_at_view_point(400.0, 300.0, 0.9)
    return camera


class LabelRoundTripCoordinatesTest(unittest.TestCase):
    def test_shapes_save_and_reload_in_image_coordinates_after_camera_changes(self):
        shapes = [
            _make_shape(
                "rect",
                "rectangle",
                [
                    (300.75, 100.125),
                    (120.5, 100.125),
                    (120.5, 220.625),
                    (300.75, 220.625),
                ],
            ),
            _make_shape(
                "poly",
                "polygon",
                [
                    (10.5, 20.25),
                    (80.75, 30.5),
                    (120.125, 90.875),
                    (50.625, 140.25),
                ],
            ),
            _make_shape("point", "point", [(512.5, 256.25)]),
        ]
        original_points = {shape.label: _shape_points(shape) for shape in shapes}

        _simulate_camera_operations()

        for shape in shapes:
            _assert_points_close(
                self,
                _shape_points(shape),
                original_points[shape.label],
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = pathlib.Path(tmpdir) / "image.png"
            image_path.write_bytes(b"not a real image; imageData avoids decoding")
            label_path = pathlib.Path(tmpdir) / "image.json"

            LabelFile().save(
                filename=str(label_path),
                shapes=[shape.to_dict() for shape in shapes],
                image_path=image_path.name,
                image_height=720,
                image_width=1280,
                image_data=b"fake image bytes",
                other_data={"checked": False},
            )

            reloaded = LabelFile(str(label_path))

        loaded_points = {
            shape.label: _shape_points(shape) for shape in reloaded.shapes
        }

        # LabelFile.save canonicalizes rectangle vertices to bounding-box order
        # and keeps float image/world coordinates in JSON.
        expected_rectangle = [
            (120.5, 100.125),
            (300.75, 100.125),
            (300.75, 220.625),
            (120.5, 220.625),
        ]
        _assert_points_close(self, loaded_points["rect"], expected_rectangle)
        _assert_points_close(self, loaded_points["poly"], original_points["poly"])
        _assert_points_close(
            self, loaded_points["point"], original_points["point"]
        )


if __name__ == "__main__":
    unittest.main()
