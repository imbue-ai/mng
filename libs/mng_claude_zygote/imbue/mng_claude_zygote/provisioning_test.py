"""Unit tests for the mng_claude_zygote provisioning module."""

from pathlib import Path
from typing import Any
from typing import cast

import pytest

from imbue.mng_claude_zygote.data_types import ChatModel
from imbue.mng_claude_zygote.provisioning import _LLM_TOOL_FILES
from imbue.mng_claude_zygote.provisioning import _SCRIPT_FILES
from imbue.mng_claude_zygote.provisioning import _is_recursive_plugin_registered
from imbue.mng_claude_zygote.provisioning import compute_claude_project_dir_name
from imbue.mng_claude_zygote.provisioning import create_changeling_symlinks
from imbue.mng_claude_zygote.provisioning import create_event_log_directories
from imbue.mng_claude_zygote.provisioning import install_llm_toolchain
from imbue.mng_claude_zygote.provisioning import link_memory_directory
from imbue.mng_claude_zygote.provisioning import load_zygote_resource
from imbue.mng_claude_zygote.provisioning import provision_changeling_scripts
from imbue.mng_claude_zygote.provisioning import provision_llm_tools
from imbue.mng_claude_zygote.provisioning import warn_if_mng_unavailable
from imbue.mng_claude_zygote.provisioning import write_default_chat_model


class _StubCommandResult:
    """Concrete test double for command execution results."""

    def __init__(self, *, success: bool = True, stderr: str = "", stdout: str = "") -> None:
        self.success = success
        self.stderr = stderr
        self.stdout = stdout


class _StubHost:
    """Concrete test double for OnlineHostInterface that records operations.

    Records all execute_command calls and write_file/write_text_file calls
    for assertion in tests.
    """

    def __init__(
        self,
        host_dir: Path = Path("/tmp/mng-test/host"),
        command_results: dict[str, _StubCommandResult] | None = None,
    ) -> None:
        self.host_dir = host_dir
        self.executed_commands: list[str] = []
        self.written_files: list[tuple[Path, bytes, str]] = []
        self.written_text_files: list[tuple[Path, str]] = []
        self._command_results = command_results or {}

    def execute_command(self, command: str, **kwargs: Any) -> _StubCommandResult:
        self.executed_commands.append(command)
        for pattern, result in self._command_results.items():
            if pattern in command:
                return result
        # For `cd <path> && pwd`, return the path as stdout
        if "&& pwd" in command and "cd " in command:
            path = command.split("cd ")[1].split(" &&")[0].strip("'\"")
            return _StubCommandResult(stdout=path + "\n")
        return _StubCommandResult()

    def write_file(self, path: Path, content: bytes, mode: str = "0644") -> None:
        self.written_files.append((path, content, mode))

    def write_text_file(self, path: Path, content: str) -> None:
        self.written_text_files.append((path, content))


# -- Resource loading tests --


def test_load_zygote_resource_loads_chat_script() -> None:
    content = load_zygote_resource("chat.sh")
    assert "#!/bin/bash" in content
    assert "chat" in content.lower()


def test_load_zygote_resource_loads_conversation_watcher() -> None:
    content = load_zygote_resource("conversation_watcher.sh")
    assert "#!/bin/bash" in content
    assert "conversation" in content.lower()


def test_load_zygote_resource_loads_event_watcher() -> None:
    content = load_zygote_resource("event_watcher.sh")
    assert "#!/bin/bash" in content
    assert "event" in content.lower()


def test_all_declared_script_files_are_loadable() -> None:
    for script_name in _SCRIPT_FILES:
        content = load_zygote_resource(script_name)
        assert content, f"{script_name} is empty"
        assert "#!/bin/bash" in content, f"{script_name} missing shebang"


def test_all_declared_llm_tool_files_are_loadable() -> None:
    for tool_file in _LLM_TOOL_FILES:
        content = load_zygote_resource(tool_file)
        assert content, f"{tool_file} is empty"
        assert "def " in content, f"{tool_file} missing function definition"


# -- Chat script content tests --


def test_chat_script_supports_new_flag() -> None:
    content = load_zygote_resource("chat.sh")
    assert "--new" in content


