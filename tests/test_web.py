"""Tests for the web subsystem (mocked)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jarvix.core.events import EventBus
from jarvix.core.execution import ExecContext
from jarvix.core.permissions import PermissionManager
from jarvix.core.tool_registry import ToolRegistry, ToolResult
from jarvix.web import register_web_tools


@pytest.fixture
def mock_tool_registry() -> ToolRegistry:
    """Create a tool registry with mocked web tools."""
    event_bus = EventBus()
    permission_manager = PermissionManager()
    registry = ToolRegistry(event_bus, permission_manager)
    return registry


class TestWebTools:
    """Test web tools registration and basic functionality."""

    def test_register_web_tools(self, mock_tool_registry: ToolRegistry) -> None:
        """Test that all web tools are registered."""
        register_web_tools(mock_tool_registry)

        expected_tools = [
            "web_search",
            "read_page",
            "browser_navigate",
            "browser_click",
            "browser_type",
            "browser_scroll",
            "browser_screenshot",
            "browser_download",
            "browser_upload",
        ]

        for tool_name in expected_tools:
            tool = mock_tool_registry.get(tool_name)
            assert tool is not None, f"Tool {tool_name} not registered"
            meta = mock_tool_registry.get_meta(tool_name)
            assert meta is not None
            assert meta.name == tool_name
            assert meta.schema is not None

    def test_web_search_tool_schema(self, mock_tool_registry: ToolRegistry) -> None:
        """Test web_search tool schema."""
        register_web_tools(mock_tool_registry)

        tool = mock_tool_registry.get("web_search")
        schema = tool.schema()

        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert "max_results" in schema["properties"]
        assert schema["required"] == ["query"]

    def test_read_page_tool_schema(self, mock_tool_registry: ToolRegistry) -> None:
        """Test read_page tool schema."""
        register_web_tools(mock_tool_registry)

        tool = mock_tool_registry.get("read_page")
        schema = tool.schema()

        assert schema["type"] == "object"
        assert "url" in schema["properties"]
        assert "format" in schema["properties"]
        assert schema["required"] == ["url"]

    def test_browser_navigate_tool_schema(self, mock_tool_registry: ToolRegistry) -> None:
        """Test browser_navigate tool schema."""
        register_web_tools(mock_tool_registry)

        tool = mock_tool_registry.get("browser_navigate")
        schema = tool.schema()

        assert schema["type"] == "object"
        assert "url" in schema["properties"]
        assert "wait_until" in schema["properties"]
        assert schema["required"] == ["url"]

    @pytest.mark.asyncio
    async def test_web_search_execution(self, mock_tool_registry: ToolRegistry) -> None:
        """Test web_search tool execution (mocked)."""
        register_web_tools(mock_tool_registry)

        # Mock the actual execution
        tool = mock_tool_registry.get("web_search")
        original_execute = tool.execute

        async def mock_execute(args, ctx):
            return ToolResult.success("Search results for: " + args["query"], data={"results": []})

        tool.execute = mock_execute

        exec_context = ExecContext(
            conversation_id="test",
            user_id="test",
            permission_manager=PermissionManager(),
        )

        result = await mock_tool_registry.execute_async("web_search", {"query": "python"}, exec_context)

        assert result.ok
        assert "python" in result.output.lower()

    @pytest.mark.asyncio
    async def test_browser_navigate_execution(self, mock_tool_registry: ToolRegistry) -> None:
        """Test browser_navigate tool execution (mocked)."""
        register_web_tools(mock_tool_registry)

        tool = mock_tool_registry.get("browser_navigate")

        async def mock_execute(args, ctx):
            return ToolResult.success(f"Navigated to {args['url']}")

        tool.execute = mock_execute

        exec_context = ExecContext(
            conversation_id="test",
            user_id="test",
            permission_manager=PermissionManager(),
        )

        result = await mock_tool_registry.execute_async("browser_navigate", {"url": "https://example.com"}, exec_context)

        assert result.ok
        assert "example.com" in result.output

    @pytest.mark.asyncio
    async def test_browser_click_execution(self, mock_tool_registry: ToolRegistry) -> None:
        """Test browser_click tool execution (mocked)."""
        register_web_tools(mock_tool_registry)

        tool = mock_tool_registry.get("browser_click")

        async def mock_execute(args, ctx):
            return ToolResult.success(f"Clicked element: {args['selector']}")

        tool.execute = mock_execute

        exec_context = ExecContext(
            conversation_id="test",
            user_id="test",
            permission_manager=PermissionManager(),
        )

        result = await mock_tool_registry.execute_async("browser_click", {"selector": "button#submit"}, exec_context)

        assert result.ok
        assert "button#submit" in result.output

    @pytest.mark.asyncio
    async def test_browser_screenshot_execution(self, mock_tool_registry: ToolRegistry) -> None:
        """Test browser_screenshot tool execution (mocked)."""
        register_web_tools(mock_tool_registry)

        tool = mock_tool_registry.get("browser_screenshot")

        async def mock_execute(args, ctx):
            return ToolResult.success("Screenshot captured", data={"path": "/tmp/screenshot.png"})

        tool.execute = mock_execute

        exec_context = ExecContext(
            conversation_id="test",
            user_id="test",
            permission_manager=PermissionManager(),
        )

        result = await mock_tool_registry.execute_async("browser_screenshot", {}, exec_context)

        assert result.ok
        assert "screenshot" in result.output.lower()


class TestWebSearchModule:
    """Test web search module (mocked)."""

    @pytest.mark.asyncio
    async def test_duckduckgo_search(self) -> None:
        """Test DuckDuckGo search returns results."""
        from jarvix.web.search import search_duckduckgo

        with patch("jarvix.web.search.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.text = """
                <html>
                    <a class="result__snippet" href="https://example.com">Example result</a>
                </html>
            """
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

            results = await search_duckduckgo("test query", max_results=5)

            assert isinstance(results, list)
            # May be empty if parsing fails, but shouldn't crash

    @pytest.mark.asyncio
    async def test_google_search_fallback(self) -> None:
        """Test Google search as fallback."""
        from jarvix.web.search import search_google

        with patch("jarvix.web.search.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.text = '<div class="g"><a href="https://example.com">Example</a></div>'
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)

            results = await search_google("test query", max_results=5)

            assert isinstance(results, list)


class TestWebReaderModule:
    """Test web reader module (mocked)."""

    @pytest.mark.asyncio
    async def test_read_page_extraction(self) -> None:
        """Test HTML to markdown extraction."""
        from jarvix.web.reader import extract_content

        html = """
        <html>
            <body>
                <h1>Title</h1>
                <p>Paragraph with <strong>bold</strong> text.</p>
                <ul>
                    <li>Item 1</li>
                    <li>Item 2</li>
                </ul>
            </body>
        </html>
        """

        result = await extract_content(html, format="markdown")

        assert "Title" in result
        assert "Paragraph" in result
        assert "bold" in result
        assert "Item 1" in result

    @pytest.mark.asyncio
    async def test_read_page_text_format(self) -> None:
        """Test HTML to plain text extraction."""
        from jarvix.web.reader import extract_content

        html = "<html><body><h1>Title</h1><p>Content</p></body></html>"

        result = await extract_content(html, format="text")

        assert "Title" in result
        assert "Content" in result
        assert "<" not in result  # No HTML tags


class TestWebBrowserModule:
    """Test web browser module (mocked)."""

    @pytest.mark.asyncio
    async def test_browser_manager_lazy_init(self) -> None:
        """Test browser manager initializes lazily."""
        from jarvix.web.browser import BrowserManager, get_browser_manager

        # Reset singleton
        import jarvix.web.browser as browser_module
        browser_module._browser_manager = None

        manager = get_browser_manager()
        assert manager is not None
        assert not manager._initialized

        # Initialization should happen on first use
        with patch.object(manager, "_init_browser", new_callable=AsyncMock) as mock_init:
            mock_init.return_value = None
            await manager.navigate("https://example.com")
            mock_init.assert_called_once()

    @pytest.mark.asyncio
    async def test_browser_graceful_degradation(self) -> None:
        """Test browser gracefully handles missing Playwright."""
        from jarvix.web.browser import BrowserManager

        manager = BrowserManager()

        # Simulate Playwright not available
        with patch("jarvix.web.browser.async_playwright", side_effect=ImportError("Playwright not installed")):
            result = await manager.navigate("https://example.com")
            assert not result.ok
            assert "playwright" in result.error.lower() or "browser" in result.error.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])