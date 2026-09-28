# Jarvix

A unified Windows desktop AI assistant that works **offline by default** and seamlessly connects to online AI providers when available. No local LLM required for basic operation.

## 🚀 Features

- **Offline-first** — deterministic pattern-matching engine handles 80+ commands without internet
- **Online AI fallback** — plug in OpenRouter, OpenAI, Anthropic, Gemini, or Groq for enhanced capabilities
- **Voice control** — local speech-to-text with wake-word detection (faster-whisper)
- **Web automation** — Playwright-backed browser control and search
- **Vision & screen analysis** — screenshot capture, OCR, and UI element detection
- **Multi-step agent** — planner / verifier / retry pipeline for complex tasks
- **Plugin system** — extend with custom tools via JSON manifests
- **Permission gates** — every tool checked against SAFE / CONFIRM / BLOCKED levels
- **Encrypted secrets** — API keys stored securely via Fernet + machine-derived key
- **Emergency stop** — global kill switch (`Ctrl+Shift+J`) cancels all execution

## 📦 Installation

**Requirements:** Python 3.12+ on Windows 10/11

```powershell
# One-click install (creates venv, installs deps, sets up data dirs)
.\install.bat

# Or manually
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\playwright install msedge
```

**Launch:**

```powershell
.\start.bat
# or
.venv\Scripts\python -m jarvix
```

## 💬 Example Commands

| Command | What it does |
|---|---|
| `open notepad` | Launches Notepad |
| `what time is it` | Returns current time |
| `create file notes.txt content=Hello World` | Creates a text file |
| `search files *.pdf` | Finds PDFs in permitted dirs |
| `web_search python tutorials` | Searches the web via DuckDuckGo |
| `screen_capture` | Takes a screenshot |
| `analyze_screen describe what you see` | AI-powered screen description |
| `agent_plan backup my documents` | Generates a multi-step plan |
| `browser_navigate https://github.com` | Opens a website |

Full command reference and advanced usage → [docs/user_guide.md](docs/user_guide.md)

## 🏗 Architecture

Jarvix follows a **contract-first, phased architecture**. Core contracts are frozen in Phase 1; every subsequent feature registers into them.

```
User Input
    │
    ▼
┌──────────────────┐      ┌──────────────────┐
│  Offline Engine  │◄────►│   Online AI      │
│  (pattern match) │      │  (LLM tool call) │
└────────┬─────────┘      └────────┬─────────┘
         │ Tool(name, args)        │
         └──────────┬──────────────┘
                    ▼
           ┌─────────────────┐
           │  ToolRegistry   │  ← single execution spine
           │  + Permission   │
           └────────┬────────┘
                    ▼
           ┌─────────────────┐
           │   EventBus      │  ← pub/sub, no direct coupling
           └─────────────────┘
                    │
    ┌───────────────┼───────────────┐
    ▼               ▼               ▼
  Memory          Vision           Web
  (SQLite+FTS)  (screenshots)   (Playwright)
```

**Subsystem phases:**

| Phase | Subsystem |
|-------|-----------|
| 1 | Core — EventBus, config, permissions, tool registry *(frozen)* |
| 2 | Offline Engine — deterministic command matching |
| 3 | Memory — SQLite conversation & fact store |
| 4 | Online AI — multi-provider LLM abstraction |
| 5 | Voice — STT/TTS with wake word |
| 6 | Web — browser automation & search |
| 7 | Vision — screen capture & analysis |
| 8 | Plugins — dynamic tool extension system |
| 9 | Agent — planner / verifier / retry pipeline |

See [docs/architecture.md](docs/architecture.md) for the full specification.

## 🔒 Security

- No API keys in source code — encrypted at rest via `SecretStore`
- Every tool execution gated by `PermissionManager` (SAFE / CONFIRM / BLOCKED)
- File operations scoped to permitted directories
- Zero telemetry — all processing stays local unless explicitly using an online provider
- Global emergency stop (`Ctrl+Shift+J`) kills all running operations instantly

## 🧪 Testing

```bash
python -m pytest tests/ -v
```

Tests are fully mocked — no network or UI dependencies.

## 📁 Project Structure

```
jarvix/
├── core/         # EventBus, config, permissions, tool registry, secret store
├── engine/       # OfflineCommandEngine, AIEngine ABC
├── ui/           # PySide6 main window, panel & settings registries
├── agent/        # Planner, verifier, retry, recovery, background tasks
├── ai/           # Provider implementations (OpenRouter, Anthropic, etc.)
├── voice/        # STT/TTS, wake-word detection
├── web/          # Browser automation, search, page reading
├── vision/       # Screen capture, OCR, UI element detection
├── memory/       # Conversation store, fact storage
├── plugins/      # Plugin loader, calculator example, manager
└── tools/        # System tools (open app, clipboard, keyboard)
```

## 📚 Documentation

| Doc | Description |
|-----|-------------|
| [User Guide](docs/user_guide.md) | Getting started, commands, troubleshooting |
| [Architecture](docs/architecture.md) | Contract-first design, data flow, subsystem details |
| [Developer Guide](docs/developer_guide.md) | Building plugins, extending subsystems |
| [Tool Reference](docs/tool_reference.md) | Complete tool catalog with schemas |
| [Settings Reference](docs/settings_reference.md) | All configuration keys and defaults |

## 🛠️ Build & Packaging

```bash
# Build standalone executable with PyInstaller
python scripts/packaging.py
# Output: dist/jarvix.exe  +  dist/jarvix_portable/
```

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

## 🤝 Contributing

Contributions are welcome! Please read [docs/developer_guide.md](docs/developer_guide.md) before submitting changes.

For issues and questions, open a GitHub issue or consult the docs first.
