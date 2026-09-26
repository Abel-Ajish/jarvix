"""Structured logging for jarvix.

All subsystems use this logger.  The `sensitive=True` flag causes the
message field to be redacted in file output (console still prints it).
Never log API keys, raw prompts, or audio bytes.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

from jarvix.core.events import EventBus, ErrorRaised

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_LOG_DIR = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming")) / "jarvix" / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

_LOG_FILE = _LOG_DIR / "jarvix.log"
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_BACKUP_COUNT = 3


class SensitiveFormatter(logging.Formatter):
    """Formatter that redacts `record.message` if `record.sensitive` is True."""

    def format(self, record: logging.LogRecord) -> str:
        if getattr(record, "sensitive", False):
            record.message = "[REDACTED]"
        return super().format(record)


def get_logger(name: str, *, level: int = logging.INFO) -> logging.Logger:
    """Create or retrieve a configured logger for ``name``.

    The logger writes to both console (colorized if available) and a
    rotating file under ``%APPDATA%/jarvix/logs/jarvix.log``.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    logger.propagate = False

    fmt = "%(asctime)s %(levelname)-8s %(name)s %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(SensitiveFormatter(fmt, datefmt))  # Redact secrets in console too
    logger.addHandler(ch)

    # Rotating file handler with sensitive redaction
    fh = logging.handlers.RotatingFileHandler(
        _LOG_FILE, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
    )
    fh.setFormatter(SensitiveFormatter(fmt, datefmt))
    logger.addHandler(fh)

    return logger


# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------

def log_event(bus: EventBus, level: int, component: str, message: str,
              *, sensitive: bool = False, extra: Optional[dict] = None) -> None:
    """Log to both the logger and the event bus (for UI)."""
    logger = get_logger(f"jarvix.{component}")
    extra_dict = {"sensitive": sensitive}
    if extra:
        extra_dict.update(extra)
    logger.log(level, message, extra=extra_dict)

    if level >= logging.ERROR:
        bus.publish(ErrorRaised(message, component=component))