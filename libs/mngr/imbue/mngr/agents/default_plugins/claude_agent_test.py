import json
from datetime import datetime
from datetime import timezone
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pluggy
import pytest

from imbue.mngr.agents.default_plugins.claude_agent import ClaudeAgent
from imbue.mngr.agents.default_plugins.claude_agent import ClaudeAgentConfig
from imbue.mngr.agents.default_plugins.claude_agent import _build_readiness_hooks_config
from imbue.mngr.config.data_types import AgentTypeConfig
from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.config.data_types import PROFILES_DIRNAME
from imbue.mngr.errors import NoCommandDefinedError
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import HostId


@pytest.fixture
def temp_profile_dir(tmp_path: Path) -> Path:
    profile_dir = tmp_path / PROFILES_DIRNAME / uuid4().hex
    profile_dir.mkdir(parents=True, exist_ok=True)
    return profile_dir


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


def test_claude_agent_assemble_command_with_no_args(mngr_test_prefix: str, temp_profile_dir: Path) -> None:
    """ClaudeAgent should generate resume/session-id command format with no args."""
    pm = pluggy.PluginManager("mngr")
    agent_id = AgentId.generate()
    mock_host = Mock()
    mock_host.is_local = True

    agent = ClaudeAgent.model_construct(
        id=agent_id,
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("claude"),
        work_dir=Path("/tmp/work"),
        create_time=datetime.now(timezone.utc),
        host_id=HostId.generate(),
        mngr_ctx=MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm, profile_dir=temp_profile_dir),
        agent_config=ClaudeAgentConfig(),
        host=mock_host,
    )

    command = agent.assemble_command(host=mock_host, agent_args=(), command_override=None)

    uuid = agent_id.get_uuid()
    # Local hosts should NOT have IS_SANDBOX set
    assert command == CommandString(
        f"export MAIN_CLAUDE_SESSION_ID={uuid} && ( ( find ~/.claude/ -name '{uuid}' | grep . ) && claude --resume {uuid} ) || claude --session-id {uuid}"
    )


# FIXME: many of these tests contain duplicated code. Please factor it out into fixtures and/or helpers.
def test_claude_agent_assemble_command_with_agent_args(mngr_test_prefix: str, temp_profile_dir: Path) -> None:
    """ClaudeAgent should append agent args to both command variants."""
    pm = pluggy.PluginManager("mngr")
    agent_id = AgentId.generate()
    mock_host = Mock()
    mock_host.is_local = True

    agent = ClaudeAgent.model_construct(
        id=agent_id,
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("claude"),
        work_dir=Path("/tmp/work"),
        create_time=datetime.now(timezone.utc),
        host_id=HostId.generate(),
        mngr_ctx=MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm, profile_dir=temp_profile_dir),
        agent_config=ClaudeAgentConfig(),
        host=mock_host,
    )

    command = agent.assemble_command(host=mock_host, agent_args=("--model", "opus"), command_override=None)

    uuid = agent_id.get_uuid()
    assert command == CommandString(
        f"export MAIN_CLAUDE_SESSION_ID={uuid} && ( ( find ~/.claude/ -name '{uuid}' | grep . ) && claude --resume {uuid} --model opus ) || claude --session-id {uuid} --model opus"
    )


def test_claude_agent_assemble_command_with_cli_args_and_agent_args(
    mngr_test_prefix: str, temp_profile_dir: Path
) -> None:
    """ClaudeAgent should append both cli_args and agent_args to both command variants."""
    pm = pluggy.PluginManager("mngr")
    agent_id = AgentId.generate()
    mock_host = Mock()
    mock_host.is_local = True

    agent = ClaudeAgent.model_construct(
        id=agent_id,
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("claude"),
        work_dir=Path("/tmp/work"),
        create_time=datetime.now(timezone.utc),
        host_id=HostId.generate(),
        mngr_ctx=MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm, profile_dir=temp_profile_dir),
        agent_config=ClaudeAgentConfig(cli_args="--verbose"),
        host=mock_host,
    )

    command = agent.assemble_command(host=mock_host, agent_args=("--model", "opus"), command_override=None)

    uuid = agent_id.get_uuid()
    assert command == CommandString(
        f"export MAIN_CLAUDE_SESSION_ID={uuid} && ( ( find ~/.claude/ -name '{uuid}' | grep . ) && claude --resume {uuid} --verbose --model opus ) || claude --session-id {uuid} --verbose --model opus"
    )


