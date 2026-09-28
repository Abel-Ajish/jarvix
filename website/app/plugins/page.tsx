import Navigation from "../components/Navigation";
import Link from "next/link";

export default function PluginsPage() {
  const manifestExample = `{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "Plugin description",
  "author": "Your Name",
  "homepage": "https://example.com",
  "tools": ["my_tool"],
  "settings_schema": {
    "type": "object",
    "properties": {
      "enabled": {
        "type": "boolean",
        "default": true,
        "description": "Enable the plugin"
      }
    }
  },
  "permissions": [],
  "min_jarvix_version": "0.1.0"
}`;

  const pluginExample = `from jarvix.core.logger import get_logger
from jarvix.core.tool_registry import Tool, ToolResult, tool
from jarvix.core.permissions import PermissionLevel

_LOG = get_logger("jarvix.plugins.myplugin")

_settings = {"enabled": True}

def get_settings() -> dict:
    return dict(_settings)

def set_settings(new: dict) -> None:
    _settings.update(new)
    _LOG.info("Updated settings: %s", _settings)

@tool("my_tool", permission=PermissionLevel.SAFE,
      description="Do something useful.")
class MyTool(Tool):
    name = "my_tool"
    description = "Do something useful."
    permission = PermissionLevel.SAFE

    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {"arg": {"type": "string"}},
            "required": ["arg"]
        }

    async def execute(self, args, ctx) -> ToolResult:
        # Your implementation here
        result = do_something(args["arg"])
        return ToolResult.success(f"Result: {result}")

def register(tool_registry):
    """Entry point called by the loader."""
    tool_registry.register("my_tool", MyTool())
    _LOG.info("Plugin registered.");`;

  const calculatorExample = `{
  "name": "calculator",
  "version": "1.0.0",
  "description": "Basic calculator for safe math evaluation",
  "author": "Jarvix Team",
  "tools": ["calculate"],
  "settings_schema": {
    "type": "object",
    "properties": {
      "precision": {
        "type": "integer",
        "default": 10,
        "minimum": 1,
        "maximum": 50,
        "description": "Decimal precision"
      },
      "allow_functions": {
        "type": "boolean",
        "default": false,
        "description": "Allow math functions"
      }
    }
  }
}`;

  return (
    <main className="min-h-screen bg-canvas">
      <Navigation />

      <div className="pt-24 pb-20 px-6">
        <div className="max-w-4xl mx-auto">
          {/* Header */}
          <div className="mb-12">
            <div className="flex items-center gap-2 text-sm text-text-muted font-mono mb-4">
              <Link href="/" className="hover:text-primary transition-colors">Home</Link>
              <span>/</span>
              <span className="text-text-primary">Plugins</span>
            </div>
            <h1 className="text-4xl font-light tracking-tight mb-4">Plugin Development</h1>
            <p className="text-text-muted text-lg">
              Extend Jarvix with custom tools and integrations using the plugin system.
            </p>
          </div>

          {/* Architecture Overview */}
          <div className="mb-12">
            <h2 className="text-2xl font-light tracking-tight mb-6">Architecture</h2>
            <div className="grid md:grid-cols-3 gap-4">
              {[
                { step: "1", title: "plugin.json", desc: "Manifest file with metadata and settings schema" },
                { step: "2", title: "main.py", desc: "Python module with tool classes and register() hook" },
                { step: "3", title: "ToolRegistry", desc: "Tools are registered and available system-wide" },
              ].map((item) => (
                <div key={item.step} className="p-6 rounded-xl bg-surface border border-border">
                  <div className="text-3xl font-mono text-primary mb-2">{item.step}</div>
                  <div className="text-text-primary font-medium mb-2">{item.title}</div>
                  <div className="text-text-muted text-sm">{item.desc}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Folder Structure */}
          <div className="mb-12">
            <h2 className="text-2xl font-light tracking-tight mb-6">Folder Structure</h2>
            <div className="p-6 rounded-xl bg-surface border border-border font-mono text-sm">
              <code className="text-text-primary">
                jarvix/plugins/my-plugin/<br/>
                ├── plugin.json&nbsp;&nbsp;&nbsp;&nbsp;# Manifest (required)<br/>
                ├── main.py&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;# Tool definitions (required)<br/>
                ├── README.md&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;# Documentation (optional)<br/>
                └── utils.py&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;# Helper modules (optional)<br/><br/>
                <span className="text-text-muted"># Or install to user directory:</span><br/>
                %APPDATA%\jarvix\plugins\my-plugin\
              </code>
            </div>
          </div>

          {/* Manifest Reference */}
          <div className="mb-12">
            <h2 className="text-2xl font-light tracking-tight mb-6">Manifest Reference</h2>
            <div className="rounded-xl bg-surface border border-border overflow-hidden">
              <div className="px-6 py-4 border-b border-border bg-card">
                <code className="font-mono text-sm text-primary">plugin.json</code>
              </div>
              <div className="p-6 font-mono text-sm overflow-x-auto">
                <pre className="text-text-primary">
{`{
  "name": "plugin-name",        // Required: unique identifier
  "version": "1.0.0",           // Required: semantic version
  "description": "...",         // Required: short description
  "author": "Your Name",        // Required: author name
  "homepage": "https://...",    // Optional: project URL
  "tools": ["tool1", "tool2"],  // Required: list of tool names
  "settings_schema": { ... },   // Optional: JSON schema for settings
  "permissions": [...],         // Optional: ACL hints
  "min_jarvix_version": "0.1.0" // Optional: minimum version required
}`}
                </pre>
              </div>
            </div>
          </div>

          {/* Plugin Code Example */}
          <div className="mb-12">
            <h2 className="text-2xl font-light tracking-tight mb-6">Plugin Code</h2>
            <div className="rounded-xl bg-surface border border-border overflow-hidden">
              <div className="px-6 py-4 border-b border-border bg-card flex items-center gap-2">
                <div className="flex gap-2">
                  <div className="w-3 h-3 rounded-full bg-red-500" />
                  <div className="w-3 h-3 rounded-full bg-yellow-500" />
                  <div className="w-3 h-3 rounded-full bg-green-500" />
                </div>
                <code className="font-mono text-sm text-text-muted">main.py</code>
              </div>
              <div className="p-6 font-mono text-sm overflow-x-auto">
                <pre className="text-text-primary">{pluginExample}</pre>
              </div>
            </div>
          </div>

          {/* Calculator Plugin Example */}
          <div className="mb-12">
            <h2 className="text-2xl font-light tracking-tight mb-6">Example: Calculator Plugin</h2>
            <div className="space-y-6">
              <div className="rounded-xl bg-surface border border-border overflow-hidden">
                <div className="px-6 py-4 border-b border-border bg-card">
                  <code className="font-mono text-sm text-primary">plugin.json</code>
                </div>
                <div className="p-6 font-mono text-sm overflow-x-auto">
                  <pre className="text-text-primary">{calculatorExample}</pre>
                </div>
              </div>

              <div className="p-4 rounded-lg bg-card border border-border">
                <h4 className="text-text-primary font-medium mb-2">Key Points:</h4>
                <ul className="text-text-muted text-sm space-y-1 list-disc list-inside">
                  <li>Uses <code className="text-secondary font-mono">@tool</code> decorator for automatic registration</li>
                  <li>Implements <code className="text-secondary font-mono">SafeEvaluator</code> with AST parsing (no eval())</li>
                  <li>Supports configurable precision and function permissions</li>
                  <li>Tool is accessible via AI: <code className="text-metrics font-mono">{"{"}calculate: "2+3"*4{"}"}</code></li>
                </ul>
              </div>
            </div>
          </div>

          {/* Plugin Lifecycle */}
          <div className="mb-12">
            <h2 className="text-2xl font-light tracking-tight mb-6">Plugin Lifecycle</h2>
            <div className="grid md:grid-cols-2 gap-4">
              {[
                {
                  title: "Install",
                  desc: "Copy to %APPDATA%\\jarvix\\plugins\\ or use UI installer",
                },
                {
                  title: "Load",
                  desc: "Import main.py, validate register(), get_settings(), set_settings()",
                },
                {
                  title: "Enable/Disable",
                  desc: "Toggle in UI — loads/unloads tools dynamically",
                },
                {
                  title: "Uninstall",
                  desc: "Remove directory and clean secrets from SecretStore",
                },
              ].map((step) => (
                <div key={step.title} className="p-4 rounded-xl bg-surface border border-border">
                  <div className="text-text-primary font-medium mb-1">{step.title}</div>
                  <div className="text-text-muted text-sm">{step.desc}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Best Practices */}
          <div>
            <h2 className="text-2xl font-light tracking-tight mb-6">Best Practices</h2>
            <div className="space-y-3">
              {[
                "Use lowercase names with hyphens: my-plugin",
                "Always include a plugin.json with all required fields",
                "Implement get_settings()/set_settings() for configurable plugins",
                "Use safe parsers (AST) instead of eval() for code execution",
                "Set appropriate permission levels (SAFE for read-only, CONFIRM for writes)",
                "Add a README.md explaining usage and configuration",
                "Bump version in plugin.json for each update",
              ].map((tip, i) => (
                <div key={i} className="flex items-start gap-3 p-4 rounded-xl bg-surface border border-border">
                  <div className="w-6 h-6 rounded-full bg-primary/10 text-primary flex items-center justify-center font-mono text-xs flex-shrink-0">
                    {i + 1}
                  </div>
                  <span className="text-text-primary text-sm">{tip}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="py-12 px-6 border-t border-border">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row justify-between items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-secondary pulse-dot" />
            <span className="font-light text-text-primary">Jarvix</span>
            <span className="text-text-muted text-sm font-mono">v0.1.0-stable</span>
          </div>
          <div className="text-text-muted text-sm">
            © 2025 Jarvix Project
          </div>
        </div>
      </footer>
    </main>
  );
}
