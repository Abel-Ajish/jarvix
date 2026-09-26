"""pytest fixtures for jarvix tests."""

import asyncio
import tempfile
from pathlib import Path
from typing import Any, Dict, Generator
from unittest.mock import MagicMock

import pytest

from jarvix.core.config import Settings
from jarvix.core.events import EventBus
from jarvix.core.execution import ExecContext
from jarvix.core.permissions import PermissionManager
from jarvix.core.secret_store import SecretStore
from jarvix.core.tool_registry import ToolRegistry, ToolResult


@pytest.fixture
def event_bus() -> EventBus:
    """Create a fresh EventBus for each test."""
    return EventBus()


@pytest.fixture
def permission_manager() -> PermissionManager:
    """Create a PermissionManager with default settings."""
    return PermissionManager()


@pytest.fixture
def temp_settings() -> Generator[Settings, None, None]:
    """Create a temporary Settings instance with a temp directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Settings()
        # Override the config directory to use temp
        import jarvix.core.config as config_module
        original_config_dir = config_module._CONFIG_DIR
        config_module._CONFIG_DIR = Path(tmpdir)
        # Re-create subsystem files
        for fname in config_module._SUBSYSTEM_FILES:
            (Path(tmpdir) / fname).touch()
        settings.reload()
        yield settings
        config_module._CONFIG_DIR = original_config_dir


@pytest.fixture
def tool_registry(event_bus: EventBus, permission_manager: PermissionManager) -> ToolRegistry:
    """Create a ToolRegistry with fresh event bus and permission manager."""
    return ToolRegistry(event_bus, permission_manager)


@pytest.fixture
def exec_context(permission_manager: PermissionManager) -> ExecContext:
    """Create an ExecContext for testing."""
    return ExecContext(
        conversation_id="test-conv",
        user_id="test-user",
        permission_manager=permission_manager,
    )


@pytest.fixture
def mock_secret_store() -> SecretStore:
    """Create a SecretStore with a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        import jarvix.core.secret_store as secret_module
        original_secrets_dir = secret_module._SECRETS_DIR
        original_secrets_file = secret_module._SECRETS_FILE
        original_salt_file = secret_module._SALT_FILE
        secret_module._SECRETS_DIR = Path(tmpdir)
        secret_module._SECRETS_FILE = Path(tmpdir) / "secrets.enc"
        secret_module._SALT_FILE = Path(tmpdir) / "salt.bin"
        store = SecretStore()
        yield store
        secret_module._SECRETS_DIR = original_secrets_dir
        secret_module._SECRETS_FILE = original_secrets_file
        secret_module._SALT_FILE = original_salt_file


@pytest.fixture
def sample_tool_result() -> ToolResult:
    """Create a sample ToolResult for testing."""
    return ToolResult.success("test output", data={"key": "value"})


@pytest.fixture
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()