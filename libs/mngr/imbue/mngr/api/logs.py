from collections.abc import Callable
from typing import Final

from loguru import logger
from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.logging import log_span
from imbue.imbue_common.mutable_model import MutableModel
from imbue.imbue_common.pure import pure
from imbue.mngr.api.list import load_all_agents_grouped_by_host
from imbue.mngr.api.providers import get_provider_instance
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import MngrError
from imbue.mngr.errors import UserInputError
from imbue.mngr.interfaces.data_types import VolumeFileType
from imbue.mngr.interfaces.volume import Volume
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentReference
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import HostReference
from imbue.mngr.utils.polling import poll_until

FOLLOW_POLL_INTERVAL_SECONDS: Final[float] = 1.0


class LogsTarget(FrozenModel):
    """Resolved target for the logs command."""

    volume: Volume = Field(description="Volume scoped to the target's logs directory")
    display_name: str = Field(description="Human-readable name for the target (agent or host)")

    model_config = {"arbitrary_types_allowed": True}


class LogFileEntry(FrozenModel):
    """Information about an available log file."""

    name: str = Field(description="Log file name")
    size: int = Field(description="File size in bytes")


@pure
def _find_agent_in_hosts(
    identifier: str,
    agents_by_host: dict[HostReference, list[AgentReference]],
) -> tuple[HostReference, AgentReference] | None:
    """Find an agent by name or ID across all hosts.

    Returns (host_ref, agent_ref) or None if not found.
    """
    # Try as AgentId first
    try:
        agent_id = AgentId(identifier)
        for host_ref, agent_refs in agents_by_host.items():
            for agent_ref in agent_refs:
                if agent_ref.agent_id == agent_id:
                    return host_ref, agent_ref
    except ValueError:
        pass

    # Try as AgentName
    agent_name = AgentName(identifier)
    matches: list[tuple[HostReference, AgentReference]] = []
    for host_ref, agent_refs in agents_by_host.items():
        for agent_ref in agent_refs:
            if agent_ref.agent_name == agent_name:
                matches.append((host_ref, agent_ref))
    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        raise UserInputError(f"Multiple agents found with name '{identifier}'. Please use the agent ID instead.")
    else:
        return None


@pure
def _find_host_in_hosts(
    identifier: str,
    agents_by_host: dict[HostReference, list[AgentReference]],
) -> HostReference | None:
    """Find a host by name or ID.

    Returns the HostReference or None if not found.
    """
    # Try as HostId first
    try:
        host_id = HostId(identifier)
        for host_ref in agents_by_host:
            if host_ref.host_id == host_id:
                return host_ref
    except ValueError:
        pass

    # Try as HostName
    host_name = HostName(identifier)
    matches = [host_ref for host_ref in agents_by_host if host_ref.host_name == host_name]
    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        raise UserInputError(f"Multiple hosts found with name '{identifier}'. Please use the host ID instead.")
    else:
        return None


def resolve_logs_target(
    identifier: str,
    mngr_ctx: MngrContext,
) -> LogsTarget:
    """Resolve a target identifier (agent or host name/ID) to a LogsTarget.

    First tries to find an agent with the given identifier.
    If no agent is found, tries to find a host.
    """
    with log_span("Loading agents and hosts"):
        agents_by_host, _providers = load_all_agents_grouped_by_host(mngr_ctx, include_destroyed=False)

    # Try finding as an agent first
    agent_result = _find_agent_in_hosts(identifier, agents_by_host)
    if agent_result is not None:
        host_ref, agent_ref = agent_result
        with log_span("Getting volume for agent {}", agent_ref.agent_name):
            provider = get_provider_instance(host_ref.provider_name, mngr_ctx)
            host_volume = provider.get_volume_for_host(host_ref.host_id)
            if host_volume is None:
                raise MngrError(
                    f"Provider '{host_ref.provider_name}' does not support volumes. Cannot read logs for this agent."
                )
            agent_volume = host_volume.get_agent_volume(agent_ref.agent_id)
            logs_volume = agent_volume.scoped("logs")
        return LogsTarget(
            volume=logs_volume,
            display_name=f"agent '{agent_ref.agent_name}'",
        )

    # Try finding as a host
    host_ref = _find_host_in_hosts(identifier, agents_by_host)
    if host_ref is not None:
        with log_span("Getting volume for host {}", host_ref.host_name):
            provider = get_provider_instance(host_ref.provider_name, mngr_ctx)
            host_volume = provider.get_volume_for_host(host_ref.host_id)
            if host_volume is None:
                raise MngrError(
                    f"Provider '{host_ref.provider_name}' does not support volumes. Cannot read logs for this host."
                )
            logs_volume = host_volume.volume.scoped("logs")
        return LogsTarget(
            volume=logs_volume,
            display_name=f"host '{host_ref.host_name}'",
        )

    raise UserInputError(f"No agent or host found with name or ID: {identifier}")


