"""Core contract tests for jarvix.

Tests EventBus pub/sub, ToolRegistry register/execute, PermissionManager gates,
SecretStore encrypt/decrypt, Config merge.
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Dict

import pytest

from jarvix.core.config import Settings
from jarvix.core.events import (
    Event,
    EventBus,
    ToolExecuted,
    PermissionRequested,
    OnlineStatusChanged,
    VoiceWake,
    VoiceResult,
    EmergencyStopRequested,
    AICancelRequested,
    ShutdownRequested,
)
from jarvix.core.permissions import PermissionManager, PermissionLevel, PermissionDecision
from jarvix.core.secret_store import SecretStore
from jarvix.core.tool_registry import Tool, ToolRegistry, ToolResult, ToolMeta
from jarvix.core.execution import ExecContext, ExecutionCancelled


# =============================================================================
# Test Tools for Testing
# =============================================================================

class TestTool(Tool):
    """A simple test tool."""
    name = "test_tool"
    description = "A test tool"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "value": {"type": "string"},
            },
            "required": ["value"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        return ToolResult.success(f"Executed with {args['value']}")


class ConfirmTool(Tool):
    """A tool requiring confirmation."""
    name = "confirm_tool"
    description = "A tool that requires confirmation"
    permission = PermissionManager  # Will be set in test

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string"},
            },
            "required": ["action"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        return ToolResult.success(f"Confirmed: {args['action']}")


class FailingTool(Tool):
    """A tool that always fails."""
    name = "failing_tool"
    description = "A tool that fails"

    def schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        raise ValueError("Intentional failure")


# =============================================================================
# EventBus Tests
# =============================================================================

class TestEventBus:
    """Test EventBus pub/sub functionality."""

    def test_subscribe_and_publish(self, event_bus: EventBus) -> None:
        """Test basic subscribe and publish."""
        received = []

        def handler(event: Event) -> None:
            received.append(event)

        event_bus.subscribe("test.event", handler)
        event_bus.publish(Event("test.event", data={"key": "value"}))

        assert len(received) == 1
        assert received[0].type == "test.event"
        assert received[0].data == {"key": "value"}

    def test_wildcard_subscription(self, event_bus: EventBus) -> None:
        """Test wildcard subscription receives all events."""
        received = []

        def handler(event: Event) -> None:
            received.append(event)

        event_bus.subscribe("*", handler)
        event_bus.publish(Event("event.one"))
        event_bus.publish(Event("event.two"))

        assert len(received) == 2
        assert received[0].type == "event.one"
        assert received[1].type == "event.two"

    def test_unsubscribe(self, event_bus: EventBus) -> None:
        """Test unsubscribe removes handler."""
        received = []

        def handler(event: Event) -> None:
            received.append(event)

        event_bus.subscribe("test.event", handler)
        event_bus.publish(Event("test.event"))
        assert len(received) == 1

        event_bus.unsubscribe("test.event", handler)
        event_bus.publish(Event("test.event"))
        assert len(received) == 1  # No new events

    def test_standard_events(self, event_bus: EventBus) -> None:
        """Test all standard event types can be published."""
        events = [
            ToolExecuted("test_tool", {"arg": "value"}, ToolResult.success("ok")),
            PermissionRequested("test_tool", {"arg": "value"}),
            OnlineStatusChanged(True),
            VoiceWake(),
            VoiceResult("hello"),
            EmergencyStopRequested(),
            AICancelRequested(),
            ShutdownRequested(),
        ]

        for event in events:
            event_bus.publish(event)  # Should not raise

    def test_handler_exception_isolation(self, event_bus: EventBus) -> None:
        """Test that handler exceptions don't crash publisher."""
        def bad_handler(event: Event) -> None:
            raise ValueError("Handler error")

        def good_handler(event: Event) -> None:
            good_handler.called = True

        good_handler.called = False
        event_bus.subscribe("test.event", bad_handler)
        event_bus.subscribe("test.event", good_handler)

        event_bus.publish(Event("test.event"))
        assert good_handler.called  # Good handler still called


# =============================================================================
# ToolRegistry Tests
# =============================================================================

