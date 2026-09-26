"""Task lifecycle management for the Advanced Agent subsystem.

Handles creating, queuing, executing, monitoring, cancelling, and persisting tasks.
Integrates with EventBus for progress events and coordinates with planner,
verifier, retry, recovery, and background execution.
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

from jarvix.agent.background import BackgroundTaskManager, ProgressReporter, get_background_manager
from jarvix.agent.planner import Planner, create_plan
from jarvix.agent.recovery import RecoveryManager, RecoveryResult, select_recovery_action
from jarvix.agent.retry import RetryManager, execute_with_retry
from jarvix.agent.task import (
    Plan,
    Task,
    TaskResult,
    TaskStatus,
    TaskStep,
    StepStatus,
)
from jarvix.agent.verifier import Verifier, verify_step
from jarvix.core.events import EventBus
from jarvix.core.execution import ExecContext
from jarvix.core.logger import get_logger
from jarvix.core.tool_registry import ToolRegistry, ToolResult

_LOG = get_logger("jarvix.agent.task_manager")


# ---------------------------------------------------------------------------
# Task execution context
# ---------------------------------------------------------------------------


@dataclass
class ExecutionContext:
    """Context for task execution."""

    task: Task
    plan: Plan
    tool_registry: ToolRegistry
    event_bus: EventBus
    ai_engine: Any  # AIEngine
    exec_ctx: ExecContext
    progress: ProgressReporter
    completed_steps: Dict[str, ToolResult] = field(default_factory=dict)
    failed_step: Optional[TaskStep] = None


# ---------------------------------------------------------------------------
# Task manager
# ---------------------------------------------------------------------------


class TaskManager:
    """Manages the full lifecycle of agent tasks."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        event_bus: EventBus,
        ai_engine: Any,  # AIEngine
        background_manager: Optional[BackgroundTaskManager] = None,
        persist_dir: Optional[Path] = None,
    ):
        self._tool_registry = tool_registry
        self._event_bus = event_bus
        self._ai_engine = ai_engine
        self._background_manager = background_manager or get_background_manager()
        self._background_manager.set_event_bus(event_bus)

        # Initialize sub-components
        self._planner = Planner(ai_engine)
        self._verifier = Verifier(ai_engine)
        self._retry_manager = RetryManager()
        self._recovery_manager = RecoveryManager()

        # Persistence
        self._persist_dir = persist_dir or Path.home() / "AppData" / "Roaming" / "jarvix" / "tasks"
        self._persist_dir.mkdir(parents=True, exist_ok=True)

        # Active tasks
        self._active_tasks: Dict[str, Task] = {}
        self._execution_contexts: Dict[str, ExecutionContext] = {}

    # -----------------------------------------------------------------------
    # Task creation
    # -----------------------------------------------------------------------

    def create_task(
        self,
        name: str,
        goal: str,
        *,
        description: str = "",
        context: str = "",
        max_steps: int = 10,
        allowed_tools: Optional[List[str]] = None,
        background: bool = True,
    ) -> Task:
        """Create a new task (plans but doesn't execute yet).

        Args:
            name: Human-readable task name
            goal: The goal to achieve
            description: Optional detailed description
            context: Additional context for planning
            max_steps: Maximum steps in plan
            allowed_tools: Optional tool restriction
            background: Whether to run in background

        Returns:
            Created Task object
        """
        task = Task(
            id=str(uuid.uuid4())[:8],
            name=name,
            description=description or goal,
            status=TaskStatus.PENDING,
            metadata={
                "goal": goal,
                "context": context,
                "max_steps": max_steps,
                "allowed_tools": allowed_tools,
                "background": background,
            },
        )

        self._active_tasks[task.id] = task
        _LOG.info("Created task %s: %s", task.id, name)
        return task

    async def plan_task(
        self,
        task: Task,
        ctx: Optional[ExecContext] = None,
    ) -> Plan:
        """Generate a plan for the task.

        Args:
            task: The task to plan
            ctx: Execution context for cancellation

        Returns:
            Generated Plan
        """
        if ctx:
            ctx.check_cancelled()

        goal = task.metadata.get("goal", task.description)
        context = task.metadata.get("context", "")
        max_steps = task.metadata.get("max_steps", 10)
        allowed_tools = task.metadata.get("allowed_tools")

        _LOG.info("Planning task %s: %s", task.id, goal[:100])
        plan = await self._planner.create_plan(
            goal,
            context=context,
            max_steps=max_steps,
            allowed_tools=allowed_tools,
            ctx=ctx,
        )

        task.plan = plan
        return plan

    # -----------------------------------------------------------------------
    # Task execution
    # -----------------------------------------------------------------------

    async def execute_task(
        self,
        task: Task,
        *,
        background: bool = True,
        ctx: Optional[ExecContext] = None,
    ) -> TaskResult:
        """Execute a task (plan + execute).

        Args:
            task: The task to execute
            background: Whether to run in background
            ctx: Execution context for cancellation

        Returns:
            TaskResult
        """
        if ctx:
            ctx.check_cancelled()

        # Plan if not already planned
        if not task.plan:
            await self.plan_task(task, ctx=ctx)

        if not task.plan or not task.plan.steps:
            raise RuntimeError("No plan generated for task")

        if background:
            return await self._execute_background(task, ctx)
        else:
            return await self._execute_foreground(task, ctx)

    async def _execute_foreground(
        self,
        task: Task,
        ctx: Optional[ExecContext] = None,
    ) -> TaskResult:
        """Execute task in foreground (blocking)."""
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()

        # Create execution context
        exec_ctx = ctx or ExecContext()
        progress = ProgressReporter(task.id, self._event_bus)
        progress.set_total_steps(len(task.plan.steps))

        exec_context = ExecutionContext(
            task=task,
            plan=task.plan,
            tool_registry=self._tool_registry,
            event_bus=self._event_bus,
            ai_engine=self._ai_engine,
            exec_ctx=exec_ctx,
            progress=progress,
        )
        self._execution_contexts[task.id] = exec_context

        try:
            result = await self._run_plan(exec_context)
            task.result = result
            task.status = TaskStatus.COMPLETED if result.status == TaskStatus.COMPLETED else TaskStatus.FAILED
            task.completed_at = datetime.now()
            return result

        except asyncio.CancelledError:
            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.now()
            raise
        except Exception as e:
            _LOG.exception("Task %s failed", task.id)
            task.status = TaskStatus.FAILED
            task.completed_at = datetime.now()
            error_result = TaskResult(
                task_id=task.id,
                plan_id=task.plan.id,
                status=TaskStatus.FAILED,
                started_at=task.started_at or datetime.now(),
                completed_at=datetime.now(),
                error=str(e),
            )
            task.result = error_result
            return error_result
        finally:
            self._execution_contexts.pop(task.id, None)

    async def _execute_background(
        self,
        task: Task,
        ctx: Optional[ExecContext] = None,
    ) -> TaskResult:
        """Execute task in background (non-blocking)."""
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()

        def _execute_fn(task_obj: Task, exec_ctx: ExecContext) -> Any:
            # Create a new execution context for this task
            progress = ProgressReporter(task_obj.id, self._event_bus)
            progress.set_total_steps(len(task_obj.plan.steps) if task_obj.plan else 1)

            exec_context = ExecutionContext(
                task=task_obj,
                plan=task_obj.plan,
                tool_registry=self._tool_registry,
                event_bus=self._event_bus,
                ai_engine=self._ai_engine,
                exec_ctx=exec_ctx,
                progress=progress,
            )
            self._execution_contexts[task_obj.id] = exec_context

            async def _run():
                try:
                    return await self._run_plan(exec_context)
                finally:
                    self._execution_contexts.pop(task_obj.id, None)

            # Handle case where we're already in an async context
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # No running loop - safely create one
                return asyncio.run(_run())
            else:
                # Already have running loop - use create_task
                asyncio.create_task(_run())
                return None  # Background execution - no return value

        # Submit to background manager
        self._background_manager.submit(task, _execute_fn)

        # Return a pending result
        return TaskResult(
            task_id=task.id,
            plan_id=task.plan.id,
            status=TaskStatus.RUNNING,
            started_at=task.started_at or datetime.now(),
        )

    async def _run_plan(self, exec_context: ExecutionContext) -> TaskResult:
        """Execute all steps in the plan."""
        task = exec_context.task
        plan = exec_context.plan
        progress = exec_context.progress

        completed_step_ids: Set[str] = set()
        step_results: Dict[str, ToolResult] = {}

        for step in plan.steps:
            exec_context.exec_ctx.check_cancelled()

            # Check dependencies
            if not all(dep in completed_step_ids for dep in step.dependencies):
                # Dependencies not met - this shouldn't happen with proper planning
                _LOG.warning("Step %s dependencies not met, skipping", step.id)
                step.status = StepStatus.SKIPPED
                continue

            # Execute step with retry
            step.status = StepStatus.RUNNING
            step.started_at = datetime.now()
            progress.next_step(step.id, f"Executing: {step.description}")

            # Define step execution function
            async def execute_step(s: TaskStep) -> ToolResult:
                return await self._execute_single_step(s, exec_context)

            # Define verification function
            async def verify_step_fn(s: TaskStep, result: ToolResult) -> Dict[str, Any]:
                return await self._verifier.verify_step(s, result, plan=plan, ctx=exec_context.exec_ctx)

            # Execute with retry
            result, verification = await self._retry_manager.execute_with_retry(
                step,
                execute_step,
                verify_step_fn,
                exec_context.exec_ctx,
            )

            step_results[step.id] = result
            exec_context.completed_steps[step.id] = result

            if verification.get("passed", False):
                step.status = StepStatus.COMPLETED
                step.completed_at = datetime.now()
                step.result = result.output
                completed_step_ids.add(step.id)
                progress.step_completed(step.id, f"Completed: {step.description}")
                # Persist task state after each step completion
                self.save_task(task)

                # Register compensation for potential rollback
                self._recovery_manager.register_compensation(
                    step.id,
                    step.tool.name,
                    step.tool.args,
                    description=f"Undo: {step.description}",
                )

            else:
                step.status = StepStatus.FAILED
                step.completed_at = datetime.now()
                step.error = result.error or verification.get("reasoning", "Verification failed")

                # Determine recovery action
                recovery_action = select_recovery_action(
                    step, result, verification, len(completed_step_ids)
                )

                _LOG.info("Step %s failed, attempting recovery: %s", step.id, recovery_action.value)

                recovery_result = await self._recovery_manager.recover(
                    task,
                    step,
                    result,
                    exec_context.completed_steps,
                    execute_step,
                    recovery_action,
                    exec_context.exec_ctx,
                )

                if recovery_result.success and recovery_action != RecoveryAction.PARTIAL_COMPLETION:
                    # Recovery succeeded, continue with next step
                    completed_step_ids.add(step.id)
                    step_results.update(recovery_result.partial_results)
                    continue

                # Recovery failed or partial completion - stop execution
                exec_context.failed_step = step
                break

        # Build final result
        overall_status = TaskStatus.COMPLETED
        if exec_context.failed_step:
            overall_status = TaskStatus.FAILED

        # Verify overall plan
        plan_verification = await self._verifier.verify_plan(plan, step_results, exec_context.exec_ctx)

        return TaskResult(
            task_id=task.id,
            plan_id=plan.id,
            status=overall_status,
            started_at=task.started_at or datetime.now(),
            completed_at=datetime.now(),
            step_results={k: v.output for k, v in step_results.items()},
            error=exec_context.failed_step.error if exec_context.failed_step else None,
            partial_results=step_results,
        )

    async def _execute_single_step(
        self,
        step: TaskStep,
        exec_context: ExecutionContext,
    ) -> ToolResult:
        """Execute a single step using the tool registry."""
        exec_context.exec_ctx.check_cancelled()

        tool_name = step.tool.name
        tool_args = step.tool.args

        _LOG.debug("Executing step %s with tool %s", step.id, tool_name)

        # Check if tool exists
        tool = self._tool_registry.get(tool_name)
        if not tool:
            return ToolResult.failure(f"Tool '{tool_name}' not found")

        # Execute via tool registry
        if asyncio.iscoroutinefunction(tool.execute):
            result = await self._tool_registry.execute_async(tool_name, tool_args, exec_context.exec_ctx)
        else:
            result = self._tool_registry.execute(tool_name, tool_args, exec_context.exec_ctx)

        # Handle CONFIRM_REQUIRED - in real execution this would need UI confirmation
        # For now, we treat it as failure
        if result.error and result.error.startswith("CONFIRM_REQUIRED"):
            return ToolResult.failure(f"Tool '{tool_name}' requires confirmation")

        return result

    # -----------------------------------------------------------------------
    # Task control
    # -----------------------------------------------------------------------

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task."""
        # Cancel foreground task
        exec_context = self._execution_contexts.get(task_id)
        if exec_context:
            exec_context.exec_ctx.cancel_event.set()
            return True

        # Cancel background task
        return self._background_manager.cancel(task_id)

    def pause_task(self, task_id: str) -> bool:
        """Pause a task (not fully implemented - marks as paused)."""
        task = self._active_tasks.get(task_id)
        if task and task.status == TaskStatus.RUNNING:
            task.status = TaskStatus.PAUSED
            _LOG.info("Task %s paused", task_id)
            return True
        return False

    def resume_task(self, task_id: str) -> bool:
        """Resume a paused task (not fully implemented)."""
        task = self._active_tasks.get(task_id)
        if task and task.status == TaskStatus.PAUSED:
            task.status = TaskStatus.RUNNING
            _LOG.info("Task %s resumed", task_id)
            return True
        return False

    # -----------------------------------------------------------------------
    # Task queries
    # -----------------------------------------------------------------------

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        # Check active tasks
        task = self._active_tasks.get(task_id)
        if task:
            return task

        # Check background manager
        bg_task = self._background_manager.get_task(task_id)
        if bg_task:
            return bg_task

        return None

    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """Get task status."""
        task = self.get_task(task_id)
        if task:
            return task.status

        # Check background
        return self._background_manager.get_status(task_id)

    def get_task_result(self, task_id: str) -> Optional[TaskResult]:
        """Get task result."""
        task = self.get_task(task_id)
        if task:
            return task.result

        return self._background_manager.get_result(task_id)

    def list_tasks(
        self,
        *,
        status: Optional[TaskStatus] = None,
        include_background: bool = True,
    ) -> List[Task]:
        """List all tasks."""
        tasks = list(self._active_tasks.values())

        if include_background:
            bg_tasks = self._background_manager.list_tasks()
            # Merge, avoiding duplicates
            existing_ids = {t.id for t in tasks}
            for bg_task in bg_tasks:
                if bg_task.id not in existing_ids:
                    tasks.append(bg_task)

        if status:
            tasks = [t for t in tasks if t.status == status]

        return tasks

    # -----------------------------------------------------------------------
    # Persistence
    # -----------------------------------------------------------------------

    def save_task(self, task: Task) -> Path:
        """Save a task to disk."""
        file_path = self._persist_dir / f"{task.id}.json"
        with file_path.open("w", encoding="utf-8") as f:
            json.dump(task.to_dict(), f, indent=2)
        _LOG.debug("Saved task %s to %s", task.id, file_path)
        return file_path

    def load_task(self, task_id: str) -> Optional[Task]:
        """Load a task from disk."""
        file_path = self._persist_dir / f"{task_id}.json"
        if not file_path.exists():
            return None

        try:
            with file_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return Task.from_dict(data)
        except Exception as e:
            _LOG.error("Failed to load task %s: %s", task_id, e)
            return None

    def list_saved_tasks(self) -> List[str]:
        """List all saved task IDs."""
        return [f.stem for f in self._persist_dir.glob("*.json")]

    def delete_saved_task(self, task_id: str) -> bool:
        """Delete a saved task."""
        file_path = self._persist_dir / f"{task_id}.json"
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    # -----------------------------------------------------------------------
    # Cleanup
    # -----------------------------------------------------------------------

    def cleanup_completed_tasks(self, max_age_hours: float = 24) -> int:
        """Remove completed tasks from memory (not disk)."""
        now = datetime.now()
        to_remove = []

        for task_id, task in self._active_tasks.items():
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                if task.completed_at:
                    age = (now - task.completed_at).total_seconds() / 3600
                    if age > max_age_hours:
                        to_remove.append(task_id)

        for task_id in to_remove:
            del self._active_tasks[task_id]

        # Also clean background manager
        self._background_manager.cleanup_completed(max_age_seconds=max_age_hours * 3600)

        _LOG.info("Cleaned up %d completed tasks", len(to_remove))
        return len(to_remove)


# ---------------------------------------------------------------------------
# Global instance
# ---------------------------------------------------------------------------


_task_manager: Optional[TaskManager] = None


def get_task_manager() -> Optional[TaskManager]:
    """Get the global task manager (if initialized)."""
    return _task_manager


def set_task_manager(manager: TaskManager) -> None:
    """Set the global task manager."""
    global _task_manager
    _task_manager = manager


async def create_task_manager(
    tool_registry: ToolRegistry,
    event_bus: EventBus,
    ai_engine: Any,
    persist_dir: Optional[Path] = None,
) -> TaskManager:
    """Create and initialize the global task manager."""
    manager = TaskManager(
        tool_registry=tool_registry,
        event_bus=event_bus,
        ai_engine=ai_engine,
        persist_dir=persist_dir,
    )
    set_task_manager(manager)
    return manager