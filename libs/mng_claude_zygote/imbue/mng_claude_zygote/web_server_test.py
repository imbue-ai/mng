"""Unit tests for the web_server.py resource script.

Tests the pure/near-pure functions by importing them from the resource module.
The web_server.py script is loaded as a module for testing purposes.
"""

import io
import json
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from imbue.mng_claude_zygote.provisioning import load_zygote_resource


@pytest.fixture()
def web_server_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    """Load web_server.py as a module for testing.

    Sets environment variables via monkeypatch.setenv so the module can be
    loaded without requiring a real agent state directory.
    """
    agent_state_dir = tmp_path / "agent_state"
    agent_state_dir.mkdir()
    host_dir = tmp_path / "host"
    host_dir.mkdir()
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    monkeypatch.setenv("MNG_AGENT_STATE_DIR", str(agent_state_dir))
    monkeypatch.setenv("MNG_HOST_DIR", str(host_dir))
    monkeypatch.setenv("MNG_AGENT_WORK_DIR", str(work_dir))
    monkeypatch.setenv("MNG_AGENT_ID", "agent-test-123")
    monkeypatch.setenv("MNG_AGENT_NAME", "test-agent")
    monkeypatch.setenv("MNG_HOST_NAME", "test-host")

    source = load_zygote_resource("web_server.py")
    module = types.ModuleType("web_server_test_module")
    module.__file__ = "web_server.py"
    exec(compile(source, "web_server.py", "exec"), module.__dict__)  # noqa: S102
    return module


def _make_process_stub(
    *,
    is_alive: bool,
) -> SimpleNamespace:
    """Create a lightweight process-like stub with poll() and terminate()."""
    return SimpleNamespace(
        poll=lambda: None if is_alive else 1,
        terminate=lambda: None,
        kill=lambda: None,
        wait=lambda: None,
    )


# -- _html_escape tests --


def test_html_escape_escapes_ampersand(web_server_module: types.ModuleType) -> None:
    assert web_server_module._html_escape("a&b") == "a&amp;b"


def test_html_escape_escapes_angle_brackets(web_server_module: types.ModuleType) -> None:
    result = web_server_module._html_escape("<script>")
    assert "<" not in result
    assert ">" not in result


def test_html_escape_escapes_quotes(web_server_module: types.ModuleType) -> None:
    assert "&quot;" in web_server_module._html_escape('say "hello"')


def test_html_escape_escapes_single_quotes(web_server_module: types.ModuleType) -> None:
    result = web_server_module._html_escape("it's")
    # html.escape escapes single quotes as &#x27;
    assert "&#x27;" in result or "'" in result


# -- _read_conversations tests --


def test_read_conversations_empty_when_no_event_files(web_server_module: types.ModuleType) -> None:
    # The module's paths point to tmp dirs that have no event files
    result = web_server_module._read_conversations()
    assert result == []


def test_read_conversations_parses_conversation_events(web_server_module: types.ModuleType) -> None:
    events_path = web_server_module.CONVERSATIONS_EVENTS_PATH
    events_path.parent.mkdir(parents=True, exist_ok=True)
    events_path.write_text(
        json.dumps(
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "type": "conversation_created",
                "event_id": "evt-1",
                "source": "conversations",
                "conversation_id": "conv-abc",
                "model": "claude-sonnet-4-6",
            }
        )
        + "\n"
    )

    result = web_server_module._read_conversations()

    assert len(result) == 1
    assert result[0]["conversation_id"] == "conv-abc"
    assert result[0]["model"] == "claude-sonnet-4-6"


