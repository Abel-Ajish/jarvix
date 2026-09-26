"""Step verification using AIEngine.structured_output().

Verifies step completion by evaluating execution results against
success criteria. Returns pass/fail with reasoning.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from jarvix.agent.task import (
    Plan,
    StepStatus,
    SuccessCriterion,
    TaskStep,
)
from jarvix.core.tool_registry import ToolResult
from jarvix.core.execution import ExecContext
from jarvix.core.logger import get_logger
from jarvix.engine.ai_engine import AIEngine

_LOG = get_logger("jarvix.agent.verifier")


# ---------------------------------------------------------------------------
# JSON Schema for verification output
# ---------------------------------------------------------------------------

VERIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "passed": {"type": "boolean", "description": "Whether the step passed verification"},
        "reasoning": {"type": "string", "description": "Detailed reasoning for the decision"},
        "criteria_results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "criterion": {"type": "string"},
                    "passed": {"type": "boolean"},
                    "reasoning": {"type": "string"},
                },
                "required": ["criterion", "passed", "reasoning"],
            },
        },
        "suggested_action": {
            "type": "string",
            "enum": ["continue", "retry", "skip", "escalate"],
            "description": "Suggested next action if verification failed",
        },
    },
    "required": ["passed", "reasoning", "criteria_results", "suggested_action"],
}


# ---------------------------------------------------------------------------
# System prompt for verification
# ---------------------------------------------------------------------------

VERIFIER_SYSTEM_PROMPT = """You are a step verifier for Jarvix's advanced agent system.
Your job is to evaluate whether a task step has been successfully completed
by examining the step definition, its success criteria, and the execution result.

Evaluation guidelines:
1. Check EACH success criterion independently
2. Be strict but fair - the step must clearly meet its stated criteria
3. Consider the tool's output (success/failure), output text, and any data returned
4. If the tool failed (error), the step generally fails unless criteria explicitly allow it
5. For "output_contains" checks, verify the expected text is in the tool output
6. For "tool_result_ok" checks, verify the tool returned success (ok=True)
7. Provide clear reasoning for each criterion and the overall decision

