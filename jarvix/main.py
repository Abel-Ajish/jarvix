"""Main entry point for jarvix.

Bootstraps the Qt application, creates the event bus, core services,
registers the offline engine and system tools, and shows the main window.
"""

from __future__ import annotations

import sys
from typing import Any

from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import QApplication

from jarvix.core.events import EventBus, OnlineStatusChanged
from jarvix.core.logger import get_logger
from jarvix.core.config import get_settings
from jarvix.core.secret_store import get_secret_store
from jarvix.core.permissions import PermissionManager
from jarvix.core.tool_registry import ToolRegistry
from jarvix.core.execution import ExecContext
from jarvix.core.emergency_stop import EmergencyStop
from jarvix.engine.offline import OfflineCommandEngine
from jarvix.ui.main_window import JarvixWindow
from jarvix.ui.extensions import get_panel_registry, get_settings_tab_registry
from jarvix.tools.system import OpenApplicationTool

# Subsystem tool registrations (imported lazily so a missing optional
# dependency never blocks the app from starting).
def _register_subsystem_tools(tool_registry: ToolRegistry) -> None:
    """Register all subsystem tools with the global ToolRegistry."""
    # Web (Phase 6)
    try:
        from jarvix.web import register_web_tools
        register_web_tools(tool_registry)
    except Exception as e:
        _LOG.warning("Failed to register web tools: %s", e)

    # Plugins (Phase 8)
    try:
        from jarvix.plugins.tools import register_plugin_tools
        register_plugin_tools(tool_registry)
    except Exception as e:
        _LOG.warning("Failed to register plugin tools: %s", e)

    # Vision (Phase 7)
    try:
        from jarvix.vision import register_vision_tools
        register_vision_tools(tool_registry)
    except Exception as e:
        _LOG.warning("Failed to register vision tools: %s", e)

    # Advanced Agent (Phase 9)
    try:
        from jarvix.agent import register_agent_tools
        register_agent_tools(tool_registry)
    except Exception as e:
        _LOG.warning("Failed to register agent tools: %s", e)

_LOG = get_logger("jarvix.main")


def main() -> int:
    """Application entry point."""
    # Initialize Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("jarvix")
    app.setApplicationVersion("0.1.0")
    app.setQuitOnLastWindowClosed(True)

    # Core services
    event_bus = EventBus()
    settings = get_settings()
    secret_store = get_secret_store()
    permission_manager = PermissionManager()
    tool_registry = ToolRegistry(event_bus, permission_manager)

    # Register core tools
    tool_registry.register("open_application", OpenApplicationTool())

    # Register subsystem tools (web, plugins, vision, agent)
    _register_subsystem_tools(tool_registry)

    # Create offline engine (stub for Phase 1)
    offline_engine = OfflineCommandEngine(event_bus, tool_registry)

    # Emergency stop
    emergency_stop = EmergencyStop(event_bus)
    emergency_stop.register_hotkey()  # Ctrl+Shift+J
    emergency_stop.start()

    def on_emergency() -> None:
        # Cancel any ongoing execution by setting cancel event
        # The actual cancel event is per-ExecContext; we broadcast the event
        pass
    emergency_stop.on_trigger(on_emergency)

    # UI registries
    panel_registry = get_panel_registry()
    settings_tab_registry = get_settings_tab_registry()

    # Create main window
    window = JarvixWindow(event_bus, panel_registry, settings_tab_registry)
    window.show()

    # Network status detection (simple ping for Phase 1)
    from PySide6.QtCore import QThread

    class NetworkChecker(QThread):
        def run(self):
            import socket
            try:
                socket.create_connection(("8.8.8.8", 53), timeout=2)
                event_bus.publish(OnlineStatusChanged(True))
            except OSError:
                event_bus.publish(OnlineStatusChanged(False))

    # Initial check (fire and forget in background thread)
    NetworkChecker().start()

    # Periodic check every 30 seconds
    timer = QTimer()
    timer.timeout.connect(lambda: NetworkChecker().start())
    timer.start(30_000)

    _LOG.info("jarvix started")

    # Run event loop
    try:
        return app.exec()
    finally:
        emergency_stop.stop()
        # Cleanup browser if running
        try:
            from jarvix.web.browser import get_browser_manager
            mgr = get_browser_manager()
            if mgr and mgr.is_running:
                import asyncio
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    asyncio.ensure_future(mgr.stop())
                else:
                    loop.run_until_complete(mgr.stop())
        except Exception:
            pass
        _LOG.info("jarvix stopped")


if __name__ == "__main__":
    sys.exit(main())