from pathlib import Path
from uuid import uuid4

import pytest

from imbue.mngr.api.create import CreateAgentOptions
from imbue.mngr.api.transcript import SessionTranscript
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
    session = SessionTranscript(
        session_id="abc-123",
        file_path=Path("/home/user/.claude/projects/foo/abc123.jsonl"),
        content='{"type":"user","message":"hello"}\n',
    )
    result = TranscriptResult(
        agent_name="test-agent",
        sessions=(session,),
    )
    assert result.agent_name == "test-agent"
    assert len(result.sessions) == 1
    assert result.sessions[0].content == '{"type":"user","message":"hello"}\n'
    assert result.sessions[0].file_path == Path("/home/user/.claude/projects/foo/abc123.jsonl")


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
    host = local_provider.create_host(HostName("test-no-transcript-" + uuid4().hex))
    assert isinstance(host, Host)

    agent = host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=CreateAgentOptions(
            name=AgentName("no-transcript-agent-" + uuid4().hex),
            agent_type=AgentTypeName("generic"),
            command=CommandString("sleep 928374"),
        ),
    )

    with pytest.raises(TranscriptNotFoundError):
        get_agent_transcript(
            mngr_ctx=temp_mngr_ctx,
            agent_identifier=str(agent.name),
        )


def test_get_agent_transcript_returns_single_session_from_uuid(
    tmp_home_dir: Path,
    temp_work_dir: Path,
    temp_mngr_ctx: MngrContext,
    local_provider: LocalProviderInstance,
) -> None:
    """Test that get_agent_transcript finds the session file by agent UUID when no history exists."""
    host = local_provider.create_host(HostName("test-transcript-" + uuid4().hex))
    assert isinstance(host, Host)

    agent = host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=CreateAgentOptions(
            name=AgentName("transcript-agent-" + uuid4().hex),
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
    assert len(result.sessions) == 1
    assert result.sessions[0].content == fake_content
    assert result.sessions[0].session_id == str(agent_uuid)


def test_get_agent_transcript_returns_multiple_sessions_from_history(
    tmp_home_dir: Path,
    temp_work_dir: Path,
    temp_host_dir: Path,
    temp_mngr_ctx: MngrContext,
    local_provider: LocalProviderInstance,
) -> None:
    """Test that get_agent_transcript reads all sessions from the history file."""
    host = local_provider.create_host(HostName("test-multi-session-" + uuid4().hex))
    assert isinstance(host, Host)

    agent = host.create_agent_state(
        work_dir_path=temp_work_dir,
        options=CreateAgentOptions(
            name=AgentName("multi-session-agent-" + uuid4().hex),
            agent_type=AgentTypeName("generic"),
            command=CommandString("sleep 928376"),
        ),
    )

    agent_uuid = agent.id.get_uuid()
    second_session_id = str(uuid4())

    # Create session files
    claude_projects_dir = tmp_home_dir / ".claude" / "projects" / "test-project"
    claude_projects_dir.mkdir(parents=True, exist_ok=True)

    first_content = '{"type":"user","message":"first session"}\n'
    (claude_projects_dir / f"{agent_uuid}.jsonl").write_text(first_content)

    second_content = '{"type":"user","message":"second session"}\n'
    (claude_projects_dir / f"{second_session_id}.jsonl").write_text(second_content)

    # Write session history file
    agent_state_dir = temp_host_dir / "agents" / str(agent.id)
    history_file = agent_state_dir / "claude_session_id_history"
    history_file.write_text(f"{agent_uuid}\n{second_session_id}\n")

    result = get_agent_transcript(
        mngr_ctx=temp_mngr_ctx,
        agent_identifier=str(agent.name),
    )

    assert result.agent_name == str(agent.name)
    assert len(result.sessions) == 2
    assert result.sessions[0].session_id == str(agent_uuid)
    assert result.sessions[0].content == first_content
    assert result.sessions[1].session_id == second_session_id
    assert result.sessions[1].content == second_content
