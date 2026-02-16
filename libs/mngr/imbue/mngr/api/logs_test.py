import json
from collections.abc import Callable
from pathlib import Path

import pytest
from inline_snapshot import snapshot

from imbue.mngr.api.logs import LogsTarget
from imbue.mngr.api.logs import _FollowState
from imbue.mngr.api.logs import _check_for_new_content
from imbue.mngr.api.logs import _extract_filename
from imbue.mngr.api.logs import apply_head_or_tail
from imbue.mngr.api.logs import follow_log_file
from imbue.mngr.api.logs import list_log_files
from imbue.mngr.api.logs import read_log_content
from imbue.mngr.api.logs import resolve_logs_target
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import UserInputError
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import HostName
from imbue.mngr.providers.local.volume import LocalVolume


def _capture_and_interrupt(captured: list[str]) -> Callable[[str], None]:
    """Create a callback that captures content then interrupts."""

    def _callback(content: str) -> None:
        captured.append(content)
        raise KeyboardInterrupt

    return _callback


@pytest.fixture
def logs_volume_target(tmp_path: Path) -> tuple[LogsTarget, Path]:
    """Create a LogsTarget backed by a temp directory.

    Returns (target, logs_dir) so tests can write files into the volume.
    """
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    volume = LocalVolume(root_path=logs_dir)
    target = LogsTarget(volume=volume, display_name="test")
    return target, logs_dir


# =============================================================================
# apply_head_or_tail tests
# =============================================================================


def test_apply_head_or_tail_returns_all_when_no_filter() -> None:
    content = "line1\nline2\nline3\n"
    result = apply_head_or_tail(content, head_count=None, tail_count=None)
    assert result == content


def test_apply_head_or_tail_returns_first_n_lines() -> None:
    content = "line1\nline2\nline3\nline4\n"
    result = apply_head_or_tail(content, head_count=2, tail_count=None)
    assert result == snapshot("line1\nline2\n")


def test_apply_head_or_tail_returns_last_n_lines() -> None:
    content = "line1\nline2\nline3\nline4\n"
    result = apply_head_or_tail(content, head_count=None, tail_count=2)
    assert result == snapshot("line3\nline4\n")


def test_apply_head_or_tail_handles_head_larger_than_content() -> None:
    content = "line1\nline2\n"
    result = apply_head_or_tail(content, head_count=10, tail_count=None)
    assert result == content


def test_apply_head_or_tail_handles_tail_larger_than_content() -> None:
    content = "line1\nline2\n"
    result = apply_head_or_tail(content, head_count=None, tail_count=10)
    assert result == content


def test_apply_head_or_tail_handles_empty_content() -> None:
    result = apply_head_or_tail("", head_count=5, tail_count=None)
    assert result == ""


# =============================================================================
# _extract_filename tests
# =============================================================================


def test_extract_filename_from_simple_path() -> None:
    assert _extract_filename("output.log") == "output.log"


def test_extract_filename_from_nested_path() -> None:
    assert _extract_filename("some/dir/output.log") == "output.log"


# =============================================================================
# list_log_files / read_log_content tests
# =============================================================================


def test_list_log_files_returns_only_files(logs_volume_target: tuple[LogsTarget, Path]) -> None:
    target, logs_dir = logs_volume_target
    (logs_dir / "output.log").write_text("some log data")
    (logs_dir / "error.log").write_text("some errors")
    (logs_dir / "subdir").mkdir()

    log_files = list_log_files(target)

    names = sorted(lf.name for lf in log_files)
    assert names == snapshot(["error.log", "output.log"])


def test_read_log_content_returns_file_contents(logs_volume_target: tuple[LogsTarget, Path]) -> None:
    target, logs_dir = logs_volume_target
    (logs_dir / "test.log").write_text("hello world\nsecond line\n")

    content = read_log_content(target, "test.log")

    assert content == snapshot("hello world\nsecond line\n")


# =============================================================================
# resolve_logs_target tests
# =============================================================================


def _create_agent_data_json(
    # The per-host directory (local_provider.host_dir)
    per_host_dir: Path,
    agent_name: str,
    command: str,
) -> AgentId:
    """Create an agent data.json file so the agent appears in agent references.

    Returns the generated AgentId.
    """
    agent_id = AgentId.generate()
    agent_dir = per_host_dir / "agents" / str(agent_id)
    agent_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "id": str(agent_id),
        "name": agent_name,
        "type": "generic",
        "command": command,
        "work_dir": "/tmp/test",
        "create_time": "2026-01-01T00:00:00+00:00",
    }
    (agent_dir / "data.json").write_text(json.dumps(data))
    return agent_id


