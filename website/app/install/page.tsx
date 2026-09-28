import Navigation from "../components/Navigation";
import Link from "next/link";

export default function InstallPage() {
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
              <span className="text-text-primary">Install</span>
            </div>
            <h1 className="text-4xl font-light tracking-tight mb-4">Installation</h1>
            <p className="text-text-muted text-lg">
              Get Jarvix running on your Windows machine in minutes.
            </p>
          </div>

          {/* System Requirements */}
          <div className="mb-12 p-6 rounded-xl bg-surface border border-border">
            <h2 className="text-xl font-medium mb-4 flex items-center gap-2">
              <span className="text-metrics">⚙</span>
              System Requirements
            </h2>
            <div className="grid md:grid-cols-2 gap-4 font-mono text-sm">
              <div className="p-4 rounded-lg bg-card">
                <div className="text-text-muted mb-1">Operating System</div>
                <div className="text-text-primary">Windows 10/11 (64-bit)</div>
              </div>
              <div className="p-4 rounded-lg bg-card">
                <div className="text-text-muted mb-1">Python Version</div>
                <div className="text-text-primary">3.12 or higher</div>
              </div>
              <div className="p-4 rounded-lg bg-card">
                <div className="text-text-muted mb-1">Disk Space</div>
                <div className="text-text-primary">~500 MB</div>
              </div>
              <div className="p-4 rounded-lg bg-card">
                <div className="text-text-muted mb-1">RAM</div>
                <div className="text-text-primary">4 GB minimum</div>
              </div>
            </div>
          </div>

          {/* Quick Install */}
          <div className="mb-12">
            <h2 className="text-2xl font-light tracking-tight mb-6">Quick Install</h2>

            <div className="space-y-6">
              {/* Step 1 */}
              <div className="flex gap-4">
                <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary text-white flex items-center justify-center font-mono text-sm">
                  1
                </div>
                <div className="flex-1">
                  <h3 className="text-text-primary font-medium mb-2">Download the source code</h3>
                  <p className="text-text-muted text-sm mb-3">
                    Clone the repository or download the ZIP archive from GitHub.
                  </p>
                  <div className="p-4 rounded-lg bg-card border border-border font-mono text-sm">
                    <code className="text-secondary">$ git clone https://github.com/jarvix/jarvix.git</code>
                  </div>
                </div>
              </div>

              {/* Step 2 */}
              <div className="flex gap-4">
                <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary text-white flex items-center justify-center font-mono text-sm">
                  2
                </div>
                <div className="flex-1">
                  <h3 className="text-text-primary font-medium mb-2">Run the installer</h3>
                  <p className="text-text-muted text-sm mb-3">
                    Navigate to the project folder and run the installation script.
                    This creates a virtual environment and installs all dependencies.
                  </p>
                  <div className="p-4 rounded-lg bg-card border border-border font-mono text-sm">
                    <code className="text-metrics">$ cd jarvix<br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;.\install.bat</code>
                  </div>
                </div>
              </div>

              {/* Step 3 */}
              <div className="flex gap-4">
                <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary text-white flex items-center justify-center font-mono text-sm">
                  3
                </div>
                <div className="flex-1">
                  <h3 className="text-text-primary font-medium mb-2">Launch Jarvix</h3>
                  <p className="text-text-muted text-sm mb-3">
                    Run the startup script or launch directly from the command line.
                  </p>
                  <div className="p-4 rounded-lg bg-card border border-border font-mono text-sm">
                    <code className="text-secondary">.\start.bat<br/><br/># Or manually:<br/>.\.venv\Scripts\python.exe -m jarvix</code>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Manual Installation */}
          <div className="mb-12">
            <h2 className="text-2xl font-light tracking-tight mb-6">Manual Installation</h2>
            <div className="p-4 rounded-lg bg-surface border border-border font-mono text-sm mb-4">
              <code className="text-text-muted"># Create and activate virtual environment<br/>$ python -m venv .venv<br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;.venv\Scripts\activate<br/><br/># Upgrade pip<br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;pip install --upgrade pip<br/><br/># Install dependencies<br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;pip install -r requirements.txt<br/><br/># Install Playwright browsers<br/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;playwright install msedge</code>
            </div>
          </div>

          {/* Configuration */}
          <div className="mb-12">
            <h2 className="text-2xl font-light tracking-tight mb-6">Configuration</h2>
            <div className="p-6 rounded-xl bg-surface border border-border">
              <p className="text-text-muted mb-4">
                Settings are stored in <code className="px-2 py-1 rounded bg-card font-mono text-sm text-metrics">%APPDATA%\jarvix\settings\</code>
              </p>
              <div className="grid md:grid-cols-2 gap-4">
                <div className="p-4 rounded-lg bg-card">
                  <div className="text-text-muted text-sm mb-1">Settings File</div>
                  <div className="font-mono text-sm text-text-primary">settings.yaml</div>
                </div>
                <div className="p-4 rounded-lg bg-card">
                  <div className="text-text-muted text-sm mb-1">Secrets Store</div>
                  <div className="font-mono text-sm text-text-primary">Fernet encrypted</div>
                </div>
                <div className="p-4 rounded-lg bg-card">
                  <div className="text-text-muted text-sm mb-1">Logs</div>
                  <div className="font-mono text-sm text-text-primary">%APPDATA%\jarvix\logs\</div>
                </div>
                <div className="p-4 rounded-lg bg-card">
                  <div className="text-text-muted text-sm mb-1">Plugins</div>
                  <div className="font-mono text-sm text-text-primary">%APPDATA%\jarvix\plugins\</div>
                </div>
              </div>
            </div>
          </div>

          {/* Build Executable */}
          <div>
            <h2 className="text-2xl font-light tracking-tight mb-6">Build Executable (Optional)</h2>
            <p className="text-text-muted mb-4">
              Create a standalone executable with PyInstaller:
            </p>
            <div className="p-4 rounded-lg bg-surface border border-border font-mono text-sm">
              <code className="text-secondary">python scripts/packaging.py<br/><br/># With clean build:<br/>python scripts/packaging.py --clean<br/><br/># With smoke test:<br/>python scripts/packaging.py --test<br/><br/># Portable bundle:<br/>python scripts/packaging.py --portable</code>
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
