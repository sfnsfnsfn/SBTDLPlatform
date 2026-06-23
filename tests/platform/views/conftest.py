"""Shared fixtures for platform views tests — manages QApplication lifecycle."""

from __future__ import annotations

import sys

import pytest

try:
    from PyQt6 import QtCore, QtWidgets

    _HAS_PYQT = True
except ImportError:
    _HAS_PYQT = False


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication — created once, reused across all tests."""
    if not _HAS_PYQT:
        pytest.skip("PyQt6 not available")
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    QtCore.QTimer.singleShot(0, lambda: None)
    yield app
    # Let Qt process pending events before cleanup
    app.processEvents()
