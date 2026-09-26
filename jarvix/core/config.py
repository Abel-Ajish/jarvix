"""Settings management for jarvix.

Uses per-subsystem YAML files merged at load time so parallel agents can
own their settings files without conflicts.
"""

from __future__ import annotations

import copy
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from jarvix.core.logger import get_logger

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_APP_DATA = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming"))
_CONFIG_DIR = _APP_DATA / "jarvix" / "settings"
_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# Each subsystem owns its own file under settings/
_SUBSYSTEM_FILES = [
    "core.yaml",
    "voice.yaml",
    "web.yaml",
    "plugins.yaml",
    "ai.yaml",
]

_LOG = get_logger("jarvix.config")


class Settings:
    """Merged settings from multiple YAML files."""

    def __init__(self) -> None:
        self._data: Dict[str, Any] = {}
        self._file_times: Dict[str, float] = {}
        self.reload()

    def reload(self) -> None:
        """Reload all subsystem YAML files, merging them."""
        self._data = {}
        self._file_times = {}
        for fname in _SUBSYSTEM_FILES:
            path = _CONFIG_DIR / fname
            if path.exists():
                try:
                    with path.open("r", encoding="utf-8") as f:
                        self._data.update(yaml.safe_load(f) or {})
                    self._file_times[fname] = path.stat().st_mtime
                except Exception as e:
                    _LOG.warning("Failed to load %s: %s", fname, e)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting by dotted key (e.g. 'voice.mic_enabled')."""
        parts = key.split(".")
        node = self._data
        for part in parts:
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, key: str, value: Any) -> None:
        """Set a setting by dotted key and persist to its subsystem file."""
        parts = key.split(".")
        node = self._data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

        # Determine which subsystem file owns this key and write there.
        fname = f"{parts[0]}.yaml"
        path = _CONFIG_DIR / fname
        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(self._data, f, sort_keys=True)

    def all(self) -> Dict[str, Any]:
        """Return a deep copy of all settings."""
        return copy.deepcopy(self._data)


# Global singleton
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings