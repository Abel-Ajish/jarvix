"""Polish subsystem for jarvix (Phase 10).

Performance, UX, edge-case handling, and accessibility improvements.
"""

from __future__ import annotations

from jarvix.polish.performance import PerformanceMonitor, get_performance
from jarvix.polish.ux import UXImprovements, get_ux
from jarvix.polish.edge_cases import EdgeCaseHandler, get_edge_handler
from jarvix.polish.accessibility import AccessibilityManager, get_accessibility

__all__ = [
    "PerformanceMonitor",
    "get_performance",
    "UXImprovements",
    "get_ux",
    "EdgeCaseHandler",
    "get_edge_handler",
    "AccessibilityManager",
    "get_accessibility",
]