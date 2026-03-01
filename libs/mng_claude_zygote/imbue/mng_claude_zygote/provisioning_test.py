"""Unit tests for the mng_claude_zygote provisioning module."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from imbue.mng_claude_zygote.data_types import ChatModel
from imbue.mng_claude_zygote.provisioning import _LLM_TOOL_FILES
from imbue.mng_claude_zygote.provisioning import _SCRIPT_FILES
from imbue.mng_claude_zygote.provisioning import create_changeling_symlinks
from imbue.mng_claude_zygote.provisioning import create_conversation_directories
from imbue.mng_claude_zygote.provisioning import install_llm_toolchain
from imbue.mng_claude_zygote.provisioning import load_zygote_resource
from imbue.mng_claude_zygote.provisioning import provision_changeling_scripts
from imbue.mng_claude_zygote.provisioning import provision_llm_tools
from imbue.mng_claude_zygote.provisioning import write_default_chat_model


class TestLoadZygoteResource:
    def test_loads_chat_script(self) -> None:
        """Verify that chat.sh can be loaded as a resource."""
        content = load_zygote_resource("chat.sh")
        assert "#!/bin/bash" in content
        assert "chat" in content.lower()

    def test_loads_conversation_watcher(self) -> None:
        """Verify that conversation_watcher.sh can be loaded."""
        content = load_zygote_resource("conversation_watcher.sh")
        assert "#!/bin/bash" in content
        assert "conversation" in content.lower()

    def test_loads_event_watcher(self) -> None:
        """Verify that event_watcher.sh can be loaded."""
        content = load_zygote_resource("event_watcher.sh")
        assert "#!/bin/bash" in content
        assert "event" in content.lower()

    def test_loads_memory_linker(self) -> None:
        """Verify that memory_linker.sh can be loaded."""
        content = load_zygote_resource("memory_linker.sh")
        assert "#!/bin/bash" in content
        assert "memory" in content.lower()


class TestResourceScripts:
    def test_all_script_files_are_loadable(self) -> None:
        """Verify that all declared script files exist and can be loaded."""
        for script_name in _SCRIPT_FILES:
            content = load_zygote_resource(script_name)
            assert content, f"{script_name} is empty"
            assert "#!/bin/bash" in content, f"{script_name} missing shebang"

    def test_all_llm_tool_files_are_loadable(self) -> None:
        """Verify that all declared LLM tool files exist and can be loaded."""
        for tool_file in _LLM_TOOL_FILES:
            content = load_zygote_resource(tool_file)
            assert content, f"{tool_file} is empty"
            assert "def " in content, f"{tool_file} missing function definition"


class TestChatScriptContent:
    def test_chat_script_has_new_flag(self) -> None:
        """Verify that chat.sh supports the --new flag."""
        content = load_zygote_resource("chat.sh")
        assert "--new" in content

    def test_chat_script_has_resume_flag(self) -> None:
        """Verify that chat.sh supports the --resume flag."""
        content = load_zygote_resource("chat.sh")
        assert "--resume" in content

    def test_chat_script_has_as_agent_flag(self) -> None:
        """Verify that chat.sh supports --as-agent for agent-initiated conversations."""
        content = load_zygote_resource("chat.sh")
        assert "--as-agent" in content

    def test_chat_script_uses_llm_live_chat(self) -> None:
        """Verify that chat.sh invokes llm live-chat for user conversations."""
        content = load_zygote_resource("chat.sh")
        assert "llm live-chat" in content

    def test_chat_script_uses_llm_inject(self) -> None:
        """Verify that chat.sh invokes llm inject for agent-initiated conversations."""
        content = load_zygote_resource("chat.sh")
        assert "llm inject" in content

    def test_chat_script_writes_conversations_jsonl(self) -> None:
        """Verify that chat.sh writes to conversations.jsonl."""
        content = load_zygote_resource("chat.sh")
        assert "conversations.jsonl" in content

    def test_chat_script_uses_agent_state_dir(self) -> None:
        """Verify that chat.sh uses MNG_AGENT_STATE_DIR."""
        content = load_zygote_resource("chat.sh")
        assert "MNG_AGENT_STATE_DIR" in content

    def test_chat_script_passes_llm_tools(self) -> None:
        """Verify that chat.sh passes --functions for LLM tools."""
        content = load_zygote_resource("chat.sh")
        assert "--functions" in content
        assert "llm_tools" in content


class TestConversationWatcherContent:
    def test_watches_llm_database(self) -> None:
        """Verify that conversation_watcher.sh queries the llm database."""
        content = load_zygote_resource("conversation_watcher.sh")
        assert "sqlite3" in content or "llm logs" in content

    def test_syncs_to_conversations_dir(self) -> None:
        """Verify that conversation_watcher.sh syncs to conversations/ directory."""
        content = load_zygote_resource("conversation_watcher.sh")
        assert "conversations" in content

    def test_supports_inotifywait(self) -> None:
        """Verify that conversation_watcher.sh checks for inotifywait."""
        content = load_zygote_resource("conversation_watcher.sh")
        assert "inotifywait" in content


class TestEventWatcherContent:
    def test_sends_mng_message(self) -> None:
        """Verify that event_watcher.sh sends events via mng message."""
        content = load_zygote_resource("event_watcher.sh")
        assert "mng message" in content

    def test_watches_conversations_dir(self) -> None:
        """Verify that event_watcher.sh watches the conversations directory."""
        content = load_zygote_resource("event_watcher.sh")
        assert "conversations" in content

    def test_watches_entrypoint_events(self) -> None:
        """Verify that event_watcher.sh watches entrypoint_events.jsonl."""
        content = load_zygote_resource("event_watcher.sh")
        assert "entrypoint_events.jsonl" in content

    def test_tracks_offsets(self) -> None:
        """Verify that event_watcher.sh tracks event offsets."""
        content = load_zygote_resource("event_watcher.sh")
        assert "offset" in content.lower()

    def test_supports_inotifywait(self) -> None:
        """Verify that event_watcher.sh checks for inotifywait."""
        content = load_zygote_resource("event_watcher.sh")
        assert "inotifywait" in content


class TestLlmToolContent:
    def test_context_tool_has_gather_context(self) -> None:
        """Verify that context_tool.py defines a gather_context function."""
        content = load_zygote_resource("context_tool.py")
        assert "def gather_context" in content

    def test_context_tool_has_docstring(self) -> None:
        """Verify that gather_context has a docstring (required by llm)."""
        content = load_zygote_resource("context_tool.py")
        assert '"""' in content

    def test_context_tool_has_return_type(self) -> None:
        """Verify that gather_context has a return type annotation."""
        content = load_zygote_resource("context_tool.py")
        assert "-> str" in content

    def test_extra_context_tool_has_gather_extra_context(self) -> None:
        """Verify that extra_context_tool.py defines gather_extra_context."""
        content = load_zygote_resource("extra_context_tool.py")
        assert "def gather_extra_context" in content

    def test_extra_context_tool_uses_mng_list(self) -> None:
        """Verify that extra_context_tool.py calls mng list."""
        content = load_zygote_resource("extra_context_tool.py")
        assert "mng" in content
        assert "list" in content


