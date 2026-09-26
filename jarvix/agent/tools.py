"""Agent tools for the Advanced Agent subsystem.

Tools for planning, executing, and managing multi-step tasks.
All tools register via @tool decorator with proper permissions.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

from jarvix.agent.task_manager import get_task_manager, create_task_manager
from jarvix.agent.task import Task, TaskStatus
from jarvix.core.execution import ExecContext
from jarvix.core.logger import get_logger
from jarvix.core.permissions import PermissionLevel
from jarvix.core.tool_registry import Tool, ToolResult, tool

_LOG = get_logger("jarvix.agent.tools")


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _get_task_manager() -> Optional[Any]:
    """Get the global task manager, creating if needed."""
    from jarvix.agent.task_manager import get_task_manager as _get_tm

    return _get_tm()


def _ensure_task_manager() -> Any:
    """Ensure task manager exists, raise helpful error if not."""
    mgr = _get_task_manager()
    if mgr is None:
        raise RuntimeError(
            "Task manager not initialized. Call create_task_manager() during startup."
        )
    return mgr


def _task_to_dict(task: Task) -> Dict[str, Any]:
    """Convert task to dict for tool output."""
    data = task.to_dict()
    # Add computed fields
    if task.plan:
        data["step_count"] = len(task.plan.steps)
        data["completed_steps"] = sum(
            1 for s in task.plan.steps if s.status.value == "completed"
        )
    return data


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@tool("agent_plan", permission=PermissionLevel.SAFE, description="Create a multi-step plan for a goal")
class AgentPlanTool(Tool):
    """Create a structured execution plan for a natural language goal."""

    name = "agent_plan"
    description = "Create a multi-step plan for a goal using the AI planner"
    permission = PermissionLevel.CONFIRM

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "The goal to achieve (e.g., 'Find all Python files and create a summary')",
                },
                "context": {
                    "type": "string",
                    "description": "Additional context for planning",
                    "default": "",
                },
                "max_steps": {
                    "type": "integer",
                    "description": "Maximum number of steps in the plan",
                    "default": 10,
                },
                "allowed_tools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of tool names to restrict to",
                },
                "task_name": {
                    "type": "string",
                    "description": "Optional name for the task",
                    "default": "",
                },
            },
            "required": ["goal"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        ctx.check_cancelled()

        goal = args.get("goal", "").strip()
        if not goal:
            return ToolResult.failure("goal is required")

        context = args.get("context", "")
        max_steps = args.get("max_steps", 10)
        allowed_tools = args.get("allowed_tools")
        task_name = args.get("task_name", "").strip() or f"Plan: {goal[:50]}"

        try:
            mgr = _ensure_task_manager()

            # Create task
            task = mgr.create_task(
                name=task_name,
                goal=goal,
                context=context,
                max_steps=max_steps,
                allowed_tools=allowed_tools,
                background=False,  # Planning is fast
            )

            # Generate plan
            plan = await mgr.plan_task(task, ctx=ctx)

            return ToolResult.success(
                f"Created plan with {len(plan.steps)} steps for: {goal}",
                data={
                    "task_id": task.id,
                    "plan": plan.model_dump(),
                    "steps": [
                        {
                            "id": s.id,
                            "description": s.description,
                            "tool": s.tool.name,
                            "dependencies": s.dependencies,
                        }
                        for s in plan.steps
                    ],
                },
            )

        except RuntimeError as e:
            return ToolResult.failure(str(e))
        except Exception as e:
            _LOG.exception("Agent plan failed")
            return ToolResult.failure(f"Planning failed: {e}")


@tool("agent_execute", permission=PermissionLevel.SAFE, description="Execute a planned task with verification/retry/recovery")
class AgentExecuteTool(Tool):
    """Execute a task (plan + execute with verification, retry, recovery)."""

    name = "agent_execute"
    description = "Execute a planned task with full verification, retry, and recovery"
    permission = PermissionLevel.CONFIRM

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "ID of the task to execute (from agent_plan)",
                },
                "background": {
                    "type": "boolean",
                    "description": "Run in background (non-blocking)",
                    "default": True,
                },
            },
            "required": ["task_id"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        ctx.check_cancelled()

        task_id = args.get("task_id", "").strip()
        if not task_id:
            return ToolResult.failure("task_id is required")

        background = args.get("background", True)

        try:
            mgr = _ensure_task_manager()

            task = mgr.get_task(task_id)
            if not task:
                return ToolResult.failure(f"Task not found: {task_id}")

            if not task.plan:
                return ToolResult.failure(f"Task {task_id} has no plan. Run agent_plan first.")

            if task.status == TaskStatus.RUNNING:
                return ToolResult.failure(f"Task {task_id} is already running")

            # Execute task
            result = await mgr.execute_task(task, background=background, ctx=ctx)

            if background:
                return ToolResult.success(
                    f"Task {task_id} started in background",
                    data={
                        "task_id": task_id,
                        "status": "running",
                        "background": True,
                    },
                )
            else:
                status_text = "completed" if result.ok else "failed"
                return ToolResult.success(
                    f"Task {task_id} {status_text}",
                    data={
                        "task_id": task_id,
                        "result": result.to_dict(),
                    },
                )

        except RuntimeError as e:
            return ToolResult.failure(str(e))
        except Exception as e:
            _LOG.exception("Agent execute failed")
            return ToolResult.failure(f"Execution failed: {e}")


@tool("agent_task_create", permission=PermissionLevel.SAFE, description="Create a background task from a goal")
class AgentTaskCreateTool(Tool):
    """Create a background task directly from a goal (plans and queues for execution)."""

    name = "agent_task_create"
    description = "Create and queue a background task from a natural language goal"
    permission = PermissionLevel.SAFE

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "goal": {
                    "type": "string",
                    "description": "The goal to achieve",
                },
                "name": {
                    "type": "string",
                    "description": "Optional task name",
                    "default": "",
                },
                "context": {
                    "type": "string",
                    "description": "Additional context",
                    "default": "",
                },
                "max_steps": {
                    "type": "integer",
                    "description": "Maximum steps in plan",
                    "default": 10,
                },
                "auto_execute": {
                    "type": "boolean",
                    "description": "Automatically start execution",
                    "default": True,
                },
            },
            "required": ["goal"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        ctx.check_cancelled()

        goal = args.get("goal", "").strip()
        if not goal:
            return ToolResult.failure("goal is required")

        name = args.get("name", "").strip() or f"Task: {goal[:50]}"
        context = args.get("context", "")
        max_steps = args.get("max_steps", 10)
        auto_execute = args.get("auto_execute", True)

        try:
            mgr = _ensure_task_manager()

            # Create task
            task = mgr.create_task(
                name=name,
                goal=goal,
                context=context,
                max_steps=max_steps,
                background=True,
            )

            if auto_execute:
                # Plan and execute in background
                await mgr.plan_task(task, ctx=ctx)
                await mgr.execute_task(task, background=True, ctx=ctx)

                return ToolResult.success(
                    f"Created and started task {task.id}",
                    data=_task_to_dict(task),
                )
            else:
                return ToolResult.success(
                    f"Created task {task.id} (not started)",
                    data=_task_to_dict(task),
                )

        except RuntimeError as e:
            return ToolResult.failure(str(e))
        except Exception as e:
            _LOG.exception("Agent task create failed")
            return ToolResult.failure(f"Task creation failed: {e}")


@tool("agent_task_status", permission=PermissionLevel.SAFE, description="Get status of a background task")
class AgentTaskStatusTool(Tool):
    """Get the status and progress of a background task."""

    name = "agent_task_status"
    description = "Get status, progress, and result of a background task"
    permission = PermissionLevel.SAFE

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "ID of the task to check",
                },
            },
            "required": ["task_id"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        ctx.check_cancelled()

        task_id = args.get("task_id", "").strip()
        if not task_id:
            return ToolResult.failure("task_id is required")

        try:
            mgr = _ensure_task_manager()

            task = mgr.get_task(task_id)
            if not task:
                return ToolResult.failure(f"Task not found: {task_id}")

            data = _task_to_dict(task)

            # Add step details if plan exists
            if task.plan:
                data["steps"] = [
                    {
                        "id": s.id,
                        "description": s.description,
                        "tool": s.tool.name,
                        "status": s.status.value,
                        "result": s.result,
                        "error": s.error,
                        "attempts": s.attempts,
                    }
                    for s in task.plan.steps
                ]

            return ToolResult.success(
                f"Task {task_id}: {task.status.value}",
                data=data,
            )

        except RuntimeError as e:
            return ToolResult.failure(str(e))
        except Exception as e:
            _LOG.exception("Agent task status failed")
            return ToolResult.failure(f"Status check failed: {e}")


@tool("agent_task_cancel", permission=PermissionLevel.CONFIRM, description="Cancel a running background task")
class AgentTaskCancelTool(Tool):
    """Cancel a running background task."""

    name = "agent_task_cancel"
    description = "Cancel a running background task"
    permission = PermissionLevel.CONFIRM

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "ID of the task to cancel",
                },
            },
            "required": ["task_id"],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        ctx.check_cancelled()

        task_id = args.get("task_id", "").strip()
        if not task_id:
            return ToolResult.failure("task_id is required")

        try:
            mgr = _ensure_task_manager()

            task = mgr.get_task(task_id)
            if not task:
                return ToolResult.failure(f"Task not found: {task_id}")

            if task.status not in (TaskStatus.RUNNING, TaskStatus.PENDING, TaskStatus.PAUSED):
                return ToolResult.failure(f"Task {task_id} is not running (status: {task.status.value})")

            success = mgr.cancel_task(task_id)

            if success:
                return ToolResult.success(
                    f"Cancellation requested for task {task_id}",
                    data={"task_id": task_id, "cancelled": True},
                )
            else:
                return ToolResult.failure(f"Failed to cancel task {task_id}")

        except RuntimeError as e:
            return ToolResult.failure(str(e))
        except Exception as e:
            _LOG.exception("Agent task cancel failed")
            return ToolResult.failure(f"Cancellation failed: {e}")


@tool("agent_task_list", permission=PermissionLevel.SAFE, description="List all background tasks")
class AgentTaskListTool(Tool):
    """List all background tasks with optional status filter."""

    name = "agent_task_list"
    description = "List all tasks with their status"
    permission = PermissionLevel.SAFE

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filter by status",
                    "enum": ["pending", "running", "paused", "completed", "failed", "cancelled"],
                },
                "include_background": {
                    "type": "boolean",
                    "description": "Include background tasks",
                    "default": True,
                },
            },
            "required": [],
        }

    async def execute(self, args: Dict[str, Any], ctx: ExecContext) -> ToolResult:
        ctx.check_cancelled()

        status_str = args.get("status")
        include_background = args.get("include_background", True)

        try:
            mgr = _ensure_task_manager()

            status_filter = None
            if status_str:
                try:
                    status_filter = TaskStatus(status_str)
                except ValueError:
                    return ToolResult.failure(f"Invalid status: {status_str}")

            tasks = mgr.list_tasks(status=status_filter, include_background=include_background)

            task_list = []
            for task in tasks:
                data = {
                    "id": task.id,
                    "name": task.name,
                    "status": task.status.value,
                    "created_at": task.created_at.isoformat(),
                }
                if task.started_at:
                    data["started_at"] = task.started_at.isoformat()
                if task.completed_at:
                    data["completed_at"] = task.completed_at.isoformat()
                if task.plan:
                    data["step_count"] = len(task.plan.steps)
                    data["completed_steps"] = sum(
                        1 for s in task.plan.steps if s.status.value == "completed"
                    )
                task_list.append(data)

            return ToolResult.success(
                f"Found {len(task_list)} task(s)",
                data={"tasks": task_list},
            )

        except RuntimeError as e:
            return ToolResult.failure(str(e))
        except Exception as e:
            _LOG.exception("Agent task list failed")
            return ToolResult.failure(f"Task listing failed: {e}")