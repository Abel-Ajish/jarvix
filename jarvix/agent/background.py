"""Background task execution for the Advanced Agent subsystem.

Supports fire-and-forget tasks, progress callbacks, cancellation,
and result collection. Integrates with EventBus for progress events.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from jarvix.agent.task import Task, TaskResult, TaskStatus
from jarvix.core.events import Event, EventBus
from jarvix.core.execution import ExecContext, ExecutionCancelled
from jarvix.core.logger import get_logger

_LOG = get_logger("jarvix.agent.background")


# ---------------------------------------------------------------------------
# Events for background task progress
# ---------------------------------------------------------------------------


class TaskProgressEvent(Event):
    """Event published when a background task makes progress."""

    def __init__(
        self,
        task_id: str,
        progress: float,
        message: str = "",
        step: Optional[str] = None,
    ) -> None:
        super().__init__(
            "task.progress",
            data={
                "task_id": task_id,
                "progress": progress,
                "message": message,
                "step": step,
            },
        )


class TaskCompletedEvent(Event):
    """Event published when a background task completes."""

    def __init__(self, task_id: str, success: bool, result: Optional[TaskResult] = None) -> None:
        super().__init__(
            "task.completed",
            data={
                "task_id": task_id,
                "success": success,
                "result": result.to_dict() if result else None,
            },
        )


class TaskCancelledEvent(Event):
    """Event published when a background task is cancelled."""

    def __init__(self, task_id: str) -> None:
        super().__init__("task.cancelled", data={"task_id": task_id})


# ---------------------------------------------------------------------------
# Background task wrapper
# ---------------------------------------------------------------------------


@dataclass
class BackgroundTask:
    """A task running in the background."""

    id: str
    task: Task
    future: asyncio.Future
    created_at: datetime = field(default_factory=datetime.now)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    progress_callback: Optional[Callable[[float, str, Optional[str]], None]] = None


# ---------------------------------------------------------------------------
# Background task manager
# ---------------------------------------------------------------------------


class BackgroundTaskManager:
    """Manages background task execution."""

    def __init__(self, event_bus: Optional[EventBus] = None):
        self._event_bus = event_bus
        self._tasks: Dict[str, BackgroundTask] = {}
        self._running: Set[str] = set()
    def save_task_state(self, task_id: str, status: TaskStatus, result: Optional[TaskResult] = None) -> None:
        """Persist background task state to disk."""
        try:
            data = {
                "task_id": task_id,
                "status": status.value,
                "completed_at": datetime.now().isoformat(),
            }
            if result:
                data["result"] = {
                    "task_id": result.task_id,
                    "status": result.status.value,
                    "error": result.error,
                }
            file_path = self._persist_dir / f"{task_id}.json"
            with file_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            _LOG.debug("Failed to persist background task %s", task_id, exc_info=True)
        self._persist_dir.mkdir(parents=True, exist_ok=True)

    def set_event_bus(self, event_bus: EventBus) -> None:
        """Set the event bus for progress events."""
        self._event_bus = event_bus

    def submit(
        self,
        task: Task,
        execute_fn: Callable[[Task, ExecContext], Any],
        *,
        progress_callback: Optional[Callable[[float, str, Optional[str]], None]] = None,
    ) -> str:
        """Submit a task for background execution.

        Args:
            task: The task to execute
            execute_fn: Async function that executes the task (task, ctx) -> TaskResult
            progress_callback: Optional callback for progress updates (progress, message, step)

        Returns:
            Task ID
        """
        task_id = task.id or str(uuid.uuid4())[:8]
        task.id = task_id
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()

        cancel_event = asyncio.Event()
        ctx = ExecContext(cancel_event=cancel_event)

        # Create the future
        async def _run_task():
            try:
                result = await execute_fn(task, ctx)
                task.result = result
                task.status = TaskStatus.COMPLETED if result.ok else TaskStatus.FAILED
                task.completed_at = datetime.now()

                # Publish completion event
                if self._event_bus:
                    self._event_bus.publish(TaskCompletedEvent(task_id, result.ok, result))

                return result

            except ExecutionCancelled:
                task.status = TaskStatus.CANCELLED
                task.completed_at = datetime.now()
                if self._event_bus:
                    self._event_bus.publish(TaskCancelledEvent(task_id))
                raise

            except Exception as e:
                _LOG.exception("Background task %s failed", task_id)
                task.status = TaskStatus.FAILED
                task.completed_at = datetime.now()
                error_result = TaskResult(
                    task_id=task_id,
                    plan_id=task.plan.id if task.plan else "",
                    status=TaskStatus.FAILED,
                    started_at=task.started_at or datetime.now(),
                    completed_at=datetime.now(),
                    error=str(e),
                )
                task.result = error_result
                if self._event_bus:
                    self._event_bus.publish(TaskCompletedEvent(task_id, False, error_result))
                raise

            finally:
                self._running.discard(task_id)
                # Persist task state after completion
                self.save_task_state(task_id, task.status, task.result)

        future = asyncio.ensure_future(_run_task())

        bg_task = BackgroundTask(
            id=task_id,
            task=task,
            future=future,
            cancel_event=cancel_event,
            progress_callback=progress_callback,
        )

        self._tasks[task_id] = bg_task
        self._running.add(task_id)

        _LOG.info("Submitted background task %s: %s", task_id, task.name)
        return task_id

    def cancel(self, task_id: str) -> bool:
        """Cancel a running background task.

        Args:
            task_id: ID of the task to cancel

        Returns:
            True if task was found and cancellation requested
        """
        bg_task = self._tasks.get(task_id)
        if not bg_task:
            return False

        if task_id not in self._running:
            return False  # Already completed

        bg_task.cancel_event.set()
        # Also cancel the future to unblock any I/O wait
        if not bg_task.future.done():
            bg_task.future.cancel()
        _LOG.info("Cancellation requested for task %s", task_id)
        return True

    def cancel_all(self) -> int:
        """Cancel all running background tasks.

        Returns:
            Number of tasks cancelled
        """
        count = 0
        for task_id in list(self._running):
            if self.cancel(task_id):
                count += 1
        return count

    def get_status(self, task_id: str) -> Optional[TaskStatus]:
        """Get the status of a background task."""
        bg_task = self._tasks.get(task_id)
        if not bg_task:
            return None
        return bg_task.task.status

    def get_result(self, task_id: str) -> Optional[TaskResult]:
        """Get the result of a completed background task."""
        bg_task = self._tasks.get(task_id)
        if not bg_task:
            return None
        return bg_task.task.result

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get the full task object."""
        bg_task = self._tasks.get(task_id)
        if not bg_task:
            return None
        return bg_task.task

    def list_tasks(self, *, status: Optional[TaskStatus] = None) -> List[Task]:
        """List all background tasks, optionally filtered by status."""
        tasks = [bg.task for bg in self._tasks.values()]
        if status:
            tasks = [t for t in tasks if t.status == status]
        return tasks

    def is_running(self, task_id: str) -> bool:
        """Check if a task is currently running."""
        return task_id in self._running

    async def wait_for(self, task_id: str, timeout: Optional[float] = None) -> Optional[TaskResult]:
        """Wait for a background task to complete.

        Args:
            task_id: ID of the task to wait for
            timeout: Optional timeout in seconds

        Returns:
            TaskResult if completed, None if timeout or not found
        """
        bg_task = self._tasks.get(task_id)
        if not bg_task:
            return None

        try:
            await asyncio.wait_for(bg_task.future, timeout=timeout)
            return bg_task.task.result
        except asyncio.TimeoutError:
            return None
        except Exception:
            return bg_task.task.result

    def cleanup_completed(self, max_age_seconds: float = 3600) -> int:
        """Remove completed tasks older than max_age_seconds and clean persistence files."""
        now = datetime.now()
        to_remove = []

        for task_id, bg_task in self._tasks.items():
            if task_id in self._running:
                continue
            if bg_task.task.completed_at:
                age = (now - bg_task.task.completed_at).total_seconds()
                if age > max_age_seconds:
                    to_remove.append(task_id)

        for task_id in to_remove:
            del self._tasks[task_id]
            # Remove persistence file
            try:
                persistence_file = self._persist_dir / f"{task_id}.json"
                if persistence_file.exists():
                    persistence_file.unlink()
            except Exception:
                pass

        _LOG.debug("Cleaned up %d completed background tasks", len(to_remove))
        return len(to_remove)


