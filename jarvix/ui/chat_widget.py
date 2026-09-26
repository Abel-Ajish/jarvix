"""Chat widget — message display + user input."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ChatWidget(QWidget):
    """Chat interface: message history + user input."""

    message_submitted = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)

        # Message list
        self._list = QListWidget()
        self._list.setWordWrap(True)
        self._max_messages = 1000
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

        # Input mode toggle
        self._mode_toggle = QPushButton("🎤 Voice Mode")
        self._mode_toggle.setCheckable(True)
        self._mode_toggle.setChecked(False)
        self._mode_toggle.clicked.connect(self._toggle_input_mode)
        input_layout.addWidget(self._mode_toggle)

        layout.addLayout(input_layout)

    def _toggle_input_mode(self, checked: bool) -> None:
        """Toggle between voice-only and text input modes."""
        if checked:
            self._input.setEnabled(False)
            self._send_btn.setEnabled(False)
            self._mode_toggle.setText("⌨️ Text Mode")
            self.add_message("system", "Voice mode enabled. Speak your command.")
        else:
            self._input.setEnabled(True)
            self._send_btn.setEnabled(True)
            self._mode_toggle.setText("🎤 Voice Mode")
            self.add_message("system", "Text mode enabled. Type your command.")

    def get_input_mode(self) -> str:
        """Get current input mode: 'voice' or 'text'."""
        return "voice" if self._mode_toggle.isChecked() else "text"

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
        # Enforce message limit to prevent unbounded memory growth
        while self._list.count() > self._max_messages:
            self._list.takeItem(0)
        self._list.scrollToBottom()

    def set_enabled(self, enabled: bool) -> None:
        # Respect voice mode toggle
        is_voice_mode = self._mode_toggle.isChecked()
        self._input.setEnabled(enabled and not is_voice_mode)
        self._send_btn.setEnabled(enabled and not is_voice_mode)