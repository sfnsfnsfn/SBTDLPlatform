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
    coordinate_map_module = _load_module(
        "anylabeling.views.labeling.viewport.coordinate_map",
        VIEWPORT_DIR / "coordinate_map.py",
    )
    return rect_module.RectF, coordinate_map_module.CoordinateMap


RectF, CoordinateMap = _load_viewport_types()


def assert_close_pair(test_case, actual, expected, abs_tol=1e-6):
    test_case.assertTrue(math.isclose(actual[0], expected[0], abs_tol=abs_tol))
    test_case.assertTrue(math.isclose(actual[1], expected[1], abs_tol=abs_tol))


class CoordinateMapTest(unittest.TestCase):
    def test_image_view_round_trip_is_stable(self):
        coordinate_map = CoordinateMap(
            RectF(10.5, 20.25, 410.5, 320.25),
            800,
            600,
        )
        image_point = (123.456789, 234.567891)

        view_point = coordinate_map.image_to_view(*image_point)
        round_trip = coordinate_map.view_to_image(*view_point)

        assert_close_pair(self, round_trip, image_point)

    def test_negative_visible_rect_round_trip_is_stable(self):
        coordinate_map = CoordinateMap(
            RectF(-50.0, -25.0, 350.0, 275.0),
            800,
            600,
        )
        image_point = (-12.5, 44.25)

        view_point = coordinate_map.image_to_view(*image_point)
        round_trip = coordinate_map.view_to_image(*view_point)

        assert_close_pair(self, round_trip, image_point)

    def test_rect_conversion_round_trip_is_stable(self):
        coordinate_map = CoordinateMap(
            RectF(-100.0, 50.0, 700.0, 650.0),
            400,
            300,
        )
        image_rect = RectF(-10.0, 100.5, 250.25, 280.75)

        view_rect = coordinate_map.image_rect_to_view(image_rect)
        round_trip = coordinate_map.view_rect_to_image(view_rect)

        self.assertTrue(math.isclose(round_trip.x0, image_rect.x0, abs_tol=1e-6))
        self.assertTrue(math.isclose(round_trip.y0, image_rect.y0, abs_tol=1e-6))
        self.assertTrue(math.isclose(round_trip.x1, image_rect.x1, abs_tol=1e-6))
        self.assertTrue(math.isclose(round_trip.y1, image_rect.y1, abs_tol=1e-6))

    def test_scale_uses_uniform_visible_to_viewport_ratio(self):
        coordinate_map = CoordinateMap(
            RectF(25.0, 50.0, 425.0, 350.0),
            1000,
            750,
        )

        self.assertTrue(math.isclose(coordinate_map.scale, 2.5, abs_tol=1e-12))

    def test_non_uniform_aspect_is_rejected(self):
        with self.assertRaises(ValueError):
            CoordinateMap(RectF(0.0, 0.0, 100.0, 100.0), 800, 600)

    @unittest.skipUnless(
        "QPointF" in globals(),
        "PyQt6 is required for QTransform checks",
    )
    def test_qtransform_matches_numeric_formula(self):
        coordinate_map = CoordinateMap(
            RectF(-20.0, 15.0, 380.0, 315.0),
            800,
            600,
        )
        image_point = (125.5, 201.25)

        transform = coordinate_map.image_to_view_qtransform()
        mapped = transform.map(QPointF(*image_point))
        numeric = coordinate_map.image_to_view(*image_point)

        assert_close_pair(self, (mapped.x(), mapped.y()), numeric)


try:
    from PyQt6.QtCore import QPointF
except ImportError:
    pass
