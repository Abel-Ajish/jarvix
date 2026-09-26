"""Vision subsystem for jarvix (Phase 7).

Provides screen capture, online vision analysis, UI element detection,
and vision settings panel.
"""

from __future__ import annotations

from jarvix.core.tool_registry import ToolRegistry
from jarvix.vision.capture import (
    capture_screen,
    capture_screen_bytes,
    capture_to_temp,
    capture_to_temp_async,
    get_monitors,
    get_primary_monitor,
    get_capture_backend,
    HAS_MSS,
    HAS_PIL,
    MonitorInfo,
)
from jarvix.vision.online_vision import (
    OnlineVision,
    VisionResult,
    get_online_vision,
    set_online_vision,
    vision_analyze,
    vision_analyze_file,
    vision_is_available,
    encode_image_base64,
    load_image_as_bytes,
    pil_image_to_bytes,
    get_vision_prompt,
    VISION_PROMPTS,
)
from jarvix.vision.ui_understanding import (
    UIElementType,
    UIElementState,
    BoundingBox,
    UIElement,
    UIAnalysisResult,
    detect_ui_elements,
    detect_ui_elements_from_screen,
    find_ui_element,
    find_ui_element_on_screen,
    extract_screen_text,
    extract_screen_text_from_screen,
    find_button,
    find_text_field,
    find_clickable_at,
    get_click_targets,
    get_input_targets,
    UI_DETECTION_PROMPT,
    ELEMENT_FIND_PROMPT,
    TEXT_EXTRACTION_PROMPT,
)


def register_vision_tools(registry: ToolRegistry) -> None:
    """Register all vision tools with the tool registry.

    This function imports and registers the tool classes from the tools module.
    """
    from jarvix.vision.tools import (
        ScreenCaptureTool,
        AnalyzeScreenTool,
        FindUIElementTool,
        ReadScreenTextTool,
        VisionDescribeTool,
        ListMonitorsTool,
    )

    for cls in (
        ScreenCaptureTool,
        AnalyzeScreenTool,
        FindUIElementTool,
        ReadScreenTextTool,
        VisionDescribeTool,
        ListMonitorsTool,
    ):
        registry.register(cls.name, cls())


# Auto-register UI panel on import
from jarvix.vision.ui_panel import register_vision_settings_tab
register_vision_settings_tab()


__all__ = [
    # Package metadata
    "register_vision_tools",

    # Capture
    "capture_screen",
    "capture_screen_bytes",
    "capture_to_temp",
    "capture_to_temp_async",
    "get_monitors",
    "get_primary_monitor",
    "get_capture_backend",
    "HAS_MSS",
    "HAS_PIL",
    "MonitorInfo",

    # Online vision
    "OnlineVision",
    "VisionResult",
    "get_online_vision",
    "set_online_vision",
    "vision_analyze",
    "vision_analyze_file",
    "vision_is_available",
    "encode_image_base64",
    "load_image_as_bytes",
    "pil_image_to_bytes",
    "get_vision_prompt",
    "VISION_PROMPTS",

    # UI understanding
    "UIElementType",
    "UIElementState",
    "BoundingBox",
    "UIElement",
    "UIAnalysisResult",
    "detect_ui_elements",
    "detect_ui_elements_from_screen",
    "find_ui_element",
    "find_ui_element_on_screen",
    "extract_screen_text",
    "extract_screen_text_from_screen",
    "find_button",
    "find_text_field",
    "find_clickable_at",
    "get_click_targets",
    "get_input_targets",
    "UI_DETECTION_PROMPT",
    "ELEMENT_FIND_PROMPT",
    "TEXT_EXTRACTION_PROMPT",
]