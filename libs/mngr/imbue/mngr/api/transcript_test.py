from pathlib import Path
from uuid import uuid4

import pytest

from imbue.mngr.api.create import CreateAgentOptions
from imbue.mngr.api.transcript import TranscriptNotFoundError
from imbue.mngr.api.transcript import TranscriptResult
from imbue.mngr.api.transcript import get_agent_transcript
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import UserInputError
from imbue.mngr.hosts.host import Host
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import HostName
from imbue.mngr.providers.local.instance import LocalProviderInstance


def test_transcript_result_stores_expected_fields() -> None:
    result = TranscriptResult(
        agent_name="test-agent",
        content='{"type":"user","message":"hello"}\n',
        session_file_path="/home/user/.claude/projects/foo/abc123.jsonl",
    )
    assert result.agent_name == "test-agent"
    assert result.content == '{"type":"user","message":"hello"}\n'
    assert result.session_file_path == "/home/user/.claude/projects/foo/abc123.jsonl"


def test_get_agent_transcript_raises_not_found_for_nonexistent_agent(
    temp_mngr_ctx: MngrContext,
) -> None:
    with pytest.raises(UserInputError):
        get_agent_transcript(
            mngr_ctx=temp_mngr_ctx,
            agent_identifier="nonexistent-agent-" + uuid4().hex,
        )


def test_get_agent_transcript_raises_transcript_not_found_when_no_session_file(
    temp_work_dir: Path,
    temp_mngr_ctx: MngrContext,
    local_provider: LocalProviderInstance,
) -> None:
    """Test that get_agent_transcript raises TranscriptNotFoundError when there is no JSONL session file."""
    host = local_provider.create_host(HostName("test-no-transcript-" + uuid4().hex[:8]))
    assert isinstance(host, Host)

    agent = host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=CreateAgentOptions(
            name=AgentName("no-transcript-agent-" + uuid4().hex[:8]),
            agent_type=AgentTypeName("generic"),
            command=CommandString("sleep 928374"),
        ),
    )

    with pytest.raises(TranscriptNotFoundError):
        get_agent_transcript(
            mngr_ctx=temp_mngr_ctx,
            agent_identifier=str(agent.name),
        )


def test_get_agent_transcript_returns_content_when_session_file_exists(
    tmp_home_dir: Path,
    temp_work_dir: Path,
    temp_mngr_ctx: MngrContext,
    local_provider: LocalProviderInstance,
) -> None:
    """Test that get_agent_transcript reads the session file content when it exists."""
    host = local_provider.create_host(HostName("test-transcript-" + uuid4().hex[:8]))
    assert isinstance(host, Host)

    agent = host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=CreateAgentOptions(
            name=AgentName("transcript-agent-" + uuid4().hex[:8]),
            agent_type=AgentTypeName("generic"),
            command=CommandString("sleep 928375"),
        ),
    )

    # Create a fake Claude Code session file at the expected path
    agent_uuid = agent.id.get_uuid()
    claude_projects_dir = tmp_home_dir / ".claude" / "projects" / "test-project"
    claude_projects_dir.mkdir(parents=True, exist_ok=True)
    session_file = claude_projects_dir / f"{agent_uuid}.jsonl"
    fake_content = '{"type":"user","message":"hello"}\n{"type":"assistant","message":"hi"}\n'
    session_file.write_text(fake_content)

    result = get_agent_transcript(
        mngr_ctx=temp_mngr_ctx,
        agent_identifier=str(agent.name),
    )

    assert result.agent_name == str(agent.name)
    assert result.content == fake_content
    assert str(agent_uuid) in result.session_file_path