class TestMemoryLinkerContent:
    def test_computes_expected_project_name(self) -> None:
        """Verify that memory_linker.sh computes the project dir name from work_dir."""
        content = load_zygote_resource("memory_linker.sh")
        assert "compute_expected_project_name" in content

    def test_uses_specific_project_dir(self) -> None:
        """Verify that memory_linker.sh looks for a specific project directory, not any."""
        content = load_zygote_resource("memory_linker.sh")
        assert "EXPECTED_PROJECT_DIR" in content

    def test_fails_on_merge_failure(self) -> None:
        """Verify that memory_linker.sh fails if merge of existing memory fails."""
        content = load_zygote_resource("memory_linker.sh")
        assert "exit 1" in content
        # Should NOT have '|| true' after rsync/cp that could lose data
        assert "rsync" in content


def _make_mock_host() -> MagicMock:
    """Create a mock OnlineHostInterface for testing provisioning functions."""
    host = MagicMock()
    # Make execute_command return success by default
    result = MagicMock()
    result.success = True
    result.stderr = ""
    host.execute_command.return_value = result
    host.host_dir = Path("/tmp/mng-test/host")
    return host


class TestCreateChangelingSymlinks:
    def test_checks_entrypoint_md_exists(self) -> None:
        """Verify that create_changeling_symlinks checks if entrypoint.md exists."""
        host = _make_mock_host()
        work_dir = Path("/test/work")
        create_changeling_symlinks(host, work_dir, ".changelings")

        # Should have called execute_command with test -f for entrypoint.md
        calls = [str(c) for c in host.execute_command.call_args_list]
        assert any("entrypoint.md" in c for c in calls)

    def test_checks_entrypoint_json_exists(self) -> None:
        """Verify that create_changeling_symlinks checks if entrypoint.json exists."""
        host = _make_mock_host()
        work_dir = Path("/test/work")
        create_changeling_symlinks(host, work_dir, ".changelings")

        calls = [str(c) for c in host.execute_command.call_args_list]
        assert any("entrypoint.json" in c for c in calls)

    def test_creates_symlink_for_claude_local_md(self) -> None:
        """Verify that create_changeling_symlinks creates CLAUDE.local.md symlink."""
        host = _make_mock_host()
        work_dir = Path("/test/work")
        create_changeling_symlinks(host, work_dir, ".changelings")

        calls = [str(c) for c in host.execute_command.call_args_list]
        assert any("ln -sf" in c and "CLAUDE.local.md" in c for c in calls)


class TestCreateConversationDirectories:
    def test_creates_conversations_dir(self) -> None:
        """Verify that create_conversation_directories creates the logs/conversations/ dir."""
        host = _make_mock_host()
        agent_state_dir = Path("/tmp/mng-test/agents/agent-123")
        create_conversation_directories(host, agent_state_dir)

        calls = [str(c) for c in host.execute_command.call_args_list]
        assert any("conversations" in c and "mkdir" in c for c in calls)


