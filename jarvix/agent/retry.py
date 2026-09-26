"""Retry logic with exponential backoff and strategy selection.

Handles retries for failed steps with configurable strategies:
- retry_same: Retry the same step with same tool
- try_alternative: Try a different tool from fallback_tools
- skip: Skip this step and continue
- escalate: Escalate to human / stop execution
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from jarvix.agent.task import RetryStrategy, StepStatus, TaskStep
from jarvix.core.execution import ExecContext
from jarvix.core.logger import get_logger
from jarvix.core.tool_registry import ToolResult

_LOG = get_logger("jarvix.agent.retry")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    backoff_multiplier: float = 2.0
    jitter: float = 0.1  # 10% jitter
    retry_on_tool_error: bool = True
    retry_on_verification_failure: bool = True


DEFAULT_RETRY_CONFIG = RetryConfig()


# ---------------------------------------------------------------------------
# Retry decision
# ---------------------------------------------------------------------------


class RetryDecision(Enum):
    """Decision for what to do after a failure."""

    RETRY_SAME = "retry_same"
    TRY_ALTERNATIVE = "try_alternative"
    SKIP = "skip"
    ESCALATE = "escalate"
    NO_RETRY = "no_retry"  # Max attempts reached


@dataclass
class RetryAction:
    """Action to take for retry."""

    decision: RetryDecision
    delay: float = 0.0
    alternative_tool: Optional[str] = None
    reason: str = ""


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------


class RetryManager:
    """Manages retry logic for step execution."""

    def __init__(self, config: Optional[RetryConfig] = None):
        self._config = config or DEFAULT_RETRY_CONFIG

    def calculate_delay(self, attempt: int, base_delay: Optional[float] = None) -> float:
        """Calculate delay with exponential backoff and jitter."""
        base = base_delay or self._config.base_delay
        delay = base * (self._config.backoff_multiplier ** attempt)
        delay = min(delay, self._config.max_delay)

        # Add jitter
        jitter_range = delay * self._config.jitter
        delay += random.uniform(-jitter_range, jitter_range)

        return max(0.0, delay)

    def decide_retry(
        self,
        step: TaskStep,
        tool_result: ToolResult,
        verification_result: Optional[Dict[str, Any]] = None,
        attempt: int = 0,
    ) -> RetryAction:
        """Decide what retry action to take.

        Args:
            step: The step that failed
            tool_result: The tool execution result
            verification_result: Optional verification result
            attempt: Current attempt number (0-indexed)

        Returns:
            RetryAction with decision and parameters
        """
        # Check if we've exhausted attempts
        if attempt >= step.max_retries:
            _LOG.info("Step %s: max retries (%d) reached", step.id, step.max_retries)
            return RetryAction(
                decision=RetryDecision.NO_RETRY,
                reason=f"Max retries ({step.max_retries}) reached",
            )

        # Check if we should retry based on config
        if not tool_result.ok and not self._config.retry_on_tool_error:
            return RetryAction(
                decision=RetryDecision.NO_RETRY,
                reason="Tool error and retry_on_tool_error is disabled",
            )

        # Check verification result for suggested action
        if verification_result:
            suggested = verification_result.get("suggested_action", "retry")
            if suggested == "escalate":
                return RetryAction(
                    decision=RetryDecision.ESCALATE,
                    reason="Verifier suggested escalation",
                )
            elif suggested == "skip":
                return RetryAction(
                    decision=RetryDecision.SKIP,
                    reason="Verifier suggested skipping step",
                )
            elif suggested == "retry":
                pass  # Continue to strategy selection

        # Determine retry strategy
        # Priority: 1. Has fallback tools -> try_alternative
        #           2. Default -> retry_same

        if step.tool.fallback_tools:
            # Try alternative tool
            return RetryAction(
                decision=RetryDecision.TRY_ALTERNATIVE,
                delay=self.calculate_delay(attempt, step.retry_delay),
                alternative_tool=step.tool.fallback_tools[0],
                reason=f"Trying fallback tool: {step.tool.fallback_tools[0]}",
            )

        # Default: retry same step
        return RetryAction(
            decision=RetryDecision.RETRY_SAME,
            delay=self.calculate_delay(attempt, step.retry_delay),
            reason=f"Retrying same step (attempt {attempt + 1}/{step.max_retries})",
        )

    async def execute_with_retry(
        self,
        step: TaskStep,
        execute_fn: Callable[[TaskStep], Any],
        verify_fn: Optional[Callable[[TaskStep, ToolResult], Any]] = None,
        ctx: Optional[ExecContext] = None,
    ) -> Tuple[ToolResult, Dict[str, Any]]:
        """Execute a step with retry logic.

        Args:
            step: The step to execute
            execute_fn: Async function that executes the step and returns ToolResult
            verify_fn: Optional async function that verifies the result
            ctx: Execution context for cancellation

        Returns:
            Tuple of (final ToolResult, verification result dict)
        """
        last_result: Optional[ToolResult] = None
        last_verification: Optional[Dict[str, Any]] = None

        for attempt in range(step.max_retries + 1):
            if ctx:
                ctx.check_cancelled()

            step.attempts = attempt + 1
            step.status = StepStatus.RETRYING if attempt > 0 else StepStatus.RUNNING

            _LOG.debug("Executing step %s (attempt %d/%d)", step.id, attempt + 1, step.max_retries + 1)

            try:
                # Execute the step
                result = await execute_fn(step)
                last_result = result

                # Verify if verification function provided
                if verify_fn and result.ok:
                    verification = await verify_fn(step, result)
                    last_verification = verification

                    if verification.get("passed", False):
                        _LOG.info("Step %s passed verification on attempt %d", step.id, attempt + 1)
                        return result, verification

                    _LOG.info("Step %s failed verification on attempt %d: %s", step.id, attempt + 1, verification.get("reasoning"))

                elif result.ok:
                    # No verification, tool succeeded
                    _LOG.info("Step %s succeeded (no verification)", step.id)
                    return result, {"passed": True, "reasoning": "Tool succeeded, no verification"}

                # Tool failed or verification failed
                _LOG.warning("Step %s failed on attempt %d: %s", step.id, attempt + 1, result.error or "verification failed")

            except asyncio.CancelledError:
                raise
            except Exception as e:
                _LOG.exception("Step %s raised exception on attempt %d", step.id, attempt + 1)
                last_result = ToolResult.failure(f"Exception: {e}")

            # Decide retry action
            action = self.decide_retry(step, last_result or ToolResult.failure("Unknown error"), last_verification, attempt)

            if action.decision == RetryDecision.NO_RETRY:
                _LOG.info("Step %s: no more retries", step.id)
                break
            elif action.decision == RetryDecision.ESCALATE:
                _LOG.warning("Step %s: escalating", step.id)
                break
            elif action.decision == RetryDecision.SKIP:
                _LOG.info("Step %s: skipping", step.id)
                return ToolResult.success("Step skipped", data={"skipped": True}), {
                    "passed": True,
                    "reasoning": "Step skipped per retry decision",
                }
            elif action.decision == RetryDecision.TRY_ALTERNATIVE:
                if action.alternative_tool:
                    _LOG.info("Step %s: switching to alternative tool %s", step.id, action.alternative_tool)
                    # Modify step to use alternative tool
                    step.tool.name = action.alternative_tool
                    step.tool.fallback_tools = step.tool.fallback_tools[1:]
                else:
                    _LOG.warning("Step %s: no alternative tools available", step.id)
                    action.decision = RetryDecision.RETRY_SAME

            # Wait before retry
            if action.delay > 0:
                _LOG.debug("Waiting %.2fs before retry", action.delay)
                try:
                    await asyncio.sleep(action.delay)
                except asyncio.CancelledError:
                    raise

        # All retries exhausted
        step.status = StepStatus.FAILED
        return last_result or ToolResult.failure("All retries exhausted"), last_verification or {
            "passed": False,
            "reasoning": "All retries exhausted",
        }


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


async def execute_with_retry(
    step: TaskStep,
    execute_fn: Callable[[TaskStep], Any],
    verify_fn: Optional[Callable[[TaskStep, ToolResult], Any]] = None,
    config: Optional[RetryConfig] = None,
    ctx: Optional[ExecContext] = None,
) -> Tuple[ToolResult, Dict[str, Any]]:
    """Convenience function to execute a step with retry logic."""
    manager = RetryManager(config)
    return await manager.execute_with_retry(step, execute_fn, verify_fn, ctx)