def test_claude_agent_assemble_command_with_command_override(mngr_test_prefix: str, temp_profile_dir: Path) -> None:
    """ClaudeAgent should use command override when provided."""
    pm = pluggy.PluginManager("mngr")
    agent_id = AgentId.generate()
    mock_host = Mock()
    mock_host.is_local = True

    agent = ClaudeAgent.model_construct(
        id=agent_id,
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("claude"),
        work_dir=Path("/tmp/work"),
        create_time=datetime.now(timezone.utc),
        host_id=HostId.generate(),
        mngr_ctx=MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm, profile_dir=temp_profile_dir),
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
        f"export MAIN_CLAUDE_SESSION_ID={uuid} && ( ( find ~/.claude/ -name '{uuid}' | grep . ) && custom-claude --resume {uuid} --model opus ) || custom-claude --session-id {uuid} --model opus"
    )


def test_claude_agent_assemble_command_raises_when_no_command(mngr_test_prefix: str, temp_profile_dir: Path) -> None:
    """ClaudeAgent should raise NoCommandDefinedError when no command defined."""
    pm = pluggy.PluginManager("mngr")
    agent_id = AgentId.generate()
    mock_host = Mock()
    mock_host.is_local = True

    # Create agent with no command configured
    agent = ClaudeAgent.model_construct(
        id=agent_id,
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("custom"),
        work_dir=Path("/tmp/work"),
        create_time=datetime.now(timezone.utc),
        host_id=HostId.generate(),
        mngr_ctx=MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm, profile_dir=temp_profile_dir),
        agent_config=AgentTypeConfig(),
        host=mock_host,
    )

    with pytest.raises(NoCommandDefinedError, match="No command defined"):
        agent.assemble_command(host=mock_host, agent_args=(), command_override=None)


def test_claude_agent_assemble_command_sets_is_sandbox_for_remote_host(
    mngr_test_prefix: str, temp_profile_dir: Path
) -> None:
    """ClaudeAgent should set IS_SANDBOX=1 only for remote (non-local) hosts."""
    pm = pluggy.PluginManager("mngr")
    agent_id = AgentId.generate()
    mock_host = Mock()
    mock_host.is_local = False

    agent = ClaudeAgent.model_construct(
        id=agent_id,
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("claude"),
        work_dir=Path("/tmp/work"),
        create_time=datetime.now(timezone.utc),
        host_id=HostId.generate(),
        mngr_ctx=MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm, profile_dir=temp_profile_dir),
        agent_config=ClaudeAgentConfig(),
        host=mock_host,
    )

    command = agent.assemble_command(host=mock_host, agent_args=(), command_override=None)

    uuid = agent_id.get_uuid()
    # Remote hosts SHOULD have IS_SANDBOX set
    assert command == CommandString(
        f"export IS_SANDBOX=1 && export MAIN_CLAUDE_SESSION_ID={uuid} && ( ( find ~/.claude/ -name '{uuid}' | grep . ) && claude --resume {uuid} ) || claude --session-id {uuid}"
    )


def test_claude_agent_config_merge_uses_override_cli_args_when_base_empty() -> None:
    """ClaudeAgentConfig merge should use override cli_args when base is empty."""
    base = ClaudeAgentConfig()
    override = ClaudeAgentConfig(cli_args="--verbose")

    merged = base.merge_with(override)

    assert merged.cli_args == "--verbose"


def test_get_claude_config_returns_config_when_claude_agent_config(
    mngr_test_prefix: str, temp_profile_dir: Path
) -> None:
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
        mngr_ctx=MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm, profile_dir=temp_profile_dir),
        agent_config=config,
        host=Mock(),
    )

    result = agent._get_claude_config()

    assert result is config
    assert result.cli_args == "--verbose"


