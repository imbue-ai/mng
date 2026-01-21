"""Unit tests for the Claude agent plugin."""

from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pluggy
import pytest

from imbue.mngr.agents.default_plugins.claude_agent import ClaudeAgentConfig
from imbue.mngr.agents.default_plugins.claude_agent import _check_claude_installed
from imbue.mngr.agents.default_plugins.claude_agent import _get_claude_config
from imbue.mngr.agents.default_plugins.claude_agent import _is_claude_agent
from imbue.mngr.agents.default_plugins.claude_agent import get_provision_file_transfers
from imbue.mngr.agents.default_plugins.claude_agent import on_before_agent_provisioning
from imbue.mngr.agents.default_plugins.claude_agent import provision_agent
from imbue.mngr.config.data_types import AgentTypeConfig
from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import PluginMngrError
from imbue.mngr.interfaces.data_types import CommandResult
from imbue.mngr.interfaces.host import CreateAgentOptions
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.primitives import CommandString


@pytest.fixture
def mock_agent() -> MagicMock:
    """Create a mock agent."""
    agent = MagicMock()
    agent.agent_type = AgentTypeName("claude")
    agent.agent_config = ClaudeAgentConfig()
    agent.work_dir = Path("/tmp/test-work-dir")
    agent.id = AgentId()
    agent.name = AgentName("test-agent")
    return agent


@pytest.fixture
def mock_non_claude_agent() -> MagicMock:
    """Create a mock non-claude agent."""
    agent = MagicMock()
    agent.agent_type = AgentTypeName("codex")
    agent.agent_config = AgentTypeConfig()
    return agent


@pytest.fixture
def mock_host() -> MagicMock:
    """Create a mock host."""
    host = MagicMock()
    host.is_local = True
    return host


@pytest.fixture
def mock_remote_host() -> MagicMock:
    """Create a mock remote host."""
    host = MagicMock()
    host.is_local = False
    return host


@pytest.fixture
def mock_mngr_ctx() -> MngrContext:
    """Create a mock MngrContext."""
    pm = pluggy.PluginManager("mngr")
    config = MngrConfig()
    return MngrContext(config=config, pm=pm)


@pytest.fixture
def mock_options(tmp_path: Path) -> CreateAgentOptions:
    """Create mock CreateAgentOptions."""
    return CreateAgentOptions(target_path=tmp_path)


def test_is_claude_agent_returns_true_for_claude_agent_type(mock_agent: MagicMock) -> None:
    """Verify _is_claude_agent returns True when agent has claude type."""
    assert _is_claude_agent(mock_agent) is True


def test_is_claude_agent_returns_false_for_non_claude_agent_type(
    mock_non_claude_agent: MagicMock,
) -> None:
    """Verify _is_claude_agent returns False when agent has a different type."""
    assert _is_claude_agent(mock_non_claude_agent) is False


def test_get_claude_config_returns_agent_config_when_claude_config_type(
    mock_agent: MagicMock,
) -> None:
    """Verify _get_claude_config returns the agent's config when it's a ClaudeAgentConfig."""
    result = _get_claude_config(mock_agent)
    assert result is mock_agent.agent_config


def test_get_claude_config_returns_default_when_agent_has_different_config_type(
    mock_non_claude_agent: MagicMock,
) -> None:
    """Verify _get_claude_config returns a default ClaudeAgentConfig for non-claude agents."""
    result = _get_claude_config(mock_non_claude_agent)
    assert isinstance(result, ClaudeAgentConfig)
    assert result.sync_home_claude_settings is True
    assert result.sync_repo_claude_settings is True


def test_check_claude_installed_returns_true_when_command_v_succeeds(
    mock_host: MagicMock,
) -> None:
    """Verify _check_claude_installed returns True when claude binary is found on path."""
    mock_host.execute_command.return_value = CommandResult(
        success=True, stdout="/usr/local/bin/claude", stderr=""
    )
    assert _check_claude_installed(mock_host) is True


def test_check_claude_installed_returns_false_when_command_v_fails(
    mock_host: MagicMock,
) -> None:
    """Verify _check_claude_installed returns False when claude binary is not found."""
    mock_host.execute_command.return_value = CommandResult(
        success=False, stdout="", stderr=""
    )
    assert _check_claude_installed(mock_host) is False


def test_on_before_agent_provisioning_skips_non_claude_agents(
    mock_non_claude_agent: MagicMock,
    mock_host: MagicMock,
    mock_options: CreateAgentOptions,
    mock_mngr_ctx: MngrContext,
) -> None:
    """Verify on_before_agent_provisioning does nothing for non-claude agent types."""
    on_before_agent_provisioning(mock_non_claude_agent, mock_host, mock_options, mock_mngr_ctx)
    mock_host.execute_command.assert_not_called()


