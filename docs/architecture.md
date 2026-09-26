# Jarvix Architecture

## System Overview

Jarvix is a Windows desktop assistant built on a **contract-first architecture**. The core contracts (Phase 1) are frozen and never modified; all subsequent phases register into these contracts.

```
┌─────────────────────────────────────────────────────────────┐
│                        Main Process                          │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   Qt GUI    │  │ Event Bus   │  │  Tool Registry      │  │
│  │ (MainWindow)│◄─┤  (Pub/Sub)  │──┤  (Single Spine)     │  │
│  └─────────────┘  └─────────────┘  └──────────┬──────────┘  │
│        │                   ▲                   │            │
│        ▼                   │                   ▼            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Permission Manager                      │   │
│  │         (SAFE / CONFIRM / BLOCKED gate)             │   │
│  └─────────────────────────────────────────────────────┘   │
│        │                   │                   │            │
│        ▼                   ▼                   ▼            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ Offline  │  │  Online  │  │  Memory  │  │  Vision  │    │
│  │ Engine   │  │    AI    │  │  Store   │  │          │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
│        │                   │                   │            │
│        ▼                   ▼                   ▼            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │   Web    │  │ Plugins  │  │  Voice   │  │  Agent   │    │
│  │          │  │          │  │          │  │          │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## Frozen Contracts (Phase 1 - DO NOT MODIFY)

| File | Purpose | Key Exports |
|------|---------|-------------|
| `jarvix/core/events.py` | EventBus pub/sub | `EventBus`, `Event`, `ToolExecuted`, `PermissionRequested`, `VoiceWake`, `VoiceResult`, `OnlineStatusChanged`, `EmergencyStopRequested`, `AICancelRequested`, `ShutdownRequested` |
| `jarvix/core/logger.py` | Structured logging | `get_logger`, `LogRecord` (with `sensitive=True` redaction) |
| `jarvix/core/config.py` | Settings (per-subsystem YAML) | `Settings`, `get_settings` |
| `jarvix/core/secret_store.py` | Encrypted secret storage | `SecretStore`, `get_secret_store` |
| `jarvix/core/permissions.py` | Permission gates | `PermissionManager`, `PermissionLevel` (SAFE/CONFIRM/BLOCKED), `PermissionDecision` |
| `jarvix/core/tool_registry.py` | **THE SPINE** | `ToolRegistry`, `Tool`, `ToolResult`, `ToolMeta`, `@tool` decorator |
| `jarvix/core/execution.py` | Execution context | `ExecContext`, `ExecutionCancelled` |
| `jarvix/core/store.py` | SQLite interfaces | `ConversationStore`, `MemoryStore`, `SCHEMA_SQL` |
| `jarvix/core/emergency_stop.py` | Global cancel | `EmergencyStop` (Ctrl+Shift+J hotkey) |
| `jarvix/engine/ai_engine.py` | AI provider abstraction | `AIEngine` ABC |
| `jarvix/ui/extensions.py` | UI extension points | `PanelRegistry`, `SettingsTabRegistry` |
| `jarvix/ui/main_window.py` | Dynamic main window | `JarvixWindow` (built from registries) |

## Wave Dependencies

```
Phase 1 (Core) ◄── Frozen Contracts
    │
    ├──► Phase 2 (Offline Engine) ──► Phase 3 (Memory) ──► Phase 4 (Online AI) ──► Phase 5 (Voice)
    │
    ├──► Phase 6 (Web) ◄──────────────────────────────────────┤
    │                                                         │
    ├──► Phase 7 (Vision) ◄───────────────────────────────────┤  (needs Phase 4 AIEngine.vision())
    │                                                         │
    ├──► Phase 8 (Plugins) ◄──────────────────────────────────┤  (needs Phase 2 filesystem tools)
    │                                                         │
    └──► Phase 9 (Agent) ◄────────────────────────────────────┘  (needs Phase 4 AIEngine.structured_output())
```

**Key Rules:**
- Phase 1 contracts are **frozen** — never modify after Phase 1
- All tool execution goes through `ToolRegistry.execute()` — single spine
- All subsystems communicate via `EventBus` — no direct imports between subsystems
- Settings are per-subsystem YAML files merged at load time

## Core Data Flow

### Tool Execution Path (Both Online & Offline)

```
User Input
    │
    ▼
┌─────────────────────┐
│  Offline Engine     │  (pattern matching)
│  Online AI Engine   │  (LLM tool calling)
└─────────┬───────────┘
          │ Tool Call (name, args)
          ▼
