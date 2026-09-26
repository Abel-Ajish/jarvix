"""Status indicator widget — shows ONLINE/OFFLINE/MIC status."""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QWidget,
)


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