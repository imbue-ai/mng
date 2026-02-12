from pathlib import Path
from uuid import UUID

from loguru import logger
from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.logging import log_call
from imbue.imbue_common.logging import log_span
from imbue.mngr.api.find import resolve_agent_reference
from imbue.mngr.api.list import load_all_agents_grouped_by_host
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import HostOfflineError
from imbue.mngr.errors import MngrError
from imbue.mngr.interfaces.host import OnlineHostInterface


class TranscriptResult(FrozenModel):
    """Result of fetching an agent's transcript."""

    agent_name: str = Field(description="Name of the agent")
    content: str = Field(description="Raw JSONL transcript content")
    session_file_path: Path = Field(description="Path to the session file on the host")


class TranscriptNotFoundError(MngrError):
    """Raised when no transcript session file is found for an agent."""

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
    assert resolved is not None, "resolve_agent_reference should not return None for non-None identifier"
    matched_host_ref, matched_agent_ref = resolved

    agent_name = str(matched_agent_ref.agent_name)

    # Get the provider and host
    provider = provider_map.get(matched_host_ref.provider_name)
    if not provider:
        raise MngrError(f"Provider '{matched_host_ref.provider_name}' not found")

    host_interface = provider.get_host(matched_host_ref.host_id)

    if not isinstance(host_interface, OnlineHostInterface):
        raise HostOfflineError(f"Host '{matched_host_ref.host_id}' is offline. Cannot read transcript.")

    host = host_interface

    # Find the JSONL session file on the host
    agent_uuid = matched_agent_ref.agent_id.get_uuid()
    session_file_path = _find_session_file(host, agent_uuid, agent_name)

    # Read the transcript content
    with log_span("Reading transcript file for agent {}", agent_name):
        content = host.read_text_file(session_file_path)

    return TranscriptResult(
        agent_name=agent_name,
        content=content,
        session_file_path=session_file_path,
    )


def _find_session_file(
    host: OnlineHostInterface,
    agent_uuid: UUID,
    agent_name: str,
) -> Path:
    """Find the Claude Code session JSONL file on the host."""
    find_command = f"find ~/.claude/projects/ -name '{agent_uuid}.jsonl' -type f 2>/dev/null | head -1"

    with log_span("Searching for session file for agent {}", agent_name):
        result = host.execute_command(find_command)

    if not result.success:
        logger.debug("Find command failed for agent {} (uuid={}): {}", agent_name, agent_uuid, result.stderr)
        raise TranscriptNotFoundError(agent_name)

    session_path = result.stdout.strip()
    if not session_path:
        logger.debug("No session file found for agent {} (uuid={})", agent_name, agent_uuid)
        raise TranscriptNotFoundError(agent_name)

    logger.debug("Found session file for agent {}: {}", agent_name, session_path)
    return Path(session_path)
