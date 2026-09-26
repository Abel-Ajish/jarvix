"""Plugins subsystem for jarvix.

Provides plugin discovery, loading, management, and UI.
"""

from __future__ import annotations

from typing import List, Optional

from jarvix.plugins.manager import PluginManager, get_plugin_manager
from jarvix.plugins.registry import PluginManifest, PluginRegistry, PluginState, get_plugin_registry
from jarvix.plugins.loader import load_plugin, unload_plugin, PluginLoadError
from jarvix.plugins.installer import install_from_path, validate_plugin_source
from jarvix.plugins.updater import PluginUpdater, get_updater
from jarvix.plugins.remover import uninstall_plugin, uninstall_all, clean_orphaned_plugins
from jarvix.plugins.ui_panel import PluginsPanel, PluginsPanelWrapper, PluginSettingsTab, register_plugins_ui

__all__ = [
    # Manager
    "PluginManager",
    "get_plugin_manager",
    # Registry
    "PluginManifest",
    "PluginRegistry",
    "PluginState",
    "get_plugin_registry",
    # Loader
    "load_plugin",
    "unload_plugin",
    "PluginLoadError",
    # Installer
    "install_from_path",
    "validate_plugin_source",
    # Updater
    "PluginUpdater",
    "get_updater",
    # Remover
    "uninstall_plugin",
    "uninstall_all",
    "clean_orphaned_plugins",
    # UI
    "PluginsPanel",
    "PluginsPanelWrapper",
    "PluginSettingsTab",
    "register_plugins_ui",
]

# Auto-register UI on import
register_plugins_ui()