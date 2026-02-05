import json
from datetime import datetime
from datetime import timezone
from pathlib import Path
from unittest.mock import Mock
from unittest.mock import patch

import pluggy
import pytest

from imbue.mngr.agents.default_plugins.claude_agent import ClaudeAgent
from imbue.mngr.agents.default_plugins.claude_agent import ClaudeAgentConfig
from imbue.mngr.agents.default_plugins.claude_agent import _build_readiness_hooks_config
from imbue.mngr.config.data_types import AgentTypeConfig
from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import NoCommandDefinedError
from imbue.mngr.hosts.host import Host
from imbue.mngr.interfaces.host import AgentGitOptions
from imbue.mngr.interfaces.host import CreateAgentOptions
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import WorkDirCopyMode
from imbue.mngr.providers.local.instance import LocalProviderInstance


def make_claude_agent(
    local_provider: LocalProviderInstance,
    tmp_path: Path,
    mngr_ctx: MngrContext,
    agent_config: ClaudeAgentConfig | AgentTypeConfig | None = None,
    agent_type: AgentTypeName | None = None,
) -> tuple[ClaudeAgent, Host]:
    """Create a ClaudeAgent with a real local host for testing."""
    host = local_provider.create_host(HostName(f"test-host-{str(AgentId.generate().get_uuid())[:8]}"))
    assert isinstance(host, Host)
    work_dir = tmp_path / f"work-{str(AgentId.generate().get_uuid())[:8]}"
    work_dir.mkdir()

    if agent_config is None:
        agent_config = ClaudeAgentConfig(check_installation=False)
    if agent_type is None:
        agent_type = AgentTypeName("claude")

    agent = ClaudeAgent.model_construct(
        id=AgentId.generate(),
        name=AgentName("test-agent"),
        agent_type=agent_type,
        work_dir=work_dir,
        create_time=datetime.now(timezone.utc),
        host_id=host.id,
        mngr_ctx=mngr_ctx,
        agent_config=agent_config,
        host=host,
    )
    return agent, host


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


def test_on_before_provisioning_skips_check_when_disabled(
    local_provider: LocalProviderInstance, tmp_path: Path, temp_mngr_ctx: MngrContext
) -> None:
    """on_before_provisioning should skip installation check when check_installation=False."""
    agent, host = make_claude_agent(local_provider, tmp_path, temp_mngr_ctx)

    options = Mock()

    # Should not raise and should complete without error
    agent.on_before_provisioning(host=host, options=options, mngr_ctx=temp_mngr_ctx)


def test_get_provision_file_transfers_returns_empty_when_no_local_settings(
    local_provider: LocalProviderInstance, tmp_path: Path, temp_mngr_ctx: MngrContext
) -> None:
    """get_provision_file_transfers should return empty list when no .claude/ settings exist."""
    # Create agent with sync_repo_settings=True but no .claude/ directory exists
    agent, host = make_claude_agent(
        local_provider,
        tmp_path,
        temp_mngr_ctx,
        agent_config=ClaudeAgentConfig(check_installation=False, sync_repo_settings=True),
    )

    options = Mock()

    transfers = agent.get_provision_file_transfers(host=host, options=options, mngr_ctx=temp_mngr_ctx)

    assert list(transfers) == []


def test_get_provision_file_transfers_returns_override_folder_files(
    local_provider: LocalProviderInstance, tmp_path: Path, temp_mngr_ctx: MngrContext
) -> None:
    """get_provision_file_transfers should return files from override_settings_folder."""
    # Create override folder with a test file
    override_folder = tmp_path / "override_settings"
    override_folder.mkdir()
    test_file = override_folder / "test_config.json"
    test_file.write_text('{"test": true}')

    # Disable sync_repo_settings to test override folder only
    agent, host = make_claude_agent(
        local_provider,
        tmp_path,
        temp_mngr_ctx,
        agent_config=ClaudeAgentConfig(
            check_installation=False,
            sync_repo_settings=False,
            override_settings_folder=override_folder,
        ),
    )

    options = Mock()

    transfers = list(agent.get_provision_file_transfers(host=host, options=options, mngr_ctx=temp_mngr_ctx))

    assert len(transfers) == 1
    assert transfers[0].local_path == test_file
    assert str(transfers[0].agent_path) == ".claude/test_config.json"
    assert transfers[0].is_required is False


def test_get_provision_file_transfers_with_sync_repo_settings_disabled(
    local_provider: LocalProviderInstance, tmp_path: Path, temp_mngr_ctx: MngrContext
) -> None:
    """get_provision_file_transfers should skip repo settings when sync_repo_settings=False."""
    agent, host = make_claude_agent(
        local_provider,
        tmp_path,
        temp_mngr_ctx,
        agent_config=ClaudeAgentConfig(check_installation=False, sync_repo_settings=False),
    )

    options = Mock()

    transfers = list(agent.get_provision_file_transfers(host=host, options=options, mngr_ctx=temp_mngr_ctx))

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
    """_build_readiness_hooks_config should include SessionStart hook that creates session_started file."""
    config = _build_readiness_hooks_config()

    assert "hooks" in config
    assert "SessionStart" in config["hooks"]
    assert len(config["hooks"]["SessionStart"]) == 1
    hook = config["hooks"]["SessionStart"][0]["hooks"][0]
    assert hook["type"] == "command"
    # SessionStart creates session_started file for polling-based detection
    assert "touch" in hook["command"]
    assert "session_started" in hook["command"]


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


