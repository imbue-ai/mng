"""Unit tests for the mng_claude_zygote plugin."""

from typing import Any

from imbue.mng.agents.default_plugins.claude_agent import ClaudeAgent
from imbue.mng.agents.default_plugins.claude_agent import ClaudeAgentConfig
from imbue.mng.interfaces.host import NamedCommand
from imbue.mng_claude_zygote.data_types import ChatModel
from imbue.mng_claude_zygote.plugin import AGENT_TTYD_COMMAND
from imbue.mng_claude_zygote.plugin import AGENT_TTYD_SERVER_NAME
from imbue.mng_claude_zygote.plugin import AGENT_TTYD_WINDOW_NAME
from imbue.mng_claude_zygote.plugin import CHAT_TTYD_COMMAND
from imbue.mng_claude_zygote.plugin import CHAT_TTYD_SERVER_NAME
from imbue.mng_claude_zygote.plugin import CHAT_TTYD_WINDOW_NAME
from imbue.mng_claude_zygote.plugin import CONV_WATCHER_COMMAND
from imbue.mng_claude_zygote.plugin import CONV_WATCHER_WINDOW_NAME
from imbue.mng_claude_zygote.plugin import ClaudeZygoteAgent
from imbue.mng_claude_zygote.plugin import ClaudeZygoteConfig
from imbue.mng_claude_zygote.plugin import EVENT_WATCHER_COMMAND
from imbue.mng_claude_zygote.plugin import EVENT_WATCHER_WINDOW_NAME
from imbue.mng_claude_zygote.plugin import MEMORY_LINKER_COMMAND
from imbue.mng_claude_zygote.plugin import MEMORY_LINKER_WINDOW_NAME
from imbue.mng_claude_zygote.plugin import inject_agent_ttyd
from imbue.mng_claude_zygote.plugin import inject_changeling_windows
from imbue.mng_claude_zygote.plugin import override_command_options


class _DummyCommandClass:
    pass


# -- Class hierarchy tests --


def test_claude_zygote_agent_inherits_from_claude_agent() -> None:
    """Verify that ClaudeZygoteAgent is a subclass of ClaudeAgent."""
    assert issubclass(ClaudeZygoteAgent, ClaudeAgent)


# -- Config tests --


def test_claude_zygote_config_defaults_trust_to_true() -> None:
    """Verify that ClaudeZygoteConfig defaults trust_working_directory to True."""
    config = ClaudeZygoteConfig()
    assert config.trust_working_directory is True


def test_claude_zygote_config_inherits_from_claude_agent_config() -> None:
    """Verify that ClaudeZygoteConfig is a subclass of ClaudeAgentConfig."""
    assert issubclass(ClaudeZygoteConfig, ClaudeAgentConfig)


def test_claude_zygote_config_overrides_base_trust_default() -> None:
    """Verify that ClaudeZygoteConfig overrides the base default (False) to True."""
    base = ClaudeAgentConfig()
    zygote = ClaudeZygoteConfig()
    assert base.trust_working_directory is False
    assert zygote.trust_working_directory is True


def test_claude_zygote_config_has_default_chat_model() -> None:
    """Verify that ClaudeZygoteConfig has a default_chat_model field."""
    config = ClaudeZygoteConfig()
    assert config.default_chat_model == ChatModel("claude-sonnet-4-6")


def test_claude_zygote_config_has_install_llm_default() -> None:
    """Verify that install_llm defaults to True."""
    config = ClaudeZygoteConfig()
    assert config.install_llm is True


def test_claude_zygote_config_has_changelings_dir_name() -> None:
    """Verify that changelings_dir_name defaults to '.changelings'."""
    config = ClaudeZygoteConfig()
    assert config.changelings_dir_name == ".changelings"


# -- override_command_options hook tests --


def test_adds_changeling_windows_for_claude_zygote_type() -> None:
    """Verify that the plugin adds all changeling windows for claude-zygote agents."""
    params: dict[str, Any] = {"add_command": (), "agent_type": "claude-zygote"}

    override_command_options(
        command_name="create",
        command_class=_DummyCommandClass,
        params=params,
    )

    # Should have 4 windows: agent ttyd, conv_watcher, events, chat ttyd
    assert len(params["add_command"]) == 5


