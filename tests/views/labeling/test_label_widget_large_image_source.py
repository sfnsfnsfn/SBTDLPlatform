from __future__ import annotations

import ast
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
LABEL_WIDGET_PATH = (
    REPO_ROOT / "anylabeling" / "views" / "labeling" / "label_widget.py"
)
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"


def _source() -> str:
    return LABEL_WIDGET_PATH.read_text(encoding="utf-8")


def _method_source(class_name: str, method_name: str) -> str:
    source = _source()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return ast.get_source_segment(source, item) or ""
    raise AssertionError(f"{class_name}.{method_name} not found")


class LabelWidgetLargeImageSourceTest(unittest.TestCase):
    def test_load_file_decides_provider_before_image_bytes_are_loaded(self):
        load_file = _method_source("LabelingWidget", "load_file")

        provider_index = load_file.index(
            "_provider = self._try_create_image_provider(filename)"
        )
        byte_load_index = load_file.index(
            "self.image_data = LabelFile.load_image_file(filename)"
        )

        self.assertLess(provider_index, byte_load_index)

    def test_load_file_uses_provider_placeholder_without_full_qimage_decode(self):
        load_file = _method_source("LabelingWidget", "load_file")

        self.assertIn("image = self._image_for_provider(_provider)", load_file)
        self.assertLess(
            load_file.index("image = self._image_for_provider(_provider)"),
            load_file.index("image = utils.img_data_to_qimage"),
        )

    def test_navigator_entry_points_use_safe_thumbnail_loader(self):
        restore = _method_source("LabelingWidget", "restore_navigator_state")
        toggle = _method_source("LabelingWidget", "toggle_navigator")

        self.assertIn("self._set_navigator_image()", restore)
        self.assertIn("self._set_navigator_image()", toggle)
        self.assertNotIn("QtGui.QPixmap.fromImage(self.image)", restore)
        self.assertNotIn("QtGui.QPixmap.fromImage(self.image)", toggle)

    def test_unused_pyqtgraph_stack_is_not_a_runtime_dependency(self):
        pyproject = PYPROJECT_PATH.read_text(encoding="utf-8")

        self.assertNotIn('"pyqtgraph>=', pyproject)
        self.assertNotIn('"tifffile>=', pyproject)


if __name__ == "__main__":
    unittest.main()
