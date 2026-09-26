"""Multi-step task planner using AIEngine.structured_output().

Takes a goal and returns a structured plan with steps, dependencies,
tool assignments, and success criteria.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from jarvix.agent.task import (
    Plan,
    SuccessCriterion,
    TaskStep,
    ToolAssignment,
)
from jarvix.core.execution import ExecContext
from jarvix.core.logger import get_logger
from jarvix.engine.ai_engine import AIEngine

_LOG = get_logger("jarvix.agent.planner")


# ---------------------------------------------------------------------------
# JSON Schema for Plan output
# ---------------------------------------------------------------------------

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "goal": {"type": "string", "description": "High-level goal of this plan"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "tool": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "args": {"type": "object"},
                            "fallback_tools": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["name"],
                    },
                    "dependencies": {"type": "array", "items": {"type": "string"}},
                    "success_criteria": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "description": {"type": "string"},
                                "check_type": {"type": "string"},
                                "expected": {"type": "string"},
                                "tool_name": {"type": "string"},
                            },
                            "required": ["description", "check_type"],
                        },
                    },
                    "max_retries": {"type": "integer", "default": 3},
                    "retry_delay": {"type": "number", "default": 1.0},
                    "retry_backoff": {"type": "number", "default": 2.0},
                    "timeout": {"type": "number"},
                },
                "required": ["description", "tool"],
            },
        },
        "success_criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "check_type": {"type": "string"},
                    "expected": {"type": "string"},
                    "tool_name": {"type": "string"},
                },
                "required": ["description", "check_type"],
            },
        },
        "max_parallel_steps": {"type": "integer", "default": 1},
    },
    "required": ["goal", "steps"],
}


# ---------------------------------------------------------------------------
# System prompt for planning
# ---------------------------------------------------------------------------

PLANNER_SYSTEM_PROMPT = """You are a task planner for Jarvix, a Windows desktop assistant.
Your job is to break down a user's goal into a structured, executable plan.

Available tools (you can only use these tool names):
- File operations: create_file, read_file, write_file, copy_file, move_file, rename_file, delete_file, create_folder, delete_folder, search_files
- System: open_application
- Web: web_search, read_page, browser_navigate, browser_click, browser_type, browser_scroll, browser_screenshot, browser_download, browser_upload
- Vision: screen_capture, analyze_screen, find_ui_element, read_screen_text, vision_describe, list_monitors
- Memory: memory_remember, memory_search, memory_retrieve, memory_list, memory_update, memory_forget
- Agent: agent_plan, agent_execute, agent_task_create, agent_task_status, agent_task_cancel, agent_task_list
- Plugins: plugin_list, plugin_info, plugin_enable, plugin_disable, plugin_install, plugin_uninstall, plugin_update

Rules for planning:
1. Each step must use exactly ONE tool from the available list
2. Steps should be atomic and independently verifiable
3. Use dependencies to sequence steps that must happen in order
4. Provide success_criteria for each step so the verifier can judge completion
5. Include fallback_tools for steps that might fail (alternative approaches)
6. Set reasonable max_retries (default 3) and retry delays
7. The plan must be executable by the agent_execute tool
8. For complex goals, break into 3-10 steps maximum
9. Use tool arguments that are as specific as possible