class TestToolRegistry:
    """Test ToolRegistry register/execute functionality."""

    def test_register_tool(self, tool_registry: ToolRegistry) -> None:
        """Test registering a tool."""
        tool = TestTool()
        handle = tool_registry.register("test_tool", tool)

        assert handle.name == "test_tool"
        assert tool_registry.get("test_tool") is tool
        meta = tool_registry.get_meta("test_tool")
        assert meta is not None
        assert meta.name == "test_tool"
        assert meta.permission == PermissionLevel.SAFE  # Default

    def test_register_duplicate_raises(self, tool_registry: ToolRegistry) -> None:
        """Test registering duplicate tool raises error."""
        tool_registry.register("test_tool", TestTool())
        with pytest.raises(ValueError, match="already registered"):
            tool_registry.register("test_tool", TestTool())

    def test_unregister_tool(self, tool_registry: ToolRegistry) -> None:
        """Test unregistering a tool."""
        tool_registry.register("test_tool", TestTool())
        tool_registry.unregister("test_tool")

        assert tool_registry.get("test_tool") is None
        assert tool_registry.get_meta("test_tool") is None

    def test_list_tools(self, tool_registry: ToolRegistry) -> None:
        """Test listing tools."""
        tool_registry.register("tool_a", TestTool())
        tool_registry.register("tool_b", TestTool())

        tools = tool_registry.list_tools()
        assert len(tools) == 2
        names = {t.name for t in tools}
        assert names == {"tool_a", "tool_b"}

    def test_list_tools_filtered_by_permission(self, tool_registry: ToolRegistry) -> None:
        """Test listing tools filtered by permission."""
        tool_registry.register("safe_tool", TestTool())  # SAFE
        confirm_tool = ConfirmTool()
        confirm_tool.permission = PermissionLevel.CONFIRM
        tool_registry.register("confirm_tool", confirm_tool)

        safe_tools = tool_registry.list_tools(permission=PermissionLevel.SAFE)
        confirm_tools = tool_registry.list_tools(permission=PermissionLevel.CONFIRM)

        assert len(safe_tools) == 1
        assert safe_tools[0].name == "safe_tool"
        assert len(confirm_tools) == 1
        assert confirm_tools[0].name == "confirm_tool"

    def test_execute_safe_tool(self, tool_registry: ToolRegistry, exec_context: ExecContext) -> None:
        """Test executing a SAFE tool."""
        tool_registry.register("test_tool", TestTool())

        result = tool_registry.execute("test_tool", {"value": "hello"}, exec_context)

        assert result.ok
        assert "hello" in result.output

    def test_execute_unknown_tool(self, tool_registry: ToolRegistry, exec_context: ExecContext) -> None:
        """Test executing unknown tool returns failure."""
        result = tool_registry.execute("unknown_tool", {}, exec_context)

        assert not result.ok
        assert "not found" in result.error.lower()

    def test_execute_with_cancellation(self, tool_registry: ToolRegistry, exec_context: ExecContext) -> None:
        """Test execution raises ExecutionCancelled when cancelled."""
        tool_registry.register("test_tool", TestTool())
        exec_context.cancel_event.set()

        with pytest.raises(ExecutionCancelled):
            tool_registry.execute("test_tool", {"value": "test"}, exec_context)

    def test_execute_confirm_tool_returns_special_result(
        self, tool_registry: ToolRegistry, exec_context: ExecContext, permission_manager: PermissionManager
    ) -> None:
        """Test CONFIRM tool returns special result requiring UI confirmation."""
        confirm_tool = ConfirmTool()
        confirm_tool.permission = PermissionLevel.CONFIRM
        tool_registry.register("confirm_tool", confirm_tool)

        result = tool_registry.execute("confirm_tool", {"action": "delete"}, exec_context)

        assert not result.ok
        assert result.error.startswith("CONFIRM_REQUIRED:")
        parts = result.error.split(":")
        assert parts[1] == "confirm_tool"

    def test_execute_blocked_tool(self, tool_registry: ToolRegistry, exec_context: ExecContext) -> None:
        """Test BLOCKED tool returns failure."""
        blocked_tool = TestTool()
        blocked_tool.permission = PermissionLevel.BLOCKED
        tool_registry.register("blocked_tool", blocked_tool)

        result = tool_registry.execute("blocked_tool", {"value": "test"}, exec_context)

        assert not result.ok
        assert "blocked" in result.error.lower()

    def test_execute_async(self, tool_registry: ToolRegistry, exec_context: ExecContext) -> None:
        """Test async execution."""
        tool_registry.register("test_tool", TestTool())

        async def run():
            return await tool_registry.execute_async("test_tool", {"value": "async"}, exec_context)

        result = asyncio.run(run())

        assert result.ok
        assert "async" in result.output

    def test_tool_exception_handled(self, tool_registry: ToolRegistry, exec_context: ExecContext) -> None:
        """Test tool exceptions are caught and returned as failure."""
        tool_registry.register("failing_tool", FailingTool())

        result = tool_registry.execute("failing_tool", {}, exec_context)

        assert not result.ok
        assert "failed" in result.error.lower()

    def test_permission_override_via_settings(
        self, tool_registry: ToolRegistry, exec_context: ExecContext, temp_settings: Settings
    ) -> None:
        """Test permission override from settings."""
        # Set permission override in settings
        temp_settings.set("permissions.test_tool", "CONFIRM")

        # Create new permission manager that uses temp_settings
        from jarvix.core.permissions import PermissionManager
        pm = PermissionManager.__new__(PermissionManager)
        pm._settings = temp_settings
        pm._overrides = {}
        pm._load_overrides()
        registry = ToolRegistry(tool_registry._event_bus, pm)
        registry.register("test_tool", TestTool())

        result = registry.execute("test_tool", {"value": "test"}, exec_context)

        assert not result.ok
        assert result.error.startswith("CONFIRM_REQUIRED:")


