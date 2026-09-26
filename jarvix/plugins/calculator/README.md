# Calculator Plugin

A safe calculator plugin for Jarvix that evaluates mathematical expressions without using `eval()`.

## Features

- Basic arithmetic: `+`, `-`, `*`, `/`, `%`, `**` (power)
- Parentheses for grouping
- Constants: `pi`, `e`
- Optional math functions: `sqrt`, `sin`, `cos`, `tan`, `log`, `exp`, `abs`, `round`, `min`, `max`, `floor`, `ceil`, etc.
- Configurable precision
- No `eval()` - uses safe AST parsing

## Installation

The calculator plugin is built-in and installed by default at:
```
%APPDATA%\jarvix\plugins\calculator\
```

## Usage

Once enabled, use the `calculate` tool:

```
calculate("2 + 3 * 4")           # Returns 14
calculate("10 / 3")              # Returns 3.3333333333
calculate("2 ** 10")             # Returns 1024
calculate("sqrt(16)")            # Returns 4 (requires allow_functions=true)
calculate("sin(pi / 2)")         # Returns 1.0 (requires allow_functions=true)
calculate("max(1, 5, 3)")        # Returns 5 (requires allow_functions=true)
```

## Configuration

Settings can be adjusted in the Plugins settings tab:

- **precision**: Decimal places for results (default: 10, range: 1-50)
- **allow_functions**: Enable math functions like sqrt, sin, cos (default: false)

## Plugin Contract

This plugin follows the Jarvix plugin contract:

1. **Manifest**: `plugin.json` with name, version, description, tools list, settings schema, permissions
2. **Entry point**: `main.py` with:
   - `register(tool_registry)` - registers tools
   - `get_settings()` - returns current settings
   - `set_settings(dict)` - updates settings
3. **Tools**: Uses `@tool` decorator from `jarvix.core.tool_registry`

## Security

The plugin **never uses `eval()` or `exec()`**. It parses expressions using Python's `ast` module and evaluates only a whitelist of safe AST nodes and operators. This prevents code injection attacks.

## Development

To create your own plugin:

1. Create a directory under `%APPDATA%\jarvix\plugins\your-plugin\`
2. Add `plugin.json` manifest
3. Add `main.py` with `register()`, `get_settings()`, `set_settings()`
4. Use `@tool` decorator to define tools
5. Install via the Plugins panel or `plugin_install` tool