def test_resolve_logs_target_finds_agent(
    temp_mngr_ctx: MngrContext,
    local_provider,
) -> None:
    """Verify resolve_logs_target finds an agent and returns a scoped logs volume."""
    per_host_dir = local_provider.host_dir
    agent_id = _create_agent_data_json(per_host_dir, "test-resolve-agent", "sleep 94817")

    # Create logs in the agent's directory (volume and host_dir are the same path now)
    agent_logs_dir = per_host_dir / "agents" / str(agent_id) / "logs"
    agent_logs_dir.mkdir(parents=True, exist_ok=True)
    (agent_logs_dir / "output.log").write_text("agent log content\n")

    # Resolve should find the agent
    target = resolve_logs_target("test-resolve-agent", temp_mngr_ctx)
    assert "test-resolve-agent" in target.display_name

    # Should be able to list and read log files
    log_files = list_log_files(target)
    assert len(log_files) == 1
    assert log_files[0].name == "output.log"

    content = read_log_content(target, "output.log")
    assert content == "agent log content\n"


def test_resolve_logs_target_finds_host(
    temp_mngr_ctx: MngrContext,
    local_provider,
) -> None:
    """Verify resolve_logs_target falls back to host when no agent matches."""
    per_host_dir = local_provider.host_dir
    host = local_provider.get_host(HostName("local"))

    # Create an agent so the host appears in load_all_agents_grouped_by_host
    _create_agent_data_json(per_host_dir, "unrelated-agent-47291", "sleep 47291")

    # Create logs directly in the host volume (not under agents/)
    host_logs_dir = per_host_dir / "logs"
    host_logs_dir.mkdir(parents=True, exist_ok=True)
    (host_logs_dir / "host-output.log").write_text("host log content\n")

    # Resolve using the host ID (not name, since "local" doesn't match agent-first)
    target = resolve_logs_target(str(host.id), temp_mngr_ctx)
    assert "host" in target.display_name

    # Should be able to list and read log files
    log_files = list_log_files(target)
    assert len(log_files) == 1
    assert log_files[0].name == "host-output.log"

    content = read_log_content(target, "host-output.log")
    assert content == "host log content\n"


def test_resolve_logs_target_raises_for_unknown_identifier(
    temp_mngr_ctx: MngrContext,
) -> None:
    with pytest.raises(UserInputError, match="No agent or host found"):
        resolve_logs_target("nonexistent-identifier-abc123", temp_mngr_ctx)


# =============================================================================
# _check_for_new_content tests
# =============================================================================


def test_check_for_new_content_detects_appended_content(logs_volume_target: tuple[LogsTarget, Path]) -> None:
    """Verify _check_for_new_content detects new content appended to a log file."""
    target, logs_dir = logs_volume_target
    log_file = logs_dir / "test.log"
    log_file.write_text("initial content\n")

    captured_content: list[str] = []
    state = _FollowState(previous_length=len("initial content\n"))

    # No new content yet
    _check_for_new_content(target, "test.log", captured_content.append, state)
    assert captured_content == []

    # Append new content
    log_file.write_text("initial content\nnew line\n")

    _check_for_new_content(target, "test.log", captured_content.append, state)
    assert len(captured_content) == 1
    assert captured_content[0] == "new line\n"


def test_check_for_new_content_handles_truncated_file(logs_volume_target: tuple[LogsTarget, Path]) -> None:
    """Verify _check_for_new_content handles file truncation."""
    target, logs_dir = logs_volume_target
    log_file = logs_dir / "test.log"
    log_file.write_text("long content that will be truncated\n")

    captured_content: list[str] = []
    state = _FollowState(previous_length=len("long content that will be truncated\n"))

    # Truncate the file
    log_file.write_text("short\n")

    _check_for_new_content(target, "test.log", captured_content.append, state)
    assert len(captured_content) == 1
    assert captured_content[0] == "short\n"


# =============================================================================
# follow_log_file tests
# =============================================================================


def test_follow_log_file_emits_initial_content_with_tail(logs_volume_target: tuple[LogsTarget, Path]) -> None:
    """Verify follow_log_file emits tailed initial content via the callback."""
    target, logs_dir = logs_volume_target
    (logs_dir / "test.log").write_text("line1\nline2\nline3\nline4\nline5\n")

    captured: list[str] = []

    with pytest.raises(KeyboardInterrupt):
        follow_log_file(
            target=target,
            log_file_name="test.log",
            on_new_content=_capture_and_interrupt(captured),
            tail_count=2,
        )

    assert len(captured) == 1
    assert captured[0] == "line4\nline5\n"


def test_follow_log_file_emits_all_content_when_no_tail(logs_volume_target: tuple[LogsTarget, Path]) -> None:
    """Verify follow_log_file emits all content when tail_count is None."""
    target, logs_dir = logs_volume_target
    (logs_dir / "test.log").write_text("line1\nline2\n")

    captured: list[str] = []

    with pytest.raises(KeyboardInterrupt):
        follow_log_file(
            target=target,
            log_file_name="test.log",
            on_new_content=_capture_and_interrupt(captured),
            tail_count=None,
        )

    assert len(captured) == 1
    assert captured[0] == "line1\nline2\n"
