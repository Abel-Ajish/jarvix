"""Event bus for jarvix.

All subsystems communicate through this bus.  Publishing an event is
fire-and-forget; subscribers are invoked synchronously in registration
order.  This is the single mechanism that lets parallel subsystems
(e.g. voice interrupt cancelling an AI loop) cooperate without importing
each other.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Event:
    """Base event.  Subclasses set ``type``."""

    type: str
    timestamp: float = 0.0
    data: Dict[str, Any] = field(default_factory=dict)


class EventBus:
    """A simple in-process pub/sub bus.

    Thread-safe: handlers are invoked on the publisher's thread, so
    handlers that touch the GUI must marshal to the Qt thread via
    ``QMetaObject.invokeMethod`` or ``QtQueuedConnection``.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscribers: Dict[str, List[Callable[[Event], None]]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: Callable[[Event], None]) -> None:
        """Register ``handler`` for every event of ``event_type``.

        ``event_type`` may be ``"*"`` to receive all events.
        """
        with self._lock:
            self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Callable[[Event], None]) -> None:
        with self._lock:
            subs = self._subscribers.get(event_type)
            if subs and handler in subs:
                subs.remove(handler)

    def publish(self, event: Event) -> None:
        """Publish ``event`` to all matching subscribers."""
        with self._lock:
            handlers = list(self._subscribers.get(event.type, []))
            wild = list(self._subscribers.get("*", []))
        for h in handlers + wild:
            try:
                h(event)
            except Exception:
                # Never let a subscriber crash the publisher.
                pass


# ---------------------------------------------------------------------------
# Standard event types.  Subclasses are defined inline so they can carry
# typed data without extra boilerplate.
# ---------------------------------------------------------------------------


class ToolExecuted(Event):
    def __init__(self, tool: str, args: dict, result: Any) -> None:
        super().__init__("tool.executed", data={"tool": tool, "args": args, "result": result})


class PermissionRequested(Event):
    def __init__(self, tool: str, args: dict) -> None:
        super().__init__("permission.requested", data={"tool": tool, "args": args})


class AIResponseChunk(Event):
    def __init__(self, chunk: str) -> None:
        super().__init__("ai.response_chunk", data={"chunk": chunk})


class VoiceWake(Event):
    def __init__(self) -> None:
        super().__init__("voice.wake")


class VoiceResult(Event):
    def __init__(self, text: str) -> None:
        super().__init__("voice.result", data={"text": text})


class OnlineStatusChanged(Event):
    def __init__(self, online: bool) -> None:
        super().__init__("online.status_changed", data={"online": online})


class BrowserNavigated(Event):
    def __init__(self, url: str) -> None:
        super().__init__("browser.navigated", data={"url": url})


class ErrorRaised(Event):
    def __init__(self, message: str, *, component: str = "jarvix") -> None:
        super().__init__("error.raised", data={"message": message, "component": component})


class EmergencyStopRequested(Event):
    def __init__(self) -> None:
        super().__init__("emergency.stop")


class AICancelRequested(Event):
    def __init__(self) -> None:
        super().__init__("ai.cancel")


class ShutdownRequested(Event):
    def __init__(self) -> None:
        super().__init__("shutdown.requested")