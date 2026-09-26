"""Data classes for AI models and provider information."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ModelInfo:
    """Information about an available model."""
    id: str
    name: str
    provider: str
    capabilities: List[str] = field(default_factory=list)  # e.g. ["chat", "vision", "tools", "reasoning"]
    context_length: Optional[int] = None
    max_output_tokens: Optional[int] = None
    pricing: Optional[Dict[str, float]] = None  # e.g. {"input": 0.001, "output": 0.002} per 1K tokens
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderConfig:
    """Configuration for an AI provider."""
    name: str
    enabled: bool = False
    api_key_env: str = ""  # Environment variable name for the API key
    base_url: Optional[str] = None
    models: List[str] = field(default_factory=list)  # Model IDs this provider can use
    timeout_seconds: float = 60.0
    max_retries: int = 3
    rate_limit_rpm: Optional[int] = None  # Requests per minute
    rate_limit_tpm: Optional[int] = None  # Tokens per minute
    extra_headers: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RoleModelMapping:
    """Maps a role to a specific provider and model."""
    role: str  # GENERAL, REASONING, CODING, VISION, FAST, WEB, TOOL_USE
    provider: str
    model: str
    fallback_provider: Optional[str] = None
    fallback_model: Optional[str] = None


# Predefined roles for model selection
class AI_Role:
    GENERAL = "general"
    REASONING = "reasoning"
    CODING = "coding"
    VISION = "vision"
    FAST = "fast"
    WEB = "web"
    TOOL_USE = "tool_use"

    ALL = [GENERAL, REASONING, CODING, VISION, FAST, WEB, TOOL_USE]