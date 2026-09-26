"""OpenRouter AI provider implementation."""

from __future__ import annotations

import base64
import json
import os
from typing import Any, AsyncIterator, Dict, List, Optional

from jarvix.ai.provider import (
    AIProviderBase,
    AuthenticationError,
    ModelUnavailableError,
    NetworkError,
    ProviderError,
    RateLimitError,
)
from jarvix.ai.models import ProviderConfig
from jarvix.core.logger import get_logger
from jarvix.engine.ai_engine import (
    ChatResponse,
    ConnectionTest,
    ModelInfo,
    StreamChunk,
    ToolCallResult,
)

_LOG = get_logger("jarvix.ai.openrouter")


class OpenRouterProvider(AIProviderBase):
    """OpenRouter provider - unified API for multiple LLM providers."""

    provider_name = "openrouter"
    supports_vision = True
    supports_tools = True

    DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
    DEFAULT_MODEL = "anthropic/claude-3.5-sonnet"

    def __init__(self, config: ProviderConfig) -> None:
        super().__init__(config)
        # Ensure base URL is set
        if not self.config.base_url:
            self.config.base_url = self.DEFAULT_BASE_URL

    def _get_headers(self) -> Dict[str, str]:
        headers = super()._get_headers()
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        # OpenRouter recommends these headers
        headers["HTTP-Referer"] = "https://github.com/jarvix"
        headers["X-Title"] = "jarvix"
        return headers

    def _get_base_url(self) -> str:
        return self.config.base_url or self.DEFAULT_BASE_URL

    def _format_messages(
        self,
        messages: List[Dict[str, Any]],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Format messages for OpenRouter API."""
        formatted = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                formatted.append({"role": "system", "content": content})
            elif role == "user":
                if isinstance(content, list):
                    # Multi-modal content (text + images)
                    formatted.append({"role": "user", "content": content})
                else:
                    formatted.append({"role": "user", "content": content})
            elif role == "assistant":
                if msg.get("tool_calls"):
                    formatted.append({
                        "role": "assistant",
                        "content": content or None,
                        "tool_calls": msg["tool_calls"],
                    })
                else:
                    formatted.append({"role": "assistant", "content": content})
            elif role == "tool":
                formatted.append({
                    "role": "tool",
                    "content": content,
                    "tool_call_id": msg.get("tool_call_id"),
                })

        return formatted

    def _format_tools(self, tools: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
        """Format tools for OpenRouter API (OpenAI-compatible)."""
        if not tools:
            return None

        formatted = []
        for tool in tools:
            if tool.get("type") == "function":
                formatted.append(tool)
            else:
                # Convert from internal format if needed
                formatted.append({
                    "type": "function",
                    "function": {
                        "name": tool.get("name", ""),
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", {}),
                    }
                })
        return formatted

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        ctx: Optional[Any] = None,
    ) -> ChatResponse:
        self._check_auth()

        payload = {
            "model": self.config.models[0] if self.config.models else self.DEFAULT_MODEL,
            "messages": self._format_messages(messages, tools=tools),
            "temperature": 0.7,
            "max_tokens": 4096,
        }

        if tools:
            payload["tools"] = self._format_tools(tools)
            payload["tool_choice"] = "auto"

        try:
            response = await self._make_request("POST", "/chat/completions", json_data=payload)
            data = response.json()

            choice = data["choices"][0]
            message = choice["message"]

            tool_calls = None
            if message.get("tool_calls"):
                tool_calls = []
                for tc in message["tool_calls"]:
                    tool_calls.append({
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "arguments": json.loads(tc["function"]["arguments"]),
                    })

            usage = data.get("usage")
            usage_dict = None
            if usage:
                usage_dict = {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                }

            self._record_success()
            return ChatResponse(
                content=message.get("content", ""),
                tool_calls=tool_calls,
                model=data.get("model"),
                usage=usage_dict,
            )

        except (AuthenticationError, RateLimitError, ModelUnavailableError, NetworkError):
            self._record_failure()
            raise
        except Exception as e:
            self._record_failure()
            _LOG.exception("OpenRouter chat failed")
            raise ProviderError(f"Chat failed: {e}", provider=self.provider_name)

    async def stream(
        self,
        messages: List[Dict[str, Any]],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        ctx: Optional[Any] = None,
    ) -> AsyncIterator[StreamChunk]:
        self._check_auth()

        payload = {
            "model": self.config.models[0] if self.config.models else self.DEFAULT_MODEL,
            "messages": self._format_messages(messages, tools=tools),
            "temperature": 0.7,
            "max_tokens": 4096,
            "stream": True,
        }

        if tools:
            payload["tools"] = self._format_tools(tools)
            payload["tool_choice"] = "auto"

        try:
            buffer = ""
            async for line in self._make_streaming_request("POST", "/chat/completions", json_data=payload):
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break

                    try:
                        data = json.loads(data_str)
                        choice = data["choices"][0]
                        delta = choice.get("delta", {})

                        content = delta.get("content", "")
                        if content:
                            buffer += content
                            yield StreamChunk(content=content)

                        if delta.get("tool_calls"):
                            for tc in delta["tool_calls"]:
                                if tc["index"] == 0:
                                    yield StreamChunk(
                                        content="",
                                        tool_call={
                                            "id": tc["id"],
                                            "name": tc["function"]["name"],
                                            "arguments": tc["function"]["arguments"],
                                        }
                                    )

                        if choice.get("finish_reason"):
                            yield StreamChunk(content="", done=True)
                            break

                    except json.JSONDecodeError:
                        continue

            self._record_success()

        except (AuthenticationError, RateLimitError, ModelUnavailableError, NetworkError):
            self._record_failure()
            raise
        except Exception as e:
            self._record_failure()
            _LOG.exception("OpenRouter stream failed")
            yield StreamChunk(content=f"Error: {e}", done=True)

    async def tool_call(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        ctx: Optional[Any] = None,
    ) -> ToolCallResult:
        """Force tool use by setting tool_choice to required."""
        self._check_auth()

        payload = {
            "model": self.config.models[0] if self.config.models else self.DEFAULT_MODEL,
            "messages": self._format_messages(messages, tools=tools),
            "temperature": 0.3,
            "max_tokens": 4096,
            "tools": self._format_tools(tools),
            "tool_choice": "required",
        }

        try:
            response = await self._make_request("POST", "/chat/completions", json_data=payload)
            data = response.json()

            choice = data["choices"][0]
            message = choice["message"]

            tool_calls = []
            if message.get("tool_calls"):
                for tc in message["tool_calls"]:
                    tool_calls.append({
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "arguments": json.loads(tc["function"]["arguments"]),
                    })

            self._record_success()
            return ToolCallResult(
                tool_calls=tool_calls,
                content=message.get("content", ""),
            )

        except (AuthenticationError, RateLimitError, ModelUnavailableError, NetworkError):
            self._record_failure()
            raise
        except Exception as e:
            self._record_failure()
            _LOG.exception("OpenRouter tool_call failed")
            raise ProviderError(f"Tool call failed: {e}", provider=self.provider_name)

    async def vision(
        self,
        image_bytes: bytes,
        prompt: str,
        *,
        ctx: Optional[Any] = None,
    ) -> str:
        self._check_auth()

        # Encode image to base64
        image_b64 = base64.b64encode(image_bytes).decode()

        payload = {
            "model": self.config.models[0] if self.config.models else "anthropic/claude-3.5-sonnet",
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_b64}",
                        }
                    }
                ]
            }],
            "max_tokens": 2048,
        }

        try:
            response = await self._make_request("POST", "/chat/completions", json_data=payload)
            data = response.json()

            content = data["choices"][0]["message"].get("content", "")
            self._record_success()
            return content

        except (AuthenticationError, RateLimitError, ModelUnavailableError, NetworkError):
            self._record_failure()
            raise
        except Exception as e:
            self._record_failure()
            _LOG.exception("OpenRouter vision failed")
            raise ProviderError(f"Vision failed: {e}", provider=self.provider_name)

    async def structured_output(
        self,
        messages: List[Dict[str, Any]],
        schema: Dict[str, Any],
        ctx: Optional[Any] = None,
    ) -> Dict[str, Any]:
        self._check_auth()

        # OpenRouter supports response_format with json_schema
        payload = {
            "model": self.config.models[0] if self.config.models else self.DEFAULT_MODEL,
            "messages": self._format_messages(messages),
            "temperature": 0.1,
            "max_tokens": 4096,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_output",
                    "schema": schema,
                    "strict": True,
                }
            },
        }

        try:
            response = await self._make_request("POST", "/chat/completions", json_data=payload)
            data = response.json()

            content = data["choices"][0]["message"].get("content", "{}")
            result = json.loads(content)
            self._record_success()
            return result

        except (AuthenticationError, RateLimitError, ModelUnavailableError, NetworkError):
            self._record_failure()
            raise
        except Exception as e:
            self._record_failure()
            _LOG.exception("OpenRouter structured_output failed")
            raise ProviderError(f"Structured output failed: {e}", provider=self.provider_name)

    async def test_connection(self) -> ConnectionTest:
        import time
        start = time.time()

        try:
            self._check_auth()

            # Test with a minimal request
            payload = {
                "model": self.config.models[0] if self.config.models else self.DEFAULT_MODEL,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 5,
            }

            response = await self._make_request("POST", "/chat/completions", json_data=payload)
            data = response.json()

            latency_ms = int((time.time() - start) * 1000)
            return ConnectionTest(
                ok=True,
                message="OpenRouter connection successful",
                latency_ms=latency_ms,
            )

        except AuthenticationError as e:
            return ConnectionTest(ok=False, message=f"Authentication failed: {e}")
        except RateLimitError as e:
            return ConnectionTest(ok=False, message=f"Rate limited: {e}")
        except NetworkError as e:
            return ConnectionTest(ok=False, message=f"Network error: {e}")
        except Exception as e:
            _LOG.exception("OpenRouter test_connection failed")
            return ConnectionTest(ok=False, message=f"Connection test failed: {e}")

    async def list_models(self) -> List[ModelInfo]:
        try:
            self._check_auth()

            response = await self._make_request("GET", "/models")
            data = response.json()

            models = []
            for m in data.get("data", []):
                model_id = m.get("id", "")
                # Filter to only models we can actually use
                if self.config.models and model_id not in self.config.models:
                    continue

                models.append(ModelInfo(
                    id=model_id,
                    name=m.get("name", model_id),
                    provider=self.provider_name,
                    capabilities=["chat", "tools"] if m.get("supports_tools") else ["chat"],
                    context_length=m.get("context_length"),
                    description=m.get("description", ""),
                    metadata={
                        "pricing": m.get("pricing"),
                        "top_provider": m.get("top_provider"),
                    }
                ))

            return models

        except Exception as e:
            _LOG.exception("OpenRouter list_models failed")
            return []