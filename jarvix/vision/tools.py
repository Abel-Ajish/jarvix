"""Vision tools for jarvix (Phase 7).

Tools for screen capture, vision analysis, UI detection, and text extraction.
All tools register via @tool decorator with proper permissions.
"""

from __future__ import annotations

import asyncio
import base64
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from jarvix.core.config import get_settings
from jarvix.core.execution import ExecContext
from jarvix.core.logger import get_logger
from jarvix.core.permissions import PermissionLevel
from jarvix.core.tool_registry import Tool, ToolResult, tool
from jarvix.vision.capture import (
    capture_screen_bytes,
    capture_to_temp,
    capture_to_temp_async,
    get_monitors,
    get_primary_monitor,
    image_to_bytes,
)
from jarvix.vision.online_vision import (
    VisionResult,
    vision_analyze,
    vision_analyze_file,
    vision_is_available,
    get_vision_prompt,
)
from jarvix.vision.ui_understanding import (
    UIElement,
    UIElementType,
    detect_ui_elements,
    extract_screen_text,
    find_ui_element,
    find_button,
    find_text_field,
    get_click_targets,
    get_input_targets,
)

_LOG = get_logger("jarvix.vision.tools")


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _get_vision_settings() -> Dict[str, Any]:
    """Get vision-specific settings."""
    settings = get_settings()
    return {
        "confidence_threshold": settings.get("vision.confidence_threshold", 0.3),
        "max_elements": settings.get("vision.max_elements", 100),
        "default_monitor": settings.get("vision.default_monitor", 0),
        "use_custom_region": settings.get("vision.use_custom_region", False),
        "region_left": settings.get("vision.region_left", 0),
        "region_top": settings.get("vision.region_top", 0),
        "region_width": settings.get("vision.region_width", 1920),
        "region_height": settings.get("vision.region_height", 1080),
    }


def _get_capture_args(args: Dict[str, Any]) -> Tuple[Optional[int], Optional[Tuple[int, int, int, int]]]:
    """Extract monitor_index and region from tool args."""
    monitor_index = args.get("monitor")
    if monitor_index is not None:
        monitor_index = int(monitor_index)

    region = None
    if "region" in args and args["region"]:
        region_dict = args["region"]
        if isinstance(region_dict, dict):
            region = (
                region_dict.get("left", 0),
                region_dict.get("top", 0),
                region_dict.get("right", 0),
                region_dict.get("bottom", 0),
            )

    # Also check for legacy individual region params
    if region is None:
        left = args.get("left", 0)
        top = args.get("top", 0)
        right = args.get("right", 0)
        bottom = args.get("bottom", 0)
        if any([left, top, right, bottom]):
            region = (left, top, right, bottom)

    return monitor_index, region


def _vision_result_to_toolresult(result: VisionResult) -> ToolResult:
    """Convert VisionResult to ToolResult."""
    if result.ok:
        return ToolResult.success(result.text, data={"model": result.model, "usage": result.usage})
    return ToolResult.failure(result.error or "Vision analysis failed")


def _elements_to_toolresult(elements: List[UIElement], screen_size: Tuple[int, int]) -> ToolResult:
    """Convert UI elements to ToolResult."""
    data = {
        "elements": [e.to_dict() for e in elements],
        "screen_size": {"width": screen_size[0], "height": screen_size[1]},
        "count": len(elements),
    }
    return ToolResult.success(
        f"Found {len(elements)} UI elements",
        data=data,
    )


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool("screen_capture", permission=PermissionLevel.SAFE, description="Capture screen to file")
class ScreenCaptureTool(Tool):
    name = "screen_capture"
    description = "Capture full screen, specific monitor, or region to a temporary file"
    permission = PermissionLevel.SAFE

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "monitor": {
                    "type": "integer",
                    "description": "Monitor index (0 = all combined, 1+ = specific monitor)",
                },
                "region": {
                    "type": "object",
                    "description": "Capture region as {left, top, right, bottom}",
                    "properties": {
                        "left": {"type": "integer"},
                        "top": {"type": "integer"},
                        "right": {"type": "integer"},
                        "bottom": {"type": "integer"},
                    },
                },
                "save_path": {
                    "type": "string",
                    "description": "Optional path to save the capture (default: temp file)",
                },
            },
            "required": [],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        ctx.check_cancelled()

        monitor_index, region = _get_capture_args(args)
        save_path = args.get("save_path")

        try:
            if save_path:
                path = Path(save_path).expanduser()
                path.parent.mkdir(parents=True, exist_ok=True)
                # Capture directly to path
                from jarvix.vision.capture import capture_screen
                img = await capture_screen(
                    monitor_index=monitor_index,
                    region=region,
                    save_path=str(path),
                )
                return ToolResult.success(
                    f"Captured screen to {path}",
                    data={"path": str(path), "width": img.width, "height": img.height},
                )
            else:
                # Capture to temp file
                path = await capture_to_temp_async(
                    monitor_index=monitor_index,
                    region=region,
                )
                return ToolResult.success(
                    f"Captured screen to temporary file",
                    data={"path": path},
                )

        except Exception as e:
            _LOG.exception("Screen capture failed")
            return ToolResult.failure(f"Screen capture failed: {e}")


