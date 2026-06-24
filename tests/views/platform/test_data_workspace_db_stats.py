"""Tests for DataWorkspace DB-backed statistics via ProjectContext (F2-1).

These tests verify that DataWorkspace can read statistics from a
ProjectContext (DB-backed) source and fall back gracefully when no
context is available.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6")


@pytest.fixture
def qapp():
    """Create a QApplication instance for widget tests."""
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


class TestDataWorkspaceDbStats:
    """DataWorkspace reads DB statistics via ProjectContext."""

    def test_set_context_stores_reference(self, qapp):
        """set_context stores the context for later use."""
        from anylabeling.views.platform.data_workspace import DataWorkspace

        ws = DataWorkspace()
        assert ws._context is None

        context = MagicMock()
        ws.set_context(context)
        assert ws._context is context

    def test_refresh_stats_with_context(self, qapp):
        """refresh_stats queries context and updates labels from DB stats."""
        from anylabeling.views.platform.data_workspace import DataWorkspace

        ws = DataWorkspace()

        context = MagicMock()
        context.assets.stats.return_value = {
            "total_assets": 150,
            "annotated_count": 90,
            "completed_builds": 3,
        }
        ws.set_context(context)
        ws.refresh_stats()

        # Verify context was queried
        context.assets.stats.assert_called_once()

        # Verify labels display DB values
        assert "150" in ws._stats_label.text()
        coverage_text = ws._coverage_label.text()
        assert "90" in coverage_text
        assert "150" in coverage_text
        assert "3" in ws._builds_label.text()

    def test_refresh_stats_without_context_fallback(self, qapp):
        """refresh_stats with no context does not crash."""
        from anylabeling.views.platform.data_workspace import DataWorkspace

        ws = DataWorkspace()

        # Should not raise when context is not set
        ws.refresh_stats()

        # Labels remain intact
        assert ws._stats_label is not None
        assert ws._coverage_label is not None
        assert ws._builds_label is not None
