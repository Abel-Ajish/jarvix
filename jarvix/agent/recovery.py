"""Recovery strategies for failed steps.

Provides strategies for handling step failures:
- rollback: Undo completed steps
- compensate: Run compensating actions
- alternative_path: Try alternative execution path
- partial_completion: Report partial completion and stop
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from jarvix.agent.task import (
    Plan,
    RecoveryAction,
    StepStatus,
    Task,
    TaskResult,
    TaskStep,
    TaskStatus,
    ToolAssignment,
)
from jarvix.core.execution import ExecContext
from jarvix.core.logger import get_logger
from jarvix.core.tool_registry import ToolResult

_LOG = get_logger("jarvix.agent.recovery")


# ---------------------------------------------------------------------------
# Recovery result
# ---------------------------------------------------------------------------


@dataclass
class RecoveryResult:
    """Result of a recovery attempt."""

    action: RecoveryAction
    success: bool
    message: str
    rolled_back_steps: List[str] = field(default_factory=list)
    compensating_results: Dict[str, ToolResult] = field(default_factory=dict)
    partial_results: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Compensation action
# ---------------------------------------------------------------------------


@dataclass
class CompensationAction:
    """A compensating action for a completed step."""

    step_id: str
    description: str
    tool_name: str
    args: Dict[str, Any]
    # Optional: custom function for complex compensation
    custom_fn: Optional[Callable[..., Any]] = None


# ---------------------------------------------------------------------------
# Recovery manager
# ---------------------------------------------------------------------------


class RecoveryManager:
    """Manages recovery strategies for failed task execution."""

    def __init__(self):
        self._compensation_map: Dict[str, CompensationAction] = {}

    def register_compensation(
        self,
        step_id: str,
        tool_name: str,
        args: Dict[str, Any],
        description: str = "",
        custom_fn: Optional[Callable[..., Any]] = None,
    ) -> None:
        """Register a compensation action for a step.

        This should be called when a step completes successfully,
        so we know how to undo it if a later step fails.
        """
        self._compensation_map[step_id] = CompensationAction(
            step_id=step_id,
            description=description or f"Undo step {step_id}",
            tool_name=tool_name,
            args=args,
            custom_fn=custom_fn,
        )

    def get_compensation(self, step_id: str) -> Optional[CompensationAction]:
        """Get the compensation action for a step."""
        return self._compensation_map.get(step_id)

    async def recover(
        self,
        task: Task,
        failed_step: TaskStep,
        tool_result: ToolResult,
        completed_steps: Dict[str, ToolResult],
        execute_fn: Callable[[TaskStep], Any],
        recovery_action: RecoveryAction = RecoveryAction.PARTIAL_COMPLETION,
        ctx: Optional[ExecContext] = None,
    ) -> RecoveryResult:
        """Attempt recovery based on the specified strategy.

        Args:
            task: The task being executed
            failed_step: The step that failed
            tool_result: The failed tool result
            completed_steps: Dict of step_id -> ToolResult for completed steps
            execute_fn: Function to execute a step (for compensation)
            recovery_action: Which recovery strategy to use
            ctx: Execution context for cancellation

        Returns:
            RecoveryResult with outcome
        """
        if ctx:
            ctx.check_cancelled()

        _LOG.info(
            "Attempting recovery for step %s with action %s",
            failed_step.id,
            recovery_action.value,
        )

        if recovery_action == RecoveryAction.ROLLBACK:
            return await self._rollback(task, failed_step, completed_steps, execute_fn, ctx)
        elif recovery_action == RecoveryAction.COMPENSATE:
            return await self._compensate(failed_step, completed_steps, execute_fn, ctx)
        elif recovery_action == RecoveryAction.ALTERNATIVE_PATH:
            return await self._alternative_path(task, failed_step, completed_steps, execute_fn, ctx)
        elif recovery_action == RecoveryAction.PARTIAL_COMPLETION:
            # Note: _partial_completion is intentionally sync (no async ops needed)
            return self._partial_completion(task, failed_step, completed_steps)
        else:
            return RecoveryResult(
                action=recovery_action,
                success=False,
                message=f"Unknown recovery action: {recovery_action}",
            )

    async def _rollback(
        self,
        task: Task,
        failed_step: TaskStep,
        completed_steps: Dict[str, ToolResult],
        execute_fn: Callable[[TaskStep], Any],
        ctx: Optional[ExecContext] = None,
    ) -> RecoveryResult:
        """Rollback completed steps in reverse order."""
        rolled_back = []

        # Get completed step IDs in reverse order
        completed_ids = [
            sid for sid, result in completed_steps.items() if result.ok
        ]
        completed_ids.reverse()

        for step_id in completed_ids:
            if ctx:
                ctx.check_cancelled()

            compensation = self.get_compensation(step_id)
            if not compensation:
                _LOG.warning("No compensation registered for step %s", step_id)
                continue

            try:
                _LOG.info("Rolling back step %s: %s", step_id, compensation.description)

                # Create a compensation step
                comp_step = TaskStep(
                    id=f"rollback_{step_id}",
                    description=f"Rollback: {compensation.description}",
                    tool=ToolAssignment(
                        name=compensation.tool_name,
                        args=compensation.args,
                    ),
                )

                if compensation.custom_fn:
                    await compensation.custom_fn(step_id, completed_steps[step_id])
                else:
                    result = await execute_fn(comp_step)
                    if not isinstance(result, ToolResult) or not result.ok:
                        err_msg = getattr(result, 'error', str(result))
                        _LOG.exception("Compensation step %s failed: %s", step_id, err_msg)
                        return RecoveryResult(
                            action=RecoveryAction.ROLLBACK,
                            success=False,
                            message=f"Compensation failed at step {step_id}: {err_msg}",
                            rolled_back_steps=rolled_back,
                        )

                rolled_back.append(step_id)

            except Exception as e:
                _LOG.exception("Failed to rollback step %s", step_id)
                return RecoveryResult(
                    action=RecoveryAction.ROLLBACK,
                    success=False,
                    message=f"Rollback failed at step {step_id}: {e}",
                    rolled_back_steps=rolled_back,
                )

        return RecoveryResult(
            action=RecoveryAction.ROLLBACK,
            success=True,
            message=f"Rolled back {len(rolled_back)} steps",
            rolled_back_steps=rolled_back,
        )

    async def _compensate(
        self,
        failed_step: TaskStep,
        completed_steps: Dict[str, ToolResult],
        execute_fn: Callable[[TaskStep], Any],
        ctx: Optional[ExecContext] = None,
    ) -> RecoveryResult:
        """Run compensating actions for completed steps without full rollback."""
        compensating_results = {}

        # Get completed step IDs (order doesn't matter for compensation)
        completed_ids = [
            sid for sid, result in completed_steps.items() if result.ok
        ]

        for step_id in completed_ids:
            if ctx:
                ctx.check_cancelled()

            compensation = self.get_compensation(step_id)
            if not compensation:
                _LOG.debug("No compensation for step %s", step_id)
                continue

            try:
                _LOG.info("Compensating step %s: %s", step_id, compensation.description)

                comp_step = TaskStep(
                    id=f"compensate_{step_id}",
                    description=f"Compensate: {compensation.description}",
                    tool=ToolAssignment(
                        name=compensation.tool_name,
                        args=compensation.args,
                    ),
                )

                if compensation.custom_fn:
                    result = await compensation.custom_fn(step_id, completed_steps[step_id])
                    compensating_results[step_id] = (
                        result if isinstance(result, ToolResult) else ToolResult.success("Custom compensation done")
                    )
                else:
                    result = await execute_fn(comp_step)
                    compensating_results[step_id] = result

            except Exception as e:
                _LOG.exception("Failed to compensate step %s", step_id)
                compensating_results[step_id] = ToolResult.failure(f"Compensation failed: {e}")

        return RecoveryResult(
            action=RecoveryAction.COMPENSATE,
            success=True,
            message=f"Ran compensation for {len(compensating_results)} steps",
            compensating_results=compensating_results,
        )

    async def _alternative_path(
        self,
        task: Task,
        failed_step: TaskStep,
        completed_steps: Dict[str, ToolResult],
        execute_fn: Callable[[TaskStep], Any],
        ctx: Optional[ExecContext] = None,
    ) -> RecoveryResult:
        """Try an alternative execution path.

        This looks for alternative steps in the plan that could achieve
        the same goal, or uses fallback tools from the failed step.
        """
        if not task.plan:
            return RecoveryResult(
                action=RecoveryAction.ALTERNATIVE_PATH,
                success=False,
                message="No plan available for alternative path",
            )

        # Try fallback tools from the failed step
        if failed_step.tool.fallback_tools:
            for alt_tool in failed_step.tool.fallback_tools:
                if ctx:
                    ctx.check_cancelled()

                _LOG.info("Trying alternative tool %s for step %s", alt_tool, failed_step.id)

                alt_step = TaskStep(
                    id=f"{failed_step.id}_alt_{alt_tool}",
                    description=f"Alternative: {failed_step.description} (using {alt_tool})",
                    tool=ToolAssignment(
                        name=alt_tool,
                        args=failed_step.tool.args.copy(),
                    ),
                    success_criteria=failed_step.success_criteria,
                )

                try:
                    result = await execute_fn(alt_step)
                    if result.ok:
                        return RecoveryResult(
                            action=RecoveryAction.ALTERNATIVE_PATH,
                            success=True,
                            message=f"Alternative tool {alt_tool} succeeded",
                            partial_results={alt_step.id: result.data},
                        )
                except Exception as e:
                    _LOG.warning("Alternative tool %s failed: %s", alt_tool, e)
                    continue

        # Look for alternative steps in plan with similar descriptions
        # (simplified - in practice could use AI to find alternatives)
        for step in task.plan.steps:
            if step.id == failed_step.id:
                continue
            if step.status == StepStatus.PENDING:
                # Check if this step could substitute
                _LOG.info("Found pending step %s as potential alternative", step.id)
                # Would need more sophisticated matching

        return RecoveryResult(
            action=RecoveryAction.ALTERNATIVE_PATH,
            success=False,
            message="No viable alternative path found",
        )

    def _partial_completion(
        self,
        task: Task,
        failed_step: TaskStep,
        completed_steps: Dict[str, ToolResult],
    ) -> RecoveryResult:
        """Report partial completion and stop."""
        partial_results = {}

        for step_id, result in completed_steps.items():
            if result.ok:
                partial_results[step_id] = {
                    "output": result.output,
                    "data": result.data,
                }

        return RecoveryResult(
            action=RecoveryAction.PARTIAL_COMPLETION,
            success=True,  # This is a successful "partial" outcome
            message=f"Task partially completed: {len(partial_results)} steps succeeded, failed at {failed_step.id}",
            partial_results=partial_results,
        )


# ---------------------------------------------------------------------------
# Automatic recovery action selection
# ---------------------------------------------------------------------------


def select_recovery_action(
    failed_step: TaskStep,
    tool_result: ToolResult,
    verification_result: Optional[Dict[str, Any]] = None,
    completed_count: int = 0,
) -> RecoveryAction:
    """Automatically select the best recovery action based on context.

    Args:
        failed_step: The step that failed
        tool_result: The tool result
        verification_result: Optional verification result
        completed_count: Number of previously completed steps

    Returns:
        Recommended RecoveryAction
    """
    # If verifier suggested an action, prefer that
    if verification_result:
        suggested = verification_result.get("suggested_action")
        if suggested == "escalate":
            return RecoveryAction.PARTIAL_COMPLETION
        elif suggested == "skip":
            return RecoveryAction.PARTIAL_COMPLETION

    # If we have fallback tools, try alternative path first
    if failed_step.tool.fallback_tools:
        return RecoveryAction.ALTERNATIVE_PATH

    # If many steps completed, try to compensate rather than lose all progress
    if completed_count > 2:
        return RecoveryAction.COMPENSATE

    # If critical step (first step or has many dependents), try rollback
    if completed_count == 0 or failed_step.dependencies:
        return RecoveryAction.ROLLBACK

    # Default: partial completion
    return RecoveryAction.PARTIAL_COMPLETION


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


async def recover_from_failure(
    task: Task,
    failed_step: TaskStep,
    tool_result: ToolResult,
    completed_steps: Dict[str, ToolResult],
    execute_fn: Callable[[TaskStep], Any],
    recovery_action: Optional[RecoveryAction] = None,
    ctx: Optional[ExecContext] = None,
) -> RecoveryResult:
    """Convenience function to recover from a step failure."""
    manager = RecoveryManager()

    if recovery_action is None:
        recovery_action = select_recovery_action(
            failed_step, tool_result, completed_count=len(completed_steps)
        )

    return await manager.recover(
        task, failed_step, tool_result, completed_steps, execute_fn, recovery_action, ctx
    )