def test_read_conversations_sorted_by_most_recent(web_server_module: types.ModuleType) -> None:
    events_path = web_server_module.CONVERSATIONS_EVENTS_PATH
    events_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "conversation_id": "conv-old",
                "model": "m",
                "type": "conversation_created",
                "event_id": "e1",
                "source": "conversations",
            }
        ),
        json.dumps(
            {
                "timestamp": "2026-02-01T00:00:00Z",
                "conversation_id": "conv-new",
                "model": "m",
                "type": "conversation_created",
                "event_id": "e2",
                "source": "conversations",
            }
        ),
    ]
    events_path.write_text("\n".join(lines) + "\n")

    result = web_server_module._read_conversations()

    assert len(result) == 2
    assert result[0]["conversation_id"] == "conv-new"
    assert result[1]["conversation_id"] == "conv-old"


def test_read_conversations_updates_with_message_timestamps(
    web_server_module: types.ModuleType,
) -> None:
    conv_path = web_server_module.CONVERSATIONS_EVENTS_PATH
    conv_path.parent.mkdir(parents=True, exist_ok=True)
    conv_path.write_text(
        json.dumps(
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "conversation_id": "conv-1",
                "model": "m",
                "type": "conversation_created",
                "event_id": "e1",
                "source": "conversations",
            }
        )
        + "\n"
    )
    msg_path = web_server_module.MESSAGES_EVENTS_PATH
    msg_path.parent.mkdir(parents=True, exist_ok=True)
    msg_path.write_text(
        json.dumps(
            {
                "timestamp": "2026-03-01T00:00:00Z",
                "conversation_id": "conv-1",
                "role": "user",
                "content": "hello",
                "type": "message",
                "event_id": "e2",
                "source": "messages",
            }
        )
        + "\n"
    )

    result = web_server_module._read_conversations()
    assert result[0]["updated_at"] == "2026-03-01T00:00:00Z"


def test_read_conversations_skips_malformed_lines(web_server_module: types.ModuleType) -> None:
    events_path = web_server_module.CONVERSATIONS_EVENTS_PATH
    events_path.parent.mkdir(parents=True, exist_ok=True)
    events_path.write_text(
        "not valid json\n"
        + json.dumps(
            {
                "timestamp": "2026-01-01T00:00:00Z",
                "conversation_id": "conv-good",
                "model": "m",
                "type": "conversation_created",
                "event_id": "e1",
                "source": "conversations",
            }
        )
        + "\n"
    )

    result = web_server_module._read_conversations()

    assert len(result) == 1
    assert result[0]["conversation_id"] == "conv-good"


# -- _detect_ttyd_port tests --


def test_detect_ttyd_port_extracts_port_from_stderr(web_server_module: types.ModuleType) -> None:
    process_stub = SimpleNamespace(
        stderr=io.BytesIO(b"[INFO] Listening on port: 12345\n"),
        poll=lambda: None,
    )
    result = web_server_module._detect_ttyd_port(process_stub)
    assert result == 12345


def test_detect_ttyd_port_returns_none_when_process_exits(
    web_server_module: types.ModuleType,
) -> None:
    process_stub = SimpleNamespace(
        stderr=io.BytesIO(b""),
        poll=lambda: 1,
    )
    result = web_server_module._detect_ttyd_port(process_stub)
    assert result is None


def test_detect_ttyd_port_ignores_non_port_lines(web_server_module: types.ModuleType) -> None:
    process_stub = SimpleNamespace(
        stderr=io.BytesIO(b"[INFO] Starting server\n[INFO] Listening on port: 9999\n"),
        poll=lambda: None,
    )
    result = web_server_module._detect_ttyd_port(process_stub)
    assert result == 9999


# -- _register_server tests --


def test_register_server_appends_to_jsonl(web_server_module: types.ModuleType) -> None:
    web_server_module._register_server("web", 8080)

    content = web_server_module.SERVERS_JSONL_PATH.read_text()
    record = json.loads(content.strip())
    assert record["server"] == "web"
    assert record["url"] == "http://127.0.0.1:8080"


def test_register_server_appends_multiple(web_server_module: types.ModuleType) -> None:
    web_server_module._register_server("web", 8080)
    web_server_module._register_server("chat", 9090)

    lines = web_server_module.SERVERS_JSONL_PATH.read_text().strip().splitlines()
    assert len(lines) == 2


