"""Platform UI style helpers — theme-aware QSS generation.

All platform views MUST use these helpers instead of hardcoding color values.
This ensures dark/light mode support and visual consistency across the pipeline.

Usage::

    from anylabeling.views.platform.style import (
        get_primary_button_style,
        get_secondary_button_style,
        get_input_style,
        get_panel_style,
        get_state_color,
    )
    btn.setStyleSheet(get_primary_button_style())
"""

from __future__ import annotations

from anylabeling.views.labeling.utils.theme import get_mode, get_theme

# ---------------------------------------------------------------------------
# Shell layout constants (px)
# ---------------------------------------------------------------------------

APPBAR_HEIGHT = 48
PRIMARY_NAV_WIDTH = 216
PRIMARY_NAV_MIN_WIDTH = 56
PAGE_HEADER_HEIGHT = 56
PAGE_HEADER_MIN_HEIGHT = 48
PAGE_HEADER_MAX_HEIGHT = 64
STATUS_BAR_HEIGHT = 24
TASK_DRAWER_WIDTH = 480
TASK_DRAWER_MIN_WIDTH = 360
TASK_DRAWER_MAX_WIDTH = 520
MIN_WINDOW_WIDTH = 1920
MIN_WINDOW_HEIGHT = 1080
RECOMMENDED_WIDTH = 1920
RECOMMENDED_HEIGHT = 1080
# Responsive breakpoints
BREAKPOINT_NAV_FOLD = 1600


# ---------------------------------------------------------------------------
# Font hierarchy — unified typography scale for the platform
# ---------------------------------------------------------------------------

FONT_FAMILY = '"Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif'
FONT_FAMILY_MONO = '"Cascadia Code", "Consolas", "Courier New", monospace'

FONT_SIZE_HERO = 18       # main page titles
FONT_SIZE_HEADING = 14    # section headers
FONT_SIZE_BODY = 12       # body text, labels
FONT_SIZE_CAPTION = 11    # secondary text, hints
FONT_SIZE_MONO = 11       # log/code output


def _t(key: str) -> str:
    """Look up a theme token by key. Returns the key itself as fallback."""
    return get_theme().get(key, key)


def _is_dark() -> bool:
    return get_mode() == "dark"


# ---------------------------------------------------------------------------
# State colors — semantic, theme-aware
# ---------------------------------------------------------------------------

def get_state_color(state: str) -> str:
    """Return a hex color for a job/training state.

    Args:
        state: One of 'idle', 'queued', 'starting', 'running',
               'completed', 'failed', 'cancelled', 'cancelling', 'unknown'.
    """
    mapping: dict[str, str] = {
        "idle": _t("text_secondary"),
        "queued": _t("text_secondary"),
        "starting": "#faad14",
        "running": _t("primary"),
        "completed": _t("success"),
        "failed": _t("error"),
        "cancelled": _t("error"),
        "cancelling": "#faad14",
        "unknown": _t("text_secondary"),
    }
    return mapping.get(state, _t("text_secondary"))


# ---------------------------------------------------------------------------
# Button styles
# ---------------------------------------------------------------------------

def get_primary_button_style(*, min_width: int = 0,
                              min_height: int = 0) -> str:
    """QSS for a primary (filled) action button."""
    t = get_theme()
    mw = f"min-width: {min_width}px;" if min_width else ""
    mh = f"min-height: {min_height}px;" if min_height else ""
    return f"""
        QPushButton {{
            background-color: {t["primary"]};
            color: {t.get("selection_text", "#ffffff")};
            border: none;
            border-radius: 6px;
            padding: 8px 20px;
            font-weight: 600;
            font-size: {FONT_SIZE_BODY}px;
            font-family: {FONT_FAMILY};
            {mw}
            {mh}
        }}
        QPushButton:hover {{
            background-color: {t["primary_hover"]};
        }}
        QPushButton:pressed {{
            background-color: {t["primary_pressed"]};
        }}
        QPushButton:disabled {{
            background-color: {t["border"]};
            color: {t["text_secondary"]};
        }}
    """


def get_secondary_button_style(*, min_width: int = 0,
                                 min_height: int = 0) -> str:
    """QSS for a secondary (outlined) button."""
    t = get_theme()
    mw = f"min-width: {min_width}px;" if min_width else ""
    mh = f"min-height: {min_height}px;" if min_height else ""
    return f"""
        QPushButton {{
            background-color: {t["background"]};
            color: {t["text"]};
            border: 1px solid {t["border_light"]};
            border-radius: 6px;
            padding: 8px 20px;
            font-size: {FONT_SIZE_BODY}px;
            font-family: {FONT_FAMILY};
            {mw}
            {mh}
        }}
        QPushButton:hover {{
            color: {t["primary"]};
            border-color: {t["primary"]};
        }}
        QPushButton:pressed {{
            color: {t["primary_pressed"]};
            border-color: {t["primary_pressed"]};
        }}
        QPushButton:disabled {{
            color: {t["text_secondary"]};
            border-color: {t["border"]};
        }}
    """


