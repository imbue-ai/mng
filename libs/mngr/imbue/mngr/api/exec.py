from collections.abc import Callable
from collections.abc import Sequence
from pathlib import Path

from loguru import logger
from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.logging import log_call
from imbue.imbue_common.logging import log_span
from imbue.imbue_common.mutable_model import MutableModel
from imbue.mngr.api.find import find_agents_by_identifiers_or_state
from imbue.mngr.api.find import find_and_maybe_start_agent_by_name_or_id
from imbue.mngr.api.find import group_agents_by_host
from imbue.mngr.api.list import load_all_agents_grouped_by_host
from imbue.mngr.api.providers import get_provider_instance
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import MngrError
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.primitives import ErrorBehavior
from imbue.mngr.primitives import HostId


class ExecResult(FrozenModel):
    """Result of executing a command on an agent's host."""

    agent_name: str = Field(description="Name of the agent the command was executed on")
    stdout: str = Field(description="Standard output from the command")
    stderr: str = Field(description="Standard error from the command")
    success: bool = Field(description="True if the command succeeded")


class MultiExecResult(MutableModel):
    """Result of executing a command on multiple agents."""

    successful_results: list[ExecResult] = Field(
        default_factory=list, description="Results from agents where the command was executed"
    )
    failed_agents: list[tuple[str, str]] = Field(
        default_factory=list,
        description="List of (agent_name, error_message) tuples for agents that could not be reached",
    )


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
        agent_str, agents_by_host, mngr_ctx, "exec", is_start_desired=is_start_desired
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


@log_call
def exec_command_on_agents(
    mngr_ctx: MngrContext,
    agent_identifiers: Sequence[str],
    command: str,
    is_all: bool,
    user: str | None = None,
    cwd: str | None = None,
    timeout_seconds: float | None = None,
    is_start_desired: bool = True,
    error_behavior: ErrorBehavior = ErrorBehavior.CONTINUE,
    # Optional callback invoked on each successful exec
    on_success: Callable[[ExecResult], None] | None = None,
    # Optional callback invoked on each failure
    on_error: Callable[[str, str], None] | None = None,
) -> MultiExecResult:
    """Execute a shell command on the hosts where multiple agents run.

    Resolves each agent by name or ID, optionally starts them if stopped,
    then executes the command on each host (defaulting to the agent's work_dir).
    """
    result = MultiExecResult()

    # Find all matching agents
    matches = find_agents_by_identifiers_or_state(
        agent_identifiers=agent_identifiers,
        filter_all=is_all,
        target_state=None,
        mngr_ctx=mngr_ctx,
    )

    if not matches:
        return result

    # Group by host for efficient iteration
    agents_by_host = group_agents_by_host(matches)

    for host_key, agent_list in agents_by_host.items():
        host_id_str, _ = host_key.split(":", 1)
        provider_name = agent_list[0].provider_name

        # Get the host
        try:
            provider = get_provider_instance(provider_name, mngr_ctx)
            host_interface = provider.get_host(HostId(host_id_str))
        except MngrError as e:
            for match in agent_list:
                error_msg = f"Failed to get host for agent {match.agent_name}: {e}"
                result.failed_agents.append((str(match.agent_name), error_msg))
                if on_error is not None:
                    on_error(str(match.agent_name), error_msg)
                if error_behavior == ErrorBehavior.ABORT:
                    return result
            continue

        # Ensure host is online
        if not isinstance(host_interface, OnlineHostInterface):
            if is_start_desired:
                try:
                    with log_span("Starting host {}", host_id_str):
                        host_interface = provider.start_host(host_interface)
                except MngrError as e:
                    for match in agent_list:
                        error_msg = f"Failed to start host for agent {match.agent_name}: {e}"
                        result.failed_agents.append((str(match.agent_name), error_msg))
                        if on_error is not None:
                            on_error(str(match.agent_name), error_msg)
                        if error_behavior == ErrorBehavior.ABORT:
                            return result
                    continue
            else:
                for match in agent_list:
                    error_msg = f"Host '{host_id_str}' is offline and automatic starting is disabled"
                    result.failed_agents.append((str(match.agent_name), error_msg))
                    if on_error is not None:
                        on_error(str(match.agent_name), error_msg)
                    if error_behavior == ErrorBehavior.ABORT:
                        return result
                continue

        online_host: OnlineHostInterface = host_interface

        # Execute command on each agent on this host
        for match in agent_list:
            try:
                # Find the agent on the host to get its work_dir
                agent_work_dir: Path | None = None
                for agent in online_host.get_agents():
                    if agent.id == match.agent_id:
                        agent_work_dir = agent.work_dir
                        break

                effective_cwd = Path(cwd) if cwd is not None else agent_work_dir

                with log_span("Executing command on agent {}", match.agent_name):
                    cmd_result = online_host.execute_command(
                        command,
                        user=user,
                        cwd=effective_cwd,
                        timeout_seconds=timeout_seconds,
                    )

                exec_result = ExecResult(
                    agent_name=str(match.agent_name),
                    stdout=cmd_result.stdout,
                    stderr=cmd_result.stderr,
                    success=cmd_result.success,
                )
                result.successful_results.append(exec_result)
                if on_success is not None:
                    on_success(exec_result)

            except MngrError as e:
                error_msg = f"Failed to execute command on agent {match.agent_name}: {e}"
                result.failed_agents.append((str(match.agent_name), error_msg))
                if on_error is not None:
                    on_error(str(match.agent_name), error_msg)
                if error_behavior == ErrorBehavior.ABORT:
                    return result

    return result
