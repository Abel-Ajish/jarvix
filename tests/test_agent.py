"""Tests for the agent subsystem."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jarvix.core.events import EventBus
from jarvix.core.execution import ExecContext
from jarvix.core.permissions import PermissionManager
from jarvix.core.tool_registry import ToolRegistry, ToolResult
from jarvix.agent import register_agent_tools
from jarvix.agent.planner import Planner, create_plan, Plan, TaskStep
from jarvix.agent.verifier import Verifier, verify_step
from jarvix.agent.retry import RetryManager, RetryConfig, execute_with_retry, RetryDecision
from jarvix.agent.recovery import RecoveryManager, RecoveryAction, RecoveryResult, recover_from_failure
from jarvix.agent.task import Task, TaskStatus, TaskResult, StepStatus
from jarvix.agent.task_manager import TaskManager, get_task_manager, create_task_manager
from jarvix.agent.background import BackgroundTaskManager, ProgressReporter, get_background_manager


@pytest.fixture
def mock_ai_engine() -> MagicMock:
    """Create a mocked AI engine."""
    engine = MagicMock()
    engine.structured_output = AsyncMock()
    engine.chat = AsyncMock()
    return engine


@pytest.fixture
def task_manager() -> TaskManager:
    """Create a task manager."""
    event_bus = EventBus()
    tool_registry = ToolRegistry(event_bus, PermissionManager())
    manager = TaskManager(
        tool_registry=tool_registry,
        event_bus=event_bus,
        ai_engine=MagicMock(),
    )
    yield manager


class TestPlanner:
    """Test the planner."""

    @pytest.mark.asyncio
    async def test_create_plan(self, mock_ai_engine: MagicMock) -> None:
        """Test creating a plan from a goal."""
        mock_ai_engine.structured_output = AsyncMock(return_value={
            "steps": [
                {"tool": "open_application", "args": {"app_name": "notepad"}, "description": "Open Notepad"},
                {"tool": "keyboard_type", "args": {"text": "Hello World"}, "description": "Type text"},
            ],
            "estimated_duration": 10,
        })

        plan = await create_plan(mock_ai_engine, "Open notepad and type hello world")

        assert isinstance(plan, Plan)
        assert len(plan.steps) == 2
        assert plan.steps[0].tool.name == "open_application"
        assert plan.steps[1].tool.name == "keyboard_type"

    @pytest.mark.asyncio
    async def test_planner_class(self, mock_ai_engine: MagicMock) -> None:
        """Test Planner class."""
        planner = Planner(mock_ai_engine)

        mock_ai_engine.structured_output = AsyncMock(return_value={
            "steps": [
                {"tool": "create_folder", "args": {"path": "Test"}, "description": "Create folder"},
            ],
            "estimated_duration": 5,
        })

        plan = await planner.create_plan("Create a test folder")

        assert len(plan.steps) == 1
        assert plan.steps[0].tool.name == "create_folder"


class TestVerifier:
    """Test the verifier."""

    @pytest.mark.asyncio
    async def test_verify_step_success(self, mock_ai_engine: MagicMock) -> None:
        """Test verifying a successful step."""
        mock_ai_engine.chat = AsyncMock(return_value=MagicMock(
            content='{"success": true, "reason": "Step completed"}'
        ))

        from jarvix.agent.task import ToolAssignment
        step = TaskStep(
            tool=ToolAssignment(name="open_application", args={"app_name": "notepad"}),
            description="Open Notepad",
        )
        result = ToolResult.success("Opened notepad")

        success = await verify_step(mock_ai_engine, step, result)

        assert success is True

    @pytest.mark.asyncio
    async def test_verify_step_failure(self, mock_ai_engine: MagicMock) -> None:
        """Test verifying a failed step."""
        mock_ai_engine.chat = AsyncMock(return_value=MagicMock(
            content='{"success": false, "reason": "Application not found"}'
        ))

        from jarvix.agent.task import ToolAssignment
        step = TaskStep(
            tool=ToolAssignment(name="open_application", args={"app_name": "nonexistent"}),
            description="Open app",
        )
        result = ToolResult.failure("Application not found")

        success = await verify_step(mock_ai_engine, step, result)

        assert success is False

    @pytest.mark.asyncio
    async def test_verifier_class(self, mock_ai_engine: MagicMock) -> None:
        """Test Verifier class."""
        verifier = Verifier(mock_ai_engine)

        mock_ai_engine.chat = AsyncMock(return_value=MagicMock(
            content='{"success": true, "reason": "Done"}'
        ))

        from jarvix.agent.task import ToolAssignment
        step = TaskStep(tool=ToolAssignment(name="test"), description="Test")
        result = ToolResult.success("Done")

        success = await verifier.verify(step, result)

        assert success is True


class TestRetryManager:
    """Test the retry manager."""

    @pytest.mark.asyncio
    async def test_execute_with_retry_success(self) -> None:
        """Test retry on success first try."""
        config = RetryConfig(max_attempts=3, base_delay=0.01)
        manager = RetryManager(config)

        call_count = 0

        async def operation():
            nonlocal call_count
            call_count += 1
            return ToolResult.success("Success")

        from jarvix.agent.task import ToolAssignment, TaskStep
        step = TaskStep(tool=ToolAssignment(name="test"), description="Test")
        result = await manager.execute_with_retry(step, operation)

        assert result[0].ok
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_execute_with_retry_eventual_success(self) -> None:
        """Test retry eventually succeeds."""
        config = RetryConfig(max_attempts=3, base_delay=0.01)
        manager = RetryManager(config)

        call_count = 0

        async def operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return ToolResult.failure("Temporary failure")
            return ToolResult.success("Success")

        from jarvix.agent.task import ToolAssignment, TaskStep
        step = TaskStep(tool=ToolAssignment(name="test"), description="Test")
        result = await manager.execute_with_retry(step, operation)

        assert result[0].ok
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_execute_with_retry_max_attempts(self) -> None:
        """Test retry exhausts attempts."""
        config = RetryConfig(max_attempts=2, base_delay=0.01)
        manager = RetryManager(config)

        async def operation():
            return ToolResult.failure("Always fails")

        from jarvix.agent.task import ToolAssignment, TaskStep
        step = TaskStep(tool=ToolAssignment(name="test"), description="Test")
        result = await manager.execute_with_retry(step, operation)

        assert not result[0].ok
        assert "Always fails" in result[0].error

    @pytest.mark.asyncio
    async def test_retry_decision(self) -> None:
        """Test retry decision logic."""
        config = RetryConfig(max_attempts=3)
        manager = RetryManager(config)

        from jarvix.agent.task import ToolAssignment, TaskStep
        step = TaskStep(tool=ToolAssignment(name="test"), description="Test")

        # Should retry on failure
        action = manager.decide_retry(step, ToolResult.failure("Error"), attempt=0)
        assert action.decision == RetryDecision.RETRY_SAME

        # Should not retry on success
        action = manager.decide_retry(step, ToolResult.success("Done"), attempt=0)
        assert action.decision == RetryDecision.NO_RETRY


class TestRecoveryManager:
    """Test the recovery manager."""

    @pytest.mark.asyncio
    async def test_recover_from_failure(self, mock_ai_engine: MagicMock) -> None:
        """Test recovering from a failed step."""
        mock_ai_engine.structured_output = AsyncMock(return_value={
            "action": "retry",
            "reason": "Try again with different args",
            "modified_args": {"app_name": "notepad.exe"},
        })

        from jarvix.agent.task import ToolAssignment, TaskStep
        step = TaskStep(
            tool=ToolAssignment(name="open_application", args={"app_name": "notepad"}),
            description="Open Notepad",
        )
        result = ToolResult.failure("Not found")

        recovery = await recover_from_failure(mock_ai_engine, step, result)

        assert isinstance(recovery, RecoveryResult)
        assert recovery.action == RecoveryAction.RETRY
        assert recovery.modified_args == {"app_name": "notepad.exe"}

    @pytest.mark.asyncio
    async def test_recovery_manager_class(self, mock_ai_engine: MagicMock) -> None:
        """Test RecoveryManager class."""
        manager = RecoveryManager()

        mock_ai_engine.structured_output = AsyncMock(return_value={
            "action": "skip",
            "reason": "Step not critical",
            "modified_args": None,
        })

        from jarvix.agent.task import ToolAssignment, TaskStep
        step = TaskStep(tool=ToolAssignment(name="optional_tool"), description="Optional")
        result = ToolResult.failure("Failed")

        recovery = await manager.recover(step, result)

        assert recovery.action == RecoveryAction.SKIP


class TestTaskManager:
    """Test the task manager."""

    def test_create_task(self, task_manager: TaskManager) -> None:
        """Test creating a task."""
        task = task_manager.create_task("test-goal", "Test goal")

        assert isinstance(task, Task)
        assert task.name == "test-goal"
        assert task.status == TaskStatus.PENDING

    def test_get_task(self, task_manager: TaskManager) -> None:
        """Test getting a task by ID."""
        task = task_manager.create_task("test-goal", "Test goal")

        retrieved = task_manager.get_task(task.id)

        assert retrieved is not None
        assert retrieved.id == task.id

    def test_list_tasks(self, task_manager: TaskManager) -> None:
        """Test listing tasks."""
        task_manager.create_task("task-1", "Task 1")
        task_manager.create_task("task-2", "Task 2")

        tasks = task_manager.list_tasks()

        assert len(tasks) == 2

    def test_cancel_task(self, task_manager: TaskManager) -> None:
        """Test cancelling a task."""
        task = task_manager.create_task("test-goal", "Test goal")

        task_manager.cancel_task(task.id)

        assert task.status == TaskStatus.CANCELLED

    def test_update_task_status(self, task_manager: TaskManager) -> None:
        """Test updating task status."""
        task = task_manager.create_task("test-goal", "Test goal")

        task_manager.update_task_status(task.id, TaskStatus.RUNNING)

        assert task.status == TaskStatus.RUNNING


class TestBackgroundTaskManager:
    """Test the background task manager."""

    @pytest.mark.asyncio
    async def test_submit_task(self) -> None:
        """Test submitting a background task."""
        from jarvix.agent.background import BackgroundTaskManager
        manager = BackgroundTaskManager()

        async def sample_task(task, ctx):
            return TaskResult(
                task_id=task.id,
                plan_id="",
                status=TaskStatus.COMPLETED,
                started_at=datetime.now(),
            )

        task = Task(name="test-task", goal="Test goal")
        task_id = manager.submit(task, sample_task)

        assert task_id is not None

        # Wait for completion
        result = await manager.wait_for(task_id, timeout=1.0)

        assert result is not None
        assert result.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_cancel_background_task(self) -> None:
        """Test cancelling a background task."""
        from jarvix.agent.background import BackgroundTaskManager
        manager = BackgroundTaskManager()

        async def long_task(task, ctx):
            await asyncio.sleep(10)
            return TaskResult(
                task_id=task.id,
                plan_id="",
                status=TaskStatus.COMPLETED,
                started_at=datetime.now(),
            )

        task = Task(name="test-task", goal="Test goal")
        task_id = manager.submit(task, long_task)

        cancelled = manager.cancel(task_id)

        assert cancelled is True

    @pytest.mark.asyncio
    async def test_progress_reporting(self) -> None:
        """Test progress reporting."""
        from jarvix.agent.background import BackgroundTaskManager
        manager = BackgroundTaskManager()

        progress_updates = []

        async def task_with_progress(task, ctx):
            progress_updates.append((0.25, "Starting"))
            await asyncio.sleep(0.01)
            progress_updates.append((0.75, "Processing"))
            return TaskResult(
                task_id=task.id,
                plan_id="",
                status=TaskStatus.COMPLETED,
                started_at=datetime.now(),
            )

        task = Task(name="test-task", goal="Test goal")
        task_id = manager.submit(task, task_with_progress)

        # Collect progress via callback
        while True:
            bg_task = manager._tasks.get(task_id)
            if bg_task and bg_task.task.status == TaskStatus.COMPLETED:
                break
            await asyncio.sleep(0.01)

        assert len(progress_updates) >= 2
        assert progress_updates[0] == (0.25, "Starting")
        assert progress_updates[-1] == (0.75, "Processing")


class TestAgentTools:
    """Test agent tools registration."""

    def test_register_agent_tools(self) -> None:
        """Test all agent tools are registered."""
        event_bus = EventBus()
        permission_manager = PermissionManager()
        registry = ToolRegistry(event_bus, permission_manager)

        register_agent_tools(registry)

        expected_tools = [
            "agent_plan",
            "agent_execute",
            "agent_task_create",
            "agent_task_status",
            "agent_task_cancel",
            "agent_task_list",
        ]

        for tool_name in expected_tools:
            tool = registry.get(tool_name)
            assert tool is not None, f"Tool {tool_name} not registered"
            meta = registry.get_meta(tool_name)
            assert meta is not None
            assert meta.name == tool_name

    def test_agent_plan_tool_schema(self) -> None:
        """Test agent_plan tool schema."""
        event_bus = EventBus()
        permission_manager = PermissionManager()
        registry = ToolRegistry(event_bus, permission_manager)
        register_agent_tools(registry)

        tool = registry.get("agent_plan")
        schema = tool.schema()

        assert "goal" in schema["properties"]
        assert schema["required"] == ["goal"]

    def test_agent_task_create_tool_schema(self) -> None:
        """Test agent_task_create tool schema."""
        event_bus = EventBus()
        permission_manager = PermissionManager()
        registry = ToolRegistry(event_bus, permission_manager)
        register_agent_tools(registry)

        tool = registry.get("agent_task_create")
        schema = tool.schema()

        assert "goal" in schema["properties"]
        assert schema["required"] == ["goal"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])