def get_danger_button_style(*, min_width: int = 0,
                              min_height: int = 0) -> str:
    """QSS for a destructive action button (stop, delete)."""
    t = get_theme()
    mw = f"min-width: {min_width}px;" if min_width else ""
    mh = f"min-height: {min_height}px;" if min_height else ""
    return f"""
        QPushButton {{
            background-color: {t["error"]};
            color: #ffffff;
            border: none;
            border-radius: 6px;
            padding: 8px 20px;
            font-weight: 600;
            font-size: {FONT_SIZE_BODY}px;
            font-family: {FONT_FAMILY};
            {mw}
            {mh}
        }}
        QPushButton:hover {{
            background-color: #ff7875;
        }}
        QPushButton:pressed {{
            background-color: #d9363e;
        }}
        QPushButton:disabled {{
            background-color: {t["border"]};
            color: {t["text_secondary"]};
        }}
    """


def get_ghost_button_style() -> str:
    """QSS for an invisible (flat) utility button (e.g. 'Clear Finished')."""
    t = get_theme()
    return f"""
        QPushButton {{
            background: transparent;
            color: {t["text_secondary"]};
            border: none;
            font-size: {FONT_SIZE_CAPTION}px;
            font-family: {FONT_FAMILY};
            padding: 2px 8px;
        }}
        QPushButton:hover {{
            color: {t["text"]};
        }}
    """


def get_outline_toolbar_button_style() -> str:
    """QSS for small bordered toolbar buttons (Add/Remove label)."""
    t = get_theme()
    return f"""
        QPushButton {{
            background-color: {t["background"]};
            color: {t["primary"]};
            border: 1px solid {t["primary"]};
            border-radius: 4px;
            padding: 4px 12px;
            font-size: {FONT_SIZE_CAPTION}px;
            font-family: {FONT_FAMILY};
        }}
        QPushButton:hover {{
            background-color: {t["highlight"]}22;
        }}
    """


# ---------------------------------------------------------------------------
# Input / control styles
# ---------------------------------------------------------------------------

def get_input_style() -> str:
    """QSS for text inputs and spin boxes."""
    t = get_theme()
    return f"""
        QLineEdit, QSpinBox, QDoubleSpinBox {{
            background-color: {t["background_secondary"]};
            color: {t["text"]};
            border: 1px solid {t["border_light"]};
            border-radius: 6px;
            padding: 6px 10px;
            font-size: {FONT_SIZE_BODY}px;
            font-family: {FONT_FAMILY};
            selection-background-color: {t["selection"]};
            selection-color: {t["selection_text"]};
            min-height: 28px;
        }}
        QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover {{
            border-color: {t["primary"]}66;
        }}
        QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
            border: 2px solid {t["primary"]};
            padding: 5px 9px;
        }}
        QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
            background-color: {t["surface"]};
            color: {t["text_secondary"]};
        }}
    """


def get_combo_style() -> str:
    """QSS for combo boxes."""
    t = get_theme()
    return f"""
        QComboBox {{
            background-color: {t["background_secondary"]};
            color: {t["text"]};
            border: 1px solid {t["border_light"]};
            border-radius: 6px;
            padding: 6px 10px;
            font-size: {FONT_SIZE_BODY}px;
            font-family: {FONT_FAMILY};
            min-height: 28px;
        }}
        QComboBox:hover {{
            border-color: {t["primary"]}66;
        }}
        QComboBox:focus {{
            border: 2px solid {t["primary"]};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 24px;
        }}
        QComboBox::down-arrow {{
            image: url(:/images/images/caret-down.svg);
            width: 12px;
            height: 12px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {t["background_secondary"]};
            color: {t["text"]};
            border: 1px solid {t["border"]};
            border-radius: 4px;
            selection-background-color: {t["selection"]};
            selection-color: {t["selection_text"]};
            outline: none;
            padding: 4px;
        }}
        QComboBox QAbstractItemView::item {{
            padding: 6px 10px;
            min-height: 22px;
        }}
        QComboBox QAbstractItemView::item:selected {{
            background-color: {t["selection"]};
            color: {t["selection_text"]};
        }}
    """


# ---------------------------------------------------------------------------
# Container / panel styles
# ---------------------------------------------------------------------------

def get_group_box_style() -> str:
    """QSS for QGroupBox sections."""
    t = get_theme()
    return f"""
        QGroupBox {{
            color: {t["text"]};
            border: 1px solid {t["border"]};
            border-radius: 8px;
            margin-top: 12px;
            padding: 16px 12px 12px 12px;
            font-weight: 600;
            font-size: {FONT_SIZE_BODY}px;
            font-family: {FONT_FAMILY};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 8px;
            color: {t["text"]};
        }}
    """


def get_scroll_area_style() -> str:
    """QSS for scroll areas with subtle border."""
    t = get_theme()
    return f"""
        QScrollArea {{
            border: 1px solid {t["border"]};
            border-radius: 6px;
            background-color: transparent;
        }}
    """


