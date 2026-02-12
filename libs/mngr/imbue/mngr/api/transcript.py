from pathlib import Path

from loguru import logger
from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.logging import log_call
from imbue.imbue_common.logging import log_span
from imbue.mngr.api.find import resolve_agent_reference
from imbue.mngr.api.list import load_all_agents_grouped_by_host
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import MngrError
from imbue.mngr.errors import ProviderInstanceNotFoundError
from imbue.mngr.interfaces.host import OnlineHostInterface


class TranscriptResult(FrozenModel):
    """Result of fetching an agent's transcript."""

    agent_name: str = Field(description="Name of the agent")
    content: str = Field(description="Raw JSONL transcript content")
    session_file_path: Path = Field(description="Path to the session file on the host")


class TranscriptNotFoundError(MngrError, FileNotFoundError):
    """Raised when no transcript session file is found for an agent."""

    user_help_text = "Ensure the agent has started a Claude Code session. Use 'mngr list' to check agent status."

    def __init__(self, agent_name: str) -> None:
        self.agent_name = agent_name
        super().__init__(
            f"No transcript session file found for agent '{agent_name}'. "
            f"The agent may not have started a Claude Code session yet."
        )


@log_call
def get_agent_transcript(
    mngr_ctx: MngrContext,
    agent_identifier: str,
) -> TranscriptResult:
    """Retrieve the raw JSONL session transcript for a single agent."""

    # Load all agents grouped by host
    with log_span("Loading agents from all providers"):
        agents_by_host, providers = load_all_agents_grouped_by_host(mngr_ctx)
    provider_map = {provider.name: provider for provider in providers}

    # Find the matching agent by name or ID
    with log_span("Resolving agent reference for {}", agent_identifier):
        resolved = resolve_agent_reference(
            agent_identifier=agent_identifier,
            resolved_host=None,
            agents_by_host=agents_by_host,
        )
    # resolve_agent_reference raises UserInputError for non-None input that doesn't match;
    # it only returns None when agent_identifier is None (which can't happen here).
    assert resolved is not None
    matched_host_ref, matched_agent_ref = resolved

    agent_name = str(matched_agent_ref.agent_name)

    # Get the provider and host
    provider = provider_map.get(matched_host_ref.provider_name)
    if not provider:
        raise ProviderInstanceNotFoundError(matched_host_ref.provider_name)

    host_interface = provider.get_host(matched_host_ref.host_id)

    if not isinstance(host_interface, OnlineHostInterface):
        raise MngrError(f"Host '{matched_host_ref.host_id}' is offline. Cannot read transcript.")

    # Find the JSONL session file on the host.
    # First try the tracked session ID (written by Claude Code's SessionStart hook),
    # then fall back to the agent's UUID (used as --session-id on first launch).
    agent_id = matched_agent_ref.agent_id
    agent_state_dir = host_interface.host_dir / "agents" / str(agent_id)
    session_id = _read_tracked_session_id(host_interface, agent_state_dir, agent_name)
    search_id = session_id if session_id else str(agent_id.get_uuid())
    session_file_path = _find_session_file(host_interface, search_id, agent_name)

    # Read the transcript content
    with log_span("Reading transcript file for agent {}", agent_name):
        content = host_interface.read_text_file(session_file_path)

    return TranscriptResult(
        agent_name=agent_name,
        content=content,
        session_file_path=session_file_path,
    )


def _read_tracked_session_id(
    host: OnlineHostInterface,
    agent_state_dir: Path,
    agent_name: str,
) -> str | None:
    """Read the tracked session ID from the agent's state directory.

    Returns the session ID string if the file exists and is non-empty, else None.
    """
    session_id_path = agent_state_dir / "claude_session_id"
    try:
        content = host.read_text_file(session_id_path).strip()
        if content:
            logger.debug("Found tracked session ID for agent {}: {}", agent_name, content)
            return content
    except FileNotFoundError:
        logger.debug("No tracked session ID file for agent {}", agent_name)
    return None


def _find_session_file(
    host: OnlineHostInterface,
    search_id: str,
    agent_name: str,
) -> Path:
    """Find the Claude Code session JSONL file on the host."""
    find_command = f"find ~/.claude/projects/ -name '{search_id}.jsonl' -type f 2>/dev/null | head -1"

    with log_span("Searching for session file for agent {}", agent_name):
        result = host.execute_command(find_command)

    if not result.success:
        logger.debug("Find command failed for agent {} (id={}): {}", agent_name, search_id, result.stderr)
        raise TranscriptNotFoundError(agent_name)

    session_path = result.stdout.strip()
    if not session_path:
        logger.debug("No session file found for agent {} (id={})", agent_name, search_id)
        raise TranscriptNotFoundError(agent_name)

    logger.debug("Found session file for agent {}: {}", agent_name, session_path)
    return Path(session_path)