@tool("analyze_screen", permission=PermissionLevel.CONFIRM, description="Capture screen and analyze with vision model")
class AnalyzeScreenTool(Tool):
    name = "analyze_screen"
    description = "Capture screen and send to vision model with a custom prompt"
    permission = PermissionLevel.CONFIRM

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Prompt for the vision model (what to analyze)",
                },
                "monitor": {
                    "type": "integer",
                    "description": "Monitor index (0 = all combined, 1+ = specific monitor)",
                },
                "region": {
                    "type": "object",
                    "description": "Capture region as {left, top, right, bottom}",
                    "properties": {
                        "left": {"type": "integer"},
                        "top": {"type": "integer"},
                        "right": {"type": "integer"},
                        "bottom": {"type": "integer"},
                    },
                },
                "template": {
                    "type": "string",
                    "description": "Use a predefined prompt template",
                    "enum": ["describe", "read_text", "ui_elements", "click_target", "accessibility"],
                },
                "template_args": {
                    "type": "object",
                    "description": "Arguments for the template (e.g. {\"action\": \"click login button\"})",
                },
            },
            "required": ["prompt"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        ctx.check_cancelled()

        if not vision_is_available():
            return ToolResult.failure(
                "No vision model configured. Set up an online AI provider with vision support in settings."
            )

        prompt = args.get("prompt", "").strip()
        template = args.get("template", "")
        template_args = args.get("template_args", {})

        # Apply template if provided
        if template:
            prompt = get_vision_prompt(template, **template_args)

        monitor_index, region = _get_capture_args(args)

        try:
            # Capture screen
            image_bytes = await capture_screen_bytes(
                monitor_index=monitor_index,
                region=region,
            )

            ctx.check_cancelled()

            # Analyze with vision
            result = await vision_analyze(image_bytes, prompt)

            return _vision_result_to_toolresult(result)

        except Exception as e:
            _LOG.exception("Screen analysis failed")
            return ToolResult.failure(f"Screen analysis failed: {e}")


@tool("find_ui_element", permission=PermissionLevel.CONFIRM, description="Find a specific UI element on screen")
class FindUIElementTool(Tool):
    name = "find_ui_element"
    description = "Capture screen and find a specific UI element by description"
    permission = PermissionLevel.CONFIRM

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Natural language description of the element to find (e.g., 'submit button', 'search box', 'file menu')",
                },
                "monitor": {
                    "type": "integer",
                    "description": "Monitor index (0 = all combined, 1+ = specific monitor)",
                },
                "region": {
                    "type": "object",
                    "description": "Capture region as {left, top, right, bottom}",
                    "properties": {
                        "left": {"type": "integer"},
                        "top": {"type": "integer"},
                        "right": {"type": "integer"},
                        "bottom": {"type": "integer"},
                    },
                },
            },
            "required": ["description"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        ctx.check_cancelled()

        if not vision_is_available():
            return ToolResult.failure(
                "No vision model configured. Set up an online AI provider with vision support in settings."
            )

        description = args.get("description", "").strip()
        if not description:
            return ToolResult.failure("description is required")

        monitor_index, region = _get_capture_args(args)

        try:
            from jarvix.vision.ui_understanding import find_ui_element_on_screen
            element = await find_ui_element_on_screen(
                description,
                monitor_index=monitor_index,
                region=region,
            )

            if element is None:
                return ToolResult.failure(f"Element not found: {description}")

            return ToolResult.success(
                f"Found {element.element_type.value}: {element.text or element.label}",
                data=element.to_dict(),
            )

        except Exception as e:
            _LOG.exception("Find UI element failed")
            return ToolResult.failure(f"Find UI element failed: {e}")


@tool("read_screen_text", permission=PermissionLevel.CONFIRM, description="Extract all text from screen via vision OCR")
class ReadScreenTextTool(Tool):
    name = "read_screen_text"
    description = "Capture screen and extract all readable text using vision model"
    permission = PermissionLevel.CONFIRM

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "monitor": {
                    "type": "integer",
                    "description": "Monitor index (0 = all combined, 1+ = specific monitor)",
                },
                "region": {
                    "type": "object",
                    "description": "Capture region as {left, top, right, bottom}",
                    "properties": {
                        "left": {"type": "integer"},
                        "top": {"type": "integer"},
                        "right": {"type": "integer"},
                        "bottom": {"type": "integer"},
                    },
                },
            },
            "required": [],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        ctx.check_cancelled()

        if not vision_is_available():
            return ToolResult.failure(
                "No vision model configured. Set up an online AI provider with vision support in settings."
            )

        monitor_index, region = _get_capture_args(args)

        try:
            image_bytes = await capture_screen_bytes(
                monitor_index=monitor_index,
                region=region,
            )

            ctx.check_cancelled()

            text_blocks = await extract_screen_text(image_bytes)

            # Check for errors
            if text_blocks and isinstance(text_blocks[0], dict) and "error" in text_blocks[0]:
                return ToolResult.failure(text_blocks[0]["error"])

            # Combine all text
            all_text = "\n".join(block.get("text", "") for block in text_blocks if isinstance(block, dict))

            return ToolResult.success(
                f"Extracted {len(text_blocks)} text blocks",
                data={"text": all_text, "blocks": text_blocks},
            )

        except Exception as e:
            _LOG.exception("Screen text extraction failed")
            return ToolResult.failure(f"Screen text extraction failed: {e}")


