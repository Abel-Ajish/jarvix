"""UI element detection for jarvix (Phase 7).

Uses vision model to identify buttons, text fields, menus, etc. from screenshots.
Returns structured element list with bounding boxes, types, text content.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from jarvix.core.logger import get_logger
from jarvix.vision.online_vision import vision_analyze, vision_is_available
from jarvix.vision.capture import capture_screen_bytes

_LOG = get_logger("jarvix.vision.ui_understanding")


class UIElementType(str, Enum):
    """Types of UI elements."""
    BUTTON = "button"
    TEXT_FIELD = "text_field"
    TEXT_AREA = "text_area"
    LABEL = "label"
    CHECKBOX = "checkbox"
    RADIO_BUTTON = "radio_button"
    DROPDOWN = "dropdown"
    COMBOBOX = "combobox"
    MENU = "menu"
    MENU_ITEM = "menu_item"
    TAB = "tab"
    TAB_PANEL = "tab_panel"
    LINK = "link"
    IMAGE = "image"
    ICON = "icon"
    SLIDER = "slider"
    PROGRESS_BAR = "progress_bar"
    SCROLLBAR = "scrollbar"
    WINDOW = "window"
    DIALOG = "dialog"
    PANEL = "panel"
    TABLE = "table"
    TREE = "tree"
    LIST = "list"
    LIST_ITEM = "list_item"
    TOOLBAR = "toolbar"
    STATUSBAR = "statusbar"
    TOOLTIP = "tooltip"
    UNKNOWN = "unknown"


class UIElementState(str, Enum):
    """States of UI elements."""
    ENABLED = "enabled"
    DISABLED = "disabled"
    FOCUSED = "focused"
    HOVERED = "hovered"
    PRESSED = "pressed"
    CHECKED = "checked"
    UNCHECKED = "unchecked"
    SELECTED = "selected"
    EXPANDED = "expanded"
    COLLAPSED = "collapsed"
    HIDDEN = "hidden"
    READONLY = "readonly"


@dataclass
class BoundingBox:
    """Bounding box for a UI element."""
    x: int
    y: int
    width: int
    height: int

    @property
    def left(self) -> int:
        return self.x

    @property
    def top(self) -> int:
        return self.y

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def center(self) -> Tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x < self.right and self.y <= y < self.bottom

    def to_dict(self) -> Dict[str, int]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BoundingBox":
        return cls(
            x=data.get("x", 0),
            y=data.get("y", 0),
            width=data.get("width", 0),
            height=data.get("height", 0),
        )


@dataclass
class UIElement:
    """A detected UI element."""
    element_type: UIElementType
    bounds: BoundingBox
    text: str = ""
    label: str = ""
    state: UIElementState = UIElementState.ENABLED
    confidence: float = 0.0
    attributes: Dict[str, Any] = field(default_factory=dict)

    @property
    def center(self) -> Tuple[int, int]:
        return self.bounds.center

    @property
    def clickable(self) -> bool:
        """Whether this element is typically clickable."""
        return self.element_type in {
            UIElementType.BUTTON,
            UIElementType.LINK,
            UIElementType.CHECKBOX,
            UIElementType.RADIO_BUTTON,
            UIElementType.DROPDOWN,
            UIElementType.COMBOBOX,
            UIElementType.MENU_ITEM,
            UIElementType.TAB,
            UIElementType.ICON,
        }

    @property
    def input_capable(self) -> bool:
        """Whether this element accepts text input."""
        return self.element_type in {
            UIElementType.TEXT_FIELD,
            UIElementType.TEXT_AREA,
            UIElementType.COMBOBOX,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.element_type.value,
            "bounds": self.bounds.to_dict(),
            "text": self.text,
            "label": self.label,
            "state": self.state.value,
            "confidence": self.confidence,
            "attributes": self.attributes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UIElement":
        return cls(
            element_type=UIElementType(data.get("type", "unknown")),
            bounds=BoundingBox.from_dict(data.get("bounds", {})),
            text=data.get("text", ""),
            label=data.get("label", ""),
            state=UIElementState(data.get("state", "enabled")),
            confidence=data.get("confidence", 0.0),
            attributes=data.get("attributes", {}),
        )


@dataclass
class UIAnalysisResult:
    """Result of UI analysis."""
    elements: List[UIElement]
    screen_size: Tuple[int, int]
    raw_response: str = ""
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def get_elements_by_type(self, element_type: UIElementType) -> List[UIElement]:
        """Filter elements by type."""
        return [e for e in self.elements if e.element_type == element_type]

    def get_clickable_elements(self) -> List[UIElement]:
        """Get all clickable elements."""
        return [e for e in self.elements if e.clickable]

    def get_input_elements(self) -> List[UIElement]:
        """Get all input-capable elements."""
        return [e for e in self.elements if e.input_capable]

    def find_element_by_text(self, text: str, exact: bool = False) -> Optional[UIElement]:
        """Find element containing text."""
        for e in self.elements:
            if exact:
                if e.text == text or e.label == text:
                    return e
            else:
                if text.lower() in e.text.lower() or text.lower() in e.label.lower():
                    return e
        return None

    def find_element_at(self, x: int, y: int) -> Optional[UIElement]:
        """Find element at screen coordinates."""
        for e in self.elements:
            if e.bounds.contains(x, y):
                return e
        return None


# ---------------------------------------------------------------------------
# Prompt engineering for UI detection
# ---------------------------------------------------------------------------

UI_DETECTION_PROMPT = """Analyze this screenshot and identify ALL visible UI elements.

