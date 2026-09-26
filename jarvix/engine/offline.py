"""Offline command engine — deterministic pattern matcher (full implementation).

This is a deterministic pattern-matching engine that maps natural language
commands to tool calls. No LLM required. Works completely offline.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from jarvix.core.events import EventBus
from jarvix.core.execution import ExecContext
from jarvix.core.logger import get_logger
from jarvix.engine.ai_engine import AIEngine, ChatResponse, StreamChunk, ToolCallResult, ConnectionTest, ModelInfo

_LOG = get_logger("jarvix.offline")


# ---------------------------------------------------------------------------
# Intent patterns (command → tool name + arg extraction)
# ---------------------------------------------------------------------------

INTENT_PATTERNS: List[Tuple[str, str, List[str]]] = [
    # (tool_name, intent_name, [patterns])
    # Each pattern is a regex with named capture groups for args

    # Windows application control
    ("open_application", "OPEN_APPLICATION", [
        r"^(?:open|launch|start|run)\s+(?P<app_name>.+)$",
    ]),
    ("close_application", "CLOSE_APPLICATION", [
        r"^(?:close|quit|exit)\s+(?P<app_name>.+)$",
    ]),
    ("focus_application", "FOCUS_APPLICATION", [
        r"^(?:focus|switch to|activate)\s+(?P<app_name>.+)$",
    ]),
    ("minimize_window", "MINIMIZE_WINDOW", [
        r"^(?:minimize|minimise)\s+(?P<app_name>.+)$",
    ]),
    ("maximize_window", "MAXIMIZE_WINDOW", [
        r"^(?:maximize|maximise|fullscreen)\s+(?P<app_name>.+)$",
    ]),

    # Screenshot
    ("take_screenshot", "TAKE_SCREENSHOT", [
        r"^(?:take|capture|screenshot|screencap|print screen|prtsc)(?:\s+(?P<area>screen|window|region))?$",
    ]),

    # File operations
    ("create_file", "CREATE_FILE", [
        r"^(?:create|make|new)\s+file\s+(?P<path>.+)$",
    ]),
    ("read_file", "READ_FILE", [
        r"^(?:read|cat|show|display)\s+file\s+(?P<path>.+)$",
    ]),
    ("write_file", "WRITE_FILE", [
        r"^(?:write|save)\s+to\s+(?P<path>.+)\s+content\s+(?P<content>.+)$",
    ]),
    ("copy_file", "COPY_FILE", [
        r"^(?:copy|cp)\s+(?P<src>.+)\s+to\s+(?P<dst>.+)$",
    ]),
    ("move_file", "MOVE_FILE", [
        r"^(?:move|mv)\s+(?P<src>.+)\s+to\s+(?P<dst>.+)$",
    ]),
    ("rename_file", "RENAME_FILE", [
        r"^(?:rename|ren)\s+(?P<src>.+)\s+to\s+(?P<dst>.+)$",
    ]),
    ("delete_file", "DELETE_FILE", [
        r"^(?:delete|remove|del|rm)\s+file\s+(?P<path>.+)$",
    ]),
    ("create_folder", "CREATE_FOLDER", [
        r"^(?:create|make|mkdir)\s+(?:folder|directory|dir)\s+(?P<path>.+)$",
    ]),
    ("delete_folder", "DELETE_FOLDER", [
        r"^(?:delete|rmdir|rm)\s+(?:folder|directory|dir)\s+(?P<path>.+)$",
    ]),
    ("search_files", "SEARCH_FILES", [
        r"^(?:find|search|locate)\s+(?:files?\s+)?(?P<query>.+?)(?:\s+in\s+(?P<path>.+))?$",
    ]),

    # System info
    ("get_cpu", "GET_CPU", [
        r"^(?:get|show|check)\s+(?:cpu|processor)(?:\s+(?:usage|load|utilization))?$",
    ]),
    ("get_ram", "GET_RAM", [
        r"^(?:get|show|check)\s+(?:ram|memory)(?:\s+(?:usage|available|free))?$",
    ]),
    ("get_disk", "GET_DISK", [
        r"^(?:get|show|check)\s+(?:disk|storage|drive)(?:\s+(?:usage|space|free))?$",
    ]),
    ("get_battery", "GET_BATTERY", [
        r"^(?:get|show|check)\s+(?:battery|power)(?:\s+(?:level|status|percent))?$",
    ]),
    ("get_network_status", "GET_NETWORK_STATUS", [
        r"^(?:get|show|check)\s+(?:network|internet|wifi|connection)(?:\s+(?:status|speed|info))?$",
    ]),

    # Volume control
    ("set_volume", "SET_VOLUME", [
        r"^(?:set|change)\s+volume\s+(?:to\s+)?(?P<level>\d+)(?:\s*%)?$",
    ]),
    ("increase_volume", "INCREASE_VOLUME", [
        r"^(?:increase|raise|turn up|volume up)\s+(?:volume|sound)?$",
    ]),
    ("decrease_volume", "DECREASE_VOLUME", [
        r"^(?:decrease|lower|turn down|volume down)\s+(?:volume|sound)?$",
    ]),
    ("mute", "MUTE", [
        r"^(?:mute|silence)\s*(?:volume|sound)?$",
    ]),
    ("unmute", "UNMUTE", [
        r"^(?:unmute|unsilence)\s*(?:volume|sound)?$",
    ]),

    # Windows power control
    ("lock_windows", "LOCK_WINDOWS", [
        r"^(?:lock|lock screen|lock computer)$",
    ]),
    ("sleep_windows", "SLEEP_WINDOWS", [
        r"^(?:sleep|suspend|standby)(?:\s+(?:computer|pc|windows))?$",
    ]),
    ("shutdown_windows", "SHUTDOWN_WINDOWS", [
        r"^(?:shutdown|shut down|power off|turn off)(?:\s+(?:computer|pc|windows))?$",
    ]),
    ("restart_windows", "RESTART_WINDOWS", [
        r"^(?:restart|reboot)(?:\s+(?:computer|pc|windows))?$",
    ]),

    # Time/date
    ("get_time", "GET_TIME", [
        r"^(?:what time|current time|time)$",
    ]),
    ("get_date", "GET_DATE", [
        r"^(?:what date|current date|date|today)$",
    ]),

    # URL opening
    ("open_url", "OPEN_URL", [
        r"^(?:open|go to|visit|browse)\s+(?:url\s+)?(?P<url>https?://\S+)$",
        r"^(?:open|go to|visit|browse)\s+(?P<url>\w+\.\w+(?:/\S*)?)$",
    ]),

    # Clipboard
    ("clipboard_read", "CLIPBOARD_READ", [
        r"^(?:clipboard|paste|get clipboard)$",
    ]),
    ("clipboard_write", "CLIPBOARD_WRITE", [
        r"^(?:copy to clipboard|set clipboard)\s+(?P<text>.+)$",
    ]),

    # Program control
    ("start_program", "START_PROGRAM", [
        r"^(?:start|run|execute)\s+(?:program\s+)?(?P<command>.+)$",
    ]),
    ("stop_program", "STOP_PROGRAM", [
        r"^(?:stop|kill|terminate)\s+(?:program\s+)?(?P<name>.+)$",
    ]),

    # Plugin control
    ("enable_plugin", "ENABLE_PLUGIN", [
        r"^(?:enable|activate)\s+plugin\s+(?P<name>.+)$",
    ]),
    ("disable_plugin", "DISABLE_PLUGIN", [
        r"^(?:disable|deactivate)\s+plugin\s+(?P<name>.+)$",
    ]),

    # Memory
    ("memory_search", "MEMORY_SEARCH", [
        r"^(?:search|find)\s+(?:in\s+)?(?:memory|memories|notes?)\s+(?P<query>.+)$",
    ]),
    ("memory_save", "MEMORY_SAVE", [
        r"^(?:remember|memorize|save to memory)\s+(?P<fact>.+)$",
    ]),
    ("memory_delete", "MEMORY_DELETE", [
        r"^(?:forget|delete from memory|remove from memory)\s+(?P<query>.+)$",
    ]),

    # Task control
    ("cancel_task", "CANCEL_TASK", [
        r"^(?:cancel|abort)\s+(?:task|operation)$",
    ]),
    ("stop_jarvix", "STOP_jarvix", [
        r"^(?:jarvix\s+)?(?:stop|quit|exit|shutdown)$",
    ]),
]


class OfflineCommandEngine(AIEngine):
    """Deterministic offline command engine implementing the AIEngine interface.

    Maps natural language commands to tool calls via pattern matching.
    No LLM required. Works completely offline.
    """

    provider_name = "offline"
    supports_vision = False
    supports_tools = True  # tools go through ToolRegistry

    def __init__(self, event_bus: EventBus, tool_registry: Any = None) -> None:
        self._event_bus = event_bus
        self._tool_registry = tool_registry
        self._compiled_patterns = self._compile_patterns()

    def _compile_patterns(self) -> List[Tuple[str, re.Pattern]]:
        """Compile all regex patterns for fast matching."""
        compiled = []
        for tool_name, intent_name, patterns in INTENT_PATTERNS:
            for pattern in patterns:
                try:
                    compiled.append((tool_name, re.compile(pattern, re.IGNORECASE)))
                except re.error as e:
                    _LOG.warning("Invalid regex pattern for %s: %s", tool_name, e)
        return compiled

    # ---------------------------------------------------------------------------
    # AIEngine interface
    # ---------------------------------------------------------------------------

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        ctx: Optional[ExecContext] = None,
    ) -> ChatResponse:
        # Extract the last user message
        user_text = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_text = msg.get("content", "")
                break

        # Try to match an offline intent
        intent, args = self._match_intent(user_text)
        if intent and self._tool_registry:
            # Execute the tool directly (bypassing AI)
            result = await self._tool_registry.execute_async(intent, args, ctx or ExecContext(
                conversation_id="offline",
                user_id="local",
            ))
            if result.ok:
                return ChatResponse(content=result.output or "Done.")
            else:
                return ChatResponse(content=f"Error: {result.error}")

        # No intent matched - return helpful message
        return ChatResponse(
            content="I'm offline and couldn't understand that command. "
            "Try: 'open notepad', 'create folder Physics', 'turn volume down', "
            "'take screenshot', 'what time is it', 'open https://example.com'."
        )

    async def stream(
        self,
        messages: List[Dict[str, Any]],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        ctx: Optional[ExecContext] = None,
    ) -> AsyncIterator[StreamChunk]:
        response = await self.chat(messages, tools=tools, ctx=ctx)
        yield StreamChunk(content=response.content, done=True)

    async def tool_call(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        ctx: Optional[ExecContext] = None,
    ) -> ToolCallResult:
        return ToolCallResult(tool_calls=[], content="")

    async def vision(
        self,
        image_bytes: bytes,
        prompt: str,
        *,
        ctx: Optional[ExecContext] = None,
    ) -> str:
        return "Screen understanding requires an online vision model."

    async def structured_output(
        self,
        messages: List[Dict[str, Any]],
        schema: Dict[str, Any],
        ctx: Optional[ExecContext] = None,
    ) -> Dict[str, Any]:
        return {}

    async def test_connection(self) -> ConnectionTest:
        return ConnectionTest(ok=True, message="Offline engine ready", latency_ms=0)

    async def list_models(self) -> List[ModelInfo]:
        return [ModelInfo(
            id="offline",
            name="Offline Command Engine",
            provider="offline",
            capabilities=["tools"],
        )]

    # ---------------------------------------------------------------------------
    # Intent matching
    # ---------------------------------------------------------------------------

    def _match_intent(self, text: str) -> Tuple[Optional[str], Dict[str, Any]]:
        """Match user text to an offline intent. Returns (tool_name, args) or (None, {})."""
        text_lower = text.strip()

        for tool_name, pattern in self._compiled_patterns:
            match = pattern.match(text_lower)
            if match:
                args = match.groupdict()
                # Clean up args
                args = {k: v.strip() for k, v in args.items() if v is not None}
                _LOG.debug("Matched intent: %s -> %s (args: %s)", text_lower, tool_name, args)
                return tool_name, args

        _LOG.debug("No intent matched for: %s", text_lower)
        return None, {}