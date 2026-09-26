"""Plugin management tools for jarvix.

These tools provide the CLI interface for managing plugins:
- plugin_list
- plugin_info
- plugin_enable / plugin_disable
- plugin_install
- plugin_uninstall
- plugin_update
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List

from jarvix.core.execution import ExecContext
from jarvix.core.logger import get_logger
from jarvix.core.permissions import PermissionLevel
from jarvix.core.tool_registry import Tool, ToolResult, tool
from jarvix.plugins.manager import get_plugin_manager
from jarvix.plugins.installer import install_from_path, validate_plugin_source
from jarvix.plugins.remover import uninstall_plugin
from jarvix.plugins.updater import get_updater

_LOG = get_logger("jarvix.tools.plugins")


@tool("plugin_list", permission=PermissionLevel.SAFE, description="List all installed plugins and their state")
class PluginListTool(Tool):
    name = "plugin_list"
    description = "List all installed plugins with their version, status, and enabled state"
    permission = PermissionLevel.SAFE

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "enabled_only": {
                    "type": "boolean",
                    "description": "Show only enabled plugins",
                    "default": False,
                },
            },
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        enabled_only = args.get("enabled_only", False)

        ctx.check_cancelled()

        try:
            mgr = get_plugin_manager()
            plugins = mgr.list_installed()

            if enabled_only:
                plugins = [p for p in plugins if p.enabled]

            if not plugins:
                return ToolResult.success("No plugins installed")

            lines = []
            for p in plugins:
                status = "enabled" if p.enabled else "disabled"
                if p.load_error:
                    status = f"error: {p.load_error}"
                elif p.loaded:
                    status += " (loaded)"
                else:
                    status += " (not loaded)"

                lines.append(f"  {p.name} v{p.manifest.version} - {status}")
                lines.append(f"    {p.manifest.description}")

            return ToolResult.success(
                f"Found {len(plugins)} plugin(s):\n" + "\n".join(lines),
                data={"plugins": [
                    {
                        "name": p.name,
                        "version": p.manifest.version,
                        "enabled": p.enabled,
                        "loaded": p.loaded,
                        "error": p.load_error,
                        "description": p.manifest.description,
                    }
                    for p in plugins
                ]}
            )
        except Exception as e:
            _LOG.exception("plugin_list failed")
            return ToolResult.failure(f"Failed to list plugins: {e}")


@tool("plugin_info", permission=PermissionLevel.SAFE, description="Show detailed information about a plugin")
class PluginInfoTool(Tool):
    name = "plugin_info"
    description = "Show detailed information about a specific plugin"
    permission = PermissionLevel.SAFE

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the plugin",
                },
            },
            "required": ["name"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        name = args.get("name", "").strip()

        if not name:
            return ToolResult.failure("Plugin name is required")

        ctx.check_cancelled()

        try:
            mgr = get_plugin_manager()
            state = mgr.get_plugin(name)

            if not state:
                return ToolResult.failure(f"Plugin '{name}' not found")

            m = state.manifest
            info_lines = [
                f"Name: {m.name}",
                f"Version: {m.version}",
                f"Description: {m.description}",
                f"Author: {m.author}",
                f"Homepage: {m.homepage or 'N/A'}",
                f"Enabled: {'Yes' if state.enabled else 'No'}",
                f"Loaded: {'Yes' if state.loaded else 'No'}",
                f"Load Error: {state.load_error or 'None'}",
                f"Path: {state.path}",
                f"Tools: {', '.join(m.tools) if m.tools else 'None'}",
                f"Permissions: {', '.join(m.permissions) if m.permissions else 'None'}",
                f"Min Jarvix Version: {m.min_jarvix_version or 'N/A'}",
            ]

            if m.settings_schema:
                info_lines.append(f"Settings Schema: {m.settings_schema}")

            return ToolResult.success(
                "\n".join(info_lines),
                data={
                    "name": m.name,
                    "version": m.version,
                    "description": m.description,
                    "author": m.author,
                    "homepage": m.homepage,
                    "enabled": state.enabled,
                    "loaded": state.loaded,
                    "load_error": state.load_error,
                    "path": state.path,
                    "tools": m.tools,
                    "permissions": m.permissions,
                    "min_jarvix_version": m.min_jarvix_version,
                    "settings_schema": m.settings_schema,
                }
            )
        except Exception as e:
            _LOG.exception("plugin_info failed")
            return ToolResult.failure(f"Failed to get plugin info: {e}")


@tool("plugin_enable", permission=PermissionLevel.CONFIRM, description="Enable a plugin")
class PluginEnableTool(Tool):
    name = "plugin_enable"
    description = "Enable a disabled plugin (loads its tools)"
    permission = PermissionLevel.CONFIRM

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the plugin to enable",
                },
            },
            "required": ["name"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        name = args.get("name", "").strip()

        if not name:
            return ToolResult.failure("Plugin name is required")

        ctx.check_cancelled()

        try:
            mgr = get_plugin_manager()
            if mgr.enable(name):
                return ToolResult.success(f"Enabled plugin: {name}")
            return ToolResult.failure(f"Plugin '{name}' not found")
        except Exception as e:
            _LOG.exception("plugin_enable failed")
            return ToolResult.failure(f"Failed to enable plugin: {e}")


@tool("plugin_disable", permission=PermissionLevel.CONFIRM, description="Disable a plugin")
class PluginDisableTool(Tool):
    name = "plugin_disable"
    description = "Disable an enabled plugin (unloads its tools)"
    permission = PermissionLevel.CONFIRM

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the plugin to disable",
                },
            },
            "required": ["name"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        name = args.get("name", "").strip()

        if not name:
            return ToolResult.failure("Plugin name is required")

        ctx.check_cancelled()

        try:
            mgr = get_plugin_manager()
            if mgr.disable(name):
                return ToolResult.success(f"Disabled plugin: {name}")
            return ToolResult.failure(f"Plugin '{name}' not found")
        except Exception as e:
            _LOG.exception("plugin_disable failed")
            return ToolResult.failure(f"Failed to disable plugin: {e}")


@tool("plugin_install", permission=PermissionLevel.CONFIRM, description="Install a plugin from a local path or archive")
class PluginInstallTool(Tool):
    name = "plugin_install"
    description = "Install a plugin from a local directory or archive (.zip, .tar.gz)"
    permission = PermissionLevel.CONFIRM

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to plugin directory or archive file",
                },
                "name": {
                    "type": "string",
                    "description": "Optional name override for the plugin",
                },
            },
            "required": ["path"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        path_str = args.get("path", "").strip()
        name = args.get("name", "").strip() or None

        if not path_str:
            return ToolResult.failure("Path is required")

        ctx.check_cancelled()

        try:
            mgr = get_plugin_manager()
            source_path = Path(path_str).expanduser().resolve()

            if not source_path.exists():
                return ToolResult.failure(f"Source not found: {source_path}")

            result = install_from_path(source_path, mgr, name)

            if result["success"]:
                return ToolResult.success(
                    f"Installed plugin: {result['plugin_name']} v{result.get('version', 'unknown')}",
                    data=result
                )
            return ToolResult.failure(result.get("error", "Install failed"))
        except Exception as e:
            _LOG.exception("plugin_install failed")
            return ToolResult.failure(f"Install failed: {e}")


@tool("plugin_uninstall", permission=PermissionLevel.CONFIRM, description="Uninstall a plugin")
class PluginUninstallTool(Tool):
    name = "plugin_uninstall"
    description = "Uninstall a plugin (removes files, tools, and settings)"
    permission = PermissionLevel.CONFIRM

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the plugin to uninstall",
                },
            },
            "required": ["name"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        name = args.get("name", "").strip()

        if not name:
            return ToolResult.failure("Plugin name is required")

        ctx.check_cancelled()

        try:
            mgr = get_plugin_manager()
            result = uninstall_plugin(name, mgr)

            if result["success"]:
                return ToolResult.success(f"Uninstalled plugin: {name}")
            return ToolResult.failure(result.get("error", "Uninstall failed"))
        except Exception as e:
            _LOG.exception("plugin_uninstall failed")
            return ToolResult.failure(f"Uninstall failed: {e}")


@tool("plugin_update", permission=PermissionLevel.CONFIRM, description="Check for or apply plugin updates")
class PluginUpdateTool(Tool):
    name = "plugin_update"
    description = "Check for plugin updates or apply available updates"
    permission = PermissionLevel.CONFIRM

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Optional plugin name to check/update (default: all)",
                },
                "apply": {
                    "type": "boolean",
                    "description": "Apply updates if available (default: false, just check)",
                    "default": False,
                },
            },
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        name = args.get("name", "").strip() or None
        apply = args.get("apply", False)

        ctx.check_cancelled()

        try:
            mgr = get_plugin_manager()
            updater = get_updater(mgr)

            if name:
                # Check specific plugin
                update = updater.check_plugin(name)
                if update:
                    if apply:
                        result = updater.apply_update(name)
                        if result["success"]:
                            return ToolResult.success(f"Updated {name} to {update.available_version}", data=result)
                        return ToolResult.failure(result.get("error", "Update failed"))
                    else:
                        return ToolResult.success(
                            f"Update available for {name}: {update.current_version} -> {update.available_version}",
                            data={"plugin": name, "current": update.current_version, "available": update.available_version}
                        )
                return ToolResult.success(f"No updates for {name}")
            else:
                # Check all plugins
                updates = updater.check_all()
                if updates:
                    if apply:
                        results = []
                        for u in updates:
                            result = updater.apply_update(u.plugin_name)
                            results.append({"plugin": u.plugin_name, **result})
                        return ToolResult.success(f"Applied {len(results)} updates", data={"results": results})
                    else:
                        lines = [f"  {u.plugin_name}: {u.current_version} -> {u.available_version}" for u in updates]
                        return ToolResult.success(
                            f"Updates available for {len(updates)} plugin(s):\n" + "\n".join(lines),
                            data={"updates": [
                                {"plugin": u.plugin_name, "current": u.current_version, "available": u.available_version}
                                for u in updates
                            ]}
                        )
                return ToolResult.success("All plugins are up to date")
        except Exception as e:
            _LOG.exception("plugin_update failed")
            return ToolResult.failure(f"Update failed: {e}")


# Register all plugin tools
def register_plugin_tools(tool_registry: Any) -> None:
    """Register all plugin management tools."""
    tool_registry.register("plugin_list", PluginListTool())
    tool_registry.register("plugin_info", PluginInfoTool())
    tool_registry.register("plugin_enable", PluginEnableTool())
    tool_registry.register("plugin_disable", PluginDisableTool())
    tool_registry.register("plugin_install", PluginInstallTool())
    tool_registry.register("plugin_uninstall", PluginUninstallTool())
    tool_registry.register("plugin_update", PluginUpdateTool())
    _LOG.info("Plugin management tools registered")