def test_chat_script_supports_resume_flag() -> None:
    content = load_zygote_resource("chat.sh")
    assert "--resume" in content


def test_chat_script_supports_as_agent_flag() -> None:
    content = load_zygote_resource("chat.sh")
    assert "--as-agent" in content


def test_chat_script_invokes_llm_live_chat() -> None:
    content = load_zygote_resource("chat.sh")
    assert "llm live-chat" in content


def test_chat_script_invokes_llm_inject() -> None:
    content = load_zygote_resource("chat.sh")
    assert "llm inject" in content


def test_chat_script_writes_conversations_jsonl() -> None:
    content = load_zygote_resource("chat.sh")
    assert "conversations/events.jsonl" in content


def test_chat_script_uses_mng_agent_state_dir() -> None:
    content = load_zygote_resource("chat.sh")
    assert "MNG_AGENT_STATE_DIR" in content


def test_chat_script_passes_llm_tool_functions() -> None:
    content = load_zygote_resource("chat.sh")
    assert "--functions" in content
    assert "llm_tools" in content


def test_chat_script_supports_list_flag() -> None:
    content = load_zygote_resource("chat.sh")
    assert "--list" in content


def test_chat_script_supports_help_flag() -> None:
    content = load_zygote_resource("chat.sh")
    assert "--help" in content


def test_chat_script_uses_jq_not_python_for_json_parsing() -> None:
    """Verify resume uses jq instead of python for single-value JSON extraction."""
    content = load_zygote_resource("chat.sh")
    # resume_conversation should use jq
    assert "jq -r" in content


def test_chat_script_uses_nanosecond_timestamps() -> None:
    """Verify timestamps include nanosecond precision."""
    content = load_zygote_resource("chat.sh")
    assert "%N" in content


def test_chat_script_reports_malformed_lines() -> None:
    """Verify list_conversations reports malformed lines instead of silently skipping."""
    content = load_zygote_resource("chat.sh")
    assert "WARNING" in content or "malformed" in content


def test_chat_script_logs_to_file() -> None:
    """Verify chat.sh writes debug output to a log file."""
    content = load_zygote_resource("chat.sh")
    assert "LOG_FILE" in content
    assert "chat.log" in content


# -- Conversation watcher content tests --


def test_conversation_watcher_queries_sqlite() -> None:
    content = load_zygote_resource("conversation_watcher.sh")
    assert "sqlite3" in content


def test_conversation_watcher_writes_to_messages_events() -> None:
    content = load_zygote_resource("conversation_watcher.sh")
    assert "messages/events.jsonl" in content


def test_conversation_watcher_logs_to_file() -> None:
    """Verify conversation_watcher.sh writes debug output to a log file."""
    content = load_zygote_resource("conversation_watcher.sh")
    assert "LOG_FILE" in content
    assert "conversation_watcher.log" in content


def test_conversation_watcher_logs_sqlite_errors() -> None:
    """Verify conversation_watcher.sh captures and logs sqlite3 errors."""
    content = load_zygote_resource("conversation_watcher.sh")
    assert "query_stderr" in content or "WARNING" in content


def test_conversation_watcher_supports_inotifywait() -> None:
    content = load_zygote_resource("conversation_watcher.sh")
    assert "inotifywait" in content


# -- Event watcher content tests --


def test_event_watcher_sends_mng_message() -> None:
    content = load_zygote_resource("event_watcher.sh")
    assert "mng message" in content


def test_event_watcher_watches_messages_events() -> None:
    content = load_zygote_resource("event_watcher.sh")
    assert "messages/events.jsonl" in content


def test_event_watcher_watches_scheduled_events() -> None:
    content = load_zygote_resource("event_watcher.sh")
    assert "scheduled" in content


def test_event_watcher_watches_mng_agents_events() -> None:
    content = load_zygote_resource("event_watcher.sh")
    assert "mng_agents" in content


def test_event_watcher_watches_stop_events() -> None:
    content = load_zygote_resource("event_watcher.sh")
    assert "stop" in content


def test_event_watcher_tracks_offsets() -> None:
    content = load_zygote_resource("event_watcher.sh")
    assert "offset" in content.lower()


def test_event_watcher_supports_inotifywait() -> None:
    content = load_zygote_resource("event_watcher.sh")
    assert "inotifywait" in content


