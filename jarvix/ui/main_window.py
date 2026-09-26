"""Main window for jarvix.

Builds the UI dynamically from PanelRegistry and SettingsTabRegistry.
No phase after Phase 1 edits this file.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from jarvix.core.events import EventBus, EmergencyStopRequested
from jarvix.core.logger import get_logger
from jarvix.ui.extensions import get_panel_registry, get_settings_tab_registry, Panel, SettingsTab

_LOG = get_logger("jarvix.main_window")


class PermissionDialog(QDialog):
    """Dialog for CONFIRM-level tool permissions."""

    def __init__(
        self,
        parent: QWidget,
        tool_name: str,
        args: Dict[str, Any],
        reason: str,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Permission Required")
        self.setModal(True)
        self.resize(400, 200)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(f"<b>Action:</b> {tool_name}"))
        layout.addWidget(QLabel(f"<b>Target:</b> {args.get('app_name', args.get('path', str(args)))}"))
        layout.addWidget(QLabel(f"<b>Reason:</b> {reason}"))
        layout.addWidget(QLabel("This action requires your confirmation."))

        buttons = QDialogButtonBox()
        deny_btn = buttons.addButton("Deny", QDialogButtonBox.RejectRole)
        allow_once_btn = buttons.addButton("Allow Once", QDialogButtonBox.AcceptRole)
        always_btn = buttons.addButton("Always Allow", QDialogButtonBox.ApplyRole)

        deny_btn.clicked.connect(self.reject)
        allow_once_btn.clicked.connect(lambda: self.done(1))  # AcceptRole
        always_btn.clicked.connect(lambda: self.done(2))  # ApplyRole

        layout.addWidget(buttons)

        self._result = 0

    def result(self) -> int:
        return self._result

    def done(self, r: int) -> None:
        self._result = r
        super().done(r)


class StatusIndicator(QWidget):
    """Shows ONLINE/OFFLINE/MIC status."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(12)

        self._online_label = QLabel("● OFFLINE")
        self._online_label.setStyleSheet("color: #ff6b6b; font-weight: bold;")
        layout.addWidget(self._online_label)

        self._mic_label = QLabel("🎤 unavailable")
        self._mic_label.setStyleSheet("color: #888;")
        layout.addWidget(self._mic_label)

        self._task_label = QLabel("Task: None")
        self._task_label.setStyleSheet("color: #888;")
        layout.addWidget(self._task_label)

        layout.addStretch()

    def set_online(self, online: bool) -> None:
        if online:
            self._online_label.setText("● ONLINE")
            self._online_label.setStyleSheet("color: #6bff6b; font-weight: bold;")
        else:
            self._online_label.setText("● OFFLINE")
            self._online_label.setStyleSheet("color: #ff6b6b; font-weight: bold;")

    def set_mic_available(self, available: bool) -> None:
        if available:
            self._mic_label.setText("🎤 ready")
            self._mic_label.setStyleSheet("color: #6bff6b;")
        else:
            self._mic_label.setText("🎤 unavailable")
            self._mic_label.setStyleSheet("color: #888;")

    def set_current_task(self, task: Optional[str]) -> None:
        if task:
            self._task_label.setText(f"Task: {task}")
            self._task_label.setStyleSheet("color: #ffd700;")
        else:
            self._task_label.setText("Task: None")
            self._task_label.setStyleSheet("color: #888;")


class ChatWidget(QWidget):
    """Chat interface: message history + user input."""

    message_submitted = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)

        # Message list
        self._list = QListWidget()
        self._list.setWordWrap(True)
        layout.addWidget(self._list)

        # Input area
        input_layout = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a command or ask a question...")
        self._input.returnPressed.connect(self._on_submit)
        input_layout.addWidget(self._input)

        self._send_btn = QPushButton("Send")
        self._send_btn.clicked.connect(self._on_submit)
        input_layout.addWidget(self._send_btn)

        layout.addLayout(input_layout)

    def _on_submit(self) -> None:
        text = self._input.text().strip()
        if text:
            self.message_submitted.emit(text)
            self._input.clear()

    def add_message(self, role: str, content: str) -> None:
        item = QListWidgetItem(f"[{role.upper()}] {content}")
        if role == "user":
            item.setBackground(Qt.lightGray)
        elif role == "assistant":
            item.setBackground(Qt.white)
        elif role == "system":
            item.setBackground(Qt.yellow)
        self._list.addItem(item)
        self._list.scrollToBottom()

    def set_enabled(self, enabled: bool) -> None:
        self._input.setEnabled(enabled)
        self._send_btn.setEnabled(enabled)


