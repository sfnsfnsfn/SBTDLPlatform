"""Tests for LabelWorkspace components."""
import sys
import pytest

pytest.importorskip("PyQt6")


class TestAssetListItem:
    """AssetListItem — annotation status display."""

    def test_create_unannotated(self, qapp):
        from anylabeling.views.platform.label_workspace import AssetListItem
        item = AssetListItem("/fake/path/image.jpg")
        assert item.asset_path == "/fake/path/image.jpg"
        assert item.annotation_status == AssetListItem.STATUS_UNANNOTATED
        assert item.icon() is not None
        assert not item.icon().isNull()
        assert "image.jpg" in item.text()

    def test_create_complete(self, qapp):
        from anylabeling.views.platform.label_workspace import AssetListItem
        item = AssetListItem("/fake/path/image.jpg", AssetListItem.STATUS_COMPLETE)
        assert item.icon() is not None
        assert not item.icon().isNull()

    def test_set_status_updates_display(self, qapp):
        from anylabeling.views.platform.label_workspace import AssetListItem
        item = AssetListItem("/fake/path/image.jpg")
        item.set_status(AssetListItem.STATUS_COMPLETE)
        # Icon should now be the "apply" (checkmark) icon
        assert item.icon() is not None
        assert not item.icon().isNull()

    def test_user_role_data(self):
        from anylabeling.views.platform.label_workspace import AssetListItem
        from PyQt6.QtCore import Qt
        item = AssetListItem("/fake/path/img.png")
        assert item.data(Qt.ItemDataRole.UserRole) == "/fake/path/img.png"


@pytest.fixture
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


class TestLabelWorkspaceCreation:
    """Smoke tests for LabelWorkspace instantiation."""

    def test_create_widget(self, qapp):
        from anylabeling.views.platform.label_workspace import LabelWorkspace
        workspace = LabelWorkspace()
        assert workspace is not None
        assert workspace._asset_list is not None
        assert workspace._search_bar is not None
        assert workspace._inspector is not None
