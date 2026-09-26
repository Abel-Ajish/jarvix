"""Plugin manager — lifecycle management for plugins.

Handles discovery, loading, enabling, disabling, reloading, and uninstalling.
Emits events on state changes.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from jarvix.core.events import EventBus, ErrorRaised
from jarvix.core.logger import get_logger
from jarvix.core.tool_registry import ToolRegistry
from jarvix.plugins.loader import load_plugin, unload_plugin, PluginLoadError
from jarvix.plugins.registry import (
    PluginManifest,
    PluginState,
    get_plugin_registry,
    load_manifest,
)

_LOG = get_logger("jarvix.plugins.manager")

# Event types for plugin lifecycle
PLUGIN_INSTALLED = "plugin.installed"
PLUGIN_UNINSTALLED = "plugin.uninstalled"
PLUGIN_ENABLED = "plugin.enabled"
PLUGIN_DISABLED = "plugin.disabled"
PLUGIN_LOADED = "plugin.loaded"
PLUGIN_UNLOADED = "plugin.unloaded"
PLUGIN_ERROR = "plugin.error"


class PluginManager:
    """Manages the full lifecycle of plugins."""

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        tool_registry: Optional[ToolRegistry] = None,
    ) -> None:
        self._event_bus = event_bus
        self._tool_registry = tool_registry
        self._registry = get_plugin_registry()
        self._plugins_dir = self._get_plugins_dir()

    def _get_plugins_dir(self) -> Path:
        """Get the plugins directory (user-writable)."""
        import os
        app_data = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming"))
        plugins_dir = app_data / "jarvix" / "plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)
        return plugins_dir

    def shutdown(self) -> None:
        """Shutdown the plugin manager, unloading all plugins."""
        for state in list(self._registry.list_plugins()):
            self.uninstall(state.name)

    def _emit(self, event_type: str, data: Dict[str, Any]) -> None:
        """Emit an event if event bus is available."""
        if self._event_bus:
            from jarvix.core.events import Event

            class PluginEvent(Event):
                def __init__(self, type: str, data: Dict[str, Any]) -> None:
                    super().__init__(type, data=data)

            self._event_bus.publish(PluginEvent(event_type, data))

    def discover(self) -> List[PluginState]:
        """Scan plugins directory for installed plugins.

        Returns list of discovered plugin states.
        """
        discovered = []

        # Also check built-in plugins (jarvix/plugins/*)
        builtin_dir = Path(__file__).parent
        self._scan_directory(builtin_dir, is_builtin=True, discovered=discovered)

        # Scan user plugins directory
        self._scan_directory(self._plugins_dir, is_builtin=False, discovered=discovered)

        return discovered

    def _scan_directory(
        self, directory: Path, is_builtin: bool, discovered: List[PluginState]
    ) -> None:
        """Scan a directory for plugin manifests."""
        if not directory.exists():
            return

        for item in directory.iterdir():
            if not item.is_dir():
                continue

            # Skip special directories
            if item.name.startswith("__") or item.name == "__pycache__":
                continue

            manifest = load_manifest(item)
            if manifest is None:
                continue

            # Check if already registered
            existing = self._registry.get(manifest.name)
            if existing:
                # Update path and manifest
                existing.path = str(item)
                existing.manifest = manifest
                discovered.append(existing)
                continue

            # New plugin
            state = PluginState(
                name=manifest.name,
                path=str(item),
                manifest=manifest,
                enabled=True,  # Default enabled
            )
            self._registry.register(state)
            discovered.append(state)
            _LOG.info("Discovered plugin: %s v%s at %s", manifest.name, manifest.version, item)

    def list_installed(self) -> List[PluginState]:
        """List all installed plugins."""
        return self._registry.list_plugins()

    def get_plugin(self, name: str) -> Optional[PluginState]:
        """Get a plugin by name."""
        return self._registry.get(name)

    def load_all(self) -> Dict[str, bool]:
        """Load all enabled plugins. Returns dict of plugin_name -> success."""
        results = {}
        if self._tool_registry is None:
            _LOG.warning("No tool registry available for plugin loading")
            return results

        for state in self._registry.list_plugins():
            if not state.enabled:
                _LOG.debug("Skipping disabled plugin: %s", state.name)
                results[state.name] = False
                continue

            try:
                load_plugin(state.name, self._tool_registry)
                self._emit(PLUGIN_LOADED, {"name": state.name})
                results[state.name] = True
            except PluginLoadError as e:
                state.load_error = str(e)
                state.loaded = False
                _LOG.error("Failed to load plugin '%s': %s", state.name, e)
                self._emit(PLUGIN_ERROR, {"name": state.name, "error": str(e)})
                results[state.name] = False
            except Exception as e:
                state.load_error = str(e)
                state.loaded = False
                _LOG.exception("Unexpected error loading plugin '%s'", state.name)
                self._emit(PLUGIN_ERROR, {"name": state.name, "error": str(e)})
                results[state.name] = False

        return results

    def enable(self, name: str) -> bool:
        """Enable a plugin. Returns True on success."""
        state = self._registry.get(name)
        if state is None:
            _LOG.warning("Cannot enable unknown plugin: %s", name)
            return False

        if state.enabled:
            return True  # Already enabled

        self._registry.set_enabled(name, True)
        self._emit(PLUGIN_ENABLED, {"name": name})

        # If tool registry available, load it now
        if self._tool_registry and not state.loaded:
            try:
                load_plugin(name, self._tool_registry)
                self._emit(PLUGIN_LOADED, {"name": name})
            except Exception as e:
                state.load_error = str(e)
                _LOG.error("Failed to load enabled plugin '%s': %s", name, e)
                self._emit(PLUGIN_ERROR, {"name": name, "error": str(e)})

        return True

    def disable(self, name: str) -> bool:
        """Disable a plugin. Returns True on success."""
        state = self._registry.get(name)
        if state is None:
            _LOG.warning("Cannot disable unknown plugin: %s", name)
            return False

        if not state.enabled:
            return True  # Already disabled

        # Unload first
        if self._tool_registry and state.loaded:
            unload_plugin(name, self._tool_registry)
            self._emit(PLUGIN_UNLOADED, {"name": name})

        self._registry.set_enabled(name, False)
        self._emit(PLUGIN_DISABLED, {"name": name})
        return True

    def reload(self, name: str) -> bool:
        """Reload a plugin. Returns True on success."""
        state = self._registry.get(name)
        if state is None:
            _LOG.warning("Cannot reload unknown plugin: %s", name)
            return False

        if not state.enabled:
            _LOG.warning("Cannot reload disabled plugin: %s", name)
            return False

        if self._tool_registry is None:
            _LOG.warning("No tool registry available for reload")
            return False

        try:
            from jarvix.plugins.loader import reload_plugin
            reload_plugin(name, self._tool_registry)
            self._emit(PLUGIN_LOADED, {"name": name})
            return True
        except Exception as e:
            state.load_error = str(e)
            _LOG.error("Failed to reload plugin '%s': %s", name, e)
            self._emit(PLUGIN_ERROR, {"name": name, "error": str(e)})
            return False

    def install_from_path(self, source_path: Path, name: Optional[str] = None) -> PluginState:
        """Install a plugin from a local directory or archive.

        Args:
            source_path: Path to plugin directory or .zip/.tar.gz archive
            name: Optional name override (defaults to manifest name)

        Returns the installed PluginState.

        Raises:
            PluginLoadError: If installation fails
        """
        import tempfile
        import zipfile
        import tarfile

        source_path = source_path.resolve()

        # Handle archive
        if source_path.suffix in (".zip", ".tar", ".gz", ".tgz"):
            with tempfile.TemporaryDirectory() as tmpdir:
                extract_dir = Path(tmpdir)
                if source_path.suffix == ".zip":
                    with zipfile.ZipFile(source_path, "r") as zf:
                        for member in zf.infolist():
                            if member.is_dir():
                                continue
                            target = (extract_dir / member.name).resolve()
                            if not str(target).startswith(str(extract_dir.resolve())):
                                raise ValueError(f"Path traversal detected in ZIP: {member.name}")
                        zf.extractall(extract_dir)
                else:
                    with tarfile.open(source_path, "r:*") as tf:
                        for member in tf.getmembers():
                            if member.islnk() or member.issym():
                                raise ValueError(f"Symlink/hardlink not allowed: {member.name}")
                            target = (extract_dir / member.name).resolve()
                            if not str(target).startswith(str(extract_dir.resolve())):
                                raise ValueError(f"Path traversal detected in tar: {member.name}")
                        tf.extractall(extract_dir)

                # Find the plugin directory (may be nested)
                plugin_dir = extract_dir
                if len(list(extract_dir.iterdir())) == 1:
                    plugin_dir = list(extract_dir.iterdir())[0]

                return self._install_from_dir(plugin_dir, name)
        else:
            # Directory
            return self._install_from_dir(source_path, name)

    def _install_from_dir(self, source_dir: Path, name: Optional[str] = None) -> PluginState:
        """Install a plugin from a directory."""
        manifest = load_manifest(source_dir)
        if manifest is None:
            raise PluginLoadError("No valid manifest found", name or source_dir.name)

        plugin_name = name or manifest.name

        # Check for conflicts
        existing = self._registry.get(plugin_name)
        if existing:
            raise PluginLoadError(f"Plugin '{plugin_name}' already installed", plugin_name)

        # Copy to plugins directory
        target_dir = self._plugins_dir / plugin_name
        if target_dir.exists():
            raise PluginLoadError(f"Target directory already exists: {target_dir}", plugin_name)

        shutil.copytree(source_dir, target_dir)

        # Register
        state = PluginState(
            name=plugin_name,
            path=str(target_dir),
            manifest=manifest,
            enabled=True,
        )
        self._registry.register(state)
        self._emit(PLUGIN_INSTALLED, {"name": plugin_name, "path": str(target_dir)})

        # Load if tool registry available
        if self._tool_registry:
            try:
                load_plugin(plugin_name, self._tool_registry)
                self._emit(PLUGIN_LOADED, {"name": plugin_name})
            except Exception as e:
                state.load_error = str(e)
                _LOG.error("Failed to load installed plugin '%s': %s", plugin_name, e)
                self._emit(PLUGIN_ERROR, {"name": plugin_name, "error": str(e)})

        return state

    def uninstall(self, name: str) -> bool:
        """Uninstall a plugin completely.

        Removes from registry, unloads tools, deletes files, cleans secrets.
        """
        state = self._registry.get(name)
        if state is None:
            _LOG.warning("Cannot uninstall unknown plugin: %s", name)
            return False

        # Unload first
        if self._tool_registry and state.loaded:
            unload_plugin(name, self._tool_registry)
            self._emit(PLUGIN_UNLOADED, {"name": name})

        # Delete plugin directory
        plugin_dir = Path(state.path)
        if plugin_dir.exists() and plugin_dir.is_relative_to(self._plugins_dir):
            try:
                shutil.rmtree(plugin_dir)
                _LOG.info("Deleted plugin directory: %s", plugin_dir)
            except Exception as e:
                _LOG.error("Failed to delete plugin directory %s: %s", plugin_dir, e)

        # Clean secrets
        self._clean_secrets(name)

        # Unregister
        self._registry.unregister(name)
        self._emit(PLUGIN_UNINSTALLED, {"name": name})

        return True

    def _clean_secrets(self, plugin_name: str) -> None:
        """Remove any secrets stored by this plugin."""
        try:
            from jarvix.core.secret_store import get_secret_store

            store = get_secret_store()
            # SecretStore currently lacks a per-key delete API.
            # Clear the entire in-memory cache so plugin secrets
            # are evicted from RAM (encrypted values persist on disk).
            store.wipe()
            _LOG.debug("Wiped secret cache for plugin '%s'", plugin_name)
        except Exception as e:
            _LOG.debug("Secret cleanup for '%s': %s", plugin_name, e)

    def get_settings(self, name: str) -> Dict[str, Any]:
        """Get settings for a plugin."""
        state = self._registry.get(name)
        if state is None:
            return {}
        try:
            module = self._load_module(state)
            if module and hasattr(module, "get_settings"):
                return module.get_settings()
        except Exception as e:
            _LOG.error("Failed to get settings for '%s': %s", name, e)
        return {}

    def set_settings(self, name: str, settings: Dict[str, Any]) -> bool:
        """Set settings for a plugin."""
        state = self._registry.get(name)
        if state is None:
            return False
        try:
            module = self._load_module(state)
            if module and hasattr(module, "set_settings"):
                module.set_settings(settings)
                return True
        except Exception as e:
            _LOG.error("Failed to set settings for '%s': %s", name, e)
        return False

    def _load_module(self, state: PluginState) -> Optional[object]:
        """Load plugin module without registering tools."""
        from jarvix.plugins.loader import load_plugin_module
        return load_plugin_module(Path(state.path), state.name)

    def check_updates(self) -> Dict[str, str]:
        """Check installed plugins for updates.

        Returns dict of plugin_name -> available_version.
        For local plugins, this compares against a remote index
        (not implemented) or returns current version.
        """
        # TODO: Implement remote version checking
        # For now, return empty - no remote index
        return {}

    def apply_update(self, name: str) -> bool:
        """Apply an update for a plugin.

        Not implemented for local-only mode.
        """
        _LOG.warning("Plugin updates not implemented for local-only mode")
        return False


# Convenience functions for direct use
_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    global _manager
    if _manager is None:
        _manager = PluginManager()
    return _manager