@tool("vision_describe", permission=PermissionLevel.CONFIRM, description="Describe what's on screen")
class VisionDescribeTool(Tool):
    name = "vision_describe"
    description = "Capture screen and get a natural language description"
    permission = PermissionLevel.CONFIRM

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "detail": {
                    "type": "string",
                    "description": "Level of detail",
                    "enum": ["brief", "normal", "detailed"],
                    "default": "normal",
                },
                "monitor": {
                    "type": "integer",
                    "description": "Monitor index (0 = all combined, 1+ = specific monitor)",
                },
                "region": {
                    "type": "object",
                    "description": "Capture region as {left, top, right, bottom}",
                    "properties": {
                        "left": {"type": "integer"},
                        "top": {"type": "integer"},
                        "right": {"type": "integer"},
                        "bottom": {"type": "integer"},
                    },
                },
            },
            "required": [],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        ctx.check_cancelled()

        if not vision_is_available():
            return ToolResult.failure(
                "No vision model configured. Set up an online AI provider with vision support in settings."
            )

        detail = args.get("detail", "normal")
        monitor_index, region = _get_capture_args(args)

        # Build prompt based on detail level
        prompts = {
            "brief": "Describe what you see in one sentence.",
            "normal": "Describe what you see in this screenshot in a few sentences. Include key UI elements, text, and overall layout.",
            "detailed": "Provide a detailed description of this screenshot. Include: all visible UI elements, text content, layout structure, colors, and any notable details.",
        }
        prompt = prompts.get(detail, prompts["normal"])

        try:
            image_bytes = await capture_screen_bytes(
                monitor_index=monitor_index,
                region=region,
            )

            ctx.check_cancelled()

            result = await vision_analyze(image_bytes, prompt)

            return _vision_result_to_toolresult(result)

        except Exception as e:
            _LOG.exception("Vision describe failed")
            return ToolResult.failure(f"Vision describe failed: {e}")


@tool("list_monitors", permission=PermissionLevel.SAFE, description="List available monitors")
class ListMonitorsTool(Tool):
    name = "list_monitors"
    description = "List all available monitors with their properties"
    permission = PermissionLevel.SAFE

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        ctx.check_cancelled()

        try:
            monitors = get_monitors()
            primary = get_primary_monitor()

            data = {
                "monitors": [
                    {
                        "index": m.index,
                        "left": m.left,
                        "top": m.top,
                        "width": m.width,
                        "height": m.height,
                        "is_primary": m.is_primary,
                        "area": m.area,
                    }
                    for m in monitors
                ],
                "primary_index": primary.index if primary else None,
                "count": len(monitors),
            }

            return ToolResult.success(
                f"Found {len(monitors)} monitor(s)",
                data=data,
            )

        except Exception as e:
            _LOG.exception("List monitors failed")
            return ToolResult.failure(f"List monitors failed: {e}")