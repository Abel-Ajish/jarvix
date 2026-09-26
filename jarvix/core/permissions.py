"""Permission system for jarvix.

Three levels:
- SAFE: automatically execute (open apps, read files, screenshots, volume, etc.)
- CONFIRM: ask before executing (delete files, install software, arbitrary commands)
- BLOCKED: require explicit enabling from Settings

The PermissionManager is the single gate through which ALL tool executions pass.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Any, Dict, Optional

from jarvix.core.config import get_settings
from jarvix.core.logger import get_logger

_LOG = get_logger("jarvix.permissions")


class PermissionLevel(Enum):
    SAFE = auto()       # auto-execute
    CONFIRM = auto()    # dialog required
    BLOCKED = auto()    # settings-gated, never auto


class PermissionDecision:
    """Result of a permission check."""

    def __init__(self, allowed: bool, requires_confirmation: bool, reason: str = "") -> None:
        self.allowed = allowed
        self.requires_confirmation = requires_confirmation
        self.reason = reason

    @classmethod
    def allow(cls, reason: str = "") -> "PermissionDecision":
        return cls(True, False, reason)

    @classmethod
    def confirm(cls, reason: str = "") -> "PermissionDecision":
        return cls(True, True, reason)

    @classmethod
    def deny(cls, reason: str = "") -> "PermissionDecision":
        return cls(False, False, reason)


class PermissionManager:
    """Central permission gate.  All tool executions go through here."""

    def __init__(self) -> None:
        self._settings = get_settings()
        # Tool name -> PermissionLevel (overrides default from tool definition)
        self._overrides: Dict[str, PermissionLevel] = {}
        self._load_overrides()

    def _load_overrides(self) -> None:
        perms = self._settings.get("permissions", {})
        for tool_name, level_name in perms.items():
            try:
                self._overrides[tool_name] = PermissionLevel[level_name.upper()]
            except KeyError:
                _LOG.warning("Unknown permission level '%s' for tool '%s'", level_name, tool_name)

    def check(self, tool_name: str, args: Dict[str, Any], default_level: PermissionLevel) -> PermissionDecision:
        """Check if ``tool_name`` with ``args`` is allowed.

        ``default_level`` is the level declared by the tool itself.
        Settings overrides take precedence.
        """
        # Settings override?
        if tool_name in self._overrides:
            effective = self._overrides[tool_name]
        else:
            effective = default_level

        if effective == PermissionLevel.SAFE:
            return PermissionDecision.allow()
        elif effective == PermissionLevel.CONFIRM:
            return PermissionDecision.confirm(f"Tool '{tool_name}' requires confirmation")
        else:  # BLOCKED
            return PermissionDecision.deny(f"Tool '{tool_name}' is blocked by settings")

    def set_gate(self, tool_name: str, level: PermissionLevel) -> None:
        """Persist a permission override for ``tool_name``."""
        self._overrides[tool_name] = level
        self._persist_overrides()

    def is_gated(self, tool_name: str) -> bool:
        """Return True if tool has a non-SAFE effective level."""
        decision = self.check(tool_name, {}, PermissionLevel.SAFE)
        return not decision.allowed or decision.requires_confirmation

    def _persist_overrides(self) -> None:
        data = {name: level.name.lower() for name, level in self._overrides.items()}
        self._settings.set("permissions", data)