def list_log_files(target: LogsTarget) -> list[LogFileEntry]:
    """List available log files in the target's logs directory."""
    with log_span("Listing log files for {}", target.display_name):
        entries = target.volume.listdir("")
        return [
            LogFileEntry(name=_extract_filename(entry.path), size=entry.size)
            for entry in entries
            if entry.file_type == VolumeFileType.FILE
        ]


@pure
def _extract_filename(path: str) -> str:
    """Extract the filename from a volume path."""
    return path.rsplit("/", 1)[-1] if "/" in path else path


def read_log_content(target: LogsTarget, log_file_name: str) -> str:
    """Read the full content of a log file."""
    with log_span("Reading log file '{}' for {}", log_file_name, target.display_name):
        content_bytes = target.volume.read_file(log_file_name)
        return content_bytes.decode("utf-8", errors="replace")


@pure
def apply_head_or_tail(
    content: str,
    head_count: int | None,
    tail_count: int | None,
) -> str:
    """Apply head or tail line filtering to log content."""
    if head_count is None and tail_count is None:
        return content
    lines = content.splitlines(keepends=True)
    if head_count is not None:
        lines = lines[:head_count]
    elif tail_count is not None:
        lines = lines[-tail_count:]
    else:
        pass
    return "".join(lines)


class _FollowState(MutableModel):
    """Mutable state for the follow polling loop."""

    previous_length: int = Field(description="Length of content at last check")


def _check_for_new_content(
    target: LogsTarget,
    log_file_name: str,
    on_new_content: Callable[[str], None],
    state: _FollowState,
) -> bool:
    """Check for new content and emit it. Always returns False to keep polling."""
    try:
        current_content = read_log_content(target, log_file_name)
    except (MngrError, OSError) as e:
        logger.trace("Failed to read log file during follow: {}", e)
        return False
    current_length = len(current_content)
    if current_length > state.previous_length:
        new_content = current_content[state.previous_length :]
        on_new_content(new_content)
        state.previous_length = current_length
    elif current_length < state.previous_length:
        # File was truncated, re-read from the start
        logger.debug("Log file was truncated, re-reading from start")
        on_new_content(current_content)
        state.previous_length = current_length
    else:
        pass
    return False


def follow_log_file(
    target: LogsTarget,
    log_file_name: str,
    # Callback invoked with new content each time the file changes
    on_new_content: Callable[[str], None],
    tail_count: int | None,
) -> None:
    """Follow a log file, polling for new content until interrupted.

    If tail_count is specified, starts by showing the last N lines.
    Then polls for new content every FOLLOW_POLL_INTERVAL_SECONDS.
    """
    # Read initial content
    try:
        content = read_log_content(target, log_file_name)
    except (MngrError, OSError) as e:
        logger.debug("Failed to read initial log content: {}", e)
        content = ""

    # Show initial content (with optional tail)
    initial_content = apply_head_or_tail(content, head_count=None, tail_count=tail_count)
    if initial_content:
        on_new_content(initial_content)

    state = _FollowState(previous_length=len(content))

    # Poll indefinitely until interrupted (KeyboardInterrupt propagates out)
    # We use a very large timeout since the user will Ctrl+C to stop
    poll_until(
        condition=lambda: _check_for_new_content(target, log_file_name, on_new_content, state),
        timeout=365 * 24 * 3600.0,
        poll_interval=FOLLOW_POLL_INTERVAL_SECONDS,
    )
