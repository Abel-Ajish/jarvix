"""Agent Settings Panel (PySide6 widget) for the Advanced Agent subsystem.

Registers as a SettingsTab in the 'agent' group.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, Slot
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
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from jarvix.core.config import get_settings
from jarvix.core.logger import get_logger
from jarvix.ui.extensions import SettingsTab, get_settings_tab_registry

_LOG = get_logger("jarvix.agent.ui_panel")


class AgentSettingsTab(SettingsTab):
    """Settings tab for agent configuration."""

    group = "agent"
    title = "Agent"

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

        # --- Planner ---
        planner_group = QGroupBox("Planner")
        planner_layout = QFormLayout(planner_group)

        self._planner_model = QComboBox()
        self._planner_model.addItems(["auto", "openrouter", "openai", "anthropic", "gemini"])
        self._planner_model.setCurrentText(self._settings.get("agent.planner_model", "auto"))
        self._planner_model.currentTextChanged.connect(self._on_planner_model_changed)
        planner_layout.addRow("Default model:", self._planner_model)

        self._max_steps = QSpinBox()
        self._max_steps.setRange(1, 50)
        self._max_steps.setValue(self._settings.get("agent.max_steps", 10))
        self._max_steps.valueChanged.connect(self._on_max_steps_changed)
        planner_layout.addRow("Max steps per plan:", self._max_steps)

        self._max_parallel = QSpinBox()
        self._max_parallel.setRange(1, 10)
        self._max_parallel.setValue(self._settings.get("agent.max_parallel_steps", 1))
        self._max_parallel.valueChanged.connect(self._on_max_parallel_changed)
        planner_layout.addRow("Max parallel steps:", self._max_parallel)

        layout.addWidget(planner_group)

        # --- Retry Policy ---
        retry_group = QGroupBox("Retry Policy")
        retry_layout = QFormLayout(retry_group)

        self._max_retries = QSpinBox()
        self._max_retries.setRange(0, 10)
        self._max_retries.setValue(self._settings.get("agent.max_retries", 3))
        self._max_retries.valueChanged.connect(self._on_max_retries_changed)
        retry_layout.addRow("Max retries per step:", self._max_retries)

        self._retry_delay = QSpinBox()
        self._retry_delay.setRange(100, 30000)
        self._retry_delay.setValue(self._settings.get("agent.retry_delay_ms", 1000))
        self._retry_delay.setSuffix(" ms")
        self._retry_delay.valueChanged.connect(self._on_retry_delay_changed)
        retry_layout.addRow("Base retry delay:", self._retry_delay)

        self._retry_backoff = QSpinBox()
        self._retry_backoff.setRange(1, 10)
        self._retry_backoff.setValue(int(self._settings.get("agent.retry_backoff", 2.0) * 10))
        self._retry_backoff.setSuffix("x")
        self._retry_backoff.setToolTip("Backoff multiplier (e.g., 2.0 = 2x each retry)")
        self._retry_backoff.valueChanged.connect(self._on_retry_backoff_changed)
        retry_layout.addRow("Exponential backoff:", self._retry_backoff)

        self._retry_on_error = QCheckBox("Retry on tool errors")
        self._retry_on_error.setChecked(self._settings.get("agent.retry_on_tool_error", True))
        self._retry_on_error.toggled.connect(self._on_retry_on_error_changed)
        retry_layout.addRow("", self._retry_on_error)

        self._retry_on_verify_fail = QCheckBox("Retry on verification failure")
        self._retry_on_verify_fail.setChecked(self._settings.get("agent.retry_on_verification_failure", True))
        self._retry_on_verify_fail.toggled.connect(self._on_retry_on_verify_fail_changed)
        retry_layout.addRow("", self._retry_on_verify_fail)

        layout.addWidget(retry_group)

        # --- Recovery ---
        recovery_group = QGroupBox("Recovery")
        recovery_layout = QFormLayout(recovery_group)

        self._default_recovery = QComboBox()
        self._default_recovery.addItems([
            "partial_completion",
            "compensate",
            "rollback",
            "alternative_path",
        ])
        self._default_recovery.setCurrentText(self._settings.get("agent.default_recovery", "partial_completion"))
        self._default_recovery.currentTextChanged.connect(self._on_default_recovery_changed)
        recovery_layout.addRow("Default strategy:", self._default_recovery)

        self._auto_recovery = QCheckBox("Automatically select recovery action")
        self._auto_recovery.setChecked(self._settings.get("agent.auto_recovery", True))
        self._auto_recovery.toggled.connect(self._on_auto_recovery_changed)
        recovery_layout.addRow("", self._auto_recovery)

        layout.addWidget(recovery_group)

        # --- Execution ---
        exec_group = QGroupBox("Execution")
        exec_layout = QFormLayout(exec_group)

        self._auto_continue = QCheckBox("Auto-continue after successful steps")
        self._auto_continue.setChecked(self._settings.get("agent.auto_continue", True))
        self._auto_continue.toggled.connect(self._on_auto_continue_changed)
        exec_layout.addRow("", self._auto_continue)

        self._require_confirm = QCheckBox("Require confirmation for CONFIRM tools")
        self._require_confirm.setChecked(self._settings.get("agent.require_confirm", True))
        self._require_confirm.toggled.connect(self._on_require_confirm_changed)
        exec_layout.addRow("", self._require_confirm)

        self._step_timeout = QSpinBox()
        self._step_timeout.setRange(0, 3600)
        self._step_timeout.setValue(self._settings.get("agent.step_timeout_seconds", 300))
        self._step_timeout.setSuffix(" s")
        self._step_timeout.setSpecialValueText("No timeout (0)")
        self._step_timeout.valueChanged.connect(self._on_step_timeout_changed)
        exec_layout.addRow("Step timeout:", self._step_timeout)

        self._task_timeout = QSpinBox()
        self._task_timeout.setRange(0, 86400)
        self._task_timeout.setValue(self._settings.get("agent.task_timeout_seconds", 3600))
        self._task_timeout.setSuffix(" s")
        self._task_timeout.setSpecialValueText("No timeout (0)")
        self._task_timeout.valueChanged.connect(self._on_task_timeout_changed)
        exec_layout.addRow("Task timeout:", self._task_timeout)

        layout.addWidget(exec_group)

        # --- Background Tasks ---
        bg_group = QGroupBox("Background Tasks")
        bg_layout = QFormLayout(bg_group)

        self._bg_enabled = QCheckBox("Enable background task execution")
        self._bg_enabled.setChecked(self._settings.get("agent.background_enabled", True))
        self._bg_enabled.toggled.connect(self._on_bg_enabled_changed)
        bg_layout.addRow("", self._bg_enabled)

        self._max_bg_tasks = QSpinBox()
        self._max_bg_tasks.setRange(1, 20)
        self._max_bg_tasks.setValue(self._settings.get("agent.max_background_tasks", 5))
        self._max_bg_tasks.valueChanged.connect(self._on_max_bg_tasks_changed)
        bg_layout.addRow("Max concurrent:", self._max_bg_tasks)

        self._persist_tasks = QCheckBox("Persist tasks to disk")
        self._persist_tasks.setChecked(self._settings.get("agent.persist_tasks", True))
        self._persist_tasks.toggled.connect(self._on_persist_tasks_changed)
        bg_layout.addRow("", self._persist_tasks)

        persist_path_layout = QHBoxLayout()
        self._persist_path = QLineEdit(self._settings.get("agent.persist_dir", str(Path.home() / "AppData" / "Roaming" / "jarvix" / "tasks")))
        self._persist_path.setReadOnly(True)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._on_browse_persist_dir)
        persist_path_layout.addWidget(self._persist_path)
        persist_path_layout.addWidget(browse_btn)
        bg_layout.addRow("Persist directory:", persist_path_layout)

        layout.addWidget(bg_group)

        # --- Maintenance ---
        maint_group = QGroupBox("Maintenance")
        maint_layout = QVBoxLayout(maint_group)

        cleanup_btn = QPushButton("Cleanup Old Completed Tasks")
        cleanup_btn.clicked.connect(self._on_cleanup)
        maint_layout.addWidget(cleanup_btn)

        reset_btn = QPushButton("Reset Agent Settings to Defaults")
        reset_btn.clicked.connect(self._on_reset)
        maint_layout.addWidget(reset_btn)

        layout.addWidget(maint_group)

        layout.addStretch()

        # Info
        info = QLabel(
            "Advanced Agent settings control multi-step task planning, execution, "
            "retry behavior, and recovery strategies. "
            "Requires an online AI provider for planning and verification."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(info)

        return widget

    # --- Handlers ---

    def _on_planner_model_changed(self, value: str) -> None:
        self._settings.set("agent.planner_model", value)

    def _on_max_steps_changed(self, value: int) -> None:
        self._settings.set("agent.max_steps", value)

    def _on_max_parallel_changed(self, value: int) -> None:
        self._settings.set("agent.max_parallel_steps", value)

    def _on_max_retries_changed(self, value: int) -> None:
        self._settings.set("agent.max_retries", value)

    def _on_retry_delay_changed(self, value: int) -> None:
        self._settings.set("agent.retry_delay_ms", value)

    def _on_retry_backoff_changed(self, value: int) -> None:
        self._settings.set("agent.retry_backoff", value / 10.0)

    def _on_retry_on_error_changed(self, checked: bool) -> None:
        self._settings.set("agent.retry_on_tool_error", checked)

    def _on_retry_on_verify_fail_changed(self, checked: bool) -> None:
        self._settings.set("agent.retry_on_verification_failure", checked)

    def _on_default_recovery_changed(self, value: str) -> None:
        self._settings.set("agent.default_recovery", value)

    def _on_auto_recovery_changed(self, checked: bool) -> None:
        self._settings.set("agent.auto_recovery", checked)

    def _on_auto_continue_changed(self, checked: bool) -> None:
        self._settings.set("agent.auto_continue", checked)

    def _on_require_confirm_changed(self, checked: bool) -> None:
        self._settings.set("agent.require_confirm", checked)

    def _on_step_timeout_changed(self, value: int) -> None:
        self._settings.set("agent.step_timeout_seconds", value)

    def _on_task_timeout_changed(self, value: int) -> None:
        self._settings.set("agent.task_timeout_seconds", value)

    def _on_bg_enabled_changed(self, checked: bool) -> None:
        self._settings.set("agent.background_enabled", checked)

    def _on_max_bg_tasks_changed(self, value: int) -> None:
        self._settings.set("agent.max_background_tasks", value)

    def _on_persist_tasks_changed(self, checked: bool) -> None:
        self._settings.set("agent.persist_tasks", checked)

    def _on_browse_persist_dir(self) -> None:
        current = self._persist_path.text()
        path = QFileDialog.getExistingDirectory(
            self._widget,
            "Select Task Persistence Directory",
            current,
            QFileDialog.ShowDirsOnly,
        )
        if path:
            self._persist_path.setText(path)
            self._settings.set("agent.persist_dir", path)

    def _on_cleanup(self) -> None:
        """Clean up old completed tasks."""
        from jarvix.agent.task_manager import get_task_manager

        mgr = get_task_manager()
        if not mgr:
            QMessageBox.warning(self._widget, "Not Available", "Task manager not initialized")
            return

        reply = QMessageBox.question(
            self._widget,
            "Cleanup Tasks",
            "Remove completed tasks older than 24 hours from memory?\n"
            "(Saved tasks on disk are not affected)",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            count = mgr.cleanup_completed_tasks(max_age_hours=24)
            QMessageBox.information(self._widget, "Done", f"Cleaned up {count} tasks from memory")

    def _on_reset(self) -> None:
        """Reset all agent settings to defaults."""
        reply = QMessageBox.question(
            self._widget,
            "Reset Agent Settings",
            "Reset all agent settings to defaults? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            defaults = {
                "agent.planner_model": "auto",
                "agent.max_steps": 10,
                "agent.max_parallel_steps": 1,
                "agent.max_retries": 3,
                "agent.retry_delay_ms": 1000,
                "agent.retry_backoff": 2.0,
                "agent.retry_on_tool_error": True,
                "agent.retry_on_verification_failure": True,
                "agent.default_recovery": "partial_completion",
                "agent.auto_recovery": True,
                "agent.auto_continue": True,
                "agent.require_confirm": True,
                "agent.step_timeout_seconds": 300,
                "agent.task_timeout_seconds": 3600,
                "agent.background_enabled": True,
                "agent.max_background_tasks": 5,
                "agent.persist_tasks": True,
                "agent.persist_dir": str(Path.home() / "AppData" / "Roaming" / "jarvix" / "tasks"),
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

            QMessageBox.information(self._widget, "Done", "Agent settings reset to defaults.")


def register_agent_settings_tab() -> None:
    """Register the agent settings tab."""
    settings_registry = get_settings_tab_registry()
    settings_registry.register(AgentSettingsTab())


# Auto-register on import
register_agent_settings_tab()