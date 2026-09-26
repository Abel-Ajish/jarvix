"""Screen capture for jarvix (Phase 7).

Uses mss (fast, multi-monitor) as primary backend with PIL fallback.
Returns PIL Images or saves to temporary files. Thread-safe for concurrent captures.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from jarvix.core.logger import get_logger

_LOG = get_logger("jarvix.vision.capture")

# Try to import mss (fast, multi-monitor support)
try:
    import mss
    HAS_MSS = True
except Exception:
    HAS_MSS = False
    _LOG.warning("mss not available, using PIL fallback for screen capture")

# PIL is required fallback
try:
    from PIL import Image, ImageGrab
    HAS_PIL = True
except Exception:
    HAS_PIL = False
    _LOG.warning("PIL not available, screen capture will fail")

# Thread-local storage for mss instances (not thread-safe to share)
_thread_local = threading.local()


@dataclass
class MonitorInfo:
    """Information about a monitor."""
    index: int
    left: int
    top: int
    width: int
    height: int
    is_primary: bool = False

    @property
    def rect(self) -> Tuple[int, int, int, int]:
        """Return (left, top, right, bottom)."""
        return (self.left, self.top, self.left + self.width, self.top + self.height)

    @property
    def area(self) -> int:
        return self.width * self.height


def _get_mss_instance() -> Optional["mss.mss"]:
    """Get thread-local mss instance."""
    if not HAS_MSS:
        return None
    if not hasattr(_thread_local, "sct"):
        _thread_local.sct = mss.mss()
    return _thread_local.sct


def _get_monitors_mss() -> List[MonitorInfo]:
    """Get monitor info using mss (includes all monitors)."""
    sct = _get_mss_instance()
    if not sct:
        return []

    monitors = []
    # mss.monitors[0] is the "all monitors combined" bounding box
    # mss.monitors[1:] are individual monitors
    for i, mon in enumerate(sct.monitors[1:], start=1):
        monitors.append(MonitorInfo(
            index=i,
            left=mon["left"],
            top=mon["top"],
            width=mon["width"],
            height=mon["height"],
            is_primary=(i == 1),  # First monitor is typically primary
        ))
    return monitors


def _get_monitors_pil() -> List[MonitorInfo]:
    """Get monitor info using PIL (single monitor only typically)."""
    if not HAS_PIL:
        return []

    # PIL's ImageGrab.grab() captures the primary monitor by default
    # For multi-monitor, we'd need platform-specific code
    try:
        # Grab a test image to get dimensions
        img = ImageGrab.grab()
        return [MonitorInfo(
            index=1,
            left=0,
            top=0,
            width=img.width,
            height=img.height,
            is_primary=True,
        )]
    except Exception:
        return []


def get_monitors() -> List[MonitorInfo]:
    """Get list of all monitors (mss preferred, PIL fallback)."""
    if HAS_MSS:
        return _get_monitors_mss()
    return _get_monitors_pil()


def get_primary_monitor() -> Optional[MonitorInfo]:
    """Get the primary monitor."""
    monitors = get_monitors()
    for m in monitors:
        if m.is_primary:
            return m
    return monitors[0] if monitors else None


async def capture_screen(
    *,
    monitor_index: Optional[int] = None,
    region: Optional[Tuple[int, int, int, int]] = None,
    save_path: Optional[str] = None,
) -> "Image.Image":
    """Capture screen to PIL Image.

    Args:
        monitor_index: 1-based monitor index (None = all monitors combined)
        region: (left, top, right, bottom) rectangle to capture
        save_path: If provided, save image to this path

    Returns:
        PIL Image of the capture
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _capture_screen_sync, monitor_index, region, save_path)


def _capture_screen_sync(
    monitor_index: Optional[int] = None,
    region: Optional[Tuple[int, int, int, int]] = None,
    save_path: Optional[str] = None,
) -> "Image.Image":
    """Synchronous screen capture (runs in executor)."""
    if not HAS_PIL:
        raise RuntimeError("PIL not available for screen capture")

    # Use mss if available (fast, multi-monitor)
    if HAS_MSS:
        return _capture_mss(monitor_index, region, save_path)

    # Fallback to PIL ImageGrab
    return _capture_pil(monitor_index, region, save_path)