def test_get_expected_process_name_returns_claude(
    local_provider: LocalProviderInstance, tmp_path: Path, temp_mngr_ctx: MngrContext
) -> None:
    """ClaudeAgent.get_expected_process_name should return 'claude'."""
    agent, _ = make_claude_agent(local_provider, tmp_path, temp_mngr_ctx)
    assert agent.get_expected_process_name() == "claude"


def test_uses_marker_based_send_message_returns_true(
    local_provider: LocalProviderInstance, tmp_path: Path, temp_mngr_ctx: MngrContext
) -> None:
    """ClaudeAgent.uses_marker_based_send_message should return True."""
    agent, _ = make_claude_agent(local_provider, tmp_path, temp_mngr_ctx)
    assert agent.uses_marker_based_send_message() is True


def test_configure_readiness_hooks_creates_settings_file(
    local_provider: LocalProviderInstance, tmp_path: Path, temp_mngr_ctx: MngrContext
) -> None:
    """_configure_readiness_hooks should create .claude/settings.local.json."""
    host = local_provider.create_host(HostName("test-hooks"))
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    agent = ClaudeAgent.model_construct(
        id=AgentId.generate(),
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("claude"),
        work_dir=work_dir,
        create_time=datetime.now(timezone.utc),
        host_id=host.id,
        mngr_ctx=temp_mngr_ctx,
        agent_config=ClaudeAgentConfig(check_installation=False),
        host=host,
    )

    agent._configure_readiness_hooks(host)

    # Verify the file was actually created
    settings_path = work_dir / ".claude" / "settings.local.json"
    assert settings_path.exists()

    # Verify the content has the expected hooks
    settings = json.loads(settings_path.read_text())
    assert "hooks" in settings
    assert "SessionStart" in settings["hooks"]
    assert "UserPromptSubmit" in settings["hooks"]
    assert "Stop" in settings["hooks"]


def test_configure_readiness_hooks_merges_with_existing_settings(
    local_provider: LocalProviderInstance, tmp_path: Path, temp_mngr_ctx: MngrContext
) -> None:
    """_configure_readiness_hooks should merge with existing settings."""
    host = local_provider.create_host(HostName("test-hooks-merge"))
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    # Create existing settings file
    claude_dir = work_dir / ".claude"
    claude_dir.mkdir()
    existing_settings = {"model": "opus", "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": []}]}}
    (claude_dir / "settings.local.json").write_text(json.dumps(existing_settings))

    agent = ClaudeAgent.model_construct(
        id=AgentId.generate(),
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("claude"),
        work_dir=work_dir,
        create_time=datetime.now(timezone.utc),
        host_id=host.id,
        mngr_ctx=temp_mngr_ctx,
        agent_config=ClaudeAgentConfig(check_installation=False),
        host=host,
    )

    agent._configure_readiness_hooks(host)

    # Read the file and verify it was merged
    settings_path = work_dir / ".claude" / "settings.local.json"
    settings = json.loads(settings_path.read_text())

    # Should preserve existing settings
    assert settings["model"] == "opus"
    assert "PreToolUse" in settings["hooks"]

    # Should add new hooks
    assert "SessionStart" in settings["hooks"]
    assert "UserPromptSubmit" in settings["hooks"]
    assert "Stop" in settings["hooks"]


def test_provision_configures_readiness_hooks_when_enabled(
    local_provider: LocalProviderInstance, tmp_path: Path, temp_mngr_ctx: MngrContext
) -> None:
    """provision should configure readiness hooks when configure_readiness_hooks=True."""
    # check_installation=False avoids running `claude --version` which would fail in test env
    agent, host = make_claude_agent(
        local_provider,
        tmp_path,
        temp_mngr_ctx,
        agent_config=ClaudeAgentConfig(
            check_installation=False,
            configure_readiness_hooks=True,
        ),
    )

    options = Mock()
    agent.provision(host=host, options=options, mngr_ctx=temp_mngr_ctx)

    # Verify the hooks file was actually created
    settings_path = agent.work_dir / ".claude" / "settings.local.json"
    assert settings_path.exists()
    settings = json.loads(settings_path.read_text())
    assert "hooks" in settings
    assert "SessionStart" in settings["hooks"]


