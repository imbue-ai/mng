from datetime import datetime
from datetime import timezone
from pathlib import Path
from unittest.mock import Mock

import pluggy
import pytest

from imbue.mngr.agents.default_plugins.claude_agent import _get_claude_config
from imbue.mngr.agents.default_plugins.claude_agent import _is_claude_agent
from imbue.mngr.agents.default_plugins.claude_agent import ClaudeAgent
from imbue.mngr.agents.default_plugins.claude_agent import ClaudeAgentConfig
from imbue.mngr.config.data_types import AgentTypeConfig
from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import NoCommandDefinedError
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import HostId


def test_claude_agent_config_has_default_command() -> None:
    """Claude agent config should have a default command."""
    config = ClaudeAgentConfig()
    assert config.command == CommandString("claude")


def test_claude_agent_config_merge_overrides_command() -> None:
    """Merging should override command field."""
    base = ClaudeAgentConfig()
    override = ClaudeAgentConfig(command=CommandString("custom-claude"))

    merged = base.merge_with(override)

    assert merged.command == CommandString("custom-claude")


def test_claude_agent_config_merge_concatenates_cli_args() -> None:
    """Claude agent config should concatenate cli_args."""
    base = ClaudeAgentConfig(cli_args="--verbose")
    override = ClaudeAgentConfig(cli_args="--model sonnet")

    merged = base.merge_with(override)

    assert merged.cli_args == "--verbose --model sonnet"


def test_claude_agent_assemble_command_with_no_args(mngr_test_prefix: str) -> None:
    """ClaudeAgent should generate resume/session-id command format with no args."""
    pm = pluggy.PluginManager("mngr")
    agent_id = AgentId.generate()
    mock_host = Mock()

    agent = ClaudeAgent.model_construct(
        id=agent_id,
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("claude"),
        work_dir=Path("/tmp/work"),
        create_time=datetime.now(timezone.utc),
        host_id=HostId.generate(),
        mngr_ctx=MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm),
        agent_config=ClaudeAgentConfig(),
        host=mock_host,
    )

    command = agent.assemble_command(host=mock_host, agent_args=(), command_override=None)

    uuid = agent_id.get_uuid()
    assert command == CommandString(
        f"export IS_SANDBOX=1 && export MAIN_CLAUDE_SESSION_ID={uuid} && ( find ~/.claude/ -name '{uuid}' && claude --resume {uuid} ) || claude --session-id {uuid}"
    )


def test_claude_agent_assemble_command_with_agent_args(mngr_test_prefix: str) -> None:
    """ClaudeAgent should append agent args to both command variants."""
    pm = pluggy.PluginManager("mngr")
    agent_id = AgentId.generate()
    mock_host = Mock()

    agent = ClaudeAgent.model_construct(
        id=agent_id,
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("claude"),
        work_dir=Path("/tmp/work"),
        create_time=datetime.now(timezone.utc),
        host_id=HostId.generate(),
        mngr_ctx=MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm),
        agent_config=ClaudeAgentConfig(),
        host=mock_host,
    )

    command = agent.assemble_command(host=mock_host, agent_args=("--model", "opus"), command_override=None)

    uuid = agent_id.get_uuid()
    assert command == CommandString(
        f"export IS_SANDBOX=1 && export MAIN_CLAUDE_SESSION_ID={uuid} && ( find ~/.claude/ -name '{uuid}' && claude --resume {uuid} --model opus ) || claude --session-id {uuid} --model opus"
    )


def test_claude_agent_assemble_command_with_cli_args_and_agent_args(mngr_test_prefix: str) -> None:
    """ClaudeAgent should append both cli_args and agent_args to both command variants."""
    pm = pluggy.PluginManager("mngr")
    agent_id = AgentId.generate()
    mock_host = Mock()

    agent = ClaudeAgent.model_construct(
        id=agent_id,
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("claude"),
        work_dir=Path("/tmp/work"),
        create_time=datetime.now(timezone.utc),
        host_id=HostId.generate(),
        mngr_ctx=MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm),
        agent_config=ClaudeAgentConfig(cli_args="--verbose"),
        host=mock_host,
    )

    command = agent.assemble_command(host=mock_host, agent_args=("--model", "opus"), command_override=None)

    uuid = agent_id.get_uuid()
    assert command == CommandString(
        f"export IS_SANDBOX=1 && export MAIN_CLAUDE_SESSION_ID={uuid} && ( find ~/.claude/ -name '{uuid}' && claude --resume {uuid} --verbose --model opus ) || claude --session-id {uuid} --verbose --model opus"
    )


