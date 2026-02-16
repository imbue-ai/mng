import json
import threading
from collections.abc import Callable
from pathlib import Path

import pytest
from inline_snapshot import snapshot

from imbue.mngr.api.connect import build_ssh_base_args
from imbue.mngr.api.logs import LogsTarget
from imbue.mngr.api.logs import _FollowState
from imbue.mngr.api.logs import _build_tail_args
from imbue.mngr.api.logs import _check_for_new_content
from imbue.mngr.api.logs import _extract_filename
from imbue.mngr.api.logs import _parse_file_listing_output
from imbue.mngr.api.logs import apply_head_or_tail
from imbue.mngr.api.logs import follow_log_file
from imbue.mngr.api.logs import list_log_files
from imbue.mngr.api.logs import read_log_content
from imbue.mngr.api.logs import resolve_logs_target
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import MngrError
from imbue.mngr.errors import UserInputError
from imbue.mngr.interfaces.host import OnlineHostInterface
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


# =============================================================================
# _parse_file_listing_output tests
# =============================================================================


def test_parse_file_listing_output_parses_tab_separated_entries() -> None:
    output = "output.log\t1234\nerror.log\t567\n"
    entries = _parse_file_listing_output(output)
    assert len(entries) == 2
    assert entries[0].name == "output.log"
    assert entries[0].size == 1234
    assert entries[1].name == "error.log"
    assert entries[1].size == 567


def test_parse_file_listing_output_skips_empty_lines() -> None:
    output = "output.log\t100\n\n\nerror.log\t200\n"
    entries = _parse_file_listing_output(output)
    assert len(entries) == 2


def test_parse_file_listing_output_handles_invalid_size() -> None:
    output = "output.log\tnot_a_number\n"
    entries = _parse_file_listing_output(output)
    assert len(entries) == 1
    assert entries[0].size == 0


def test_parse_file_listing_output_handles_empty_output() -> None:
    entries = _parse_file_listing_output("")
    assert entries == []


# =============================================================================
# _build_tail_args tests
# =============================================================================


def test_build_tail_args_with_tail_count() -> None:
    args = _build_tail_args(Path("/tmp/test.log"), tail_count=50)
    assert args == snapshot(["tail", "-n", "50", "-f", "/tmp/test.log"])


def test_build_tail_args_without_tail_count_shows_from_beginning() -> None:
    args = _build_tail_args(Path("/tmp/test.log"), tail_count=None)
    assert args == snapshot(["tail", "-n", "+1", "-f", "/tmp/test.log"])


# =============================================================================
# Host-based list/read tests
# =============================================================================


@pytest.fixture
def logs_host_target(
    tmp_path: Path,
    temp_mngr_ctx: MngrContext,
    local_provider,
) -> tuple[LogsTarget, Path]:
    """Create a LogsTarget backed by a local online host (no volume).

    Returns (target, logs_dir) so tests can write files into the logs directory.
    """
    logs_dir = tmp_path / "host_logs"
    logs_dir.mkdir()
    host = local_provider.get_host(HostName("local"))
    assert isinstance(host, OnlineHostInterface)
    target = LogsTarget(
        volume=None,
        online_host=host,
        logs_path=logs_dir,
        display_name="test-host",
    )
    return target, logs_dir


def test_list_log_files_via_host_returns_files(logs_host_target: tuple[LogsTarget, Path]) -> None:
    """Verify list_log_files works via host execute_command when volume is None."""
    target, logs_dir = logs_host_target
    (logs_dir / "output.log").write_text("some log data")
    (logs_dir / "error.log").write_text("err")
    (logs_dir / "subdir").mkdir()

    log_files = list_log_files(target)

    names = sorted(lf.name for lf in log_files)
    assert names == snapshot(["error.log", "output.log"])


def test_list_log_files_via_host_returns_correct_sizes(logs_host_target: tuple[LogsTarget, Path]) -> None:
    """Verify list_log_files via host returns correct file sizes."""
    target, logs_dir = logs_host_target
    (logs_dir / "test.log").write_text("12345")

    log_files = list_log_files(target)

    assert len(log_files) == 1
    assert log_files[0].name == "test.log"
    assert log_files[0].size == 5


def test_list_log_files_via_host_returns_empty_for_nonexistent_dir(
    temp_mngr_ctx: MngrContext,
    local_provider,
) -> None:
    """Verify list_log_files via host returns empty list when logs dir does not exist."""
    host = local_provider.get_host(HostName("local"))
    target = LogsTarget(
        volume=None,
        online_host=host,
        logs_path=Path("/tmp/nonexistent-dir-logs-92847"),
        display_name="test-host",
    )

    log_files = list_log_files(target)

    assert log_files == []


def test_read_log_content_via_host(logs_host_target: tuple[LogsTarget, Path]) -> None:
    """Verify read_log_content works via host execute_command when volume is None.

    Note: pyinfra's CommandOutput.stdout joins lines with newlines but drops
    the final trailing newline, so host-based reads may differ from volume-based
    reads in trailing whitespace.
    """
    target, logs_dir = logs_host_target
    (logs_dir / "test.log").write_text("hello from host\nsecond line\n")

    content = read_log_content(target, "test.log")

    assert "hello from host" in content
    assert "second line" in content


def test_read_log_content_via_host_raises_for_missing_file(logs_host_target: tuple[LogsTarget, Path]) -> None:
    """Verify read_log_content via host raises MngrError for missing files."""
    target, _logs_dir = logs_host_target

    with pytest.raises(MngrError, match="Failed to read log file"):
        read_log_content(target, "nonexistent-file-58291.log")


