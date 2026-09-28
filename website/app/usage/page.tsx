import Navigation from "../components/Navigation";
import Link from "next/link";

export default function UsagePage() {
  const commands = [
    { command: "open notepad", description: "Launch Notepad application", permission: "SAFE" },
    { command: "what time is it", description: "Get current time", permission: "SAFE" },
    { command: "create file hello.txt content=Hello World", description: "Create a text file", permission: "SAFE" },
    { command: "read file hello.txt", description: "Read file contents", permission: "SAFE" },
    { command: "search files *.txt", description: "Search for text files", permission: "SAFE" },
    { command: "web_search python tutorials", description: "Search the web", permission: "SAFE" },
    { command: "screen_capture", description: "Take screenshot", permission: "SAFE" },
    { command: "calculate(\"2 + 3 * 4\")", description: "Evaluate math expression", permission: "SAFE" },
    { command: "agent_plan backup my documents", description: "Create execution plan", permission: "CONFIRM" },
    { command: "browser_navigate https://github.com", description: "Open website in browser", permission: "SAFE" },
    { command: "read_screen_text", description: "OCR screen text", permission: "SAFE" },
    { command: "open settings", description: "Open settings window", permission: "SAFE" },
  ];

  const shortcuts = [
    { keys: "Ctrl+Shift+J", description: "Emergency stop (halts all operations)" },
    { keys: "Alt+F4", description: "Close main window" },
    { keys: "Ctrl+,", description: "Open Settings" },
    { keys: "Esc", description: "Clear input box" },
  ];

  const permissionLevels = [
    { level: "SAFE", color: "bg-secondary", description: "Runs immediately — read-only, local operations" },
    { level: "CONFIRM", color: "bg-metrics", description: "Shows confirmation dialog before running" },
    { level: "BLOCKED", color: "bg-red-500", description: "Never runs — reserved for dangerous operations" },
  ];

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
              <span className="text-text-primary">Usage</span>
            </div>
            <h1 className="text-4xl font-light tracking-tight mb-4">Usage Guide</h1>
            <p className="text-text-muted text-lg">
              Learn how to interact with Jarvix and master its capabilities.
            </p>
          </div>

          {/* Getting Started */}
          <div className="mb-12">
            <h2 className="text-2xl font-light tracking-tight mb-6">Getting Started</h2>
            <div className="grid md:grid-cols-3 gap-4">
              {[
                { step: "1", title: "Type", desc: "Enter commands in the main input box" },
                { step: "2", title: "Submit", desc: "Press Enter or click send" },
                { step: "3", title: "Execute", desc: "Jarvix processes and returns results" },
              ].map((s) => (
                <div key={s.step} className="p-6 rounded-xl bg-surface border border-border">
                  <div className="text-3xl font-mono text-primary mb-2">{s.step}</div>
                  <div className="text-text-primary font-medium mb-1">{s.title}</div>
                  <div className="text-text-muted text-sm">{s.desc}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Example Commands */}
          <div className="mb-12">
            <h2 className="text-2xl font-light tracking-tight mb-6">Example Commands</h2>
            <div className="rounded-xl bg-surface border border-border overflow-hidden">
              <div className="grid grid-cols-[1fr_2fr_80px] gap-4 px-6 py-4 border-b border-border bg-card">
                <span className="text-sm font-mono text-text-muted">Command</span>
                <span className="text-sm font-mono text-text-muted">Description</span>
                <span className="text-sm font-mono text-text-muted">Permission</span>
              </div>
              {commands.map((cmd, i) => (
                <div
                  key={i}
                  className="grid grid-cols-[1fr_2fr_80px] gap-4 px-6 py-4 border-b border-border last:border-0 hover:bg-card transition-colors"
                >
                  <code className="font-mono text-sm text-secondary">{cmd.command}</code>
                  <span className="text-sm text-text-primary">{cmd.description}</span>
                  <span className={`inline-flex items-center justify-center px-2 py-1 rounded text-xs font-mono ${
                    cmd.permission === "SAFE" ? "bg-secondary/10 text-secondary" :
                    cmd.permission === "CONFIRM" ? "bg-metrics/10 text-metrics" :
                    "bg-red-500/10 text-red-500"
                  }`}>
                    {cmd.permission}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Permission Levels */}
          <div className="mb-12">
            <h2 className="text-2xl font-light tracking-tight mb-6">Permission Levels</h2>
            <div className="space-y-3">
              {permissionLevels.map((p) => (
                <div key={p.level} className="flex items-start gap-4 p-4 rounded-xl bg-surface border border-border">
                  <div className={`w-3 h-3 rounded-full ${p.color} mt-1`} />
                  <div>
                    <div className="font-mono text-text-primary font-medium">{p.level}</div>
                    <div className="text-text-muted text-sm">{p.description}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Keyboard Shortcuts */}
          <div className="mb-12">
            <h2 className="text-2xl font-light tracking-tight mb-6">Keyboard Shortcuts</h2>
            <div className="grid md:grid-cols-2 gap-4">
              {shortcuts.map((s) => (
                <div key={s.keys} className="flex items-center justify-between p-4 rounded-xl bg-surface border border-border">
                  <span className="text-text-primary text-sm">{s.description}</span>
                  <kbd className="px-3 py-1 rounded bg-card font-mono text-sm text-metrics border border-border">
                    {s.keys}
                  </kbd>
                </div>
              ))}
            </div>
          </div>

          {/* Voice Commands */}
          <div className="mb-12">
            <h2 className="text-2xl font-light tracking-tight mb-6">Voice Commands</h2>
            <div className="p-6 rounded-xl bg-surface border border-border">
              <p className="text-text-muted mb-4">
                Enable voice input in <code className="font-mono text-metrics">Settings → Voice</code> to use voice commands.
                The default wake word is <span className="text-secondary font-mono">"jarvix"</span>.
              </p>
              <div className="p-4 rounded-lg bg-card border border-border">
                <code className="font-mono text-sm text-text-primary">
                  "jarvix, what's the weather today?"
                </code>
              </div>
            </div>
          </div>

          {/* CLI */}
          <div>
            <h2 className="text-2xl font-light tracking-tight mb-6">Command Line Interface</h2>
            <div className="p-4 rounded-lg bg-surface border border-border font-mono text-sm">
              <code className="text-text-primary">
                # Show version<br/>
                $ python -m jarvix --version<br/><br/>
                # Run a one-shot command<br/>
                $ python -m jarvix --exec "open notepad"<br/><br/>
                # Run tests<br/>
                $ python -m pytest tests/
              </code>
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
