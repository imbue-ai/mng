"""Additional unit tests for claude_agent.py to improve coverage."""

from datetime import datetime
from datetime import timezone
from pathlib import Path
from unittest.mock import Mock
from unittest.mock import patch

import pluggy
import pytest

from imbue.mngr.agents.default_plugins.claude_agent import ClaudeAgent
from imbue.mngr.agents.default_plugins.claude_agent import ClaudeAgentConfig
from imbue.mngr.agents.default_plugins.claude_agent import _check_claude_installed
from imbue.mngr.agents.default_plugins.claude_agent import _install_claude
from imbue.mngr.agents.default_plugins.claude_agent import _prompt_user_for_installation
from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import PluginMngrError
from imbue.mngr.interfaces.data_types import CommandResult
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.primitives import HostId

# =============================================================================
# Tests for _check_claude_installed
# =============================================================================


def test_check_claude_installed_returns_true_when_command_succeeds() -> None:
    """_check_claude_installed should return True when command result success is True."""
    mock_host = Mock()
    mock_host.execute_command.return_value = CommandResult(
        stdout="/usr/local/bin/claude",
        stderr="",
        success=True,
    )

    result = _check_claude_installed(mock_host)

    assert result is True
    mock_host.execute_command.assert_called_once_with("command -v claude", timeout_seconds=10.0)


def test_check_claude_installed_returns_false_when_command_fails() -> None:
    """_check_claude_installed should return False when command result success is False."""
    mock_host = Mock()
    mock_host.execute_command.return_value = CommandResult(
        stdout="",
        stderr="",
        success=False,
    )

    result = _check_claude_installed(mock_host)

    assert result is False
    mock_host.execute_command.assert_called_once_with("command -v claude", timeout_seconds=10.0)


# =============================================================================
# Tests for _install_claude
# =============================================================================


def test_install_claude_raises_plugin_mngr_error_on_failure() -> None:
    """_install_claude should raise PluginMngrError with stderr when installation fails."""
    mock_host = Mock()
    mock_host.execute_command.return_value = CommandResult(
        stdout="",
        stderr="Connection refused: unable to download installer",
        success=False,
    )

    with pytest.raises(PluginMngrError) as exc_info:
        _install_claude(mock_host)

    assert "Failed to install claude" in str(exc_info.value)
    assert "Connection refused: unable to download installer" in str(exc_info.value)


def test_install_claude_does_not_raise_on_success() -> None:
    """_install_claude should not raise when installation succeeds."""
    mock_host = Mock()
    mock_host.execute_command.return_value = CommandResult(
        stdout="Claude installed successfully",
        stderr="",
        success=True,
    )

    # Should not raise
    _install_claude(mock_host)

    # Verify the install command was called with 300 second timeout
    mock_host.execute_command.assert_called_once()
    call_args = mock_host.execute_command.call_args
    assert call_args[1]["timeout_seconds"] == 300.0


# =============================================================================
# Tests for _prompt_user_for_installation
# =============================================================================


def test_prompt_user_for_installation_returns_true_when_user_confirms() -> None:
    """_prompt_user_for_installation should return True when user confirms."""
    with patch("imbue.mngr.agents.default_plugins.claude_agent.click.confirm", return_value=True):
        result = _prompt_user_for_installation()

    assert result is True


def test_prompt_user_for_installation_returns_false_when_user_declines() -> None:
    """_prompt_user_for_installation should return False when user declines."""
    with patch("imbue.mngr.agents.default_plugins.claude_agent.click.confirm", return_value=False):
        result = _prompt_user_for_installation()

    assert result is False


# =============================================================================
# Tests for provision() - claude already installed
# =============================================================================


def test_provision_does_not_install_when_claude_already_installed(mngr_test_prefix: str) -> None:
    """provision should not attempt installation when claude is already installed."""
    pm = pluggy.PluginManager("mngr")
    agent_id = AgentId.generate()
    mock_host = Mock()
    mock_host.is_local = True
    # First call checks if installed (success=True means installed)
    mock_host.execute_command.return_value = CommandResult(
        stdout="/usr/local/bin/claude",
        stderr="",
        success=True,
    )
    mngr_ctx = MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm)

    agent = ClaudeAgent.model_construct(
        id=agent_id,
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("claude"),
        work_dir=Path("/tmp/work"),
        create_time=datetime.now(timezone.utc),
        host_id=HostId.generate(),
        mngr_ctx=mngr_ctx,
        agent_config=ClaudeAgentConfig(check_installation=True),
        host=mock_host,
    )

    options = Mock()

    agent.provision(host=mock_host, options=options, mngr_ctx=mngr_ctx)

    # Should only call execute_command once (for the check), not for installation
    assert mock_host.execute_command.call_count == 1
    mock_host.execute_command.assert_called_with("command -v claude", timeout_seconds=10.0)


# =============================================================================
# Tests for provision() - user rejection on local host
# =============================================================================


