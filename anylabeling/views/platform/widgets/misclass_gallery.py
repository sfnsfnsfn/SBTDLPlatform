"""Horizontal scrollable thumbnail gallery of misclassified samples.

Each card: thumbnail (150x100), prediction-vs-ground-truth label, and
confidence score.  Clicking a card emits ``sample_clicked(index)``.
"""

from __future__ import annotations

import logging

from anylabeling.views.platform.i18n import tr
from anylabeling.views.platform.style import FONT_FAMILY, FONT_SIZE_BODY

logger = logging.getLogger(__name__)

try:
    from PyQt6.QtWidgets import (
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QScrollArea,
        QLabel,
        QFrame,
    )
    from PyQt6 import QtCore
    from PyQt6.QtCore import pyqtSignal, Qt
    from PyQt6.QtGui import QPixmap

    class MisclassGallery(QWidget):
        """Horizontal scrollable thumbnail gallery of misclassified
        samples.

        Signals:
            sample_clicked(index):
                Emitted when a sample card is clicked.
        """

        sample_clicked = pyqtSignal(int)

        def __init__(self, parent=None):
            super().__init__(parent)
            self._samples: list[dict] = []
            self._cards: list[QFrame] = []
            self._build_ui()

        # ------------------------------------------------------------------
        # UI construction
        # ------------------------------------------------------------------

        def _build_ui(self):
            layout = QVBoxLayout(self)

            # Header
            header = QLabel(
                tr("误判样本", "Misclassified Samples")
            )
            header.setStyleSheet(
                f"font-weight: bold; font-size: 14px;"
                f"font-family: {FONT_FAMILY};"
            )
            layout.addWidget(header)

            # Scrollable thumbnail row
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOn
            )
            scroll.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            scroll.setFixedHeight(200)

            self._thumbnail_container = QWidget()
            self._thumbnail_layout = QHBoxLayout(
                self._thumbnail_container
            )
            self._thumbnail_layout.setAlignment(
                Qt.AlignmentFlag.AlignLeft
            )
            scroll.setWidget(self._thumbnail_container)
            layout.addWidget(scroll)

            # Empty state
            self._empty_label = QLabel(
                tr(
                    "当前评估运行没有可用的误判样本图像",
                    "Misclassification images not available"
                    " for this run",
                )
            )
            self._empty_label.setAlignment(
                Qt.AlignmentFlag.AlignCenter
            )
            self._empty_label.setWordWrap(True)
            self._empty_label.setStyleSheet(
                f"font-size: {FONT_SIZE_BODY}px;"
                f"font-family: {FONT_FAMILY};"
            )
            self._empty_label.setVisible(True)
            layout.addWidget(self._empty_label)

        # ------------------------------------------------------------------
        # public API
        # ------------------------------------------------------------------

        def set_samples(self, samples: list[dict]) -> None:
            """Display misclassified samples.

            Args:
                samples: List of dicts with keys:
                    - image_path: str (path to image file)
                    - prediction: str (predicted class name)
                    - ground_truth: str (true class name)
                    - confidence: float
                    - type: str (fp or fn)
            """
            # Clear existing cards
            while self._thumbnail_layout.count():
                item = self._thumbnail_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            self._samples = samples
            self._cards = []

            if not samples:
                self._empty_label.setVisible(True)
                return

            self._empty_label.setVisible(False)

            for i, sample in enumerate(samples):
                card = self._create_card(sample, i)
                self._thumbnail_layout.addWidget(card)
                self._cards.append(card)

        def _create_card(
            self, sample: dict, index: int
        ) -> QFrame:
            """Create a single misclassification thumbnail card."""
            card = QFrame()
            card.setFrameStyle(QFrame.Shape.StyledPanel)
            card.setFixedSize(170, 180)
            card.setCursor(Qt.CursorShape.PointingHandCursor)

            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(4, 4, 4, 4)

            # Thumbnail or placeholder
            image_path = sample.get("image_path", "")
            thumbnail = QLabel()
            thumbnail.setFixedSize(150, 100)
            thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if image_path:
                pixmap = QPixmap(image_path)
                if not pixmap.isNull():
                    pixmap = pixmap.scaled(
                        150,
                        100,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    thumbnail.setPixmap(pixmap)
                else:
                    thumbnail.setText(tr("无图像", "No Image"))
                    thumbnail.setStyleSheet(
                        f"font-family: {FONT_FAMILY};"
                    )
            else:
                thumbnail.setText(tr("无图像", "No Image"))
                thumbnail.setStyleSheet(
                    f"font-family: {FONT_FAMILY};"
                )
            card_layout.addWidget(thumbnail)

            # Prediction vs GT
            pred = sample.get("prediction", "?")
            gt = sample.get("ground_truth", "?")
            result_label = QLabel(
                f"Pred: {pred} / GT: {gt}"
            )
            result_label.setWordWrap(True)
            result_label.setStyleSheet(
                f"font-size: 11px; font-family: {FONT_FAMILY};"
            )
            card_layout.addWidget(result_label)

            # Confidence + type
            conf = sample.get("confidence", 0)
            type_str = sample.get("type", "")
            type_map = {
                "fp": tr("误检", "FP"),
                "fn": tr("漏检", "FN"),
            }
            type_display = type_map.get(type_str, type_str)
            conf_label = QLabel(
                f"{type_display} | {conf:.2f}"
            )
            conf_label.setStyleSheet(
                f"font-size: 10px; color: gray;"
                f"font-family: {FONT_FAMILY};"
            )
            card_layout.addWidget(conf_label)

            # Store index on card for event filter lookup
            card._sample_index = index  # type: ignore[attr-defined]
            card.installEventFilter(self)

            return card

        def eventFilter(self, obj, event):
            if event.type() == QtCore.QEvent.Type.MouseButtonPress:
                for card in self._cards:
                    if obj is card:
                        idx = getattr(card, "_sample_index", -1)
                        if idx >= 0:
                            self.sample_clicked.emit(idx)
                        return True
            return super().eventFilter(obj, event)

        def clear(self):
            """Clear all samples."""
            while self._thumbnail_layout.count():
                item = self._thumbnail_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self._samples = []
            self._cards = []
            self._empty_label.setVisible(True)

except ImportError:
    MisclassGallery = None  # type: ignore
