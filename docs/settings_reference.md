# Jarvix Settings Reference

All settings are stored in `%APPDATA%/jarvix/settings/settings.yaml` (Windows)
or `$HOME/.jarvix/settings.yaml` (Unix-like) and merged over the defaults in
`jarvix/data/settings.yaml` at startup.

Settings are grouped by subsystem. Changing a setting requires a restart
to take effect (except where noted).

## Core Settings

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `core.theme` | string | `"system"` | UI theme: `"light"`, `"dark"`, or `"system"` (follows Windows) |
| `core.language` | string | `"en"` | UI language (ISO 639-1 code) |
| `core.auto_start` | bool | `false` | Launch Jarvix at Windows login |
| `core.minimize_to_tray` | bool | `true` | Minimize to system tray on close |

## Voice Settings

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `voice.mic_enabled` | bool | `false` | Enable microphone input |
| `voice.wake_word` | string | `"jarvix"` | Hotword to activate voice input |
| `voice.stt_model` | string | `"tiny.en"` | Faster-Whisper model for speech-to-text |
| `voice.tts_engine` | string | `"pyttsx3"` | Text-to-speech engine |
| `voice.tts_voice` | string | `""` | Specific voice name (engine-dependent) |
| `voice.tts_rate` | int | `180` | Words per minute for TTS |
| `voice.tts_volume` | float | `1.0` | Volume level (0.0 to 1.0) |

## Web Settings

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `web.search_engine` | string | `"duckduckgo"` | `"duckduckgo"` or `"google"` |
| `web.browser` | string | `"edge"` | `"edge"` or `"chromium"` for Playwright |
| `web.download_folder` | string | `"~/Downloads"` | Folder where downloads are saved |

## AI Provider Settings

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `ai.default_provider` | string | `""` | `"openrouter"`, `"openai"`, `"anthropic"`, `"gemini"`, `"groq"` |
| `ai.providers.<name>.enabled` | bool | `false` | Master switch for the provider |
| `ai.providers.<name>.api_key_env` | string | `""` | Environment variable holding the API key |
| `ai.providers.<name>.base_url` | string | *varies* | Base URL for the provider API |

## Plugin Settings

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `plugins.auto_update` | bool | `true` | Automatically check for plugin updates |
| `plugins.trusted_sources` | list | `[]` | List of trusted plugin source URLs or paths |

## Vision Settings

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `vision.capture_backend` | string | `"mss"` | `"mss"` (fast) or `"PIL"` (fallback) |
| `vision.default_monitor` | int | `0` | Monitor index (`0` = primary, `-1` = all combined) |
| `vision.default_region` | object | `null` | `{left, top, width, height}` or `null` for full screen |
| `vision.vision_model` | string | `""` | Model name override (empty = provider default) |
| `vision.confidence_threshold` | float | `0.7` | Minimum confidence for UI element detection |
| `vision.save_captures` | bool | `false` | Keep screenshots on disk for debugging |

## Agent Settings

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `agent.planner_model` | string | `""` | Model for planning (empty = default provider model) |
| `agent.max_steps` | int | `10` | Hard cap on plan length (prevents runaway plans) |
| `agent.retry_policy` | string | `"exponential"` | `"exponential"`, `"linear"`, or `"fixed"` |
| `agent.max_retries` | int | `3` | Retries per step before giving up |
| `agent.auto_continue` | bool | `true` | Automatically continue to next step on success |
| `agent.persist_tasks` | bool | `true` | Keep task history on disk between runs |

## Polish Settings

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `polish.performance_monitoring` | bool | `true` | Enable startup timing and latency tracking |
| `polish.toasts_enabled` | bool | `true` | Show non-blocking toast notifications |
| `polish.high_contrast` | bool | `false` | Use high-contrast UI palette |
| `polish.screen_reader` | bool | `false` | Enable screen-reader-friendly labels |
| `polish.lazy_imports` | bool | `true` | Defer non-critical imports until first use |

## Permission Settings

Permissions are managed via the UI and stored as a nested object under
`permissions:`. The format is:

```yaml
permissions:
  tool_name: SAFE   # or CONFIRM or BLOCKED
```

If a tool is not listed here, it uses the default permission from its
registration. Available levels are `SAFE`, `CONFIRM`, and `BLOCKED`.

## Example Custom Settings

```yaml
core:
  theme: "dark"
  language: "es"
  auto_start: true

voice:
  mic_enabled: true
  wake_word: "hey jarvix"
  tts_rate: 200

web:
  search_engine: "google"
  browser: "chromium"

ai:
  default_provider: "openrouter"
  providers:
    openrouter:
      enabled: true
      api_key_env: "OPENROUTER_API_KEY"

vision:
  capture_backend: "mss"
  confidence_threshold: 0.6
  save_captures: true

agent:
  max_steps: 15
  max_retries: 5
  persist_tasks: false

polish:
  performance_monitoring: false
  high_contrast: true