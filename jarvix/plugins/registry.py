"""Plugin registry — metadata and persistence for plugins.

Each plugin has a manifest (plugin.json) with metadata. The registry
tracks installed plugins and their enabled/disabled state, persisted
in the config store under 'plugins.installed'.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from jarvix.core.config import get_settings
from jarvix.core.logger import get_logger
from jarvix.core.secret_store import get_secret_store

_LOG = get_logger("jarvix.plugins.registry")


@dataclass
class PluginManifest:
    """Plugin metadata from plugin.json manifest file."""

    name: str
    version: str
    description: str
    author: str
    homepage: str = ""
    tools: List[str] = field(default_factory=list)
    settings_schema: Dict[str, Any] = field(default_factory=dict)
    permissions: List[str] = field(default_factory=list)
    min_jarvix_version: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PluginManifest":
        # Handle missing fields with defaults
        return cls(
            name=data.get("name", ""),
            version=data.get("version", "0.0.0"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            homepage=data.get("homepage", ""),
            tools=data.get("tools", []),
            settings_schema=data.get("settings_schema", {}),
            permissions=data.get("permissions", []),
            min_jarvix_version=data.get("min_jarvix_version", ""),
        )

    def validate(self) -> List[str]:
        """Validate the manifest. Returns list of errors (empty if valid)."""
        errors = []
        if not self.name:
            errors.append("name is required")
        if not self.version:
            errors.append("version is required")
        if not self.description:
            errors.append("description is required")
        if not self.author:
            errors.append("author is required")
        return errors


@dataclass
class PluginState:
    """Runtime state for an installed plugin."""

    name: str
    path: str  # Absolute path to plugin directory
    manifest: PluginManifest
    enabled: bool = True
    load_error: str = ""
    loaded: bool = False

    # Backwards compatibility aliases
    ENABLED = True
    DISABLED = False


class PluginRegistry:
    """Registry of installed plugins. Persists enabled/disabled state."""

    def __init__(self, plugins_dir: Optional[Path] = None) -> None:
        self._plugins_dir = plugins_dir
        self._settings = get_settings()
        self._plugins: Dict[str, PluginState] = {}
        self._load_state()

    def _load_state(self) -> None:
        """Load enabled/disabled state from config."""
        installed = self._settings.get("plugins.installed", {})
        for name, data in installed.items():
            if isinstance(data, dict) and "enabled" in data:
                # We'll fill in manifest and path on discovery
                pass

    def _persist_state(self) -> None:
        """Persist enabled/disabled state to config."""
        data = {name: {"enabled": state.enabled} for name, state in self._plugins.items()}
        self._settings.set("plugins.installed", data)

    def register(self, state: PluginState) -> None:
        """Register a plugin state."""
        self._plugins[state.name] = state
        self._persist_state()

    def unregister(self, name: str) -> bool:
        """Unregister a plugin. Returns True if it existed."""
        if name in self._plugins:
            del self._plugins[name]
            self._persist_state()
            return True
        return False

    def get(self, name: str) -> Optional[PluginState]:
        return self._plugins.get(name)

    def list_plugins(self) -> List[PluginState]:
        return list(self._plugins.values())

    def set_enabled(self, name: str, enabled: bool) -> bool:
        """Set enabled state. Returns True if plugin exists."""
        if name in self._plugins:
            self._plugins[name].enabled = enabled
            self._persist_state()
            return True
        return False

    def is_enabled(self, name: str) -> bool:
        state = self._plugins.get(name)
        return state.enabled if state else False

    def get_manifest(self, name: str) -> Optional[PluginManifest]:
        state = self._plugins.get(name)
        return state.manifest if state else None


def load_manifest(plugin_dir: Path) -> Optional[PluginManifest]:
    """Load and validate plugin manifest from plugin.json or manifest.json."""
    manifest_path = plugin_dir / "plugin.json"
    if not manifest_path.exists():
        manifest_path = plugin_dir / "manifest.json"
    if not manifest_path.exists():
        _LOG.warning("No manifest found in %s", plugin_dir)
        return None

    try:
        with manifest_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        manifest = PluginManifest.from_dict(data)
        errors = manifest.validate()
        if errors:
            _LOG.error("Invalid manifest in %s: %s", manifest_path, errors)
            return None
        return manifest
    except json.JSONDecodeError as e:
        _LOG.error("Invalid JSON in %s: %s", manifest_path, e)
        return None
    except Exception as e:
        _LOG.exception("Failed to load manifest from %s", manifest_path)
        return None


# Global singleton
_registry: Optional[PluginRegistry] = None


def get_plugin_registry() -> PluginRegistry:
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
    return _registry