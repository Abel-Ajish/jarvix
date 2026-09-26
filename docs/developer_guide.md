# Jarvix Developer Guide

## Adding a New Tool

### 1. Create the Tool Class

Tools live in `jarvix/tools/` or within a subsystem package. Use the `@tool` decorator:

```python
# jarvix/tools/my_tool.py
from jarvix.core.execution import ExecContext
from jarvix.core.logger import get_logger
from jarvix.core.permissions import PermissionLevel
from jarvix.core.tool_registry import Tool, ToolResult, tool

_LOG = get_logger("jarvix.tools.my_tool")

@tool("my_tool", permission=PermissionLevel.SAFE, description="Does something useful")
class MyTool(Tool):
    name = "my_tool"
    description = "Does something useful with the given input"
    permission = PermissionLevel.SAFE

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Input text"},
                "option": {"type": "boolean", "description": "Optional flag", "default": False},
            },
            "required": ["input"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        input_text = args["input"]
        option = args.get("option", False)
        
        ctx.check_cancelled()  # Check for emergency stop
        
        try:
            # Do work here
            result = do_something(input_text, option)
            _LOG.info("MyTool executed with input=%s", input_text)
            return ToolResult.success(f"Result: {result}")
        except Exception as e:
            _LOG.exception("MyTool failed")
            return ToolResult.failure(f"Failed: {e}")
```

### 2. Register the Tool

In `jarvix/tools/__init__.py` or a subsystem's `__init__.py`:

```python
# jarvix/tools/__init__.py
from jarvix.tools.my_tool import MyTool

__all__ = [..., "MyTool"]
```

Then in `jarvix/main.py` (for core tools) or subsystem init:

```python
# In main() or register_subsystem_tools()
from jarvix.tools.my_tool import MyTool
tool_registry.register("my_tool", MyTool())
```

### 3. Add to Offline Engine (Optional)

If the tool should work offline, add patterns to `jarvix/engine/offline.py`:

```python
INTENT_PATTERNS = [
    ...
    ("my_tool", "MY_TOOL", [
        r"^do something\s+(?P<input>.+)$",
        r"^my tool\s+(?P<input>.+)(?:\s+with\s+(?P<option>true|false))?$",
    ]),
]
```

### 4. Add Permission Default (Optional)

In `jarvix/data/settings.yaml`:

```yaml
permissions:
  my_tool: "SAFE"  # or CONFIRM, BLOCKED
```

---

## Adding a New AI Provider

### 1. Implement the AIEngine Interface

Create `jarvix/ai/providers/my_provider.py`:

```python
from jarvix.engine.ai_engine import (
    AIEngine, ChatResponse, StreamChunk, ToolCallResult,
    ConnectionTest, ModelInfo
)

class MyProviderEngine(AIEngine):
    provider_name = "my_provider"
    supports_vision = False
    supports_tools = True
    
    def __init__(self, api_key: str, **kwargs):
        self.api_key = api_key
        self.client = MyProviderClient(api_key)
    
    async def chat(self, messages, *, tools=None, ctx=None) -> ChatResponse:
        response = await self.client.chat(messages, tools=tools)
        return ChatResponse(
            content=response.text,
            tool_calls=response.tool_calls,
            model=response.model,
            usage=response.usage,
        )
    
    async def stream(self, messages, *, tools=None, ctx=None):
        async for chunk in self.client.stream(messages, tools=tools):
            yield StreamChunk(
                content=chunk.text,
                tool_call=chunk.tool_call,
                done=chunk.done,
            )
    
    async def tool_call(self, messages, tools, ctx=None) -> ToolCallResult:
        # Forced tool use
        ...
    
    async def vision(self, image_bytes, prompt, *, ctx=None) -> str:
        if not self.supports_vision:
            return "Vision not supported"
        ...
    
    async def structured_output(self, messages, schema, ctx=None):
        ...
    
    async def test_connection(self) -> ConnectionTest:
        try:
            await self.client.ping()
            return ConnectionTest(ok=True, message="Connected", latency_ms=50)
        except Exception as e:
            return ConnectionTest(ok=False, message=str(e))
    
    async def list_models(self) -> List[ModelInfo]:
        models = await self.client.list_models()
        return [ModelInfo(id=m.id, name=m.name, provider=self.provider_name, capabilities=m.caps) for m in models]
```

