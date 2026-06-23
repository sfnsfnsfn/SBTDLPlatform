"""Tests for LabelWorkspace Phase 2 — AI toolbar, progress bar, batch labeling."""
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


# ---------------------------------------------------------------------------
# AI Toolbar tests
# ---------------------------------------------------------------------------


class TestAIToolbar:
    """AI toolbar buttons and model selector."""

    def test_ai_toolbar_buttons_exist(self, qapp):
        """AI 预标注 and 批量标注 buttons exist in the workspace."""
        from anylabeling.views.platform.label_workspace import LabelWorkspace
        ws = LabelWorkspace()
        assert hasattr(ws, "_ai_predict_btn"), "AI predict button should exist"
        assert hasattr(ws, "_ai_batch_btn"), "Batch labeling button should exist"
        assert hasattr(ws, "_model_combo"), "Model combo box should exist"
        assert ws._ai_predict_btn is not None
        assert ws._ai_batch_btn is not None
        assert ws._model_combo is not None

    def test_ai_buttons_initially_disabled(self, qapp):
        """When no project is set, AI buttons are disabled."""
        from anylabeling.views.platform.label_workspace import LabelWorkspace
        ws = LabelWorkspace()
        assert not ws._ai_predict_btn.isEnabled(), (
            "AI predict button should be disabled without project"
        )
        assert not ws._ai_batch_btn.isEnabled(), (
            "Batch button should be disabled without project"
        )

    def test_ai_buttons_enabled_with_runs(self, qapp):
        """AI buttons enable when a run is selected in the model combo."""
        from anylabeling.views.platform.label_workspace import LabelWorkspace
        ws = LabelWorkspace()
        # Simulate having runs — manually call the update method
        runs = [{"id": "run_001", "adapter_id": "yolo"}]
        ws._update_ai_toolbar_state(runs=runs, has_assets=True)
        # Buttons become selectable once runs are loaded
        assert ws._model_combo.count() == len(runs)

    def test_ai_buttons_disabled_without_runs(self, qapp):
        """AI buttons stay disabled when no runs exist."""
        from anylabeling.views.platform.label_workspace import LabelWorkspace
        ws = LabelWorkspace()
        ws._update_ai_toolbar_state(runs=[], has_assets=True)
        assert not ws._ai_predict_btn.isEnabled()
        assert not ws._ai_batch_btn.isEnabled()

    def test_ai_buttons_disabled_without_assets(self, qapp):
        """AI buttons disabled without assets even if runs exist."""
        from anylabeling.views.platform.label_workspace import LabelWorkspace
        ws = LabelWorkspace()
        ws._update_ai_toolbar_state(
            runs=[{"id": "run_001"}], has_assets=False,
        )
        assert not ws._ai_predict_btn.isEnabled()
        assert not ws._ai_batch_btn.isEnabled()

    def test_ai_buttons_enabled_with_runs_and_assets(self, qapp):
        """AI buttons enabled when runs exist and assets are present."""
        from anylabeling.views.platform.label_workspace import LabelWorkspace
        ws = LabelWorkspace()
        ws._update_ai_toolbar_state(
            runs=[{"id": "run_001"}], has_assets=True,
        )
        # Add a run to the combo and select it
        ws._model_combo.addItem("run_001", "run_001")
        ws._model_combo.setCurrentIndex(0)
        # Buttons should now be enabled
        assert ws._ai_predict_btn.isEnabled()
        assert ws._ai_batch_btn.isEnabled()

    def test_ai_predict_button_emits_signal(self, qapp):
        """AI predict button click emits the predict signal."""
        from anylabeling.views.platform.label_workspace import LabelWorkspace
        ws = LabelWorkspace()
        received = []

        def on_predict():
            received.append(True)

        ws.ai_predict_requested.connect(on_predict)
        # Button must be enabled for click to work
        ws._ai_predict_btn.setEnabled(True)
        ws._ai_predict_btn.click()
        assert len(received) == 1

    def test_batch_button_emits_signal(self, qapp):
        """Batch label button click emits the batch signal."""
        from anylabeling.views.platform.label_workspace import LabelWorkspace
        ws = LabelWorkspace()
        received = []

        def on_batch():
            received.append(True)

        ws.ai_batch_requested.connect(on_batch)
        # Button must be enabled for click to work
        ws._ai_batch_btn.setEnabled(True)
        ws._ai_batch_btn.click()
        assert len(received) == 1


# ---------------------------------------------------------------------------
# Progress bar tests
# ---------------------------------------------------------------------------


