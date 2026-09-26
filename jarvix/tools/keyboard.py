"""Keyboard input tools for jarvix.

Uses pyautogui for keyboard simulation. Works without admin rights.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from jarvix.core.execution import ExecContext
from jarvix.core.logger import get_logger
from jarvix.core.permissions import PermissionLevel
from jarvix.core.tool_registry import Tool, ToolResult, tool

_LOG = get_logger("jarvix.tools.keyboard")

try:
    import pyautogui
    _HAS_PYAUTOGUI = True
except ImportError:
    pyautogui = None
    _HAS_PYAUTOGUI = False


@tool("keyboard_press", permission=PermissionLevel.SAFE, description="Press a single key")
class KeyboardPressTool(Tool):
    name = "keyboard_press"
    description = "Press a single key (e.g. 'enter', 'esc', 'tab', 'backspace')"
    permission = PermissionLevel.SAFE

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Key to press (e.g. 'enter', 'esc', 'tab')"},
                "presses": {"type": "integer", "description": "Number of times to press", "default": 1},
                "interval": {"type": "number", "description": "Interval between presses in seconds", "default": 0.1},
            },
            "required": ["key"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        key = args.get("key", "").strip().lower()
        presses = int(args.get("presses", 1))
        interval = float(args.get("interval", 0.1))

        if not key:
            return ToolResult.failure("key is required")

        ctx.check_cancelled()

        if not _HAS_PYAUTOGUI:
            return ToolResult.failure("pyautogui not available")

        try:
            await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: pyautogui.press(key, presses=presses, interval=interval),
            )
            _LOG.info("Pressed key: %s x%d", key, presses)
            return ToolResult.success(f"Pressed '{key}' {presses} time(s)")
        except Exception as e:
            _LOG.exception("Failed to press key")
            return ToolResult.failure(f"Failed to press key: {e}")


@tool("keyboard_hotkey", permission=PermissionLevel.SAFE, description="Press a combination of keys")
class KeyboardHotkeyTool(Tool):
    name = "keyboard_hotkey"
    description = "Press a combination of keys (e.g. Ctrl+C, Alt+Tab)"
    permission = PermissionLevel.SAFE

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Keys to press together (e.g. ['ctrl', 'c'])",
                },
            },
            "required": ["keys"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        keys = args.get("keys", [])
        if not keys:
            return ToolResult.failure("keys is required")

        ctx.check_cancelled()

        if not _HAS_PYAUTOGUI:
            return ToolResult.failure("pyautogui not available")

        try:
            normalized = [k.strip().lower() for k in keys if k.strip()]
            if not normalized:
                return ToolResult.failure("keys is empty")

            await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: pyautogui.hotkey(*normalized),
            )
            _LOG.info("Hotkey: %s", "+".join(normalized))
            return ToolResult.success(f"Pressed hotkey: {'+'.join(normalized)}")
        except Exception as e:
            _LOG.exception("Failed to press hotkey")
            return ToolResult.failure(f"Failed to press hotkey: {e}")


@tool("keyboard_type", permission=PermissionLevel.SAFE, description="Type text into the active window")
class KeyboardTypeTool(Tool):
    name = "keyboard_type"
    description = "Type text into the currently focused window"
    permission = PermissionLevel.SAFE

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to type"},
                "interval": {"type": "number", "description": "Interval between characters in seconds", "default": 0.05},
            },
            "required": ["text"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        text = args.get("text", "")
        interval = float(args.get("interval", 0.05))

        if not text:
            return ToolResult.failure("text is required")

        ctx.check_cancelled()

        if not _HAS_PYAUTOGUI:
            return ToolResult.failure("pyautogui not available")

        try:
            await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: pyautogui.write(text, interval=interval),
            )
            _LOG.info("Typed text: %d chars", len(text))
            return ToolResult.success(f"Typed {len(text)} characters")
        except Exception as e:
            _LOG.exception("Failed to type text")
            return ToolResult.failure(f"Failed to type text: {e}")