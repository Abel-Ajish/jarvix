"""Plugin loader — imports plugin modules and calls register().

Uses importlib with isolated module namespace to load plugins safely.
Catches and reports load failures without crashing the app.
"""

from __future__ import annotations

import importlib.util
import sys
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from jarvix.core.events import EventBus, ErrorRaised
from jarvix.core.logger import get_logger
from jarvix.core.tool_registry import ToolRegistry
from jarvix.plugins.registry import PluginManifest, PluginState, get_plugin_registry, load_manifest

_LOG = get_logger("jarvix.plugins.loader")


class PluginLoadError(Exception):
    """Raised when a plugin fails to load."""

    def __init__(self, message: str, plugin_name: str, original_error: Exception = None):
        super().__init__(message)
        self.plugin_name = plugin_name
        self.original_error = original_error


def load_plugin_module(plugin_dir: Path, plugin_name: str) -> Optional[object]:
    """Load the plugin's main.py module in an isolated namespace.

    Returns the module object on success, None on failure.
    """
    main_path = plugin_dir / "main.py"
    if not main_path.exists():
        raise PluginLoadError(f"No main.py found in {plugin_dir}", plugin_name)

    module_name = f"jarvix.plugins.{plugin_name}"

    # Create a new module spec
    spec = importlib.util.spec_from_file_location(module_name, main_path)
    if spec is None:
        raise PluginLoadError(f"Failed to create module spec for {main_path}", plugin_name)

    # Create the module
    module = importlib.util.module_from_spec(spec)

    # Insert into sys.modules BEFORE execution (for relative imports)
    sys.modules[module_name] = module

    try:
        # Execute the module
        if spec.loader is None:
            raise PluginLoadError(f"No loader for {main_path}", plugin_name)
        spec.loader.exec_module(module)
    except Exception as e:
        # Remove from sys.modules on failure
        sys.modules.pop(module_name, None)
        raise PluginLoadError(f"Plugin execution failed: {e}", plugin_name, e)

    return module


def validate_plugin_exports(module: object, manifest: PluginManifest) -> list[str]:
    """Validate that the plugin module has required exports.

    Returns list of errors (empty if valid).
    """
    errors = []

    if not hasattr(module, "register"):
        errors.append("Plugin must export a 'register(tool_registry)' function")
    elif not callable(module.register):
        errors.append("'register' must be callable")

    if not hasattr(module, "get_settings"):
        errors.append("Plugin must export a 'get_settings()' function")
    elif not callable(module.get_settings):
        errors.append("'get_settings' must be callable")

    if not hasattr(module, "set_settings"):
        errors.append("Plugin must export a 'set_settings(dict)' function")
    elif not callable(module.set_settings):
        errors.append("'set_settings' must be callable")

    # Check that declared tools are actually registered (done after registration)
    return errors


def load_plugin(plugin_name: str, tool_registry: ToolRegistry) -> PluginState:
    """Load a single plugin by name.

    Discovers the plugin directory, loads its manifest, imports main.py,
    calls register(), and returns the PluginState.

    Raises PluginLoadError on any failure.
    """
    registry = get_plugin_registry()
    state = registry.get(plugin_name)
    if state is None:
        raise PluginLoadError(f"Plugin '{plugin_name}' not in registry", plugin_name)

    plugin_dir = Path(state.path)
    if not plugin_dir.exists():
        raise PluginLoadError(f"Plugin directory not found: {plugin_dir}", plugin_name)

    # Load manifest
    manifest = load_manifest(plugin_dir)
    if manifest is None:
        raise PluginLoadError("Failed to load manifest", plugin_name)

    state.manifest = manifest

    # Load the module
    module = load_plugin_module(plugin_dir, plugin_name)
    if module is None:
        raise PluginLoadError("Failed to load module", plugin_name)

    # Validate exports
    errors = validate_plugin_exports(module, manifest)
    if errors:
        raise PluginLoadError(f"Invalid plugin exports: {errors}", plugin_name)

    # Call register()
    try:
        module.register(tool_registry)
    except Exception as e:
        _LOG.exception("Plugin '%s' register() raised exception", plugin_name)
        raise PluginLoadError(f"register() failed: {e}", plugin_name, e)

    state.loaded = True
    state.load_error = ""
    _LOG.info("Loaded plugin: %s v%s", plugin_name, manifest.version)
    return state


def unload_plugin(plugin_name: str, tool_registry: ToolRegistry) -> bool:
    """Unload a plugin by unregistering its tools.

    Returns True if the plugin was loaded and unregistered.
    """
    registry = get_plugin_registry()
    state = registry.get(plugin_name)
    if state is None:
        return False

    if not state.loaded:
        return True  # Wasn't loaded, nothing to do

    # Unregister tools declared in manifest
    for tool_name in state.manifest.tools:
        try:
            tool_registry.unregister(tool_name)
            _LOG.debug("Unregistered tool '%s' from plugin '%s'", tool_name, plugin_name)
        except Exception as e:
            _LOG.warning("Failed to unregister tool '%s': %s", tool_name, e)

    state.loaded = False
    _LOG.info("Unloaded plugin: %s", plugin_name)
    return True


def reload_plugin(plugin_name: str, tool_registry: ToolRegistry) -> PluginState:
    """Reload a plugin (unload then load)."""
    unload_plugin(plugin_name, tool_registry)
    return load_plugin(plugin_name, tool_registry)