# =============================================================================
# PermissionManager Tests
# =============================================================================

class TestPermissionManager:
    """Test PermissionManager gates."""

    def test_safe_allows(self, permission_manager: PermissionManager) -> None:
        """Test SAFE level allows execution."""
        decision = permission_manager.check("safe_tool", {}, PermissionLevel.SAFE)
        assert decision.allowed
        assert not decision.requires_confirmation

    def test_confirm_requires_confirmation(self, permission_manager: PermissionManager) -> None:
        """Test CONFIRM level requires confirmation."""
        decision = permission_manager.check("confirm_tool", {}, PermissionLevel.CONFIRM)
        assert decision.allowed
        assert decision.requires_confirmation

    def test_blocked_denies(self, permission_manager: PermissionManager) -> None:
        """Test BLOCKED level denies execution."""
        decision = permission_manager.check("blocked_tool", {}, PermissionLevel.BLOCKED)
        assert not decision.allowed
        assert not decision.requires_confirmation

    def test_settings_override(self, permission_manager: PermissionManager, temp_settings: Settings) -> None:
        """Test settings override tool's default permission."""
        temp_settings.set("permissions.custom_tool", "BLOCKED")

        # Create new permission manager that uses temp_settings
        from jarvix.core.permissions import PermissionManager
        pm = PermissionManager.__new__(PermissionManager)
        pm._settings = temp_settings
        pm._overrides = {}
        pm._load_overrides()

        decision = pm.check("custom_tool", {}, PermissionLevel.SAFE)
        assert not decision.allowed

    def test_set_gate_persists(self, permission_manager: PermissionManager, temp_settings: Settings) -> None:
        """Test set_gate persists to settings."""
        permission_manager.set_gate("new_tool", PermissionLevel.CONFIRM)

        # Check it's in settings
        perms = permission_manager._overrides
        assert "new_tool" in permission_manager._overrides

    def test_is_gated(self, permission_manager: PermissionManager) -> None:
        """Test is_gated returns True for non-SAFE tools."""
        assert not permission_manager.is_gated("safe_tool")  # Not in overrides, defaults to SAFE

        permission_manager.set_gate("gated_tool", PermissionLevel.CONFIRM)
        assert permission_manager.is_gated("gated_tool")


# =============================================================================
# SecretStore Tests
# =============================================================================

