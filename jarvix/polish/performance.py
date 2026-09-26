"""Performance monitoring for jarvix.

Tracks startup time, tool execution latency, memory usage, and lazy-import
heuristics.  All measurements are best-effort and never block the UI.
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from jarvix.core.logger import get_logger

_LOG = get_logger("jarvix.polish.performance")


class PerformanceMonitor:
    """Records timing and resource metrics for the application lifecycle."""

    def __init__(self) -> None:
        self._start_time: float = time.monotonic()
        self._checkpoints: Dict[str, float] = {}
        self._tool_timings: Dict[str, List[float]] = {}
        self._lazy_imports: Dict[str, float] = {}
        self._peak_memory: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def mark(self, label: str) -> None:
        """Record a checkpoint timestamp."""
        self._checkpoints[label] = time.monotonic() - self._start_time

    @contextmanager
    def measure(self, label: str):
        """Context manager that records elapsed time for ``label``."""
        start = time.monotonic()
        try:
            yield
        finally:
            elapsed = time.monotonic() - start
            self._tool_timings.setdefault(label, []).append(elapsed)
            if elapsed > 1.0:
                _LOG.warning("Slow operation: %s took %.2fs", label, elapsed)

    def record_lazy_import(self, module_name: str) -> None:
        """Record the time at which a module was first imported."""
        self._lazy_imports[module_name] = time.monotonic() - self._start_time

    def update_memory(self) -> None:
        """Sample current RSS and track the peak."""
        try:
            import psutil  # type: ignore
            rss = psutil.Process(os.getpid()).memory_info().rss
            if rss > self._peak_memory:
                self._peak_memory = rss
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def startup_report(self) -> Dict[str, Any]:
        """Return a dict suitable for logging or settings persistence."""
        self.update_memory()
        return {
            "startup_seconds": round(time.monotonic() - self._start_time, 3),
            "checkpoints": dict(self._checkpoints),
            "lazy_imports": {k: round(v, 3) for k, v in self._lazy_imports.items()},
            "peak_memory_mb": round(self._peak_memory / (1024 * 1024), 1),
            "tool_avg_ms": {
                name: round(sum(times) / len(times) * 1000, 1)
                for name, times in self._tool_timings.items()
                if times
            },
        }

    def slow_operations(self, threshold_seconds: float = 0.5) -> List[Dict[str, Any]]:
        """Return operations that exceeded ``threshold_seconds``."""
        slow: List[Dict[str, Any]] = []
        for name, times in self._tool_timings.items():
            for elapsed in times:
                if elapsed >= threshold_seconds:
                    slow.append({"name": name, "seconds": round(elapsed, 3)})
        return slow


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_performance: Optional[PerformanceMonitor] = None


def get_performance() -> PerformanceMonitor:
    """Return the global PerformanceMonitor singleton."""
    global _performance
    if _performance is None:
        _performance = PerformanceMonitor()
    return _performance


def measure(label: str):
    """Convenience wrapper around ``get_performance().measure(label)``."""
    return get_performance().measure(label)