def test_on_before_agent_provisioning_skips_when_skip_installation_check_enabled(
    mock_agent: MagicMock,
    mock_host: MagicMock,
    mock_options: CreateAgentOptions,
    mock_mngr_ctx: MngrContext,
) -> None:
    """Verify on_before_agent_provisioning skips check when skip_installation_check=True."""
    mock_agent.agent_config = ClaudeAgentConfig(skip_installation_check=True)
    on_before_agent_provisioning(mock_agent, mock_host, mock_options, mock_mngr_ctx)
    mock_host.execute_command.assert_not_called()


def test_on_before_agent_provisioning_skips_when_command_override_provided(
    mock_agent: MagicMock,
    mock_host: MagicMock,
    mock_mngr_ctx: MngrContext,
    tmp_path: Path,
) -> None:
    """Verify on_before_agent_provisioning skips check when user provides --agent-cmd."""
    options_with_command = CreateAgentOptions(
        target_path=tmp_path,
        command=CommandString("sleep 1000"),
    )
    on_before_agent_provisioning(mock_agent, mock_host, options_with_command, mock_mngr_ctx)
    mock_host.execute_command.assert_not_called()


def test_on_before_agent_provisioning_passes_when_claude_is_already_installed(
    mock_agent: MagicMock,
    mock_host: MagicMock,
    mock_options: CreateAgentOptions,
    mock_mngr_ctx: MngrContext,
) -> None:
    """Verify on_before_agent_provisioning completes without error when claude is installed."""
    mock_host.execute_command.return_value = CommandResult(
        success=True, stdout="/usr/local/bin/claude", stderr=""
    )
    on_before_agent_provisioning(mock_agent, mock_host, mock_options, mock_mngr_ctx)


def test_on_before_agent_provisioning_prompts_user_and_continues_when_user_accepts(
    mock_agent: MagicMock,
    mock_host: MagicMock,
    mock_options: CreateAgentOptions,
    mock_mngr_ctx: MngrContext,
) -> None:
    """Verify on_before_agent_provisioning prompts user on local host and continues if accepted."""
    mock_host.is_local = True
    mock_host.execute_command.return_value = CommandResult(
        success=False, stdout="", stderr=""
    )

    with patch(
        "imbue.mngr.agents.default_plugins.claude_agent._prompt_user_for_installation",
        return_value=True,
    ):
        on_before_agent_provisioning(mock_agent, mock_host, mock_options, mock_mngr_ctx)

    mock_host.execute_command.assert_called_once()


def test_on_before_agent_provisioning_raises_when_user_declines_installation(
    mock_agent: MagicMock,
    mock_host: MagicMock,
    mock_options: CreateAgentOptions,
    mock_mngr_ctx: MngrContext,
) -> None:
    """Verify on_before_agent_provisioning raises error when user declines installation."""
    mock_host.is_local = True
    mock_host.execute_command.return_value = CommandResult(
        success=False, stdout="", stderr=""
    )

    with patch(
        "imbue.mngr.agents.default_plugins.claude_agent._prompt_user_for_installation",
        return_value=False,
    ):
        with pytest.raises(PluginMngrError, match="Claude is not installed"):
            on_before_agent_provisioning(mock_agent, mock_host, mock_options, mock_mngr_ctx)


def test_on_before_agent_provisioning_does_not_prompt_on_remote_host(
    mock_agent: MagicMock,
    mock_remote_host: MagicMock,
    mock_options: CreateAgentOptions,
    mock_mngr_ctx: MngrContext,
) -> None:
    """Verify on_before_agent_provisioning skips prompting on remote hosts."""
    mock_remote_host.execute_command.return_value = CommandResult(
        success=False, stdout="", stderr=""
    )

    with patch(
        "imbue.mngr.agents.default_plugins.claude_agent._prompt_user_for_installation"
    ) as mock_prompt:
        on_before_agent_provisioning(
            mock_agent, mock_remote_host, mock_options, mock_mngr_ctx
        )
        mock_prompt.assert_not_called()


def test_get_provision_file_transfers_returns_none_for_non_claude_agents(
    mock_non_claude_agent: MagicMock,
    mock_host: MagicMock,
    mock_options: CreateAgentOptions,
    mock_mngr_ctx: MngrContext,
) -> None:
    """Verify get_provision_file_transfers returns None for non-claude agent types."""
    result = get_provision_file_transfers(
        mock_non_claude_agent, mock_host, mock_options, mock_mngr_ctx
    )
    assert result is None


