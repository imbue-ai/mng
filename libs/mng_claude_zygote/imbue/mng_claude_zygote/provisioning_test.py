"""Unit tests for the mng_claude_zygote provisioning module."""

from imbue.mng_claude_zygote.provisioning import _LLM_TOOL_FILES
from imbue.mng_claude_zygote.provisioning import _SCRIPT_FILES
from imbue.mng_claude_zygote.provisioning import load_zygote_resource


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