def test_provision_raises_when_user_declines_installation_on_local_host(mngr_test_prefix: str) -> None:
    """provision should raise PluginMngrError when user declines installation on local host."""
    pm = pluggy.PluginManager("mngr")
    agent_id = AgentId.generate()
    mock_host = Mock()
    mock_host.is_local = True
    # Claude is not installed
    mock_host.execute_command.return_value = CommandResult(
        stdout="",
        stderr="",
        success=False,
    )
    mngr_ctx = MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm, is_interactive=True)

    agent = ClaudeAgent.model_construct(
        id=agent_id,
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("claude"),
        work_dir=Path("/tmp/work"),
        create_time=datetime.now(timezone.utc),
        host_id=HostId.generate(),
        mngr_ctx=mngr_ctx,
        agent_config=ClaudeAgentConfig(check_installation=True),
        host=mock_host,
    )

    options = Mock()

    # User declines installation
    with patch(
        "imbue.mngr.agents.default_plugins.claude_agent._prompt_user_for_installation",
        return_value=False,
    ):
        with pytest.raises(PluginMngrError) as exc_info:
            agent.provision(host=mock_host, options=options, mngr_ctx=mngr_ctx)

    assert "Claude is not installed" in str(exc_info.value)
    assert "curl -fsSL https://claude.ai/install.sh" in str(exc_info.value)


def test_provision_raises_in_non_interactive_mode_when_not_installed(mngr_test_prefix: str) -> None:
    """provision should raise PluginMngrError in non-interactive mode when claude not installed."""
    pm = pluggy.PluginManager("mngr")
    agent_id = AgentId.generate()
    mock_host = Mock()
    mock_host.is_local = True
    # Claude is not installed
    mock_host.execute_command.return_value = CommandResult(
        stdout="",
        stderr="",
        success=False,
    )
    mngr_ctx = MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm, is_interactive=False)

    agent = ClaudeAgent.model_construct(
        id=agent_id,
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("claude"),
        work_dir=Path("/tmp/work"),
        create_time=datetime.now(timezone.utc),
        host_id=HostId.generate(),
        mngr_ctx=mngr_ctx,
        agent_config=ClaudeAgentConfig(check_installation=True),
        host=mock_host,
    )

    options = Mock()

    with pytest.raises(PluginMngrError) as exc_info:
        agent.provision(host=mock_host, options=options, mngr_ctx=mngr_ctx)

    assert "Claude is not installed" in str(exc_info.value)


# =============================================================================
# Tests for get_provision_file_transfers - relative path calculation
# =============================================================================


def test_get_provision_file_transfers_calculates_relative_paths_correctly(
    mngr_test_prefix: str, tmp_path: Path
) -> None:
    """get_provision_file_transfers should calculate relative paths from work_dir correctly."""
    pm = pluggy.PluginManager("mngr")
    agent_id = AgentId.generate()
    mock_host = Mock()
    mngr_ctx = MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm)

    # Create a .claude directory with local settings files
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    settings_file = claude_dir / "settings.local.json"
    settings_file.write_text('{"setting": "value"}')

    # Create a nested local file
    nested_dir = claude_dir / "nested"
    nested_dir.mkdir()
    nested_file = nested_dir / "config.local.toml"
    nested_file.write_text("key = 'value'")

    agent = ClaudeAgent.model_construct(
        id=agent_id,
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("claude"),
        work_dir=tmp_path,
        create_time=datetime.now(timezone.utc),
        host_id=HostId.generate(),
        mngr_ctx=mngr_ctx,
        agent_config=ClaudeAgentConfig(sync_repo_settings=True),
        host=mock_host,
    )

    options = Mock()

    transfers = list(agent.get_provision_file_transfers(host=mock_host, options=options, mngr_ctx=mngr_ctx))

    # Should have 2 transfers for the .local. files
    assert len(transfers) == 2

    # Check that paths are relative to work_dir
    transfer_paths = {str(t.agent_path) for t in transfers}
    assert ".claude/settings.local.json" in transfer_paths
    assert ".claude/nested/config.local.toml" in transfer_paths

    # Check that local paths are absolute
    for transfer in transfers:
        assert transfer.local_path.is_absolute()
        assert transfer.is_required is True


def test_get_provision_file_transfers_with_override_folder_nested_files(mngr_test_prefix: str, tmp_path: Path) -> None:
    """get_provision_file_transfers should handle nested files in override folder."""
    pm = pluggy.PluginManager("mngr")
    agent_id = AgentId.generate()
    mock_host = Mock()
    mngr_ctx = MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm)

    # Create override folder with nested structure
    override_folder = tmp_path / "override"
    override_folder.mkdir()

    # Create files at different nesting levels
    root_file = override_folder / "root.json"
    root_file.write_text("{}")

    subdir = override_folder / "subdir"
    subdir.mkdir()
    nested_file = subdir / "nested.json"
    nested_file.write_text("{}")

    agent = ClaudeAgent.model_construct(
        id=agent_id,
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("claude"),
        work_dir=tmp_path / "work",
        create_time=datetime.now(timezone.utc),
        host_id=HostId.generate(),
        mngr_ctx=mngr_ctx,
        agent_config=ClaudeAgentConfig(
            sync_repo_settings=False,
            override_settings_folder=override_folder,
        ),
        host=mock_host,
    )

    options = Mock()

    transfers = list(agent.get_provision_file_transfers(host=mock_host, options=options, mngr_ctx=mngr_ctx))

    # Should have 2 transfers
    assert len(transfers) == 2

    # Check that remote paths are under .claude/
    transfer_paths = {str(t.agent_path) for t in transfers}
    assert ".claude/root.json" in transfer_paths
    assert ".claude/subdir/nested.json" in transfer_paths

    # All override folder files should be non-required
    for transfer in transfers:
        assert transfer.is_required is False
