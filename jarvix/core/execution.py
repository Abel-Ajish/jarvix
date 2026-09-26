"""Execution context and cancellation for jarvix.

Every tool execution and AI loop receives an ExecContext that carries
cancellation state.  The emergency stop and voice interrupt set the
cancel_event, which all long-running operations must check.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from jarvix.core.permissions import PermissionManager, PermissionLevel, PermissionDecision


class NoOpPermissionManager:
    """A permissive no-op permission manager for contexts where no real manager is available."""

    def check(self, tool_name: str, args: Dict[str, Any], default_level: PermissionLevel) -> PermissionDecision:
        return PermissionDecision.allow()


class ExecutionCancelled(Exception):
    """Raised when execution is cancelled via emergency stop or voice interrupt."""
    pass


@dataclass
class ExecContext:
    """Context passed to every tool execution and AI call."""

    conversation_id: str = ""
    user_id: str = ""
    permission_manager: Optional[PermissionManager] = field(default=None)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def check_cancelled(self) -> None:
        """Raise ExecutionCancelled if the cancel event is set."""
        if self.cancel_event.is_set():
            raise ExecutionCancelled("Execution cancelled")

    def with_metadata(self, **kwargs: Any) -> "ExecContext":
        """Return a new context with additional metadata (shallow copy)."""
        new_metadata = {**self.metadata, **kwargs}
        # Extract known fields from kwargs
        user_id = kwargs.get("user_id", self.user_id)
        new_ctx = ExecContext(
            conversation_id=self.conversation_id,
            user_id=user_id,
            permission_manager=self.permission_manager,
            cancel_event=self.cancel_event,
            metadata=new_metadata,
        )
        return new_ctx