def test_get_claude_config_returns_default_when_not_claude_agent_config(
    mngr_test_prefix: str, temp_profile_dir: Path
) -> None:
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
        mngr_ctx=MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm, profile_dir=temp_profile_dir),
        agent_config=AgentTypeConfig(),
        host=Mock(),
    )

    result = agent._get_claude_config()

    assert isinstance(result, ClaudeAgentConfig)
    assert result.command == CommandString("claude")


# =============================================================================
# Provisioning Lifecycle Tests
# =============================================================================


def test_on_before_provisioning_skips_check_when_disabled(mngr_test_prefix: str, temp_profile_dir: Path) -> None:
    """on_before_provisioning should skip installation check when check_installation=False."""
    pm = pluggy.PluginManager("mngr")
    agent_id = AgentId.generate()
    mock_host = Mock()
    mngr_ctx = MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm, profile_dir=temp_profile_dir)

    agent = ClaudeAgent.model_construct(
        id=agent_id,
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("claude"),
        work_dir=Path("/tmp/work"),
        create_time=datetime.now(timezone.utc),
        host_id=HostId.generate(),
        mngr_ctx=mngr_ctx,
        agent_config=ClaudeAgentConfig(check_installation=False),
        host=mock_host,
    )

    options = Mock()

    # Should not raise and should complete without error
    agent.on_before_provisioning(host=mock_host, options=options, mngr_ctx=mngr_ctx)


def test_get_provision_file_transfers_returns_empty_when_no_local_settings(
    mngr_test_prefix: str, tmp_path: Path, temp_profile_dir: Path
) -> None:
    """get_provision_file_transfers should return empty list when no .claude/ settings exist."""
    pm = pluggy.PluginManager("mngr")
    agent_id = AgentId.generate()
    mock_host = Mock()
    mngr_ctx = MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm, profile_dir=temp_profile_dir)

    # Create agent with sync_repo_settings=True but no .claude/ directory exists
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

    transfers = agent.get_provision_file_transfers(host=mock_host, options=options, mngr_ctx=mngr_ctx)

    assert list(transfers) == []


def test_get_provision_file_transfers_returns_override_folder_files(
    mngr_test_prefix: str, tmp_path: Path, temp_profile_dir: Path
) -> None:
    """get_provision_file_transfers should return files from override_settings_folder."""
    pm = pluggy.PluginManager("mngr")
    agent_id = AgentId.generate()
    mock_host = Mock()
    mngr_ctx = MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm, profile_dir=temp_profile_dir)

    # Create override folder with a test file
    override_folder = tmp_path / "override_settings"
    override_folder.mkdir()
    test_file = override_folder / "test_config.json"
    test_file.write_text('{"test": true}')

    agent = ClaudeAgent.model_construct(
        id=agent_id,
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("claude"),
        work_dir=tmp_path,
        create_time=datetime.now(timezone.utc),
        host_id=HostId.generate(),
        mngr_ctx=mngr_ctx,
        # Disable sync_repo_settings to test override folder only
        agent_config=ClaudeAgentConfig(
            sync_repo_settings=False,
            override_settings_folder=override_folder,
        ),
        host=mock_host,
    )

    options = Mock()

    transfers = list(agent.get_provision_file_transfers(host=mock_host, options=options, mngr_ctx=mngr_ctx))

    assert len(transfers) == 1
    assert transfers[0].local_path == test_file
    assert str(transfers[0].agent_path) == ".claude/test_config.json"
    assert transfers[0].is_required is False


def test_get_provision_file_transfers_with_sync_repo_settings_disabled(
    mngr_test_prefix: str, tmp_path: Path, temp_profile_dir: Path
) -> None:
    """get_provision_file_transfers should skip repo settings when sync_repo_settings=False."""
    pm = pluggy.PluginManager("mngr")
    agent_id = AgentId.generate()
    mock_host = Mock()
    mngr_ctx = MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm, profile_dir=temp_profile_dir)

    agent = ClaudeAgent.model_construct(
        id=agent_id,
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("claude"),
        work_dir=tmp_path,
        create_time=datetime.now(timezone.utc),
        host_id=HostId.generate(),
        mngr_ctx=mngr_ctx,
        agent_config=ClaudeAgentConfig(sync_repo_settings=False),
        host=mock_host,
    )

    options = Mock()

    transfers = list(agent.get_provision_file_transfers(host=mock_host, options=options, mngr_ctx=mngr_ctx))

    # Should return empty since sync_repo_settings=False and no override folder
    assert transfers == []


