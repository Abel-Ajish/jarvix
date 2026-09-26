"""Download management for jarvix (Phase 6).

Tracks active downloads with progress events, handles cancellation,
and manages the download directory.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from jarvix.core.config import get_settings
from jarvix.core.events import EventBus
from jarvix.core.logger import get_logger

_LOG = get_logger("jarvix.web.downloads")


class DownloadStatus(Enum):
    PENDING = "pending"
    STARTED = "started"
    PROGRESS = "progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class DownloadInfo:
    """Information about a single download."""

    id: str
    url: str
    suggested_filename: str
    status: DownloadStatus = DownloadStatus.PENDING
    path: Optional[Path] = None
    total_bytes: Optional[int] = None
    received_bytes: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "filename": self.suggested_filename,
            "status": self.status.value,
            "path": str(self.path) if self.path else None,
            "total_bytes": self.total_bytes,
            "received_bytes": self.received_bytes,
            "progress": (
                (self.received_bytes / self.total_bytes * 100)
                if self.total_bytes and self.total_bytes > 0
                else 0.0
            ),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }


class DownloadManager:
    """Manages all downloads for the web subsystem."""

    def __init__(self, event_bus: Optional[EventBus] = None) -> None:
        self._event_bus = event_bus
        self._downloads: Dict[str, DownloadInfo] = {}
        self._download_path = self._get_download_path()
        self._callbacks: List[Callable[[DownloadInfo], None]] = []

    def _get_download_path(self) -> Path:
        """Get the configured download directory from settings."""
        settings = get_settings()
        path_str = settings.get("web.download_folder", "~/Downloads/jarvix")
        path = Path(path_str).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def download_path(self) -> Path:
        return self._download_path

    def register_callback(self, cb: Callable[[DownloadInfo], None]) -> None:
        """Register a callback for download status changes."""
        self._callbacks.append(cb)

    def _notify(self, info: DownloadInfo) -> None:
        """Notify all callbacks and the event bus."""
        for cb in self._callbacks:
            try:
                cb(info)
            except Exception:
                _LOG.exception("Download callback failed")
        if self._event_bus:
            try:
                from jarvix.core.events import ErrorRaised

                self._event_bus.publish(
                    ErrorRaised(
                        f"Download {info.status.value}: {info.suggested_filename}",
                        component="web.downloads",
                    )
                )
            except Exception:
                pass

    def create_download(
        self,
        url: str,
        suggested_filename: Optional[str] = None,
    ) -> DownloadInfo:
        """Create a new download entry (pending)."""
        dl_id = str(uuid.uuid4())[:8]
        filename = suggested_filename or os.path.basename(urllib.parse.urlparse(url).path) or "download"
        info = DownloadInfo(
            id=dl_id,
            url=url,
            suggested_filename=filename,
            status=DownloadStatus.PENDING,
            started_at=datetime.now(),
        )
        self._downloads[dl_id] = info
        _LOG.info("Created download: %s (%s)", filename, dl_id)
        self._notify(info)
        return info

    def update_progress(
        self,
        dl_id: str,
        *,
        received_bytes: Optional[int] = None,
        total_bytes: Optional[int] = None,
        status: Optional[DownloadStatus] = None,
    ) -> Optional[DownloadInfo]:
        """Update download progress."""
        info = self._downloads.get(dl_id)
        if not info:
            return None

        if received_bytes is not None:
            info.received_bytes = received_bytes
        if total_bytes is not None:
            info.total_bytes = total_bytes
        if status is not None:
            info.status = status
            if status in (DownloadStatus.COMPLETED, DownloadStatus.FAILED, DownloadStatus.CANCELLED):
                info.completed_at = datetime.now()

        self._notify(info)
        return info

    def complete_download(self, dl_id: str, path: Path) -> Optional[DownloadInfo]:
        """Mark download as completed with final path."""
        info = self._downloads.get(dl_id)
        if not info:
            return None
        info.path = path
        info.status = DownloadStatus.COMPLETED
        info.completed_at = datetime.now()
        info.received_bytes = info.total_bytes or path.stat().st_size
        _LOG.info("Download completed: %s -> %s", info.suggested_filename, path)
        self._notify(info)
        return info

    def fail_download(self, dl_id: str, error: str) -> Optional[DownloadInfo]:
        """Mark download as failed."""
        info = self._downloads.get(dl_id)
        if not info:
            return None
        info.status = DownloadStatus.FAILED
        info.error = error
        info.completed_at = datetime.now()
        _LOG.error("Download failed: %s - %s", info.suggested_filename, error)
        self._notify(info)
        return info

    def cancel_download(self, dl_id: str) -> bool:
        """Cancel a pending/in-progress download."""
        info = self._downloads.get(dl_id)
        if not info:
            return False
        if info.status in (DownloadStatus.COMPLETED, DownloadStatus.FAILED, DownloadStatus.CANCELLED):
            return False
        info.status = DownloadStatus.CANCELLED
        info.completed_at = datetime.now()
        _LOG.info("Download cancelled: %s", info.suggested_filename)
        self._notify(info)
        return True

    def get_download(self, dl_id: str) -> Optional[DownloadInfo]:
        return self._downloads.get(dl_id)

    def list_downloads(self, *, status: Optional[DownloadStatus] = None) -> List[DownloadInfo]:
        """List all downloads, optionally filtered by status."""
        result = list(self._downloads.values())
        if status:
            result = [d for d in result if d.status == status]
        # Sort by start time, newest first
        result.sort(key=lambda d: d.started_at or datetime.min, reverse=True)
        return result

    def clear_history(self, *, keep_completed: bool = False) -> int:
        """Clear download history. Returns number removed."""
        if keep_completed:
            to_remove = [
                dl_id
                for dl_id, info in self._downloads.items()
                if info.status != DownloadStatus.COMPLETED
            ]
        else:
            to_remove = list(self._downloads.keys())

        for dl_id in to_remove:
            del self._downloads[dl_id]

        _LOG.info("Cleared %d downloads from history", len(to_remove))
        return len(to_remove)


# Global manager instance
_DOWNLOAD_MANAGER: Optional[DownloadManager] = None


def get_download_manager(event_bus: Optional[EventBus] = None) -> DownloadManager:
    """Get or create the global DownloadManager."""
    global _DOWNLOAD_MANAGER
    if _DOWNLOAD_MANAGER is None:
        _DOWNLOAD_MANAGER = DownloadManager(event_bus)
    return _DOWNLOAD_MANAGER


# Playwright download integration
async def handle_playwright_download(download: "Download", manager: DownloadManager) -> DownloadInfo:
    """Handle a Playwright Download object and track it."""
    import urllib.parse

    # Create download entry
    info = manager.create_download(
        url=download.url,
        suggested_filename=download.suggested_filename,
    )

    # Update to started
    manager.update_progress(info.id, status=DownloadStatus.STARTED)

    try:
        # Wait for download to complete and get the temp path
        temp_path = await download.path()
        from pathlib import PurePath
        safe_name = PurePath(info.suggested_filename).name
        final_path = manager.download_path / safe_name

        # Ensure unique filename if exists
        if final_path.exists():
            stem = final_path.stem
            suffix = final_path.suffix
            counter = 1
            while final_path.exists():
                final_path = manager.download_path / f"{stem}_{counter}{suffix}"
                counter += 1

        # Save to final location
        await download.save_as(final_path)

        # Update info with final path
        manager.complete_download(info.id, final_path)
        return manager.get_download(info.id)  # type: ignore

    except Exception as e:
        manager.fail_download(info.id, str(e))
        raise


# Import urllib.parse for URL parsing
import urllib.parse