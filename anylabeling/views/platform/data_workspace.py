# STATUS: Phase 3 — import entry point + empty/non-empty states added.
"""Data Workspace -- simplified data overview with navigation to preprocessing."""

from __future__ import annotations

from pathlib import Path

from anylabeling.views.platform.i18n import tr


# ---------------------------------------------------------------------------
# Helper functions (non-GUI, testable without QApplication)
# ---------------------------------------------------------------------------


def _format_count(n: int) -> str:
    """Format an integer count with thousand separators."""
    return f"{n:,}"


def _format_coverage(ratio: float | None) -> str:
    """Format a coverage ratio as percentage string."""
    if ratio is None:
        return tr("无数据", "N/A")
    return f"{ratio * 100:.1f}%"


def _validate_split_ratios(train: float, val: float, test: float) -> list[str]:
    """Validate train/val/test split ratios. Returns list of issues (empty = valid)."""
    issues: list[str] = []

    total = train + val + test
    if abs(total - 1.0) > 0.001:
        issues.append(f"Ratios sum to {total:.3f}, expected 1.0")

    if train <= 0:
        issues.append("Train ratio must be > 0")
    if val < 0:
        issues.append("Val ratio must be >= 0")
    if test < 0:
        issues.append("Test ratio must be >= 0")

    return issues


# ---------------------------------------------------------------------------
# DataWorkspace widget
# ---------------------------------------------------------------------------

