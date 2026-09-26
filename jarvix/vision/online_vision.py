"""Online vision for jarvix (Phase 7).

Calls AIEngine.vision() with captured images. Handles image encoding (base64),
prompt construction, streaming responses. Falls back gracefully if no online
AI configured.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Union

from jarvix.core.config import get_settings
from jarvix.core.logger import get_logger
from jarvix.engine.ai_engine import AIEngine

_LOG = get_logger("jarvix.vision.online_vision")


@dataclass
class VisionResult:
    """Result of a vision analysis."""
    text: str
    model: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    error: Optional[str] = None

    @classmethod
    def success(cls, text: str, model: Optional[str] = None, usage: Optional[Dict[str, int]] = None) -> "VisionResult":
        return cls(text=text, model=model, usage=usage)

    @classmethod
    def failure(cls, error: str) -> "VisionResult":
        return cls(text="", error=error)

    @property
    def ok(self) -> bool:
        return self.error is None


class OnlineVision:
    """Manages vision calls to the configured AI provider."""

    def __init__(self, engine: Optional[AIEngine] = None) -> None:
        self._engine = engine
        self._settings = get_settings()

    @property
    def engine(self) -> Optional[AIEngine]:
        return self._engine

    @engine.setter
    def engine(self, value: Optional[AIEngine]) -> None:
        self._engine = value

    def is_available(self) -> bool:
        """Check if a vision-capable provider is configured."""
        if self._engine is None:
            return False
        return self._engine.supports_vision

    async def analyze(
        self,
        image_bytes: bytes,
        prompt: str,
        *,
        model: Optional[str] = None,
    ) -> VisionResult:
        """Analyze an image with the vision model.

        Args:
            image_bytes: Raw image bytes (PNG/JPEG)
            prompt: Prompt to send with the image
            model: Optional model override

        Returns:
            VisionResult with analysis text or error
        """
        if not self.is_available():
            return VisionResult.failure(
                "No vision model configured. Set up an online AI provider in settings."
            )

        try:
            result = await self._engine.vision(image_bytes, prompt)
            return VisionResult.success(result, model=self._engine.provider_name)
        except Exception as e:
            _LOG.exception("Vision analysis failed")
            return VisionResult.failure(f"Vision analysis failed: {e}")

    async def analyze_stream(
        self,
        image_bytes: bytes,
        prompt: str,
        *,
        model: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """Stream vision analysis (if provider supports streaming vision).

        Note: Most providers don't support streaming for vision yet.
        This falls back to non-streaming and yields the complete result.
        """
        if not self.is_available():
            yield "No vision model configured. Set up an online AI provider in settings."
            return

        try:
            # Try streaming via chat with image content
            messages = [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64.b64encode(image_bytes).decode()}"
                        }
                    }
                ]
            }]

            async for chunk in self._engine.stream(messages):
                if chunk.content:
                    yield chunk.content
                if chunk.done:
                    break
        except Exception as e:
            _LOG.exception("Vision stream failed")
            yield f"Error: {e}"

    async def analyze_file(
        self,
        image_path: Union[str, Path],
        prompt: str,
        *,
        model: Optional[str] = None,
    ) -> VisionResult:
        """Analyze an image file."""
        path = Path(image_path)
        if not path.exists():
            return VisionResult.failure(f"Image file not found: {path}")

        with path.open("rb") as f:
            image_bytes = f.read()

        return await self.analyze(image_bytes, prompt, model=model)


# ---------------------------------------------------------------------------
# Convenience functions using global engine (for tool integration)
# ---------------------------------------------------------------------------

# Global instance, set by the AI engine initialization
_online_vision: Optional[OnlineVision] = None


def set_online_vision(engine: AIEngine) -> None:
    """Set the global OnlineVision instance with an engine."""
    global _online_vision
    _online_vision = OnlineVision(engine)
    _LOG.info("OnlineVision initialized with provider: %s", engine.provider_name)


def get_online_vision() -> Optional[OnlineVision]:
    """Get the global OnlineVision instance."""
    return _online_vision


async def vision_analyze(
    image_bytes: bytes,
    prompt: str,
    *,
    model: Optional[str] = None,
) -> VisionResult:
    """Convenience function for vision analysis using global engine."""
    vision = get_online_vision()
    if vision is None:
        return VisionResult.failure("No AI engine configured for vision")
    return await vision.analyze(image_bytes, prompt, model=model)


async def vision_analyze_file(
    image_path: Union[str, Path],
    prompt: str,
    *,
    model: Optional[str] = None,
) -> VisionResult:
    """Convenience function for vision analysis of a file."""
    vision = get_online_vision()
    if vision is None:
        return VisionResult.failure("No AI engine configured for vision")
    return await vision.analyze_file(image_path, prompt, model=model)


def vision_is_available() -> bool:
    """Check if vision is available via global engine."""
    vision = get_online_vision()
    return vision is not None and vision.is_available()


# ---------------------------------------------------------------------------
# Image encoding utilities
# ---------------------------------------------------------------------------

def encode_image_base64(image_bytes: bytes, mime_type: str = "image/png") -> str:
    """Encode image bytes as base64 data URL."""
    b64 = base64.b64encode(image_bytes).decode()
    return f"data:{mime_type};base64,{b64}"


def load_image_as_bytes(path: Union[str, Path]) -> bytes:
    """Load image file as bytes."""
    with Path(path).open("rb") as f:
        return f.read()


def pil_image_to_bytes(img, format: str = "PNG") -> bytes:
    """Convert PIL Image to bytes."""
    buf = BytesIO()
    img.save(buf, format=format)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Prompt templates for common vision tasks
# ---------------------------------------------------------------------------

VISION_PROMPTS = {
    "describe": "Describe what you see in this image in detail.",
    "read_text": "Extract all readable text from this image. Return only the text content.",
    "find_element": "Find the {element_type} in this image. Return its location (bounding box) and any text on it.",
    "ui_elements": "Identify all UI elements in this screenshot: buttons, text fields, menus, checkboxes, links, etc. "
                   "Return a JSON array with each element's type, bounding box (x, y, width, height), and text label.",
    "click_target": "Find the best target to click for: {action}. Return the element's bounding box and description.",
    "accessibility": "Describe this UI for accessibility: list all interactive elements, their roles, labels, and states.",
}


def get_vision_prompt(template: str, **kwargs) -> str:
    """Get a vision prompt template with formatting."""
    template_str = VISION_PROMPTS.get(template, template)
    return template_str.format(**kwargs)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    "VisionResult",
    "OnlineVision",
    "set_online_vision",
    "get_online_vision",
    "vision_analyze",
    "vision_analyze_file",
    "vision_is_available",
    "encode_image_base64",
    "load_image_as_bytes",
    "pil_image_to_bytes",
    "get_vision_prompt",
    "VISION_PROMPTS",
]