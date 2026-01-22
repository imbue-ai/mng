"""Unit tests for the claude agent plugin."""

from pathlib import Path
from unittest.mock import Mock
from unittest.mock import patch

from imbue.mngr.agents.default_plugins.claude_agent import _check_claude_installed
from imbue.mngr.agents.default_plugins.claude_agent import _get_claude_config
from imbue.mngr.agents.default_plugins.claude_agent import _is_claude_agent
from imbue.mngr.agents.default_plugins.claude_agent import ClaudeAgentConfig
from imbue.mngr.agents.default_plugins.claude_agent import get_provision_file_transfers
from imbue.mngr.agents.default_plugins.claude_agent import on_before_agent_provisioning
from imbue.mngr.agents.default_plugins.claude_agent import provision_agent
from imbue.mngr.config.data_types import AgentTypeConfig
from imbue.mngr.interfaces.data_types import CommandResult
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.primitives import CommandString


def test_is_claude_agent_returns_true_for_claude_type() -> None:
    """_is_claude_agent should return True for agents with type 'claude'."""
    agent = Mock()
    agent.agent_type = AgentTypeName("claude")
    assert _is_claude_agent(agent) is True


def test_is_claude_agent_returns_false_for_other_types() -> None:
    """_is_claude_agent should return False for non-claude agent types."""
    agent = Mock()
    agent.agent_type = AgentTypeName("codex")
    assert _is_claude_agent(agent) is False


def test_get_claude_config_returns_agent_config_if_claude_type() -> None:
    """_get_claude_config should return the agent's config if it's ClaudeAgentConfig."""
    config = ClaudeAgentConfig(command=CommandString("custom-claude"))
    agent = Mock()
    agent.agent_config = config

    result = _get_claude_config(agent)

    assert result is config
    assert result.command == CommandString("custom-claude")


def test_get_claude_config_returns_default_if_not_claude_config() -> None:
    """_get_claude_config should return default ClaudeAgentConfig if agent has different config type."""
    agent = Mock()
    agent.agent_config = AgentTypeConfig()

    result = _get_claude_config(agent)

    assert isinstance(result, ClaudeAgentConfig)
    assert result.command == CommandString("claude")


def test_check_claude_installed_returns_true_when_command_exists() -> None:
    """_check_claude_installed should return True when claude command is found."""
    host = Mock()
    host.execute_command.return_value = CommandResult(
        stdout="/usr/local/bin/claude",
        stderr="",
        success=True,
    )

    result = _check_claude_installed(host)

    assert result is True
    host.execute_command.assert_called_once_with("command -v claude", timeout_seconds=10.0)


def test_check_claude_installed_returns_false_when_command_not_found() -> None:
    """_check_claude_installed should return False when claude command is not found."""
    host = Mock()
    host.execute_command.return_value = CommandResult(
        stdout="",
        stderr="",
        success=False,
    )

    result = _check_claude_installed(host)

    assert result is False


def test_on_before_provisioning_skips_non_claude_agents() -> None:
    """on_before_agent_provisioning should do nothing for non-claude agents."""
    agent = Mock()
    agent.agent_type = AgentTypeName("codex")
    host = Mock()
    options = Mock()
    mngr_ctx = Mock()

    # Should not raise or do anything
    on_before_agent_provisioning(agent, host, options, mngr_ctx)


def test_on_before_provisioning_skips_when_check_installation_false() -> None:
    """on_before_agent_provisioning should skip check when check_installation is False."""
    agent = Mock()
    agent.agent_type = AgentTypeName("claude")
    agent.agent_config = ClaudeAgentConfig(check_installation=False)
    host = Mock()
    options = Mock()
    options.command = None
    mngr_ctx = Mock()

    # Should not check installation
    on_before_agent_provisioning(agent, host, options, mngr_ctx)

    # No host methods should be called
    host.execute_command.assert_not_called()


def test_on_before_provisioning_skips_when_command_override_provided() -> None:
    """on_before_agent_provisioning should skip check when command override is provided."""
    agent = Mock()
    agent.agent_type = AgentTypeName("claude")
    agent.agent_config = ClaudeAgentConfig(check_installation=True)
    host = Mock()
    options = Mock()
    options.command = CommandString("custom-command")
    mngr_ctx = Mock()

    # Should not check installation because command is overridden
    on_before_agent_provisioning(agent, host, options, mngr_ctx)

    # No host methods should be called
    host.execute_command.assert_not_called()


