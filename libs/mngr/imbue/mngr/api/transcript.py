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
from imbue.mngr.primitives import AgentId


class SessionTranscript(FrozenModel):
    """A single session's transcript data."""

    session_id: str = Field(description="Session ID (UUID)")
    file_path: Path = Field(description="Path to the session file on the host")
    content: str = Field(description="Raw JSONL transcript content")


class TranscriptResult(FrozenModel):
    """Result of fetching an agent's transcript across all sessions."""

    agent_name: str = Field(description="Name of the agent")
    sessions: tuple[SessionTranscript, ...] = Field(description="Transcripts for each session, in chronological order")


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
    """Retrieve the raw JSONL session transcripts for a single agent."""

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

    # Build the ordered list of session IDs to search for.
    # The history file has one session ID per line in chronological order.
    # The agent UUID is always the first session (used as --session-id on first launch).
    agent_id = matched_agent_ref.agent_id
    agent_state_dir = host_interface.host_dir / "agents" / str(agent_id)
    session_ids = _get_all_session_ids(host_interface, agent_state_dir, agent_id, agent_name)

    # Find and read all session files
    sessions: list[SessionTranscript] = []
    for session_id in session_ids:
        session_file = _find_session_file(host_interface, session_id, agent_name)
        if session_file is None:
            logger.debug("Session file not found for session {}, skipping", session_id)
            continue
        with log_span("Reading transcript file {} for agent {}", session_id, agent_name):
            content = host_interface.read_text_file(session_file)
        sessions.append(
            SessionTranscript(
                session_id=session_id,
                file_path=session_file,
                content=content,
            )
        )

    if not sessions:
        raise TranscriptNotFoundError(agent_name)

    return TranscriptResult(
        agent_name=agent_name,
        sessions=tuple(sessions),
    )


def _get_all_session_ids(
    host: OnlineHostInterface,
    agent_state_dir: Path,
    agent_id: AgentId,
    agent_name: str,
) -> list[str]:
    """Build the ordered list of all session IDs for an agent.

    Reads claude_session_id_history (one ID per line, chronological order).
    Falls back to the agent UUID if no history file exists.
    Deduplicates while preserving order.
    """
    history_path = agent_state_dir / "claude_session_id_history"
    try:
        content = host.read_text_file(history_path).strip()
        if content:
            history_ids = [line.strip() for line in content.splitlines() if line.strip()]
            logger.debug("Found {} session IDs in history for agent {}", len(history_ids), agent_name)
            # The agent UUID is the initial session; include it first if not already in history
            agent_uuid_str = str(agent_id.get_uuid())
            seen: set[str] = set()
            all_ids: list[str] = []
            for sid in [agent_uuid_str] + history_ids:
                if sid not in seen:
                    seen.add(sid)
                    all_ids.append(sid)
            return all_ids
    except FileNotFoundError:
        logger.debug("No session history file for agent {}", agent_name)

    # Fall back to agent UUID only
    return [str(agent_id.get_uuid())]


def _find_session_file(
    host: OnlineHostInterface,
    search_id: str,
    agent_name: str,
) -> Path | None:
    """Find a Claude Code session JSONL file on the host. Returns None if not found."""
    find_command = f"find ~/.claude/projects/ -name '{search_id}.jsonl' -type f 2>/dev/null | head -1"

    with log_span("Searching for session file {} for agent {}", search_id, agent_name):
        result = host.execute_command(find_command)

    if not result.success:
        logger.debug("Find command failed for agent {} (id={}): {}", agent_name, search_id, result.stderr)
        return None

    session_path = result.stdout.strip()
    if not session_path:
        logger.debug("No session file found for agent {} (id={})", agent_name, search_id)
        return None

    logger.debug("Found session file for agent {}: {}", agent_name, session_path)
    return Path(session_path)
