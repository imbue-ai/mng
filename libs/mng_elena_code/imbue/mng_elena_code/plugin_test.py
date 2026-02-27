"""Unit tests for the mng_elena_code plugin."""

from typing import Any

from imbue.mng.agents.default_plugins.claude_agent import ClaudeAgent
from imbue.mng_claude_zygote.plugin import AGENT_TTYD_COMMAND
from imbue.mng_claude_zygote.plugin import AGENT_TTYD_WINDOW_NAME
from imbue.mng_claude_zygote.plugin import ClaudeZygoteAgent
from imbue.mng_elena_code.plugin import ELENA_SYSTEM_PROMPT
from imbue.mng_elena_code.plugin import ElenaCodeAgent
from imbue.mng_elena_code.plugin import override_command_options


class _DummyCommandClass:
    pass


def test_elena_code_agent_inherits_from_claude_zygote_agent() -> None:
    """Verify that ElenaCodeAgent is a subclass of ClaudeZygoteAgent."""
    assert issubclass(ElenaCodeAgent, ClaudeZygoteAgent)


def test_elena_code_agent_inherits_from_claude_agent() -> None:
    """Verify that ElenaCodeAgent is transitively a subclass of ClaudeAgent."""
    assert issubclass(ElenaCodeAgent, ClaudeAgent)


def test_adds_agent_ttyd_for_elena_code_type() -> None:
    """Verify that the plugin adds an agent ttyd command for elena-code agents."""
    params: dict[str, Any] = {"add_command": (), "agent_type": "elena-code"}

    override_command_options(
        command_name="create",
        command_class=_DummyCommandClass,
        params=params,
    )

    assert len(params["add_command"]) == 1
    assert AGENT_TTYD_WINDOW_NAME in params["add_command"][0]
    assert AGENT_TTYD_COMMAND in params["add_command"][0]


def test_does_not_modify_non_create_commands() -> None:
    """Verify that the plugin does not modify params for non-create commands."""
    params: dict[str, Any] = {"add_command": (), "agent_type": "elena-code"}

    override_command_options(
        command_name="connect",
        command_class=_DummyCommandClass,
        params=params,
    )

    assert params["add_command"] == ()


def test_does_not_modify_for_other_agent_types() -> None:
    """Verify that the plugin does not modify params for non-elena-code agents."""
    params: dict[str, Any] = {"add_command": (), "agent_type": "claude"}

    override_command_options(
        command_name="create",
        command_class=_DummyCommandClass,
        params=params,
    )

    assert params["add_command"] == ()


def test_elena_system_prompt_is_conversational() -> None:
    """Verify that the system prompt instructs Elena to be conversational."""
    assert "conversational" in ELENA_SYSTEM_PROMPT.lower()


def test_elena_system_prompt_forbids_code_writing() -> None:
    """Verify that the system prompt instructs Elena not to write code."""
    assert "NEVER write code" in ELENA_SYSTEM_PROMPT
