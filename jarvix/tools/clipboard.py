"""Clipboard tools for jarvix.

Uses Windows clipboard APIs via ctypes (no admin required).
"""

from __future__ import annotations

import asyncio
import ctypes
from typing import Any, Dict

from jarvix.core.execution import ExecContext
from jarvix.core.logger import get_logger
from jarvix.core.permissions import PermissionLevel
from jarvix.core.tool_registry import Tool, ToolResult, tool

_LOG = get_logger("jarvix.tools.clipboard")

# Win32 clipboard constants
CF_TEXT = 1
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
GHND = GMEM_MOVEABLE
CF_DIB = 8  # Bitmap

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


def _read_clipboard_text() -> str:
    """Read text from the Windows clipboard."""
    if not user32.OpenClipboard(0):
        return ""

    try:
        # Try Unicode first
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if handle:
            ptr = kernel32.GlobalLock(handle)
            if ptr:
                text = ctypes.wchar_p(ptr).value or ""
                kernel32.GlobalUnlock(handle)
                return text

        # Fall back to ANSI text
        handle = user32.GetClipboardData(CF_TEXT)
        if handle:
            ptr = kernel32.GlobalLock(handle)
            if ptr:
                text = ctypes.c_char_p(ptr).value.decode("utf-8", errors="replace")
                kernel32.GlobalUnlock(handle)
                return text

        return ""
    finally:
        user32.CloseClipboard()


def _write_clipboard_text(text: str) -> bool:
    """Write text to the Windows clipboard."""
    if not user32.OpenClipboard(0):
        return False

    try:
        user32.EmptyClipboard()

        # Write Unicode text
        data = text.encode("utf-16-le") + b"\x00\x00"
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            return False

        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            kernel32.GlobalFree(handle)
            return False

        ctypes.memcpy(ptr, data, len(data))
        kernel32.GlobalUnlock(handle)

        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            return False

        return True
    finally:
        user32.CloseClipboard()


@tool("clipboard_read", permission=PermissionLevel.SAFE, description="Read text from the system clipboard")
class ClipboardReadTool(Tool):
    name = "clipboard_read"
    description = "Read the current text content from the system clipboard"
    permission = PermissionLevel.SAFE

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        ctx.check_cancelled()
        try:
            text = await asyncio.get_running_loop().run_in_executor(None, _read_clipboard_text)
            if not text:
                return ToolResult.success("Clipboard is empty")
            return ToolResult.success(text, data={"text": text, "length": len(text)})
        except Exception as e:
            _LOG.exception("Failed to read clipboard")
            return ToolResult.failure(f"Failed to read clipboard: {e}")


@tool("clipboard_write", permission=PermissionLevel.CONFIRM, description="Write text to the system clipboard")
class ClipboardWriteTool(Tool):
    name = "clipboard_write"
    description = "Write text to the system clipboard"
    permission = PermissionLevel.CONFIRM

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to copy to clipboard"},
            },
            "required": ["text"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        text = args.get("text", "")
        if not text:
            return ToolResult.failure("text is required")

        ctx.check_cancelled()
        try:
            ok = await asyncio.get_running_loop().run_in_executor(None, lambda: _write_clipboard_text(text))
            if ok:
                _LOG.info("Clipboard written: %d chars", len(text))
                return ToolResult.success(f"Copied {len(text)} characters to clipboard")
            return ToolResult.failure("Failed to write to clipboard")
        except Exception as e:
            _LOG.exception("Failed to write clipboard")
            return ToolResult.failure(f"Failed to write clipboard: {e}")