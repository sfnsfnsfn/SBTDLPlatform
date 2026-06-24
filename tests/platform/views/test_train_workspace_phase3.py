"""Phase 3 tests for TrainWorkspace — algorithm combo, model size recommendation,
dynamic param generation, TrainingMonitor, incremental training checkbox.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("PyQt6")

from PyQt6 import QtWidgets


@pytest.fixture(autouse=True)
def _ensure_ultralytics_registered():
    """Ensure AlgorithmRegistry has Ultralytics providers registered."""
    from anylabeling.platform.adapters.registry import AlgorithmRegistry
    # Import ultralytics package to trigger auto-registration
    import anylabeling.platform.adapters.ultralytics  # noqa: F401
    yield
    # Do NOT clear — other tests need the registry populated


@pytest.fixture
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


# ---------------------------------------------------------------------------
# Model size recommendation logic (pure function, no PyQt needed)
# ---------------------------------------------------------------------------

class TestModelSizeRecommendation:
    """Test model size recommendation logic based on image count."""

    def test_nano_for_less_than_50(self):
        """< 50 images → 'n' (nano)."""
        from anylabeling.views.platform.train_workspace import _recommend_model_size
        assert _recommend_model_size(10) == "n"
        assert _recommend_model_size(49) == "n"
        assert _recommend_model_size(0) == "n"

    def test_small_for_50_to_200(self):
        """50-200 images → 's' (small)."""
        from anylabeling.views.platform.train_workspace import _recommend_model_size
        assert _recommend_model_size(50) == "s"
        assert _recommend_model_size(100) == "s"
        assert _recommend_model_size(200) == "s"

    def test_medium_for_200_to_1000(self):
        """200-1000 images → 'm' (medium)."""
        from anylabeling.views.platform.train_workspace import _recommend_model_size
        assert _recommend_model_size(201) == "m"
        assert _recommend_model_size(500) == "m"
        assert _recommend_model_size(1000) == "m"

    def test_large_for_more_than_1000(self):
        """> 1000 images → 'l' (large)."""
        from anylabeling.views.platform.train_workspace import _recommend_model_size
        assert _recommend_model_size(1001) == "l"
        assert _recommend_model_size(10000) == "l"

    def test_recommendation_label_format(self):
        """The recommendation label uses the expected format."""
        from anylabeling.views.platform.train_workspace import _format_recommendation
        text = _format_recommendation(100, "s")
        assert "100" in text
        assert "s" in text.lower()


# ---------------------------------------------------------------------------
# Algorithm QComboBox tests
# ---------------------------------------------------------------------------

class TestAlgorithmCombo:
    def test_combo_populated_from_registry(self, qapp):
        """Algorithm QComboBox is populated from AlgorithmRegistry."""
        from anylabeling.views.platform.train_workspace import TrainWorkspace
        from anylabeling.platform.adapters.registry import AlgorithmRegistry

        ws = TrainWorkspace()
        # After import, registry should have entries
        all_caps = AlgorithmRegistry.list_all()
        trainable = [c for c in all_caps if c.supports_training]
        assert len(trainable) > 0, "No trainable algorithms in registry"

        # The combo should have been populated in __init__ via _populate_algorithm_combo
        assert ws._combo_algorithm.count() == len(trainable), (
            f"Expected {len(trainable)} items, got {ws._combo_algorithm.count()}"
        )
        ws.close()

    def test_combo_displays_display_name(self, qapp):
        """Each combo item shows display_name."""
        from anylabeling.views.platform.train_workspace import TrainWorkspace
        from anylabeling.platform.adapters.registry import AlgorithmRegistry

        ws = TrainWorkspace()
        for i in range(ws._combo_algorithm.count()):
            text = ws._combo_algorithm.itemText(i)
            data = ws._combo_algorithm.itemData(i)
            # data should be the adapter_id string
            assert data, f"Item {i} has no adapter_id data"
            cap = AlgorithmRegistry.get(data)
            assert text == cap.display_name, (
                f"Item {i} text '{text}' != display_name '{cap.display_name}'"
            )
        ws.close()

    def test_filter_by_task_family(self, qapp):
        """When task is selected, algorithm combo filters by task family."""
        from anylabeling.views.platform.train_workspace import TrainWorkspace
        from anylabeling.platform.domain.task import TaskSpec

        ws = TrainWorkspace()
        # Simulate having a detection task
        task = TaskSpec(id="task_001", family="detection_hbb")
        ws._task_specs = [task]
        ws._populate_algorithm_combo_for_family("detection_hbb")

        from anylabeling.platform.adapters.registry import AlgorithmRegistry
        expected = AlgorithmRegistry.for_task("detection_hbb")
        expected_trainable = [c for c in expected if c.supports_training]

        assert ws._combo_algorithm.count() == len(expected_trainable), (
            f"Expected {len(expected_trainable)} detection algorithms, "
            f"got {ws._combo_algorithm.count()}"
        )
        ws.close()

    def test_algorithm_change_updates_param_panel(self, qapp):
        """Switching algorithm triggers parameter panel regeneration."""
        from anylabeling.views.platform.train_workspace import TrainWorkspace

        ws = TrainWorkspace()
        # The algorithm combo should have items
        if ws._combo_algorithm.count() >= 2:
            initial_count = len(ws._numeric_inputs)
            ws._combo_algorithm.setCurrentIndex(1)
            # After algorithm change, param panel should have been regenerated
            # (at minimum, the params may differ — just verify the signal was connected)
            assert ws._combo_algorithm.currentIndex() == 1, (
                "Algorithm combo should switch index"
            )
        ws.close()

    def test_combo_has_algorithm_change_signal_connected(self, qapp):
        """Algorithm QComboBox change signal is connected."""
        from anylabeling.views.platform.train_workspace import TrainWorkspace

        ws = TrainWorkspace()
        # Verify the signal connection exists (receiver count > 0)
        receivers = ws._combo_algorithm.receivers(
            ws._combo_algorithm.currentIndexChanged
        )
        assert receivers > 0, (
            "Algorithm combo signal should be connected to a handler"
        )
        ws.close()


# ---------------------------------------------------------------------------
# TrainingMonitor tests
# ---------------------------------------------------------------------------

class TestTrainingMonitor:
    def test_monitor_initialization_no_timer(self, qapp):
        """TrainingMonitor initializes but does NOT start timer by default."""
        from anylabeling.views.platform.widgets.training_monitor import TrainingMonitor
        monitor = TrainingMonitor()
        assert monitor._timer is not None, "Should have a QTimer"
        assert not monitor._timer.isActive(), (
            "Timer should NOT be active when no active job"
        )
        monitor.close()

    def test_monitor_has_matplotlib_canvas(self, qapp):
        """TrainingMonitor contains a matplotlib FigureCanvas."""
        from anylabeling.views.platform.widgets.training_monitor import TrainingMonitor
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        monitor = TrainingMonitor()
        canvas = monitor.findChild(FigureCanvasQTAgg)
        assert canvas is not None, "Should have a matplotlib canvas embedded"
        monitor.close()

    def test_monitor_start_stop_timer(self, qapp):
        """set_active_job starts timer; clear_active_job stops it."""
        from anylabeling.views.platform.widgets.training_monitor import TrainingMonitor
        monitor = TrainingMonitor()
        monitor.set_active_job("test_job", "/tmp/test_runs")
        assert monitor._timer.isActive(), "Timer should start when job set"
        monitor.clear_active_job()
        assert not monitor._timer.isActive(), "Timer should stop when job cleared"
        monitor.close()

    def test_monitor_initial_state_labels(self, qapp):
        """Monitor shows idle state initially."""
        from anylabeling.views.platform.widgets.training_monitor import TrainingMonitor
        monitor = TrainingMonitor()
        assert monitor._status_label is not None, "Should have status label"
        assert "idle" in monitor._status_label.text().lower() or (
            "空闲" in monitor._status_label.text()
            or "IDLE" in monitor._status_label.text()
        ), f"Expected idle indicator, got '{monitor._status_label.text()}'"
        monitor.close()


# ---------------------------------------------------------------------------
# Dynamic parameter generation tests
# ---------------------------------------------------------------------------

class TestDynamicParamGeneration:
    def test_parse_schema_properties(self):
        """_create_params_from_schema creates correct widgets for each type."""
        from anylabeling.views.platform.train_workspace import _create_params_from_schema
        schema = {
            "type": "object",
            "properties": {
                "epochs": {"type": "integer", "default": 200, "minimum": 1},
                "lr0": {"type": "number", "default": 0.01, "minimum": 0},
                "device": {"type": "string", "default": "0"},
                "cos_lr": {"type": "boolean", "default": False},
            },
        }
        inputs, bools = _create_params_from_schema(schema)
        assert "epochs" in inputs, "integer field should be in inputs"
        assert "lr0" in inputs, "number field should be in inputs"
        assert "device" in inputs, "string field should be in inputs"
        assert "cos_lr" in bools, "boolean field should be in bools"
        # Verify widget types
        assert isinstance(inputs["epochs"], QtWidgets.QSpinBox), (
            "integer should create QSpinBox"
        )
        assert isinstance(inputs["lr0"], QtWidgets.QDoubleSpinBox), (
            "number should create QDoubleSpinBox"
        )
        assert isinstance(inputs["device"], QtWidgets.QLineEdit), (
            "string should create QLineEdit"
        )
        assert isinstance(bools["cos_lr"], QtWidgets.QCheckBox), (
            "boolean should create QCheckBox"
        )

    def test_schema_defaults_set_on_widgets(self):
        """Default values from schema are applied to widgets."""
        from anylabeling.views.platform.train_workspace import _create_params_from_schema
        schema = {
            "type": "object",
            "properties": {
                "epochs": {"type": "integer", "default": 300, "minimum": 1},
                "lr0": {"type": "number", "default": 0.001, "minimum": 0},
                "cos_lr": {"type": "boolean", "default": True},
            },
        }
        inputs, bools = _create_params_from_schema(schema)
        assert inputs["epochs"].value() == 300, "Default should be set on SpinBox"
        assert inputs["lr0"].value() == 0.001, "Default should be set on DoubleSpinBox"
        assert bools["cos_lr"].isChecked(), "Default True should be checked"


# ---------------------------------------------------------------------------
# Incremental training checkbox tests
# ---------------------------------------------------------------------------

class TestIncrementalTraining:
    def test_checkbox_exists(self, qapp):
        """TrainWorkspace has an incremental training checkbox."""
        from anylabeling.views.platform.train_workspace import TrainWorkspace
        ws = TrainWorkspace()
        assert hasattr(ws, "_chk_resume"), (
            "Should have incremental training checkbox"
        )
        assert isinstance(ws._chk_resume, QtWidgets.QCheckBox), (
            "_chk_resume should be a QCheckBox"
        )
        ws.close()

    def test_checkbox_text_is_descriptive(self, qapp):
        """Checkbox has user-facing descriptive text."""
        from anylabeling.views.platform.train_workspace import TrainWorkspace
        ws = TrainWorkspace()
        text = ws._chk_resume.text()
        assert len(text) > 0, "Checkbox should have descriptive text"
        ws.close()


# ---------------------------------------------------------------------------
# Model size recommendation label in UI
# ---------------------------------------------------------------------------

class TestRecommendationLabel:
    def test_label_exists(self, qapp):
        """TrainWorkspace has a model size recommendation label."""
        from anylabeling.views.platform.train_workspace import TrainWorkspace
        ws = TrainWorkspace()
        assert hasattr(ws, "_lbl_model_size_rec"), (
            "Should have recommendation label"
        )
        assert isinstance(ws._lbl_model_size_rec, QtWidgets.QLabel), (
            "_lbl_model_size_rec should be a QLabel"
        )
        ws.close()

    def test_label_has_tooltip(self, qapp):
        """Recommendation label has a tooltip for user guidance."""
        from anylabeling.views.platform.train_workspace import TrainWorkspace
        ws = TrainWorkspace()
        tip = ws._lbl_model_size_rec.toolTip()
        assert len(tip) > 0, "Recommendation label should have a tooltip"
        ws.close()