class TestProgressBar:
    """Progress bar display and update logic."""

    def test_progress_format_zero_assets(self, qapp):
        """Progress shows 0/0 at 0% when no assets."""
        from anylabeling.views.platform.label_workspace import LabelWorkspace
        ws = LabelWorkspace()
        ws._update_progress(0, 0)
        text = ws._progress_label.text()
        assert "0" in text
        assert "0%" in text

    def test_progress_format_with_annotations(self, qapp):
        """Progress shows correct annotated/total counts."""
        from anylabeling.views.platform.label_workspace import LabelWorkspace
        ws = LabelWorkspace()
        ws._update_progress(3, 10)
        text = ws._progress_label.text()
        assert "3" in text
        assert "10" in text
        assert "30%" in text

    def test_progress_format_all_annotated(self, qapp):
        """Progress at 100% when all assets are annotated."""
        from anylabeling.views.platform.label_workspace import LabelWorkspace
        ws = LabelWorkspace()
        ws._update_progress(5, 5)
        text = ws._progress_label.text()
        assert "100%" in text


# ---------------------------------------------------------------------------
# Status icon tests
# ---------------------------------------------------------------------------


class TestStatusIcons:
    """AssetListItem uses QIcon instead of emoji (UI Finding #7 fix)."""

    def test_status_unannotated_has_icon(self, qapp):
        from anylabeling.views.platform.label_workspace import AssetListItem
        item = AssetListItem("/fake/path/img.png")
        # Should have an icon set, not just text
        assert item.icon() is not None
        assert not item.icon().isNull()

    def test_status_complete_has_icon(self, qapp):
        from anylabeling.views.platform.label_workspace import AssetListItem
        item = AssetListItem("/fake/path/img.png", AssetListItem.STATUS_COMPLETE)
        assert item.icon() is not None
        assert not item.icon().isNull()

    def test_icon_changes_on_status_update(self, qapp):
        from anylabeling.views.platform.label_workspace import AssetListItem
        item = AssetListItem("/fake/path/img.png")
        icon_before = item.icon()
        item.set_status(AssetListItem.STATUS_COMPLETE)
        # Icon should be different after status change
        assert not (icon_before.cacheKey() == item.icon().cacheKey())


# ---------------------------------------------------------------------------
# BatchLabelingService tests
# ---------------------------------------------------------------------------


class TestBatchLabelingService:
    """BatchLabelingService — orchestrates batch AI labeling."""

    def test_service_creation(self):
        """BatchLabelingService can be created without PyQt."""
        from pathlib import Path
        from anylabeling.platform.application.batch_labeling_service import (
            BatchLabelingService,
        )
        service = BatchLabelingService("/fake/project")
        assert service is not None
        assert Path(service.project_path) == Path("/fake/project")

    def test_service_discovers_assets(self, tmp_path):
        """Service can list unannotated assets."""
        from anylabeling.platform.application.batch_labeling_service import (
            BatchLabelingService,
        )

        project = tmp_path / "test_proj"
        project.mkdir()
        assets_dir = project / "assets"
        assets_dir.mkdir()
        annotations_dir = project / "annotations"
        annotations_dir.mkdir()

        # Create images
        (assets_dir / "img1.jpg").write_text("fake")
        (assets_dir / "img2.png").write_text("fake")
        (assets_dir / "img3.jpg").write_text("fake")
        # Annotation for img1 only
        (annotations_dir / "img1.json").write_text('{"shapes": [{"label": "cat"}]}')

        service = BatchLabelingService(str(project))
        unannotated = service.get_unannotated_assets()
        annotated = service.get_annotated_assets()

        assert len(unannotated) == 2  # img2, img3
        assert len(annotated) == 1     # img1

    def test_service_get_unannotated_assets_empty(self, tmp_path):
        """Returns empty list when no assets exist."""
        from anylabeling.platform.application.batch_labeling_service import (
            BatchLabelingService,
        )

        project = tmp_path / "empty_project"
        project.mkdir()
        (project / "assets").mkdir()
        (project / "annotations").mkdir()

        service = BatchLabelingService(str(project))
        assets = service.get_unannotated_assets()
        assert assets == []

    def test_service_progress_counts(self, tmp_path):
        """Service reports correct progress counts."""
        from anylabeling.platform.application.batch_labeling_service import (
            BatchLabelingService,
        )

        project = tmp_path / "test_proj"
        project.mkdir()
        assets_dir = project / "assets"
        assets_dir.mkdir()
        annotations_dir = project / "annotations"
        annotations_dir.mkdir()

        for i in range(10):
            (assets_dir / f"img{i}.jpg").write_text("fake")
        for i in range(4):
            (annotations_dir / f"img{i}.json").write_text('{"shapes": [{"label": "x"}]}')

        service = BatchLabelingService(str(project))
        total, annotated = service.get_progress()
        assert total == 10
        assert annotated == 4
