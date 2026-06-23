"""App bar — top-level application bar (48 px)."""

from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from anylabeling.views.platform.i18n import tr
from anylabeling.views.platform.style import (
    APPBAR_HEIGHT,
    FONT_FAMILY,
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
)
from anylabeling.views.labeling.utils.theme import get_theme


class AppBar(QtWidgets.QWidget):
    """Top application bar — fixed 48 px height.

    Layout::

        [Logo + App Name] ... [Project▼] ... [●N Task Center] [⚙ Settings] [? Help]

    Emits signals for project selection, task center toggle,
    settings, and help requests.
    """

    project_selected = QtCore.pyqtSignal(str)  # project path
    task_center_toggled = QtCore.pyqtSignal()
    models_requested = QtCore.pyqtSignal()
    settings_requested = QtCore.pyqtSignal()
    help_requested = QtCore.pyqtSignal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)

        self._project_name: str = ""
        self._project_health: str = "unknown"
        self._task_count: int = 0

        self._build_ui()
        self._apply_theme()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_project(self, name: str, health: str = "healthy") -> None:
        """Set the current project name and health indicator."""
        self._project_name = name
        self._project_health = health
        self._project_btn.setText(name)
        self._update_health_indicator()
        self._project_group.setVisible(True)
        self._models_btn.setVisible(True)

    def set_task_count(self, active: int) -> None:
        """Update the task center badge count."""
        self._task_count = active
        if active > 0:
            self._task_btn.setText(
                tr(f"任务中心 ●{active}", f"Task Center ●{active}")
            )
            self._task_btn.setVisible(True)
        else:
            self._task_btn.setVisible(False)

    def clear_project(self) -> None:
        """Hide the project section (no project open)."""
        self._project_group.setVisible(False)
        self._project_name = ""
        self._project_health = "unknown"
        self._task_count = 0
        self._task_btn.setVisible(False)
        self._models_btn.setVisible(False)

    # ------------------------------------------------------------------
    # Internal — UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setFixedHeight(APPBAR_HEIGHT)

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)

        # Left: Logo + App name
        self._logo_label = QtWidgets.QLabel("X")
        self._logo_label.setFixedSize(24, 24)
        self._logo_label.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignCenter
        )
        self._logo_label.setStyleSheet(
            f"font-weight: 900; font-size: 14px; "
            f"font-family: {FONT_FAMILY}; "
            f"background-color: {get_theme()['primary']}; "
            f"color: #ffffff; border-radius: 4px;"
        )

        self._app_name = QtWidgets.QLabel(
            tr("视觉算法平台", "Vision Algorithm Platform")
        )
        self._app_name.setStyleSheet(
            f"font-weight: 700; font-size: {FONT_SIZE_BODY}px; "
            f"font-family: {FONT_FAMILY};"
        )

        layout.addWidget(self._logo_label)
        layout.addWidget(self._app_name)
        layout.addSpacing(16)

        # Middle: Project selector
        self._project_group = QtWidgets.QWidget()
        pg_layout = QtWidgets.QHBoxLayout()
        pg_layout.setContentsMargins(0, 0, 0, 0)
        pg_layout.setSpacing(4)

        self._health_label = QtWidgets.QLabel()
        self._health_label.setFixedSize(8, 8)
        self._health_label.setStyleSheet(
            "border-radius: 4px; background-color: #52c41a;"
        )

        self._project_btn = QtWidgets.QPushButton()
        self._project_btn.setFlat(True)
        self._project_btn.setCursor(
            QtCore.Qt.CursorShape.PointingHandCursor
        )
        self._project_btn.clicked.connect(
            lambda: self.project_selected.emit("__toggle__")
        )

        pg_layout.addWidget(self._health_label)
        pg_layout.addWidget(self._project_btn)
        self._project_group.setLayout(pg_layout)
        self._project_group.setVisible(False)
        layout.addWidget(self._project_group)

        layout.addStretch(1)

        # Right: actions
        # Task center button
        self._task_btn = QtWidgets.QPushButton()
        self._task_btn.setFlat(True)
        self._task_btn.setCursor(
            QtCore.Qt.CursorShape.PointingHandCursor
        )
        self._task_btn.clicked.connect(self.task_center_toggled.emit)
        self._task_btn.setVisible(False)
        layout.addWidget(self._task_btn)

        # Models button
        self._models_btn = QtWidgets.QPushButton(
            tr("模型库", "Models")
        )
        self._models_btn.setFlat(True)
        self._models_btn.setCursor(
            QtCore.Qt.CursorShape.PointingHandCursor
        )
        self._models_btn.clicked.connect(self.models_requested.emit)
        self._models_btn.setVisible(False)
        layout.addWidget(self._models_btn)

        # Settings button
        self._settings_btn = QtWidgets.QPushButton(
            tr("设置", "Settings")
        )
        self._settings_btn.setFlat(True)
        self._settings_btn.setCursor(
            QtCore.Qt.CursorShape.PointingHandCursor
        )
        self._settings_btn.clicked.connect(self.settings_requested.emit)
        layout.addWidget(self._settings_btn)

        # Help button
        self._help_btn = QtWidgets.QPushButton(tr("帮助", "Help"))
        self._help_btn.setFlat(True)
        self._help_btn.setCursor(
            QtCore.Qt.CursorShape.PointingHandCursor
        )
        self._help_btn.clicked.connect(self.help_requested.emit)
        layout.addWidget(self._help_btn)

        self.setLayout(layout)

    # ------------------------------------------------------------------
    # Internal — theme
    # ------------------------------------------------------------------

    def _apply_theme(self) -> None:
        t = get_theme()
        self.setStyleSheet(f"""
            AppBar {{
                background-color: {t["background"]};
                border-bottom: 1px solid {t["border"]};
            }}
        """)
        self._app_name.setStyleSheet(
            f"font-weight: 700; font-size: {FONT_SIZE_BODY}px; "
            f"color: {t['text']}; font-family: {FONT_FAMILY};"
        )
        self._project_btn.setStyleSheet(f"""
            QPushButton {{
                color: {t["text"]};
                border: none;
                background: transparent;
                font-size: {FONT_SIZE_BODY}px;
                font-family: {FONT_FAMILY};
                padding: 2px 8px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {t["highlight"]}22;
            }}
        """)
        flat_style = f"""
            QPushButton {{
                color: {t["text_secondary"]};
                border: none;
                background: transparent;
                font-size: {FONT_SIZE_CAPTION}px;
                font-family: {FONT_FAMILY};
                padding: 4px 10px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                color: {t["text"]};
                background-color: {t["highlight"]}22;
            }}
        """
        self._settings_btn.setStyleSheet(flat_style)
        self._help_btn.setStyleSheet(flat_style)
        self._models_btn.setStyleSheet(flat_style)
        self._task_btn.setStyleSheet(f"""
            QPushButton {{
                color: {t["primary"]};
                border: none;
                background: transparent;
                font-size: {FONT_SIZE_CAPTION}px;
                font-family: {FONT_FAMILY};
                font-weight: 600;
                padding: 4px 10px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {t["highlight"]}22;
            }}
        """)

    def _update_health_indicator(self) -> None:
        t = get_theme()
        color_map = {
            "healthy": "#52c41a",
            "warning": "#faad14",
            "error": "#ff4d4f",
            "unknown": t["text_secondary"],
        }
        color = color_map.get(self._project_health, color_map["unknown"])
        self._health_label.setStyleSheet(
            f"border-radius: 4px; background-color: {color};"
        )
        self._health_label.setToolTip(
            tr(
                f"项目健康: {self._project_health}",
                f"Project health: {self._project_health}",
            )
        )