┌─────────────────────┐
│  ToolRegistry       │  (SINGLE execution path)
│  .execute()         │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  PermissionManager  │  (SAFE → auto, CONFIRM → dialog, BLOCKED → deny)
│  .check()           │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Tool.execute()     │  (async, with ExecContext)
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  EventBus.publish() │  (ToolExecuted event)
└─────────────────────┘
```

### Event Bus Communication

All subsystems publish/subscribe to events — **no direct coupling**:

```
Voice Wake Word ──► VoiceWake event ──► Offline Engine starts listening
Emergency Stop ──► EmergencyStopRequested ──► All ExecContext.cancel_event.set()
Tool Result ──► ToolExecuted ──► UI updates, logging, memory
Online Status ──► OnlineStatusChanged ──► Engine switches
```

## Subsystem Architecture

### Offline Engine (Phase 2)
- **Deterministic pattern matcher** — regex-based intent → tool mapping
- Implements `AIEngine` interface — interchangeable with online AI
- Zero dependencies — works completely offline
- `INTENT_PATTERNS` list maps 80+ commands to tools

### Memory (Phase 3)
- **SQLite + FTS5** — conversations, facts, tool call log, permission log
- Implements frozen `ConversationStore` / `MemoryStore` interfaces
- `MemoryManager` provides high-level API

### Online AI (Phase 4)
- **Provider abstraction** — `AIEngine` ABC with multiple providers
- Providers: OpenRouter, OpenAI, Anthropic, Gemini, Groq, etc.
- Failover chain, model selection, streaming support
- `structured_output()` for planner, `vision()` for vision subsystem

### Voice (Phase 5)
- **faster-whisper** STT (local, no cloud)
- Wake word detection (porcupine-style or simple energy-based)
- Graceful degradation when no microphone

### Web (Phase 6)
- **Playwright** browser automation (Edge/Chromium)
- DuckDuckGo/Google search, HTML→markdown reader
- Download tracking with progress events
- Lazy initialization, graceful degradation

### Vision (Phase 7)
- **Screen capture** via `mss` (primary) or PIL (fallback)
- Multi-monitor support, region capture
- `AIEngine.vision()` integration for analysis
- UI element detection (buttons, fields, menus) with bounding boxes

### Plugins (Phase 8)
- **Dynamic loading** — plugins are directories with `manifest.json` + `main.py`
- `register(tool_registry)` function in `main.py` registers tools
- Manager handles discovery, enable/disable, install/update/remove
- Example: calculator plugin with safe AST-based `calculate` tool

### Agent (Phase 9)
- **Multi-step task execution** with planner, verifier, retry, recovery
- `Planner` uses `AIEngine.structured_output()` for plan generation
- `Verifier` checks step success against criteria
- `RetryManager` with exponential backoff and strategy selection
- `RecoveryManager` for failure recovery (retry/skip/abort/modify)
- `BackgroundTaskManager` for long-running tasks with progress/cancellation
- `TaskManager` for task lifecycle

## Configuration

Settings are stored in `%APPDATA%\jarvix\settings\` as per-subsystem YAML:

```
core.yaml       # theme, language, auto_start
voice.yaml      # mic_enabled, wake_word, stt_model, tts_*
web.yaml        # search_engine, browser, download_folder
ai.yaml         # default_provider, providers.{openrouter,openai,...}.enabled
plugins.yaml    # auto_update, trusted_sources
permissions.yaml # tool_name: permission_level (overrides)
```

## Security Model

1. **No API keys in code** — stored encrypted via `SecretStore` (Fernet + machine-derived key)
2. **Permission gates** — every tool execution checked by `PermissionManager`
3. **Path restrictions** — file tools scoped to permitted directories
4. **No telemetry** — all processing local unless explicitly using online AI
5. **Emergency stop** — global kill switch (Ctrl+Shift+J) cancels all execution

## Extension Points

| Extension | Registry | How to Extend |
|-----------|----------|---------------|
| Main Window Panel | `PanelRegistry` | Create `Panel` subclass, call `register()` |
| Settings Tab | `SettingsTabRegistry` | Create `SettingsTab` subclass, call `register()` |
| Tool | `ToolRegistry` | Create `Tool` subclass, use `@tool` decorator or `register()` |
| AI Provider | `AIEngine` ABC | Implement all abstract methods |
| Plugin | Plugin Manager | Create directory with `manifest.json` + `main.py` |

## Testing Strategy

- **Contract tests** (`test_core.py`) — verify frozen contracts work
- **Unit tests** per subsystem — mocked dependencies
- **Integration tests** (`test_integration.py`) — end-to-end flows
- **No external dependencies** in tests — all mocked

## Packaging

- **PyInstaller** — standalone executable
- **Bundled**: Python runtime, all deps, settings.yaml, assets
- **Output**: `dist/jarvix.exe` + `dist/jarvix_portable/` folder
- **Version** from `jarvix/__init__.py`