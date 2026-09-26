"""Task data models for the Advanced Agent subsystem.

Defines Pydantic models for tasks, steps, plans, and results.
"""

from __future__ import annotations

import enum
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TaskStatus(str, enum.Enum):
    """Status of a task."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(str, enum.Enum):
    """Status of a task step."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


class RetryStrategy(str, enum.Enum):
    """Strategy for retrying a failed step."""

    RETRY_SAME = "retry_same"  # Retry the same step with same tool
    TRY_ALTERNATIVE = "try_alternative"  # Try a different tool
    SKIP = "skip"  # Skip this step and continue
    ESCALATE = "escalate"  # Escalate to human / stop execution


class RecoveryAction(str, enum.Enum):
    """Recovery action when a step fails."""

    ROLLBACK = "rollback"  # Rollback completed steps
    COMPENSATE = "compensate"  # Run compensating action
    ALTERNATIVE_PATH = "alternative_path"  # Try alternative execution path
    PARTIAL_COMPLETION = "partial_completion"  # Report partial completion and stop


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


class ToolAssignment(BaseModel):
    """Assignment of a tool to a step."""

    name: str = Field(..., description="Tool name to execute")
    args: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    fallback_tools: List[str] = Field(
        default_factory=list, description="Alternative tool names if primary fails"
    )


class SuccessCriterion(BaseModel):
    """Success criterion for a step or plan."""

    description: str = Field(..., description="Human-readable description of success")
    check_type: str = Field(
        ..., description="Type of check: 'output_contains', 'tool_result_ok', 'custom'"
    )
    expected: Optional[str] = Field(
        None, description="Expected output/result pattern for validation"
    )
    tool_name: Optional[str] = Field(
        None, description="Tool to use for custom verification"
    )


class TaskStep(BaseModel):
    """A single step in a task plan."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str = Field(..., description="What this step does")
    tool: ToolAssignment = Field(..., description="Tool to execute for this step")
    dependencies: List[str] = Field(
        default_factory=list, description="Step IDs that must complete first"
    )
    success_criteria: List[SuccessCriterion] = Field(
        default_factory=list, description="Criteria to verify step completion"
    )
    max_retries: int = Field(default=3, description="Maximum retry attempts")
    retry_delay: float = Field(default=1.0, description="Base delay between retries (seconds)")
    retry_backoff: float = Field(default=2.0, description="Exponential backoff multiplier")
    timeout: Optional[float] = Field(None, description="Step timeout in seconds")
    status: StepStatus = Field(default=StepStatus.PENDING)
    result: Optional[str] = None
    error: Optional[str] = None
    attempts: int = Field(default=0)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("tool", mode="before")
    @classmethod
    def _ensure_tool_assignment(cls, v):
        if isinstance(v, dict):
            return ToolAssignment(**v)
        return v


class Plan(BaseModel):
    """A multi-step execution plan."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    goal: str = Field(..., description="High-level goal of this plan")
    steps: List[TaskStep] = Field(..., description="Steps to execute")
    success_criteria: List[SuccessCriterion] = Field(
        default_factory=list, description="Overall plan success criteria"
    )
    created_at: datetime = Field(default_factory=datetime.now)
    max_parallel_steps: int = Field(default=1, description="Max steps to run in parallel")
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def get_step(self, step_id: str) -> Optional[TaskStep]:
        """Get a step by ID."""
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def get_ready_steps(self, completed_step_ids: set[str]) -> List[TaskStep]:
        """Get steps whose dependencies are all satisfied."""
        ready = []
        for step in self.steps:
            if step.status == StepStatus.PENDING:
                if all(dep in completed_step_ids for dep in step.dependencies):
                    ready.append(step)
        return ready


class TaskResult(BaseModel):
    """Result of a task execution."""

    task_id: str
    plan_id: str
    status: TaskStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    step_results: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    partial_results: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "task_id": self.task_id,
            "plan_id": self.plan_id,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "step_results": self.step_results,
            "error": self.error,
            "partial_results": self.partial_results,
        }


class Task(BaseModel):
    """A task with its plan and execution state."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = Field(..., description="Human-readable task name")
    description: str = Field(default="", description="Task description")
    plan: Optional[Plan] = None
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[TaskResult] = None
    progress_callback: Optional[str] = None  # Name of callback for progress updates
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metadata": self.metadata,
        }
        if self.plan:
            data["plan"] = self.plan.model_dump()
        if self.result:
            data["result"] = self.result.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        """Create Task from dictionary."""
        if "plan" in data and data["plan"]:
            data["plan"] = Plan(**data["plan"])
        if "result" in data and data["result"]:
            data["result"] = TaskResult(**data["result"])
        for dt_field in ["created_at", "started_at", "completed_at"]:
            if data.get(dt_field) and isinstance(data[dt_field], str):
                data[dt_field] = datetime.fromisoformat(data[dt_field])
        return cls(**data)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def plan_to_json(plan: Plan) -> str:
    """Serialize a plan to JSON string."""
    return plan.model_dump_json(indent=2)


def plan_from_json(json_str: str) -> Plan:
    """Deserialize a plan from JSON string."""
    return Plan.model_validate_json(json_str)


def task_to_json(task: Task) -> str:
    """Serialize a task to JSON string."""
    return json.dumps(task.to_dict(), indent=2)


def task_from_json(json_str: str) -> Task:
    """Deserialize a task from JSON string."""
    return Task.from_dict(json.loads(json_str))