"""Shared test fixtures for API tests."""

import shlex
import subprocess
from pathlib import Path
from typing import Any

from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.mutable_model import MutableModel
from imbue.mngr.api.sync import LocalGitContext
from imbue.mngr.interfaces.data_types import CommandResult


class FakeAgent(FrozenModel):
    """Minimal test double for AgentInterface -- only implements work_dir."""

    work_dir: Path = Field(description="Working directory for this agent")


class FakeHost(MutableModel):
    """Minimal test double for OnlineHostInterface that executes commands locally."""

    is_local: bool = Field(default=True, description="Whether this is a local host")

    def execute_command(
        self,
        command: str,
        cwd: Path | None = None,
    ) -> CommandResult:
        """Execute a command locally and return the result."""
        result = subprocess.run(
            shlex.split(command),
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        return CommandResult(
            stdout=result.stdout,
            stderr=result.stderr,
            success=result.returncode == 0,
        )


class SyncTestContext(FrozenModel):
    """Shared test context for sync integration tests (pull, push, pair)."""

    agent_dir: Path = Field(description="Agent working directory")
    local_dir: Path = Field(description="Local directory")
    agent: Any = Field(description="Test agent (FakeAgent)")
    host: Any = Field(description="Test host (FakeHost)")


def has_uncommitted_changes(path: Path) -> bool:
    """Check for uncommitted changes using LocalGitContext."""
    return LocalGitContext().has_uncommitted_changes(path)