Return a JSON array of objects with these fields:
- type: one of [button, text_field, text_area, label, checkbox, radio_button, dropdown, combobox, menu, menu_item, tab, tab_panel, link, image, icon, slider, progress_bar, scrollbar, window, dialog, panel, table, tree, list, list_item, toolbar, statusbar, tooltip, unknown]
- bounds: {x, y, width, height} in pixels (top-left origin)
- text: any visible text on/in the element
- label: accessible name/label (if different from text)
- state: one of [enabled, disabled, focused, hovered, pressed, checked, unchecked, selected, expanded, collapsed, hidden, readonly]
- confidence: 0.0-1.0 detection confidence
- attributes: any additional properties (e.g., {"placeholder": "Search...", "required": true})

Include ALL interactive elements and significant static elements.
Be precise with bounding boxes - they will be used for click coordinates.
Only return the JSON array, no extra text."""


ELEMENT_FIND_PROMPT = """Find the {element_description} in this screenshot.

Return a single JSON object with:
- type: element type
- bounds: {{x, y, width, height}}
- text: visible text
- label: accessible label
- state: element state
- confidence: 0.0-1.0
- attributes: additional properties

If not found, return {{"found": false}}.
Only return the JSON object."""


TEXT_EXTRACTION_PROMPT = """Extract ALL readable text from this screenshot.

Return a JSON array of text blocks:
- text: the text content
- bounds: {x, y, width, height} of the text region
- type: likely element type (label, button, heading, paragraph, etc.)

