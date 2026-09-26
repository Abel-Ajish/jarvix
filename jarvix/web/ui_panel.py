"""Web UI Panel for jarvix settings (Phase 6).

Provides a settings tab for web configuration:
- Search engine selection
- Browser channel (Edge/Chromium)
- Headless mode
- Download folder
- Browser management (clear cache, reset)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jarvix.core.config import get_settings
from jarvix.core.logger import get_logger
from jarvix.ui.extensions import SettingsTab, get_settings_tab_registry

_LOG = get_logger("jarvix.web.ui_panel")


class WebSettingsTab(SettingsTab):
    """Settings tab for web configuration."""

    group = "web"
    title = "Web"

    def __init__(self) -> None:
        self._widget: Optional[QWidget] = None
        self._settings = get_settings()

    def widget(self) -> QWidget:
        if self._widget is None:
            self._widget = self._build_widget()
        return self._widget

    def _build_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # --- Search Engine ---
        search_group = QGroupBox("Search")
        search_layout = QFormLayout(search_group)

        self._search_engine = QComboBox()
        self._search_engine.addItems(["duckduckgo", "google"])
        self._search_engine.setCurrentText(self._settings.get("web.search_engine", "duckduckgo"))
        self._search_engine.currentTextChanged.connect(self._on_search_engine_changed)
        search_layout.addRow("Default engine:", self._search_engine)

        layout.addWidget(search_group)

        # --- Browser ---
        browser_group = QGroupBox("Browser (Playwright)")
        browser_layout = QFormLayout(browser_group)

        self._browser_channel = QComboBox()
        self._browser_channel.addItems(["msedge", "chromium", "firefox", "webkit"])
        self._browser_channel.setCurrentText(self._settings.get("web.browser", "msedge"))
        self._browser_channel.currentTextChanged.connect(self._on_browser_changed)
        browser_layout.addRow("Channel:", self._browser_channel)

        self._headless = QCheckBox("Run headless (no visible window)")
        self._headless.setChecked(self._settings.get("web.headless", True))
        self._headless.toggled.connect(self._on_headless_changed)
        browser_layout.addRow("", self._headless)

        # Viewport
        viewport_layout = QHBoxLayout()
        self._viewport_width = QLineEdit(str(self._settings.get("web.viewport_width", 1280)))
        self._viewport_width.setPlaceholderText("width")
        self._viewport_width.setMaximumWidth(80)
        self._viewport_height = QLineEdit(str(self._settings.get("web.viewport_height", 720)))
        self._viewport_height.setPlaceholderText("height")
        self._viewport_height.setMaximumWidth(80)
        viewport_layout.addWidget(self._viewport_width)
        viewport_layout.addWidget(QLabel("×"))
        viewport_layout.addWidget(self._viewport_height)
        viewport_layout.addStretch()
        self._viewport_width.editingFinished.connect(self._on_viewport_changed)
        self._viewport_height.editingFinished.connect(self._on_viewport_changed)
        browser_layout.addRow("Viewport:", viewport_layout)

        # Test browser button
        test_btn = QPushButton("Test Browser Launch")
        test_btn.clicked.connect(self._on_test_browser)
        browser_layout.addRow("", test_btn)

        layout.addWidget(browser_group)

        # --- Downloads ---
        download_group = QGroupBox("Downloads")
        download_layout = QFormLayout(download_group)

        download_path_layout = QHBoxLayout()
        self._download_path = QLineEdit(self._settings.get("web.download_folder", "~/Downloads/jarvix"))
        self._download_path.setReadOnly(True)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._on_browse_download_folder)
        download_path_layout.addWidget(self._download_path)
        download_path_layout.addWidget(browse_btn)
        download_layout.addRow("Folder:", download_path_layout)

        open_folder_btn = QPushButton("Open Download Folder")
        open_folder_btn.clicked.connect(self._on_open_download_folder)
        download_layout.addRow("", open_folder_btn)

        layout.addWidget(download_group)

        # --- Maintenance ---
        maint_group = QGroupBox("Maintenance")
        maint_layout = QVBoxLayout(maint_group)

        clear_cache_btn = QPushButton("Clear Browser Cache & Data")
        clear_cache_btn.clicked.connect(self._on_clear_browser_cache)
        maint_layout.addWidget(clear_cache_btn)

        reset_browser_btn = QPushButton("Reset Browser Settings")
        reset_browser_btn.clicked.connect(self._on_reset_browser)
        maint_layout.addWidget(reset_browser_btn)

        layout.addWidget(maint_group)

        layout.addStretch()

        # Info
        info = QLabel(
            "Web subsystem uses Playwright for browser automation. "
            "Edge (msedge) is recommended on Windows. "
            "Run 'playwright install' in the venv if browsers are missing."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(info)

        return widget

    # --- Handlers ---

    def _on_search_engine_changed(self, value: str) -> None:
        self._settings.set("web.search_engine", value)

    def _on_browser_changed(self, value: str) -> None:
        self._settings.set("web.browser", value)

    def _on_headless_changed(self, checked: bool) -> None:
        self._settings.set("web.headless", checked)

    def _on_viewport_changed(self) -> None:
        try:
            w = int(self._viewport_width.text())
            h = int(self._viewport_height.text())
            if 400 <= w <= 3840 and 300 <= h <= 2160:
                self._settings.set("web.viewport_width", w)
                self._settings.set("web.viewport_height", h)
            else:
                raise ValueError("Out of range")
        except Exception:
            # Reset to current settings
            self._viewport_width.setText(str(self._settings.get("web.viewport_width", 1280)))
            self._viewport_height.setText(str(self._settings.get("web.viewport_height", 720)))

    def _on_browse_download_folder(self) -> None:
        current = self._download_path.text()
        path = QFileDialog.getExistingDirectory(
            self._widget,
            "Select Download Folder",
            current,
            QFileDialog.ShowDirsOnly,
        )
        if path:
            self._download_path.setText(path)
            self._settings.set("web.download_folder", path)

    def _on_open_download_folder(self) -> None:
        import subprocess
        path = Path(self._download_path.text()).expanduser()
        if path.exists():
            subprocess.Popen(['explorer', str(path)])
        else:
            QMessageBox.warning(self._widget, "Not Found", f"Folder does not exist: {path}")

    def _on_test_browser(self) -> None:
        """Test browser launch in background."""
        from jarvix.web.browser import get_browser_manager, reset_browser_manager

        # Reset to pick up new settings
        reset_browser_manager()

        btn = self._widget.findChild(QPushButton, "test_browser_btn")
        if btn:
            btn.setEnabled(False)
            btn.setText("Testing...")

        async def _test():
            try:
                mgr = get_browser_manager(
                    headless=self._headless.isChecked(),
                    channel=self._browser_channel.currentText(),
                    viewport=(
                        int(self._viewport_width.text()),
                        int(self._viewport_height.text()),
                    ),
                )
                await mgr.start()
                await mgr.stop()
                return True, "Browser launched and closed successfully!"
            except Exception as e:
                return False, f"Browser test failed: {e}"

        def _done(fut):
            try:
                ok, msg = fut.result()
                if self._widget:
                    if btn:
                        btn.setEnabled(True)
                        btn.setText("Test Browser Launch")
                    QMessageBox.information(self._widget, "Browser Test", msg)
            except Exception as e:
                if self._widget and btn:
                    btn.setEnabled(True)
                    btn.setText("Test Browser Launch")
                _LOG.exception("Test browser callback failed")

        # Schedule on event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        fut = asyncio.run_coroutine_threadsafe(_test(), loop)
        fut.add_done_callback(_done)

    def _on_clear_browser_cache(self) -> None:
        """Clear Playwright browser cache/data."""
        from jarvix.web.browser import reset_browser_manager

        reply = QMessageBox.question(
            self._widget,
            "Clear Browser Cache",
            "This will reset the browser and clear all cached data.\nContinue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            reset_browser_manager()
            QMessageBox.information(self._widget, "Done", "Browser cache cleared. Next launch will be fresh.")

    def _on_reset_browser(self) -> None:
        """Reset all web settings to defaults."""
        reply = QMessageBox.question(
            self._widget,
            "Reset Web Settings",
            "Reset all web settings to defaults? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            defaults = {
                "web.search_engine": "duckduckgo",
                "web.browser": "msedge",
                "web.headless": True,
                "web.viewport_width": 1280,
                "web.viewport_height": 720,
                "web.download_folder": str(Path.home() / "Downloads" / "jarvix"),
            }
            for k, v in defaults.items():
                self._settings.set(k, v)

            # Reload widget
            if self._widget:
                parent = self._widget.parent()
                if parent:
                    layout = parent.layout()
                    if layout:
                        idx = layout.indexOf(self._widget)
                        if idx >= 0:
                            self._widget.deleteLater()
                            self._widget = None
                            new_widget = self._build_widget()
                            layout.insertWidget(idx, new_widget)

            QMessageBox.information(self._widget, "Done", "Web settings reset to defaults.")


def register_web_settings_tab() -> None:
    """Register the web settings tab."""
    settings_registry = get_settings_tab_registry()
    settings_registry.register(WebSettingsTab())


# Auto-register on import
register_web_settings_tab()