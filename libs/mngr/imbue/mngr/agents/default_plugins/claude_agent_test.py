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


class TestIsClaudeAgent:
    """Tests for _is_claude_agent function."""

    def test_returns_true_for_claude_agent(self, mock_agent: MagicMock) -> None:
        """Test that _is_claude_agent returns True for claude agents."""
        assert _is_claude_agent(mock_agent) is True

    def test_returns_false_for_non_claude_agent(self, mock_non_claude_agent: MagicMock) -> None:
        """Test that _is_claude_agent returns False for non-claude agents."""
        assert _is_claude_agent(mock_non_claude_agent) is False


class TestGetClaudeConfig:
    """Tests for _get_claude_config function."""

    def test_returns_config_when_agent_has_claude_config(self, mock_agent: MagicMock) -> None:
        """Test that _get_claude_config returns the agent's config when it's a ClaudeAgentConfig."""
        result = _get_claude_config(mock_agent)
        assert result is mock_agent.agent_config

    def test_returns_default_config_when_agent_has_different_config(
        self, mock_non_claude_agent: MagicMock
    ) -> None:
        """Test that _get_claude_config returns a default config when agent has a different config type."""
        result = _get_claude_config(mock_non_claude_agent)
        assert isinstance(result, ClaudeAgentConfig)
        # Should be a new default instance
        assert result.sync_home_claude_settings is True
        assert result.sync_repo_claude_settings is True


class TestCheckClaudeInstalled:
    """Tests for _check_claude_installed function."""

    def test_returns_true_when_claude_is_installed(self, mock_host: MagicMock) -> None:
        """Test that _check_claude_installed returns True when claude is on the path."""
        mock_host.execute_command.return_value = CommandResult(
            success=True, stdout="/usr/local/bin/claude", stderr=""
        )
        assert _check_claude_installed(mock_host) is True

    def test_returns_false_when_claude_is_not_installed(self, mock_host: MagicMock) -> None:
        """Test that _check_claude_installed returns False when claude is not on the path."""
        mock_host.execute_command.return_value = CommandResult(
            success=False, stdout="", stderr=""
        )
        assert _check_claude_installed(mock_host) is False


class TestOnBeforeAgentProvisioning:
    """Tests for on_before_agent_provisioning hook."""

    def test_skips_non_claude_agents(
        self,
        mock_non_claude_agent: MagicMock,
        mock_host: MagicMock,
        mock_options: CreateAgentOptions,
        mock_mngr_ctx: MngrContext,
    ) -> None:
        """Test that non-claude agents are skipped."""
        # Should not raise and should not check installation
        on_before_agent_provisioning(mock_non_claude_agent, mock_host, mock_options, mock_mngr_ctx)
        mock_host.execute_command.assert_not_called()

    def test_skips_when_skip_installation_check_is_true(
        self,
        mock_agent: MagicMock,
        mock_host: MagicMock,
        mock_options: CreateAgentOptions,
        mock_mngr_ctx: MngrContext,
    ) -> None:
        """Test that installation check is skipped when skip_installation_check=True."""
        mock_agent.agent_config = ClaudeAgentConfig(skip_installation_check=True)
        on_before_agent_provisioning(mock_agent, mock_host, mock_options, mock_mngr_ctx)
        mock_host.execute_command.assert_not_called()

    def test_skips_when_command_override_provided(
        self,
        mock_agent: MagicMock,
        mock_host: MagicMock,
        mock_mngr_ctx: MngrContext,
        tmp_path: Path,
    ) -> None:
        """Test that installation check is skipped when command override is provided."""
        options_with_command = CreateAgentOptions(
            target_path=tmp_path,
            command=CommandString("sleep 1000"),
        )
        on_before_agent_provisioning(mock_agent, mock_host, options_with_command, mock_mngr_ctx)
        mock_host.execute_command.assert_not_called()

    def test_passes_when_claude_is_installed(
        self,
        mock_agent: MagicMock,
        mock_host: MagicMock,
        mock_options: CreateAgentOptions,
        mock_mngr_ctx: MngrContext,
    ) -> None:
        """Test that validation passes when claude is installed."""
        mock_host.execute_command.return_value = CommandResult(
            success=True, stdout="/usr/local/bin/claude", stderr=""
        )
        # Should not raise
        on_before_agent_provisioning(mock_agent, mock_host, mock_options, mock_mngr_ctx)

    def test_prompts_user_on_local_host_when_not_installed(
        self,
        mock_agent: MagicMock,
        mock_host: MagicMock,
        mock_options: CreateAgentOptions,
        mock_mngr_ctx: MngrContext,
    ) -> None:
        """Test that user is prompted on local host when claude is not installed."""
        mock_host.is_local = True
        # First call: check if installed (returns False)
        # Second call: install (if user confirms)
        mock_host.execute_command.side_effect = [
            CommandResult(success=False, stdout="", stderr=""),
            CommandResult(success=True, stdout="", stderr=""),
        ]

        with patch(
            "imbue.mngr.agents.default_plugins.claude_agent._prompt_user_for_installation",
            return_value=True,
        ):
            on_before_agent_provisioning(mock_agent, mock_host, mock_options, mock_mngr_ctx)

        # Should have called execute_command twice (check + install)
        assert mock_host.execute_command.call_count == 2

    def test_raises_when_user_declines_installation_on_local_host(
        self,
        mock_agent: MagicMock,
        mock_host: MagicMock,
        mock_options: CreateAgentOptions,
        mock_mngr_ctx: MngrContext,
    ) -> None:
        """Test that error is raised when user declines installation on local host."""
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

    def test_does_not_prompt_on_remote_host_when_not_installed(
        self,
        mock_agent: MagicMock,
        mock_remote_host: MagicMock,
        mock_options: CreateAgentOptions,
        mock_mngr_ctx: MngrContext,
    ) -> None:
        """Test that remote hosts do not prompt user (installation happens in provision_agent)."""
        mock_remote_host.execute_command.return_value = CommandResult(
            success=False, stdout="", stderr=""
        )

        with patch(
            "imbue.mngr.agents.default_plugins.claude_agent._prompt_user_for_installation"
        ) as mock_prompt:
            # Should not raise and should not prompt
            on_before_agent_provisioning(
                mock_agent, mock_remote_host, mock_options, mock_mngr_ctx
            )
            mock_prompt.assert_not_called()