def test_get_provision_file_transfers_includes_home_claude_settings_files(
    mock_agent: MagicMock,
    mock_host: MagicMock,
    mock_options: CreateAgentOptions,
    mock_mngr_ctx: MngrContext,
) -> None:
    """Verify get_provision_file_transfers includes home dir settings when enabled."""
    mock_agent.agent_config = ClaudeAgentConfig(
        sync_home_claude_settings=True,
        sync_repo_claude_settings=False,
    )

    result = get_provision_file_transfers(mock_agent, mock_host, mock_options, mock_mngr_ctx)
    assert result is not None

    remote_paths = [str(t.remote_path) for t in result]
    assert any("~/.claude/settings.json" in p for p in remote_paths)
    assert any("statsig_metadata.json" in p for p in remote_paths)


def test_get_provision_file_transfers_includes_repo_local_settings_files(
    mock_agent: MagicMock,
    mock_host: MagicMock,
    mock_options: CreateAgentOptions,
    mock_mngr_ctx: MngrContext,
) -> None:
    """Verify get_provision_file_transfers includes repo .claude/ settings when enabled."""
    mock_agent.agent_config = ClaudeAgentConfig(
        sync_home_claude_settings=False,
        sync_repo_claude_settings=True,
    )

    result = get_provision_file_transfers(mock_agent, mock_host, mock_options, mock_mngr_ctx)
    assert result is not None

    remote_paths = [str(t.remote_path) for t in result]
    assert any("settings.local.json" in p for p in remote_paths)


def test_get_provision_file_transfers_returns_empty_list_when_both_sync_options_disabled(
    mock_agent: MagicMock,
    mock_host: MagicMock,
    mock_options: CreateAgentOptions,
    mock_mngr_ctx: MngrContext,
) -> None:
    """Verify get_provision_file_transfers returns empty list when all sync options disabled."""
    mock_agent.agent_config = ClaudeAgentConfig(
        sync_home_claude_settings=False,
        sync_repo_claude_settings=False,
    )

    result = get_provision_file_transfers(mock_agent, mock_host, mock_options, mock_mngr_ctx)
    assert result is not None
    assert len(result) == 0


def test_get_provision_file_transfers_includes_extra_home_folder_files(
    mock_agent: MagicMock,
    mock_host: MagicMock,
    mock_mngr_ctx: MngrContext,
    tmp_path: Path,
) -> None:
    """Verify get_provision_file_transfers includes files from extra_home_claude_folder."""
    extra_folder = tmp_path / "extra_home"
    extra_folder.mkdir()
    (extra_folder / "custom_settings.json").write_text('{"custom": true}')
    (extra_folder / "subdir").mkdir()
    (extra_folder / "subdir" / "nested_file.txt").write_text("nested")

    mock_agent.agent_config = ClaudeAgentConfig(
        sync_home_claude_settings=False,
        sync_repo_claude_settings=False,
        extra_home_claude_folder=extra_folder,
    )

    mock_options = CreateAgentOptions(target_path=tmp_path)
    result = get_provision_file_transfers(mock_agent, mock_host, mock_options, mock_mngr_ctx)
    assert result is not None

    remote_paths = [str(t.remote_path) for t in result]
    assert any("custom_settings.json" in p for p in remote_paths)
    assert any("nested_file.txt" in p for p in remote_paths)


def test_get_provision_file_transfers_includes_extra_repo_folder_files(
    mock_agent: MagicMock,
    mock_host: MagicMock,
    mock_mngr_ctx: MngrContext,
    tmp_path: Path,
) -> None:
    """Verify get_provision_file_transfers includes files from extra_repo_claude_folder."""
    extra_folder = tmp_path / "extra_repo"
    extra_folder.mkdir()
    (extra_folder / "repo_settings.json").write_text('{"repo": true}')

    mock_agent.agent_config = ClaudeAgentConfig(
        sync_home_claude_settings=False,
        sync_repo_claude_settings=False,
        extra_repo_claude_folder=extra_folder,
    )

    mock_options = CreateAgentOptions(target_path=tmp_path)
    result = get_provision_file_transfers(mock_agent, mock_host, mock_options, mock_mngr_ctx)
    assert result is not None

    remote_paths = [str(t.remote_path) for t in result]
    assert any("repo_settings.json" in p for p in remote_paths)


def test_provision_agent_skips_non_claude_agents(
    mock_non_claude_agent: MagicMock,
    mock_host: MagicMock,
    mock_options: CreateAgentOptions,
    mock_mngr_ctx: MngrContext,
) -> None:
    """Verify provision_agent does nothing for non-claude agent types."""
    provision_agent(mock_non_claude_agent, mock_host, mock_options, mock_mngr_ctx)
    mock_host.execute_command.assert_not_called()


def test_provision_agent_skips_when_skip_installation_check_enabled(
    mock_agent: MagicMock,
    mock_remote_host: MagicMock,
    mock_options: CreateAgentOptions,
    mock_mngr_ctx: MngrContext,
) -> None:
    """Verify provision_agent skips installation when skip_installation_check=True."""
    mock_agent.agent_config = ClaudeAgentConfig(skip_installation_check=True)
    provision_agent(mock_agent, mock_remote_host, mock_options, mock_mngr_ctx)
    mock_remote_host.execute_command.assert_not_called()


