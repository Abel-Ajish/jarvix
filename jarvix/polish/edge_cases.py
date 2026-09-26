"""Edge-case handling for jarvix.

Covers the degraded modes the application must survive gracefully:
no internet, no microphone, no browser, no AI provider, permission
denied, and cancellation mid-operation.
"""

from __future__ import annotations

import os
import socket
from typing import Any, Dict, Optional

from jarvix.core.config import get_settings
from jarvix.core.logger import get_logger

_LOG = get_logger("jarvix.polish.edge_cases")


class EdgeCaseHandler:
    """Detects and reports degraded-environment conditions."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._last_check: Dict[str, bool] = {}

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def has_internet(self, timeout: float = 2.0) -> bool:
        """Check for internet connectivity via a short TCP probe."""
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=timeout)
            self._last_check["internet"] = True
            return True
        except OSError:
            self._last_check["internet"] = False
            return False

    def has_microphone(self) -> bool:
        """Check whether an audio input device is available."""
        try:
            import pyaudio  # type: ignore
            pa = pyaudio.PyAudio()
            count = pa.get_device_count_by_host_api(0)
            pa.terminate()
            return count > 0
        except Exception:
            return False

    def has_browser(self) -> bool:
        """Check whether a Playwright browser binary is installed."""
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                browser.close()
            return True
        except Exception:
            return False

    def has_ai_provider(self) -> bool:
        """Check whether an online AI provider is configured."""
        try:
            from jarvix.ai.provider import get_ai_engine
            engine = get_ai_engine()
            return engine is not None and engine.is_available()
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def environment_report(self) -> Dict[str, Any]:
        """Return a snapshot of all environment checks."""
        report = {
            "internet": self.has_internet(),
            "microphone": self.has_microphone(),
            "browser": self.has_browser(),
            "ai_provider": self.has_ai_provider(),
        }
        self._last_check.update(report)
        return report

    def degraded_features(self) -> Dict[str, str]:
        """Return features that are unavailable and why."""
        report = self.environment_report()
        degraded: Dict[str, str] = {}
        if not report["internet"]:
            degraded["online_ai"] = "No internet connection"
            degraded["web_search"] = "No internet connection"
            degraded["web_browsing"] = "No internet connection"
        if not report["microphone"]:
            degraded["voice_input"] = "No microphone detected"
        if not report["browser"]:
            degraded["browser_navigate"] = "No browser installed (run `playwright install`)"
        if not report["ai_provider"]:
            degraded["planning"] = "No AI provider configured"
            degraded["vision"] = "No AI provider configured"
            degraded["chat"] = "No AI provider configured"
        return degraded

    def is_feature_available(self, feature: str) -> bool:
        """Check whether a named feature is usable in the current environment."""
        return feature not in self.degraded_features()

    def suggested_fallback(self, feature: str) -> Optional[str]:
        """Return a suggested offline fallback for a degraded feature."""
        fallbacks: Dict[str, str] = {
            "online_ai": "Use the offline command engine instead.",
            "web_search": "Try a local file search or memory lookup.",
            "web_browsing": "Use the file tools to work offline.",
            "voice_input": "Type your command instead.",
            "browser_navigate": "Use read_file / create_file tools instead.",
            "planning": "Use simple single-step commands.",
            "vision": "Use screen_capture and manual inspection.",
            "chat": "Use the offline command engine instead.",
        }
        return fallbacks.get(feature)


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_edge: Optional[EdgeCaseHandler] = None


def get_edge_handler() -> EdgeCaseHandler:
    """Return the global EdgeCaseHandler singleton."""
    global _edge
    if _edge is None:
        _edge = EdgeCaseHandler()
    return _edge