try:
    from PyQt6.QtWidgets import (
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QListWidget,
        QPushButton,
        QLabel,
        QFrame,
    )
    from PyQt6.QtCore import pyqtSignal, Qt
    from anylabeling.views.platform.navigation_bar import PipelineStep
    from anylabeling.views.platform.style import (
        FONT_FAMILY,
        FONT_SIZE_BODY,
        FONT_SIZE_CAPTION,
        FONT_SIZE_HERO,
    )
    from anylabeling.views.labeling.utils.theme import get_theme

    class DataWorkspace(QWidget):
        """Data Workspace page — simplified to data overview with navigation.

        In Phase 2, tile/split/augment config moved to PreprocessWorkspace.
        DataWorkspace now shows asset statistics, class distribution, and
        a button to navigate to the Preprocess step.

        Phase 3: Added import button and empty-state CTA for new projects.
        """

        import_requested = pyqtSignal()
        navigate_to_step = pyqtSignal(PipelineStep)

        def __init__(self, parent=None):
            super().__init__(parent)

            t = get_theme()
            label_font = (
                f"font-family: {FONT_FAMILY};"
                f"font-size: {FONT_SIZE_BODY}px;"
                f"color: {t['text']};"
            )

            self._asset_list = QListWidget()

            self._stats_label = QLabel(tr("资源：0", "Assets: 0"))
            self._stats_label.setStyleSheet(label_font)

            self._class_dist_label = QLabel(
                tr("类别分布：无数据", "Class distribution: N/A")
            )
            self._class_dist_label.setStyleSheet(label_font)
            self._class_dist_label.setWordWrap(True)

            self._coverage_label = QLabel(
                tr("覆盖率：无数据", "Coverage: N/A")
            )
            self._coverage_label.setStyleSheet(label_font)

            self._goto_preprocess_btn = QPushButton(
                tr("前往预处理 →", "Go to Preprocess →")
            )
            self._goto_preprocess_btn.setToolTip(
                tr(
                    "配置切片、切分和数据增强参数",
                    "Configure tile, split, and augmentation parameters",
                )
            )
            self._goto_preprocess_btn.clicked.connect(
                lambda: self.navigate_to_step.emit(PipelineStep.PREPROCESS)
            )

            # --- Non-empty state: import button + asset list/stats ---
            # Import button row (top, right-aligned, shown when assets exist)
            self._import_more_btn = QPushButton(
                tr("📥 导入更多", "📥 Import More")
            )
            self._import_more_btn.setObjectName("ImportPrimaryBtn")
            self._import_more_btn.setMinimumSize(120, 32)
            self._import_more_btn.setStyleSheet(
                f"QPushButton#ImportPrimaryBtn {{"
                f"min-width: 120px; min-height: 32px;"
                f"font-size: {FONT_SIZE_BODY}px; font-weight: bold;"
                f"font-family: {FONT_FAMILY};"
                f"background-color: {t['primary']};"
                f"color: {t.get('selection_text', '#ffffff')};"
                f"border: none; border-radius: 6px; padding: 6px 16px;"
                f"}}"
                f"QPushButton#ImportPrimaryBtn:hover {{"
                f"background-color: {t['primary_hover']};"
                f"}}"
                f"QPushButton#ImportPrimaryBtn:pressed {{"
                f"background-color: {t['primary_pressed']};"
                f"}}"
                f"QPushButton#ImportPrimaryBtn:disabled {{"
                f"background-color: {t['border']};"
                f"color: {t['text_secondary']};"
                f"}}"
            )
            self._import_more_btn.clicked.connect(
                self.import_requested.emit
            )

            import_btn_row = QHBoxLayout()
            import_btn_row.addStretch()
            import_btn_row.addWidget(self._import_more_btn)

            # Separator
            separator = QFrame()
            separator.setFrameShape(QFrame.Shape.HLine)
            separator.setFixedHeight(1)
            separator.setStyleSheet(
                f"background-color: {t['border']}; border: none;"
            )

            # --- Empty state: centered CTA ---
            self._empty_widget = QWidget()
            self._empty_widget.setObjectName("emptyState")
            empty_layout = QVBoxLayout()
            empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            # Top spacer (48px equivalent)
            empty_layout.addStretch(1)

            # Hero text
            self._empty_title = QLabel(
                tr("🎉 开始你的第一个标注项目", "🎉 Start Your First Labeling Project")
            )
            self._empty_title.setStyleSheet(
                f"font-family: {FONT_FAMILY};"
                f"font-size: {FONT_SIZE_HERO}px;"
                f"font-weight: bold;"
                f"color: {t['text']};"
            )
            self._empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_layout.addWidget(self._empty_title)

            # Spacing 16px
            spacer_16 = QWidget()
            spacer_16.setFixedHeight(16)
            empty_layout.addWidget(spacer_16)

            # Import CTA button
            self._empty_import_btn = QPushButton(
                tr("📥 导入图片", "📥 Import Images")
            )
            self._empty_import_btn.setObjectName("ImportPrimaryBtn")
            self._empty_import_btn.setMinimumSize(160, 36)
            self._empty_import_btn.setMaximumSize(200, 36)
            self._empty_import_btn.setStyleSheet(
                f"QPushButton#ImportPrimaryBtn {{"
                f"min-width: 160px; min-height: 36px;"
                f"font-size: {FONT_SIZE_BODY}px; font-weight: bold;"
                f"font-family: {FONT_FAMILY};"
                f"background-color: {t['primary']};"
                f"color: {t.get('selection_text', '#ffffff')};"
                f"border: none; border-radius: 6px; padding: 8px 24px;"
                f"}}"
                f"QPushButton#ImportPrimaryBtn:hover {{"
                f"background-color: {t['primary_hover']};"
                f"}}"
                f"QPushButton#ImportPrimaryBtn:pressed {{"
                f"background-color: {t['primary_pressed']};"
                f"}}"
                f"QPushButton#ImportPrimaryBtn:disabled {{"
                f"background-color: {t['border']};"
                f"color: {t['text_secondary']};"
                f"}}"
            )
            self._empty_import_btn.clicked.connect(
                self.import_requested.emit
            )
            btn_centered = QHBoxLayout()
            btn_centered.setAlignment(Qt.AlignmentFlag.AlignCenter)
            btn_centered.addWidget(self._empty_import_btn)
            empty_layout.addLayout(btn_centered)

            # Spacing 12px
            spacer_12 = QWidget()
            spacer_12.setFixedHeight(12)
            empty_layout.addWidget(spacer_12)

            # Supported formats hint
            self._empty_hint = QLabel(
                tr(
                    "支持格式: JPG, PNG, TIFF, BMP, WebP\n"
                    "支持标注伴随导入: YOLO, COCO, VOC, X-AnyLabeling",
                    "Supported formats: JPG, PNG, TIFF, BMP, WebP\n"
                    "Supports annotation import: YOLO, COCO, VOC, X-AnyLabeling",
                )
            )
            self._empty_hint.setStyleSheet(
                f"font-family: {FONT_FAMILY};"
                f"font-size: {FONT_SIZE_CAPTION}px;"
                f"color: {t['text_secondary']};"
            )
            self._empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_layout.addWidget(self._empty_hint)

            # Bottom spacer (48px equivalent)
            empty_layout.addStretch(1)

            self._empty_widget.setLayout(empty_layout)
            self._empty_widget.setStyleSheet(
                f"QWidget#emptyState {{"
                f"background-color: {t['background_secondary']};"
                f"border: 2px dashed {t['border']};"
                f"border-radius: 12px;"
                f"}}"
            )

            # --- Asset content (left-right layout, shown when has assets) ---
            self._content_widget = QWidget()
            content_main = QVBoxLayout()
            content_main.setContentsMargins(0, 0, 0, 0)
            content_main.setSpacing(8)
            content_main.addLayout(import_btn_row)
            content_main.addWidget(separator)

            left = QVBoxLayout()
            left.addWidget(QLabel(tr("资源列表", "Assets")))
            left.addWidget(self._asset_list)

            right = QVBoxLayout()
            right.addWidget(self._stats_label)
            right.addWidget(self._class_dist_label)
            right.addWidget(self._coverage_label)
            right.addStretch()
            right.addWidget(self._goto_preprocess_btn)

            main_row = QHBoxLayout()
            main_row.addLayout(left, 2)
            main_row.addLayout(right, 1)
            content_main.addLayout(main_row)

            self._content_widget.setLayout(content_main)

            # --- Root layout: stacks empty and content ---
            root = QVBoxLayout()
            root.setContentsMargins(16, 12, 16, 12)
            root.setSpacing(0)
            root.addWidget(self._empty_widget)
            root.addWidget(self._content_widget)
            self.setLayout(root)

            # Start in empty state
            self._show_empty_state()

        # ------------------------------------------------------------------
        # Public API
        # ------------------------------------------------------------------

        def set_assets(self, asset_paths: list):
            """Populate the asset list with file paths."""
            self._asset_list.clear()
            for p in asset_paths:
                self._asset_list.addItem(Path(p).name)
            self._stats_label.setText(
                tr(
                    f"资源：{len(asset_paths)}",
                    f"Assets: {len(asset_paths)}",
                )
            )
            if asset_paths:
                self._show_non_empty_state()
            else:
                self._show_empty_state()

        def set_class_distribution(self, dist: dict[str, int]):
            """Set class distribution display.

            Args:
                dist: Mapping of class_name -> count.
            """
            if not dist:
                self._class_dist_label.setText(
                    tr(
                        "类别分布：无数据",
                        "Class distribution: N/A",
                    )
                )
                return

            lines = [tr("类别分布：", "Class distribution:")]
            for cls_name, count in dist.items():
                lines.append(f"  {cls_name}: {count}")
            self._class_dist_label.setText("\n".join(lines))

        def set_coverage(self, annotated: int, total: int):
            """Set annotation coverage display."""
            if total == 0:
                self._coverage_label.setText(
                    tr("覆盖率：无数据", "Coverage: N/A")
                )
                return
            ratio = annotated / total
            self._coverage_label.setText(
                tr(
                    f"覆盖率：{_format_coverage(ratio)} ({annotated}/{total})",
                    f"Coverage: {_format_coverage(ratio)} ({annotated}/{total})",
                )
            )

        def set_import_enabled(self, enabled: bool) -> None:
            """Enable or disable the import button."""
            self._empty_import_btn.setEnabled(enabled)
            self._import_more_btn.setEnabled(enabled)

        # ------------------------------------------------------------------
        # Internal
        # ------------------------------------------------------------------

        def _show_empty_state(self) -> None:
            """Show the empty-state CTA, hide the content widget."""
            self._empty_widget.setVisible(True)
            self._content_widget.setVisible(False)

        def _show_non_empty_state(self) -> None:
            """Show the content widget with asset list, hide empty state."""
            self._empty_widget.setVisible(False)
            self._content_widget.setVisible(True)

except ImportError:
    DataWorkspace = None  # type: ignore