def test_provision_agent_skips_when_command_override_provided(
    mock_agent: MagicMock,
    mock_remote_host: MagicMock,
    mock_mngr_ctx: MngrContext,
    tmp_path: Path,
) -> None:
    """Verify provision_agent skips installation when user provides --agent-cmd."""
    options_with_command = CreateAgentOptions(
        target_path=tmp_path,
        command=CommandString("sleep 1000"),
    )
    provision_agent(mock_agent, mock_remote_host, options_with_command, mock_mngr_ctx)
    mock_remote_host.execute_command.assert_not_called()


def test_provision_agent_skips_installation_when_already_installed(
    mock_agent: MagicMock,
    mock_remote_host: MagicMock,
    mock_options: CreateAgentOptions,
    mock_mngr_ctx: MngrContext,
) -> None:
    """Verify provision_agent skips installation when claude is already present."""
    mock_remote_host.execute_command.return_value = CommandResult(
        success=True, stdout="/usr/local/bin/claude", stderr=""
    )
    provision_agent(mock_agent, mock_remote_host, mock_options, mock_mngr_ctx)
    assert mock_remote_host.execute_command.call_count == 1


def test_provision_agent_installs_claude_when_not_present(
    mock_agent: MagicMock,
    mock_remote_host: MagicMock,
    mock_options: CreateAgentOptions,
    mock_mngr_ctx: MngrContext,
) -> None:
    """Verify provision_agent runs installation when claude is not found."""
    mock_remote_host.execute_command.side_effect = [
        CommandResult(success=False, stdout="", stderr=""),
        CommandResult(success=True, stdout="", stderr=""),
    ]

    provision_agent(mock_agent, mock_remote_host, mock_options, mock_mngr_ctx)

    assert mock_remote_host.execute_command.call_count == 2
    install_call = mock_remote_host.execute_command.call_args_list[1]
    assert "curl -fsSL https://claude.ai/install.sh | bash" in install_call[0][0]


def test_provision_agent_installs_claude_on_local_host_when_not_present(
    mock_agent: MagicMock,
    mock_host: MagicMock,
    mock_options: CreateAgentOptions,
    mock_mngr_ctx: MngrContext,
) -> None:
    """Verify provision_agent installs claude on local host when not found."""
    mock_host.is_local = True
    mock_host.execute_command.side_effect = [
        CommandResult(success=False, stdout="", stderr=""),
        CommandResult(success=True, stdout="", stderr=""),
    ]

    provision_agent(mock_agent, mock_host, mock_options, mock_mngr_ctx)

    assert mock_host.execute_command.call_count == 2
    install_call = mock_host.execute_command.call_args_list[1]
    assert "curl -fsSL https://claude.ai/install.sh | bash" in install_call[0][0]


def test_provision_agent_raises_when_installation_fails(
    mock_agent: MagicMock,
    mock_remote_host: MagicMock,
    mock_options: CreateAgentOptions,
    mock_mngr_ctx: MngrContext,
) -> None:
    """Verify provision_agent raises PluginMngrError when installation command fails."""
    mock_remote_host.execute_command.side_effect = [
        CommandResult(success=False, stdout="", stderr=""),
        CommandResult(success=False, stdout="", stderr="install failed"),
    ]

    with pytest.raises(PluginMngrError, match="Failed to install claude"):
        provision_agent(mock_agent, mock_remote_host, mock_options, mock_mngr_ctx)


def test_claude_agent_config_has_expected_default_values() -> None:
    """Verify ClaudeAgentConfig has correct default values."""
    config = ClaudeAgentConfig()
    assert config.command == "claude"
    assert config.sync_home_claude_settings is True
    assert config.sync_repo_claude_settings is True
    assert config.extra_home_claude_folder is None
    assert config.extra_repo_claude_folder is None
    assert config.skip_installation_check is False


def test_claude_agent_config_accepts_custom_values(tmp_path: Path) -> None:
    """Verify ClaudeAgentConfig can be created with custom values."""
    config = ClaudeAgentConfig(
        command=CommandString("custom-claude"),
        sync_home_claude_settings=False,
        sync_repo_claude_settings=False,
        extra_home_claude_folder=tmp_path / "home",
        extra_repo_claude_folder=tmp_path / "repo",
        skip_installation_check=True,
    )
    assert config.command == CommandString("custom-claude")
    assert config.sync_home_claude_settings is False
    assert config.sync_repo_claude_settings is False
    assert config.extra_home_claude_folder == tmp_path / "home"
    assert config.extra_repo_claude_folder == tmp_path / "repo"
    assert config.skip_installation_check is True
