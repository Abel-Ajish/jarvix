"""Base AI provider class with common logic for auth, retries, timeouts."""

from __future__ import annotations

import asyncio
import os
import time
from abc import abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from jarvix.core.logger import get_logger
from jarvix.core.secret_store import get_secret_store
from jarvix.engine.ai_engine import (
    AIEngine,
    ChatResponse,
    ConnectionTest,
    ModelInfo,
    StreamChunk,
    ToolCallResult,
)
from jarvix.ai.models import ProviderConfig

_LOG = get_logger("jarvix.ai.provider")


class ProviderError(Exception):
    """Base exception for provider errors."""
    def __init__(self, message: str, error_type: str = "unknown", provider: str = "", retryable: bool = False):
        super().__init__(message)
        self.error_type = error_type
        self.provider = provider
        self.retryable = retryable


class AuthenticationError(ProviderError):
    """API key invalid or missing."""
    def __init__(self, message: str, provider: str = ""):
        super().__init__(message, error_type="authentication", provider=provider, retryable=False)


class RateLimitError(ProviderError):
    """Rate limit exceeded."""
    def __init__(self, message: str, provider: str = "", retry_after: Optional[float] = None):
        super().__init__(message, error_type="rate_limit", provider=provider, retryable=True)
        self.retry_after = retry_after


class ModelUnavailableError(ProviderError):
    """Model not available or not found."""
    def __init__(self, message: str, provider: str = ""):
        super().__init__(message, error_type="model_unavailable", provider=provider, retryable=False)


class NetworkError(ProviderError):
    """Network connectivity issue."""
    def __init__(self, message: str, provider: str = ""):
        super().__init__(message, error_type="network", provider=provider, retryable=True)


class TimeoutError(ProviderError):
    """Request timed out."""
    def __init__(self, message: str, provider: str = ""):
        super().__init__(message, error_type="timeout", provider=provider, retryable=True)


