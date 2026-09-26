"""Web subsystem for jarvix (Phase 6).

Provides:
  - ``browser``  — Playwright wrapper (Edge/Chromium) with lazy init, graceful
                   degradation when no browser is installed.
  - ``search``   — DuckDuckGo HTML search with optional Google fallback.
  - ``reader``   — HTML → readable markdown/text extraction.
  - ``downloads``— Active download tracking, progress events, cancellation.
  - ``ui_panel`` — Web settings panel registered into the UI extension points.

Importing this package also registers the web settings tab.
"""

from __future__ import annotations

from jarvix.web import browser, search, reader, downloads, ui_panel

__all__ = ["browser", "search", "reader", "downloads", "ui_panel"]


def register_web_tools(registry) -> None:
    """Register all web tools into a ``ToolRegistry``.

    Importing this function also imports the tool modules so the ``@tool``
    decorators run and the classes become available.
    """
    # Importing the tool modules triggers @tool decoration; the classes are
    # then instantiated and registered explicitly so callers control the
    # registration order.
    from jarvix.web.browser import (
        BrowserNavigateTool,
        BrowserClickTool,
        BrowserTypeTool,
        BrowserScrollTool,
        BrowserScreenshotTool,
        BrowserDownloadTool,
        BrowserUploadTool,
    )
    from jarvix.web.search import WebSearchTool
    from jarvix.web.reader import ReadPageTool

    for cls in (
        WebSearchTool,
        ReadPageTool,
        BrowserNavigateTool,
        BrowserClickTool,
        BrowserTypeTool,
        BrowserScrollTool,
        BrowserScreenshotTool,
        BrowserDownloadTool,
        BrowserUploadTool,
    ):
        registry.register(cls.name, cls())