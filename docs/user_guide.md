# Jarvix User Guide

Jarvix is a Windows desktop assistant that helps you get things done using natural language commands. It works offline by default and can connect to online AI providers for enhanced capabilities.

## Getting Started

### Installation

1. Run `install.bat` to create the virtual environment and install dependencies
2. Run `start.bat` to launch Jarvix
3. The first time you run Jarvix, it will create a settings file at `%APPDATA%/jarvix/settings/settings.yaml`

### Basic Usage

Once Jarvix is running, you can interact with it in several ways:

- **Type a command** in the main window's input box
- **Use voice input** (if a microphone is configured and enabled)
- **Use the system tray icon** to show/hide the window or access settings

### Example Commands

Try these to get started:

- `open notepad` — launches Notepad
- `what time is it` — tells you the current time
- `create file hello.txt content=Hello World` — creates a file
- `search files *.txt` — finds all text files in permitted directories
- `web_search python tutorials` — searches the web for Python tutorials
- `screen_capture` — takes a screenshot of your primary monitor
- `agent_plan build a simple calculator` — creates a multi-step plan

## Key Concepts

### Intents and Tools

Jarvix works by matching your natural language input to an **intent**, which maps to a specific **tool**. For example:
- "open notepad" → intent: `open_application` → tool: `OpenApplicationTool`
- "create file test.txt" → intent: `create_file` → tool: `CreateFileTool`

Each tool has:
- A name (used internally)
- A JSON schema defining its arguments
- A permission level (SAFE, CONFIRM, BLOCKED)
- Documentation and examples

### Permissions

For security, tools require different levels of approval:

- **SAFE**: Runs immediately (read-only, local-only operations)
- **CONFIRM**: Shows a confirmation dialog before running
- **BLOCKED**: Never runs (reserved for dangerous operations like formatting drives)

You can adjust permissions in Settings → Permissions.

### Subsystems

Jarvix is organized into independent subsystems that communicate via an event bus:

| Subsystem | Phase | Responsibility |
|-----------|-------|----------------|
| Core | 1 | Event bus, permissions, settings, tool registry |
| Offline Engine | 2 | Deterministic command processing (no internet needed) |
| Memory | 3 | Conversation storage and search |
| Online AI | 4 | Connecting to AI providers (OpenRouter, OpenAI, etc.) |
| Voice | 5 | Speech-to-text and text-to-speech |
| Web | 6 | Browser automation and web search |
| Plugins | 8 | Extending Jarvix with community tools |
| Vision | 7 | Screen capture and visual understanding |
| Advanced Agent | 9 | Multi-step planning and task execution |
| Polish | 10 | Performance, UX, accessibility, packaging |

### The Offline Command Engine

When no internet is available or no AI provider is configured, Jarvix falls back to its **offline command engine**. This handles:
- File operations (create, read, write, delete, search)
- System operations (open applications, clipboard, keyboard)
- Basic math and text processing
- Plugin management

All core functionality works 100% offline.

## Common Tasks

### File Management

- `create file notes.txt content=Meeting at 3pm` — create a note
- `read file notes.txt` — view the note's contents
- `search files *.pdf` — find all PDF files
- `create folder Projects` — make a new folder
- `move file report.docx Projects/` — file into folder

### Web and Browser

- `web_search latest AI news` — search the web
- `read_page https://example.com` — get readable text from a URL
- `browser_navigate https://github.com` — open a website
- `browser_click selector="a[href='/login']"` — click a link
- `browser_type selector="#search" content=jarvix` — type into a field
- `browser_screenshot path=~/Desktop/github.png` — capture a webpage

### Vision and Screen Understanding

- `screen_capture` — take a screenshot
- `analyze_screen describe what you see` — get a description of your screen
- `find_ui_element button Submit` — locate a button on screen
- `read_screen_text` — perform OCR on the current screen
- `vision_describe` — ask Jarvix to describe what's on screen

### Planning and Automation

- `agent_plan backup my documents` — create a plan to back up files
- `agent_execute plan backup my documents` — run the plan
- `agent_task_create monitor folder Downloads` — create a background watcher
- `agent_task_status` — check on running tasks
- `agent_task_cancel task_id` — stop a task

### Voice Commands

If you have a microphone configured:
- Say the wake word (default: "jarvix") followed by your command
- Example: "jarvix, what's the weather today?"
- Voice input can be disabled in Settings → Voice

### Settings

Access Settings from the system tray icon or by typing `open settings`.

Key sections:
- **Core**: Theme, language, startup behavior
- **Voice**: Microphone, wake word, TTS settings
- **Web**: Search engine, browser choice, download folder
- **AI**: Provider selection and API keys
- **Vision**: Capture backend, model selection, confidence
- **Agent**: Planner model, step limits, retry policy
- **Polish**: Performance monitoring, toasts, accessibility
- **Permissions**: Adjust tool approval levels

## Troubleshooting

### Jarvix won't start

1. Check that `install.bat` completed successfully
2. Look for error messages in the console window
3. Verify you have Python 3.12+ installed
4. Try running `python -m jarvix` directly from the command line

### Commands don't work

1. Check the permission level (hover over the tool in suggestions)
2. Verify any required dependencies are installed
3. Look at the status bar for error messages
4. Check Settings → Permissions if a tool is unexpectedly blocked

### Web features don't work

1. Ensure you have internet connectivity
2. Run `python -m pip install playwright` then `playwright install`
3. Check Settings → Web for browser selection
4. Some websites block automation; try different sites

### Voice input doesn't work

1. Verify a microphone is connected and not muted
2. Check Settings → Voice for mic_enabled
3. Try speaking louder or closer to the microphone
4. Background noise can interfere with wake word detection

### Performance is slow

1. Check Settings → Polish for performance_monitoring
2. Look at the startup time reported in the logs
3. Consider disabling unused subsystems in Settings
4. First launch after changes may be slower while caches build

## Advanced Usage

### Creating Plugins

See `docs/developer_guide.md` for full details, but briefly:
1. Create a folder under `jarvix/plugins/`
2. Add a `plugin.json` manifest
3. Add a `main.py` that calls `register(tool_registry)`
4. Restart Jarvix or use `plugin_install` to load it

### Keyboard Shortcuts

- **Ctrl+Shift+J** — Emergency stop (halts all current operations)
- **Alt+F4** — Close the main window
- **Ctrl+Comma** — Open Settings (when window focused)
- **Esc** — Clear the input box

### Command Line Interface

You can run Jarvix directly from a terminal:
```bash
# Show version
python -m jarvix --version

# Run a one-shot command
python -m jarvix --exec "open notepad"

# Run tests
python -m pytest tests/

# Build executable
python scripts/packaging.py
```

## Support

For issues, questions, or contributions:
- Check the existing documentation first
- Look at the example plugin at `jarvix/plugins/calculator/`
- Review the source code — it's designed to be readable and maintainable

Jarvix is released under the MIT License. See `LICENSE` for details.