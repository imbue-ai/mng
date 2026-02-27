"""Unit tests for the mng_elena_code plugin."""

from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any
from typing import cast

import pluggy

from imbue.mng.agents.default_plugins.claude_agent import ClaudeAgent
from imbue.mng.agents.default_plugins.claude_agent import ClaudeAgentConfig
from imbue.mng.api.test_fixtures import FakeHost
from imbue.mng.config.data_types import MngConfig
from imbue.mng.config.data_types import MngContext
from imbue.mng.interfaces.host import OnlineHostInterface
from imbue.mng.primitives import AgentId
from imbue.mng.primitives import AgentName
from imbue.mng.primitives import AgentTypeName
from imbue.mng.primitives import HostId
from imbue.mng_claude_zygote.plugin import AGENT_TTYD_COMMAND
from imbue.mng_claude_zygote.plugin import AGENT_TTYD_WINDOW_NAME
from imbue.mng_claude_zygote.plugin import ClaudeZygoteAgent
from imbue.mng_elena_code.plugin import ELENA_SYSTEM_PROMPT
from imbue.mng_elena_code.plugin import ElenaCodeAgent
from imbue.mng_elena_code.plugin import override_command_options


class _DummyCommandClass:
    pass


def _make_elena_agent(tmp_path: Path) -> tuple[ElenaCodeAgent, OnlineHostInterface]:
    """Create an ElenaCodeAgent with minimal dependencies for testing assemble_command."""
    pm = pluggy.PluginManager("mng")
    config = MngConfig(default_host_dir=tmp_path / "host")
    mng_ctx = MngContext.model_construct(
        config=config,
        pm=pm,
        profile_dir=tmp_path / "profile",
    )

    host = cast(OnlineHostInterface, FakeHost(is_local=True, host_dir=tmp_path / "host"))

    agent = ElenaCodeAgent.model_construct(
        id=AgentId.generate(),
        name=AgentName("test-elena"),
        agent_type=AgentTypeName("elena-code"),
        work_dir=tmp_path / "work",
        create_time=datetime.now(timezone.utc),
        host_id=HostId.generate(),
        mng_ctx=mng_ctx,
        agent_config=ClaudeAgentConfig(check_installation=False),
        host=host,
    )
    return agent, host


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


def test_elena_assemble_command_includes_system_prompt(tmp_path: Path) -> None:
    """Verify that ElenaCodeAgent.assemble_command injects the system prompt."""
    agent, host = _make_elena_agent(tmp_path)

    command = agent.assemble_command(host=host, agent_args=(), command_override=None)

    assert "--append-system-prompt" in str(command)


def test_elena_assemble_command_prompt_is_quoted(tmp_path: Path) -> None:
    """Verify that the system prompt is shell-quoted in the assembled command."""
    agent, host = _make_elena_agent(tmp_path)

    command = agent.assemble_command(host=host, agent_args=(), command_override=None)

    # shlex.quote wraps multi-word strings in single quotes
    assert "'" in str(command)
    # The prompt text should appear (quoted) in the command
    assert "Elena" in str(command)


def test_elena_assemble_command_preserves_agent_args(tmp_path: Path) -> None:
    """Verify that additional agent_args are preserved alongside the system prompt."""
    agent, host = _make_elena_agent(tmp_path)

    command = agent.assemble_command(host=host, agent_args=("--model", "sonnet"), command_override=None)

    assert "--append-system-prompt" in str(command)
    assert "--model" in str(command)
    assert "sonnet" in str(command)