Preserve reading order (top-to-bottom, left-to-right).
Only return the JSON array."""


# ---------------------------------------------------------------------------
# Core analysis functions
# ---------------------------------------------------------------------------

async def detect_ui_elements(
    image_bytes: bytes,
    *,
    confidence_threshold: float = 0.3,
) -> UIAnalysisResult:
    """Detect all UI elements in a screenshot.

    Args:
        image_bytes: Screenshot bytes
        confidence_threshold: Minimum confidence to include element

    Returns:
        UIAnalysisResult with detected elements
    """
    if not vision_is_available():
        return UIAnalysisResult(
            elements=[],
            screen_size=(0, 0),
            error="No vision model configured. Set up an online AI provider in settings.",
        )

    try:
        response = await vision_analyze(image_bytes, UI_DETECTION_PROMPT)

        if not response.ok:
            return UIAnalysisResult(
                elements=[],
                screen_size=(0, 0),
                error=response.error,
            )

        # Parse JSON response
        elements = _parse_elements_response(response.text, confidence_threshold)

        # Estimate screen size from image (we'd need PIL to get exact size)
        # For now, derive from max bounds
        screen_width = max((e.bounds.right for e in elements), default=1920)
        screen_height = max((e.bounds.bottom for e in elements), default=1080)

        return UIAnalysisResult(
            elements=elements,
            screen_size=(screen_width, screen_height),
            raw_response=response.text,
        )

    except Exception as e:
        _LOG.exception("UI detection failed")
        return UIAnalysisResult(
            elements=[],
            screen_size=(0, 0),
            error=f"UI detection failed: {e}",
        )


async def detect_ui_elements_from_screen(
    *,
    monitor_index: Optional[int] = None,
    region: Optional[Tuple[int, int, int, int]] = None,
    confidence_threshold: float = 0.3,
) -> UIAnalysisResult:
    """Capture screen and detect UI elements."""
    image_bytes = await capture_screen_bytes(
        monitor_index=monitor_index,
        region=region,
    )
    return await detect_ui_elements(image_bytes, confidence_threshold=confidence_threshold)


async def find_ui_element(
    image_bytes: bytes,
    element_description: str,
) -> Optional[UIElement]:
    """Find a specific UI element by description.

    Args:
        image_bytes: Screenshot bytes
        element_description: Natural language description (e.g., "the submit button", "search box")

    Returns:
        UIElement if found, None otherwise
    """
    if not vision_is_available():
        _LOG.warning("No vision model available for element finding")
        return None

    prompt = ELEMENT_FIND_PROMPT.format(element_description=element_description)

    try:
        response = await vision_analyze(image_bytes, prompt)

        if not response.ok:
            return None

        data = json.loads(response.text)
        if not data.get("found", True):
            return None

        return UIElement.from_dict(data)

    except Exception as e:
        _LOG.exception("Find UI element failed")
        return None


async def find_ui_element_on_screen(
    element_description: str,
    *,
    monitor_index: Optional[int] = None,
    region: Optional[Tuple[int, int, int, int]] = None,
) -> Optional[UIElement]:
    """Capture screen and find a specific UI element."""
    image_bytes = await capture_screen_bytes(
        monitor_index=monitor_index,
        region=region,
    )
    return await find_ui_element(image_bytes, element_description)


async def extract_screen_text(
    image_bytes: bytes,
) -> List[Dict[str, Any]]:
    """Extract all readable text from screenshot with positions.

    Returns:
        List of dicts with text, bounds, type
    """
    if not vision_is_available():
        return [{"error": "No vision model configured"}]

    try:
        response = await vision_analyze(image_bytes, TEXT_EXTRACTION_PROMPT)

        if not response.ok:
            return [{"error": response.error}]

        return json.loads(response.text)

    except Exception as e:
        _LOG.exception("Text extraction failed")
        return [{"error": f"Text extraction failed: {e}"}]


async def extract_screen_text_from_screen(
    *,
    monitor_index: Optional[int] = None,
    region: Optional[Tuple[int, int, int, int]] = None,
) -> List[Dict[str, Any]]:
    """Capture screen and extract text."""
    image_bytes = await capture_screen_bytes(
        monitor_index=monitor_index,
        region=region,
    )
    return await extract_screen_text(image_bytes)


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_elements_response(
    response_text: str,
    confidence_threshold: float,
) -> List[UIElement]:
    """Parse vision model response into UIElement list."""
    elements = []

    # Try to find JSON array in response
    json_text = _extract_json_array(response_text)
    if not json_text:
        _LOG.warning("No JSON array found in vision response")
        return elements

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as e:
        _LOG.warning("Failed to parse vision response JSON: %s", e)
        return elements

    if not isinstance(data, list):
        _LOG.warning("Vision response is not an array")
        return elements

    for item in data:
        try:
            element = UIElement.from_dict(item)
            if element.confidence >= confidence_threshold:
                elements.append(element)
        except Exception as e:
            _LOG.debug("Failed to parse element: %s", e)
            continue

    return elements


def _extract_json_array(text: str) -> Optional[str]:
    """Extract JSON array from text (handles markdown code blocks)."""
    # Try to find ```json ... ``` or ``` ... ```
    code_block_pattern = r"```(?:json)?\s*(\[.*?\])\s*```"
    match = re.search(code_block_pattern, text, re.DOTALL)
    if match:
        return match.group(1)

    # Try to find bare array
    array_pattern = r"(\[.*?\])"
    match = re.search(array_pattern, text, re.DOTALL)
    if match:
        return match.group(1)

    return None


# ---------------------------------------------------------------------------
# High-level helpers
# ---------------------------------------------------------------------------

async def find_button(
    image_bytes: bytes,
    label: str,
) -> Optional[UIElement]:
    """Find a button by its label/text."""
    return await find_ui_element(image_bytes, f"button labeled '{label}'")


async def find_text_field(
    image_bytes: bytes,
    placeholder_or_label: str,
) -> Optional[UIElement]:
    """Find a text field by placeholder or label."""
    return await find_ui_element(image_bytes, f"text field with '{placeholder_or_label}'")


async def find_clickable_at(
    image_bytes: bytes,
    x: int,
    y: int,
) -> Optional[UIElement]:
    """Find clickable element at coordinates."""
    result = await detect_ui_elements(image_bytes)
    if not result.ok:
        return None

    for element in result.get_clickable_elements():
        if element.bounds.contains(x, y):
            return element
    return None


async def get_click_targets(
    image_bytes: bytes,
) -> List[UIElement]:
    """Get all clickable elements (buttons, links, etc.)."""
    result = await detect_ui_elements(image_bytes)
    if not result.ok:
        return []
    return result.get_clickable_elements()


async def get_input_targets(
    image_bytes: bytes,
) -> List[UIElement]:
    """Get all text input elements."""
    result = await detect_ui_elements(image_bytes)
    if not result.ok:
        return []
    return result.get_input_elements()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
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