def test_adds_agent_ttyd_for_claude_zygote_type() -> None:
    """Verify that agent ttyd is included in the changeling windows."""
    params: dict[str, Any] = {"add_command": (), "agent_type": "claude-zygote"}

    override_command_options(
        command_name="create",
        command_class=_DummyCommandClass,
        params=params,
    )

    assert AGENT_TTYD_WINDOW_NAME in params["add_command"][0]
    assert AGENT_TTYD_COMMAND in params["add_command"][0]


def test_adds_conv_watcher_window() -> None:
    """Verify that conversation watcher window is injected."""
    params: dict[str, Any] = {"add_command": (), "agent_type": "claude-zygote"}

    override_command_options(
        command_name="create",
        command_class=_DummyCommandClass,
        params=params,
    )

    watcher_entries = [c for c in params["add_command"] if CONV_WATCHER_WINDOW_NAME in c]
    assert len(watcher_entries) == 1
    assert CONV_WATCHER_COMMAND in watcher_entries[0]


def test_adds_event_watcher_window() -> None:
    """Verify that event watcher window is injected."""
    params: dict[str, Any] = {"add_command": (), "agent_type": "claude-zygote"}

    override_command_options(
        command_name="create",
        command_class=_DummyCommandClass,
        params=params,
    )

    event_entries = [c for c in params["add_command"] if EVENT_WATCHER_WINDOW_NAME in c]
    assert len(event_entries) == 1
    assert EVENT_WATCHER_COMMAND in event_entries[0]


def test_adds_chat_ttyd_window() -> None:
    """Verify that chat ttyd window is injected."""
    params: dict[str, Any] = {"add_command": (), "agent_type": "claude-zygote"}

    override_command_options(
        command_name="create",
        command_class=_DummyCommandClass,
        params=params,
    )

    chat_entries = [c for c in params["add_command"] if CHAT_TTYD_WINDOW_NAME in c]
    assert len(chat_entries) == 1


def test_adds_changeling_windows_for_positional_agent_type() -> None:
    """Verify that the plugin detects agent type from positional_agent_type."""
    params: dict[str, Any] = {"add_command": (), "positional_agent_type": "claude-zygote"}

    override_command_options(
        command_name="create",
        command_class=_DummyCommandClass,
        params=params,
    )

    assert len(params["add_command"]) == 5


def test_does_not_modify_non_create_commands() -> None:
    """Verify that the plugin does not modify params for non-create commands."""
    params: dict[str, Any] = {"add_command": (), "agent_type": "claude-zygote"}

    override_command_options(
        command_name="connect",
        command_class=_DummyCommandClass,
        params=params,
    )

    assert params["add_command"] == ()


def test_does_not_modify_for_other_agent_types() -> None:
    """Verify that the plugin does not modify params for non-claude-zygote agents."""
    params: dict[str, Any] = {"add_command": (), "agent_type": "claude"}

    override_command_options(
        command_name="create",
        command_class=_DummyCommandClass,
        params=params,
    )

    assert params["add_command"] == ()


def test_does_not_modify_when_no_agent_type() -> None:
    """Verify that the plugin does not modify params when no agent type is specified."""
    params: dict[str, Any] = {"add_command": ()}

    override_command_options(
        command_name="create",
        command_class=_DummyCommandClass,
        params=params,
    )

    assert params["add_command"] == ()


def test_preserves_existing_add_commands() -> None:
    """Verify that the plugin preserves any existing additional commands."""
    params: dict[str, Any] = {
        "add_command": ('monitor="htop"',),
        "agent_type": "claude-zygote",
    }

    override_command_options(
        command_name="create",
        command_class=_DummyCommandClass,
        params=params,
    )

    # 1 existing + 5 new = 6
    assert len(params["add_command"]) == 6
    assert params["add_command"][0] == 'monitor="htop"'


# -- inject_agent_ttyd tests (direct function) --


def test_inject_agent_ttyd_adds_command() -> None:
    """Verify that inject_agent_ttyd adds the ttyd command to params."""
    params: dict[str, Any] = {}

    inject_agent_ttyd(params)

    assert len(params["add_command"]) == 1
    assert AGENT_TTYD_WINDOW_NAME in params["add_command"][0]


def test_inject_agent_ttyd_preserves_existing() -> None:
    """Verify that inject_agent_ttyd preserves existing add_command entries."""
    params: dict[str, Any] = {"add_command": ('foo="bar"',)}

    inject_agent_ttyd(params)

    assert len(params["add_command"]) == 2


# -- inject_changeling_windows tests --


