"""End-to-end integration tests."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jarvix.core.events import EventBus
from jarvix.core.execution import ExecContext
from jarvix.core.permissions import PermissionManager
from jarvix.core.tool_registry import ToolRegistry, ToolResult
from jarvix.engine.offline import OfflineCommandEngine


@pytest.fixture
def full_system() -> dict:
    """Create a complete system for integration testing."""
    event_bus = EventBus()
    permission_manager = PermissionManager()
    tool_registry = ToolRegistry(event_bus, permission_manager)

    # Register core tools
    from jarvix.tools.system import OpenApplicationTool
    from jarvix.tools.keyboard import KeyboardPressTool, KeyboardHotkeyTool, KeyboardTypeTool
    from jarvix.tools.clipboard import ClipboardReadTool, ClipboardWriteTool
    from jarvix.tools.file import (
        CreateFileTool, ReadFileTool, WriteFileTool,
        CopyFileTool, MoveFileTool, DeleteFileTool,
        CreateFolderTool, DeleteFolderTool, SearchFilesTool,
    )

    for cls in (
        OpenApplicationTool, KeyboardPressTool, KeyboardHotkeyTool, KeyboardTypeTool,
        ClipboardReadTool, ClipboardWriteTool,
        CreateFileTool, ReadFileTool, WriteFileTool,
        CopyFileTool, MoveFileTool, DeleteFileTool,
        CreateFolderTool, DeleteFolderTool, SearchFilesTool,
    ):
        tool_registry.register(cls.name, cls())

    # Create offline engine
    offline_engine = OfflineCommandEngine(event_bus, tool_registry)

    return {
        "event_bus": event_bus,
        "permission_manager": permission_manager,
        "tool_registry": tool_registry,
        "offline_engine": offline_engine,
    }


class TestEndToEnd:
    """End-to-end integration tests."""

    @pytest.mark.asyncio
    async def test_open_notepad_flow(self, full_system: dict) -> None:
        """Test 'open notepad' → intent → tool → result."""
        offline_engine = full_system["offline_engine"]
        tool_registry = full_system["tool_registry"]

        # Mock the open_application tool to avoid actually opening notepad
        original_tool = tool_registry.get("open_application")

        async def mock_execute(args, ctx):
            return ToolResult.success(f"Opened {args['app_name']} (mocked)")

        original_tool.execute = mock_execute

        # Test intent matching
        tool_name, args = offline_engine._match_intent("open notepad")
        assert tool_name == "open_application"
        assert args["app_name"] == "notepad"

        # Test execution through registry
        exec_context = ExecContext(
            conversation_id="test",
            user_id="test",
            permission_manager=full_system["permission_manager"],
        )

        result = await tool_registry.execute_async("open_application", args, exec_context)

        assert result.ok
        assert "notepad" in result.output.lower()

    @pytest.mark.asyncio
    async def test_create_folder_flow(self, full_system: dict) -> None:
        """Test 'create folder Documents' flow."""
        offline_engine = full_system["offline_engine"]
        tool_registry = full_system["tool_registry"]

        original_tool = tool_registry.get("create_folder")

        async def mock_execute(args, ctx):
            return ToolResult.success(f"Created folder: {args['path']} (mocked)")

        original_tool.execute = mock_execute

        tool_name, args = offline_engine._match_intent("create folder Documents")
        assert tool_name == "create_folder"
        assert args["path"] == "Documents"

        exec_context = ExecContext(
            conversation_id="test",
            user_id="test",
            permission_manager=full_system["permission_manager"],
        )

        result = await tool_registry.execute_async("create_folder", args, exec_context)

        assert result.ok
        assert "Documents" in result.output

    @pytest.mark.asyncio
    async def test_volume_control_flow(self, full_system: dict) -> None:
        """Test volume control flow."""
        offline_engine = full_system["offline_engine"]
        tool_registry = full_system["tool_registry"]

        # Mock volume tools
        for tool_name in ["set_volume", "increase_volume", "decrease_volume", "mute", "unmute"]:
            tool = tool_registry.get(tool_name)
            if tool:
                async def mock_execute(args, ctx, tn=tool_name):
                    return ToolResult.success(f"{tn} executed (mocked)")
                tool.execute = mock_execute

        exec_context = ExecContext(
            conversation_id="test",
            user_id="test",
            permission_manager=full_system["permission_manager"],
        )

        test_cases = [
            ("set volume to 50", "set_volume"),
            ("volume up", "increase_volume"),
            ("volume down", "decrease_volume"),
            ("mute", "mute"),
            ("unmute", "unmute"),
        ]

        for text, expected_tool in test_cases:
            tool_name, args = offline_engine._match_intent(text)
            assert tool_name == expected_tool

            result = await tool_registry.execute_async(tool_name, args, exec_context)
            assert result.ok

    @pytest.mark.asyncio
    async def test_file_operations_flow(self, full_system: dict) -> None:
        """Test file operations flow."""
        offline_engine = full_system["offline_engine"]
        tool_registry = full_system["tool_registry"]

        # Mock file tools
        file_tools = {
            "create_file": {"path": "test.txt", "content": "Hello"},
            "read_file": {"path": "test.txt"},
            "write_file": {"path": "test.txt", "content": "World"},
            "delete_file": {"path": "test.txt"},
        }

        for tool_name, mock_args in file_tools.items():
            tool = tool_registry.get(tool_name)
            if tool:
                async def mock_execute(args, ctx, tn=tool_name):
                    return ToolResult.success(f"{tn} executed with {args} (mocked)")
                tool.execute = mock_execute

        exec_context = ExecContext(
            conversation_id="test",
            user_id="test",
            permission_manager=full_system["permission_manager"],
        )

        test_cases = [
            ("create file test.txt content Hello", "create_file"),
            ("read file test.txt", "read_file"),
            ("write to test.txt content World", "write_file"),
            ("delete file test.txt", "delete_file"),
        ]

        for text, expected_tool in test_cases:
            tool_name, args = offline_engine._match_intent(text)
            assert tool_name == expected_tool

            result = await tool_registry.execute_async(tool_name, args, exec_context)
            assert result.ok

    @pytest.mark.asyncio
    async def test_keyboard_flow(self, full_system: dict) -> None:
        """Test keyboard operations flow."""
        offline_engine = full_system["offline_engine"]
        tool_registry = full_system["tool_registry"]

        keyboard_tools = ["keyboard_press", "keyboard_hotkey", "keyboard_type"]

        for tool_name in keyboard_tools:
            tool = tool_registry.get(tool_name)
            if tool:
                async def mock_execute(args, ctx, tn=tool_name):
                    return ToolResult.success(f"{tn} executed (mocked)")
                tool.execute = mock_execute

        exec_context = ExecContext(
            conversation_id="test",
            user_id="test",
            permission_manager=full_system["permission_manager"],
        )

        test_cases = [
            ("press enter", "keyboard_press", {"key": "enter"}),
            ("hotkey ctrl c", "keyboard_hotkey", {"keys": ["ctrl", "c"]}),
            ("type hello world", "keyboard_type", {"text": "hello world"}),
        ]

        for text, expected_tool, expected_args in test_cases:
            tool_name, args = offline_engine._match_intent(text)
            assert tool_name == expected_tool
            for k, v in expected_args.items():
                assert args.get(k) == v

            result = await tool_registry.execute_async(tool_name, args, exec_context)
            assert result.ok

    @pytest.mark.asyncio
    async def test_clipboard_flow(self, full_system: dict) -> None:
        """Test clipboard operations flow."""
        offline_engine = full_system["offline_engine"]
        tool_registry = full_system["tool_registry"]

        clipboard_tools = ["clipboard_read", "clipboard_write"]

        for tool_name in clipboard_tools:
            tool = tool_registry.get(tool_name)
            if tool:
                async def mock_execute(args, ctx, tn=tool_name):
                    return ToolResult.success(f"{tn} executed (mocked)")
                tool.execute = mock_execute

        exec_context = ExecContext(
            conversation_id="test",
            user_id="test",
            permission_manager=full_system["permission_manager"],
        )

        # clipboard read
        tool_name, args = offline_engine._match_intent("clipboard")
        assert tool_name == "clipboard_read"
        result = await tool_registry.execute_async(tool_name, args, exec_context)
        assert result.ok

        # clipboard write
        tool_name, args = offline_engine._match_intent("copy to clipboard hello")
        assert tool_name == "clipboard_write"
        assert args["text"] == "hello"
        result = await tool_registry.execute_async(tool_name, args, exec_context)
        assert result.ok

    @pytest.mark.asyncio
    async def test_power_control_flow(self, full_system: dict) -> None:
        """Test power control flow."""
        offline_engine = full_system["offline_engine"]
        tool_registry = full_system["tool_registry"]

        power_tools = ["lock_windows", "sleep_windows", "shutdown_windows", "restart_windows"]

        for tool_name in power_tools:
            tool = tool_registry.get(tool_name)
            if tool:
                async def mock_execute(args, ctx, tn=tool_name):
                    return ToolResult.success(f"{tn} executed (mocked)")
                tool.execute = mock_execute

        exec_context = ExecContext(
            conversation_id="test",
            user_id="test",
            permission_manager=full_system["permission_manager"],
        )

        test_cases = [
            ("lock", "lock_windows"),
            ("sleep", "sleep_windows"),
            ("shutdown", "shutdown_windows"),
            ("restart", "restart_windows"),
        ]

        for text, expected_tool in test_cases:
            tool_name, args = offline_engine._match_intent(text)
            assert tool_name == expected_tool

            result = await tool_registry.execute_async(tool_name, args, exec_context)
            assert result.ok

    @pytest.mark.asyncio
    async def test_time_date_flow(self, full_system: dict) -> None:
        """Test time/date flow."""
        offline_engine = full_system["offline_engine"]
        tool_registry = full_system["tool_registry"]

        time_tools = ["get_time", "get_date"]

        for tool_name in time_tools:
            tool = tool_registry.get(tool_name)
            if tool:
                async def mock_execute(args, ctx, tn=tool_name):
                    return ToolResult.success(f"{tn} executed (mocked)")
                tool.execute = mock_execute

        exec_context = ExecContext(
            conversation_id="test",
            user_id="test",
            permission_manager=full_system["permission_manager"],
        )

        tool_name, args = offline_engine._match_intent("what time is it")
        assert tool_name == "get_time"
        result = await tool_registry.execute_async(tool_name, args, exec_context)
        assert result.ok

        tool_name, args = offline_engine._match_intent("what date is it")
        assert tool_name == "get_date"
        result = await tool_registry.execute_async(tool_name, args, exec_context)
        assert result.ok

    @pytest.mark.asyncio
    async def test_offline_chat_flow(self, full_system: dict) -> None:
        """Test full offline chat flow."""
        offline_engine = full_system["offline_engine"]

        messages = [{"role": "user", "content": "open notepad"}]
        exec_context = ExecContext(
            conversation_id="test",
            user_id="test",
            permission_manager=full_system["permission_manager"],
        )

        # Mock the tool execution
        tool_registry = full_system["tool_registry"]
        original_tool = tool_registry.get("open_application")

        async def mock_execute(args, ctx):
            return ToolResult.success("Opened notepad (mocked)")

        original_tool.execute = mock_execute

        response = await offline_engine.chat(messages, ctx=exec_context)

        assert "notepad" in response.content.lower() or "opened" in response.content.lower()

    @pytest.mark.asyncio
    async def test_offline_chat_unknown_command(self, full_system: dict) -> None:
        """Test offline chat with unknown command."""
        offline_engine = full_system["offline_engine"]

        messages = [{"role": "user", "content": "do something completely unknown"}]
        exec_context = ExecContext(
            conversation_id="test",
            user_id="test",
            permission_manager=full_system["permission_manager"],
        )

        response = await offline_engine.chat(messages, ctx=exec_context)

        assert "offline" in response.content.lower()
        assert "couldn't understand" in response.content.lower()

    @pytest.mark.asyncio
    async def test_emergency_stop_cancels_execution(self, full_system: dict) -> None:
        """Test emergency stop cancels execution."""
        from jarvix.core.execution import ExecutionCancelled

        tool_registry = full_system["tool_registry"]
        exec_context = ExecContext(
            conversation_id="test",
            user_id="test",
            permission_manager=full_system["permission_manager"],
        )

        # Set cancellation
        exec_context.cancel_event.set()

        # Try to execute a tool
        with pytest.raises(ExecutionCancelled):
            await tool_registry.execute_async("open_application", {"app_name": "notepad"}, exec_context)


class TestPermissionGates:
    """Test permission gates in integration."""

    @pytest.mark.asyncio
    async def test_safe_tool_auto_executes(self, full_system: dict) -> None:
        """Test SAFE tools execute without confirmation."""
        tool_registry = full_system["tool_registry"]
        exec_context = ExecContext(
            conversation_id="test",
            user_id="test",
            permission_manager=full_system["permission_manager"],
        )

        # open_application is SAFE
        tool = tool_registry.get("open_application")
        assert tool.permission.value == 1  # SAFE

        # Mock execute
        async def mock_execute(args, ctx):
            return ToolResult.success("Opened (mocked)")
        tool.execute = mock_execute

        result = await tool_registry.execute_async("open_application", {"app_name": "notepad"}, exec_context)

        assert result.ok
        assert "CONFIRM_REQUIRED" not in result.error

    @pytest.mark.asyncio
    async def test_confirm_tool_requires_confirmation(self, full_system: dict) -> None:
        """Test CONFIRM tools return confirmation required."""
        tool_registry = full_system["tool_registry"]
        exec_context = ExecContext(
            conversation_id="test",
            user_id="test",
            permission_manager=full_system["permission_manager"],
        )

        # delete_file is CONFIRM
        tool = tool_registry.get("delete_file")
        assert tool.permission.value == 2  # CONFIRM

        async def mock_execute(args, ctx):
            return ToolResult.success("Deleted (mocked)")
        tool.execute = mock_execute

        result = await tool_registry.execute_async("delete_file", {"path": "test.txt"}, exec_context)

        assert not result.ok
        assert result.error.startswith("CONFIRM_REQUIRED:")

    @pytest.mark.asyncio
    async def test_blocked_tool_denied(self, full_system: dict) -> None:
        """Test BLOCKED tools are denied."""
        tool_registry = full_system["tool_registry"]
        exec_context = ExecContext(
            conversation_id="test",
            user_id="test",
            permission_manager=full_system["permission_manager"],
        )

        # Create a blocked tool
        from jarvix.core.tool_registry import Tool
        from jarvix.core.permissions import PermissionLevel

        class BlockedTool(Tool):
            name = "blocked_tool"
            description = "A blocked tool"
            permission = PermissionLevel.BLOCKED

            def schema(self):
                return {"type": "object", "properties": {}}

            async def execute(self, args, ctx):
                return ToolResult.success("Done")

        tool_registry.register("blocked_tool", BlockedTool())

        result = await tool_registry.execute_async("blocked_tool", {}, exec_context)

        assert not result.ok
        assert "blocked" in result.error.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])