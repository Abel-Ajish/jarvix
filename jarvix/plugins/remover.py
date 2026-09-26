"""Plugin remover — uninstall plugins completely.

Removes plugin from registry, unloads tools, deletes files, and cleans secrets.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict

from jarvix.core.logger import get_logger
from jarvix.core.secret_store import get_secret_store
from jarvix.plugins.manager import PluginManager

_LOG = get_logger("jarvix.plugins.remover")


def uninstall_plugin(name: str, manager: PluginManager) -> Dict[str, Any]:
    """Uninstall a plugin completely.

    Returns dict with: success, plugin_name, error
    """
    state = manager.get_plugin(name)
    if state is None:
        return {"success": False, "error": f"Plugin '{name}' not found"}

    try:
        # The manager's uninstall handles unloading, file deletion, secret cleanup
        success = manager.uninstall(name)
        if success:
            return {"success": True, "plugin_name": name}
        return {"success": False, "error": "Uninstall returned False"}
    except Exception as e:
        _LOG.exception("Uninstall failed for '%s'", name)
        return {"success": False, "error": str(e)}


def uninstall_all(manager: PluginManager) -> Dict[str, Any]:
    """Uninstall all plugins. Returns summary."""
    results = {"success": [], "failed": []}
    for state in manager.list_installed():
        result = uninstall_plugin(state.name, manager)
        if result["success"]:
            results["success"].append(state.name)
        else:
            results["failed"].append({"name": state.name, "error": result.get("error", "Unknown error")})
    return results


def clean_orphaned_plugins(manager: PluginManager) -> Dict[str, Any]:
    """Clean up plugin directories that are not in the registry.

    Returns dict with: removed, errors
    """
    import os
    app_data = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming"))
    plugins_dir = app_data / "jarvix" / "plugins"

    if not plugins_dir.exists():
        return {"removed": [], "errors": []}

    registered_paths = {Path(s.path).resolve() for s in manager.list_installed()}

    removed = []
    errors = []

    for item in plugins_dir.iterdir():
        if not item.is_dir():
            continue
        if item.resolve() not in registered_paths:
            try:
                shutil.rmtree(item)
                removed.append(str(item))
                _LOG.info("Removed orphaned plugin directory: %s", item)
            except Exception as e:
                errors.append({"path": str(item), "error": str(e)})

    return {"removed": removed, "errors": errors}