def _capture_mss(
    monitor_index: Optional[int] = None,
    region: Optional[Tuple[int, int, int, int]] = None,
    save_path: Optional[str] = None,
) -> "Image.Image":
    """Capture using mss."""
    sct = _get_mss_instance()
    if not sct:
        raise RuntimeError("mss not initialized")

    if region:
        # Custom region: (left, top, right, bottom) -> mss format (left, top, width, height)
        left, top, right, bottom = region
        mon = {"left": left, "top": top, "width": right - left, "height": bottom - top}
        screenshot = sct.grab(mon)
        img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
    elif monitor_index is not None:
        # Specific monitor (1-based, 0 = all combined in mss)
        if monitor_index == 0:
            # All monitors combined
            mon = sct.monitors[0]
        elif 1 <= monitor_index < len(sct.monitors):
            mon = sct.monitors[monitor_index]
        else:
            raise ValueError(f"Invalid monitor index: {monitor_index}")
        screenshot = sct.grab(mon)
        img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
    else:
        # Default: all monitors combined (monitor 0 in mss)
        mon = sct.monitors[0]
        screenshot = sct.grab(mon)
        img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)

    if save_path:
        img.save(save_path)
        _LOG.debug("Saved screenshot to %s", save_path)

    return img


def _capture_pil(
    monitor_index: Optional[int] = None,
    region: Optional[Tuple[int, int, int, int]] = None,
    save_path: Optional[str] = None,
) -> "Image.Image":
    """Capture using PIL ImageGrab (single monitor fallback)."""
    if region:
        img = ImageGrab.grab(bbox=region)
    else:
        img = ImageGrab.grab()

    if save_path:
        img.save(save_path)
        _LOG.debug("Saved screenshot to %s", save_path)

    return img


def capture_to_temp(
    *,
    monitor_index: Optional[int] = None,
    region: Optional[Tuple[int, int, int, int]] = None,
    prefix: str = "jarvix_capture_",
    suffix: str = ".png",
) -> str:
    """Capture screen and save to a temporary file.

    Returns:
        Path to the temporary file
    """
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=suffix)
    os.close(fd)

    img = _capture_screen_sync(monitor_index=monitor_index, region=region, save_path=path)
    _LOG.debug("Captured screen to temp file: %s (%dx%d)", path, img.width, img.height)
    return path


async def capture_to_temp_async(
    *,
    monitor_index: Optional[int] = None,
    region: Optional[Tuple[int, int, int, int]] = None,
    prefix: str = "jarvix_capture_",
    suffix: str = ".png",
) -> str:
    """Async version of capture_to_temp."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, capture_to_temp, monitor_index, region, prefix, suffix)


def image_to_bytes(img: "Image.Image", format: str = "PNG") -> bytes:
    """Convert PIL Image to bytes."""
    from io import BytesIO
    buf = BytesIO()
    img.save(buf, format=format)
    return buf.getvalue()


async def capture_screen_bytes(
    *,
    monitor_index: Optional[int] = None,
    region: Optional[Tuple[int, int, int, int]] = None,
    format: str = "PNG",
) -> bytes:
    """Capture screen and return as bytes (for vision API)."""
    img = await capture_screen(monitor_index=monitor_index, region=region)
    return image_to_bytes(img, format)


def get_capture_backend() -> str:
    """Return the active capture backend name."""
    if HAS_MSS:
        return "mss"
    if HAS_PIL:
        return "PIL"
    return "none"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    "MonitorInfo",
    "get_monitors",
    "get_primary_monitor",
    "capture_screen",
    "capture_to_temp",
    "capture_to_temp_async",
    "capture_screen_bytes",
    "image_to_bytes",
    "get_capture_backend",
    "HAS_MSS",
    "HAS_PIL",
]