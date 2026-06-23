"""Tests for DataWorkspace Phase 2 — simplified to data overview only."""
import sys
import pytest

pytest.importorskip("PyQt6")


@pytest.fixture
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


class TestDataWorkspaceSimplification:
    """DataWorkspace no longer contains tile/split/build config UI."""

    def test_no_tile_group(self, qapp):
        """DataWorkspace should NOT have a tile parameters group."""
        from anylabeling.views.platform.data_workspace import DataWorkspace
        ws = DataWorkspace()
        assert not hasattr(ws, "_tile_group"), (
            "DataWorkspace should not have tile config controls"
        )

    def test_no_split_group(self, qapp):
        """DataWorkspace should NOT have a split parameters group."""
        from anylabeling.views.platform.data_workspace import DataWorkspace
        ws = DataWorkspace()
        assert not hasattr(ws, "_split_group"), (
            "DataWorkspace should not have split config controls"
        )

    def test_no_build_button(self, qapp):
        """DataWorkspace should NOT have a build dataset button."""
        from anylabeling.views.platform.data_workspace import DataWorkspace
        ws = DataWorkspace()
        assert not hasattr(ws, "_build_btn"), (
            "DataWorkspace should not have a build button"
        )

    def test_has_stats_label(self, qapp):
        """DataWorkspace retains the stats label for data overview."""
        from anylabeling.views.platform.data_workspace import DataWorkspace
        ws = DataWorkspace()
        assert hasattr(ws, "_stats_label")
        assert ws._stats_label is not None

    def test_has_asset_list(self, qapp):
        """DataWorkspace retains the asset list."""
        from anylabeling.views.platform.data_workspace import DataWorkspace
        ws = DataWorkspace()
        assert hasattr(ws, "_asset_list")
        assert ws._asset_list is not None

    def test_has_navigate_to_preprocess_button(self, qapp):
        """DataWorkspace has a button to navigate to PREPROCESS step."""
        from anylabeling.views.platform.data_workspace import DataWorkspace
        ws = DataWorkspace()
        assert hasattr(ws, "_goto_preprocess_btn"), (
            "DataWorkspace should have a 'Go to Preprocess' button"
        )
        assert ws._goto_preprocess_btn is not None

    def test_navigate_signal_emits_pipeline_step(self, qapp):
        """Clicking the navigate button emits the PREPROCESS PipelineStep."""
        from anylabeling.views.platform.data_workspace import DataWorkspace
        from anylabeling.views.platform.navigation_bar import PipelineStep

        ws = DataWorkspace()
        emitted = []

        def on_navigate(step):
            emitted.append(step)

        ws.navigate_to_step.connect(on_navigate)
        ws._goto_preprocess_btn.click()

        assert len(emitted) == 1
        assert emitted[0] == PipelineStep.PREPROCESS

    def test_set_assets_updates_stats(self, qapp):
        """Setting assets updates the stats label."""
        from anylabeling.views.platform.data_workspace import DataWorkspace
        ws = DataWorkspace()
        ws.set_assets(["/a/1.jpg", "/a/2.jpg", "/a/3.png"])
        text = ws._stats_label.text()
        assert "3" in text

    def test_class_distribution_section_exists(self, qapp):
        """DataWorkspace has a class distribution display section."""
        from anylabeling.views.platform.data_workspace import DataWorkspace
        ws = DataWorkspace()
        assert hasattr(ws, "_class_dist_label")
        assert ws._class_dist_label is not None

    def test_no_build_requested_signal(self, qapp):
        """DataWorkspace no longer has build_requested signal."""
        from anylabeling.views.platform.data_workspace import DataWorkspace
        ws = DataWorkspace()
        assert not hasattr(ws, "build_requested"), (
            "DataWorkspace should not have build_requested signal"
        )


# ---------------------------------------------------------------------------
# Pure-function tests (no QApplication needed)
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    """Standalone helper functions remain available."""

    def test_format_count(self):
        from anylabeling.views.platform.data_workspace import _format_count
        assert _format_count(1000) == "1,000"
        assert _format_count(0) == "0"

    def test_format_coverage(self):
        from anylabeling.views.platform.data_workspace import _format_coverage
        assert "N/A" in _format_coverage(None) or "无数据" in _format_coverage(None)
        assert "50" in _format_coverage(0.5)

    def test_validate_split_ratios(self):
        from anylabeling.views.platform.data_workspace import _validate_split_ratios
        assert _validate_split_ratios(0.7, 0.2, 0.1) == []
        assert len(_validate_split_ratios(0.5, 0.3, 0.1)) > 0
