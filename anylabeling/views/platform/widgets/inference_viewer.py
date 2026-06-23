"""Scrollable image viewer with detection bounding-box overlay.

Supports zoom via mouse wheel and bounding box rendering via QPainter.
"""

from __future__ import annotations

from pathlib import Path

from anylabeling.platform.infrastructure.image_reader import ImageReader
from anylabeling.views.platform.i18n import tr

try:
    from PyQt6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QPushButton,
    )
    from PyQt6.QtGui import (
        QPixmap, QPainter, QPen, QColor, QFont, QImage, QWheelEvent,
    )
    from PyQt6.QtCore import Qt, QRectF

    _BBOX_COLORS = [
        QColor("#FF4444"), QColor("#44FF44"), QColor("#4488FF"),
        QColor("#FFAA00"), QColor("#FF44FF"), QColor("#44FFFF"),
        QColor("#FF8888"), QColor("#88FF88"), QColor("#8888FF"),
        QColor("#CCCC00"),
    ]


    class _ZoomableLabel(QLabel):
        """QLabel with mouse-wheel zoom support."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self._zoom = 1.0
            self._base_pixmap: QPixmap | None = None
            self.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setMinimumSize(200, 200)
            self.setStyleSheet("background-color: #f0f0f0;")

        def set_base_pixmap(self, pixmap: QPixmap) -> None:
            self._base_pixmap = pixmap
            self._zoom = 1.0
            self._redraw()

        def _redraw(self) -> None:
            if self._base_pixmap is None or self._base_pixmap.isNull():
                return
            w = max(1, int(self._base_pixmap.width() * self._zoom))
            h = max(1, int(self._base_pixmap.height() * self._zoom))
            scaled = self._base_pixmap.scaled(
                w, h, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.setPixmap(scaled)

        def wheelEvent(self, event: QWheelEvent) -> None:
            factor = 1.1 if event.angleDelta().y() > 0 else 0.9
            self._zoom = max(0.1, min(10.0, self._zoom * factor))
            self._redraw()


    class InferenceViewerWidget(QWidget):
        """Image viewer with detection bounding-box overlay."""

        def __init__(self, parent=None):
            super().__init__(parent)

            self._image_label = _ZoomableLabel()

            self._scroll_area = QScrollArea()
            self._scroll_area.setWidgetResizable(True)
            self._scroll_area.setWidget(self._image_label)
            self._scroll_area.setStyleSheet(
                "QScrollArea { border: 1px solid #e8e8e8; }"
            )

            self._status_label = QLabel(
                tr("选择图片开始推理", "Select an image to start inference")
            )
            self._status_label.setStyleSheet("color: #8c8c8c; font-size: 12px;")

            self._reset_zoom_btn = QPushButton(tr("重置缩放", "Reset Zoom"))
            self._reset_zoom_btn.clicked.connect(self._on_reset_zoom)

            toolbar = QHBoxLayout()
            toolbar.addWidget(self._status_label, stretch=1)
            toolbar.addWidget(self._reset_zoom_btn)

            layout = QVBoxLayout()
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addLayout(toolbar)
            layout.addWidget(self._scroll_area, stretch=1)
            self.setLayout(layout)

        # ------------------------------------------------------------------
        # Public API
        # ------------------------------------------------------------------

        def load_image(self, image_path: str) -> None:
            """Load and display an image from file."""
            import cv2

            try:
                img = ImageReader.read(image_path, output_color="BGR")
            except Exception:
                self._status_label.setText(
                    tr(f"无法加载图片：{image_path}", f"Cannot load: {image_path}")
                )
                return

            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            h, w, ch = img_rgb.shape
            bytes_per_line = ch * w
            qimage = QImage(
                img_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888
            )
            pixmap = QPixmap.fromImage(qimage.copy())

            self._image_label.set_base_pixmap(pixmap)
            self._status_label.setText(
                tr(f"图片: {Path(image_path).name} ({w}×{h})",
                   f"Image: {Path(image_path).name} ({w}x{h})")
            )

        def draw_detections(
            self,
            detections: list[dict],
            class_names: list[str],
        ) -> None:
            """Draw bounding boxes on the current image."""
            if self._image_label._base_pixmap is None:
                return

            base = self._image_label._base_pixmap
            pixmap = base.copy()
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            img_w = base.width()
            img_h = base.height()

            for det in detections:
                bbox = det["bbox"]
                cls_id = det.get("class", 0)
                conf = det.get("conf", 0.0)
                color = _BBOX_COLORS[cls_id % len(_BBOX_COLORS)]

                x1, y1, x2, y2 = [float(v) for v in bbox[:4]]
                x1, y1 = max(0, min(x1, img_w)), max(0, min(y1, img_h))
                x2, y2 = max(0, min(x2, img_w)), max(0, min(y2, img_h))

                pen_width = max(2, int(img_w / 400))
                painter.setPen(QPen(color, pen_width))
                painter.drawRect(QRectF(x1, y1, x2 - x1, y2 - y1))

                label = (
                    class_names[cls_id]
                    if cls_id < len(class_names)
                    else f"cls_{cls_id}"
                )
                text = f"{label} {conf:.2f}"

                font = QFont("Segoe UI", max(9, int(img_w / 120)))
                font.setBold(True)
                painter.setFont(font)

                fm = painter.fontMetrics()
                text_rect = fm.boundingRect(text)
                text_w = text_rect.width() + 6
                text_h = text_rect.height() + 4

                label_y = y1 - text_h - 2
                if label_y < 0:
                    label_y = y1 + 2

                painter.fillRect(QRectF(x1, label_y, text_w, text_h), color)
                painter.setPen(QPen(QColor("white")))
                painter.drawText(
                    QRectF(x1 + 3, label_y, text_w, text_h),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    text,
                )

            painter.end()
            self._image_label.set_base_pixmap(pixmap)
            self._status_label.setText(
                tr(f"检测到 {len(detections)} 个目标",
                   f"{len(detections)} object(s) detected")
            )

        def clear(self) -> None:
            """Clear all detections and reset status."""
            self._status_label.setText(
                tr("选择图片开始推理", "Select an image to start inference")
            )

        # ------------------------------------------------------------------
        # Internal
        # ------------------------------------------------------------------

        def _on_reset_zoom(self) -> None:
            if self._image_label._base_pixmap is not None:
                self._image_label.set_base_pixmap(self._image_label._base_pixmap)

except ImportError:
    InferenceViewerWidget = None  # type: ignore
