"""TileInspectorPanel — per-tile detail panel showing object fragments.

Displays label fragments for a selected tile with area percentages,
truncation indicators, and accept/flag actions.
"""

from __future__ import annotations

import logging

from PyQt6 import QtCore, QtGui, QtWidgets

from anylabeling.platform.application.dataset_build_service import (
    _SPLITTER_REGISTRY,
)
from anylabeling.platform.domain.annotation import AnnotationDocument, AnnotationObject
from anylabeling.platform.domain.tile import TilePlan, TileRecord
logger = logging.getLogger(__name__)


class TileInspectorPanel(QtWidgets.QWidget):
    """Per-tile detail panel.

    Shows per-tile object fragment details: area percentage,
    truncation status, and accept/flag actions.

    Signals:
        accept_tile(tile_id): User accepts the tile as valid.
        flag_tile(tile_id, reason): User flags the tile with a reason.
    """

    accept_tile = QtCore.pyqtSignal(str)
    flag_tile = QtCore.pyqtSignal(str, str)

    # Threshold for "truncated" — visibility ratio below this is flagged
    TRUNCATION_THRESHOLD = 0.8

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._tile_id: str = ""
        self._objects: list[AnnotationObject] = []
        self._source_w: int = 0
        self._source_h: int = 0
        self._build_ui()
        self._apply_theme()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        from anylabeling.views.platform.style import (
            FONT_FAMILY,
            FONT_SIZE_BODY,
            FONT_SIZE_CAPTION,
        )
        from anylabeling.views.labeling.utils.theme import get_theme

        t = get_theme()
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Title
        self._title_label = QtWidgets.QLabel()
        self._title_label.setStyleSheet(
            f"font-family: {FONT_FAMILY}; font-size: {FONT_SIZE_BODY + 2}px; "
            f"font-weight: bold; color: {t['text']};"
        )
        layout.addWidget(self._title_label)

        # Region info
        self._region_label = QtWidgets.QLabel()
        self._region_label.setStyleSheet(
            f"font-family: {FONT_FAMILY}; font-size: {FONT_SIZE_CAPTION}px; "
            f"color: {t['text_secondary']};"
        )
        layout.addWidget(self._region_label)

        # Separator
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {t['border']};")
        layout.addWidget(sep)

        # Object count
        self._obj_count_label = QtWidgets.QLabel()
        self._obj_count_label.setStyleSheet(
            f"font-family: {FONT_FAMILY}; font-size: {FONT_SIZE_BODY}px; "
            f"color: {t['text']};"
        )
        layout.addWidget(self._obj_count_label)

        # Object list
        self._obj_list = QtWidgets.QListWidget()
        self._obj_list.setStyleSheet(
            f"QListWidget {{ border: 1px solid {t['border']}; "
            f"border-radius: 4px; background-color: {t['surface']}; "
            f"font-family: {FONT_FAMILY}; font-size: {FONT_SIZE_CAPTION}px; "
            f"color: {t['text']}; }}"
        )
        self._obj_list.setMinimumHeight(120)
        layout.addWidget(self._obj_list, stretch=1)

        # Action buttons
        btn_layout = QtWidgets.QHBoxLayout()
        self._accept_btn = QtWidgets.QPushButton("Accept")
        self._accept_btn.clicked.connect(self._on_accept)
        btn_layout.addWidget(self._accept_btn)

        self._flag_btn = QtWidgets.QPushButton("Flag")
        self._flag_btn.clicked.connect(self._on_flag)
        btn_layout.addWidget(self._flag_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def _apply_theme(self) -> None:
        """Apply theme-aware button styling."""
        from anylabeling.views.platform.style import (
            get_primary_button_style,
            get_secondary_button_style,
        )

        self._accept_btn.setStyleSheet(get_primary_button_style())
        self._flag_btn.setStyleSheet(get_secondary_button_style())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_tile(
        self,
        tile: TileRecord,
        objects: list[AnnotationObject],
        source_image_size: tuple[int, int],
        tile_plan: TilePlan | None = None,
        task_family: str = "",
    ) -> None:
        """Display tile details and split annotation objects on-the-fly.

        Parameters
        ----------
        tile:
            The TileRecord for the selected tile.
        objects:
            Full-image AnnotationObjects (L0 coordinates).
        source_image_size:
            ``(width, height)`` of the source image in L0 pixels.
        tile_plan:
            Optional TilePlan used to run label splitters. If omitted,
            a basic visibility check is performed.
        task_family:
            Task family string used to select the right label splitter.
        """
        self._tile_id = tile.tile_id
        self._source_w, self._source_h = source_image_size

        # Build a temporary AnnotationDocument
        ann_doc = AnnotationDocument(
            asset_id=tile.asset_id,
            image_width=self._source_w,
            image_height=self._source_h,
            objects=objects,
        )

        # Run label splitters on-the-fly
        if tile_plan is not None and task_family:
            splitter_cls = _SPLITTER_REGISTRY.get(task_family)
            if splitter_cls is not None:
                try:
                    splitter = splitter_cls()
                    self._objects = splitter.split(ann_doc, tile, tile_plan)
                except Exception:
                    logger.exception(
                        "Label splitter failed for tile %s", tile.tile_id
                    )
                    self._objects = []
            else:
                self._objects = []
        else:
            # Basic visibility check — clip objects manually
            self._objects = self._basic_clip(objects, tile)

        self._render_tile_info(tile)
        self._render_object_list()

    def _basic_clip(
        self, objects: list[AnnotationObject], tile: TileRecord
    ) -> list[AnnotationObject]:
        """Manual visibility check without full splitter (fallback)."""
        results: list[AnnotationObject] = []
        tx1 = tile.x0
        ty1 = tile.y0
        tx2 = tile.x0 + tile.width
        ty2 = tile.y0 + tile.height

        for obj in objects:
            if obj.geometry_type == "bbox_xyxy":
                x1, y1, x2, y2 = obj.geometry  # type: ignore[misc]
                ix1 = max(x1, tx1)
                iy1 = max(y1, ty1)
                ix2 = min(x2, tx2)
                iy2 = min(y2, ty2)
                if ix1 >= ix2 or iy1 >= iy2:
                    continue
                inter_area = (ix2 - ix1) * (iy2 - iy1)
                orig_area = (x2 - x1) * (y2 - y1)
                if orig_area <= 0:
                    continue
                visibility = inter_area / orig_area
                results.append(
                    AnnotationObject(
                        id=obj.id,
                        label_id=obj.label_id,
                        geometry_type="bbox_xyxy",
                        geometry=(
                            ix1 - tile.x0, iy1 - tile.y0,
                            ix2 - tile.x0, iy2 - tile.y0,
                        ),
                        attributes={"visibility": visibility},
                        source_object_id=obj.id,
                    )
                )
            elif obj.geometry_type in ("polygon", "obb_polygon"):
                # Simple bbox approximation
                points = obj.geometry  # type: ignore[assignment]
                xs = [p[0] for p in points]
                ys = [p[1] for p in points]
                x1, x2 = min(xs), max(xs)
                y1, y2 = min(ys), max(ys)
                ix1 = max(x1, tx1)
                iy1 = max(y1, ty1)
                ix2 = min(x2, tx2)
                iy2 = min(y2, ty2)
                if ix1 >= ix2 or iy1 >= iy2:
                    continue
                inter_area = (ix2 - ix1) * (iy2 - iy1)
                orig_area = (x2 - x1) * (y2 - y1)
                if orig_area <= 0:
                    continue
                visibility = inter_area / orig_area
                results.append(
                    AnnotationObject(
                        id=obj.id,
                        label_id=obj.label_id,
                        geometry_type=obj.geometry_type,
                        geometry=points,
                        attributes={"visibility": visibility},
                        source_object_id=obj.id,
                    )
                )
        return results

    def _render_tile_info(self, tile: TileRecord) -> None:
        """Populate the title and region labels."""
        from anylabeling.views.platform.i18n import tr

        self._title_label.setText(
            tr(
                f"切片: {tile.tile_id[-16:]}",
                f"Tile: {tile.tile_id[-16:]}",
            )
        )
        self._region_label.setText(
            tr(
                f"区域: ({tile.x0}, {tile.y0}) {tile.width}×{tile.height}",
                f"Region: ({tile.x0}, {tile.y0}) {tile.width}×{tile.height}",
            )
        )
        self._obj_count_label.setText(
            tr(
                f"切片内目标: {len(self._objects)}",
                f"Objects in tile: {len(self._objects)}",
            )
        )

    def _render_object_list(self) -> None:
        """Populate the object list widget with colour-coded items."""
        self._obj_list.clear()

        for obj in self._objects:
            visibility = obj.attributes.get("visibility", 1.0)
            is_truncated = visibility < self.TRUNCATION_THRESHOLD

            # Determine icon
            if is_truncated:
                prefix = "⚠"
                tooltip = (
                    f"Truncated — visibility: {visibility:.0%}"
                )
            else:
                prefix = "✓"
                tooltip = f"Fully visible — visibility: {visibility:.0%}"

            text = (
                f"{prefix} {obj.id}: {obj.geometry_type} "
                f"({visibility:.0%})"
            )

            item = QtWidgets.QListWidgetItem(text)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, obj.id)
            item.setToolTip(tooltip)

            # Color-code
            if is_truncated:
                item.setForeground(QtGui.QColor(255, 165, 0))  # orange
            else:
                item.setForeground(QtGui.QColor(0, 160, 80))  # green

            self._obj_list.addItem(item)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_accept(self) -> None:
        """Emit accept_tile for the current tile."""
        if self._tile_id:
            self.accept_tile.emit(self._tile_id)

    def _on_flag(self) -> None:
        """Prompt for a flag reason then emit flag_tile."""
        if not self._tile_id:
            return
        from anylabeling.views.platform.i18n import tr

        reason, ok = QtWidgets.QInputDialog.getText(
            self,
            tr("标记切片", "Flag Tile"),
            tr("标记原因:", "Flag reason:"),
            QtWidgets.QLineEdit.EchoMode.Normal,
            "",
        )
        if ok and reason.strip():
            self.flag_tile.emit(self._tile_id, reason.strip())


__all__ = ["TileInspectorPanel"]
