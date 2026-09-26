"""Plugin management UI panel — PySide6 widget for managing plugins.

Shows installed plugins with enable/disable toggles, install/uninstall buttons.
Registers as Panel via PanelRegistry and SettingsTab via SettingsTabRegistry.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from jarvix.core.logger import get_logger
from jarvix.plugins.manager import PluginManager, get_plugin_manager
from jarvix.plugins.installer import install_from_path, validate_plugin_source
from jarvix.plugins.remover import uninstall_plugin
from jarvix.ui.extensions import Panel, SettingsTab, get_panel_registry, get_settings_tab_registry

_LOG = get_logger("jarvix.plugins.panel")


class PluginTableWidget(QTableWidget):
    """Table widget for listing plugins."""

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setColumnCount(5)
        self.setHorizontalHeaderLabels(["Name", "Version", "Description", "Status", "Actions"])
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.SingleSelection)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        # Configure columns
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Name
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Version
        header.setSectionResizeMode(2, QHeaderView.Stretch)  # Description
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Status
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Actions

    def _show_context_menu(self, pos) -> None:
        from PySide6.QtWidgets import QMenu
        item = self.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        enable_action = menu.addAction("Enable")
        enable_action.triggered.connect(lambda: self._toggle_enable(item.row(), True))
        disable_action = menu.addAction("Disable")
        disable_action.triggered.connect(lambda: self._toggle_enable(item.row(), False))
        menu.addSeparator()
        uninstall_action = menu.addAction("Uninstall")
        uninstall_action.triggered.connect(lambda: self._uninstall(item.row()))
        menu.exec(self.mapToGlobal(pos))

    def _toggle_enable(self, row: int, enabled: bool) -> None:
        plugin_name = self.item(row, 0).data(Qt.UserRole)
        if plugin_name and hasattr(self, "_manager"):
            if enabled:
                self._manager.enable(plugin_name)
            else:
                self._manager.disable(plugin_name)
            self.parent()._refresh_table()

    def _uninstall(self, row: int) -> None:
        plugin_name = self.item(row, 0).data(Qt.UserRole)
        if plugin_name:
            reply = QMessageBox.question(
                self,
                "Uninstall Plugin",
                f"Uninstall plugin '{plugin_name}'? This cannot be undone.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                if hasattr(self, "_manager"):
                    uninstall_plugin(plugin_name, self._manager)
                    self.parent()._refresh_table()


class PluginsPanel(QWidget):
    """Main widget for the Plugins panel."""

    def __init__(self, manager: Optional[PluginManager] = None) -> None:
        super().__init__()
        self._manager = manager or get_plugin_manager()
        self._setup_ui()
        self._refresh_table()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Toolbar
        toolbar = QToolBar()
        toolbar.setMovable(False)

        # Search
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search plugins...")
        self._search_input.setMinimumWidth(200)
        self._search_input.returnPressed.connect(self._on_search)
        toolbar.addWidget(QLabel("Search:"))
        toolbar.addWidget(self._search_input)

        toolbar.addSeparator()

        # Install button
        install_action = QAction("Install Plugin", self)
        install_action.triggered.connect(self._on_install)
        toolbar.addAction(install_action)

        # Refresh button
        refresh_action = QAction("Refresh", self)
        refresh_action.triggered.connect(self._refresh_table)
        toolbar.addAction(refresh_action)

        # Check updates button
        update_action = QAction("Check Updates", self)
        update_action.triggered.connect(self._on_check_updates)
        toolbar.addAction(update_action)

        layout.addWidget(toolbar)

        # Table
        self._table = PluginTableWidget()
        self._table._manager = self._manager  # Inject manager for context menu
        layout.addWidget(self._table)

        # Status label
        self._status_label = QLabel("Ready")
        layout.addWidget(self._status_label)

    def _refresh_table(self) -> None:
        """Refresh the plugin table."""
        self._status_label.setText("Loading plugins...")
        QTimer.singleShot(0, self._do_refresh)

    def _do_refresh(self) -> None:
        try:
            plugins = self._manager.list_installed()
            self._table.setRowCount(0)
            self._table.setRowCount(len(plugins))

            for row, state in enumerate(plugins):
                # Name
                name_item = QTableWidgetItem(state.name)
                name_item.setData(Qt.UserRole, state.name)
                name_item.setToolTip(state.manifest.description)
                self._table.setItem(row, 0, name_item)

                # Version
                version_item = QTableWidgetItem(state.manifest.version)
                version_item.setTextAlignment(Qt.AlignCenter)
                self._table.setItem(row, 1, version_item)

                # Description
                desc_item = QTableWidgetItem(state.manifest.description)
                self._table.setItem(row, 2, desc_item)

                # Status
                status_text = "Enabled" if state.enabled else "Disabled"
                if state.load_error:
                    status_text = f"Error: {state.load_error}"
                elif state.loaded:
                    status_text += " (Loaded)"
                else:
                    status_text += " (Not Loaded)"
                status_item = QTableWidgetItem(status_text)
                status_item.setTextAlignment(Qt.AlignCenter)
                if state.load_error:
                    status_item.setForeground(Qt.red)
                elif state.enabled and state.loaded:
                    status_item.setForeground(Qt.darkGreen)
                elif state.enabled and not state.loaded:
                    status_item.setForeground(Qt.darkYellow)
                else:
                    status_item.setForeground(Qt.gray)
                self._table.setItem(row, 3, status_item)

                # Actions - enable/disable button
                actions_widget = QWidget()
                actions_layout = QHBoxLayout(actions_widget)
                actions_layout.setContentsMargins(4, 2, 4, 2)

                toggle_btn = QPushButton("Disable" if state.enabled else "Enable")
                toggle_btn.setProperty("plugin_name", state.name)
                toggle_btn.clicked.connect(self._on_toggle_enable)
                actions_layout.addWidget(toggle_btn)

                uninstall_btn = QPushButton("Uninstall")
                uninstall_btn.setProperty("plugin_name", state.name)
                uninstall_btn.clicked.connect(self._on_uninstall)
                actions_layout.addWidget(uninstall_btn)

                self._table.setCellWidget(row, 4, actions_widget)

            self._status_label.setText(f"Showing {len(plugins)} plugins")
        except Exception as e:
            _LOG.error("Failed to refresh plugin table: %s", e)
            self._status_label.setText(f"Error: {e}")

    def _on_search(self) -> None:
        """Filter table by search text."""
        query = self._search_input.text().strip().lower()
        if not query:
            for row in range(self._table.rowCount()):
                self._table.setRowHidden(row, False)
            return

        for row in range(self._table.rowCount()):
            name_item = self._table.item(row, 0)
            desc_item = self._table.item(row, 2)
            match = False
            if name_item and query in name_item.text().lower():
                match = True
            if desc_item and query in desc_item.text().lower():
                match = True
            self._table.setRowHidden(row, not match)

    @Slot()
    def _on_install(self) -> None:
        """Handle install plugin button."""
        file_dialog = QFileDialog(self)
        file_dialog.setFileMode(QFileDialog.ExistingFile)
        file_dialog.setNameFilter("Plugin Archives (*.zip *.tar.gz *.tgz);;All Files (*)")
        file_dialog.setWindowTitle("Select Plugin Archive or Directory")

        if file_dialog.exec() == QFileDialog.Accepted:
            selected = file_dialog.selectedFiles()
            if selected:
                source_path = Path(selected[0])
                self._status_label.setText(f"Installing {source_path.name}...")
                QTimer.singleShot(0, lambda: self._do_install(source_path))

    async def _do_install(self, source_path: Path) -> None:
        try:
            result = install_from_path(source_path, self._manager)
            if result["success"]:
                _LOG.info("Installed plugin: %s", result["plugin_name"])
                self._status_label.setText(f"Installed: {result['plugin_name']}")
                self._refresh_table()
            else:
                _LOG.error("Install failed: %s", result.get("error", "Unknown"))
                self._status_label.setText(f"Install failed: {result.get('error', 'Unknown')}")
                QMessageBox.critical(self, "Install Failed", result.get("error", "Unknown error"))
        except Exception as e:
            _LOG.exception("Install failed")
            self._status_label.setText(f"Install error: {e}")
            QMessageBox.critical(self, "Install Error", str(e))

    @Slot()
    def _on_toggle_enable(self) -> None:
        """Handle enable/disable button click."""
        btn = self.sender()
        if not isinstance(btn, QPushButton):
            return
        plugin_name = btn.property("plugin_name")
        if not plugin_name:
            return

        state = self._manager.get_plugin(plugin_name)
        if not state:
            return

        if state.enabled:
            self._manager.disable(plugin_name)
        else:
            self._manager.enable(plugin_name)
        self._refresh_table()

    @Slot()
    def _on_uninstall(self) -> None:
        """Handle uninstall button click."""
        btn = self.sender()
        if not isinstance(btn, QPushButton):
            return
        plugin_name = btn.property("plugin_name")
        if not plugin_name:
            return

        reply = QMessageBox.question(
            self,
            "Uninstall Plugin",
            f"Uninstall plugin '{plugin_name}'? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            result = uninstall_plugin(plugin_name, self._manager)
            if result["success"]:
                _LOG.info("Uninstalled plugin: %s", plugin_name)
                self._status_label.setText(f"Uninstalled: {plugin_name}")
            else:
                _LOG.error("Uninstall failed: %s", result.get("error", "Unknown"))
                self._status_label.setText(f"Uninstall failed: {result.get('error', 'Unknown')}")
                QMessageBox.critical(self, "Uninstall Failed", result.get("error", "Unknown error"))
            self._refresh_table()

    @Slot()
    def _on_check_updates(self) -> None:
        """Check for plugin updates."""
        self._status_label.setText("Checking for updates...")
        try:
            from jarvix.plugins.updater import get_updater
            updater = get_updater(self._manager)
            updates = updater.check_all()
            if updates:
                msg = f"Found {len(updates)} updates:\n"
                for u in updates:
                    msg += f"  {u.plugin_name}: {u.current_version} → {u.available_version}\n"
                QMessageBox.information(self, "Updates Available", msg)
            else:
                QMessageBox.information(self, "No Updates", "All plugins are up to date")
            self._status_label.setText("Update check complete")
        except Exception as e:
            _LOG.error("Update check failed: %s", e)
            self._status_label.setText(f"Update check failed: {e}")


class PluginSettingsTab(SettingsTab):
    """Settings tab for plugin configuration."""

    group = "plugins"
    title = "Plugins"

    def __init__(self, manager: Optional[PluginManager] = None) -> None:
        self._manager = manager or get_plugin_manager()
        self._widget: Optional[QWidget] = None

    def widget(self) -> QWidget:
        if self._widget is None:
            self._widget = self._build_widget()
        return self._widget

    def _build_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        layout.addWidget(QLabel("<h3>Plugin Settings</h3>"))

        # Auto-update
        from PySide6.QtWidgets import QCheckBox
        auto_update = QCheckBox("Automatically check for plugin updates")
        auto_update.setChecked(True)
        layout.addWidget(auto_update)

        # Trusted sources
        layout.addWidget(QLabel("Trusted plugin sources (one per line):"))
        sources_input = QLineEdit()
        sources_input.setPlaceholderText("https://example.com/plugins\n~/my-plugins")
        layout.addWidget(sources_input)

        layout.addStretch()

        # Info
        info = QLabel("Plugins are stored in %APPDATA%/jarvix/plugins/")
        info.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(info)

        return widget


class PluginsPanelWrapper(Panel):
    """Panel wrapper for the Plugins UI."""

    name = "Plugins"
    icon = "🔌"

    def __init__(self) -> None:
        self._panel: Optional[PluginsPanel] = None

    def widget(self) -> QWidget:
        if self._panel is None:
            self._panel = PluginsPanel()
        return self._panel

    def on_show(self) -> None:
        if self._panel:
            self._panel._refresh_table()

    def on_hide(self) -> None:
        pass


def register_plugins_ui() -> None:
    """Register the plugins panel and settings tab."""
    registry = get_panel_registry()
    registry.register(PluginsPanelWrapper())

    settings_registry = get_settings_tab_registry()
    settings_registry.register(PluginSettingsTab())


# Auto-register when imported
register_plugins_ui()