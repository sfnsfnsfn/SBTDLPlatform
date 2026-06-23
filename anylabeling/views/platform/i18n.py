"""V4 Platform internationalization.

Dictionary-driven, no external tools required.
All platform UI strings go through ``tr()`` which picks zh_CN or en_US.

Usage::

    from anylabeling.views.platform.i18n import tr, set_locale

    label.setText(tr("视觉算法平台", "Vision Algorithm Platform"))
    set_locale("zh_CN")  # switch at runtime

The active locale is persisted in QSettings (platform/language).
On first access it falls back to the system locale.
"""

from __future__ import annotations

from PyQt6 import QtCore

# ---------------------------------------------------------------------------
# Locale state
# ---------------------------------------------------------------------------

_locale: str | None = None

def set_locale(locale: str) -> None:
    """Set the active locale for all platform UI strings."""
    global _locale
    key = str(locale).lower().replace("-", "_")
    _locale = "zh_CN" if key.startswith("zh") else "en_US"


def _get_locale() -> str:
    global _locale
    if _locale is None:
        try:
            settings = QtCore.QSettings("anylabeling", "anylabeling_platform")
            saved = settings.value("platform/language", "")
            if saved:
                set_locale(str(saved))
                return _locale
        except Exception:
            pass
        sys_locale = QtCore.QLocale.system().name()
        set_locale(sys_locale)
    return _locale


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def tr(zh_text: str, en_text: str) -> str:
    """Return the translation for the active locale.

    Args:
        zh_text: Simplified Chinese text (primary).
        en_text: English fallback text.

    Returns:
        The text in the active locale.
    """
    if _get_locale() == "zh_CN":
        return zh_text
    return en_text
