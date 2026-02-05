"""Shared test fixtures for API tests."""

import subprocess
from pathlib import Path

from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.mutable_model import MutableModel
from imbue.mngr.interfaces.data_types import CommandResult


class FakeAgent(FrozenModel):
    """Minimal test double for AgentInterface.

    Only implements work_dir, which is all the sync functions actually use.
    """

    work_dir: Path = Field(description="Working directory for this agent")


class FakeHost(MutableModel):
    """Minimal test double for OnlineHostInterface.

    Implements execute_command and is_local. Executes commands locally via subprocess.
    Set is_local=False to simulate a remote host.
    """

    is_local: bool = Field(default=True, description="Whether this is a local host")

    def execute_command(
        self,
        command: str,
        cwd: Path | None = None,
    ) -> CommandResult:
        """Execute a shell command locally and return the result."""
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        return CommandResult(
            stdout=result.stdout,
            stderr=result.stderr,
            success=result.returncode == 0,
        )