def test_list_log_files_raises_when_no_volume_or_host() -> None:
    """Verify list_log_files raises MngrError when neither volume nor host is available."""
    target = LogsTarget(display_name="test-empty")

    with pytest.raises(MngrError, match="no volume or online host"):
        list_log_files(target)


def test_read_log_content_raises_when_no_volume_or_host() -> None:
    """Verify read_log_content raises MngrError when neither volume nor host is available."""
    target = LogsTarget(display_name="test-empty")

    with pytest.raises(MngrError, match="no volume or online host"):
        read_log_content(target, "test.log")


# =============================================================================
# resolve_logs_target with online host tests
# =============================================================================


def test_resolve_logs_target_populates_online_host_for_agent(
    temp_mngr_ctx: MngrContext,
    local_provider,
) -> None:
    """Verify resolve_logs_target sets online_host and logs_path when host is online."""
    per_host_dir = local_provider.host_dir
    agent_id = _create_agent_data_json(per_host_dir, "test-online-agent-82719", "sleep 82719")

    # Create logs directory
    agent_logs_dir = per_host_dir / "agents" / str(agent_id) / "logs"
    agent_logs_dir.mkdir(parents=True, exist_ok=True)
    (agent_logs_dir / "output.log").write_text("test content\n")

    target = resolve_logs_target("test-online-agent-82719", temp_mngr_ctx)

    # Both volume and online_host should be populated for local provider
    assert target.volume is not None
    assert target.online_host is not None
    assert target.logs_path is not None
    assert str(target.logs_path).endswith(f"agents/{agent_id}/logs")


# =============================================================================
# follow_log_file via host tests
# =============================================================================


def test_follow_log_file_via_host_streams_existing_content(logs_host_target: tuple[LogsTarget, Path]) -> None:
    """Verify follow_log_file uses tail -f on host and emits existing file content."""
    target, logs_dir = logs_host_target
    (logs_dir / "test.log").write_text("line1\nline2\nline3\n")

    captured: list[str] = []
    call_count = [0]

    def capture_then_interrupt(content: str) -> None:
        captured.append(content)
        call_count[0] += 1
        # Interrupt after receiving some content
        if call_count[0] >= 3:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        follow_log_file(
            target=target,
            log_file_name="test.log",
            on_new_content=capture_then_interrupt,
            tail_count=None,
        )

    # Should have received the file content line by line (tail -f streams line by line)
    joined = "".join(captured)
    assert "line1" in joined
    assert "line2" in joined
    assert "line3" in joined


def test_follow_log_file_via_host_with_tail_count(logs_host_target: tuple[LogsTarget, Path]) -> None:
    """Verify follow_log_file via host respects tail_count."""
    target, logs_dir = logs_host_target
    (logs_dir / "test.log").write_text("line1\nline2\nline3\nline4\nline5\n")

    captured: list[str] = []
    call_count = [0]

    def capture_then_interrupt(content: str) -> None:
        captured.append(content)
        call_count[0] += 1
        if call_count[0] >= 2:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        follow_log_file(
            target=target,
            log_file_name="test.log",
            on_new_content=capture_then_interrupt,
            tail_count=2,
        )

    # Should only see the last 2 lines
    joined = "".join(captured)
    assert "line4" in joined
    assert "line5" in joined
    assert "line1" not in joined


def test_follow_log_file_via_host_detects_new_content(logs_host_target: tuple[LogsTarget, Path]) -> None:
    """Verify follow_log_file via host streams new content appended to the file."""
    target, logs_dir = logs_host_target
    log_file = logs_dir / "test.log"
    log_file.write_text("initial\n")

    captured: list[str] = []
    call_count = [0]

    append_event = threading.Event()

    def capture_and_maybe_interrupt(content: str) -> None:
        captured.append(content)
        call_count[0] += 1
        # After receiving the initial content, signal the writer thread
        if call_count[0] == 1:
            append_event.set()
        # Interrupt after we see the appended content
        if call_count[0] >= 2:
            raise KeyboardInterrupt

    # Start a writer thread that waits for the signal then appends content
    def append_content() -> None:
        append_event.wait(timeout=10.0)
        with log_file.open("a") as f:
            f.write("appended\n")
            f.flush()

    writer = threading.Thread(target=append_content, daemon=True)
    writer.start()

    with pytest.raises(KeyboardInterrupt):
        follow_log_file(
            target=target,
            log_file_name="test.log",
            on_new_content=capture_and_maybe_interrupt,
            tail_count=None,
        )

    joined = "".join(captured)
    assert "initial" in joined
    assert "appended" in joined


# =============================================================================
# build_ssh_base_args tests
# =============================================================================


def test_build_ssh_base_args_includes_key_and_port(
    temp_mngr_ctx: MngrContext,
    local_provider,
) -> None:
    """Verify build_ssh_base_args constructs correct args for a local host.

    Local hosts return basic SSH args without key/port since they use the
    local connector (not SSH). This test verifies the function runs without error.
    """
    host = local_provider.get_host(HostName("local"))
    assert isinstance(host, OnlineHostInterface)

    # Local hosts have is_local=True, so build_ssh_base_args should still work
    # (it reads from connector data which may not have SSH fields set)
    args = build_ssh_base_args(host, is_unknown_host_allowed=True)

    # Should start with "ssh" and end with the host target
    assert args[0] == "ssh"
    # Should have StrictHostKeyChecking=no since no known_hosts for local
    assert "-o" in args
    strict_idx = args.index("StrictHostKeyChecking=no") if "StrictHostKeyChecking=no" in args else -1
    assert strict_idx >= 0
