"""ModelLibrary— browseable gallery of trained model run records.

Displays completed training runs as cards in a scrollable grid with
search and task-family filtering.  Follows QWIDGET_PATTERN: signals
at class level, _build_ui() pattern.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6 import QtCore, QtWidgets

from anylabeling.views.platform.i18n import tr
from anylabeling.views.platform.style import (
    FONT_FAMILY,
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
    get_combo_style,
    get_input_style,
)
from anylabeling.views.labeling.utils.theme import get_theme

logger = logging.getLogger(__name__)

_COLS = 3


class _ModelCard(QtWidgets.QFrame):
    """Single model-run card within the library grid.

    Signals:
        clicked(run_id: str): Emitted when the card is clicked.
    """

    clicked = QtCore.pyqtSignal(str)

    def __init__(
        self,
        run_id: str,
        task_family: str,
        status: str,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._run_id = run_id
        self.setFrameStyle(QtWidgets.QFrame.Shape.StyledPanel)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(200, 120)
        self._build_ui(task_family, status)

    def _build_ui(self, task_family: str, status: str) -> None:
        t = get_theme()
        self.setStyleSheet(f"""
            _ModelCard {{
                background-color: {t["background_secondary"]};
                border: 1px solid {t["border_light"]};
                border-radius: 8px;
                padding: 8px;
            }}
            _ModelCard:hover {{
                border-color: {t["primary"]};
            }}
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        task_label = QtWidgets.QLabel(task_family)
        task_label.setStyleSheet(
            f"font-weight: bold; font-size: {FONT_SIZE_BODY}px;"
            f"color: {t['primary']}; font-family: {FONT_FAMILY};"
        )
        layout.addWidget(task_label)

        id_label = QtWidgets.QLabel(self._run_id)
        id_label.setWordWrap(True)
        id_label.setStyleSheet(
            f"font-size: {FONT_SIZE_CAPTION}px;"
            f"color: {t['text_secondary']}; font-family: {FONT_FAMILY};"
        )
        layout.addWidget(id_label)

        status_text = {
            "completed": tr("已完成", "Completed"),
            "running": tr("训练中", "Training"),
            "failed": tr("失败", "Failed"),
        }.get(status, status)
        status_color = (
            t.get("success") if status == "completed"
            else t.get("error") if status == "failed"
            else t["text_secondary"]
        )
        status_label = QtWidgets.QLabel(status_text)
        status_label.setStyleSheet(
            f"font-size: {FONT_SIZE_CAPTION}px;"
            f"color: {status_color}; font-family: {FONT_FAMILY};"
        )
        layout.addWidget(status_label)
        layout.addStretch()

    def mousePressEvent(self, event: QtCore.QEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.clicked.emit(self._run_id)
        super().mousePressEvent(event)


class ModelLibrary(QtWidgets.QWidget):
    """Browseable model gallery with search and task-family filter.

    Signals:
        model_selected(run_id: str): Emitted when a model card is clicked.
    """

    model_selected = QtCore.pyqtSignal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._training_service = None
        self._models: list[dict] = []
        self._build_ui()

    # ------------------------------------------------------------------
    # UI build
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        bar = QtWidgets.QHBoxLayout()
        bar.setSpacing(8)

        self._search_input = QtWidgets.QLineEdit()
        self._search_input.setPlaceholderText(
            tr("搜索模型...", "Search models...")
        )
        self._search_input.setStyleSheet(get_input_style())
        self._search_input.textChanged.connect(self._on_search_changed)
        bar.addWidget(self._search_input, 1)

        self._task_filter = QtWidgets.QComboBox()
        self._task_filter.addItem(tr("全部任务", "All Tasks"), "")
        self._task_filter.addItem(tr("检测", "Detection"), "detection_hbb")
        self._task_filter.addItem(
            tr("实例分割", "Instance Seg"), "instance_seg"
        )
        self._task_filter.addItem(
            tr("分类", "Classification"), "classification"
        )
        self._task_filter.addItem(tr("姿态", "Pose"), "pose")
        self._task_filter.setStyleSheet(get_combo_style())
        self._task_filter.currentIndexChanged.connect(self._on_filter_changed)
        bar.addWidget(self._task_filter)
        layout.addLayout(bar)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )

        self._grid_container = QtWidgets.QWidget()
        self._grid = QtWidgets.QGridLayout(self._grid_container)
        self._grid.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignTop
            | QtCore.Qt.AlignmentFlag.AlignLeft
        )
        self._grid.setSpacing(8)
        scroll.setWidget(self._grid_container)
        layout.addWidget(scroll, 1)

        t = get_theme()
        self._empty_label = QtWidgets.QLabel(
            tr("暂无已训练的模型", "No trained models yet")
        )
        self._empty_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(
            f"font-size: {FONT_SIZE_BODY}px;"
            f"color: {t['text_placeholder']};"
            f"font-family: {FONT_FAMILY};"
            f"padding: 32px;"
        )
        self._empty_label.setVisible(False)
        layout.addWidget(self._empty_label)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_training_service(
        self,
        training_service: "TrainingService",  # type: ignore[name-defined]  # noqa: F821
    ) -> None:
        """Set the training service and refresh the model list.

        Args:
            training_service: A TrainingService instance with a
                project_root attribute and read_run_record method.
        """
        self._training_service = training_service
        self._refresh()

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        """Scan runs/ directory and populate model cards."""
        self._clear_grid()
        self._models = []

        if self._training_service is None:
            self._empty_label.setVisible(True)
            return

        project_root = Path(self._training_service.project_root)
        runs_dir = project_root / "runs"
        if not runs_dir.exists():
            self._empty_label.setVisible(True)
            return

        for run_dir in sorted(runs_dir.iterdir(), reverse=True):
            if not run_dir.is_dir():
                continue
            try:
                run = self._training_service.read_run_record(run_dir.name)
                if run is None:
                    continue
            except Exception:
                logger.debug(
                    "Skipping run directory %s", run_dir.name, exc_info=True
                )
                continue

            self._models.append({
                "id": run.id,
                "task_family": run.task_family or "unknown",
                "status": run.status or "unknown",
                "created_at": getattr(run, "created_at", ""),
            })

        if not self._models:
            self._empty_label.setVisible(True)
            return

        self._empty_label.setVisible(False)
        self._render_cards(self._models)

    def _clear_grid(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    # ------------------------------------------------------------------
    # Card rendering
    # ------------------------------------------------------------------

    def _render_cards(self, models: list[dict]) -> None:
        self._clear_grid()
        for i, model in enumerate(models):
            card = _ModelCard(
                run_id=model["id"],
                task_family=model.get("task_family", "unknown"),
                status=model.get("status", "unknown"),
                parent=self,
            )
            card.clicked.connect(self.model_selected.emit)
            row, col = divmod(i, _COLS)
            self._grid.addWidget(card, row, col)

    # ------------------------------------------------------------------
    # Filter / Search
    # ------------------------------------------------------------------

    def _apply_filters(self) -> None:
        text_lower = self._search_input.text().lower()
        task = self._task_filter.currentData()
        filtered = [
            m
            for m in self._models
            if (not task or m.get("task_family") == task)
            and (
                not text_lower
                or text_lower in m.get("id", "").lower()
                or text_lower in m.get("task_family", "").lower()
            )
        ]
        self._render_cards(filtered)

    def _on_search_changed(self, text: str) -> None:
        self._apply_filters()

    def _on_filter_changed(self) -> None:
        self._apply_filters()


__all__ = ["ModelLibrary"]