### 2. Register Provider

In `jarvix/ai/provider.py`, add to the provider factory:

```python
def create_engine(provider: str, **kwargs) -> AIEngine:
    if provider == "my_provider":
        from jarvix.ai.providers.my_provider import MyProviderEngine
        return MyProviderEngine(**kwargs)
    ...
```

### 3. Add Settings

In `jarvix/data/settings.yaml`:

```yaml
ai:
  providers:
    my_provider:
      enabled: false
      api_key_env: "MY_PROVIDER_API_KEY"
      base_url: "https://api.myprovider.com/v1"
```

---

## Adding a New Subsystem

### 1. Create Package Structure

```
jarvix/new_subsystem/
├── __init__.py          # Package exports + register_*_tools()
├── core.py              # Core functionality
├── tools.py             # Tool classes (using @tool decorator)
├── ui_panel.py          # SettingsTab for the Settings dialog
└── models.py            # Data models (if needed)
```

### 2. Implement Tools

Follow the tool pattern above. Each tool gets registered via `@tool`.

### 3. Create Register Function

```python
# jarvix/new_subsystem/__init__.py
from jarvix.core.tool_registry import ToolRegistry

def register_new_subsystem_tools(registry: ToolRegistry) -> None:
    from jarvix.new_subsystem.tools import ToolA, ToolB
    
    for cls in (ToolA, ToolB):
        registry.register(cls.name, cls())
    
    from jarvix.core.logger import get_logger
    _LOG = get_logger("jarvix.new_subsystem")
    _LOG.info("Registered N new_subsystem tools")
```

### 4. Add Settings File

Create `jarvix/data/settings/new_subsystem.yaml`:

```yaml
new_subsystem:
  option_a: true
  option_b: "default_value"
```

Add to `_SUBSYSTEM_FILES` in `jarvix/core/config.py`:

```python
_SUBSYSTEM_FILES = [
    "core.yaml",
    "voice.yaml",
    "web.yaml",
    "plugins.yaml",
    "ai.yaml",
    "new_subsystem.yaml",  # Add here
]
```

### 5. Auto-Register UI Panel

In `jarvix/new_subsystem/ui_panel.py`:

```python
from jarvix.ui.extensions import SettingsTab, get_settings_tab_registry
from PySide6.QtWidgets import QWidget, QVBoxLayout, QCheckBox

class NewSubsystemSettingsTab(SettingsTab):
    group = "new_subsystem"
    title = "New Subsystem"
    
    def widget(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QCheckBox("Enable feature A"))
        return w

def register_new_subsystem_ui() -> None:
    get_settings_tab_registry().register(NewSubsystemSettingsTab())

# Auto-register on import
register_new_subsystem_ui()
```

Then in `__init__.py`:

```python
from jarvix.new_subsystem.ui_panel import register_new_subsystem_ui
register_new_subsystem_ui()
```

### 6. Wire Into Main

In `jarvix/main.py`:

```python
from jarvix.new_subsystem import register_new_subsystem_tools

def main():
    ...
    register_new_subsystem_tools(tool_registry)
    ...
```

---

## Adding a Plugin

### 1. Create Plugin Directory

```
jarvix/plugins/my_plugin/
├── manifest.json
├── main.py
└── (optional: other modules)
```

### 2. manifest.json

```json
{
  "name": "my_plugin",
  "version": "1.0.0",
  "description": "Does something cool",
  "author": "Your Name",
  "entry_point": "main.py",
  "permissions": ["file_read", "web_access"],
  "min_jarvix_version": "0.1.0"
}
```

### 3. main.py

```python
# jarvix/plugins/my_plugin/main.py
from jarvix.core.tool_registry import ToolRegistry
from jarvix.core.permissions import PermissionLevel
from jarvix.core.execution import ExecContext
from jarvix.core.tool_registry import Tool, ToolResult, tool

@tool("my_plugin_tool", permission=PermissionLevel.SAFE, description="Plugin tool")
class MyPluginTool(Tool):
    name = "my_plugin_tool"
    description = "Does something from the plugin"
    permission = PermissionLevel.SAFE
    
    def schema(self):
        return {
            "type": "object",
            "properties": {
                "param": {"type": "string"},
            },
            "required": ["param"],
        }
    
    async def execute(self, args, ctx):
        return ToolResult.success(f"Plugin did: {args['param']}")

def register(registry: ToolRegistry) -> None:
    """Called by PluginManager when loading this plugin."""
    registry.register("my_plugin_tool", MyPluginTool())
```

