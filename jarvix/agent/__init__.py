"""Advanced Agent subsystem (Phase 9) for Jarvix.

This package provides multi-step task planning, execution, verification,
retry, recovery, and background task management.

Exports:
- planner: Multi-step task planning via AIEngine.structured_output()
- verifier: Step verification against success criteria
- retry: Retry logic with exponential backoff and strategy selection
- recovery: Recovery strategies for failed steps
- background: Background task execution with progress/cancellation
- task: Data models (Task, TaskStep, Plan, TaskResult, etc.)
- task_manager: Task lifecycle management
- ui_panel: Agent settings panel (auto-registers)
- register_agent_tools(): Register all agent tools with ToolRegistry
"""

from __future__ import annotations

from jarvix.agent import (
    background,
    planner,
    recovery,
    retry,
    task,
    task_manager,
    ui_panel,
    verifier,
)

# Import key classes for convenience
from jarvix.agent.background import BackgroundTaskManager, ProgressReporter, get_background_manager
from jarvix.agent.planner import Planner, create_plan
from jarvix.agent.recovery import RecoveryManager, RecoveryAction, RecoveryResult, recover_from_failure
from jarvix.agent.retry import RetryManager, RetryConfig, execute_with_retry, RetryDecision
from jarvix.agent.task import (
    Plan,
    Task,
    TaskResult,
    TaskStep,
    TaskStatus,
    StepStatus,
    RetryStrategy,
    SuccessCriterion,
    ToolAssignment,
)
from jarvix.agent.task_manager import TaskManager, get_task_manager, create_task_manager
from jarvix.agent.verifier import Verifier, verify_step

# Auto-register UI panel on import (via ui_panel module)
# The ui_panel module auto-registers its SettingsTab when imported


def register_agent_tools(registry) -> None:
    """Register all agent tools with the ToolRegistry.

    Args:
        registry: ToolRegistry instance
    """
    from jarvix.agent.tools import (
        AgentPlanTool,
        AgentExecuteTool,
        AgentTaskCreateTool,
        AgentTaskStatusTool,
        AgentTaskCancelTool,
        AgentTaskListTool,
    )

    for cls in (
        AgentPlanTool,
        AgentExecuteTool,
        AgentTaskCreateTool,
        AgentTaskStatusTool,
        AgentTaskCancelTool,
        AgentTaskListTool,
    ):
        registry.register(cls.name, cls())

    from jarvix.core.logger import get_logger
    _LOG = get_logger("jarvix.agent")
    _LOG.info("Registered 6 agent tools")


__all__ = [
    # Submodules
    "background",
    "planner",
    "recovery",
    "retry",
    "task",
    "task_manager",
    "ui_panel",
    "verifier",
    # Key classes
    "BackgroundTaskManager",
    "ProgressReporter",
    "get_background_manager",
    "Planner",
    "create_plan",
    "RecoveryManager",
    "RecoveryAction",
    "RecoveryResult",
    "recover_from_failure",
    "RetryManager",
    "RetryConfig",
    "execute_with_retry",
    "RetryDecision",
    "Plan",
    "Task",
    "TaskResult",
    "TaskStep",
    "TaskStatus",
    "StepStatus",
    "RetryStrategy",
    "SuccessCriterion",
    "ToolAssignment",
    "TaskManager",
    "get_task_manager",
    "create_task_manager",
    "Verifier",
    "verify_step",
    # Registration
    "register_agent_tools",
]