def test_inject_changeling_windows_adds_all_windows() -> None:
    """Verify that inject_changeling_windows adds all 4 windows."""
    params: dict[str, Any] = {}

    inject_changeling_windows(params)

    assert len(params["add_command"]) == 5


def test_inject_changeling_windows_preserves_existing() -> None:
    """Verify that inject_changeling_windows preserves existing commands."""
    params: dict[str, Any] = {"add_command": ('foo="bar"',)}

    inject_changeling_windows(params)

    # 1 existing + 5 new windows = 6
    assert len(params["add_command"]) == 6
    assert params["add_command"][0] == 'foo="bar"'


# -- Agent ttyd command content tests --


def test_agent_ttyd_command_is_parseable_as_named_command() -> None:
    """Verify that the injected command string can be parsed by NamedCommand.from_string."""
    params: dict[str, Any] = {}

    inject_agent_ttyd(params)

    named_cmd = NamedCommand.from_string(params["add_command"][0])
    assert named_cmd.window_name == AGENT_TTYD_WINDOW_NAME
    assert str(named_cmd.command) == AGENT_TTYD_COMMAND


def test_agent_ttyd_command_uses_random_port() -> None:
    """Verify that the ttyd command binds to a random port via -p 0."""
    assert "ttyd -p 0" in AGENT_TTYD_COMMAND


def test_agent_ttyd_command_writes_server_log() -> None:
    """Verify that the ttyd command writes to servers.jsonl for forwarding server discovery."""
    assert "servers.jsonl" in AGENT_TTYD_COMMAND
    assert AGENT_TTYD_SERVER_NAME in AGENT_TTYD_COMMAND
    assert "MNG_AGENT_STATE_DIR" in AGENT_TTYD_COMMAND


def test_agent_ttyd_command_watches_stderr_for_port() -> None:
    """Verify that the command parses the port from ttyd's output."""
    assert "Listening on port:" in AGENT_TTYD_COMMAND


def test_agent_ttyd_command_attaches_to_session() -> None:
    """Verify that the command uses tmux attach to connect to the agent session."""
    assert "tmux attach" in AGENT_TTYD_COMMAND
    assert "session_name" in AGENT_TTYD_COMMAND


def test_agent_ttyd_command_unsets_tmux_env() -> None:
    """Verify that the command unsets the TMUX env var to allow nested tmux attach."""
    assert "unset TMUX" in AGENT_TTYD_COMMAND


def test_agent_ttyd_command_skips_log_when_no_state_dir() -> None:
    """Verify that the command gracefully handles MNG_AGENT_STATE_DIR being unset."""
    assert 'if [ -n "$MNG_AGENT_STATE_DIR" ]' in AGENT_TTYD_COMMAND


# -- Chat ttyd command content tests --


def test_chat_ttyd_command_uses_random_port() -> None:
    """Verify that the chat ttyd command binds to a random port."""
    assert "ttyd -p 0" in CHAT_TTYD_COMMAND


def test_chat_ttyd_command_writes_server_log() -> None:
    """Verify that the chat ttyd writes to servers.jsonl."""
    assert "servers.jsonl" in CHAT_TTYD_COMMAND
    assert CHAT_TTYD_SERVER_NAME in CHAT_TTYD_COMMAND


def test_chat_ttyd_command_runs_chat_script() -> None:
    """Verify that the chat ttyd runs the chat.sh script."""
    assert "chat.sh" in CHAT_TTYD_COMMAND


# -- Watcher command content tests --


def test_conv_watcher_command_references_script() -> None:
    """Verify that the conversation watcher command references the correct script."""
    assert "conversation_watcher.sh" in CONV_WATCHER_COMMAND


def test_event_watcher_command_references_script() -> None:
    """Verify that the event watcher command references the correct script."""
    assert "event_watcher.sh" in EVENT_WATCHER_COMMAND


def test_memory_linker_command_references_script() -> None:
    """Verify that the memory linker command references the correct script."""
    assert "memory_linker.sh" in MEMORY_LINKER_COMMAND


def test_adds_memory_linker_window() -> None:
    """Verify that memory linker window is injected."""
    params: dict[str, Any] = {"add_command": (), "agent_type": "claude-zygote"}

    override_command_options(
        command_name="create",
        command_class=_DummyCommandClass,
        params=params,
    )

    linker_entries = [c for c in params["add_command"] if MEMORY_LINKER_WINDOW_NAME in c]
    assert len(linker_entries) == 1
    assert MEMORY_LINKER_COMMAND in linker_entries[0]