class TestGetProvisionFileTransfers:
    """Tests for get_provision_file_transfers hook."""

    def test_returns_none_for_non_claude_agents(
        self,
        mock_non_claude_agent: MagicMock,
        mock_host: MagicMock,
        mock_options: CreateAgentOptions,
        mock_mngr_ctx: MngrContext,
    ) -> None:
        """Test that None is returned for non-claude agents."""
        result = get_provision_file_transfers(
            mock_non_claude_agent, mock_host, mock_options, mock_mngr_ctx
        )
        assert result is None

    def test_returns_transfers_for_home_settings_when_enabled(
        self,
        mock_agent: MagicMock,
        mock_host: MagicMock,
        mock_options: CreateAgentOptions,
        mock_mngr_ctx: MngrContext,
    ) -> None:
        """Test that home settings transfers are included when sync_home_claude_settings=True."""
        mock_agent.agent_config = ClaudeAgentConfig(
            sync_home_claude_settings=True,
            sync_repo_claude_settings=False,
        )

        result = get_provision_file_transfers(mock_agent, mock_host, mock_options, mock_mngr_ctx)
        assert result is not None

        # Should have transfers for home settings files
        remote_paths = [str(t.remote_path) for t in result]
        assert any("~/.claude/settings.json" in p for p in remote_paths)
        assert any("statsig_metadata.json" in p for p in remote_paths)

    def test_returns_transfers_for_repo_settings_when_enabled(
        self,
        mock_agent: MagicMock,
        mock_host: MagicMock,
        mock_options: CreateAgentOptions,
        mock_mngr_ctx: MngrContext,
    ) -> None:
        """Test that repo settings transfers are included when sync_repo_claude_settings=True."""
        mock_agent.agent_config = ClaudeAgentConfig(
            sync_home_claude_settings=False,
            sync_repo_claude_settings=True,
        )

        result = get_provision_file_transfers(mock_agent, mock_host, mock_options, mock_mngr_ctx)
        assert result is not None

        # Should have transfers for repo settings files
        remote_paths = [str(t.remote_path) for t in result]
        assert any("settings.local.json" in p for p in remote_paths)

    def test_returns_no_transfers_when_both_disabled(
        self,
        mock_agent: MagicMock,
        mock_host: MagicMock,
        mock_options: CreateAgentOptions,
        mock_mngr_ctx: MngrContext,
    ) -> None:
        """Test that no transfers are returned when both settings are disabled."""
        mock_agent.agent_config = ClaudeAgentConfig(
            sync_home_claude_settings=False,
            sync_repo_claude_settings=False,
        )

        result = get_provision_file_transfers(mock_agent, mock_host, mock_options, mock_mngr_ctx)
        assert result is not None
        assert len(result) == 0

    def test_includes_extra_home_folder_contents(
        self,
        mock_agent: MagicMock,
        mock_host: MagicMock,
        mock_mngr_ctx: MngrContext,
        tmp_path: Path,
    ) -> None:
        """Test that extra home folder contents are included in transfers."""
        # Create a temporary extra folder with some files
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

    def test_includes_extra_repo_folder_contents(
        self,
        mock_agent: MagicMock,
        mock_host: MagicMock,
        mock_mngr_ctx: MngrContext,
        tmp_path: Path,
    ) -> None:
        """Test that extra repo folder contents are included in transfers."""
        # Create a temporary extra folder with some files
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