def test_get_provision_file_transfers_returns_none_for_non_claude() -> None:
    """get_provision_file_transfers should return None for non-claude agents."""
    agent = Mock()
    agent.agent_type = AgentTypeName("codex")
    host = Mock()
    options = Mock()
    mngr_ctx = Mock()

    result = get_provision_file_transfers(agent, host, options, mngr_ctx)

    assert result is None


def test_get_provision_file_transfers_returns_empty_by_default() -> None:
    """get_provision_file_transfers should return empty list when no override folder configured."""
    agent = Mock()
    agent.agent_type = AgentTypeName("claude")
    agent.agent_config = ClaudeAgentConfig(override_settings_folder=None)
    host = Mock()
    options = Mock()
    mngr_ctx = Mock()

    result = get_provision_file_transfers(agent, host, options, mngr_ctx)

    assert result == []


def test_get_provision_file_transfers_includes_override_folder_files(tmp_path: Path) -> None:
    """get_provision_file_transfers should include files from override_settings_folder."""
    # Create a temp folder with some files
    override_folder = tmp_path / "override"
    override_folder.mkdir()
    (override_folder / "settings.json").write_text('{"key": "value"}')

    agent = Mock()
    agent.agent_type = AgentTypeName("claude")
    agent.agent_config = ClaudeAgentConfig(override_settings_folder=override_folder)
    host = Mock()
    options = Mock()
    mngr_ctx = Mock()

    result = get_provision_file_transfers(agent, host, options, mngr_ctx)

    assert result is not None
    assert len(result) == 1
    assert result[0].local_path == override_folder / "settings.json"
    assert str(result[0].agent_path) == ".claude/settings.json"
    assert result[0].is_required is False


def test_provision_agent_skips_non_claude_agents() -> None:
    """provision_agent should do nothing for non-claude agents."""
    agent = Mock()
    agent.agent_type = AgentTypeName("codex")
    host = Mock()
    options = Mock()
    mngr_ctx = Mock()

    provision_agent(agent, host, options, mngr_ctx)

    # No host methods should be called
    host.execute_command.assert_not_called()


def test_provision_agent_skips_when_command_override_provided() -> None:
    """provision_agent should skip when command override is provided."""
    agent = Mock()
    agent.agent_type = AgentTypeName("claude")
    agent.agent_config = ClaudeAgentConfig()
    host = Mock()
    options = Mock()
    options.command = CommandString("custom-command")
    mngr_ctx = Mock()

    provision_agent(agent, host, options, mngr_ctx)

    # No host methods should be called
    host.execute_command.assert_not_called()


def test_provision_agent_skips_file_transfer_for_local_host() -> None:
    """provision_agent should skip file transfers for local hosts."""
    agent = Mock()
    agent.agent_type = AgentTypeName("claude")
    agent.agent_config = ClaudeAgentConfig(check_installation=False)
    host = Mock()
    host.is_local = True
    options = Mock()
    options.command = None
    mngr_ctx = Mock()

    provision_agent(agent, host, options, mngr_ctx)

    # write_text_file should not be called for local hosts
    host.write_text_file.assert_not_called()


def test_provision_agent_uses_tilde_for_remote_paths(tmp_path: Path) -> None:
    """provision_agent should use ~ for remote paths so they expand correctly."""
    # Create a fake home directory with .claude.json
    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    claude_json = fake_home / ".claude.json"
    claude_json.write_text('{"key": "value"}')

    agent = Mock()
    agent.agent_type = AgentTypeName("claude")
    agent.agent_config = ClaudeAgentConfig(
        check_installation=False,
        sync_home_settings=False,
        sync_claude_json=True,
        sync_claude_credentials=False,
    )
    host = Mock()
    host.is_local = False
    options = Mock()
    options.command = None
    mngr_ctx = Mock()

    # Patch Path.home to return our fake home directory
    with patch.object(Path, "home", return_value=fake_home):
        provision_agent(agent, host, options, mngr_ctx)

        # Check that write_text_file was called with ~ path
        assert host.write_text_file.called, "write_text_file should be called"
        call_args = host.write_text_file.call_args
        remote_path = call_args[0][0]
        # The path should start with ~ not the local home
        assert str(remote_path).startswith("~"), (
            f"Remote path should use ~ but got: {remote_path}"
        )
