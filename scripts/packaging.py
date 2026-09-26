#!/usr/bin/env python3
"""Build a standalone jarvix executable with PyInstaller.

Usage:
    python scripts/packaging.py            # build dist/jarvix.exe
    python scripts/packaging.py --clean    # clean previous builds first
    python scripts/packaging.py --test     # build then run the executable --version
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / ".venv"
PYTHON = VENV / "Scripts" / "python.exe"
DIST = ROOT / "dist"
BUILD = ROOT / "build"
SPEC = ROOT / "jarvix.spec"

# Files that must be bundled into the executable
DATA_FILES = [
    ("jarvix/data", "jarvix/data"),
    ("docs", "docs"),
]


def _check_env() -> None:
    """Verify the venv and PyInstaller are available."""
    if not PYTHON.exists():
        print(f"ERROR: venv python not found at {PYTHON}", file=sys.stderr)
        print("Run install.bat first to set up the venv.", file=sys.stderr)
        sys.exit(1)

    # Ensure PyInstaller is installed
    subprocess.run(
        [str(PYTHON), "-m", "pip", "install", "-q", "pyinstaller"],
        check=False,
    )


def _clean() -> None:
    """Remove previous build artifacts."""
    for path in (DIST, BUILD, SPEC):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
            print(f"Cleaned {path}")


def _build(clean: bool = False) -> Path:
    """Run PyInstaller and return the path to the built executable."""
    if clean:
        _clean()

    cmd = [
        str(PYTHON), "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",           # folder bundle (faster startup than onefile)
        "--windowed",         # no console window
        "--collect-submodules", "jarvix",
        "--add-data", "jarvix/data;jarvix/data",
        "--hidden-import", "jarvix.web",
        "--hidden-import", "jarvix.vision",
        "--hidden-import", "jarvix.agent",
        "--hidden-import", "jarvix.plugins",
        "--hidden-import", "jarvix.memory",
        "--hidden-import", "jarvix.voice",
        "--hidden-import", "jarvix.ai",
        "--hidden-import", "jarvix.engine",
        "jarvix/__main__.py",
    ]

    print("Building jarvix executable...")
    result = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    if result.returncode != 0:
        print("PyInstaller failed:", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        print(result.stdout, file=sys.stderr)
        sys.exit(1)

    exe = DIST / "jarvix.exe"
    if not exe.exists():
        # PyInstaller may place it in a subdirectory
        candidates = list(DIST.glob("**/jarvix.exe"))
        if candidates:
            exe = candidates[0]
        else:
            print("ERROR: jarvix.exe not found after build", file=sys.stderr)
            sys.exit(1)

    print(f"Built: {exe}")
    return exe


def _test(exe: Path) -> bool:
    """Smoke-test the built executable."""
    print(f"Testing {exe} --version ...")
    result = subprocess.run(
        [str(exe), "--version"],
        capture_output=True, text=True, timeout=30,
    )
    ok = result.returncode == 0
    print(f"  exit={result.returncode} stdout={result.stdout.strip()!r}")
    if result.stderr.strip():
        print(f"  stderr={result.stderr.strip()!r}")
    return ok


def _portable(exe: Path) -> Path:
    """Create a portable folder with the executable and its dependencies."""
    folder = ROOT / "jarvix_portable"
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True, exist_ok=True)

    # Copy the entire dist folder (onedir bundle)
    dist_folder = exe.parent
    shutil.copytree(dist_folder, folder / dist_folder.name, dirs_exist_ok=True)

    # Copy settings template
    settings_src = ROOT / "jarvix" / "data" / "settings.yaml"
    if settings_src.exists():
        shutil.copy2(settings_src, folder / "settings.yaml")

    # Copy README
    readme = ROOT / "README.md"
    if readme.exists():
        shutil.copy2(readme, folder / "README.md")

    print(f"Portable bundle: {folder}")
    return folder


def main() -> int:
    parser = argparse.ArgumentParser(description="Build standalone jarvix executable")
    parser.add_argument("--clean", action="store_true", help="Clean previous builds first")
    parser.add_argument("--test", action="store_true", help="Run --version smoke test after build")
    parser.add_argument("--portable", action="store_true", help="Also create a portable folder bundle")
    args = parser.parse_args()

    _check_env()
    exe = _build(clean=args.clean)

    if args.test:
        if not _test(exe):
            print("Smoke test FAILED", file=sys.stderr)
            return 1
        print("Smoke test PASSED")

    if args.portable:
        _portable(exe)

    print("\nBuild complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())