# Jarvix Tool Reference

All tools are registered with the global `ToolRegistry` at startup. Each tool
has a name, a JSON schema, a permission level (`SAFE`, `CONFIRM`, `BLOCKED`),
and an async `execute(args, ctx) -> ToolResult` method.

## Permission Levels

| Level | Meaning |
|-------|---------|
| `SAFE` | Runs without confirmation. Read-only or local-only. |
| `CONFIRM` | Requires user approval before execution. |
| `BLOCKED` | Never runs (reserved for dangerous operations). |

## File System Tools

| Tool | Permission | Description |
|------|-----------|-------------|
| `create_file` | CONFIRM | Create a new file with content |
| `read_file` | SAFE | Read the contents of a file |
| `write_file` | CONFIRM | Write content to a file (overwrites) |
| `copy_file` | CONFIRM | Copy a file to a new location |
| `move_file` | CONFIRM | Move/rename a file |
| `rename_file` | CONFIRM | Rename a file (same directory) |
| `delete_file` | CONFIRM | Delete a file |
| `create_folder` | CONFIRM | Create a new directory |
| `delete_folder` | CONFIRM | Delete a directory (recursively) |
| `search_files` | SAFE | Search for files by name/pattern |

## Clipboard & Keyboard Tools

| Tool | Permission | Description |
|------|-----------|-------------|
| `clipboard_read` | SAFE | Read the clipboard contents |
| `clipboard_write` | CONFIRM | Write text to the clipboard |
| `keyboard_press` | CONFIRM | Press a single key |
| `keyboard_type` | CONFIRM | Type text into the active window |
| `keyboard_hotkey` | CONFIRM | Press a combination of keys |

## System Tools

| Tool | Permission | Description |
|------|-----------|-------------|
| `open_application` | CONFIRM | Open an application by name or path |

## Web Tools (Phase 6)

| Tool | Permission | Description |
|------|-----------|-------------|
| `web_search` | CONFIRM | Search the web via DuckDuckGo (Google fallback) |
| `read_page` | CONFIRM | Fetch a URL and extract readable markdown |
| `browser_navigate` | CONFIRM | Navigate to a URL in the browser |
| `browser_click` | CONFIRM | Click an element by CSS selector |
| `browser_type` | CONFIRM | Type text into an element |
| `browser_scroll` | SAFE | Scroll the page up/down/top/bottom |
| `browser_screenshot` | SAFE | Capture a page screenshot to disk |
| `browser_download` | CONFIRM | Trigger or wait for a download |
| `browser_upload` | CONFIRM | Upload a file to an `<input type=file>` |

## Vision Tools (Phase 7)

| Tool | Permission | Description |
|------|-----------|-------------|
| `screen_capture` | SAFE | Capture full screen, a monitor, or a region |
| `analyze_screen` | CONFIRM | Capture + send to vision model with a prompt |
| `find_ui_element` | CONFIRM | Capture + detect a specific UI element |
| `read_screen_text` | CONFIRM | Capture + OCR via vision model |
| `vision_describe` | CONFIRM | Capture + natural language description |
| `list_monitors` | SAFE | List all monitors with properties |

## Plugin Management Tools (Phase 8)

| Tool | Permission | Description |
|------|-----------|-------------|
| `plugin_list` | SAFE | List installed plugins and their state |
| `plugin_info` | SAFE | Show details for a named plugin |
| `plugin_enable` | CONFIRM | Enable a plugin |
| `plugin_disable` | CONFIRM | Disable a plugin |
| `plugin_install` | CONFIRM | Install a plugin from a local path/archive |
| `plugin_uninstall` | CONFIRM | Remove a plugin |
| `plugin_update` | CONFIRM | Check for or apply plugin updates |

## Advanced Agent Tools (Phase 9)

| Tool | Permission | Description |
|------|-----------|-------------|
| `agent_plan` | CONFIRM | Create a multi-step plan for a goal |
| `agent_execute` | CONFIRM | Execute a plan with verification/retry/recovery |
| `agent_task_create` | SAFE | Create a background task |
| `agent_task_status` | SAFE | Get the status of a task |
| `agent_task_cancel` | CONFIRM | Cancel a running task |
| `agent_task_list` | SAFE | List all tasks |

## Example Plugin Tools

| Tool | Permission | Description |
|------|-----------|-------------|
| `calculate` | SAFE | Evaluate a math expression safely (AST-based, no `eval`) |

## Tool Execution Flow

```
User intent
  → OfflineCommandEngine.match()      # intent → tool name
  → PermissionManager.check()         # SAFE / CONFIRM / BLOCKED
  → ExecContext (cancel_event)        # cancellation support
  → Tool.execute(args, ctx)           # async execution
  → ToolResult.success() / failure()  # structured result
  → EventBus.publish(ToolExecuted)     # observers notified
```