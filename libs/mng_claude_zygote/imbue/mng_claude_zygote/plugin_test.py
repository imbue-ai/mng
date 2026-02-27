"""Unit tests for the mng_claude_zygote plugin."""

from typing import Any

from imbue.mng.agents.default_plugins.claude_agent import ClaudeAgent
from imbue.mng.interfaces.host import NamedCommand
from imbue.mng_claude_zygote.plugin import AGENT_TTYD_COMMAND
from imbue.mng_claude_zygote.plugin import AGENT_TTYD_SERVER_NAME
from imbue.mng_claude_zygote.plugin import AGENT_TTYD_WINDOW_NAME
from imbue.mng_claude_zygote.plugin import ClaudeZygoteAgent
from imbue.mng_claude_zygote.plugin import inject_agent_ttyd
from imbue.mng_claude_zygote.plugin import override_command_options


class _DummyCommandClass:
    pass


def test_claude_zygote_agent_inherits_from_claude_agent() -> None:
    """Verify that ClaudeZygoteAgent is a subclass of ClaudeAgent."""
    assert issubclass(ClaudeZygoteAgent, ClaudeAgent)


def test_adds_agent_ttyd_for_claude_zygote_type() -> None:
    """Verify that the plugin adds an agent ttyd command for claude-zygote agents."""
    params: dict[str, Any] = {"add_command": (), "agent_type": "claude-zygote"}

    override_command_options(
        command_name="create",
        command_class=_DummyCommandClass,
        params=params,
    )

    assert len(params["add_command"]) == 1
    assert AGENT_TTYD_WINDOW_NAME in params["add_command"][0]
    assert AGENT_TTYD_COMMAND in params["add_command"][0]


def test_adds_agent_ttyd_for_positional_agent_type() -> None:
    """Verify that the plugin detects agent type from positional_agent_type."""
    params: dict[str, Any] = {"add_command": (), "positional_agent_type": "claude-zygote"}

    override_command_options(
        command_name="create",
        command_class=_DummyCommandClass,
        params=params,
    )

    assert len(params["add_command"]) == 1


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

    assert len(params["add_command"]) == 2
    assert params["add_command"][0] == 'monitor="htop"'
    assert AGENT_TTYD_COMMAND in params["add_command"][1]


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
