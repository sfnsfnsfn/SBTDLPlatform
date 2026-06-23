from __future__ import annotations

import inspect
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
    provider_module = _load_module(
        "anylabeling.views.labeling.viewport.image_provider",
        VIEWPORT_DIR / "image_provider.py",
    )
    return (
        camera_module.Camera2D,
        provider_module.EmptyImageRegionError,
        provider_module.ImageProvider,
        provider_module.ImageReadResult,
        rect_module.RectF,
    )


(
    Camera2D,
    EmptyImageRegionError,
    ImageProvider,
    ImageReadResult,
    RectF,
) = _load_viewport_types()


class FakeImageProvider(ImageProvider):
    def __init__(self, image_width: int = 100, image_height: int = 80) -> None:
        self._image_width = image_width
        self._image_height = image_height
        self.reads = []

    @property
    def image_width(self) -> int:
        return self._image_width

    @property
    def image_height(self) -> int:
        return self._image_height

    def read_region(
        self, image_rect: RectF, target_size: tuple[int, int]
    ) -> ImageReadResult:
        region = self.prepare_region(image_rect, target_size)
        self.reads.append(region.clipped_rect)
        return ImageReadResult(
            region=region,
            image=f"fake:{region.clipped_rect}",
        )


class ImageProviderContractTest(unittest.TestCase):
    def test_inside_image_uses_outward_rounded_rect(self) -> None:
        provider = FakeImageProvider(100, 80)
        image_rect = RectF(10.2, 20.8, 30.1, 40.01)

        result = provider.read_region(image_rect, (200, 100))

        self.assertEqual(result.requested_rect, image_rect)
        self.assertEqual(result.clipped_rect, RectF(10.0, 20.0, 31.0, 41.0))
        self.assertEqual(result.target_size, (200, 100))
        self.assertEqual(provider.reads, [RectF(10.0, 20.0, 31.0, 41.0)])

    def test_partially_outside_image_reads_only_intersection(self) -> None:
        provider = FakeImageProvider(100, 80)
        image_rect = RectF(-5.7, 70.2, 105.4, 83.6)

        result = provider.read_region(image_rect, (64, 32))

        self.assertEqual(result.requested_rect, image_rect)
        self.assertEqual(result.clipped_rect, RectF(0.0, 70.0, 100.0, 80.0))

    def test_fully_outside_image_raises_defined_exception(self) -> None:
        provider = FakeImageProvider(100, 80)

        with self.assertRaises(EmptyImageRegionError):
            provider.read_region(RectF(101.1, 10.0, 120.0, 20.0), (16, 16))

        with self.assertRaises(EmptyImageRegionError):
            provider.read_region(RectF(1.0, -20.0, 5.0, -0.1), (16, 16))

    def test_target_size_must_be_positive_integers(self) -> None:
        provider = FakeImageProvider(100, 80)
        image_rect = RectF(0.0, 0.0, 10.0, 10.0)

        invalid_target_sizes = [
            (0, 1),
            (1, 0),
            (-1, 1),
            (1, -1),
            (1.5, 1),
            (1, 1.5),
            (True, 1),
            (1, False),
            [1, 1],
            (1,),
            (1, 1, 1),
        ]

        for target_size in invalid_target_sizes:
            with self.subTest(target_size=target_size):
                with self.assertRaises(ValueError):
                    provider.read_region(image_rect, target_size)  # type: ignore[arg-type]

    def test_provider_does_not_modify_input_rect_or_camera_visible(self) -> None:
        provider = FakeImageProvider(100, 80)
        image_rect = RectF(10.2, 20.8, 30.1, 40.01)
        camera = Camera2D(
            image_width=100,
            image_height=80,
            viewport_width=50,
            viewport_height=40,
            visible=RectF(10.0, 10.0, 60.0, 50.0),
        )
        original_visible = camera.visible

        provider.read_region(image_rect, (20, 20))

        self.assertEqual(image_rect, RectF(10.2, 20.8, 30.1, 40.01))
        self.assertEqual(camera.visible, original_visible)

    def test_provider_has_no_view_coordinate_mapping_dependency(self) -> None:
        source = inspect.getsource(ImageProvider)

        self.assertNotIn("view_to_image", source)
        self.assertNotIn("image_to_view", source)
        self.assertNotIn("CoordinateMap", source)
        self.assertNotIn("Camera2D", source)
        self.assertNotIn("viewport_", source)


if __name__ == "__main__":
    unittest.main()