def test_event_watcher_logs_to_file() -> None:
    """Verify event_watcher.sh writes debug output to a log file."""
    content = load_zygote_resource("event_watcher.sh")
    assert "LOG_FILE" in content
    assert "event_watcher.log" in content


def test_event_watcher_logs_send_errors() -> None:
    """Verify event_watcher.sh captures and logs mng message errors."""
    content = load_zygote_resource("event_watcher.sh")
    assert "send_stderr" in content or "ERROR" in content


# -- LLM tool content tests --


def test_context_tool_defines_gather_context() -> None:
    content = load_zygote_resource("context_tool.py")
    assert "def gather_context" in content


def test_context_tool_has_docstring_for_llm() -> None:
    content = load_zygote_resource("context_tool.py")
    assert '"""' in content


def test_context_tool_has_return_type_annotation() -> None:
    content = load_zygote_resource("context_tool.py")
    assert "-> str" in content


def test_extra_context_tool_defines_gather_extra_context() -> None:
    content = load_zygote_resource("extra_context_tool.py")
    assert "def gather_extra_context" in content


def test_extra_context_tool_calls_mng_list() -> None:
    content = load_zygote_resource("extra_context_tool.py")
    assert "mng" in content
    assert "list" in content


# -- Memory linker content tests --


def test_compute_claude_project_dir_name_replaces_slashes() -> None:
    assert compute_claude_project_dir_name("/home/user/project") == "-home-user-project"


def test_compute_claude_project_dir_name_replaces_dots() -> None:
    assert compute_claude_project_dir_name("/home/user/.changelings/agent") == "-home-user--changelings-agent"


def test_link_memory_directory_creates_changelings_memory_dir() -> None:
    host = _StubHost()
    link_memory_directory(cast(Any, host), Path("/home/user/.changelings/agent"), ".changelings")

    assert any("mkdir" in c and ".changelings/memory" in c for c in host.executed_commands)


def test_link_memory_directory_creates_claude_project_dir_with_home_var() -> None:
    host = _StubHost()
    link_memory_directory(cast(Any, host), Path("/home/user/.changelings/agent"), ".changelings")

    # Must use $HOME (not ~) so tilde expansion works inside quotes
    mkdir_cmds = [c for c in host.executed_commands if "mkdir" in c and ".claude/projects" in c]
    assert len(mkdir_cmds) == 1
    assert "$HOME" in mkdir_cmds[0]
    assert "-home-user--changelings-agent" in mkdir_cmds[0]


def test_link_memory_directory_creates_symlink_with_correct_paths() -> None:
    host = _StubHost()
    link_memory_directory(cast(Any, host), Path("/home/user/.changelings/agent"), ".changelings")

    ln_cmds = [c for c in host.executed_commands if "ln -sfn" in c]
    assert len(ln_cmds) == 1
    # Symlink target should be the changelings memory dir
    assert ".changelings/memory" in ln_cmds[0]
    # Symlink source should use $HOME for the Claude project dir
    assert "$HOME/.claude/projects/" in ln_cmds[0]
    assert "-home-user--changelings-agent" in ln_cmds[0]


def test_link_memory_directory_does_not_use_literal_tilde() -> None:
    """Verify that ~ is never used in paths (it doesn't expand inside single quotes)."""
    host = _StubHost()
    link_memory_directory(cast(Any, host), Path("/home/user/project"), ".changelings")

    for cmd in host.executed_commands:
        if ".claude/projects" in cmd:
            assert "~" not in cmd, f"Found literal ~ in command (won't expand in quotes): {cmd}"


# -- Provisioning function tests (using _StubHost) --


def test_install_llm_toolchain_skips_when_already_present() -> None:
    host = _StubHost()
    install_llm_toolchain(cast(Any, host))

    assert any("command -v llm" in c for c in host.executed_commands)
    assert not any("uv tool install llm" in c for c in host.executed_commands)


def test_install_llm_toolchain_installs_when_missing() -> None:
    host = _StubHost(command_results={"command -v llm": _StubCommandResult(success=False)})
    install_llm_toolchain(cast(Any, host))

    assert any("uv tool install llm" in c for c in host.executed_commands)


