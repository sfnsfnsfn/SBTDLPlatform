from __future__ import annotations

import ast
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SHAPE_PATH = REPO_ROOT / "anylabeling" / "views" / "labeling" / "shape.py"


def _source() -> str:
    return SHAPE_PATH.read_text(encoding="utf-8")


def _method_source(class_name: str, method_name: str) -> str:
    source = _source()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return ast.get_source_segment(source, item) or ""
    raise AssertionError(f"{class_name}.{method_name} not found")


class ShapeDisplaySourceTest(unittest.TestCase):
    def test_shape_line_pens_are_cosmetic_screen_pixel_widths(self):
        source = _source()

        self.assertIn("def _display_pen", source)
        self.assertIn("pen.setWidthF(float(self.line_width))", source)
        self.assertIn("pen.setCosmetic(True)", source)
        self.assertNotIn(
            "pen.setWidth(max(1, int(round(self.line_width / self.scale))))",
            source,
        )

    def test_shape_points_use_display_size_helper(self):
        source = _source()

        self.assertIn("def _display_size", source)
        self.assertIn("d = self._display_size(self.point_size)", source)
        self.assertIn("tip_len = self._display_size(10.0)", source)
        self.assertIn("arm_len = self._display_size(12.0)", source)
        self.assertNotIn("self.point_size / self.scale", source)
        self.assertNotIn("max(4, 10 / self.scale)", source)

    def test_paint_helpers_do_not_mutate_shape_points(self):
        for method_name in ("paint", "_draw_quadrilateral_order", "draw_vertex"):
            method = ast.parse(
                _method_source("Shape", method_name)
            )
            for node in ast.walk(method):
                if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                    continue
                if isinstance(node, ast.Assign):
                    targets = node.targets
                else:
                    targets = [node.target]
                for target in targets:
                    if (
                        isinstance(target, ast.Attribute)
                        and target.attr == "points"
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "self"
                    ):
                        self.fail(f"{method_name} mutates self.points")


if __name__ == "__main__":
    unittest.main()
