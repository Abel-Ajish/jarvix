"""GUI extension registries.

Later phases register panels and settings tabs here.  The main window
builds itself dynamically from these registries — no agent edits
main_window.py after Phase 1.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from PySide6.QtWidgets import QWidget


class Panel(ABC):
    """A panel shown in the main tab bar (Home, Chat, Memory, Tasks, etc.)."""

    name: str
    icon: str = ""

    @abstractmethod
    def widget(self) -> QWidget:
        """Return the panel's root widget."""
        ...

    def on_show(self) -> None:
        """Called when the panel becomes visible."""
        pass

    def on_hide(self) -> None:
        """Called when the panel is hidden."""
        pass


class PanelRegistry:
    """Registry for main window panels."""

    def __init__(self) -> None:
        self._panels: List[Panel] = []

    def register(self, panel: Panel) -> None:
        self._panels.append(panel)

    def panels(self) -> List[Panel]:
        return list(self._panels)


class SettingsTab(ABC):
    """A tab in the settings dialog."""

    group: str  # e.g. "core", "voice", "web", "ai", "plugins"
    title: str

    @abstractmethod
    def widget(self) -> QWidget:
        """Return the tab's root widget."""
        ...


class SettingsTabRegistry:
    """Registry for settings dialog tabs."""

    def __init__(self) -> None:
        self._tabs: Dict[str, List[SettingsTab]] = {}

    def register(self, tab: SettingsTab) -> None:
        self._tabs.setdefault(tab.group, []).append(tab)

    def tabs_for_group(self, group: str) -> List[SettingsTab]:
        return self._tabs.get(group, [])

    def all_groups(self) -> List[str]:
        return list(self._tabs.keys())


# Global singletons
_panel_registry: Optional[PanelRegistry] = None
_settings_tab_registry: Optional[SettingsTabRegistry] = None


def get_panel_registry() -> PanelRegistry:
    global _panel_registry
    if _panel_registry is None:
        _panel_registry = PanelRegistry()
    return _panel_registry


def get_settings_tab_registry() -> SettingsTabRegistry:
    global _settings_tab_registry
    if _settings_tab_registry is None:
        _settings_tab_registry = SettingsTabRegistry()
    return _settings_tab_registry