def test_install_llm_toolchain_installs_anthropic_plugin() -> None:
    host = _StubHost()
    install_llm_toolchain(cast(Any, host))

    assert any("llm install llm-anthropic" in c for c in host.executed_commands)


def test_install_llm_toolchain_installs_live_chat_plugin() -> None:
    host = _StubHost()
    install_llm_toolchain(cast(Any, host))

    assert any("llm install llm-live-chat" in c for c in host.executed_commands)


def test_install_llm_toolchain_raises_on_llm_install_failure() -> None:
    host = _StubHost(
        command_results={
            "command -v llm": _StubCommandResult(success=False),
            "uv tool install llm": _StubCommandResult(success=False, stderr="install failed"),
        }
    )
    with pytest.raises(RuntimeError, match="Failed to install llm"):
        install_llm_toolchain(cast(Any, host))


def test_install_llm_toolchain_raises_on_plugin_install_failure() -> None:
    host = _StubHost(
        command_results={"llm install llm-anthropic": _StubCommandResult(success=False, stderr="plugin failed")}
    )
    with pytest.raises(RuntimeError, match="Failed to install llm-anthropic"):
        install_llm_toolchain(cast(Any, host))


def test_create_changeling_symlinks_checks_entrypoint_md() -> None:
    host = _StubHost()
    create_changeling_symlinks(cast(Any, host), Path("/test/work"), ".changelings")

    assert any("entrypoint.md" in c for c in host.executed_commands)


def test_create_changeling_symlinks_checks_entrypoint_json() -> None:
    host = _StubHost()
    create_changeling_symlinks(cast(Any, host), Path("/test/work"), ".changelings")

    assert any("entrypoint.json" in c for c in host.executed_commands)


def test_create_changeling_symlinks_creates_claude_local_md() -> None:
    host = _StubHost()
    create_changeling_symlinks(cast(Any, host), Path("/test/work"), ".changelings")

    assert any("ln -sf" in c and "CLAUDE.local.md" in c for c in host.executed_commands)


def test_provision_changeling_scripts_creates_commands_dir() -> None:
    host = _StubHost()
    provision_changeling_scripts(cast(Any, host))

    assert any("mkdir" in c and "commands" in c for c in host.executed_commands)


def test_provision_changeling_scripts_writes_all_scripts() -> None:
    host = _StubHost()
    provision_changeling_scripts(cast(Any, host))

    written_names = [str(path) for path, _, _ in host.written_files]
    for script_name in _SCRIPT_FILES:
        assert any(script_name in name for name in written_names), f"{script_name} not written"


def test_provision_changeling_scripts_uses_executable_mode() -> None:
    host = _StubHost()
    provision_changeling_scripts(cast(Any, host))

    for _, _, mode in host.written_files:
        assert mode == "0755"


def test_provision_llm_tools_creates_tools_dir() -> None:
    host = _StubHost()
    provision_llm_tools(cast(Any, host))

    assert any("mkdir" in c and "llm_tools" in c for c in host.executed_commands)


def test_provision_llm_tools_writes_all_tool_files() -> None:
    host = _StubHost()
    provision_llm_tools(cast(Any, host))

    written_names = [str(path) for path, _, _ in host.written_files]
    for tool_file in _LLM_TOOL_FILES:
        assert any(tool_file in name for name in written_names), f"{tool_file} not written"


def test_create_event_log_directories_creates_all_source_dirs() -> None:
    host = _StubHost()
    create_event_log_directories(cast(Any, host), Path("/tmp/mng-test/agents/agent-123"))

    for source in ("conversations", "messages", "scheduled", "mng_agents", "stop", "monitor", "claude_transcript"):
        assert any(source in c and "mkdir" in c for c in host.executed_commands), f"Missing mkdir for {source}"


def test_write_default_chat_model_writes_model_to_file() -> None:
    host = _StubHost()
    write_default_chat_model(cast(Any, host), Path("/tmp/mng-test/agents/agent-123"), ChatModel("claude-sonnet-4-6"))

    assert len(host.written_text_files) == 1
    path, content = host.written_text_files[0]
    assert "claude-sonnet-4-6" in content
    assert str(path).endswith("default_chat_model")


# -- mng availability check tests --


