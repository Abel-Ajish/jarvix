"""Permission dialog for CONFIRM-level tools."""

from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class PermissionDialog(QDialog):
    """Dialog for CONFIRM-level tool permissions."""

    def __init__(
        self,
        parent: Optional[QWidget],
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
        target = args.get("app_name", args.get("path", str(args)))
        layout.addWidget(QLabel(f"<b>Target:</b> {target}"))
        layout.addWidget(QLabel(f"<b>Reason:</b> {reason}"))
        layout.addWidget(QLabel("This action requires your confirmation."))

        buttons = QDialogButtonBox()
        deny_btn = buttons.addButton("Deny", QDialogButtonBox.RejectRole)
        allow_once_btn = buttons.addButton("Allow Once", QDialogButtonBox.AcceptRole)
        always_btn = buttons.addButton("Always Allow", QDialogButtonBox.ApplyRole)

        deny_btn.clicked.connect(self.reject)
        allow_once_btn.clicked.connect(lambda: self.done(1))  # Allow once
        always_btn.clicked.connect(lambda: self.done(2))  # Always allow

        layout.addWidget(buttons)

        self._result = 0

    def result(self) -> int:
        return self._result

    def done(self, r: int) -> None:
        self._result = r
        super().done(r)