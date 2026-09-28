"""Tool registry — the spine of jarvix.

Every capability (Windows control, file ops, web, vision, plugins) registers
as a Tool here.  Both the online AI and the offline command engine route
their tool calls through this registry, which gates via PermissionManager.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type, get_type_hints

from jarvix.core.events import EventBus, ToolExecuted
from jarvix.core.logger import get_logger
from jarvix.core.permissions import PermissionLevel, PermissionManager, PermissionDecision
from jarvix.core.execution import ExecContext, ExecutionCancelled, NoOpPermissionManager

_LOG = get_logger("jarvix.tool_registry")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ToolResult:
    """Result of a tool execution."""
    ok: bool
    output: Optional[str] = None
    error: Optional[str] = None
    data: Optional[Any] = None

    @classmethod
    def success(cls, output: str = "", data: Any = None) -> "ToolResult":
        return cls(True, output=output, data=data)

    @classmethod
    def failure(cls, error: str) -> "ToolResult":
        return cls(False, error=error)


@dataclass
class ToolMeta:
    """Metadata for a registered tool (for listing)."""
    name: str
    description: str
    permission: PermissionLevel
    schema: Dict[str, Any] = field(default_factory=dict)


class Tool(ABC):
    """Base class for all tools.

    Subclasses must define:
      - name: unique identifier
      - description: human-readable description
      - permission: PermissionLevel
      - schema(): JSON schema for arguments
      - execute(): implementation
    """

    name: str
    description: str
    permission: PermissionLevel = PermissionLevel.SAFE

    @abstractmethod
    def schema(self) -> Dict[str, Any]:
        """Return JSON schema for tool arguments."""
        ...

    @abstractmethod
    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        """Execute the tool with given arguments."""
        ...


class ToolHandle:
    """Handle returned when a tool is registered."""

    def __init__(self, name: str, registry: "ToolRegistry") -> None:
        self.name = name
        self._registry = registry

    def unregister(self) -> None:
        self._registry.unregister(self.name)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class ToolRegistry:
    """Central registry for all tools.

    - Tools register themselves via @tool decorator or register().
    - All execution goes through execute(), which checks permissions.
    - Both online AI and offline engine use the SAME registry.
    """

    def __init__(self, event_bus: EventBus, permission_manager: Optional[PermissionManager] = None) -> None:
        self._event_bus = event_bus
        self._permission_manager = permission_manager or NoOpPermissionManager()
        self._tools: Dict[str, Tool] = {}
        self._meta: Dict[str, ToolMeta] = {}

    def register(
        self,
        name: str,
        tool: Tool,
        *,
        permission: Optional[PermissionLevel] = None,
    ) -> ToolHandle:
        """Register a tool instance.

        If ``permission`` is provided, it overrides the tool's declared level.
        """
        if name in self._tools:
            raise ValueError(f"Tool '{name}' already registered")

        self._tools[name] = tool
        self._meta[name] = ToolMeta(
            name=name,
            description=tool.description,
            permission=permission or tool.permission,
            schema=tool.schema(),
        )
        _LOG.info("Registered tool: %s (permission=%s)", name, self._meta[name].permission.name)
        return ToolHandle(name, self)

    def unregister(self, name: str) -> None:
        if name in self._tools:
            del self._tools[name]
            del self._meta[name]
            _LOG.info("Unregistered tool: %s", name)

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def get_meta(self, name: str) -> Optional[ToolMeta]:
        return self._meta.get(name)

    def list_tools(self, *, permission: Optional[PermissionLevel] = None) -> List[ToolMeta]:
        """List all tools, optionally filtered by permission level."""
        result = list(self._meta.values())
        if permission:
            result = [m for m in result if m.permission == permission]
        return result

    def execute(self, name: str, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        """Execute a tool, enforcing permissions and cancellation.

        This is the SINGLE execution path for ALL tool calls (online and offline).
        """
        tool = self._tools.get(name)
        if not tool:
            return ToolResult.failure(f"Tool '{name}' not found")

        # Check cancellation BEFORE permission (emergency stop must work)
        if ctx.cancel_event.is_set():
            raise ExecutionCancelled("Execution cancelled")

        # Permission check
        default_level = tool.permission
        decision = self._permission_manager.check(name, args, default_level)

        if not decision.allowed:
            return ToolResult.failure(decision.reason or f"Tool '{name}' blocked by permissions")

        if decision.requires_confirmation:
            # For CONFIRM tools, the UI must show a dialog.  The tool itself
            # cannot block here (async).  We raise a special result that the
            # caller (chat loop) must handle by showing the dialog and re-trying.
            return ToolResult.failure(
                f"CONFIRM_REQUIRED:{name}:{json.dumps(args)}:{decision.reason}"
            )

        # Execute the tool
        try:
            if asyncio.iscoroutinefunction(tool.execute):
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    # No event loop running — safe to create one
                    loop = None
                if loop is not None and loop.is_running():
                    # Already in async context - delegate to async path
                    future = asyncio.run_coroutine_threadsafe(tool.execute(args, ctx), loop)
                    result = future.result(timeout=30.0)
                else:
                    result = asyncio.run(tool.execute(args, ctx))
            else:
                result = tool.execute(args, ctx)
        except ExecutionCancelled:
            raise
        except Exception as e:
            _LOG.exception("Tool '%s' raised exception", name)
            return ToolResult.failure(f"Tool '{name}' failed: {e}")

        # Publish event for logging / UI
        self._event_bus.publish(ToolExecuted(name, args, result))

        return result

    async def execute_async(self, name: str, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        """Async version of execute()."""
        tool = self._tools.get(name)
        if not tool:
            return ToolResult.failure(f"Tool '{name}' not found")

        if ctx.cancel_event.is_set():
            raise ExecutionCancelled("Execution cancelled")

        default_level = tool.permission
        decision = self._permission_manager.check(name, args, default_level)

        if not decision.allowed:
            return ToolResult.failure(decision.reason or f"Tool '{name}' blocked by permissions")

        if decision.requires_confirmation:
            return ToolResult.failure(
                f"CONFIRM_REQUIRED:{name}:{json.dumps(args)}:{decision.reason}"
            )

        try:
            result = await tool.execute(args, ctx)
        except ExecutionCancelled:
            raise
        except Exception as e:
            _LOG.exception("Tool '%s' raised exception", name)
            return ToolResult.failure(f"Tool '{name}' failed: {e}")

        self._event_bus.publish(ToolExecuted(name, args, result))
        return result


# ---------------------------------------------------------------------------
# Decorator for self-registration
# ---------------------------------------------------------------------------

def tool(
    name: str,
    *,
    permission: PermissionLevel = PermissionLevel.SAFE,
    description: str = "",
) -> Callable[[Type[Tool]], Type[Tool]]:
    """Class decorator to register a Tool subclass.

    Usage:
        @tool("open_application", permission=PermissionLevel.SAFE)
        class OpenApplicationTool(Tool):
            ...
    """
    def decorator(cls: Type[Tool]) -> Type[Tool]:
        cls.name = name
        cls.description = description or cls.__doc__ or ""
        cls.permission = permission
        return cls
    return decorator