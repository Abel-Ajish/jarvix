"""Tests for the offline command engine."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jarvix.core.events import EventBus
from jarvix.core.execution import ExecContext
from jarvix.core.permissions import PermissionManager
from jarvix.core.tool_registry import ToolRegistry, ToolResult
from jarvix.engine.offline import OfflineCommandEngine


class MockTool:
    """Mock tool for testing."""
    name = "mock_tool"
    description = "A mock tool"

    def schema(self):
        return {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]}

    async def execute(self, args, ctx):
        return ToolResult.success(f"Mock executed with {args['value']}")


@pytest.fixture
def offline_engine() -> OfflineCommandEngine:
    """Create an offline engine with mocked tool registry."""
    event_bus = EventBus()
    tool_registry = MagicMock()
    tool_registry.execute_async = AsyncMock(return_value=ToolResult.success("Mock executed"))

    engine = OfflineCommandEngine(event_bus, tool_registry)
    return engine


class TestOfflineEngine:
    """Test offline engine intent parsing and execution."""

    @pytest.mark.asyncio
    async def test_open_application_intent(self, offline_engine: OfflineCommandEngine) -> None:
        """Test 'open notepad' maps to open_application tool."""
        # We need to check the intent matching
        tool_name, args = offline_engine._match_intent("open notepad")

        assert tool_name == "open_application"
        assert args.get("app_name") == "notepad"

    @pytest.mark.asyncio
    async def test_close_application_intent(self, offline_engine: OfflineCommandEngine) -> None:
        """Test 'close chrome' maps to close_application tool."""
        tool_name, args = offline_engine._match_intent("close chrome")

        assert tool_name == "close_application"
        assert args.get("app_name") == "chrome"

    @pytest.mark.asyncio
    async def test_take_screenshot_intent(self, offline_engine: OfflineCommandEngine) -> None:
        """Test 'take screenshot' maps to take_screenshot tool."""
        tool_name, args = offline_engine._match_intent("take screenshot")

        assert tool_name == "take_screenshot"
        # area is optional and may or may not be set depending on regex match

    @pytest.mark.asyncio
    async def test_create_folder_intent(self, offline_engine: OfflineCommandEngine) -> None:
        """Test 'create folder Documents' maps to create_folder tool."""
        tool_name, args = offline_engine._match_intent("create folder Documents")

        assert tool_name == "create_folder"
        assert args.get("path") == "Documents"

    @pytest.mark.asyncio
    async def test_volume_control_intents(self, offline_engine: OfflineCommandEngine) -> None:
        """Test volume control intents."""
        test_cases = [
            ("set volume to 50", "set_volume", {"level": "50"}),
            ("volume up", "increase_volume", {}),
            ("volume down", "decrease_volume", {}),
            ("mute", "mute", {}),
            ("unmute", "unmute", {}),
        ]

        for text, expected_tool, expected_args in test_cases:
            tool_name, args = offline_engine._match_intent(text)
            assert tool_name == expected_tool, f"Failed for: {text}"
            for k, v in expected_args.items():
                assert args.get(k) == v, f"Arg {k} mismatch for {text}"

    @pytest.mark.asyncio
    async def test_power_control_intents(self, offline_engine: OfflineCommandEngine) -> None:
        """Test power control intents."""
        test_cases = [
            ("lock", "lock_windows", {}),
            ("sleep", "sleep_windows", {}),
            ("shutdown", "shutdown_windows", {}),
            ("restart", "restart_windows", {}),
        ]

        for text, expected_tool, expected_args in test_cases:
            tool_name, args = offline_engine._match_intent(text)
            assert tool_name == expected_tool, f"Failed for: {text}"

    @pytest.mark.asyncio
    async def test_time_date_intents(self, offline_engine: OfflineCommandEngine) -> None:
        """Test time/date intents."""
        tool_name, args = offline_engine._match_intent("what time is it")
        assert tool_name == "get_time"

        tool_name, args = offline_engine._match_intent("what date is it")
        assert tool_name == "get_date"

    @pytest.mark.asyncio
    async def test_open_url_intent(self, offline_engine: OfflineCommandEngine) -> None:
        """Test open URL intents."""
        tool_name, args = offline_engine._match_intent("open https://example.com")
        assert tool_name == "open_url"
        assert args.get("url") == "https://example.com"

        tool_name, args = offline_engine._match_intent("go to example.com")
        assert tool_name == "open_url"
        assert args.get("url") == "example.com"

    @pytest.mark.asyncio
    async def test_clipboard_intents(self, offline_engine: OfflineCommandEngine) -> None:
        """Test clipboard intents."""
        tool_name, args = offline_engine._match_intent("clipboard")
        assert tool_name == "clipboard_read"

        tool_name, args = offline_engine._match_intent("copy to clipboard hello world")
        assert tool_name == "clipboard_write"
        assert args.get("text") == "hello world"

    @pytest.mark.asyncio
    async def test_memory_intents(self, offline_engine: OfflineCommandEngine) -> None:
        """Test memory intents."""
        tool_name, args = offline_engine._match_intent("search memory for python")
        assert tool_name == "memory_search"
        assert args.get("query") == "python"

        tool_name, args = offline_engine._match_intent("remember that I like python")
        assert tool_name == "memory_save"
        assert args.get("fact") == "that I like python"

    @pytest.mark.asyncio
    async def test_no_match_returns_none(self, offline_engine: OfflineCommandEngine) -> None:
        """Test unrecognized commands return None."""
        tool_name, args = offline_engine._match_intent("do something completely random")

        assert tool_name is None
        assert args == {}

    @pytest.mark.asyncio
    async def test_chat_returns_helpful_message_when_no_intent(self, offline_engine: OfflineCommandEngine) -> None:
        """Test chat returns helpful message when no intent matched."""
        from jarvix.engine.ai_engine import ChatResponse

        messages = [{"role": "user", "content": "do something completely random"}]
        exec_context = ExecContext(
            conversation_id="test",
            user_id="test",
            permission_manager=PermissionManager(),
        )

        response = await offline_engine.chat(messages, ctx=exec_context)

        assert isinstance(response, ChatResponse)
        assert "offline" in response.content.lower()
        assert "couldn't understand" in response.content.lower()

    @pytest.mark.asyncio
    async def test_chat_executes_tool_when_intent_matched(self, offline_engine: OfflineCommandEngine) -> None:
        """Test chat executes tool when intent matched."""
        from jarvix.engine.ai_engine import ChatResponse

        messages = [{"role": "user", "content": "open notepad"}]
        exec_context = ExecContext(
            conversation_id="test",
            user_id="test",
            permission_manager=PermissionManager(),
        )

        response = await offline_engine.chat(messages, ctx=exec_context)

        assert isinstance(response, ChatResponse)
        assert "executed" in response.content.lower() or "done" in response.content.lower()

    @pytest.mark.asyncio
    async def test_stream_yields_single_chunk(self, offline_engine: OfflineCommandEngine) -> None:
        """Test stream yields a single chunk with done=True."""
        messages = [{"role": "user", "content": "open notepad"}]
        exec_context = ExecContext(
            conversation_id="test",
            user_id="test",
            permission_manager=PermissionManager(),
        )

        chunks = []
        async for chunk in offline_engine.stream(messages, ctx=exec_context):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert chunks[0].done is True

    @pytest.mark.asyncio
    async def test_tool_call_returns_empty(self, offline_engine: OfflineCommandEngine) -> None:
        """Test tool_call returns empty result (offline engine doesn't do tool calling)."""
        from jarvix.engine.ai_engine import ToolCallResult

        messages = [{"role": "user", "content": "open notepad"}]
        tools = [{"name": "open_application", "description": "Open an app"}]
        exec_context = ExecContext(
            conversation_id="test",
            user_id="test",
            permission_manager=PermissionManager(),
        )

        result = await offline_engine.tool_call(messages, tools, ctx=exec_context)

        assert isinstance(result, ToolCallResult)
        assert result.tool_calls == []

    @pytest.mark.asyncio
    async def test_vision_returns_offline_message(self, offline_engine: OfflineCommandEngine) -> None:
        """Test vision returns offline message."""
        result = await offline_engine.vision(b"fake_image", "describe this")

        assert "requires an online vision model" in result

    @pytest.mark.asyncio
    async def test_structured_output_returns_empty(self, offline_engine: OfflineCommandEngine) -> None:
        """Test structured_output returns empty dict."""
        messages = [{"role": "user", "content": "test"}]
        schema = {"type": "object"}
        exec_context = ExecContext(
            conversation_id="test",
            user_id="test",
            permission_manager=PermissionManager(),
        )

        result = await offline_engine.structured_output(messages, schema, ctx=exec_context)

        assert result == {}

    @pytest.mark.asyncio
    async def test_test_connection_returns_ok(self, offline_engine: OfflineCommandEngine) -> None:
        """Test test_connection returns success."""
        from jarvix.engine.ai_engine import ConnectionTest

        result = await offline_engine.test_connection()

        assert isinstance(result, ConnectionTest)
        assert result.ok is True
        assert "ready" in result.message.lower()

    @pytest.mark.asyncio
    async def test_list_models_returns_offline_model(self, offline_engine: OfflineCommandEngine) -> None:
        """Test list_models returns offline engine model info."""
        from jarvix.engine.ai_engine import ModelInfo

        models = await offline_engine.list_models()

        assert len(models) == 1
        assert isinstance(models[0], ModelInfo)
        assert models[0].id == "offline"
        assert models[0].provider == "offline"
        assert "tools" in models[0].capabilities


if __name__ == "__main__":
    pytest.main([__file__, "-v"])