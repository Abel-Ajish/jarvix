"""Tests for the vision subsystem (mocked)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jarvix.core.events import EventBus
from jarvix.core.execution import ExecContext
from jarvix.core.permissions import PermissionManager
from jarvix.core.tool_registry import ToolRegistry, ToolResult
from jarvix.vision import register_vision_tools


@pytest.fixture
def mock_tool_registry() -> ToolRegistry:
    """Create a tool registry with mocked vision tools."""
    event_bus = EventBus()
    permission_manager = PermissionManager()
    registry = ToolRegistry(event_bus, permission_manager)
    return registry


class TestVisionTools:
    """Test vision tools registration and basic functionality."""

    def test_register_vision_tools(self, mock_tool_registry: ToolRegistry) -> None:
        """Test that all vision tools are registered."""
        register_vision_tools(mock_tool_registry)

        expected_tools = [
            "screen_capture",
            "analyze_screen",
            "find_ui_element",
            "read_screen_text",
            "vision_describe",
            "list_monitors",
        ]

        for tool_name in expected_tools:
            tool = mock_tool_registry.get(tool_name)
            assert tool is not None, f"Tool {tool_name} not registered"
            meta = mock_tool_registry.get_meta(tool_name)
            assert meta is not None
            assert meta.name == tool_name

    def test_screen_capture_tool_schema(self, mock_tool_registry: ToolRegistry) -> None:
        """Test screen_capture tool schema."""
        register_vision_tools(mock_tool_registry)

        tool = mock_tool_registry.get("screen_capture")
        schema = tool.schema()

        assert schema["type"] == "object"
        assert "monitor" in schema["properties"]
        assert "region" in schema["properties"]
        assert "save_path" in schema["properties"]

    def test_analyze_screen_tool_schema(self, mock_tool_registry: ToolRegistry) -> None:
        """Test analyze_screen tool schema."""
        register_vision_tools(mock_tool_registry)

        tool = mock_tool_registry.get("analyze_screen")
        schema = tool.schema()

        assert schema["type"] == "object"
        assert "prompt" in schema["properties"]
        assert "monitor" in schema["properties"]
        assert schema["required"] == ["prompt"]

    def test_find_ui_element_tool_schema(self, mock_tool_registry: ToolRegistry) -> None:
        """Test find_ui_element tool schema."""
        register_vision_tools(mock_tool_registry)

        tool = mock_tool_registry.get("find_ui_element")
        schema = tool.schema()

        assert schema["type"] == "object"
        assert "description" in schema["properties"]
        assert "monitor" in schema["properties"]
        assert schema["required"] == ["description"]

    @pytest.mark.asyncio
    async def test_screen_capture_execution(self, mock_tool_registry: ToolRegistry) -> None:
        """Test screen_capture tool execution (mocked)."""
        register_vision_tools(mock_tool_registry)

        tool = mock_tool_registry.get("screen_capture")

        async def mock_execute(args, ctx):
            return ToolResult.success("Screenshot captured", data={"path": "/tmp/screen.png", "size": [1920, 1080]})

        tool.execute = mock_execute

        exec_context = ExecContext(
            conversation_id="test",
            user_id="test",
            permission_manager=PermissionManager(),
        )

        result = await mock_tool_registry.execute_async("screen_capture", {"monitor": 0}, exec_context)

        assert result.ok
        assert "screenshot" in result.output.lower()
        assert "path" in result.data

    @pytest.mark.asyncio
    async def test_list_monitors_execution(self, mock_tool_registry: ToolRegistry) -> None:
        """Test list_monitors tool execution (mocked)."""
        register_vision_tools(mock_tool_registry)

        tool = mock_tool_registry.get("list_monitors")

        async def mock_execute(args, ctx):
            return ToolResult.success("Monitors listed", data={
                "monitors": [
                    {"index": 0, "width": 1920, "height": 1080, "is_primary": True},
                    {"index": 1, "width": 2560, "height": 1440, "is_primary": False},
                ]
            })

        tool.execute = mock_execute

        exec_context = ExecContext(
            conversation_id="test",
            user_id="test",
            permission_manager=PermissionManager(),
        )

        result = await mock_tool_registry.execute_async("list_monitors", {}, exec_context)

        assert result.ok
        assert "monitors" in result.data
        assert len(result.data["monitors"]) == 2


class TestVisionCaptureModule:
    """Test vision capture module (mocked)."""

    @pytest.mark.asyncio
    async def test_capture_screen_bytes(self) -> None:
        """Test capturing screen returns bytes."""
        from jarvix.vision.capture import capture_screen_bytes
        from jarvix.vision.capture import image_to_bytes

        with patch("jarvix.vision.capture.capture_screen", return_value=MagicMock()) as mock_capture:
            mock_capture.return_value = MagicMock()
            with patch("jarvix.vision.capture.image_to_bytes", return_value=b"fake_image_bytes"):
                result = await capture_screen_bytes(monitor_index=0)

                assert result == b"fake_image_bytes"
                mock_capture.assert_called_once()

    @pytest.mark.asyncio
    async def test_capture_screen_fallback(self) -> None:
        """Test fallback to PIL when mss fails."""
        from jarvix.vision.capture import capture_screen_bytes

        with patch("jarvix.vision.capture._capture_screen_sync") as mock_sync:
            mock_sync.return_value = MagicMock()
            with patch("jarvix.vision.capture.image_to_bytes", return_value=b"pil_image_bytes"):
                result = await capture_screen_bytes(monitor_index=0)
                assert result == b"pil_image_bytes"

    @pytest.mark.asyncio
    async def test_get_monitors(self) -> None:
        """Test getting monitor information."""
        from jarvix.vision.capture import get_monitors, MonitorInfo

        with patch("jarvix.vision.capture._get_monitors_mss") as mock_mss:
            mock_mss.return_value = [
                MonitorInfo(index=0, left=0, top=0, width=1920, height=1080, is_primary=True),
                MonitorInfo(index=1, left=1920, top=0, width=2560, height=1440, is_primary=False),
            ]

            monitors = get_monitors()

            assert len(monitors) == 2
            assert monitors[0].is_primary
            assert monitors[1].width == 2560


class TestOnlineVisionModule:
    """Test online vision module (mocked)."""

    @pytest.mark.asyncio
    async def test_vision_analyze(self) -> None:
        """Test vision analysis with mocked AI engine."""
        from jarvix.vision.online_vision import vision_analyze, VisionResult

        mock_result = VisionResult.success("This is a screenshot of a desktop")
        mock_engine = MagicMock()
        mock_engine.analyze = AsyncMock(return_value=mock_result)
        mock_engine.is_available.return_value = True

        with patch("jarvix.vision.online_vision.get_online_vision", return_value=mock_engine):
            result = await vision_analyze(b"fake_image", "What do you see?")

            assert isinstance(result, VisionResult)
            assert "desktop" in result.text.lower()

    @pytest.mark.asyncio
    async def test_vision_is_available(self) -> None:
        """Test vision availability check."""
        from jarvix.vision.online_vision import vision_is_available, OnlineVision

        mock_engine = MagicMock()
        mock_engine.is_available.return_value = True

        with patch("jarvix.vision.online_vision.get_online_vision", return_value=mock_engine):
            available = vision_is_available()

            assert available is True

    @pytest.mark.asyncio
    async def test_encode_image_base64(self) -> None:
        """Test base64 encoding of image."""
        from jarvix.vision.online_vision import encode_image_base64

        # Use properly padded base64 data
        image_bytes = b"\x89PNG\r\n\x1a\n"
        encoded = encode_image_base64(image_bytes)

        assert isinstance(encoded, str)
        assert encoded.startswith("data:image/png;base64,")


class TestUIUnderstandingModule:
    """Test UI understanding module (mocked)."""

    @pytest.mark.asyncio
    async def test_detect_ui_elements(self) -> None:
        """Test UI element detection."""
        from jarvix.vision.ui_understanding import detect_ui_elements, UIAnalysisResult, UIElementType
        from jarvix.vision.online_vision import vision_analyze, vision_is_available, VisionResult

        mock_vision_result = VisionResult.success('[{"type": "button", "bbox": {"left": 100, "top": 100, "right": 200, "bottom": 150}, "text": "Click me", "confidence": 0.9}]')

        with patch("jarvix.vision.ui_understanding.vision_is_available", return_value=True):
            with patch("jarvix.vision.ui_understanding.vision_analyze", new_callable=AsyncMock, return_value=mock_vision_result):
                result = await detect_ui_elements(b"fake_image")

                assert isinstance(result, UIAnalysisResult)
                assert len(result.elements) == 1
                assert result.elements[0].element_type == UIElementType.BUTTON
                assert result.elements[0].text == "Click me"

    @pytest.mark.asyncio
    async def test_find_ui_element(self) -> None:
        """Test finding specific UI element."""
        from jarvix.vision.ui_understanding import find_ui_element
        from jarvix.vision.online_vision import vision_analyze, vision_is_available, VisionResult

        mock_vision_result = VisionResult.success('{"type": "button", "bbox": {"left": 100, "top": 100, "right": 200, "bottom": 150}, "text": "Submit", "confidence": 0.95, "found": true}')

        with patch("jarvix.vision.ui_understanding.vision_is_available", return_value=True):
            with patch("jarvix.vision.ui_understanding.vision_analyze", new_callable=AsyncMock, return_value=mock_vision_result):
                element = await find_ui_element(b"fake_image", "submit button")

                assert element is not None
                assert element.text == "Submit"

    @pytest.mark.asyncio
    async def test_extract_screen_text(self) -> None:
        """Test OCR text extraction."""
        from jarvix.vision.ui_understanding import extract_screen_text
        from jarvix.vision.online_vision import vision_analyze, vision_is_available, VisionResult

        mock_vision_result = VisionResult.success('[{"text": "Hello World"}]')

        with patch("jarvix.vision.ui_understanding.vision_is_available", return_value=True):
            with patch("jarvix.vision.ui_understanding.vision_analyze", new_callable=AsyncMock, return_value=mock_vision_result):
                text = await extract_screen_text(b"fake_image")

                assert len(text) == 1
        assert text[0]["text"] == "Hello World"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])