def test_claude_agent_assemble_command_with_command_override(mngr_test_prefix: str) -> None:
    """ClaudeAgent should use command override when provided."""
    pm = pluggy.PluginManager("mngr")
    agent_id = AgentId.generate()
    mock_host = Mock()

    agent = ClaudeAgent.model_construct(
        id=agent_id,
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("claude"),
        work_dir=Path("/tmp/work"),
        create_time=datetime.now(timezone.utc),
        host_id=HostId.generate(),
        mngr_ctx=MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm),
        agent_config=ClaudeAgentConfig(),
        host=mock_host,
    )

    command = agent.assemble_command(
        host=mock_host,
        agent_args=("--model", "opus"),
        command_override=CommandString("custom-claude"),
    )

    uuid = agent_id.get_uuid()
    assert command == CommandString(
        f"export IS_SANDBOX=1 && export MAIN_CLAUDE_SESSION_ID={uuid} && ( find ~/.claude/ -name '{uuid}' && custom-claude --resume {uuid} --model opus ) || custom-claude --session-id {uuid} --model opus"
    )


def test_claude_agent_assemble_command_raises_when_no_command(mngr_test_prefix: str) -> None:
    """ClaudeAgent should raise NoCommandDefinedError when no command defined."""
    pm = pluggy.PluginManager("mngr")
    agent_id = AgentId.generate()
    mock_host = Mock()

    # Create agent with no command configured
    agent = ClaudeAgent.model_construct(
        id=agent_id,
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("custom"),
        work_dir=Path("/tmp/work"),
        create_time=datetime.now(timezone.utc),
        host_id=HostId.generate(),
        mngr_ctx=MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm),
        agent_config=AgentTypeConfig(),
        host=mock_host,
    )

    with pytest.raises(NoCommandDefinedError, match="No command defined"):
        agent.assemble_command(host=mock_host, agent_args=(), command_override=None)


def test_claude_agent_config_merge_uses_override_cli_args_when_base_empty() -> None:
    """ClaudeAgentConfig merge should use override cli_args when base is empty."""
    base = ClaudeAgentConfig()
    override = ClaudeAgentConfig(cli_args="--verbose")

    merged = base.merge_with(override)

    assert merged.cli_args == "--verbose"


def test_is_claude_agent_returns_true_for_claude_type(mngr_test_prefix: str) -> None:
    """_is_claude_agent should return True for agents with 'claude' type."""
    pm = pluggy.PluginManager("mngr")
    agent_id = AgentId.generate()

    agent = ClaudeAgent.model_construct(
        id=agent_id,
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("claude"),
        work_dir=Path("/tmp/work"),
        create_time=datetime.now(timezone.utc),
        host_id=HostId.generate(),
        mngr_ctx=MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm),
        agent_config=ClaudeAgentConfig(),
        host=Mock(),
    )

    assert _is_claude_agent(agent) is True


def test_is_claude_agent_returns_false_for_other_type(mngr_test_prefix: str) -> None:
    """_is_claude_agent should return False for agents with non-claude type."""
    pm = pluggy.PluginManager("mngr")
    agent_id = AgentId.generate()

    agent = ClaudeAgent.model_construct(
        id=agent_id,
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("codex"),
        work_dir=Path("/tmp/work"),
        create_time=datetime.now(timezone.utc),
        host_id=HostId.generate(),
        mngr_ctx=MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm),
        agent_config=AgentTypeConfig(),
        host=Mock(),
    )

    assert _is_claude_agent(agent) is False


def test_get_claude_config_returns_config_when_claude_agent_config(mngr_test_prefix: str) -> None:
    """_get_claude_config should return the config when it is a ClaudeAgentConfig."""
    pm = pluggy.PluginManager("mngr")
    agent_id = AgentId.generate()
    config = ClaudeAgentConfig(cli_args="--verbose")

    agent = ClaudeAgent.model_construct(
        id=agent_id,
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("claude"),
        work_dir=Path("/tmp/work"),
        create_time=datetime.now(timezone.utc),
        host_id=HostId.generate(),
        mngr_ctx=MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm),
        agent_config=config,
        host=Mock(),
    )

    result = _get_claude_config(agent)

    assert result is config
    assert result.cli_args == "--verbose"


def test_get_claude_config_returns_default_when_not_claude_agent_config(mngr_test_prefix: str) -> None:
    """_get_claude_config should return default ClaudeAgentConfig when config is not ClaudeAgentConfig."""
    pm = pluggy.PluginManager("mngr")
    agent_id = AgentId.generate()

    agent = ClaudeAgent.model_construct(
        id=agent_id,
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("claude"),
        work_dir=Path("/tmp/work"),
        create_time=datetime.now(timezone.utc),
        host_id=HostId.generate(),
        mngr_ctx=MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm),
        agent_config=AgentTypeConfig(),
        host=Mock(),
    )

    result = _get_claude_config(agent)

    assert isinstance(result, ClaudeAgentConfig)
    assert result.command == CommandString("claude")