def _make_fake_pm(plugins: list[tuple[str, object]]) -> Any:
    """Create a fake PluginManager that returns the given plugin list."""

    class _FakePM:
        def list_name_plugin(self) -> list[tuple[str, object]]:
            return plugins

    return cast(Any, _FakePM())


def test_warn_if_mng_unavailable_skips_on_local_host() -> None:
    host = _StubHost()
    host.is_local = True  # type: ignore[attr-defined]

    warn_if_mng_unavailable(cast(Any, host), _make_fake_pm([]))

    assert not any("command -v mng" in c for c in host.executed_commands)


def test_warn_if_mng_unavailable_skips_when_recursive_plugin_registered() -> None:
    host = _StubHost()
    host.is_local = False  # type: ignore[attr-defined]

    warn_if_mng_unavailable(cast(Any, host), _make_fake_pm([("recursive_mng", object())]))

    assert not any("command -v mng" in c for c in host.executed_commands)


def test_warn_if_mng_unavailable_checks_on_remote_without_recursive() -> None:
    host = _StubHost()
    host.is_local = False  # type: ignore[attr-defined]

    warn_if_mng_unavailable(cast(Any, host), _make_fake_pm([("some_other_plugin", object())]))

    assert any("command -v mng" in c for c in host.executed_commands)


def test_is_recursive_plugin_registered_returns_true_when_present() -> None:
    assert _is_recursive_plugin_registered(_make_fake_pm([("recursive_mng", object())])) is True


def test_is_recursive_plugin_registered_returns_false_when_absent() -> None:
    assert _is_recursive_plugin_registered(_make_fake_pm([("some_plugin", object())])) is False


# -- context_tool incremental behavior tests --