def test_register_server_does_nothing_when_path_is_none(
    web_server_module: types.ModuleType,
) -> None:
    original = web_server_module.SERVERS_JSONL_PATH
    web_server_module.SERVERS_JSONL_PATH = None
    try:
        web_server_module._register_server("web", 8080)
    finally:
        web_server_module.SERVERS_JSONL_PATH = original


# -- _TtydEntry tests --


def test_ttyd_entry_is_alive_when_process_running(web_server_module: types.ModuleType) -> None:
    process_stub = _make_process_stub(is_alive=True)
    entry = web_server_module._TtydEntry(process=process_stub, port=1234)
    assert entry.is_alive() is True


def test_ttyd_entry_is_not_alive_when_process_exited(web_server_module: types.ModuleType) -> None:
    process_stub = _make_process_stub(is_alive=False)
    entry = web_server_module._TtydEntry(process=process_stub, port=1234)
    assert entry.is_alive() is False


# -- HTTP handler tests --


def test_handler_class_has_get_and_post_methods(web_server_module: types.ModuleType) -> None:
    handler = web_server_module._WebServerHandler
    assert hasattr(handler, "do_GET")
    assert hasattr(handler, "do_POST")


# -- Template rendering tests --


def test_main_page_html_contains_conversation_dropdown(
    web_server_module: types.ModuleType,
) -> None:
    rendered = web_server_module._MAIN_PAGE_HTML.format(agent_name="TestAgent")
    assert "conv-select" in rendered
    assert "TestAgent" in rendered
    assert "All Agents" in rendered
    assert "agents-page" in rendered


def test_agents_page_html_contains_agent_list(web_server_module: types.ModuleType) -> None:
    rendered = web_server_module._AGENTS_PAGE_HTML.format(agent_name="TestAgent")
    assert "agent-list" in rendered
    assert "TestAgent" in rendered
    assert "Back to Conversations" in rendered


def test_main_page_uses_post_for_ensure_endpoints(
    web_server_module: types.ModuleType,
) -> None:
    rendered = web_server_module._MAIN_PAGE_HTML.format(agent_name="Test")
    assert "method: 'POST'" in rendered


def test_agents_page_uses_post_for_ensure_endpoints(
    web_server_module: types.ModuleType,
) -> None:
    rendered = web_server_module._AGENTS_PAGE_HTML.format(agent_name="Test")
    assert "method: 'POST'" in rendered


# -- Shell quoting tests --


def test_ensure_conversation_ttyd_returns_none_when_no_chat_script(
    web_server_module: types.ModuleType,
) -> None:
    original = web_server_module.CHAT_SCRIPT_PATH
    web_server_module.CHAT_SCRIPT_PATH = None
    try:
        result = web_server_module._ensure_conversation_ttyd("conv-abc-123")
        assert result is None
    finally:
        web_server_module.CHAT_SCRIPT_PATH = original


# -- _start_ttyd_for_command internal logic tests --
#
# These tests exercise the dict management, sentinel, and limit logic
# without actually spawning ttyd. They rely on ttyd not being available
# (or use a nonexistent binary) so the function fails at the Popen stage,
# allowing us to verify cleanup behavior.


def test_start_ttyd_reuses_alive_entry(web_server_module: types.ModuleType) -> None:
    """Verify that an existing alive ttyd is reused without spawning a new one."""
    process_stub = _make_process_stub(is_alive=True)
    alive_entry = web_server_module._TtydEntry(process=process_stub, port=7777)
    web_server_module._ttyd_by_server_name["test-reuse-72941"] = alive_entry

    try:
        result = web_server_module._start_ttyd_for_command("test-reuse-72941", ["bash"])
        assert result is alive_entry
    finally:
        web_server_module._ttyd_by_server_name.pop("test-reuse-72941", None)