Output must match the provided JSON schema exactly."""


# ---------------------------------------------------------------------------
# Planner class
# ---------------------------------------------------------------------------


class Planner:
    """Creates structured execution plans from natural language goals."""

    def __init__(self, ai_engine: Optional[AIEngine] = None):
        self._ai_engine = ai_engine

    def set_ai_engine(self, engine: AIEngine) -> None:
        """Set the AI engine to use for planning."""
        self._ai_engine = engine

    async def create_plan(
        self,
        goal: str,
        *,
        context: Optional[str] = None,
        max_steps: int = 10,
        allowed_tools: Optional[List[str]] = None,
        ctx: Optional[ExecContext] = None,
    ) -> Plan:
        """Create a multi-step plan for the given goal.

        Args:
            goal: Natural language description of what to achieve
            context: Optional additional context (previous results, constraints)
            max_steps: Maximum number of steps in the plan
            allowed_tools: Optional list of tool names to restrict to
            ctx: Execution context for cancellation

        Returns:
            A structured Plan object

        Raises:
            RuntimeError: If no AI engine is configured or planning fails
        """
        if ctx:
            ctx.check_cancelled()

        if self._ai_engine is None:
            _LOG.error("No AI engine configured for planning")
            raise RuntimeError(
                "No AI provider configured. Set up an online AI provider in settings."
            )

        # Build messages for the AI
        messages = [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
        ]

        if allowed_tools:
            tool_list = ", ".join(allowed_tools)
            messages.append(
                {
                    "role": "system",
                    "content": f"Only use these tools: {tool_list}",
                }
            )

        user_content = f"Goal: {goal}"
        if context:
            user_content += f"\n\nContext:\n{context}"
        user_content += f"\n\nCreate a plan with at most {max_steps} steps."

        messages.append({"role": "user", "content": user_content})

        try:
            if ctx:
                ctx.check_cancelled()

            _LOG.info("Requesting plan for goal: %s", goal[:100])
            result = await self._ai_engine.structured_output(messages, PLAN_SCHEMA, ctx=ctx)

            if ctx:
                ctx.check_cancelled()

            # Convert the raw dict to Plan object
            plan = self._parse_plan_result(result)
            _LOG.info("Created plan with %d steps for goal: %s", len(plan.steps), goal[:100])
            return plan

        except Exception as e:
            _LOG.exception("Failed to create plan")
            raise RuntimeError(f"Planning failed: {e}") from e

    def _parse_plan_result(self, result: Dict[str, Any]) -> Plan:
        """Parse the AI's structured output into a Plan object."""
        if not isinstance(result, dict):
            raise ValueError(f"Expected dict from AI, got {type(result).__name__}")

        steps_raw = result.get("steps")
        if steps_raw is not None and not isinstance(steps_raw, list):
            raise ValueError(f"Expected 'steps' to be a list, got {type(steps_raw).__name__}")
        steps = []

        for i, step_data in enumerate(steps_raw or []):
            if not isinstance(step_data, dict):
                _LOG.warning("Skipping non-dict step at index %d", i)
                continue

            # Ensure step has an ID
            if "id" not in step_data:
                step_data["id"] = f"step_{i + 1}"

            # Parse tool assignment
            tool_data = step_data.get("tool")
            if not isinstance(tool_data, dict):
                tool_data = {}
            tool = ToolAssignment(
                name=tool_data.get("name", ""),
                args=tool_data.get("args"),
                fallback_tools=tool_data.get("fallback_tools", []),
            )

            # Parse success criteria
            criteria = []
            for crit_data in step_data.get("success_criteria", []):
                criteria.append(
                    SuccessCriterion(
                        description=crit_data.get("description", ""),
                        check_type=crit_data.get("check_type", "tool_result_ok"),
                        expected=crit_data.get("expected"),
                        tool_name=crit_data.get("tool_name"),
                    )
                )

            step = TaskStep(
                id=step_data.get("id", f"step_{i + 1}"),
                description=step_data.get("description", ""),
                tool=tool,
                dependencies=step_data.get("dependencies", []),
                success_criteria=criteria,
                max_retries=step_data.get("max_retries", 3),
                retry_delay=step_data.get("retry_delay", 1.0),
                retry_backoff=step_data.get("retry_backoff", 2.0),
                timeout=step_data.get("timeout"),
            )
            steps.append(step)

        # Parse overall success criteria
        overall_criteria = []
        for crit_data in result.get("success_criteria", []):
            overall_criteria.append(
                SuccessCriterion(
                    description=crit_data.get("description", ""),
                    check_type=crit_data.get("check_type", "tool_result_ok"),
                    expected=crit_data.get("expected"),
                    tool_name=crit_data.get("tool_name"),
                )
            )

        return Plan(
            goal=result.get("goal", ""),
            steps=steps,
            success_criteria=overall_criteria,
            max_parallel_steps=result.get("max_parallel_steps", 1),
        )


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


async def create_plan(
    goal: str,
    ai_engine: AIEngine,
    *,
    context: Optional[str] = None,
    max_steps: int = 10,
    allowed_tools: Optional[List[str]] = None,
    ctx: Optional[ExecContext] = None,
) -> Plan:
    """Convenience function to create a plan."""
    planner = Planner(ai_engine)
    return await planner.create_plan(
        goal,
        context=context,
        max_steps=max_steps,
        allowed_tools=allowed_tools,
        ctx=ctx,
    )