Output must match the provided JSON schema exactly."""


# ---------------------------------------------------------------------------
# Verifier class
# ---------------------------------------------------------------------------


class Verifier:
    """Verifies step completion against success criteria."""

    def __init__(self, ai_engine: Optional[AIEngine] = None):
        self._ai_engine = ai_engine

    def set_ai_engine(self, engine: AIEngine) -> None:
        """Set the AI engine to use for verification."""
        self._ai_engine = engine

    async def verify_step(
        self,
        step: TaskStep,
        tool_result: ToolResult,
        *,
        plan: Optional[Plan] = None,
        ctx: Optional[ExecContext] = None,
    ) -> Dict[str, Any]:
        """Verify a step against its success criteria.

        Args:
            step: The step that was executed
            tool_result: The result from tool execution
            plan: Optional full plan for context
            ctx: Execution context for cancellation

        Returns:
            Dict with keys: passed (bool), reasoning (str), criteria_results (list),
                           suggested_action (str)

        Raises:
            RuntimeError: If no AI engine is configured or verification fails
        """
        if ctx:
            ctx.check_cancelled()

        if self._ai_engine is None:
            _LOG.error("No AI engine configured for verification")
            # Fallback: simple heuristic verification
            return self._heuristic_verify(step, tool_result)

        # Build messages for the AI
        messages = [
            {"role": "system", "content": VERIFIER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": self._build_verification_prompt(step, tool_result, plan),
            },
        ]

        try:
            if ctx:
                ctx.check_cancelled()

            _LOG.debug("Verifying step: %s", step.id)
            result = await self._ai_engine.structured_output(
                messages, VERIFICATION_SCHEMA, ctx=ctx
            )

            if ctx:
                ctx.check_cancelled()

            _LOG.debug("Verification result for %s: passed=%s", step.id, result.get("passed"))
            return result

        except Exception as e:
            _LOG.exception("Verification failed, using heuristic fallback")
            return self._heuristic_verify(step, tool_result)

    def _build_verification_prompt(
        self,
        step: TaskStep,
        tool_result: ToolResult,
        plan: Optional[Plan] = None,
    ) -> str:
        """Build the verification prompt for the AI."""
        parts = [
            f"Step ID: {step.id}",
            f"Step Description: {step.description}",
            f"Tool Used: {step.tool.name}",
            f"Tool Arguments: {step.tool.args}",
            "",
            "Execution Result:",
            f"  Success: {tool_result.ok}",
            f"  Output: {tool_result.output or '(none)'}",
            f"  Error: {tool_result.error or '(none)'}",
            f"  Data: {tool_result.data or '(none)'}",
            "",
            "Success Criteria:",
        ]

        if step.success_criteria:
            for i, criterion in enumerate(step.success_criteria):
                parts.append(f"  {i + 1}. {criterion.description}")
                parts.append(f"     Type: {criterion.check_type}")
                if criterion.expected:
                    parts.append(f"     Expected: {criterion.expected}")
        else:
            parts.append("  (no explicit criteria - use tool_result.ok)")

        if plan and plan.success_criteria:
            parts.append("")
            parts.append("Overall Plan Success Criteria:")
            for i, criterion in enumerate(plan.success_criteria):
                parts.append(f"  {i + 1}. {criterion.description}")

        return "\n".join(parts)

    def _heuristic_verify(
        self,
        step: TaskStep,
        tool_result: ToolResult,
    ) -> Dict[str, Any]:
        """Fallback heuristic verification when no AI is available."""
        criteria_results = []
        all_passed = True

        # Steps that are skipped or cancelled should pass verification
        if step.status in (StepStatus.SKIPPED, StepStatus.CANCELLED):
            return {
                "passed": True,
                "reasoning": f"Step was {step.status.value}; skipping verification",
                "criteria_results": [],
                "suggested_action": "continue",
            }

        # If no explicit criteria, just check tool_result.ok
        if not step.success_criteria:
            passed = tool_result.ok
            criteria_results.append(
                {
                    "criterion": "tool_result_ok (implicit)",
                    "passed": passed,
                    "reasoning": "No explicit criteria; step passes if tool succeeded"
                    if passed
                    else "Tool returned error",
                }
            )
            all_passed = passed
        else:
            for criterion in step.success_criteria:
                if criterion.check_type == "tool_result_ok":
                    passed = tool_result.ok
                    reasoning = "Tool executed successfully" if passed else f"Tool failed: {tool_result.error}"
                elif criterion.check_type == "output_contains":
                    expected = criterion.expected or ""
                    passed = expected.lower() in (tool_result.output or "").lower()
                    reasoning = (
                        f"Expected text '{expected}' found in output"
                        if passed
                        else f"Expected text '{expected}' NOT found in output"
                    )
                elif criterion.check_type == "custom":
                    # Can't evaluate custom without AI - default to tool_result.ok
                    passed = tool_result.ok
                    reasoning = "Custom check requires AI verification; defaulting to tool result"
                else:
                    passed = tool_result.ok
                    reasoning = f"Unknown check type '{criterion.check_type}'; defaulting to tool result"

                criteria_results.append(
                    {
                        "criterion": criterion.description,
                        "passed": passed,
                        "reasoning": reasoning,
                    }
                )
                if not passed:
                    all_passed = False

        suggested_action = "continue" if all_passed else "retry"

        return {
            "passed": all_passed,
            "reasoning": "Heuristic verification (no AI engine available)"
            + (" - all criteria passed" if all_passed else " - some criteria failed"),
            "criteria_results": criteria_results,
            "suggested_action": suggested_action,
        }

    async def verify_plan(
        self,
        plan: Plan,
        step_results: Dict[str, ToolResult],
        *,
        ctx: Optional[ExecContext] = None,
    ) -> Dict[str, Any]:
        """Verify the overall plan completion.

        Args:
            plan: The plan that was executed
            step_results: Mapping of step_id -> ToolResult
            ctx: Execution context for cancellation

        Returns:
            Dict with overall verification result
        """
        if ctx:
            ctx.check_cancelled()

        if self._ai_engine is None:
            # Heuristic: all steps must have results and passed
            plan_step_ids = {step.id for step in plan.steps}
            result_step_ids = set(step_results.keys())
            missing = plan_step_ids - result_step_ids
            if missing:
                return {
                    "passed": False,
                    "reasoning": f"Heuristic: {len(missing)} step(s) have no results: {sorted(missing)}",
                    "criteria_results": [],
                    "suggested_action": "escalate",
                }
            all_passed = all(r.ok for r in step_results.values())
            return {
                "passed": all_passed,
                "reasoning": "Heuristic: all steps succeeded"
                if all_passed
                else "Heuristic: some steps failed",
                "criteria_results": [],
                "suggested_action": "continue" if all_passed else "escalate",
            }

        # Build plan-level verification prompt
        messages = [
            {"role": "system", "content": VERIFIER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": self._build_plan_verification_prompt(plan, step_results),
            },
        ]

        try:
            if ctx:
                ctx.check_cancelled()

            result = await self._ai_engine.structured_output(
                messages, VERIFICATION_SCHEMA, ctx=ctx
            )
            return result

        except Exception as e:
            _LOG.exception("Plan verification failed")
            all_passed = all(r.ok for r in step_results.values())
            return {
                "passed": all_passed,
                "reasoning": f"Plan verification failed: {e}",
                "criteria_results": [],
                "suggested_action": "continue" if all_passed else "escalate",
            }

    def _build_plan_verification_prompt(
        self,
        plan: Plan,
        step_results: Dict[str, ToolResult],
    ) -> str:
        """Build the plan verification prompt."""
        parts = [
            f"Plan Goal: {plan.goal}",
            f"Steps: {len(plan.steps)}",
            "",
            "Step Results:",
        ]

        for step in plan.steps:
            result = step_results.get(step.id)
            if result:
                parts.append(
                    f"  {step.id}: {'PASS' if result.ok else 'FAIL'} - {step.description}"
                )
                if not result.ok and result.error:
                    parts.append(f"    Error: {result.error}")
            else:
                parts.append(f"  {step.id}: NOT EXECUTED - {step.description}")

        if plan.success_criteria:
            parts.append("")
            parts.append("Overall Success Criteria:")
            for i, criterion in enumerate(plan.success_criteria):
                parts.append(f"  {i + 1}. {criterion.description}")

        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


async def verify_step(
    step: TaskStep,
    tool_result: ToolResult,
    ai_engine: AIEngine,
    *,
    plan: Optional[Plan] = None,
    ctx: Optional[ExecContext] = None,
) -> Dict[str, Any]:
    """Convenience function to verify a step."""
    verifier = Verifier(ai_engine)
    return await verifier.verify_step(step, tool_result, plan=plan, ctx=ctx)