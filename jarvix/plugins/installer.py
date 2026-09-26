"""Plugin installer — install plugins from local paths or archives.

Supports installing from:
- Local directory containing plugin.json
- .zip archive
- .tar.gz / .tgz archive
"""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional

from jarvix.core.logger import get_logger
from jarvix.plugins.manager import PluginManager, PluginLoadError
from jarvix.plugins.registry import load_manifest

_LOG = get_logger("jarvix.plugins.installer")


def install_from_path(
    source_path: Path,
    manager: PluginManager,
    name: Optional[str] = None,
) -> Dict[str, Any]:
    """Install a plugin from a local path or archive.

    Args:
        source_path: Path to plugin directory or archive
        manager: PluginManager instance
        name: Optional name override

    Returns dict with: success, plugin_name, path, error
    """
    source_path = source_path.resolve()

    if not source_path.exists():
        return {"success": False, "error": f"Source not found: {source_path}"}

    try:
        # Handle archive
        if source_path.suffix in (".zip", ".tar", ".gz", ".tgz"):
            with tempfile.TemporaryDirectory() as tmpdir:
                extract_dir = Path(tmpdir)
                if source_path.suffix == ".zip":
                    with zipfile.ZipFile(source_path, "r") as zf:
                        for member in zf.infolist():
                            if member.is_dir():
                                continue
                            target = (extract_dir / member.name).resolve()
                            if not str(target).startswith(str(extract_dir.resolve())):
                                raise ValueError(f"Path traversal detected in ZIP: {member.name}")
                        zf.extractall(extract_dir)
                else:
                    import tarfile
                    with tarfile.open(source_path, "r:*") as tf:
                        for member in tf.getmembers():
                            if member.islnk() or member.issym():
                                raise ValueError(f"Symlink/hardlink not allowed: {member.name}")
                            target = (extract_dir / member.name).resolve()
                            if not str(target).startswith(str(extract_dir.resolve())):
                                raise ValueError(f"Path traversal detected in tar: {member.name}")
                        tf.extractall(extract_dir)

                # Find the plugin directory (may be nested)
                plugin_dir = extract_dir
                items = list(extract_dir.iterdir())
                if len(items) == 1 and items[0].is_dir():
                    plugin_dir = items[0]

                return _install_from_dir(plugin_dir, manager, name)
        else:
            # Directory
            return _install_from_dir(source_path, manager, name)

    except Exception as e:
        _LOG.exception("Install failed for %s", source_path)
        return {"success": False, "error": str(e)}


def _install_from_dir(
    source_dir: Path, manager: PluginManager, name: Optional[str] = None
) -> Dict[str, Any]:
    """Install a plugin from a directory."""
    manifest = load_manifest(source_dir)
    if manifest is None:
        return {"success": False, "error": "No valid manifest found"}

    plugin_name = name or manifest.name

    # Check for conflicts
    existing = manager.get_plugin(plugin_name)
    if existing:
        return {"success": False, "error": f"Plugin '{plugin_name}' already installed"}

    # Get plugins directory
    import os
    app_data = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming"))
    plugins_dir = app_data / "jarvix" / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)

    target_dir = plugins_dir / plugin_name
    if target_dir.exists():
        return {"success": False, "error": f"Target directory already exists: {target_dir}"}

    # Copy
    try:
        shutil.copytree(source_dir, target_dir)
    except Exception as e:
        return {"success": False, "error": f"Failed to copy plugin: {e}"}

    # Register and load via manager
    try:
        state = manager.install_from_path(source_dir, name)
        return {
            "success": True,
            "plugin_name": plugin_name,
            "path": str(target_dir),
            "version": manifest.version,
        }
    except PluginLoadError as e:
        # Cleanup on failure
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        return {"success": False, "error": str(e)}
    except Exception as e:
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        return {"success": False, "error": f"Install failed: {e}"}


def validate_plugin_source(source_path: Path) -> Dict[str, Any]:
    """Validate a plugin source without installing.

    Returns dict with: valid, manifest, error
    """
    source_path = source_path.resolve()

    if not source_path.exists():
        return {"valid": False, "error": f"Source not found: {source_path}"}

    try:
        if source_path.suffix in (".zip", ".tar", ".gz", ".tgz"):
            with tempfile.TemporaryDirectory() as tmpdir:
                extract_dir = Path(tmpdir)
                if source_path.suffix == ".zip":
                    with zipfile.ZipFile(source_path, "r") as zf:
                        for member in zf.infolist():
                            if member.is_dir():
                                continue
                            target = (extract_dir / member.name).resolve()
                            if not str(target).startswith(str(extract_dir.resolve())):
                                raise ValueError(f"Path traversal detected in ZIP: {member.name}")
                        zf.extractall(extract_dir)
                else:
                    import tarfile
                    with tarfile.open(source_path, "r:*") as tf:
                        for member in tf.getmembers():
                            if member.islnk() or member.issym():
                                raise ValueError(f"Symlink/hardlink not allowed: {member.name}")
                            target = (extract_dir / member.name).resolve()
                            if not str(target).startswith(str(extract_dir.resolve())):
                                raise ValueError(f"Path traversal detected in tar: {member.name}")
                        tf.extractall(extract_dir)

                plugin_dir = extract_dir
                items = list(extract_dir.iterdir())
                if len(items) == 1 and items[0].is_dir():
                    plugin_dir = items[0]

                manifest = load_manifest(plugin_dir)
                if manifest:
                    return {"valid": True, "manifest": manifest.to_dict()}
                return {"valid": False, "error": "No valid manifest in archive"}
        else:
            manifest = load_manifest(source_path)
            if manifest:
                return {"valid": True, "manifest": manifest.to_dict()}
            return {"valid": False, "error": "No valid manifest in directory"}

    except Exception as e:
        return {"valid": False, "error": f"Validation failed: {e}"}