def _load_fresh_context_tool(name: str) -> Any:
    """Load a fresh instance of context_tool.py with clean state."""
    import importlib

    spec = importlib.util.spec_from_file_location(
        name,
        Path(__file__).parent / "resources" / "context_tool.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_context_tool_gather_context_returns_no_context_when_env_not_set(tmp_path: Path) -> None:
    """Verify gather_context returns a message when MNG_AGENT_STATE_DIR is not set."""
    import os

    module = _load_fresh_context_tool("context_tool_test_module")

    old_val = os.environ.pop("MNG_AGENT_STATE_DIR", None)
    try:
        result = module.gather_context()
        assert "No agent data directory" in result
    finally:
        if old_val is not None:
            os.environ["MNG_AGENT_STATE_DIR"] = old_val


def test_context_tool_gather_context_returns_no_new_context_on_second_call(tmp_path: Path) -> None:
    """Verify gather_context returns incremental results on subsequent calls."""
    import os

    # Set up a minimal agent data dir with one scheduled event
    logs_dir = tmp_path / "logs" / "scheduled"
    logs_dir.mkdir(parents=True)
    events_file = logs_dir / "events.jsonl"
    events_file.write_text('{"timestamp":"2026-01-01T00:00:00Z","type":"test","event_id":"e1","source":"scheduled"}\n')

    module = _load_fresh_context_tool("context_tool_incremental_test")

    old_val = os.environ.get("MNG_AGENT_STATE_DIR")
    os.environ["MNG_AGENT_STATE_DIR"] = str(tmp_path)
    try:
        # First call: should return the event
        first_result = module.gather_context()
        assert "scheduled" in first_result.lower()

        # Second call with no new events: should report no new context
        second_result = module.gather_context()
        assert "No new context" in second_result
    finally:
        if old_val is not None:
            os.environ["MNG_AGENT_STATE_DIR"] = old_val
        else:
            os.environ.pop("MNG_AGENT_STATE_DIR", None)


def _make_event_line(event_id: str, source: str = "test") -> str:
    return f'{{"timestamp":"2026-01-01T00:00:00Z","type":"test","event_id":"{event_id}","source":"{source}"}}'


def test_read_tail_lines_returns_last_n_lines(tmp_path: Path) -> None:
    """Verify _read_tail_lines returns only the last N complete lines."""
    module = _load_fresh_context_tool("tail_last_n")
    f = tmp_path / "events.jsonl"
    lines = [_make_event_line(f"e{i}") for i in range(20)]
    f.write_text("\n".join(lines) + "\n")

    result = module._read_tail_lines(f, 5)
    assert len(result) == 5
    for i, line in enumerate(result):
        assert f'"event_id":"e{15 + i}"' in line


def test_read_tail_lines_drops_incomplete_last_line(tmp_path: Path) -> None:
    """Verify _read_tail_lines drops the last line when it lacks a trailing newline."""
    module = _load_fresh_context_tool("tail_incomplete")
    f = tmp_path / "events.jsonl"
    complete = _make_event_line("complete")
    incomplete = '{"partial":"data_no_newline'
    f.write_text(complete + "\n" + incomplete)

    result = module._read_tail_lines(f, 5)
    assert len(result) == 1
    assert "complete" in result[0]
    assert "partial" not in result[0]


def test_read_tail_lines_handles_empty_file(tmp_path: Path) -> None:
    """Verify _read_tail_lines returns empty list for an empty file."""
    module = _load_fresh_context_tool("tail_empty")
    f = tmp_path / "events.jsonl"
    f.write_text("")

    result = module._read_tail_lines(f, 5)
    assert result == []


def test_read_tail_lines_handles_missing_file(tmp_path: Path) -> None:
    """Verify _read_tail_lines returns empty list for a nonexistent file."""
    module = _load_fresh_context_tool("tail_missing")
    f = tmp_path / "nonexistent.jsonl"

    result = module._read_tail_lines(f, 5)
    assert result == []


def test_read_tail_lines_returns_all_when_fewer_than_n(tmp_path: Path) -> None:
    """Verify _read_tail_lines returns all lines when fewer than N exist."""
    module = _load_fresh_context_tool("tail_fewer")
    f = tmp_path / "events.jsonl"
    lines = [_make_event_line(f"e{i}") for i in range(3)]
    f.write_text("\n".join(lines) + "\n")

    result = module._read_tail_lines(f, 10)
    assert len(result) == 3


def test_read_tail_lines_file_only_incomplete_line(tmp_path: Path) -> None:
    """Verify _read_tail_lines returns empty when file has only an incomplete line."""
    module = _load_fresh_context_tool("tail_only_incomplete")
    f = tmp_path / "events.jsonl"
    f.write_text("partial data no newline")

    result = module._read_tail_lines(f, 5)
    assert result == []


def test_get_new_lines_returns_appended_data(tmp_path: Path) -> None:
    """Verify _get_new_lines returns lines appended after a _read_tail_lines call."""
    module = _load_fresh_context_tool("new_lines_append")
    f = tmp_path / "events.jsonl"
    f.write_text(_make_event_line("e1") + "\n")

    # Prime the offset via _read_tail_lines
    module._read_tail_lines(f, 5)

    # Append new data
    with f.open("a") as fh:
        fh.write(_make_event_line("e2") + "\n")

    result = module._get_new_lines(f)
    assert len(result) == 1
    assert '"event_id":"e2"' in result[0]


def test_get_new_lines_drops_incomplete_appended_line(tmp_path: Path) -> None:
    """Verify _get_new_lines skips an incomplete trailing line."""
    module = _load_fresh_context_tool("new_lines_incomplete")
    f = tmp_path / "events.jsonl"
    f.write_text(_make_event_line("e1") + "\n")

    module._read_tail_lines(f, 5)

    # Append one complete line and one incomplete
    with f.open("a") as fh:
        fh.write(_make_event_line("e2") + "\n")
        fh.write("incomplete")

    result = module._get_new_lines(f)
    assert len(result) == 1
    assert '"event_id":"e2"' in result[0]

    # Now "complete" the incomplete line
    with f.open("a") as fh:
        fh.write("_data\n")

    result2 = module._get_new_lines(f)
    assert len(result2) == 1
    assert "incomplete_data" in result2[0]


def test_get_new_lines_returns_empty_when_no_new_data(tmp_path: Path) -> None:
    """Verify _get_new_lines returns empty when file hasn't changed."""
    module = _load_fresh_context_tool("new_lines_no_change")
    f = tmp_path / "events.jsonl"
    f.write_text(_make_event_line("e1") + "\n")

    module._read_tail_lines(f, 5)

    result = module._get_new_lines(f)
    assert result == []
