"""Unit tests for the mng_claude_zygote provisioning module."""

from pathlib import Path
from typing import Any
from typing import cast

import pytest

from imbue.mng_claude_zygote.data_types import ChatModel
from imbue.mng_claude_zygote.provisioning import _LLM_TOOL_FILES
from imbue.mng_claude_zygote.provisioning import _SCRIPT_FILES
from imbue.mng_claude_zygote.provisioning import compute_claude_project_dir_name
from imbue.mng_claude_zygote.provisioning import create_changeling_symlinks
from imbue.mng_claude_zygote.provisioning import create_event_log_directories
from imbue.mng_claude_zygote.provisioning import install_llm_toolchain
from imbue.mng_claude_zygote.provisioning import link_memory_directory
from imbue.mng_claude_zygote.provisioning import load_zygote_resource
from imbue.mng_claude_zygote.provisioning import provision_changeling_scripts
from imbue.mng_claude_zygote.provisioning import provision_llm_tools
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


def test_chat_script_uses_uv_run_python() -> None:
    """Verify list_conversations uses 'uv run python3' instead of bare 'python3'."""
    content = load_zygote_resource("chat.sh")
    assert "uv run python3" in content


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


def test_event_watcher_watches_entrypoint_events() -> None:
    content = load_zygote_resource("event_watcher.sh")
    assert "entrypoint/events.jsonl" in content


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

    for source in ("conversations", "messages", "entrypoint", "transcript"):
        assert any(source in c and "mkdir" in c for c in host.executed_commands), f"Missing mkdir for {source}"


def test_write_default_chat_model_writes_model_to_file() -> None:
    host = _StubHost()
    write_default_chat_model(cast(Any, host), Path("/tmp/mng-test/agents/agent-123"), ChatModel("claude-sonnet-4-6"))

    assert len(host.written_text_files) == 1
    path, content = host.written_text_files[0]
    assert "claude-sonnet-4-6" in content
    assert str(path).endswith("default_chat_model")