# ---------------------------------------------------------------------------
# Progress reporting helper
# ---------------------------------------------------------------------------


class ProgressReporter:
    """Helper for reporting progress from within a task."""

    def __init__(
        self,
        task_id: str,
        event_bus: Optional[EventBus] = None,
        callback: Optional[Callable[[float, str, Optional[str]], None]] = None,
    ):
        self._task_id = task_id
        self._event_bus = event_bus
        self._callback = callback
        self._current_step: Optional[str] = None
        self._progress = 0.0

    def update(self, progress: float, message: str = "", step: Optional[str] = None) -> None:
        """Report progress (0.0 to 1.0)."""
        self._progress = max(0.0, min(1.0, progress))
        if step:
            self._current_step = step

        # Call callback
        if self._callback:
            try:
                self._callback(self._progress, message, self._current_step)
            except Exception:
                _LOG.exception("Progress callback failed")

        # Publish event
        if self._event_bus:
            try:
                self._event_bus.publish(
                    TaskProgressEvent(self._task_id, self._progress, message, self._current_step)
                )
            except Exception:
                _LOG.exception("Failed to publish progress event")

    def step_started(self, step_id: str, message: str = "") -> None:
        """Report that a step has started."""
        self._current_step = step_id
        self.update(self._progress, message or f"Starting step {step_id}", step_id)

    def step_completed(self, step_id: str, message: str = "") -> None:
        """Report that a step has completed."""
        self.update(self._progress, message or f"Completed step {step_id}", step_id)

    def set_total_steps(self, total: int) -> None:
        """Set the total number of steps for automatic progress calculation."""
        self._total_steps = total
        self._completed_steps = 0

    def next_step(self, step_id: str, message: str = "") -> None:
        """Advance to the next step (auto-calculates progress)."""
        if not hasattr(self, "_total_steps") or self._total_steps <= 0:
            self.step_started(step_id, message)
            return

        self._completed_steps += 1
        progress = self._completed_steps / self._total_steps
        self.step_started(step_id, message)
        self.update(progress, message, step_id)


# ---------------------------------------------------------------------------
# Global instance
# ---------------------------------------------------------------------------


_background_manager: Optional[BackgroundTaskManager] = None


def get_background_manager() -> BackgroundTaskManager:
    """Get the global background task manager."""
    global _background_manager
    if _background_manager is None:
        _background_manager = BackgroundTaskManager()
    return _background_manager


def set_background_manager(manager: BackgroundTaskManager) -> None:
    """Set the global background task manager."""
    global _background_manager
    _background_manager = manager