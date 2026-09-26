"""Plugin updater — check for and apply plugin updates.

For local-only mode, this provides a framework. A real implementation
would check a remote index/registry for newer versions.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from jarvix.core.logger import get_logger
from jarvix.plugins.manager import PluginManager
from jarvix.plugins.registry import PluginManifest, load_manifest

_LOG = get_logger("jarvix.plugins.updater")


@dataclass
class UpdateInfo:
    """Information about an available update."""

    plugin_name: str
    current_version: str
    available_version: str
    changelog: str = ""
    download_url: str = ""


class PluginUpdater:
    """Checks for and applies plugin updates."""

    def __init__(self, manager: PluginManager) -> None:
        self._manager = manager

    def check_all(self) -> List[UpdateInfo]:
        """Check all installed plugins for updates.

        Returns list of UpdateInfo for plugins with available updates.
        """
        updates = []
        for state in self._manager.list_installed():
            update = self.check_plugin(state.name)
            if update:
                updates.append(update)
        return updates

    def check_plugin(self, name: str) -> Optional[UpdateInfo]:
        """Check a single plugin for updates.

        For local-only mode, this returns None (no remote index).
        Override in subclass for remote checking.
        """
        state = self._manager.get_plugin(name)
        if not state:
            return None

        # TODO: Implement remote version checking
        # For now, return None - no updates available
        return None

    def apply_update(self, name: str) -> Dict[str, Any]:
        """Apply an update for a plugin.

        For local-only mode, this is not implemented.
        """
        return {"success": False, "error": "Plugin updates not implemented for local-only mode"}


def get_updater(manager: PluginManager) -> PluginUpdater:
    """Get a plugin updater instance."""
    return PluginUpdater(manager)