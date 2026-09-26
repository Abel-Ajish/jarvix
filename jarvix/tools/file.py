"""File system tools for jarvix.

All file operations are scoped to permitted paths. When path restrictions
are enabled (via settings), access outside permitted directories is denied.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import stat
from pathlib import Path
from typing import Any, Dict, List

from jarvix.core.config import get_settings
from jarvix.core.execution import ExecContext
from jarvix.core.logger import get_logger
from jarvix.core.permissions import PermissionLevel
from jarvix.core.tool_registry import Tool, ToolResult, tool

_LOG = get_logger("jarvix.tools.file")


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------

def _get_permitted_paths() -> List[Path]:
    """Get list of permitted root paths from settings."""
    settings = get_settings()
    paths = settings.get("file.permitted_paths", [])
    if not paths:
        # Default to user's home directory
        return [Path.home()]
    return [Path(p).expanduser().resolve() for p in paths]


def _is_path_permitted(path: Path) -> bool:
    """Check if a path is within permitted directories."""
    try:
        resolved = path.resolve()
    except Exception:
        return False

    for permitted in _get_permitted_paths():
        try:
            resolved.relative_to(permitted)
            return True
        except ValueError:
            continue
    return False


def _validate_path(path: Path, *, must_exist: bool = False) -> Path:
    """Validate and resolve a path, checking permissions."""
    if not _is_path_permitted(path):
        raise PermissionError(f"Access denied: '{path}' is outside permitted directories")

    if must_exist and not path.exists():
        raise FileNotFoundError(f"Path not found: {path}")

    return path.resolve()


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool("create_file", permission=PermissionLevel.CONFIRM, description="Create a new file with content")
class CreateFileTool(Tool):
    name = "create_file"
    description = "Create a new file with the given content"
    permission = PermissionLevel.CONFIRM

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path of the file to create"},
                "content": {"type": "string", "description": "Content to write to the file", "default": ""},
                "overwrite": {"type": "boolean", "description": "Overwrite if file exists", "default": False},
            },
            "required": ["path"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        path = Path(args.get("path", "")).expanduser()
        content = args.get("content", "")
        overwrite = args.get("overwrite", False)

        ctx.check_cancelled()

        try:
            validated = _validate_path(path)
            if validated.exists() and not overwrite:
                return ToolResult.failure(f"File already exists: {validated}. Use overwrite=true to replace.")
            validated.parent.mkdir(parents=True, exist_ok=True)
            validated.write_text(content, encoding="utf-8")
            _LOG.info("Created file: %s", validated)
            return ToolResult.success(f"Created file: {validated}")
        except PermissionError as e:
            return ToolResult.failure(str(e))
        except Exception as e:
            _LOG.exception("Failed to create file")
            return ToolResult.failure(f"Failed to create file: {e}")


@tool("read_file", permission=PermissionLevel.SAFE, description="Read the contents of a file")
class ReadFileTool(Tool):
    name = "read_file"
    description = "Read the contents of a file"
    permission = PermissionLevel.SAFE

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path of the file to read"},
                "max_bytes": {"type": "integer", "description": "Maximum bytes to read (0 = no limit)", "default": 0},
            },
            "required": ["path"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        path = Path(args.get("path", "")).expanduser()
        max_bytes = args.get("max_bytes", 0)

        ctx.check_cancelled()

        try:
            validated = _validate_path(path, must_exist=True)
            if max_bytes > 0:
                content = validated.read_bytes()[:max_bytes].decode("utf-8", errors="replace")
            else:
                content = validated.read_text(encoding="utf-8")
            return ToolResult.success(content, data={"path": str(validated), "size": validated.stat().st_size})
        except PermissionError as e:
            return ToolResult.failure(str(e))
        except FileNotFoundError as e:
            return ToolResult.failure(str(e))
        except Exception as e:
            _LOG.exception("Failed to read file")
            return ToolResult.failure(f"Failed to read file: {e}")


@tool("write_file", permission=PermissionLevel.CONFIRM, description="Write content to a file (overwrites)")
class WriteFileTool(Tool):
    name = "write_file"
    description = "Write content to a file, overwriting if it exists"
    permission = PermissionLevel.CONFIRM

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path of the file to write"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        path = Path(args.get("path", "")).expanduser()
        content = args.get("content", "")

        ctx.check_cancelled()

        try:
            validated = _validate_path(path)
            validated.parent.mkdir(parents=True, exist_ok=True)
            validated.write_text(content, encoding="utf-8")
            _LOG.info("Wrote file: %s", validated)
            return ToolResult.success(f"Wrote file: {validated}")
        except PermissionError as e:
            return ToolResult.failure(str(e))
        except Exception as e:
            _LOG.exception("Failed to write file")
            return ToolResult.failure(f"Failed to write file: {e}")


@tool("copy_file", permission=PermissionLevel.CONFIRM, description="Copy a file to a new location")
class CopyFileTool(Tool):
    name = "copy_file"
    description = "Copy a file to a new location"
    permission = PermissionLevel.CONFIRM

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Source file path"},
                "destination": {"type": "string", "description": "Destination file path"},
                "overwrite": {"type": "boolean", "description": "Overwrite if destination exists", "default": False},
            },
            "required": ["source", "destination"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        source = Path(args.get("source", "")).expanduser()
        dest = Path(args.get("destination", "")).expanduser()
        overwrite = args.get("overwrite", False)

        ctx.check_cancelled()

        try:
            src_validated = _validate_path(source, must_exist=True)
            dst_validated = _validate_path(dest)
            if dst_validated.exists() and not overwrite:
                return ToolResult.failure(f"Destination already exists: {dst_validated}. Use overwrite=true to replace.")
            dst_validated.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.get_running_loop().run_in_executor(None, lambda: shutil.copy2(src_validated, dst_validated))
            _LOG.info("Copied %s -> %s", src_validated, dst_validated)
            return ToolResult.success(f"Copied {src_validated} -> {dst_validated}")
        except PermissionError as e:
            return ToolResult.failure(str(e))
        except Exception as e:
            _LOG.exception("Failed to copy file")
            return ToolResult.failure(f"Failed to copy file: {e}")


@tool("move_file", permission=PermissionLevel.CONFIRM, description="Move/rename a file")
class MoveFileTool(Tool):
    name = "move_file"
    description = "Move a file to a new location (rename)"
    permission = PermissionLevel.CONFIRM

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Source file path"},
                "destination": {"type": "string", "description": "Destination file path"},
                "overwrite": {"type": "boolean", "description": "Overwrite if destination exists", "default": False},
            },
            "required": ["source", "destination"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        source = Path(args.get("source", "")).expanduser()
        dest = Path(args.get("destination", "")).expanduser()
        overwrite = args.get("overwrite", False)

        ctx.check_cancelled()

        try:
            src_validated = _validate_path(source, must_exist=True)
            dst_validated = _validate_path(dest)
            if dst_validated.exists() and not overwrite:
                return ToolResult.failure(f"Destination already exists: {dst_validated}. Use overwrite=true to replace.")
            dst_validated.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.get_running_loop().run_in_executor(None, lambda: shutil.move(str(src_validated), str(dst_validated)))
            _LOG.info("Moved %s -> %s", src_validated, dst_validated)
            return ToolResult.success(f"Moved {src_validated} -> {dst_validated}")
        except PermissionError as e:
            return ToolResult.failure(str(e))
        except Exception as e:
            _LOG.exception("Failed to move file")
            return ToolResult.failure(f"Failed to move file: {e}")


@tool("rename_file", permission=PermissionLevel.CONFIRM, description="Rename a file (same directory)")
class RenameFileTool(Tool):
    name = "rename_file"
    description = "Rename a file within the same directory"
    permission = PermissionLevel.CONFIRM

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Current file path"},
                "new_name": {"type": "string", "description": "New file name (not full path)"},
            },
            "required": ["path", "new_name"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        path = Path(args.get("path", "")).expanduser()
        new_name = args.get("new_name", "").strip()

        ctx.check_cancelled()

        if not new_name:
            return ToolResult.failure("new_name is required")

        try:
            validated = _validate_path(path, must_exist=True)
            new_path = validated.parent / new_name
            dst_validated = _validate_path(new_path)
            if dst_validated.exists():
                return ToolResult.failure(f"File already exists: {dst_validated}")
            await asyncio.get_running_loop().run_in_executor(None, lambda: validated.rename(dst_validated))
            _LOG.info("Renamed %s -> %s", validated, dst_validated)
            return ToolResult.success(f"Renamed {validated.name} -> {new_name}")
        except PermissionError as e:
            return ToolResult.failure(str(e))
        except Exception as e:
            _LOG.exception("Failed to rename file")
            return ToolResult.failure(f"Failed to rename file: {e}")


@tool("delete_file", permission=PermissionLevel.CONFIRM, description="Delete a file")
class DeleteFileTool(Tool):
    name = "delete_file"
    description = "Delete a file permanently"
    permission = PermissionLevel.CONFIRM

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path of the file to delete"},
            },
            "required": ["path"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        path = Path(args.get("path", "")).expanduser()

        ctx.check_cancelled()

        try:
            validated = _validate_path(path, must_exist=True)
            if validated.is_dir():
                return ToolResult.failure(f"Path is a directory, use delete_folder: {validated}")
            await asyncio.get_running_loop().run_in_executor(None, validated.unlink)
            _LOG.info("Deleted file: %s", validated)
            return ToolResult.success(f"Deleted file: {validated}")
        except PermissionError as e:
            return ToolResult.failure(str(e))
        except FileNotFoundError as e:
            return ToolResult.failure(str(e))
        except Exception as e:
            _LOG.exception("Failed to delete file")
            return ToolResult.failure(f"Failed to delete file: {e}")


@tool("create_folder", permission=PermissionLevel.CONFIRM, description="Create a new directory")
class CreateFolderTool(Tool):
    name = "create_folder"
    description = "Create a new directory (folder)"
    permission = PermissionLevel.CONFIRM

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path of the folder to create"},
                "parents": {"type": "boolean", "description": "Create parent directories if needed", "default": True},
            },
            "required": ["path"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        path = Path(args.get("path", "")).expanduser()
        parents = args.get("parents", True)

        ctx.check_cancelled()

        try:
            validated = _validate_path(path)
            await asyncio.get_running_loop().run_in_executor(None, lambda: validated.mkdir(parents=parents, exist_ok=True))
            _LOG.info("Created folder: %s", validated)
            return ToolResult.success(f"Created folder: {validated}")
        except PermissionError as e:
            return ToolResult.failure(str(e))
        except Exception as e:
            _LOG.exception("Failed to create folder")
            return ToolResult.failure(f"Failed to create folder: {e}")


@tool("delete_folder", permission=PermissionLevel.CONFIRM, description="Delete a directory (recursively)")
class DeleteFolderTool(Tool):
    name = "delete_folder"
    description = "Delete a directory and all its contents"
    permission = PermissionLevel.CONFIRM

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path of the folder to delete"},
                "recursive": {"type": "boolean", "description": "Delete non-empty folder recursively", "default": True},
            },
            "required": ["path"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        path = Path(args.get("path", "")).expanduser()
        recursive = args.get("recursive", True)

        ctx.check_cancelled()

        try:
            validated = _validate_path(path, must_exist=True)
            if not validated.is_dir():
                return ToolResult.failure(f"Path is not a directory: {validated}")
            if recursive:
                await asyncio.get_running_loop().run_in_executor(None, lambda: shutil.rmtree(validated))
            else:
                await asyncio.get_running_loop().run_in_executor(None, validated.rmdir)
            _LOG.info("Deleted folder: %s", validated)
            return ToolResult.success(f"Deleted folder: {validated}")
        except PermissionError as e:
            return ToolResult.failure(str(e))
        except Exception as e:
            _LOG.exception("Failed to delete folder")
            return ToolResult.failure(f"Failed to delete folder: {e}")


@tool("search_files", permission=PermissionLevel.SAFE, description="Search for files by name/pattern")
class SearchFilesTool(Tool):
    name = "search_files"
    description = "Search for files matching a pattern within permitted directories"
    permission = PermissionLevel.SAFE

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern to match (e.g. '*.txt', '**/*.py')"},
                "root": {"type": "string", "description": "Root directory to search (default: first permitted path)"},
                "max_results": {"type": "integer", "description": "Maximum number of results", "default": 50},
            },
            "required": ["pattern"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        pattern = args.get("pattern", "").strip()
        root_str = args.get("root", "")
        max_results = args.get("max_results", 50)

        if not pattern:
            return ToolResult.failure("pattern is required")

        ctx.check_cancelled()

        try:
            if root_str:
                root = _validate_path(Path(root_str).expanduser(), must_exist=True)
            else:
                root = _get_permitted_paths()[0]

            results: List[Dict[str, Any]] = []
            for path in root.rglob(pattern):
                if len(results) >= max_results:
                    break
                if _is_path_permitted(path):
                    try:
                        stat = path.stat()
                        results.append({
                            "path": str(path),
                            "name": path.name,
                            "is_dir": path.is_dir(),
                            "size": stat.st_size,
                            "modified": stat.st_mtime,
                        })
                    except OSError:
                        pass

            return ToolResult.success(
                f"Found {len(results)} matches",
                data={"results": results, "root": str(root), "pattern": pattern}
            )
        except PermissionError as e:
            return ToolResult.failure(str(e))
        except Exception as e:
            _LOG.exception("Failed to search files")
            return ToolResult.failure(f"Failed to search files: {e}")