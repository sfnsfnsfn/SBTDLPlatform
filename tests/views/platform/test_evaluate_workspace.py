"""TDD: Evaluate Workspace UI tests."""

from __future__ import annotations

import os
import pytest


class TestEvaluateImports:
    def test_module_importable(self):
        from anylabeling.views.platform import evaluate_workspace  # noqa: F401


class TestEvaluateHelpers:
    def test_format_metric(self):
        from anylabeling.views.platform.evaluate_workspace import _format_metric
        assert _format_metric("mAP50", 0.742) == "mAP50: 0.742"

    def test_format_metric_percent(self):
        from anylabeling.views.platform.evaluate_workspace import _format_metric
        assert _format_metric("Precision", 0.853, True) == "Precision: 85.3%"


_HAS_DISPLAY = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


@pytest.mark.skipif(not _HAS_DISPLAY, reason="Requires display")
class TestEvaluateWorkspaceGUI:
    @pytest.fixture
    def workspace(self, qapp):
        from anylabeling.views.platform.evaluate_workspace import EvaluateWorkspace
        return EvaluateWorkspace()

    def test_widget(self, workspace):
        from PyQt6.QtWidgets import QWidget
        assert isinstance(workspace, QWidget)

    def test_has_run_combo(self, workspace):
        assert workspace._run_combo is not None

    def test_has_evaluate_btn(self, workspace):
        assert workspace._evaluate_btn is not None

    def test_btn_disabled(self, workspace):
        assert not workspace._evaluate_btn.isEnabled()

    def test_has_metrics(self, workspace):
        assert workspace._metrics_text is not None
