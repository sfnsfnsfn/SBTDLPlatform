from __future__ import annotations

import ast
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
LABEL_LIST_WIDGET_PATH = (
    REPO_ROOT
    / "anylabeling"
    / "views"
    / "labeling"
    / "widgets"
    / "label_list_widget.py"
)
LABEL_WIDGET_PATH = (
    REPO_ROOT / "anylabeling" / "views" / "labeling" / "label_widget.py"
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


class LabelDeleteSelectionSourceTest(unittest.TestCase):
    def test_label_list_delete_key_requests_shape_delete(self):
        source = _source(LABEL_LIST_WIDGET_PATH)
        key_press = _method_source(
            LABEL_LIST_WIDGET_PATH, "LabelListWidget", "keyPressEvent"
        )

        self.assertIn("delete_requested = QtCore.pyqtSignal()", source)
        self.assertIn("Qt.Key.Key_Delete", key_press)
        self.assertIn("Qt.Key.Key_Backspace", key_press)
        self.assertIn("self.delete_requested.emit()", key_press)

    def test_label_widget_connects_label_list_delete_request(self):
        source = _source(LABEL_WIDGET_PATH)

        self.assertIn(
            "self.label_list.delete_requested.connect("
            "self.delete_selected_shape)",
            source.replace("\n", ""),
        )

    def test_delete_uses_label_list_selection_when_canvas_is_not_synced(self):
        source = _source(LABEL_WIDGET_PATH)
        helper = _method_source(
            LABEL_WIDGET_PATH, "LabelingWidget", "_selected_shapes_for_delete"
        )
        delete_method = _method_source(
            LABEL_WIDGET_PATH, "LabelingWidget", "delete_selected_shape"
        )

        self.assertIn("self.canvas.selected_shapes", helper)
        self.assertIn("self.label_list.selected_items()", helper)
        self.assertIn("_selected_shapes_for_delete()", delete_method)


if __name__ == "__main__":
    unittest.main()
