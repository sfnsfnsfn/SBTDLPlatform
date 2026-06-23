from __future__ import annotations

import ast
import pathlib
import re
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
CONFIG_PATH = (
    REPO_ROOT / "anylabeling" / "configs" / "xanylabeling_config.yaml"
)
LABEL_WIDGET_PATH = (
    REPO_ROOT / "anylabeling" / "views" / "labeling" / "label_widget.py"
)
RUNTIME_APPLIER_PATH = (
    REPO_ROOT
    / "anylabeling"
    / "views"
    / "labeling"
    / "settings"
    / "runtime_applier.py"
)


def _source(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _method_source(
    path: pathlib.Path, class_name: str, method_name: str
) -> str:
    source = _source(path)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if (
                    isinstance(item, ast.FunctionDef)
                    and item.name == method_name
                ):
                    return ast.get_source_segment(source, item) or ""
    raise AssertionError(f"{class_name}.{method_name} not found")


class ShapeFillOpacitySourceTest(unittest.TestCase):
    def test_default_config_exposes_label_fill_opacity(self):
        config_source = CONFIG_PATH.read_text(encoding="utf-8")

        self.assertRegex(
            config_source,
            re.compile(r"^\s+fill_opacity:\s+128\s*$", re.MULTILINE),
        )

    def test_label_widget_uses_fill_opacity_for_label_area_alpha(self):
        source = _source(LABEL_WIDGET_PATH)
        update_method = _method_source(
            LABEL_WIDGET_PATH, "LabelingWidget", "_update_shape_color"
        )

        self.assertIn("def _shape_fill_opacity", source)
        self.assertIn("self._shape_fill_opacity()", update_method)
        self.assertNotIn("QtGui.QColor(r, g, b, 128)", update_method)

    def test_runtime_applier_refreshes_existing_shape_fill_opacity(self):
        source = _source(RUNTIME_APPLIER_PATH)

        self.assertIn('"shape.fill_opacity"', source)
        self.assertIn("_refresh_shape_fill_opacity()", source)


if __name__ == "__main__":
    unittest.main()