### 4. Install Plugin

```bash
# Via UI: Settings > Plugins > Install
# Or programmatically:
from jarvix.plugins.installer import install_from_path
install_from_path(Path("path/to/my_plugin"))
```

---

## Writing Tests

### Unit Test Pattern

```python
# tests/test_my_feature.py
import pytest
from unittest.mock import MagicMock, AsyncMock

from jarvix.core.events import EventBus
from jarvix.core.execution import ExecContext
from jarvix.core.permissions import PermissionManager
from jarvix.core.tool_registry import ToolRegistry

@pytest.fixture
def tool_registry():
    event_bus = EventBus()
    permission_manager = PermissionManager()
    return ToolRegistry(event_bus, permission_manager)

def test_my_tool_registers(tool_registry):
    from jarvix.tools.my_tool import MyTool
    tool_registry.register("my_tool", MyTool())
    
    assert tool_registry.get("my_tool") is not None
    meta = tool_registry.get_meta("my_tool")
    assert meta.permission == PermissionLevel.SAFE

@pytest.mark.asyncio
async def test_my_tool_execution(tool_registry):
    from jarvix.tools.my_tool import MyTool
    tool_registry.register("my_tool", MyTool())
    
    exec_context = ExecContext(
        conversation_id="test",
        user_id="test",
        permission_manager=PermissionManager(),
    )
    
    result = await tool_registry.execute_async("my_tool", {"input": "test"}, exec_context)
    
    assert result.ok
    assert "test" in result.output
```

### Mock External Dependencies

```python
# For tools that need external services
@pytest.mark.asyncio
async def test_external_service_tool(tool_registry):
    from jarvix.tools.external_tool import ExternalTool
    tool_registry.register("external_tool", ExternalTool())
    
    # Mock the external service
    with patch("jarvix.tools.external_tool.external_api_call") as mock_api:
        mock_api.return_value = "mocked response"
        
        exec_context = ExecContext(...)
        result = await tool_registry.execute_async("external_tool", {...}, exec_context)
        
        assert result.ok
        mock_api.assert_called_once()
```

---

## Debugging

### Enable Debug Logging

```python
# In code
from jarvix.core.logger import get_logger
_LOG = get_logger("jarvix.my_module")
_LOG.debug("Debug message with data: %s", data)

# Environment variable
JARVIX_LOG_LEVEL=DEBUG python -m jarvix
```

### Inspect Tool Registry

```python
# In Python REPL or debug
from jarvix.core.tool_registry import get_tool_registry  # if exposed
tools = tool_registry.list_tools()
for t in tools:
    print(f"{t.name}: {t.permission.name} - {t.description}")
```

### Event Bus Debugging

```python
def debug_handler(event):
    print(f"EVENT: {event.type} - {event.data}")

event_bus.subscribe("*", debug_handler)  # Log all events
```

---

## Code Style

- **Type hints** — required for all public APIs
- **Async/await** — all I/O operations async
- **Logging** — use `get_logger(__name__)`, include context
- **Error handling** — return `ToolResult.failure()`, never raise (except `ExecutionCancelled`)
- **Cancellation** — call `ctx.check_cancelled()` in long loops
- **Permissions** — declare appropriate `PermissionLevel` on tools

---

## Common Patterns

### Running in Executor (Blocking Calls)

```python
import asyncio

async def execute(self, args, ctx):
    result = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: blocking_call(args["param"])
    )
    return ToolResult.success(result)
```

### Graceful Degradation

```python
try:
    import optional_dependency
    HAS_DEP = True
except ImportError:
    optional_dependency = None
    HAS_DEP = False

@tool("optional_tool", permission=PermissionLevel.SAFE)
class OptionalTool(Tool):
    async def execute(self, args, ctx):
        if not HAS_DEP:
            return ToolResult.failure("Optional dependency not installed")
        ...
```

### Settings Access

```python
from jarvix.core.config import get_settings

settings = get_settings()
value = settings.get("my_subsystem.option", "default")
settings.set("my_subsystem.option", new_value)  # Persists
```