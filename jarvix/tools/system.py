"""System tools for jarvix (Phase 1: open_application only).

Uses subprocess.Popen which works without admin rights.
"""

from __future__ import annotations

import asyncio
import subprocess
from typing import Any, Dict

import shlex
from typing import Set

from jarvix.core.execution import ExecContext
from jarvix.core.logger import get_logger
from jarvix.core.tool_registry import Tool, ToolResult, tool
from jarvix.core.permissions import PermissionLevel

_LOG = get_logger("jarvix.tools.system")

# Safe executables only — no shell metacharacters can be injected.
_ALLOWED_EXECUTABLES: frozenset[str] = frozenset({
    "notepad", "calc", "explorer", "msedge", "chrome", "mspaint",
    "write", "winmine", "sol", "snippingtool", "wordpad", "powerpnt",
    "winword", "onenote", "teams",
})


def _sanitize_app_name(raw: str) -> tuple[str, bool]:
    """Parse and validate an application name.

    Returns (clean_exe_name, allowed).  ``allowed`` is False when the input
    attempts shell injection or is not in the allowlist.
    """
    try:
        tokens = shlex.split(raw)
    except ValueError:
        return "", False
    if not tokens:
        return "", False
    exe = tokens[0].strip().lower()
    # Reject anything that isn't a bare executable name (no path separators,
    # no shell operators, no spaces).
    if "\\" in exe or "/" in exe or ";" in exe or "&" in exe or "|" in exe:
        return "", False
    return exe, exe in _ALLOWED_EXECUTABLES


def _resolve_exe(exe: str) -> Optional[str]:
    """Resolve executable name to absolute path via shutil.which()."""
    import shutil
    exe_path = shutil.which(exe)
    if exe_path is None:
        return None
    # Verify the resolved path matches the requested name (prevents PATH poisoning)
    if Path(exe_path).name.lower() != exe:
        return None
    return exe_path


@tool("open_application", permission=PermissionLevel.SAFE, description="Open a Windows application by name")
class OpenApplicationTool(Tool):
    name = "open_application"
    description = "Open a Windows application by name (e.g. 'notepad', 'chrome', 'explorer')"
    permission = PermissionLevel.SAFE

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": "Name of the application to open (e.g. 'notepad', 'chrome', 'calc')",
                },
            },
            "required": ["app_name"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        raw = args.get("app_name", "").strip()
        if not raw:
            return ToolResult.failure("app_name is required")

        ctx.check_cancelled()

        exe, allowed = _sanitize_app_name(raw)
        if not allowed:
            return ToolResult.failure(
                f"Application '{raw}' is not permitted. "
                "Only safe executables are allowed (e.g. notepad, calc, explorer)."
            )

        exe_path = _resolve_exe(exe)
        if exe_path is None:
            return ToolResult.failure(f"Application '{exe}' not found in PATH")

        try:
            # shell=False prevents command injection; exe_path is absolute.
            proc = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda p=exe_path: subprocess.Popen(
                    [p],
                    shell=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                ),
            )
            _LOG.info("Opened application: %s (PID=%d)", exe, proc.pid)
            return ToolResult.success(f"Opened {exe}")
        except FileNotFoundError:
            return ToolResult.failure(f"Application '{exe}' not found in PATH")
        except Exception as e:
            _LOG.exception("Failed to open %s", exe)
            return ToolResult.failure(f"Failed to open '{exe}': {e}")