class JarvixWindow(QMainWindow):
    """Main application window."""

    def __init__(
        self,
        event_bus: EventBus,
        panel_registry: Any,
        settings_tab_registry: Any,
    ) -> None:
        super().__init__()
        self._event_bus = event_bus
        self._panel_registry = panel_registry
        self._settings_tab_registry = settings_tab_registry

        self.setWindowTitle("jarvix")
        self.resize(900, 600)

        # Status bar
        self._status = StatusIndicator()
        self.statusBar().addPermanentWidget(self._status)

        # Toolbar
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # Panels tab widget
        self._tabs = QTabWidget()
        self.setCentralWidget(self._tabs)

        # Build panels from registry
        self._build_panels()

        # Settings action
        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self._show_settings)
        toolbar.addAction(settings_action)

        # Emergency stop action
        stop_action = QAction("Emergency Stop", self)
        stop_action.setShortcut(QKeySequence("Ctrl+Shift+J"))
        stop_action.triggered.connect(self._emergency_stop)
        toolbar.addAction(stop_action)

        # Subscribe to events
        self._event_bus.subscribe("online.status_changed", self._on_online_changed)
        self._event_bus.subscribe("voice.wake", self._on_voice_wake)
        self._event_bus.subscribe("emergency.stop", self._on_emergency_stop)

        _LOG.info("Main window initialized")

    def _build_panels(self) -> None:
        panels = self._panel_registry.panels()
        if not panels:
            # Fallback: create a basic Home panel
            home = QWidget()
            layout = QVBoxLayout(home)
            layout.addWidget(QLabel("jarvix\n\nNo panels registered yet."))
            self._tabs.addTab(home, "Home")
        else:
            for panel in panels:
                self._tabs.addTab(panel.widget(), panel.name)

    def _show_settings(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Settings")
        dialog.resize(600, 500)

        layout = QVBoxLayout(dialog)

        tab_widget = QTabWidget()
        for group in self._settings_tab_registry.all_groups():
            group_widget = QWidget()
            group_layout = QVBoxLayout(group_widget)
            for tab in self._settings_tab_registry.tabs_for_group(group):
                group_layout.addWidget(tab.widget())
            group_layout.addStretch()
            tab_widget.addTab(group_widget, group.capitalize())

        layout.addWidget(tab_widget)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        dialog.exec()

    def _emergency_stop(self) -> None:
        self._event_bus.publish(EmergencyStopRequested())

    def _on_online_changed(self, event: Any) -> None:
        from PySide6.QtCore import QMetaObject, Qt, Q_ARG
        QMetaObject.invokeMethod(
            self._status, "set_online",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(bool, event.data.get("online", False))
        )

    def _on_voice_wake(self, event: Any) -> None:
        from PySide6.QtCore import QMetaObject, Qt, Q_ARG
        QMetaObject.invokeMethod(
            self._status, "set_mic_available",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(bool, True)
        )

    def _on_emergency_stop(self, event: Any) -> None:
        QMessageBox.warning(self, "Emergency Stop", "All operations cancelled.")

    def closeEvent(self, event: Any) -> None:
        from jarvix.core.emergency_stop import get_emergency_stop
        es = get_emergency_stop()
        if es:
            es.stop()
        self._event_bus.unsubscribe("online.status_changed", self._on_online_changed)
        self._event_bus.unsubscribe("voice.wake", self._on_voice_wake)
        self._event_bus.unsubscribe("emergency.stop", self._on_emergency_stop)
        from jarvix.core.events import ShutdownRequested
        self._event_bus.publish(ShutdownRequested())
        super().closeEvent(event)