class AIProviderBase(AIEngine):
    """Base class for all AI providers.

    Handles:
    - Authentication via SecretStore
    - Retries with exponential backoff
    - Timeouts
    - Rate limit handling
    - Error classification
    """

    # Class attributes that subclasses should override
    provider_name: str = "base"
    supports_vision: bool = False
    supports_tools: bool = False

    # Default configuration
    DEFAULT_TIMEOUT = 60.0
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_BASE_DELAY = 1.0
    DEFAULT_MAX_DELAY = 60.0

    def __init__(
        self,
        config: ProviderConfig,
        *,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> None:
        self.config = config
        self.timeout = timeout or config.timeout_seconds or self.DEFAULT_TIMEOUT
        self.max_retries = max_retries if max_retries is not None else config.max_retries or self.DEFAULT_MAX_RETRIES

        # Load API key from SecretStore using env var name from settings
        self._api_key: Optional[str] = None
        if config.api_key_env:
            secret_store = get_secret_store()
            self._api_key = secret_store.get(config.api_key_env)

        # HTTP client with timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._client_lock = asyncio.Lock()

        # Rate limiting
        self._last_request_time = 0.0
        self._request_count = 0
        self._rate_limit_reset_time = 0.0

        # Cooldown tracking
        self._cooldown_until = 0.0
        self._consecutive_failures = 0

        # Logger for this provider
        self._log = get_logger(f"jarvix.ai.{self.provider_name}")

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        async with self._client_lock:
            if self._client is None or self._client.is_closed:
                self._client = httpx.AsyncClient(
                    timeout=httpx.Timeout(self.timeout),
                    follow_redirects=True,
                )
            return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        async with self._client_lock:
            if self._client and not self._client.is_closed:
                await self._client.aclose()
                self._client = None

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers including auth. Override in subclasses."""
        headers = {
            "Content-Type": "application/json",
        }
        if self.config.extra_headers:
            headers.update(self.config.extra_headers)
        return headers

    def _get_base_url(self) -> str:
        """Get the base URL for API requests. Override in subclasses."""
        return self.config.base_url or ""

    def _check_auth(self) -> None:
        """Check if authentication is configured. Raise if not."""
        if not self._api_key:
            raise AuthenticationError(
                f"No API key configured for {self.provider_name}. "
                f"Set {self.config.api_key_env} in SecretStore.",
                provider=self.provider_name
            )

    async def _handle_rate_limit(self) -> None:
        """Wait if rate limited."""
        now = time.time()
        if self._rate_limit_reset_time > now:
            wait_time = self._rate_limit_reset_time - now
            self._log.warning("Rate limited, waiting %.1fs", wait_time)
            await asyncio.sleep(wait_time)
            self._rate_limit_reset_time = 0.0

    async def _make_request(
        self,
        method: str,
        path: str,
        *,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        stream: bool = False,
    ) -> httpx.Response:
        """Make an HTTP request with retries and error handling."""
        await self._handle_rate_limit()

        url = f"{self._get_base_url()}{path}"
        request_headers = self._get_headers()
        if headers:
            request_headers.update(headers)

        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                client = await self._get_client()

                if stream:
                    # For streaming, we need special handling
                    response = await client.request(
                        method, url, json=json_data, headers=request_headers
                    )
                    return response

                response = await client.request(
                    method, url, json=json_data, headers=request_headers
                )

                # Handle different status codes
                if response.status_code == 200:
                    self._consecutive_failures = 0
                    return response

                elif response.status_code == 401:
                    raise AuthenticationError(
                        f"Authentication failed: {response.text}",
                        provider=self.provider_name
                    )

                elif response.status_code == 429:
                    # Rate limited
                    retry_after = None
                    if "retry-after" in response.headers:
                        try:
                            retry_after = float(response.headers["retry-after"])
                        except ValueError:
                            pass
                    elif "x-ratelimit-reset" in response.headers:
                        try:
                            retry_after = float(response.headers["x-ratelimit-reset"]) - time.time()
                        except ValueError:
                            pass

                    raise RateLimitError(
                        f"Rate limited: {response.text}",
                        provider=self.provider_name,
                        retry_after=retry_after
                    )

                elif response.status_code == 404:
                    raise ModelUnavailableError(
                        f"Model or endpoint not found: {response.text}",
                        provider=self.provider_name
                    )

                elif response.status_code >= 500:
                    # Server error - retryable
                    raise NetworkError(
                        f"Server error ({response.status_code}): {response.text}",
                        provider=self.provider_name
                    )

                else:
                    # Other client errors - may or may not be retryable
                    raise ProviderError(
                        f"Request failed ({response.status_code}): {response.text}",
                        provider=self.provider_name,
                        retryable=response.status_code >= 500
                    )

            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = NetworkError(
                    f"Network error: {e}",
                    provider=self.provider_name
                )
                self._consecutive_failures += 1

            except asyncio.TimeoutError as e:
                last_error = TimeoutError(
                    f"Request timed out: {e}",
                    provider=self.provider_name
                )
                self._consecutive_failures += 1

            except ProviderError as e:
                # Re-raise our custom errors
                if not e.retryable or attempt >= self.max_retries:
                    raise
                last_error = e
                self._consecutive_failures += 1

            # Wait before retry with exponential backoff
            if attempt < self.max_retries:
                delay = min(
                    self.DEFAULT_BASE_DELAY * (2 ** attempt),
                    self.DEFAULT_MAX_DELAY
                )
                # Add jitter
                import random
                delay *= (0.5 + random.random())

                self._log.warning(
                    "Request failed (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1, self.max_retries + 1, delay, last_error
                )
                await asyncio.sleep(delay)

        # All retries exhausted
        if last_error:
            raise last_error
        raise ProviderError("Request failed after retries", provider=self.provider_name)

    async def _make_streaming_request(
        self,
        method: str,
        path: str,
        *,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> AsyncIterator[str]:
        """Make a streaming HTTP request."""
        await self._handle_rate_limit()

        url = f"{self._get_base_url()}{path}"
        request_headers = self._get_headers()
        if headers:
            request_headers.update(headers)

        client = await self._get_client()

        async with client.stream(method, url, json=json_data, headers=request_headers) as response:
            if response.status_code != 200:
                error_text = await response.aread()
                if response.status_code == 401:
                    raise AuthenticationError(
                        f"Authentication failed: {error_text.decode()}",
                        provider=self.provider_name
                    )
                elif response.status_code == 429:
                    raise RateLimitError(
                        f"Rate limited: {error_text.decode()}",
                        provider=self.provider_name
                    )
                else:
                    raise ProviderError(
                        f"Streaming request failed ({response.status_code}): {error_text.decode()}",
                        provider=self.provider_name
                    )

            async for line in response.aiter_lines():
                yield line

    def _should_cooldown(self) -> bool:
        """Check if provider should be in cooldown."""
        return time.time() < self._cooldown_until

    def _set_cooldown(self, seconds: float) -> None:
        """Set provider cooldown."""
        self._cooldown_until = time.time() + seconds
        self._log.warning("Provider %s in cooldown for %.1fs", self.provider_name, seconds)

    def _record_failure(self) -> None:
        """Record a failure and potentially trigger cooldown."""
        self._consecutive_failures += 1
        if self._consecutive_failures >= 5:
            # Exponential cooldown: 30s, 60s, 120s, 240s, max 300s
            cooldown = min(30 * (2 ** (self._consecutive_failures - 5)), 300)
            self._set_cooldown(cooldown)

    def _record_success(self) -> None:
        """Record a success."""
        self._consecutive_failures = 0

    # Abstract methods that subclasses must implement

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