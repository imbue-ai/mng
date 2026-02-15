from pathlib import Path

from loguru import logger
from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.logging import log_call
from imbue.mngr.api.find import find_and_maybe_start_agent_by_name_or_id
from imbue.mngr.api.list import load_all_agents_grouped_by_host
from imbue.mngr.config.data_types import MngrContext


class ExecResult(FrozenModel):
    """Result of executing a command on an agent's host."""

    agent_name: str = Field(description="Name of the agent the command was executed on")
    stdout: str = Field(description="Standard output from the command")
    stderr: str = Field(description="Standard error from the command")
    success: bool = Field(description="True if the command succeeded")


@log_call
def exec_command_on_agent(
    mngr_ctx: MngrContext,
    agent_str: str,
    command: str,
    user: str | None = None,
    cwd: str | None = None,
    timeout_seconds: float | None = None,
    is_start_desired: bool = True,
) -> ExecResult:
    """Execute a shell command on the host where an agent runs.

    Resolves the agent by name or ID, optionally starts it if stopped,
    then executes the command on its host (defaulting to the agent's work_dir).
    """
    agents_by_host, _providers = load_all_agents_grouped_by_host(mngr_ctx)

    agent, host = find_and_maybe_start_agent_by_name_or_id(
        agent_str, agents_by_host, mngr_ctx, "exec", start_host_if_needed=is_start_desired
    )

    # Determine working directory: explicit --cwd, or agent's work_dir
    effective_cwd = Path(cwd) if cwd is not None else agent.work_dir

    logger.debug("Executing command on agent {}: {}", agent.name, command)
    result = host.execute_command(
        command,
        user=user,
        cwd=effective_cwd,
        timeout_seconds=timeout_seconds,
    )

    return ExecResult(
        agent_name=str(agent.name),
        stdout=result.stdout,
        stderr=result.stderr,
        success=result.success,
    )
