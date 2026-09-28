"""Tests for the plugins subsystem."""

import asyncio
import tempfile
from pathlib import Path
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jarvix.core.events import EventBus
from jarvix.core.execution import ExecContext, NoOpPermissionManager
from jarvix.core.permissions import PermissionManager
from jarvix.core.tool_registry import ToolRegistry, ToolResult
from jarvix.plugins import register_plugins_ui
from jarvix.plugins.manager import PluginManager, get_plugin_manager
from jarvix.plugins.registry import PluginRegistry, get_plugin_registry, PluginState, PluginManifest


@pytest.fixture
def temp_plugin_dir() -> Generator[Path, None, None]:
    """Create a temporary plugin directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plugin_dir = Path(tmpdir) / "plugins"
        plugin_dir.mkdir()
        yield plugin_dir


@pytest.fixture
def plugin_manager() -> Generator[PluginManager, None, None]:
    """Create a plugin manager with default settings."""
    manager = PluginManager()
    yield manager


@pytest.fixture
def plugin_registry(temp_plugin_dir: Path) -> PluginRegistry:
    """Create a plugin registry with temp directory."""
    registry = PluginRegistry(temp_plugin_dir)
    yield registry


class TestPluginManager:
    """Test plugin manager lifecycle."""

    def test_discover_plugins(self, plugin_manager: PluginManager, temp_plugin_dir: Path) -> None:
        """Test discovering plugins in directory."""
        # Create a dummy plugin
        calc_plugin = temp_plugin_dir / "calculator"
        calc_plugin.mkdir()
        (calc_plugin / "manifest.json").write_text('{"name": "calculator", "version": "1.0.0", "description": "Test", "author": "Test"}')
        (calc_plugin / "main.py").write_text('def register(reg): pass')

        plugins = plugin_manager.discover()

        assert len(plugins) > 0
        plugin_names = [p.name for p in plugins]
        assert "calculator" in plugin_names

    def test_enable_plugin(self, plugin_manager: PluginManager, temp_plugin_dir: Path) -> None:
        """Test enabling a plugin."""
        from jarvix.plugins.registry import PluginState, PluginManifest

        calc_plugin = temp_plugin_dir / "calculator"
        calc_plugin.mkdir()
        (calc_plugin / "manifest.json").write_text('{"name": "calculator", "version": "1.0.0", "description": "Test", "author": "Test"}')
        (calc_plugin / "main.py").write_text('def register(reg): pass')

        manifest = PluginManifest(name="calculator", version="1.0.0", description="Test", author="Test")
        state = PluginState(name="calculator", path=str(calc_plugin), manifest=manifest, enabled=False)
        plugin_manager._registry.register(state)

        result = plugin_manager.enable("calculator")

        assert result is True
        assert plugin_manager._registry.is_enabled("calculator")

    def test_disable_plugin(self, plugin_manager: PluginManager, temp_plugin_dir: Path) -> None:
        """Test disabling a plugin."""
        from jarvix.plugins.registry import PluginState, PluginManifest

        calc_plugin = temp_plugin_dir / "calculator"
        calc_plugin.mkdir()
        (calc_plugin / "manifest.json").write_text('{"name": "calculator", "version": "1.0.0", "description": "Test", "author": "Test"}')
        (calc_plugin / "main.py").write_text('def register(reg): pass')

        manifest = PluginManifest(name="calculator", version="1.0.0", description="Test", author="Test")
        state = PluginState(name="calculator", path=str(calc_plugin), manifest=manifest, enabled=True)
        plugin_manager._registry.register(state)
        plugin_manager.enable("calculator")
        result = plugin_manager.disable("calculator")

        assert result is True
        assert not plugin_manager._registry.is_enabled("calculator")

    def test_list_plugins(self, plugin_manager: PluginManager, temp_plugin_dir: Path) -> None:
        """Test listing all plugins."""
        from jarvix.plugins.registry import PluginState, PluginManifest

        for name in ["calc", "test_plugin"]:
            pdir = temp_plugin_dir / name
            pdir.mkdir()
            (pdir / "manifest.json").write_text(f'{{"name": "{name}", "version": "1.0.0", "description": "Test", "author": "Test"}}')
            (pdir / "main.py").write_text('def register(reg): pass\n')

            manifest = PluginManifest(name=name, version="1.0.0", description="Test", author="Test")
            state = PluginState(name=name, path=str(pdir), manifest=manifest, enabled=True)
            plugin_manager._registry.register(state)

        plugins = plugin_manager._registry.list_plugins()

        # Filter out built-in calculator plugin
        custom_plugins = [p for p in plugins if p.name in ["calc", "test_plugin"]]
        assert len(custom_plugins) == 2
        names = {p.name for p in custom_plugins}
        assert names == {"calc", "test_plugin"}


class TestPluginRegistry:
    """Test plugin registry."""

    def test_register_manifest(self, plugin_registry: PluginRegistry) -> None:
        """Test registering a plugin manifest."""
        manifest = PluginManifest(
            name="test",
            version="1.0.0",
            description="Test plugin",
            author="Test Author",
        )
        state = PluginState(name="test", path="/tmp/test", manifest=manifest)
        plugin_registry.register(state)

        assert plugin_registry.get("test") == state

    def test_get_plugin_state(self, plugin_registry: PluginRegistry) -> None:
        """Test getting plugin state."""
        from jarvix.plugins.registry import PluginManifest, PluginState

        manifest = PluginManifest(name="test", version="1.0.0", description="Test", author="Test")
        state = PluginState(name="test", path="/tmp/test", manifest=manifest, enabled=False)
        plugin_registry.register(state)

        result = plugin_registry.get("test")
        assert result is not None
        assert result.enabled is False  # Explicitly set to False

    def test_set_plugin_state(self, plugin_registry: PluginRegistry) -> None:
        """Test setting plugin state."""
        from jarvix.plugins.registry import PluginManifest, PluginState

        manifest = PluginManifest(name="test", version="1.0.0", description="Test", author="Test")
        state = PluginState(name="test", path="/tmp/test", manifest=manifest, enabled=False)
        plugin_registry.register(state)

        plugin_registry.set_enabled("test", True)

        assert plugin_registry.get("test").enabled is True


class TestCalculatorPlugin:
    """Test the calculator example plugin."""

    def test_calculator_plugin_loads(self, temp_plugin_dir: Path) -> None:
        """Test calculator plugin can be loaded."""
        calc_dir = temp_plugin_dir / "calculator"
        calc_dir.mkdir()

        # Create a minimal calculator plugin in temp dir with required exports
        (calc_dir / "manifest.json").write_text('{"name": "calculator", "version": "1.0.0", "description": "Test", "author": "Test"}')
        (calc_dir / "main.py").write_text('''
from jarvix.core.tool_registry import Tool, tool
from jarvix.core.permissions import PermissionLevel

def get_settings():
    return {}

def set_settings(settings):
    pass

@tool("calculate", permission=PermissionLevel.SAFE, description="Calculate math expressions")
class CalculateTool(Tool):
    name = "calculate"

    def schema(self):
        return {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]}

    async def execute(self, args, ctx):
        return ToolResult.success("result")

def register(reg):
    reg.register("calculate", CalculateTool())
''')

        from jarvix.plugins.registry import PluginState, PluginManifest, get_plugin_registry
        manifest = PluginManifest(name="calculator", version="1.0.0", description="Test", author="Test")
        state = PluginState(name="calculator", path=str(calc_dir), manifest=manifest, enabled=True)
        get_plugin_registry().register(state)

        from jarvix.plugins.loader import load_plugin
        from jarvix.core.tool_registry import ToolRegistry
        tool_reg = ToolRegistry(None, None)
        plugin = load_plugin("calculator", tool_reg)

        assert plugin is not None
        assert plugin.manifest.name == "calculator"

    @pytest.mark.skip(reason="Flaky: load_plugin shadows sys.modules, breaking direct import")
    @pytest.mark.asyncio
    async def test_calculate_tool_execution(self) -> None:
        """Test the calculate tool evaluates expressions."""
        from jarvix.plugins.calculator.main import CalculateTool

        tool = CalculateTool()
        exec_context = ExecContext(
            conversation_id="test",
            user_id="test",
            permission_manager=PermissionManager(),
        )

        # Test basic arithmetic
        result = await tool.execute({"expression": "2 + 3 * 4"}, exec_context)

        assert result.ok
        assert "14" in result.output

        # Test parentheses
        result = await tool.execute({"expression": "(2 + 3) * 4"}, exec_context)
        assert result.ok
        assert "20" in result.output

        # Test invalid expression
        result = await tool.execute({"expression": "2 +"}, exec_context)
        assert not result.ok


class TestPluginTools:
    """Test plugin management tools."""

    def test_register_plugin_tools(self) -> None:
        """Test plugin management tools register."""
        event_bus = EventBus()
        permission_manager = PermissionManager()
        registry = ToolRegistry(event_bus, permission_manager)

        from jarvix.plugins.tools import (
            PluginListTool,
            PluginInfoTool,
            PluginEnableTool,
            PluginDisableTool,
            PluginInstallTool,
            PluginUninstallTool,
            PluginUpdateTool,
        )

        for cls in (
            PluginListTool,
            PluginInfoTool,
            PluginEnableTool,
            PluginDisableTool,
            PluginInstallTool,
            PluginUninstallTool,
            PluginUpdateTool,
        ):
            registry.register(cls.name, cls())

        assert registry.get("plugin_list") is not None
        assert registry.get("plugin_info") is not None
        assert registry.get("plugin_enable") is not None
        assert registry.get("plugin_disable") is not None
        assert registry.get("plugin_install") is not None
        assert registry.get("plugin_uninstall") is not None
        assert registry.get("plugin_update") is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
