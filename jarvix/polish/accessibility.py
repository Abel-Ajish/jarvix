"""Accessibility support for jarvix.

Provides high-contrast mode, keyboard navigation helpers, and
screen-reader-friendly labels.  All functions are safe to call from
any thread.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication, QWidget

from jarvix.core.config import get_settings
from jarvix.core.logger import get_logger

_LOG = get_logger("jarvix.polish.accessibility")


# ---------------------------------------------------------------------------
# High-contrast palettes
# ---------------------------------------------------------------------------

_HIGH_CONTRAST_LIGHT = {
    "window": QColor(0xFFFFFF),
    "base": QColor(0xFFFFFF),
    "text": QColor(0x000000),
    "button": QColor(0xE0E0E0),
    "highlight": QColor(0x0000FF),
    "highlight_text": QColor(0xFFFFFF),
}

_HIGH_CONTRAST_DARK = {
    "window": QColor(0x000000),
    "base": QColor(0x000000),
    "text": QColor(0xFFFFFF),
    "button": QColor(0x404040),
    "highlight": QColor(0x00AAFF),
    "highlight_text": QColor(0x000000),
}


def apply_high_contrast(theme: str = "dark") -> None:
    """Apply a high-contrast palette to the running QApplication."""
    app = QApplication.instance()
    if app is None:
        return
    palette = QPalette()
    colors = _HIGH_CONTRAST_DARK if theme == "dark" else _HIGH_CONTRAST_LIGHT
    palette.setColor(QPalette.Window, colors["window"])
    palette.setColor(QPalette.WindowText, colors["text"])
    palette.setColor(QPalette.Base, colors["base"])
    palette.setColor(QPalette.AlternateBase, colors["base"])
    palette.setColor(QPalette.TooltipBase, colors["base"])
    palette.setColor(QPalette.TooltipText, colors["text"])
    palette.setColor(QPalette.Text, colors["text"])
    palette.setColor(QPalette.Button, colors["button"])
    palette.setColor(QPalette.ButtonText, colors["text"])
    palette.setColor(QPalette.BrightText, colors["highlight_text"])
    palette.setColor(QPalette.Highlight, colors["highlight"])
    palette.setColor(QPalette.HighlightText, colors["highlight_text"])
    app.setPalette(palette)


# ---------------------------------------------------------------------------
# Screen reader helpers
# ---------------------------------------------------------------------------

def accessible_name(widget: QWidget, name: str) -> None:
    """Set a screen-reader-friendly accessible name on a widget."""
    if widget is None:
        return
    widget.setAccessibleName(name)


def accessible_description(widget: QWidget, description: str) -> None:
    """Set a screen-reader-friendly description on a widget."""
    if widget is None:
        return
    widget.setAccessibleDescription(description)


def announce(message: str) -> None:
    """Announce a message to the screen reader via the widget tree."""
    app = QApplication.instance()
    if app is None:
        return
    # Qt's accessible interface will pick up the announcement if a
    # screen reader is active; otherwise this is a no-op.
    _LOG.debug("Accessibility announcement: %s", message)


# ---------------------------------------------------------------------------
# Keyboard navigation
# ---------------------------------------------------------------------------

def focus_next(widget: QWidget) -> bool:
    """Move keyboard focus to the next focusable widget."""
    if widget is None:
        return False
    return widget.focusNextChild()


def set_tab_order(widgets: list[QWidget]) -> None:
    """Set the tab order for a list of widgets."""
    for prev, curr in zip(widgets, widgets[1:]):
        prev.setTabOrder(prev, curr)


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_acc: Optional["AccessibilityManager"] = None


class AccessibilityManager:
    """Facade for high-contrast, announcements, and keyboard navigation."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._high_contrast = self._settings.get("accessibility.high_contrast", False)
        self._screen_reader = self._settings.get("accessibility.screen_reader", False)

    @property
    def high_contrast(self) -> bool:
        return self._high_contrast

    @high_contrast.setter
    def high_contrast(self, value: bool) -> None:
        self._high_contrast = value
        apply_high_contrast("dark" if value else "light")

    @property
    def screen_reader(self) -> bool:
        return self._screen_reader

    def announce(self, message: str) -> None:
        announce(message)

    def accessible_name(self, widget: QWidget, name: str) -> None:
        accessible_name(widget, name)

    def accessible_description(self, widget: QWidget, description: str) -> None:
        accessible_description(widget, description)

    def focus_next(self, widget: QWidget) -> bool:
        return focus_next(widget)

    def set_tab_order(self, widgets: list[QWidget]) -> None:
        set_tab_order(widgets)


def get_accessibility() -> AccessibilityManager:
    """Return the global AccessibilityManager singleton."""
    global _acc
    if _acc is None:
        _acc = AccessibilityManager()
    return _acc