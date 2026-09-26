"""Emergency stop protocol for jarvix.

Uses Win32 RegisterHotKey for a global hotkey that works without admin.
Also listens for voice phrase "jarvix stop" via the event bus.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import threading
import time
from typing import Callable, Optional

from jarvix.core.events import EventBus, EmergencyStopRequested, AICancelRequested
from jarvix.core.logger import get_logger

_LOG = get_logger("jarvix.emergency_stop")

# ---------------------------------------------------------------------------
# Win32 constants
# ---------------------------------------------------------------------------

WM_HOTKEY = 0x0312
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
VK_J = 0x4A

# ---------------------------------------------------------------------------
# EmergencyStop class
# ---------------------------------------------------------------------------


class EmergencyStop:
    """Manages the global emergency stop hotkey and event dispatch."""

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._hotkey_id = 1
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable[[], None]] = None

    def register_hotkey(self, modifiers: int = MOD_CONTROL | MOD_SHIFT, key: int = VK_J) -> bool:
        """Register the global hotkey (default: Ctrl+Shift+J).

        Returns True on success, False if registration failed.
        """
        # Must be called from the thread that runs the message loop
        result = ctypes.windll.user32.RegisterHotKey(
            0,  # hWnd = 0 means thread message queue
            self._hotkey_id,
            modifiers,
            key,
        )
        if not result:
            _LOG.warning("Failed to register global hotkey (may already be in use)")
            return False
        _LOG.info("Registered global hotkey: Ctrl+Shift+J")
        return True

    def start(self) -> None:
        """Start the message pump thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._message_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the message pump and unregister hotkey."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        ctypes.windll.user32.UnregisterHotKey(0, self._hotkey_id)

    def on_trigger(self, callback: Callable[[], None]) -> None:
        """Register a callback to run when emergency stop is triggered."""
        self._callback = callback

    def _message_loop(self) -> None:
        """Windows message loop waiting for WM_HOTKEY."""
        msg = ctypes.wintypes.MSG()
        while self._running:
            if ctypes.windll.user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) > 0:
                if msg.message == WM_HOTKEY and msg.wParam == self._hotkey_id:
                    self._trigger()
                ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
                ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))
            else:
                # GetMessage returned 0 or -1 (WM_QUIT or error)
                time.sleep(0.01)

    def _trigger(self) -> None:
        """Called when hotkey is pressed or voice phrase detected."""
        _LOG.warning("EMERGENCY STOP TRIGGERED")
        self._event_bus.publish(EmergencyStopRequested())
        self._event_bus.publish(AICancelRequested())
        if self._callback:
            try:
                self._callback()
            except Exception:
                _LOG.exception("Emergency stop callback failed")


# ---------------------------------------------------------------------------
# Voice phrase detection (called from voice subsystem)
# ---------------------------------------------------------------------------

def check_voice_emergency(text: str) -> bool:
    """Return True if the transcribed text contains the emergency stop phrase."""
    normalized = text.lower().strip()
    return normalized in ("jarvix stop", "jarvix emergency stop", "emergency stop")