class TestWriteDefaultChatModel:
    def test_writes_model_to_file(self) -> None:
        """Verify that write_default_chat_model writes the model name."""
        host = _make_mock_host()
        agent_state_dir = Path("/tmp/mng-test/agents/agent-123")
        model = ChatModel("claude-sonnet-4-6")

        write_default_chat_model(host, agent_state_dir, model)

        host.write_text_file.assert_called_once()
        call_args = host.write_text_file.call_args
        assert "claude-sonnet-4-6" in call_args[0][1]
        assert str(call_args[0][0]).endswith("default_chat_model")


class TestInstallLlmToolchain:
    def test_skips_install_when_llm_already_present(self) -> None:
        """Verify that install_llm_toolchain skips llm install if already available."""
        host = _make_mock_host()
        install_llm_toolchain(host)

        # Should check for llm, then install plugins (not llm itself)
        calls = [str(c) for c in host.execute_command.call_args_list]
        assert any("command -v llm" in c for c in calls)
        assert not any("uv tool install llm" in c for c in calls)

    def test_installs_llm_when_not_present(self) -> None:
        """Verify that install_llm_toolchain installs llm when not available."""
        host = _make_mock_host()
        # First call (command -v llm) fails, rest succeed
        fail_result = MagicMock()
        fail_result.success = False
        fail_result.stderr = "not found"
        ok_result = MagicMock()
        ok_result.success = True
        ok_result.stderr = ""
        host.execute_command.side_effect = [fail_result, ok_result, ok_result, ok_result]

        install_llm_toolchain(host)

        calls = [str(c) for c in host.execute_command.call_args_list]
        assert any("uv tool install llm" in c for c in calls)

    def test_installs_llm_plugins(self) -> None:
        """Verify that install_llm_toolchain installs llm-anthropic and llm-live-chat."""
        host = _make_mock_host()
        install_llm_toolchain(host)

        calls = [str(c) for c in host.execute_command.call_args_list]
        assert any("llm install llm-anthropic" in c for c in calls)
        assert any("llm install llm-live-chat" in c for c in calls)

    def test_raises_on_llm_install_failure(self) -> None:
        """Verify that install_llm_toolchain raises on llm install failure."""
        host = _make_mock_host()
        fail_result = MagicMock()
        fail_result.success = False
        fail_result.stderr = "install failed"
        # command -v fails, then uv tool install fails
        host.execute_command.side_effect = [fail_result, fail_result]

        with pytest.raises(RuntimeError, match="Failed to install llm"):
            install_llm_toolchain(host)

    def test_raises_on_plugin_install_failure(self) -> None:
        """Verify that install_llm_toolchain raises on plugin install failure."""
        host = _make_mock_host()
        ok_result = MagicMock()
        ok_result.success = True
        ok_result.stderr = ""
        fail_result = MagicMock()
        fail_result.success = False
        fail_result.stderr = "plugin install failed"
        # command -v succeeds, then llm install llm-anthropic fails
        host.execute_command.side_effect = [ok_result, fail_result]

        with pytest.raises(RuntimeError, match="Failed to install llm-anthropic"):
            install_llm_toolchain(host)


class TestProvisionChangelingScripts:
    def test_creates_commands_directory(self) -> None:
        """Verify that provision_changeling_scripts creates the commands directory."""
        host = _make_mock_host()
        provision_changeling_scripts(host)

        calls = [str(c) for c in host.execute_command.call_args_list]
        assert any("mkdir" in c and "commands" in c for c in calls)

    def test_writes_all_scripts(self) -> None:
        """Verify that provision_changeling_scripts writes all script files."""
        host = _make_mock_host()
        provision_changeling_scripts(host)

        write_calls = host.write_file.call_args_list
        written_names = [str(c[0][0]) for c in write_calls]
        for script_name in _SCRIPT_FILES:
            assert any(script_name in name for name in written_names), f"{script_name} not written"

    def test_writes_scripts_as_executable(self) -> None:
        """Verify that scripts are written with mode 0755."""
        host = _make_mock_host()
        provision_changeling_scripts(host)

        for write_call in host.write_file.call_args_list:
            assert write_call[1].get("mode") == "0755" or (len(write_call[0]) > 2 and write_call[0][2] == "0755")


class TestProvisionLlmTools:
    def test_creates_llm_tools_directory(self) -> None:
        """Verify that provision_llm_tools creates the llm_tools directory."""
        host = _make_mock_host()
        provision_llm_tools(host)

        calls = [str(c) for c in host.execute_command.call_args_list]
        assert any("mkdir" in c and "llm_tools" in c for c in calls)

    def test_writes_all_tool_files(self) -> None:
        """Verify that provision_llm_tools writes all tool files."""
        host = _make_mock_host()
        provision_llm_tools(host)

        write_calls = host.write_file.call_args_list
        written_names = [str(c[0][0]) for c in write_calls]
        for tool_file in _LLM_TOOL_FILES:
            assert any(tool_file in name for name in written_names), f"{tool_file} not written"
