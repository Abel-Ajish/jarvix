"""Playwright browser wrapper for jarvix (Phase 6).

Provides a lazy-initialized browser instance (Edge/Chromium via Playwright)
with graceful degradation when no browser is installed.  All browser
operations are async and cancellable via ``ExecContext``.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from jarvix.core.execution import ExecContext
from jarvix.core.logger import get_logger
from jarvix.core.permissions import PermissionLevel
from jarvix.core.tool_registry import Tool, ToolResult, tool

_LOG = get_logger("jarvix.web.browser")

# ---------------------------------------------------------------------------
# Browser management (lazy singleton)
# ---------------------------------------------------------------------------

_BROWSER: Optional["BrowserManager"] = None


@dataclass
class BrowserState:
    """Current state of the active browser session."""

    is_running: bool = False
    current_url: str = ""
    viewport: Tuple[int, int] = (1280, 720)


class BrowserManager:
    """Manages a single Playwright browser + context + page lifecycle."""

    def __init__(
        self,
        *,
        headless: bool = True,
        channel: str = "msedge",
        viewport: Tuple[int, int] = (1280, 720),
        download_path: Optional[Path] = None,
    ) -> None:
        self._headless = headless
        self._channel = channel  # "msedge" for Edge, "chromium" for Chromium
        self._viewport = viewport
        self._download_path = download_path or Path.home() / "Downloads" / "jarvix"
        self._download_path.mkdir(parents=True, exist_ok=True)

        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._state = BrowserState()
        self._download_queue: asyncio.Queue = asyncio.Queue()
        self._active_downloads: Dict[str, Dict[str, Any]] = {}

    async def start(self) -> None:
        """Launch browser, create context and page."""
        if self._browser is not None:
            return

        try:
            from playwright.async_api import async_playwright
        except Exception as e:
            raise RuntimeError(
                "Playwright not installed. Run: pip install playwright"
            ) from e

        self._playwright = await async_playwright().start()

        # Try the requested channel (Edge), fall back to bare Chromium.
        launch_error: Optional[Exception] = None
        for ch in (self._channel, "chromium"):
            try:
                self._browser = await self._playwright.chromium.launch(
                    channel=ch,
                    headless=self._headless,
                )
                _LOG.info("Launched browser via channel '%s'", ch)
                break
            except Exception as e:
                launch_error = e
                _LOG.warning("Channel '%s' launch failed: %s", ch, e)

        if self._browser is None:
            await self._playwright.stop()
            self._playwright = None
            raise RuntimeError(
                f"No browser available. Tried 'msedge' and 'chromium'. "
                f"Last error: {launch_error}. "
                f"Run 'playwright install' in the venv."
            )

        self._context = await self._browser.new_context(
            accept_downloads=True,
            viewport={"width": self._viewport[0], "height": self._viewport[1]},
        )
        self._page = await self._context.new_page()
        self._page.set_default_timeout(30_000)  # 30s default navigation timeout

        # Set up download listener
        self._page.on("download", self._on_download)

        self._state.is_running = True
        _LOG.info("Browser started (downloads to %s)", self._download_path)

    async def stop(self) -> None:
        """Close browser and cleanup."""
        if self._page:
            await self._page.close()
            self._page = None
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        self._state.is_running = False
        _LOG.info("Browser stopped")

    @property
    def is_running(self) -> bool:
        return self._state.is_running

    @property
    def page(self) -> Optional["Page"]:
        """Return the active Playwright page, or None if not started."""
        return self._page

    @property
    def state(self) -> BrowserState:
        return self._state

    @property
    def download_path(self) -> Path:
        return self._download_path

    def _on_download(self, download: "Download") -> None:
        """Internal download event handler."""
        import uuid

        dl_id = str(uuid.uuid4())[:8]
        info = {
            "id": dl_id,
            "download": download,
            "suggested_filename": download.suggested_filename,
            "url": download.url,
            "status": "started",
            "path": None,
            "error": None,
        }
        self._active_downloads[dl_id] = info
        _LOG.info("Download started: %s (%s)", download.suggested_filename, dl_id)

    async def wait_for_download(
        self, dl_id: str, *, timeout: float = 60.0
    ) -> Dict[str, Any]:
        """Wait for a specific download to complete."""
        import asyncio as aio

        async def _wait():
            info = self._active_downloads.get(dl_id)
            if not info:
                return {"error": f"Download {dl_id} not found"}
            download = info["download"]
            try:
                # This blocks until the download completes (or fails)
                path = await download.path()
                final_path = self._download_path / info["suggested_filename"]
                await download.save_as(final_path)
                info["path"] = str(final_path)
                info["status"] = "completed"
                _LOG.info("Download completed: %s -> %s", info["suggested_filename"], final_path)
                return info
            except Exception as e:
                info["status"] = "failed"
                info["error"] = str(e)
                _LOG.error("Download failed: %s", e)
                return info

        return await asyncio.wait_for(_wait(), timeout=timeout)

    def list_downloads(self) -> List[Dict[str, Any]]:
        """Return list of active/completed downloads."""
        result = []
        for info in self._active_downloads.values():
            result.append(
                {
                    "id": info["id"],
                    "filename": info["suggested_filename"],
                    "url": info["url"],
                    "status": info["status"],
                    "path": info["path"],
                    "error": info["error"],
                }
            )
        return result

    def clear_downloads(self) -> None:
        """Clear download history."""
        self._active_downloads.clear()


def get_browser_manager(**kwargs) -> BrowserManager:
    """Get or create the global BrowserManager singleton."""
    global _BROWSER
    if _BROWSER is None:
        _BROWSER = BrowserManager(**kwargs)
    return _BROWSER


def reset_browser_manager() -> None:
    """Reset the singleton (used when settings change)."""
    global _BROWSER
    _BROWSER = None


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


@tool(
    "browser_navigate",
    permission=PermissionLevel.CONFIRM,
    description="Navigate to a URL in the browser",
)
class BrowserNavigateTool(Tool):
    name = "browser_navigate"
    description = "Navigate to a URL in the browser (opens browser if needed)"
    permission = PermissionLevel.CONFIRM

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to navigate to (e.g. 'https://example.com')",
                },
                "wait_until": {
                    "type": "string",
                    "description": "When to consider navigation complete",
                    "default": "domcontentloaded",
                    "enum": ["load", "domcontentloaded", "networkidle"],
                },
                "timeout": {
                    "type": "integer",
                    "description": "Navigation timeout in milliseconds",
                    "default": 30000,
                },
            },
            "required": ["url"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        url = args.get("url", "").strip()
        if not url:
            return ToolResult.failure("url is required")
        if not (url.startswith("http://") or url.startswith("https://")):
            url = "https://" + url

        wait_until = args.get("wait_until", "domcontentloaded")
        timeout = args.get("timeout", 30000)

        ctx.check_cancelled()

        try:
            mgr = get_browser_manager()
            await mgr.start()
        except Exception as e:
            return ToolResult.failure(f"Failed to start browser: {e}")

        page = mgr.page
        if page is None:
            return ToolResult.failure("Browser page not available")

        try:
            response = await asyncio.wait_for(
                page.goto(url, wait_until=wait_until, timeout=timeout),
                timeout=timeout / 1000.0 + 5.0,
            )
            mgr.state.current_url = page.url
            status = response.status if response else "unknown"
            _LOG.info("Navigated to %s (status=%s)", url, status)
            return ToolResult.success(
                f"Navigated to {page.url}",
                data={"url": page.url, "status": status, "title": await page.title()},
            )
        except asyncio.TimeoutError:
            return ToolResult.failure(f"Navigation timeout after {timeout}ms")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            _LOG.exception("Navigation failed")
            return ToolResult.failure(f"Navigation failed: {e}")


@tool(
    "browser_click",
    permission=PermissionLevel.CONFIRM,
    description="Click an element by CSS selector",
)
class BrowserClickTool(Tool):
    name = "browser_click"
    description = "Click an element on the current page by CSS selector"
    permission = PermissionLevel.CONFIRM

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector of the element to click",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in milliseconds",
                    "default": 10000,
                },
                "force": {
                    "type": "boolean",
                    "description": "Force click even if element is not visible",
                    "default": False,
                },
            },
            "required": ["selector"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        selector = args.get("selector", "").strip()
        if not selector:
            return ToolResult.failure("selector is required")

        timeout = args.get("timeout", 10000)
        force = args.get("force", False)

        ctx.check_cancelled()

        try:
            mgr = get_browser_manager()
            if not mgr.is_running:
                return ToolResult.failure("Browser not running. Use browser_navigate first.")
        except Exception as e:
            return ToolResult.failure(f"Browser error: {e}")

        page = mgr.page
        if page is None:
            return ToolResult.failure("No active page")

        try:
            await asyncio.wait_for(
                page.click(selector, timeout=timeout, force=force),
                timeout=timeout / 1000.0 + 2.0,
            )
            _LOG.info("Clicked element: %s", selector)
            return ToolResult.success(
                f"Clicked '{selector}'",
                data={"selector": selector, "url": page.url},
            )
        except asyncio.TimeoutError:
            return ToolResult.failure(f"Element not found or not clickable: {selector}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            _LOG.exception("Click failed")
            return ToolResult.failure(f"Click failed: {e}")


@tool(
    "browser_type",
    permission=PermissionLevel.CONFIRM,
    description="Type text into an element by CSS selector",
)
class BrowserTypeTool(Tool):
    name = "browser_type"
    description = "Type text into an input/textarea element by CSS selector"
    permission = PermissionLevel.CONFIRM

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector of the input element",
                },
                "text": {
                    "type": "string",
                    "description": "Text to type",
                },
                "delay": {
                    "type": "integer",
                    "description": "Delay between keystrokes in ms",
                    "default": 0,
                },
                "clear_first": {
                    "type": "boolean",
                    "description": "Clear the field before typing",
                    "default": True,
                },
            },
            "required": ["selector", "text"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        selector = args.get("selector", "").strip()
        text = args.get("text", "")
        if not selector:
            return ToolResult.failure("selector is required")
        if text == "":
            return ToolResult.failure("text is required")

        delay = args.get("delay", 0)
        clear_first = args.get("clear_first", True)

        ctx.check_cancelled()

        try:
            mgr = get_browser_manager()
            if not mgr.is_running:
                return ToolResult.failure("Browser not running. Use browser_navigate first.")
        except Exception as e:
            return ToolResult.failure(f"Browser error: {e}")

        page = mgr.page
        if page is None:
            return ToolResult.failure("No active page")

        try:
            if clear_first:
                await page.fill(selector, "")
            await page.type(selector, text, delay=delay)
            _LOG.info("Typed into %s", selector)
            return ToolResult.success(
                f"Typed into '{selector}'",
                data={"selector": selector, "length": len(text)},
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            _LOG.exception("Type failed")
            return ToolResult.failure(f"Type failed: {e}")


@tool(
    "browser_scroll",
    permission=PermissionLevel.SAFE,
    description="Scroll the page up/down",
)
class BrowserScrollTool(Tool):
    name = "browser_scroll"
    description = "Scroll the current page vertically"
    permission = PermissionLevel.SAFE

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "description": "Scroll direction",
                    "enum": ["down", "up", "top", "bottom"],
                    "default": "down",
                },
                "amount": {
                    "type": "integer",
                    "description": "Pixels to scroll (for up/down)",
                    "default": 500,
                },
            },
            "required": [],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        direction = args.get("direction", "down")
        amount = args.get("amount", 500)

        ctx.check_cancelled()

        try:
            mgr = get_browser_manager()
            if not mgr.is_running:
                return ToolResult.failure("Browser not running. Use browser_navigate first.")
        except Exception as e:
            return ToolResult.failure(f"Browser error: {e}")

        page = mgr.page
        if page is None:
            return ToolResult.failure("No active page")

        try:
            if direction == "down":
                await page.mouse.wheel(0, amount)
            elif direction == "up":
                await page.mouse.wheel(0, -amount)
            elif direction == "top":
                await page.evaluate("window.scrollTo(0, 0)")
            elif direction == "bottom":
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            else:
                return ToolResult.failure(f"Unknown direction: {direction}")

            _LOG.debug("Scrolled %s", direction)
            return ToolResult.success(
                f"Scrolled {direction}",
                data={"direction": direction, "url": page.url},
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            _LOG.exception("Scroll failed")
            return ToolResult.failure(f"Scroll failed: {e}")


@tool(
    "browser_screenshot",
    permission=PermissionLevel.SAFE,
    description="Capture a screenshot of the current page",
)
class BrowserScreenshotTool(Tool):
    name = "browser_screenshot"
    description = "Take a screenshot of the current page and save to disk"
    permission = PermissionLevel.SAFE

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Output file path (default: auto-generated in Pictures/jarvix)",
                },
                "full_page": {
                    "type": "boolean",
                    "description": "Capture full scrollable page",
                    "default": False,
                },
            },
            "required": [],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        path_str = args.get("path", "")
        full_page = args.get("full_page", False)

        ctx.check_cancelled()

        try:
            mgr = get_browser_manager()
            if not mgr.is_running:
                return ToolResult.failure("Browser not running. Use browser_navigate first.")
        except Exception as e:
            return ToolResult.failure(f"Browser error: {e}")

        page = mgr.page
        if page is None:
            return ToolResult.failure("No active page")

        try:
            if path_str:
                out_path = Path(path_str).expanduser().resolve()
                # Validate: must be within permitted output directories
                permitted_bases = [
                    Path.home().resolve(),
                    manager.download_path.resolve(),
                ]
                if not any(
                    out_path == base or out_path in base.parents or base in out_path.parents
                    for base in permitted_bases
                ):
                    return ToolResult.failure(
                        f"Screenshot path disallowed: {path_str}. "
                        "Must be inside home directory or configured download folder."
                    )
            else:
                pictures = Path.home() / "Pictures" / "jarvix"
                pictures.mkdir(parents=True, exist_ok=True)
                from datetime import datetime
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                out_path = pictures / f"screenshot_{ts}.png"

            await page.screenshot(path=str(out_path), full_page=full_page)
            size = out_path.stat().st_size
            _LOG.info("Screenshot saved: %s (%d bytes)", out_path, size)
            return ToolResult.success(
                f"Screenshot saved to {out_path}",
                data={"path": str(out_path), "size": size, "full_page": full_page},
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            _LOG.exception("Screenshot failed")
            return ToolResult.failure(f"Screenshot failed: {e}")


@tool(
    "browser_download",
    permission=PermissionLevel.CONFIRM,
    description="Trigger a download and wait for completion",
)
class BrowserDownloadTool(Tool):
    name = "browser_download"
    description = "Click a download link/button and wait for the file to complete"
    permission = PermissionLevel.CONFIRM

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector of the download link/button",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Maximum time to wait for download in ms",
                    "default": 60000,
                },
            },
            "required": ["selector"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        selector = args.get("selector", "").strip()
        if not selector:
            return ToolResult.failure("selector is required")

        timeout = args.get("timeout", 60000)

        ctx.check_cancelled()

        try:
            mgr = get_browser_manager()
            if not mgr.is_running:
                return ToolResult.failure("Browser not running. Use browser_navigate first.")
        except Exception as e:
            return ToolResult.failure(f"Browser error: {e}")

        page = mgr.page
        if page is None:
            return ToolResult.failure("No active page")

        try:
            # Trigger download by clicking; Playwright will fire the 'download' event
            # We need to wait for the download event to complete.
            # Use page.expect_download() which waits for a download to start.
            async with page.expect_download(timeout=timeout) as download_info:
                await page.click(selector, timeout=min(timeout, 10000))

            download = await download_info.value
            # Save it
            suggested = download.suggested_filename or "download"
            final_path = mgr.download_path / suggested
            await download.save_as(final_path)

            _LOG.info("Download completed: %s", final_path)
            return ToolResult.success(
                f"Downloaded {suggested} to {final_path}",
                data={
                    "filename": suggested,
                    "path": str(final_path),
                    "size": final_path.stat().st_size,
                    "url": download.url,
                },
            )
        except asyncio.TimeoutError:
            return ToolResult.failure(f"Download did not start within {timeout}ms")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            _LOG.exception("Download failed")
            return ToolResult.failure(f"Download failed: {e}")


@tool(
    "browser_upload",
    permission=PermissionLevel.CONFIRM,
    description="Upload a file to an input[type=file] element",
)
class BrowserUploadTool(Tool):
    name = "browser_upload"
    description = "Set files on an <input type='file'> element for upload"
    permission = PermissionLevel.CONFIRM

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector of the file input element",
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of file paths to upload",
                },
            },
            "required": ["selector", "files"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        selector = args.get("selector", "").strip()
        files = args.get("files", [])
        if not selector:
            return ToolResult.failure("selector is required")
        if not files:
            return ToolResult.failure("files array is required")

        ctx.check_cancelled()

        try:
            mgr = get_browser_manager()
            if not mgr.is_running:
                return ToolResult.failure("Browser not running. Use browser_navigate first.")
        except Exception as e:
            return ToolResult.failure(f"Browser error: {e}")

        page = mgr.page
        if page is None:
            return ToolResult.failure("No active page")

        # Resolve file paths
        resolved: List[str] = []
        for f in files:
            p = Path(f).expanduser()
            if not p.exists():
                return ToolResult.failure(f"File not found: {p}")
            resolved.append(str(p))

        try:
            await page.set_input_files(selector, resolved)
            _LOG.info("Uploaded %d file(s) to %s", len(resolved), selector)
            return ToolResult.success(
                f"Set {len(resolved)} file(s) on '{selector}'",
                data={"selector": selector, "files": resolved},
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            _LOG.exception("Upload failed")
            return ToolResult.failure(f"Upload failed: {e}")


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------

def register_browser_tools(registry) -> None:
    """Register all browser tools."""
    from jarvix.web.browser import (
        BrowserNavigateTool,
        BrowserClickTool,
        BrowserTypeTool,
        BrowserScrollTool,
        BrowserScreenshotTool,
        BrowserDownloadTool,
        BrowserUploadTool,
    )
    for cls in (
        BrowserNavigateTool,
        BrowserClickTool,
        BrowserTypeTool,
        BrowserScrollTool,
        BrowserScreenshotTool,
        BrowserDownloadTool,
        BrowserUploadTool,
    ):
        registry.register(cls.name, cls())