def test_provision_skips_readiness_hooks_when_disabled(
    local_provider: LocalProviderInstance, tmp_path: Path, temp_mngr_ctx: MngrContext
) -> None:
    """provision should skip readiness hooks when configure_readiness_hooks=False."""
    # check_installation=False avoids running `claude --version` which would fail in test env
    agent, host = make_claude_agent(
        local_provider,
        tmp_path,
        temp_mngr_ctx,
        agent_config=ClaudeAgentConfig(
            check_installation=False,
            configure_readiness_hooks=False,
        ),
    )

    options = Mock()
    agent.provision(host=host, options=options, mngr_ctx=temp_mngr_ctx)

    # Hooks file should not be created
    settings_path = agent.work_dir / ".claude" / "settings.local.json"
    assert not settings_path.exists()


# =============================================================================
# Trust Extension / Cleanup Tests
# =============================================================================


def make_mock_claude_agent(
    work_dir: Path, mngr_test_prefix: str, temp_profile_dir: Path
) -> tuple[ClaudeAgent, Mock, MngrContext]:
    """Create a ClaudeAgent with a mock host for verifying method calls.

    Use this when you only need to verify that methods are called with the right
    arguments (via patch/Mock). Use make_claude_agent instead if you need real
    filesystem operations.
    """
    pm = pluggy.PluginManager("mngr")
    mock_host = Mock()
    mngr_ctx = MngrContext(config=MngrConfig(prefix=mngr_test_prefix), pm=pm, profile_dir=temp_profile_dir)
    agent = ClaudeAgent.model_construct(
        id=AgentId.generate(),
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("claude"),
        work_dir=work_dir,
        create_time=datetime.now(timezone.utc),
        host_id=HostId.generate(),
        mngr_ctx=mngr_ctx,
        agent_config=ClaudeAgentConfig(check_installation=False),
        host=mock_host,
    )
    return agent, mock_host, mngr_ctx


def test_provision_extends_trust_for_worktree(mngr_test_prefix: str, tmp_path: Path, temp_profile_dir: Path) -> None:
    """provision should extend Claude trust when using worktree mode."""
    work_dir = tmp_path / "worktree"
    work_dir.mkdir()
    source_git_dir = tmp_path / "source" / ".git"

    agent, mock_host, mngr_ctx = make_mock_claude_agent(work_dir, mngr_test_prefix, temp_profile_dir)

    options = CreateAgentOptions(
        agent_type=AgentTypeName("claude"),
        git=AgentGitOptions(copy_mode=WorkDirCopyMode.WORKTREE),
    )

    with (
        patch(
            "imbue.mngr.agents.default_plugins.claude_agent.find_git_common_dir",
            return_value=source_git_dir,
        ) as mock_find,
        patch(
            "imbue.mngr.agents.default_plugins.claude_agent.extend_claude_trust_to_worktree",
        ) as mock_extend,
    ):
        agent.provision(host=mock_host, options=options, mngr_ctx=mngr_ctx)

    mock_find.assert_called_once_with(work_dir)
    mock_extend.assert_called_once_with(source_git_dir.parent, work_dir)


def test_provision_does_not_extend_trust_for_non_worktree(
    mngr_test_prefix: str, tmp_path: Path, temp_profile_dir: Path
) -> None:
    """provision should not extend trust when not using worktree mode."""
    agent, mock_host, mngr_ctx = make_mock_claude_agent(tmp_path, mngr_test_prefix, temp_profile_dir)

    options = CreateAgentOptions(
        agent_type=AgentTypeName("claude"),
        git=AgentGitOptions(copy_mode=WorkDirCopyMode.COPY),
    )

    with patch(
        "imbue.mngr.agents.default_plugins.claude_agent.extend_claude_trust_to_worktree",
    ) as mock_extend:
        agent.provision(host=mock_host, options=options, mngr_ctx=mngr_ctx)

    mock_extend.assert_not_called()


def test_provision_does_not_extend_trust_when_no_git_options(
    mngr_test_prefix: str, tmp_path: Path, temp_profile_dir: Path
) -> None:
    """provision should not extend trust when git options are None."""
    agent, mock_host, mngr_ctx = make_mock_claude_agent(tmp_path, mngr_test_prefix, temp_profile_dir)

    options = CreateAgentOptions(
        agent_type=AgentTypeName("claude"),
    )

    with patch(
        "imbue.mngr.agents.default_plugins.claude_agent.extend_claude_trust_to_worktree",
    ) as mock_extend:
        agent.provision(host=mock_host, options=options, mngr_ctx=mngr_ctx)

    mock_extend.assert_not_called()


def test_on_destroy_removes_trust(mngr_test_prefix: str, tmp_path: Path, temp_profile_dir: Path) -> None:
    """on_destroy should call remove_claude_trust_for_path with the work_dir."""
    work_dir = tmp_path / "worktree"
    work_dir.mkdir()

    agent, mock_host, _ = make_mock_claude_agent(work_dir, mngr_test_prefix, temp_profile_dir)

    with patch(
        "imbue.mngr.agents.default_plugins.claude_agent.remove_claude_trust_for_path",
        return_value=True,
    ) as mock_remove:
        agent.on_destroy(mock_host)

    mock_remove.assert_called_once_with(work_dir)
