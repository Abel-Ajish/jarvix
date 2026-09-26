"""UX improvements for jarvix.

User-facing quality-of-life enhancements: toast notifications, loading
indicators, and friendlier error messages.  All functions are safe to call
from any thread; Qt-bound helpers marshal to the GUI thread.
"""

from __future__ import annotations

import threading
from typing import Callable, Dict, Optional

from PySide6.QtCore import Qt, QTimer, QObject, Signal
from PySide6.QtWidgets import QLabel, QMessageBox, QWidget

from jarvix.core.logger import get_logger

_LOG = get_logger("jarvix.polish.ux")


# ---------------------------------------------------------------------------
# Toast notifications
# ---------------------------------------------------------------------------

class ToastManager(QObject):
    """Non-blocking toast notifications shown at the screen corner."""

    toast_requested = Signal(str, str, int)  # message, level, duration_ms

    LEVELS: Dict[str, str] = {
        "info": "Information",
        "success": "Success",
        "warning": "Warning",
        "error": "Error",
    }

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._queue: list[tuple[str, str, int]] = []
        self._active = False

    def show(self, message: str, level: str = "info", duration_ms: int = 3000) -> None:
        """Queue a toast for display."""
        if level not in self.LEVELS:
            level = "info"
        self._queue.append((message, level, duration_ms))
        self._drain()

    def _drain(self) -> None:
        if self._active or not self._queue:
            return
        self._active = True
        message, level, duration = self._queue.pop(0)
        self.toast_requested.emit(message, level, duration)
        QTimer.singleShot(duration, self._on_toast_done)

    def _on_toast_done(self) -> None:
        self._active = False
        self._drain()


# ---------------------------------------------------------------------------
# Error message formatting
# ---------------------------------------------------------------------------

_ERROR_TEMPLATES: Dict[str, str] = {
    "no_internet": (
        "No internet connection detected. I'll retry when you're back online, "
        "or you can use offline commands in the meantime."
    ),
    "no_microphone": (
        "No microphone detected. Voice input is unavailable. "
        "You can still type commands."
    ),
    "no_browser": (
        "No browser installed. Run `playwright install` in the venv to enable web features."
    ),
    "no_ai_provider": (
        "No AI provider configured. Set up an online AI provider in Settings to enable "
        "planning, vision, and chat features."
    ),
    "permission_denied": (
        "Permission denied. Check the permission settings and try again."
    ),
    "cancelled": (
        "The operation was cancelled."
    ),
    "timeout": (
        "The operation timed out. Try again or use a simpler request."
    ),
}


def friendly_error(error: Exception, *, component: str = "jarvix") -> str:
    """Convert a raw exception into a user-friendly message."""
    msg = str(error).lower()
    if "network" in msg or "connection" in msg or "internet" in msg:
        return _ERROR_TEMPLATES["no_internet"]
    if "microphone" in msg or "audio" in msg or "input device" in msg:
        return _ERROR_TEMPLATES["no_microphone"]
    if "browser" in msg or "playwright" in msg:
        return _ERROR_TEMPLATES["no_browser"]
    if "api" in msg or "provider" in msg or "key" in msg:
        return _ERROR_TEMPLATES["no_ai_provider"]
    if "permission" in msg or "denied" in msg:
        return _ERROR_TEMPLATES["permission_denied"]
    if "cancel" in msg:
        return _ERROR_TEMPLATES["cancelled"]
    if "timeout" in msg or "timed out" in msg:
        return _ERROR_TEMPLATES["timeout"]
    return f"{component}: {error}"


def loading_message(operation: str) -> str:
    """Return a friendly in-progress message for an operation."""
    return f"Working on it — {operation}..."


# ---------------------------------------------------------------------------
# Global singletons
# ---------------------------------------------------------------------------

_ux: Optional[UXImprovements] = None


class UXImprovements:
    """Facade for toast + error formatting."""

    def __init__(self) -> None:
        self._toast = ToastManager()

    def toast(self, message: str, level: str = "info", duration_ms: int = 3000) -> None:
        self._toast.show(message, level, duration_ms)

    def format_error(self, error: Exception, *, component: str = "jarvix") -> str:
        return friendly_error(error, component=component)

    def loading(self, operation: str) -> str:
        return loading_message(operation)


def get_ux() -> UXImprovements:
    """Return the global UXImprovements singleton."""
    global _ux
    if _ux is None:
        _ux = UXImprovements()
    return _ux


def toast(message: str, level: str = "info", duration_ms: int = 3000) -> None:
    """Convenience wrapper."""
    get_ux().toast(message, level, duration_ms)