def test_provision_skips_installation_check_when_disabled(mngr_test_prefix: str, temp_profile_dir: Path) -> None:
    """provision should skip claude installation check when check_installation=False."""
    pm = pluggy.PluginManager("mngr")
    agent_id = AgentId.generate()
    mock_host = Mock()
    mock_host.is_local = True
    mock_host.read_text_file.side_effect = FileNotFoundError()
    mngr_ctx = MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm, profile_dir=temp_profile_dir)

    agent = ClaudeAgent.model_construct(
        id=agent_id,
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("claude"),
        work_dir=Path("/tmp/work"),
        create_time=datetime.now(timezone.utc),
        host_id=HostId.generate(),
        mngr_ctx=mngr_ctx,
        agent_config=ClaudeAgentConfig(check_installation=False),
        host=mock_host,
    )

    options = Mock()

    # Should not call execute_command to check installation
    agent.provision(host=mock_host, options=options, mngr_ctx=mngr_ctx)

    # execute_command should not be called since check_installation=False
    mock_host.execute_command.assert_not_called()


# =============================================================================
# Readiness Hooks Tests
# =============================================================================


def test_build_readiness_hooks_config_has_session_start_hook() -> None:
    """_build_readiness_hooks_config should include SessionStart hook."""
    config = _build_readiness_hooks_config()

    assert "hooks" in config
    assert "SessionStart" in config["hooks"]
    assert len(config["hooks"]["SessionStart"]) == 1
    hook = config["hooks"]["SessionStart"][0]["hooks"][0]
    assert hook["type"] == "command"
    assert "touch" in hook["command"]
    assert "MNGR_AGENT_STATE_DIR" in hook["command"]


def test_build_readiness_hooks_config_has_user_prompt_submit_hook() -> None:
    """_build_readiness_hooks_config should include UserPromptSubmit hook."""
    config = _build_readiness_hooks_config()

    assert "UserPromptSubmit" in config["hooks"]
    assert len(config["hooks"]["UserPromptSubmit"]) == 1
    hook = config["hooks"]["UserPromptSubmit"][0]["hooks"][0]
    assert hook["type"] == "command"
    assert "rm -f" in hook["command"]
    assert "MNGR_AGENT_STATE_DIR" in hook["command"]


def test_build_readiness_hooks_config_has_stop_hook() -> None:
    """_build_readiness_hooks_config should include Stop hook."""
    config = _build_readiness_hooks_config()

    assert "Stop" in config["hooks"]
    assert len(config["hooks"]["Stop"]) == 1
    hook = config["hooks"]["Stop"][0]["hooks"][0]
    assert hook["type"] == "command"
    assert "touch" in hook["command"]
    assert "MNGR_AGENT_STATE_DIR" in hook["command"]


def test_configure_readiness_hooks_creates_settings_file(
    mngr_test_prefix: str, tmp_path: Path, temp_profile_dir: Path
) -> None:
    """_configure_readiness_hooks should create .claude/settings.local.json."""
    pm = pluggy.PluginManager("mngr")
    agent_id = AgentId.generate()
    mock_host = Mock()
    mock_host.is_local = True
    mock_host.read_text_file.side_effect = FileNotFoundError()
    mngr_ctx = MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm, profile_dir=temp_profile_dir)

    agent = ClaudeAgent.model_construct(
        id=agent_id,
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("claude"),
        work_dir=tmp_path,
        create_time=datetime.now(timezone.utc),
        host_id=HostId.generate(),
        mngr_ctx=mngr_ctx,
        agent_config=ClaudeAgentConfig(check_installation=False),
        host=mock_host,
    )

    agent._configure_readiness_hooks(mock_host)

    # Verify write_text_file was called with the correct path
    mock_host.write_text_file.assert_called_once()
    call_args = mock_host.write_text_file.call_args
    path = call_args[0][0]
    content = call_args[0][1]

    assert str(path) == str(tmp_path / ".claude" / "settings.local.json")

    # Verify the content has the expected hooks
    settings = json.loads(content)
    assert "hooks" in settings
    assert "SessionStart" in settings["hooks"]
    assert "UserPromptSubmit" in settings["hooks"]
    assert "Stop" in settings["hooks"]