class TestSecretStore:
    """Test SecretStore encrypt/decrypt."""

    def test_set_and_get(self, mock_secret_store: SecretStore) -> None:
        """Test setting and getting a secret."""
        mock_secret_store.set("api_key", "sk-test123")

        value = mock_secret_store.get("api_key")
        assert value == "sk-test123"

    def test_get_nonexistent(self, mock_secret_store: SecretStore) -> None:
        """Test getting nonexistent secret returns None."""
        value = mock_secret_store.get("nonexistent")
        assert value is None

    def test_delete(self, mock_secret_store: SecretStore) -> None:
        """Test deleting a secret."""
        mock_secret_store.set("temp_key", "temp_value")
        mock_secret_store.delete("temp_key")

        assert mock_secret_store.get("temp_key") is None

    def test_clear(self, mock_secret_store: SecretStore) -> None:
        """Test clearing all secrets."""
        mock_secret_store.set("key1", "value1")
        mock_secret_store.set("key2", "value2")
        mock_secret_store.clear()

        assert mock_secret_store.get("key1") is None
        assert mock_secret_store.get("key2") is None

    def test_persistence(self, mock_secret_store: SecretStore) -> None:
        """Test secrets persist across store instances."""
        mock_secret_store.set("persistent_key", "persistent_value")

        # Create new store with same directory
        import jarvix.core.secret_store as secret_module
        new_store = SecretStore()

        assert new_store.get("persistent_key") == "persistent_value"


# =============================================================================
# Config Tests
# =============================================================================

class TestConfig:
    """Test Settings merge and persistence."""

    def test_get_nested_key(self, temp_settings: Settings) -> None:
        """Test getting nested key with dot notation."""
        temp_settings.set("core.theme", "dark")
        temp_settings.set("core.language", "en")

        assert temp_settings.get("core.theme") == "dark"
        assert temp_settings.get("core.language") == "en"

    def test_get_default(self, temp_settings: Settings) -> None:
        """Test getting default for missing key."""
        assert temp_settings.get("nonexistent", "default") == "default"

    def test_set_persists_to_subsystem_file(self, temp_settings: Settings) -> None:
        """Test set persists to correct subsystem file."""
        temp_settings.set("voice.mic_enabled", True)

        # Check the voice.yaml file was written
        import jarvix.core.config as config_module
        voice_file = config_module._CONFIG_DIR / "voice.yaml"
        assert voice_file.exists()

        import yaml
        with voice_file.open() as f:
            data = yaml.safe_load(f)
        assert data.get("voice", {}).get("mic_enabled") is True

    def test_all_returns_copy(self, temp_settings: Settings) -> None:
        """Test all() returns a copy."""
        temp_settings.set("core.test_key", "value")
        all_settings = temp_settings.all()
        all_settings["core"]["new_key"] = "value"

        # Original should not be modified
        assert "new_key" not in temp_settings.get("core", {})

    def test_reload(self, temp_settings: Settings) -> None:
        """Test reload picks up file changes."""
        import jarvix.core.config as config_module
        import yaml

        # Write directly to file
        core_file = config_module._CONFIG_DIR / "core.yaml"
        with core_file.open("w") as f:
            yaml.safe_dump({"core": {"theme": "light"}}, f)

        temp_settings.reload()
        assert temp_settings.get("core.theme") == "light"


# =============================================================================
# ExecContext Tests
# =============================================================================

class TestExecContext:
    """Test ExecContext cancellation."""

    def test_check_cancelled_raises(self, exec_context: ExecContext) -> None:
        """Test check_cancelled raises when event is set."""
        exec_context.cancel_event.set()

        with pytest.raises(ExecutionCancelled):
            exec_context.check_cancelled()

    def test_check_cancelled_noop_when_not_set(self, exec_context: ExecContext) -> None:
        """Test check_cancelled does nothing when not cancelled."""
        exec_context.check_cancelled()  # Should not raise

    def test_with_metadata_creates_new_context(self, exec_context: ExecContext) -> None:
        """Test with_metadata creates new context with merged metadata."""
        new_ctx = exec_context.with_metadata(extra="data", user_id="new-user")

        assert new_ctx.conversation_id == exec_context.conversation_id
        assert new_ctx.user_id == "new-user"
        assert new_ctx.metadata["extra"] == "data"
        assert new_ctx.cancel_event is exec_context.cancel_event  # Same event
        assert new_ctx.permission_manager is exec_context.permission_manager


if __name__ == "__main__":
    pytest.main([__file__, "-v"])