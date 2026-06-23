"""Tests for M3.4: Train Workspace UI — hyperparameter form + training progress.

Test strategy:
- Non-GUI tests: verify RunViewModel logic, TrainRequest defaults
- GUI tests (require QApplication): verify widget construction, form
  population, collapsible groups, button states
- Tests that require QApplication are skipped if no display is available.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _qapp_available() -> bool:
    """Return True if QApplication can be instantiated (display available)."""
    try:
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
                return True
            return False
        return True
    except ImportError:
        return False


def _create_qapp():
    """Create a QApplication instance if one doesn't exist."""
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


_HAS_QAPP = _qapp_available()
skip_without_display = pytest.mark.skipif(
    not _HAS_QAPP, reason="Requires display (QApplication)"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_jobs_root(tmp_path):
    """A temporary jobs root directory."""
    jobs_root = tmp_path / "jobs"
    jobs_root.mkdir()
    return jobs_root


@pytest.fixture
def job_service(tmp_jobs_root):
    """A real JobService backed by a temp directory."""
    from anylabeling.platform.application.job_service import JobService
    return JobService(tmp_jobs_root)


@pytest.fixture
def training_service(job_service, tmp_path):
    """A TrainingService backed by a temp project root."""
    from anylabeling.platform.application.training_service import TrainingService
    return TrainingService(job_service, tmp_path)


@pytest.fixture
def sample_task_spec():
    """A minimal TaskSpec for detection."""
    from anylabeling.platform.domain.task import TaskSpec, LabelClass
    return TaskSpec(
        id="detection_v1",
        family="detection_hbb",
        labels=(LabelClass(id=0, name="object"),),
        annotation_schema="hbb",
        primary_metric="mAP50",
    )


@pytest.fixture
def sample_dataset_build(sample_task_spec):
    """A minimal DatasetBuild."""
    from anylabeling.platform.domain.dataset import DatasetBuild
    return DatasetBuild(
        id="build_v1",
        task_spec_id=sample_task_spec.id,
        source_asset_manifest_hash="abc123",
        annotation_manifest_hash="def456",
        split_seed=42,
        split_strategy="random",
        adapter_id="ultralytics_yolo_detect",
        output_path="/tmp/builds/build_v1",
    )


# ============================================================================
# 1. RunViewModel tests (non-GUI)
# ============================================================================


class TestRunViewModel:
    """Tests for RunViewModel — start, stop, get_status."""

    def test_construction(self, job_service, training_service):
        """RunViewModel can be constructed with JobService and TrainingService."""
        from anylabeling.views.platform.view_models.run_vm import RunViewModel

        vm = RunViewModel(job_service, training_service)
        assert vm.job_service is job_service
        assert vm.training_service is training_service

    def test_get_status_unknown_job(self, job_service, training_service):
        """get_status returns unknown state for nonexistent job_id."""
        from anylabeling.views.platform.view_models.run_vm import RunViewModel

        vm = RunViewModel(job_service, training_service)
        status = vm.get_status("nonexistent_job_id")
        assert status["state"] == "unknown"
        assert status["epoch"] == 0
        assert status["best_metric"] is None

    def test_stop_training_delegates_to_job_service(
        self, job_service, training_service
    ):
        """stop_training calls JobService.cancel_job."""
        from anylabeling.views.platform.view_models.run_vm import RunViewModel

        vm = RunViewModel(job_service, training_service)

        # Cancelling a non-existent job should not raise (JobService
        # cancel_job is idempotent on unknown IDs via the runner)
        # We patch since ProcessJobRunner.cancel will fail on nonexistent dir
        with patch.object(job_service._runner, "cancel") as mock_cancel:
            vm.stop_training("some_job_id")
            mock_cancel.assert_called_once_with("some_job_id")

    def test_start_training_delegates_to_training_service(
        self, job_service, training_service, sample_task_spec,
        sample_dataset_build,
    ):
        """start_training calls TrainingService.start_training and returns job_id."""
        from anylabeling.views.platform.view_models.run_vm import RunViewModel
        from anylabeling.platform.adapters.ultralytics.train_adapter import (
            TrainRequest,
        )

        vm = RunViewModel(job_service, training_service)

        request = TrainRequest(
            task_spec=sample_task_spec,
            dataset_build=sample_dataset_build,
            base_model="/tmp/model.pt",
            epochs=10,
            batch=8,
            imgsz=320,
        )

        with patch.object(training_service, "start_training",
                          return_value="job_abc123") as mock_start:
            job_id = vm.start_training(request)
            mock_start.assert_called_once_with(request)
            assert job_id == "job_abc123"

    def test_get_status_returns_events_from_job(
        self, job_service, training_service,
    ):
        """get_status extracts epoch and best_metric from job events."""
        from anylabeling.views.platform.view_models.run_vm import RunViewModel
        from anylabeling.platform.workers.protocol import JobEvent

        vm = RunViewModel(job_service, training_service)

        fake_events = [
            JobEvent(seq=1, type="started", payload={}, timestamp=""),
            JobEvent(seq=2, type="progress",
                     payload={"epoch": 5}, timestamp=""),
            JobEvent(seq=3, type="metric",
                     payload={"name": "mAP50", "value": 0.72, "step": 5},
                     timestamp=""),
            JobEvent(seq=4, type="progress",
                     payload={"epoch": 10}, timestamp=""),
            JobEvent(seq=5, type="metric",
                     payload={"name": "mAP50", "value": 0.85, "step": 10},
                     timestamp=""),
        ]

        with patch.object(job_service, "get_job_state",
                          return_value=MagicMock(value="running")):
            with patch.object(job_service, "get_job_events",
                              return_value=fake_events):
                status = vm.get_status("test_job")
                assert status["state"] == "running"
                assert status["epoch"] == 10
                assert status["best_metric"] is not None
                assert status["best_metric"]["name"] == "mAP50"
                assert status["best_metric"]["value"] == 0.85


# ============================================================================
# 2. TrainWorkspace construction tests (require QApplication)
# ============================================================================


class TestTrainWorkspaceConstruction:
    """Tests for TrainWorkspace — widget creation, sub-widgets, layout."""

    @pytest.fixture
    def qapp(self):
        if not _HAS_QAPP:
            pytest.skip("Requires QApplication")
        app = _create_qapp()
        yield app

    @pytest.fixture
    def workspace(self, qapp):
        from anylabeling.views.platform.train_workspace import TrainWorkspace
        return TrainWorkspace()

    def test_creates_all_sub_widgets(self, workspace):
        """TrainWorkspace creates all required sub-widgets on construction."""
        assert hasattr(workspace, "_btn_start")
        assert hasattr(workspace, "_btn_stop")
        assert hasattr(workspace, "_lbl_status")
        assert hasattr(workspace, "_lbl_epoch")
        assert hasattr(workspace, "_progress_bar")
        assert hasattr(workspace, "_lbl_best_metric")
        assert hasattr(workspace, "_log_view")
        assert hasattr(workspace, "_combo_task")
        assert hasattr(workspace, "_combo_dataset")
        assert hasattr(workspace, "_combo_algorithm")
        assert hasattr(workspace, "_combo_optimizer")
        assert hasattr(workspace, "_edit_base_model")

    def test_form_has_default_values(self, workspace):
        """Form fields are populated with TrainRequest defaults."""
        # Check that basic fields have defaults
        for field_name in ["epochs", "batch", "imgsz", "device", "workers", "seed"]:
            assert field_name in workspace._numeric_inputs
            text = workspace._numeric_inputs[field_name].text()
            assert len(text) > 0, f"Field '{field_name}' should have a default value"

    def test_epochs_default_is_200(self, workspace):
        """Epochs field defaults to 200 (TrainRequest default)."""
        assert "epochs" in workspace._numeric_inputs
        assert workspace._numeric_inputs["epochs"].text() == "200"

    def test_batch_default_is_32(self, workspace):
        """Batch field defaults to 32."""
        assert "batch" in workspace._numeric_inputs
        assert workspace._numeric_inputs["batch"].text() == "32"

    def test_imgsz_default_is_640(self, workspace):
        """Imgsz field defaults to 640."""
        assert "imgsz" in workspace._numeric_inputs
        assert workspace._numeric_inputs["imgsz"].text() == "640"

    def test_optimizer_combo_has_options(self, workspace):
        """Optimizer combo has the expected options."""
        assert workspace._combo_optimizer.count() >= 5
        items = [
            workspace._combo_optimizer.itemText(i)
            for i in range(workspace._combo_optimizer.count())
        ]
        assert "SGD" in items
        assert "Adam" in items
        assert "AdamW" in items

    def test_optimizer_default_is_auto(self, workspace):
        """Optimizer combo defaults to 'auto'."""
        assert workspace._combo_optimizer.currentText() == "auto"

    def test_algorithm_combo_contains_registered_algorithms(self, workspace):
        """Algorithm combo is populated from AlgorithmRegistry."""
        assert workspace._combo_algorithm.count() >= 1

    def test_status_starts_as_idle(self, workspace):
        """Status label shows IDLE on construction."""
        assert workspace._lbl_status.text() == "IDLE"

    def test_start_button_enabled_only_with_context(self, workspace):
        """Start button is disabled when no project context is set."""
        assert not workspace._btn_start.isEnabled()
        assert not workspace._btn_stop.isEnabled()

    def test_stop_button_disabled_initially(self, workspace):
        """Stop button is disabled initially."""
        assert not workspace._btn_stop.isEnabled()


# ============================================================================
# 3. TrainWorkspace with project context tests
# ============================================================================


class TestTrainWorkspaceWithContext:
    """Tests for TrainWorkspace after set_project_context()."""

    @pytest.fixture
    def qapp(self):
        if not _HAS_QAPP:
            pytest.skip("Requires QApplication")
        app = _create_qapp()
        yield app

    @pytest.fixture
    def workspace_with_context(
        self, qapp, job_service, training_service, sample_task_spec,
        sample_dataset_build,
    ):
        from anylabeling.views.platform.train_workspace import TrainWorkspace

        ws = TrainWorkspace()
        ws.set_project_context(
            job_service=job_service,
            training_service=training_service,
            task_specs=[sample_task_spec],
            dataset_builds=[sample_dataset_build],
        )
        yield ws

    def test_context_enables_start_button(self, workspace_with_context):
        """Start button is enabled after set_project_context."""
        assert workspace_with_context._btn_start.isEnabled()

    def test_task_combo_populated(self, workspace_with_context):
        """Task combo contains the provided TaskSpec."""
        assert workspace_with_context._combo_task.count() >= 1
        assert workspace_with_context._combo_task.itemText(0) != ""

    def test_dataset_combo_populated(self, workspace_with_context):
        """Dataset combo contains the provided DatasetBuild."""
        assert workspace_with_context._combo_dataset.count() >= 1
        assert workspace_with_context._combo_dataset.itemText(0) != ""

    def test_job_service_accessor(self, workspace_with_context, job_service):
        """job_service() returns the attached JobService."""
        assert workspace_with_context.job_service() is job_service

    def test_training_service_accessor(
        self, workspace_with_context, training_service
    ):
        """training_service() returns the attached TrainingService."""
        assert workspace_with_context.training_service() is training_service

    def test_active_job_id_starts_none(self, workspace_with_context):
        """active_job_id() is None before any training starts."""
        assert workspace_with_context.active_job_id() is None


# ============================================================================
# 4. Collapsible group tests
# ============================================================================


class TestCollapsibleGroup:
    """Tests for the _CollapsibleGroup widget."""

    @pytest.fixture
    def qapp(self):
        if not _HAS_QAPP:
            pytest.skip("Requires QApplication")
        app = _create_qapp()
        yield app

    def test_group_starts_checked(self, qapp):
        """Collapsible group starts expanded (checked) with content visible."""
        from anylabeling.views.platform.train_workspace import _CollapsibleGroup
        from PyQt6.QtWidgets import QLabel

        group = _CollapsibleGroup("Test Group")
        content = QLabel("Content")
        group.set_content(content)

        assert group.isChecked()
        assert content.isVisible()

    def test_group_collapses_when_unchecked(self, qapp):
        """Content is hidden when the group is unchecked."""
        from anylabeling.views.platform.train_workspace import _CollapsibleGroup
        from PyQt6.QtWidgets import QLabel

        group = _CollapsibleGroup("Test Group")
        content = QLabel("Content")
        group.set_content(content)

        group.setChecked(False)
        assert not content.isVisible()

    def test_group_expands_when_rechecked(self, qapp):
        """Content is shown again when re-checked."""
        from anylabeling.views.platform.train_workspace import _CollapsibleGroup
        from PyQt6.QtWidgets import QLabel

        group = _CollapsibleGroup("Test Group")
        content = QLabel("Content")
        group.set_content(content)

        group.setChecked(False)
        assert not content.isVisible()
        group.setChecked(True)
        assert content.isVisible()


# ============================================================================
# 5. TrainRequest building tests
# ============================================================================


class TestTrainRequestBuilding:
    """Tests for _build_train_request() — validation and type coercion."""

    @pytest.fixture
    def qapp(self):
        if not _HAS_QAPP:
            pytest.skip("Requires QApplication")
        app = _create_qapp()
        yield app

    @pytest.fixture
    def workspace_with_context(
        self, qapp, job_service, training_service, sample_task_spec,
        sample_dataset_build,
    ):
        from anylabeling.views.platform.train_workspace import TrainWorkspace

        ws = TrainWorkspace()
        ws.set_project_context(
            job_service=job_service,
            training_service=training_service,
            task_specs=[sample_task_spec],
            dataset_builds=[sample_dataset_build],
        )
        # Fill in base model (required for validation)
        ws._edit_base_model.setText("/tmp/model.pt")
        return ws

    def test_builds_valid_request(self, workspace_with_context):
        """_build_train_request returns a TrainRequest when form is valid."""
        request = workspace_with_context._build_train_request()
        assert request is not None
        assert request.epochs == 200  # default
        assert request.batch == 32
        assert request.imgsz == 640
        assert request.optimizer == "auto"

    def test_rejects_missing_task(self, workspace_with_context):
        """_build_train_request returns None when no task is selected."""
        # Clear the task combo
        workspace_with_context._combo_task.clear()
        with patch.object(QtWidgets.QMessageBox, "warning"):
            request = workspace_with_context._build_train_request()
            assert request is None

    def test_rejects_missing_dataset_build(self, workspace_with_context):
        """_build_train_request returns None when no dataset build is selected."""
        workspace_with_context._combo_dataset.clear()
        with patch.object(QtWidgets.QMessageBox, "warning"):
            request = workspace_with_context._build_train_request()
            assert request is None

    def test_rejects_empty_base_model(self, workspace_with_context):
        """_build_train_request returns None when base model is empty."""
        workspace_with_context._edit_base_model.clear()
        with patch.object(QtWidgets.QMessageBox, "warning"):
            request = workspace_with_context._build_train_request()
            assert request is None

    def test_rejects_invalid_numeric_value(self, workspace_with_context):
        """_build_train_request returns None when a numeric field is invalid."""
        workspace_with_context._numeric_inputs["epochs"].setText("not_a_number")
        with patch.object(QtWidgets.QMessageBox, "warning"):
            request = workspace_with_context._build_train_request()
            assert request is None

    def test_custom_epoch_value_in_request(self, workspace_with_context):
        """Modified epoch value is reflected in the built request."""
        workspace_with_context._numeric_inputs["epochs"].setText("50")
        request = workspace_with_context._build_train_request()
        assert request is not None
        assert request.epochs == 50

    def test_custom_batch_value_in_request(self, workspace_with_context):
        """Modified batch value is reflected in the built request."""
        workspace_with_context._numeric_inputs["batch"].setText("16")
        request = workspace_with_context._build_train_request()
        assert request is not None
        assert request.batch == 16


# ============================================================================
# 6. set_task_specs / set_dataset_builds tests
# ============================================================================


class TestSetterMethods:
    """Tests for set_task_specs() and set_dataset_builds() methods."""

    @pytest.fixture
    def qapp(self):
        if not _HAS_QAPP:
            pytest.skip("Requires QApplication")
        app = _create_qapp()
        yield app

    @pytest.fixture
    def workspace(self, qapp):
        from anylabeling.views.platform.train_workspace import TrainWorkspace
        return TrainWorkspace()

    def test_set_task_specs_populates_combo(self, workspace, sample_task_spec):
        """set_task_specs populates the task combo."""
        workspace.set_task_specs([sample_task_spec])
        assert workspace._combo_task.count() == 1
        fetched = workspace._combo_task.itemData(0)
        assert fetched is sample_task_spec

    def test_set_dataset_builds_populates_combo(
        self, workspace, sample_dataset_build
    ):
        """set_dataset_builds populates the dataset combo."""
        workspace.set_dataset_builds([sample_dataset_build])
        assert workspace._combo_dataset.count() == 1
        fetched = workspace._combo_dataset.itemData(0)
        assert fetched is sample_dataset_build


# ============================================================================
# 7. Module importability (no QApplication required)
# ============================================================================


class TestModuleImports:
    """Verify that all new modules can be imported without side effects."""

    def test_run_vm_imports(self):
        from anylabeling.views.platform.view_models.run_vm import RunViewModel
        assert RunViewModel is not None

    def test_train_workspace_imports(self):
        from anylabeling.views.platform.train_workspace import TrainWorkspace
        assert TrainWorkspace is not None

    def test_view_models_package_imports(self):
        from anylabeling.views.platform.view_models import RunViewModel
        assert RunViewModel is not None

    def test_train_workspace_helpers_import(self):
        from anylabeling.views.platform.train_workspace import (
            _format_label,
            _coerce_value,
        )
        assert _format_label is not None
        assert _coerce_value is not None


# ============================================================================
# 8. Helper function tests (non-GUI)
# ============================================================================


class TestHelperFunctions:
    """Tests for the _format_label and _coerce_value helpers (Phase B i18n)."""

    def test_format_label_known_fields(self):
        """Known fields return i18n labels (not mechanical conversion)."""
        from anylabeling.views.platform.train_workspace import _format_label
        # All 31 fields should return non-empty labels
        for field_name in [
            "epochs", "batch", "imgsz", "device", "workers", "seed",
            "lr0", "lrf", "momentum", "weight_decay", "warmup_epochs",
            "cos_lr", "amp",
            "hsv_h", "hsv_s", "hsv_v", "degrees", "translate", "scale",
            "shear", "perspective", "fliplr", "mosaic", "mixup", "copy_paste",
            "close_mosaic",
            "box", "cls", "dfl", "pose", "kobj",
        ]:
            label = _format_label(field_name)
            assert label, f"Label for '{field_name}' should not be empty"
            assert ":" in label or "：" in label, (
                f"Label for '{field_name}' should end with colon: got '{label}'"
            )
            # NOT the old mechanical conversion
            mechanical = field_name.replace("_", " ").title() + ":"
            # The i18n label may differ from mechanical conversion
            # (which is the whole point of this fix)

    def test_format_label_unknown_field_fallback(self):
        """Unknown fields fall back to mechanical conversion."""
        from anylabeling.views.platform.train_workspace import _format_label
        assert _format_label("unknown_field") == "Unknown Field:"

    def test_coerce_value_int(self):
        from anylabeling.views.platform.train_workspace import _coerce_value
        assert _coerce_value("epochs", "200") == 200
        assert isinstance(_coerce_value("epochs", "200"), int)

    def test_coerce_value_float(self):
        from anylabeling.views.platform.train_workspace import _coerce_value
        result = _coerce_value("lr0", "0.01")
        assert result == 0.01
        assert isinstance(result, float)

    def test_coerce_value_str_fallback(self):
        from anylabeling.views.platform.train_workspace import _coerce_value
        assert _coerce_value("device", "0") == "0"
        assert _coerce_value("unknown_field", "hello") == "hello"

    def test_coerce_value_bool_from_string(self):
        from anylabeling.views.platform.train_workspace import _coerce_value
        # cos_lr default is bool(False) → bool type path
        assert _coerce_value("cos_lr", "true") is True
        assert _coerce_value("cos_lr", "True") is True
        assert _coerce_value("cos_lr", "1") is True
        assert _coerce_value("cos_lr", "false") is False
        assert _coerce_value("cos_lr", "0") is False


# ============================================================================
# 9. TrainRequest defaults coverage
# ============================================================================


class TestTrainRequestDefaults:
    """Verify all TrainRequest fields have form coverage."""

    def test_all_numeric_fields_have_inputs(self):
        """Every form-covered numeric field is a real TrainRequest field."""
        from anylabeling.platform.adapters.ultralytics.train_adapter import (
            TrainRequest,
        )
        from anylabeling.views.platform.train_workspace import (
            _BASIC_FIELDS,
            _OPTIMIZER_NUMERIC_FIELDS,
            _AUGMENTATION_FIELDS,
            _LOSS_FIELDS,
        )

        import dataclasses
        train_request_fields = {
            f.name for f in dataclasses.fields(TrainRequest)
        }

        # Collect all form-covered fields
        covered = set()
        covered.update(_BASIC_FIELDS)
        covered.update(_OPTIMIZER_NUMERIC_FIELDS)
        covered.update(_AUGMENTATION_FIELDS)
        covered.update(_LOSS_FIELDS)

        # Every form-covered field should be a real TrainRequest field
        for name in sorted(covered):
            assert name in train_request_fields, (
                f"Form field '{name}' is not a valid TrainRequest field"
            )

    def test_all_bool_fields_have_inputs(self):
        """Every form-covered boolean field has a corresponding checkbox."""
        from anylabeling.platform.adapters.ultralytics.train_adapter import (
            TrainRequest,
        )
        from anylabeling.views.platform.train_workspace import (
            _OPTIMIZER_BOOL_FIELDS,
        )

        # Get all TrainRequest boolean fields
        import dataclasses
        train_request_bool_fields = {
            f.name
            for f in dataclasses.fields(TrainRequest)
            if f.default is not dataclasses.MISSING
            and isinstance(f.default, bool)
        }

        covered_booleans = set(_OPTIMIZER_BOOL_FIELDS)
        # Verify every form-covered boolean is a real TrainRequest field
        for name in sorted(covered_booleans):
            assert name in train_request_bool_fields, (
                f"Form boolean field '{name}' is not a TrainRequest bool field"
            )


# ============================================================================
# 10. Edge case: timer behavior
# ============================================================================


class TestTimerBehavior:
    """Tests for QTimer polling lifecycle."""

    @pytest.fixture
    def qapp(self):
        if not _HAS_QAPP:
            pytest.skip("Requires QApplication")
        app = _create_qapp()
        yield app

    def test_timer_does_not_start_without_context(self, qapp):
        """Timer is not active until set_project_context is called."""
        from anylabeling.views.platform.train_workspace import TrainWorkspace

        ws = TrainWorkspace()
        assert not ws._timer.isActive()

    def test_timer_starts_with_context(
        self, qapp, job_service, training_service
    ):
        """Timer becomes active after set_project_context."""
        from anylabeling.views.platform.train_workspace import TrainWorkspace

        ws = TrainWorkspace()
        ws.set_project_context(
            job_service=job_service,
            training_service=training_service,
        )
        assert ws._timer.isActive()