def get_list_widget_style() -> str:
    """QSS for list/table widgets."""
    t = get_theme()
    return f"""
        QListWidget, QTableWidget, QTreeWidget {{
            background-color: {t["background"]};
            color: {t["text"]};
            border: 1px solid {t["border"]};
            border-radius: 6px;
            alternate-background-color: {t["background_secondary"]};
            outline: none;
            font-size: {FONT_SIZE_BODY}px;
            font-family: {FONT_FAMILY};
        }}
        QListWidget::item, QTableWidget::item {{
            padding: 6px 10px;
            border-bottom: 1px solid {t["border"]};
        }}
        QListWidget::item:hover, QTableWidget::item:hover {{
            background-color: {t["surface_hover"]};
        }}
        QListWidget::item:selected, QTableWidget::item:selected {{
            background-color: {t["selection"]};
            color: {t["selection_text"]};
        }}
        QHeaderView::section {{
            background-color: {t["surface"]};
            color: {t["text"]};
            border: none;
            border-bottom: 1px solid {t["border"]};
            border-right: 1px solid {t["border"]};
            padding: 6px 10px;
            font-weight: 600;
            font-size: {FONT_SIZE_CAPTION}px;
            font-family: {FONT_FAMILY};
        }}
    """


def get_log_view_style() -> str:
    """QSS for read-only log / code text areas."""
    t = get_theme()
    if _is_dark():
        bg = "#1a1a2e"
        fg = "#d4d4d4"
    else:
        bg = t["background_secondary"]
        fg = t["text"]
    return f"""
        QTextEdit, QPlainTextEdit {{
            background-color: {bg};
            color: {fg};
            border: 1px solid {t["border"]};
            border-radius: 6px;
            font-family: {FONT_FAMILY_MONO};
            font-size: {FONT_SIZE_MONO}px;
            selection-background-color: {t["selection"]};
            selection-color: {t["selection_text"]};
        }}
    """


# ---------------------------------------------------------------------------
# Label / typography helpers
# ---------------------------------------------------------------------------

def get_hero_label_style() -> str:
    """QSS for main page title labels."""
    t = get_theme()
    return f"""
        font-size: {FONT_SIZE_HERO}px;
        font-weight: 700;
        color: {t["text"]};
        font-family: {FONT_FAMILY};
    """


def get_heading_label_style() -> str:
    """QSS for section heading labels."""
    t = get_theme()
    return f"""
        font-size: {FONT_SIZE_HEADING}px;
        font-weight: 600;
        color: {t["text"]};
        font-family: {FONT_FAMILY};
    """


def get_caption_label_style() -> str:
    """QSS for secondary / caption text."""
    t = get_theme()
    return f"""
        font-size: {FONT_SIZE_CAPTION}px;
        color: {t["text_secondary"]};
        font-family: {FONT_FAMILY};
    """


# ---------------------------------------------------------------------------
# Status banner helpers
# ---------------------------------------------------------------------------

def get_status_badge_style(state: str) -> str:
    """QSS for a small status badge label.

    Args:
        state: Job/training state string.
    """
    color = get_state_color(state)
    return f"""
        font-weight: 700;
        font-size: {FONT_SIZE_BODY}px;
        color: {color};
        font-family: {FONT_FAMILY};
    """


def get_info_banner_style(variant: str = "info") -> str:
    """QSS for an inline message banner.

    Args:
        variant: 'info', 'success', 'warning', or 'error'.
    """
    t = get_theme()
    if variant == "success":
        bg, border_c, fg = "#f6ffed", "#b7eb8f", t["text"]
    elif variant == "warning":
        bg, border_c, fg = "#fffbe6", "#ffe58f", t["text"]
    elif variant == "error":
        bg, border_c, fg = "#fff2f0", "#ffccc7", t["text"]
    else:  # info
        bg = t["surface"]
        border_c = t["border_light"]
        fg = t["text"]

    return f"""
        QLabel {{
            background-color: {bg};
            border: 1px solid {border_c};
            border-radius: 8px;
            padding: 12px 16px;
            font-size: {FONT_SIZE_BODY}px;
            color: {fg};
            font-family: {FONT_FAMILY};
        }}
    """


def get_empty_state_style() -> str:
    """QSS for empty state placeholder widgets."""
    t = get_theme()
    return f"""
        QWidget#emptyState {{
            background-color: {t["background_secondary"]};
            border: 2px dashed {t["border"]};
            border-radius: 12px;
        }}
        QLabel#emptyStateTitle {{
            font-size: {FONT_SIZE_HEADING}px;
            font-weight: 600;
            color: {t["text_secondary"]};
            font-family: {FONT_FAMILY};
        }}
        QLabel#emptyStateHint {{
            font-size: {FONT_SIZE_BODY}px;
            color: {t["text_placeholder"]};
            font-family: {FONT_FAMILY};
        }}
    """