def test_configure_readiness_hooks_merges_with_existing_settings(
    mngr_test_prefix: str, tmp_path: Path, temp_profile_dir: Path
) -> None:
    """_configure_readiness_hooks should merge with existing settings."""
    pm = pluggy.PluginManager("mngr")
    agent_id = AgentId.generate()
    mock_host = Mock()
    mock_host.is_local = True

    # Simulate existing settings file
    existing_settings = {"model": "opus", "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": []}]}}
    mock_host.read_text_file.return_value = json.dumps(existing_settings)

    mngr_ctx = MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm, profile_dir=temp_profile_dir)

    agent = ClaudeAgent.model_construct(
        id=agent_id,
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("claude"),
        work_dir=tmp_path,
        create_time=datetime.now(timezone.utc),
        host_id=HostId.generate(),
        mngr_ctx=mngr_ctx,
        agent_config=ClaudeAgentConfig(check_installation=False),
        host=mock_host,
    )

    agent._configure_readiness_hooks(mock_host)

    # Verify write_text_file was called
    mock_host.write_text_file.assert_called_once()
    content = mock_host.write_text_file.call_args[0][1]
    settings = json.loads(content)

    # Should preserve existing settings
    assert settings["model"] == "opus"
    assert "PreToolUse" in settings["hooks"]

    # Should add new hooks
    assert "SessionStart" in settings["hooks"]
    assert "UserPromptSubmit" in settings["hooks"]
    assert "Stop" in settings["hooks"]


def test_provision_configures_readiness_hooks_when_enabled(
    mngr_test_prefix: str, tmp_path: Path, temp_profile_dir: Path
) -> None:
    """provision should configure readiness hooks when configure_readiness_hooks=True."""
    pm = pluggy.PluginManager("mngr")
    agent_id = AgentId.generate()
    mock_host = Mock()
    mock_host.is_local = True
    mock_host.read_text_file.side_effect = FileNotFoundError()

    # Mock execute_command for the installation check
    mock_result = Mock()
    mock_result.success = True
    mock_host.execute_command.return_value = mock_result

    mngr_ctx = MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm, profile_dir=temp_profile_dir)

    agent = ClaudeAgent.model_construct(
        id=agent_id,
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("claude"),
        work_dir=tmp_path,
        create_time=datetime.now(timezone.utc),
        host_id=HostId.generate(),
        mngr_ctx=mngr_ctx,
        agent_config=ClaudeAgentConfig(configure_readiness_hooks=True),
        host=mock_host,
    )

    options = Mock()
    agent.provision(host=mock_host, options=options, mngr_ctx=mngr_ctx)

    # Verify write_text_file was called (for the hooks config)
    mock_host.write_text_file.assert_called()


def test_provision_skips_readiness_hooks_when_disabled(
    mngr_test_prefix: str, tmp_path: Path, temp_profile_dir: Path
) -> None:
    """provision should skip readiness hooks when configure_readiness_hooks=False."""
    pm = pluggy.PluginManager("mngr")
    agent_id = AgentId.generate()
    mock_host = Mock()
    mock_host.is_local = True

    # Mock execute_command for the installation check
    mock_result = Mock()
    mock_result.success = True
    mock_host.execute_command.return_value = mock_result

    mngr_ctx = MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm, profile_dir=temp_profile_dir)

    agent = ClaudeAgent.model_construct(
        id=agent_id,
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("claude"),
        work_dir=tmp_path,
        create_time=datetime.now(timezone.utc),
        host_id=HostId.generate(),
        mngr_ctx=mngr_ctx,
        agent_config=ClaudeAgentConfig(
            check_installation=False,
            configure_readiness_hooks=False,
        ),
        host=mock_host,
    )

    options = Mock()
    agent.provision(host=mock_host, options=options, mngr_ctx=mngr_ctx)

    # write_text_file should not be called since both check_installation and
    # configure_readiness_hooks are False
    mock_host.write_text_file.assert_not_called()
