from __future__ import annotations

import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
HUGE_CANVAS_PATH = (
    REPO_ROOT
    / "anylabeling"
    / "views"
    / "labeling"
    / "widgets"
    / "huge_image_canvas.py"
)


class HugeImageCanvasSourceTest(unittest.TestCase):
    def test_lod_image_item_keeps_level0_scene_rect(self):
        source = HUGE_CANVAS_PATH.read_text(encoding="utf-8")

        self.assertIn("def _set_image_level", source)
        self.assertIn("self.image_item.setRect", source)
        self.assertIn("self._image_width", source)
        self.assertIn("self._image_height", source)

    def test_zoom_scale_is_screen_pixels_per_visible_image_pixel(self):
        source = HUGE_CANVAS_PATH.read_text(encoding="utf-8")

        self.assertIn("screen_w = max(1, self.viewport().width())", source)
        self.assertIn("scale = screen_w / view_w", source)

    def test_pixel_grid_requires_explicit_debug_flag(self):
        source = HUGE_CANVAS_PATH.read_text(encoding="utf-8")

        self.assertIn("show_pixel_grid: bool = False", source)
        self.assertIn("self._show_pixel_grid = bool(show_pixel_grid)", source)
        self.assertIn(
            "self.pixel_grid.set_visible(self._show_pixel_grid and scale >= 8.0)",
            source,
        )


if __name__ == "__main__":
    unittest.main()