class TestProvisionAgent:
    """Tests for provision_agent hook."""

    def test_skips_non_claude_agents(
        self,
        mock_non_claude_agent: MagicMock,
        mock_host: MagicMock,
        mock_options: CreateAgentOptions,
        mock_mngr_ctx: MngrContext,
    ) -> None:
        """Test that non-claude agents are skipped."""
        provision_agent(mock_non_claude_agent, mock_host, mock_options, mock_mngr_ctx)
        mock_host.execute_command.assert_not_called()

    def test_skips_when_skip_installation_check_is_true(
        self,
        mock_agent: MagicMock,
        mock_remote_host: MagicMock,
        mock_options: CreateAgentOptions,
        mock_mngr_ctx: MngrContext,
    ) -> None:
        """Test that installation is skipped when skip_installation_check=True."""
        mock_agent.agent_config = ClaudeAgentConfig(skip_installation_check=True)
        provision_agent(mock_agent, mock_remote_host, mock_options, mock_mngr_ctx)
        mock_remote_host.execute_command.assert_not_called()

    def test_skips_when_command_override_provided(
        self,
        mock_agent: MagicMock,
        mock_remote_host: MagicMock,
        mock_mngr_ctx: MngrContext,
        tmp_path: Path,
    ) -> None:
        """Test that installation is skipped when command override is provided."""
        options_with_command = CreateAgentOptions(
            target_path=tmp_path,
            command=CommandString("sleep 1000"),
        )
        provision_agent(mock_agent, mock_remote_host, options_with_command, mock_mngr_ctx)
        mock_remote_host.execute_command.assert_not_called()

    def test_skips_local_hosts(
        self,
        mock_agent: MagicMock,
        mock_host: MagicMock,
        mock_options: CreateAgentOptions,
        mock_mngr_ctx: MngrContext,
    ) -> None:
        """Test that local hosts are skipped (installation handled in on_before_agent_provisioning)."""
        mock_host.is_local = True
        provision_agent(mock_agent, mock_host, mock_options, mock_mngr_ctx)
        mock_host.execute_command.assert_not_called()

    def test_skips_when_already_installed_on_remote(
        self,
        mock_agent: MagicMock,
        mock_remote_host: MagicMock,
        mock_options: CreateAgentOptions,
        mock_mngr_ctx: MngrContext,
    ) -> None:
        """Test that installation is skipped when claude is already installed on remote."""
        mock_remote_host.execute_command.return_value = CommandResult(
            success=True, stdout="/usr/local/bin/claude", stderr=""
        )
        provision_agent(mock_agent, mock_remote_host, mock_options, mock_mngr_ctx)
        # Only the check command should be called
        assert mock_remote_host.execute_command.call_count == 1

    def test_installs_on_remote_when_not_installed(
        self,
        mock_agent: MagicMock,
        mock_remote_host: MagicMock,
        mock_options: CreateAgentOptions,
        mock_mngr_ctx: MngrContext,
    ) -> None:
        """Test that claude is installed on remote host when not present."""
        # First call: check if installed (returns False)
        # Second call: install command
        mock_remote_host.execute_command.side_effect = [
            CommandResult(success=False, stdout="", stderr=""),
            CommandResult(success=True, stdout="", stderr=""),
        ]

        provision_agent(mock_agent, mock_remote_host, mock_options, mock_mngr_ctx)

        # Should have called execute_command twice (check + install)
        assert mock_remote_host.execute_command.call_count == 2
        # Check that install command was called
        install_call = mock_remote_host.execute_command.call_args_list[1]
        assert "curl -fsSL https://claude.ai/install.sh | bash" in install_call[0][0]

    def test_raises_when_installation_fails_on_remote(
        self,
        mock_agent: MagicMock,
        mock_remote_host: MagicMock,
        mock_options: CreateAgentOptions,
        mock_mngr_ctx: MngrContext,
    ) -> None:
        """Test that error is raised when installation fails on remote host."""
        mock_remote_host.execute_command.side_effect = [
            CommandResult(success=False, stdout="", stderr=""),
            CommandResult(success=False, stdout="", stderr="install failed"),
        ]

        with pytest.raises(PluginMngrError, match="Failed to install claude"):
            provision_agent(mock_agent, mock_remote_host, mock_options, mock_mngr_ctx)


class TestClaudeAgentConfig:
    """Tests for ClaudeAgentConfig."""

    def test_default_values(self) -> None:
        """Test that default values are set correctly."""
        config = ClaudeAgentConfig()
        assert config.command == "claude"
        assert config.sync_home_claude_settings is True
        assert config.sync_repo_claude_settings is True
        assert config.extra_home_claude_folder is None
        assert config.extra_repo_claude_folder is None
        assert config.skip_installation_check is False

    def test_can_set_custom_values(self, tmp_path: Path) -> None:
        """Test that custom values can be set."""
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
