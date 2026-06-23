from __future__ import annotations

import ast
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
LABEL_FILE_PATH = (
    REPO_ROOT / "anylabeling" / "views" / "labeling" / "label_file.py"
)


def _source() -> str:
    return LABEL_FILE_PATH.read_text(encoding="utf-8")


def _method_source(class_name: str, method_name: str) -> str:
    source = _source()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return ast.get_source_segment(source, item) or ""
    raise AssertionError(f"{class_name}.{method_name} not found")


class LabelFileLazyImageDataSourceTest(unittest.TestCase):
    def test_label_file_exposes_lazy_image_data_loading(self):
        init_source = _method_source("LabelFile", "__init__")
        load_source = _method_source("LabelFile", "load")

        self.assertIn("load_image_data=True", init_source)
        self.assertIn("load_image_data=True", load_source)
        self.assertIn("self.load(filename, load_image_data)", init_source)

    def test_label_file_skips_external_image_read_when_lazy(self):
        load_source = _method_source("LabelFile", "load")

        self.assertIn("if load_image_data:", load_source)
        self.assertIn("image_data = None", load_source)
        self.assertLess(
            load_source.index("if load_image_data:"),
            load_source.index("self.load_image_file(image_path)"),
        )

    def test_label_file_preserves_image_size_metadata_without_image_bytes(self):
        init_source = _method_source("LabelFile", "__init__")
        load_source = _method_source("LabelFile", "load")

        self.assertIn("self.image_height = None", init_source)
        self.assertIn("self.image_width = None", init_source)
        self.assertIn("self.image_height = image_height", load_source)
        self.assertIn("self.image_width = image_width", load_source)


if __name__ == "__main__":
    unittest.main()