def test_start_ttyd_removes_dead_entry_before_spawn(
    web_server_module: types.ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that a dead entry is removed when a new spawn is attempted."""
    process_stub = _make_process_stub(is_alive=False)
    dead_entry = web_server_module._TtydEntry(process=process_stub, port=5555)
    web_server_module._ttyd_by_server_name["test-dead-81723"] = dead_entry

    # Ensure ttyd is not found so Popen fails with FileNotFoundError
    monkeypatch.setenv("PATH", "")

    try:
        result = web_server_module._start_ttyd_for_command("test-dead-81723", ["bash"])
        assert result is None
        assert "test-dead-81723" not in web_server_module._ttyd_by_server_name
    finally:
        web_server_module._ttyd_by_server_name.pop("test-dead-81723", None)


def test_start_ttyd_enforces_max_limit(web_server_module: types.ModuleType) -> None:
    """Verify that the MAX_TTYD_PROCESSES limit is enforced."""
    original_max = web_server_module.MAX_TTYD_PROCESSES
    web_server_module.MAX_TTYD_PROCESSES = 2

    try:
        for i in range(2):
            process_stub = _make_process_stub(is_alive=True)
            web_server_module._ttyd_by_server_name[f"limit-test-{i}-39182"] = web_server_module._TtydEntry(
                process=process_stub, port=5000 + i
            )

        result = web_server_module._start_ttyd_for_command("over-limit-39182", ["bash"])
        assert result is None
    finally:
        web_server_module.MAX_TTYD_PROCESSES = original_max
        for i in range(2):
            web_server_module._ttyd_by_server_name.pop(f"limit-test-{i}-39182", None)
        web_server_module._ttyd_by_server_name.pop("over-limit-39182", None)


def test_start_ttyd_cleans_dead_before_limit_check(
    web_server_module: types.ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that dead entries are cleaned up before checking the limit."""
    original_max = web_server_module.MAX_TTYD_PROCESSES
    web_server_module.MAX_TTYD_PROCESSES = 2

    monkeypatch.setenv("PATH", "")

    try:
        alive_stub = _make_process_stub(is_alive=True)
        dead_stub = _make_process_stub(is_alive=False)
        web_server_module._ttyd_by_server_name["alive-48291"] = web_server_module._TtydEntry(
            process=alive_stub, port=5000
        )
        web_server_module._ttyd_by_server_name["dead-48291"] = web_server_module._TtydEntry(
            process=dead_stub, port=5001
        )

        # Should proceed past the limit (1 alive < 2 max) after cleaning dead
        web_server_module._start_ttyd_for_command("new-48291", ["bash"])

        assert "dead-48291" not in web_server_module._ttyd_by_server_name
    finally:
        web_server_module.MAX_TTYD_PROCESSES = original_max
        web_server_module._ttyd_by_server_name.pop("alive-48291", None)
        web_server_module._ttyd_by_server_name.pop("dead-48291", None)
        web_server_module._ttyd_by_server_name.pop("new-48291", None)


def test_start_ttyd_sentinel_prevents_duplicate_spawn(
    web_server_module: types.ModuleType,
) -> None:
    """Verify that a spawning sentinel prevents a second spawn for the same name."""
    web_server_module._ttyd_by_server_name["sentinel-test-57193"] = web_server_module._SPAWNING_SENTINEL

    try:
        result = web_server_module._start_ttyd_for_command("sentinel-test-57193", ["bash"])
        assert result is None
    finally:
        web_server_module._ttyd_by_server_name.pop("sentinel-test-57193", None)


def test_start_ttyd_clears_sentinel_on_spawn_failure(
    web_server_module: types.ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that the sentinel is removed if Popen fails."""
    monkeypatch.setenv("PATH", "")

    result = web_server_module._start_ttyd_for_command("fail-63841", ["bash"])

    assert result is None
    assert "fail-63841" not in web_server_module._ttyd_by_server_name
