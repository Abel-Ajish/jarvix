import Navigation from "./components/Navigation";
import Link from "next/link";

export default function Home() {
  return (
    <main className="min-h-screen bg-canvas">
      <Navigation />

      {/* Hero Section */}
      <section className="pt-32 pb-20 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="grid lg:grid-cols-2 gap-16 items-center">
            {/* Left - Content */}
            <div className="space-y-8">
              <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-primary/10 border border-primary/20">
                <div className="w-2 h-2 rounded-full bg-secondary pulse-dot" />
                <span className="text-sm text-primary-light font-mono">v0.1.0 — Offline First</span>
              </div>

              <h1 className="text-5xl md:text-6xl font-light leading-tight tracking-tight text-text-primary">
                Your desktop assistant,{" "}
                <span className="text-primary-light">reinvented.</span>
              </h1>

              <p className="text-lg text-text-muted leading-relaxed max-w-xl">
                Jarvix is an offline-first Windows desktop assistant that understands natural language commands.
                Run tools, manage files, browse the web, and extend functionality with plugins — all without an internet connection.
              </p>

              <div className="flex flex-wrap gap-4">
                <Link
                  href="/install"
                  className="px-8 py-4 rounded-lg bg-primary text-white font-medium hover:bg-primary-light transition-all duration-300 shadow-lg shadow-primary/20"
                >
                  Get Started
                </Link>
                <Link
                  href="/usage"
                  className="px-8 py-4 rounded-lg border border-border text-text-primary font-medium hover:border-primary hover:text-primary transition-all duration-300"
                >
                  View Documentation
                </Link>
              </div>

              {/* Metrics Bar */}
              <div className="flex flex-wrap gap-8 pt-8 border-t border-border">
                <div>
                  <div className="text-2xl font-mono font-semibold text-metrics">100%</div>
                  <div className="text-sm text-text-muted">Offline Capable</div>
                </div>
                <div>
                  <div className="text-2xl font-mono font-semibold text-secondary">50+</div>
                  <div className="text-sm text-text-muted">Built-in Tools</div>
                </div>
                <div>
                  <div className="text-2xl font-mono font-semibold text-primary-light">∞</div>
                  <div className="text-sm text-text-muted">Plugin Extensible</div>
                </div>
              </div>
            </div>

            {/* Right - Feature Nodes Visualization */}
            <div className="relative h-96 lg:h-auto aspect-square">
              {/* Central Node */}
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="w-32 h-32 rounded-2xl bg-primary/20 border border-primary/40 flex items-center justify-center float-animation">
                  <span className="text-4xl">🤖</span>
                </div>
              </div>

              {/* Orbiting Nodes */}
              {[
                { label: "Offline Engine", color: "bg-secondary", delay: "0s" },
                { label: "Plugin System", color: "bg-primary", delay: "0.5s" },
                { label: "AI Integration", color: "bg-metrics", delay: "1s" },
                { label: "Voice Control", color: "bg-purple-500", delay: "1.5s" },
                { label: "Vision", color: "bg-pink-500", delay: "2s" },
              ].map((node, i) => {
                const angle = (i * 72) * (Math.PI / 180);
                const radius = 140;
                const x = Math.cos(angle) * radius;
                const y = Math.sin(angle) * radius;

                return (
                  <div
                    key={node.label}
                    className={`absolute top-1/2 left-1/2 w-24 h-24 -ml-12 -mt-12 rounded-xl ${node.color}/20 border border-${node.color.split("-")[1]}-500/30 flex flex-col items-center justify-center gap-2 transition-all duration-300 hover:scale-110`}
                    style={{
                      transform: `translate(${x}px, ${y}px)`,
                      animationDelay: node.delay
                    }}
                  >
                    <div className={`w-3 h-3 rounded-full ${node.color}`} />
                    <span className="text-xs text-text-muted text-center px-2">{node.label}</span>
                  </div>
                );
              })}

              {/* Connection Lines (SVG) */}
              <svg className="absolute inset-0 w-full h-full pointer-events-none" viewBox="0 0 400 400">
                {[0, 72, 144, 216, 288].map((angle, i) => {
                  const rad = (angle * Math.PI) / 180;
                  const x2 = 200 + Math.cos(rad) * 140;
                  const y2 = 200 + Math.sin(rad) * 140;
                  return (
                    <line
                      key={i}
                      x1="200"
                      y1="200"
                      x2={x2}
                      y2={y2}
                      stroke="rgba(99, 102, 241, 0.2)"
                      strokeWidth="1"
                      strokeDasharray="4 4"
                    >
                      <animate
                        attributeName="stroke-dashoffset"
                        from="0"
                        to="8"
                        dur="1s"
                        repeatCount="indefinite"
                      />
                    </line>
                  );
                })}
              </svg>
            </div>
          </div>
        </div>
      </section>

      {/* Features Grid */}
      <section className="py-20 px-6 bg-surface/50">
        <div className="max-w-7xl mx-auto">
          <h2 className="text-3xl font-light tracking-tight text-center mb-12">
            Built for <span className="text-primary-light">power users</span>
          </h2>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[
              {
                title: "Offline First",
                description: "All core functionality works without internet. No API keys required for basic operations.",
                icon: "🔌",
              },
              {
                title: "Plugin System",
                description: "Extend Jarvix with custom tools and integrations. Simple JSON manifest + Python code.",
                icon: "🧩",
              },
              {
                title: "Permission System",
                description: "Three-tier permission levels (SAFE, CONFIRM, BLOCKED) keep your system secure.",
                icon: "🔒",
              },
              {
                title: "Voice Control",
                description: "Wake word detection and speech-to-text for hands-free operation.",
                icon: "🎤",
              },
              {
                title: "Web Automation",
                description: "Browser automation with Playwright for web search, navigation, and screenshots.",
                icon: "🌐",
              },
              {
                title: "AI Powered",
                description: "Optional AI integration with OpenRouter, OpenAI, Anthropic, and more.",
                icon: "🧠",
              },
            ].map((feature, i) => (
              <div
                key={i}
                className="p-6 rounded-xl bg-card border border-border hover:border-primary/50 transition-all duration-300 group"
              >
                <div className="text-3xl mb-4 group-hover:scale-110 transition-transform duration-300">
                  {feature.icon}
                </div>
                <h3 className="text-lg font-medium text-text-primary mb-2">{feature.title}</h3>
                <p className="text-text-muted text-sm leading-relaxed">{feature.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Quick Start */}
      <section className="py-20 px-6">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-3xl font-light tracking-tight mb-6">
            Ready to get started?
          </h2>
          <p className="text-text-muted mb-8">
            Install Jarvix in minutes and start automating your workflow.
          </p>
          <Link
            href="/install"
            className="inline-flex items-center gap-2 px-8 py-4 rounded-lg bg-primary text-white font-medium hover:bg-primary-light transition-all duration-300 shadow-lg shadow-primary/20"
          >
            Installation Guide
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </svg>
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 px-6 border-t border-border">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row justify-between items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-secondary pulse-dot" />
            <span className="font-light text-text-primary">Jarvix</span>
            <span className="text-text-muted text-sm font-mono">v0.1.0-stable</span>
          </div>
          <div className="text-text-muted text-sm">
            Offline-first Windows desktop assistant
          </div>
          <div className="text-text-muted text-sm">
            © 2025 Jarvix Project
          </div>
        </div>
      </footer>
    </main>
  );
}
