"""Shared test fixtures for API tests."""

import shlex
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import Field

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.mutable_model import MutableModel
from imbue.mng.api.sync import LocalGitContext
from imbue.mng.interfaces.data_types import CommandResult
from imbue.mng.primitives import AgentName


class FakeAgent(FrozenModel):
    """Minimal test double for AgentInterface -- only implements work_dir and name."""

    work_dir: Path = Field(description="Working directory for this agent")
    name: AgentName = Field(default=AgentName("fake-agent"), description="Agent name")


class FakeHost(MutableModel):
    """Minimal test double for OnlineHostInterface that executes commands locally."""

    is_local: bool = Field(default=True, description="Whether this is a local host")

    def execute_command(
        self,
        command: str,
        user: str | None = None,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> CommandResult:
        """Execute a command locally and return the result.

        The user, env, and timeout_seconds parameters are accepted for interface
        compatibility but are not applied to the subprocess call.
        """
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


def has_uncommitted_changes(path: Path, cg: ConcurrencyGroup) -> bool:
    """Check for uncommitted changes using LocalGitContext."""
    return LocalGitContext(cg=cg).has_uncommitted_changes(path)
