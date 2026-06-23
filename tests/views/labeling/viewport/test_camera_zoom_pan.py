import math
import pathlib
import sys
import types
import unittest
from importlib import util as importlib_util

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
VIEWPORT_DIR = REPO_ROOT / "anylabeling" / "views" / "labeling" / "viewport"


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


def _load_viewport_types():
    _ensure_package("anylabeling")
    _ensure_package("anylabeling.views")
    _ensure_package("anylabeling.views.labeling")
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
    return rect_module.RectF, camera_module.Camera2D


RectF, Camera2D = _load_viewport_types()


def assert_rect_close(test_case, actual, expected, abs_tol=1e-6):
    test_case.assertTrue(math.isclose(actual.x0, expected.x0, abs_tol=abs_tol))
    test_case.assertTrue(math.isclose(actual.y0, expected.y0, abs_tol=abs_tol))
    test_case.assertTrue(math.isclose(actual.x1, expected.x1, abs_tol=abs_tol))
    test_case.assertTrue(math.isclose(actual.y1, expected.y1, abs_tol=abs_tol))


class CameraZoomPanTest(unittest.TestCase):
    def test_fit_to_window_preserves_viewport_aspect_and_shows_full_image(self):
        camera = Camera2D(1000, 500, 300, 300)

        self.assertTrue(math.isclose(camera.visible.width / camera.visible.height, 1.0))
        self.assertLessEqual(camera.visible.x0, 0.0)
        self.assertLessEqual(camera.visible.y0, 0.0)
        self.assertGreaterEqual(camera.visible.x1, 1000.0)
        self.assertGreaterEqual(camera.visible.y1, 500.0)

    def test_zoom_at_cursor_keeps_anchor_image_coordinate_stable(self):
        camera = Camera2D(1000, 800, 500, 400)
        view_point = (375.25, 103.5)
        before = camera.coordinate_map().view_to_image(*view_point)

        camera.zoom_at_view_point(*view_point, factor=2.0)

        after = camera.coordinate_map().view_to_image(*view_point)
        self.assertTrue(math.isclose(after[0], before[0], abs_tol=1e-6))
        self.assertTrue(math.isclose(after[1], before[1], abs_tol=1e-6))

    def test_pan_by_view_delta_moves_visible_rect_by_expected_image_delta(self):
        camera = Camera2D(
            1000,
            800,
            500,
            400,
            visible=RectF(100.0, 80.0, 600.0, 480.0),
        )

        camera.pan_by_view_delta(50.0, -20.0)

        assert_rect_close(self, camera.visible, RectF(50.0, 100.0, 550.0, 500.0))

    def test_pan_is_limited_to_keep_image_recoverable(self):
        camera = Camera2D(1000, 800, 500, 400)

        camera.pan_by_view_delta(100000.0, -100000.0)

        self.assertGreaterEqual(camera.visible.x1, 0.0)
        self.assertLessEqual(camera.visible.x0, camera.image_width)
        self.assertGreaterEqual(camera.visible.y1, 0.0)
        self.assertLessEqual(camera.visible.y0, camera.image_height)

    def test_zoom_clamp_keeps_visible_height_at_least_one_pixel(self):
        camera = Camera2D(1000, 800, 1000, 100)

        camera.zoom_at_view_point(500.0, 50.0, factor=1_000_000.0)

        self.assertGreaterEqual(camera.visible.width, 10.0)
        self.assertGreaterEqual(camera.visible.height, 1.0)

    def test_resize_viewport_keeps_center_and_adjusts_aspect(self):
        camera = Camera2D(
            1000,
            800,
            500,
            400,
            visible=RectF(100.0, 80.0, 600.0, 480.0),
        )

        camera.resize_viewport(800, 400, keep_center=True)

        self.assertTrue(math.isclose(camera.visible.center_x, 350.0, abs_tol=1e-6))
        self.assertTrue(math.isclose(camera.visible.center_y, 280.0, abs_tol=1e-6))
        self.assertTrue(math.isclose(camera.visible.width / camera.visible.height, 2.0))

    def test_set_visible_rect_expands_to_viewport_aspect(self):
        camera = Camera2D(1000, 800, 800, 400)

        camera.set_visible_rect(RectF(100.0, 100.0, 300.0, 300.0))

        self.assertTrue(math.isclose(camera.visible.center_x, 200.0, abs_tol=1e-6))
        self.assertTrue(math.isclose(camera.visible.center_y, 200.0, abs_tol=1e-6))
        self.assertTrue(math.isclose(camera.visible.width / camera.visible.height, 2.0))
        self.assertGreaterEqual(camera.visible.width, 200.0)
        self.assertGreaterEqual(camera.visible.height, 200.0)

    def test_fit_width_shows_full_image_width_at_viewport_aspect(self):
        camera = Camera2D(1000, 800, 500, 250)
        camera.zoom_at_view_point(250.0, 125.0, factor=2.0)

        camera.fit_width()

        self.assertTrue(math.isclose(camera.visible.x0, 0.0, abs_tol=1e-6))
        self.assertTrue(math.isclose(camera.visible.x1, 1000.0, abs_tol=1e-6))
        self.assertTrue(
            math.isclose(
                camera.visible.center_y,
                camera.image_height / 2.0,
                abs_tol=1e-6,
            )
        )
        self.assertTrue(
            math.isclose(
                camera.visible.width / camera.visible.height,
                camera.viewport_width / camera.viewport_height,
                abs_tol=1e-6,
            )
        )

    def test_set_scale_around_center_uses_camera_zoom_model(self):
        camera = Camera2D(
            1000,
            800,
            500,
            400,
            visible=RectF(100.0, 80.0, 600.0, 480.0),
        )

        camera.set_scale_around_center(2.0)

        self.assertTrue(math.isclose(camera.coordinate_map().scale, 2.0))
        self.assertTrue(math.isclose(camera.visible.center_x, 350.0))
        self.assertTrue(math.isclose(camera.visible.center_y, 280.0))

    def test_invalid_rect_size_is_rejected(self):
        with self.assertRaises(ValueError):
            RectF(0.0, 0.0, 0.0, 1.0)
