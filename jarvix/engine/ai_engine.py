"""AIEngine interface — the single abstraction for all AI providers.

All provider-specific code is hidden behind this interface.  The rest of
jarvix only depends on this ABC.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional


@dataclass
class ChatResponse:
    """Response from a chat completion."""
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    model: Optional[str] = None
    usage: Optional[Dict[str, int]] = None


@dataclass
class StreamChunk:
    """A single chunk from a streaming response."""
    content: str = ""
    tool_call: Optional[Dict[str, Any]] = None
    done: bool = False


@dataclass
class ToolCallResult:
    """Result of a tool-use completion."""
    tool_calls: List[Dict[str, Any]]
    content: str = ""


@dataclass
class ConnectionTest:
    """Result of test_connection()."""
    ok: bool
    message: str = ""
    latency_ms: Optional[int] = None


@dataclass
class ModelInfo:
    """Information about an available model."""
    id: str
    name: str
    provider: str
    capabilities: List[str] = field(default_factory=list)  # e.g. ["chat", "vision", "tools"]
    context_length: Optional[int] = None


class AIEngine(ABC):
    """Abstract base class for all AI providers.

    Concrete implementations:
    - OpenRouterEngine
    - OpenAIEngine
    - AnthropicEngine
    - GeminiEngine
    - GroqEngine
    - TogetherEngine
    - NIM Engine
    - GenericOpenAIEngine
    - OfflineEngine (deterministic pattern matcher)
    """

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, Any]],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        ctx: Optional[Any] = None,
    ) -> ChatResponse:
        """Single-turn chat completion."""
        ...

    @abstractmethod
    async def stream(
        self,
        messages: List[Dict[str, Any]],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        ctx: Optional[Any] = None,
    ) -> AsyncIterator[StreamChunk]:
        """Streaming chat completion."""
        ...

    @abstractmethod
    async def tool_call(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        ctx: Optional[Any] = None,
    ) -> ToolCallResult:
        """Forced tool-use completion (model MUST call a tool)."""
        ...

    @abstractmethod
    async def vision(
        self,
        image_bytes: bytes,
        prompt: str,
        *,
        ctx: Optional[Any] = None,
    ) -> str:
        """Vision completion: describe image + answer prompt."""
        ...

    @abstractmethod
    async def structured_output(
        self,
        messages: List[Dict[str, Any]],
        schema: Dict[str, Any],
        ctx: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Completion constrained to a JSON schema."""
        ...

    @abstractmethod
    async def test_connection(self) -> ConnectionTest:
        """Test if the provider is reachable and credentials work."""
        ...

    @abstractmethod
    async def list_models(self) -> List[ModelInfo]:
        """List available models for this provider."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique provider identifier (e.g. 'openrouter', 'anthropic')."""
        ...

    @property
    @abstractmethod
    def supports_vision(self) -> bool:
        """Whether this provider supports vision()."""
        ...

    @property
    @abstractmethod
    def supports_tools(self) -> bool:
        """Whether this provider supports tool calling."""
        ...