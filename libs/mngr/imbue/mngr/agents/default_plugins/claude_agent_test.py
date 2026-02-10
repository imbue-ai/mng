import json
import subprocess
from datetime import datetime
from datetime import timezone
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import pluggy
import pytest

from imbue.mngr.agents.default_plugins.claude_agent import ClaudeAgent
from imbue.mngr.agents.default_plugins.claude_agent import ClaudeAgentConfig
from imbue.mngr.agents.default_plugins.claude_config import build_readiness_hooks_config
from imbue.mngr.config.data_types import AgentTypeConfig
from imbue.mngr.config.data_types import MngrConfig
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import NoCommandDefinedError
from imbue.mngr.errors import PluginMngrError
from imbue.mngr.hosts.host import Host
from imbue.mngr.interfaces.host import AgentGitOptions
from imbue.mngr.interfaces.host import CreateAgentOptions
from imbue.mngr.interfaces.host import OnlineHostInterface
from imbue.mngr.primitives import AgentId
from imbue.mngr.primitives import AgentName
from imbue.mngr.primitives import AgentTypeName
from imbue.mngr.primitives import CommandString
from imbue.mngr.primitives import HostId
from imbue.mngr.primitives import HostName
from imbue.mngr.primitives import WorkDirCopyMode
from imbue.mngr.providers.local.instance import LocalProviderInstance
from imbue.mngr.utils.testing import init_git_repo

# =============================================================================
# Test Helpers
# =============================================================================


def make_claude_agent(
    local_provider: LocalProviderInstance,
    tmp_path: Path,
    mngr_ctx: MngrContext,
    agent_config: ClaudeAgentConfig | AgentTypeConfig | None = None,
    agent_type: AgentTypeName | None = None,
    work_dir: Path | None = None,
) -> tuple[ClaudeAgent, Host]:
    """Create a ClaudeAgent with a real local host for testing."""
    host = local_provider.create_host(HostName(f"test-host-{str(AgentId.generate().get_uuid())[:8]}"))
    assert isinstance(host, Host)
    if work_dir is None:
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


def _init_git_with_gitignore(work_dir: Path) -> None:
    """Initialize a git repo in work_dir with .claude/settings.local.json gitignored."""
    init_git_repo(work_dir, initial_commit=False)
    (work_dir / ".gitignore").write_text(".claude/settings.local.json\n")


def _setup_git_worktree(tmp_path: Path) -> tuple[Path, Path]:
    """Set up a git repo and worktree for trust extension testing.

    Creates a source repo with .gitignore (for readiness hooks) and a worktree
    branched from it. Requires setup_git_config fixture for git user config.

    Returns (source_path, worktree_path).
    """
    source = tmp_path / "source"
    source.mkdir()
    init_git_repo(source, initial_commit=True)

    # Add .gitignore (needed by _configure_readiness_hooks in provision)
    (source / ".gitignore").write_text(".claude/settings.local.json\n")
    subprocess.run(["git", "-C", str(source), "add", ".gitignore"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(source), "commit", "-m", "add gitignore"],
        check=True,
        capture_output=True,
    )

    # Create worktree from the source repo
    worktree = tmp_path / "worktree"
    subprocess.run(
        ["git", "-C", str(source), "worktree", "add", str(worktree), "-b", "test-branch"],
        check=True,
        capture_output=True,
    )

    return source, worktree


def _write_claude_trust(source_path: Path) -> None:
    """Write ~/.claude.json with trust entry for source_path."""
    config_path = Path.home() / ".claude.json"
    config = {
        "projects": {
            str(source_path.resolve()): {
                "hasTrustDialogAccepted": True,
                "allowedTools": [],
            }
        }
    }
    config_path.write_text(json.dumps(config))


def _write_mngr_trust_entry(path: Path) -> None:
    """Write ~/.claude.json with a mngr-created trust entry for path."""
    config_path = Path.home() / ".claude.json"
    config = {
        "projects": {
            str(path.resolve()): {
                "hasTrustDialogAccepted": True,
                "allowedTools": [],
                "_mngrCreated": True,
                "_mngrSourcePath": "/some/source",
            }
        }
    }
    config_path.write_text(json.dumps(config))


# =============================================================================
# ClaudeAgentConfig Tests
# =============================================================================


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


def test_claude_agent_config_merge_uses_override_cli_args_when_base_empty() -> None:
    """ClaudeAgentConfig merge should use override cli_args when base is empty."""
    base = ClaudeAgentConfig()
    override = ClaudeAgentConfig(cli_args="--verbose")

    merged = base.merge_with(override)

    assert merged.cli_args == "--verbose"


# =============================================================================
# assemble_command Tests
# =============================================================================


def test_claude_agent_assemble_command_with_no_args(
    local_provider: LocalProviderInstance, tmp_path: Path, temp_mngr_ctx: MngrContext
) -> None:
    """ClaudeAgent should generate resume/session-id command format with no args."""
    agent, host = make_claude_agent(local_provider, tmp_path, temp_mngr_ctx)

    command = agent.assemble_command(host=host, agent_args=(), command_override=None)

    uuid = agent.id.get_uuid()
    prefix = temp_mngr_ctx.config.prefix
    session_name = f"{prefix}test-agent"
    activity_cmd = agent._build_activity_updater_command(session_name)
    # Local hosts should NOT have IS_SANDBOX set
    assert command == CommandString(
        f"{activity_cmd} export MAIN_CLAUDE_SESSION_ID={uuid} && ( ( find ~/.claude/ -name '{uuid}' | grep . ) && claude --resume {uuid} ) || claude --session-id {uuid}"
    )


def test_claude_agent_assemble_command_with_agent_args(
    local_provider: LocalProviderInstance, tmp_path: Path, temp_mngr_ctx: MngrContext
) -> None:
    """ClaudeAgent should append agent args to both command variants."""
    agent, host = make_claude_agent(local_provider, tmp_path, temp_mngr_ctx)

    command = agent.assemble_command(host=host, agent_args=("--model", "opus"), command_override=None)

    uuid = agent.id.get_uuid()
    prefix = temp_mngr_ctx.config.prefix
    session_name = f"{prefix}test-agent"
    activity_cmd = agent._build_activity_updater_command(session_name)
    assert command == CommandString(
        f"{activity_cmd} export MAIN_CLAUDE_SESSION_ID={uuid} && ( ( find ~/.claude/ -name '{uuid}' | grep . ) && claude --resume {uuid} --model opus ) || claude --session-id {uuid} --model opus"
    )


def test_claude_agent_assemble_command_with_cli_args_and_agent_args(
    local_provider: LocalProviderInstance, tmp_path: Path, temp_mngr_ctx: MngrContext
) -> None:
    """ClaudeAgent should append both cli_args and agent_args to both command variants."""
    agent, host = make_claude_agent(
        local_provider,
        tmp_path,
        temp_mngr_ctx,
        agent_config=ClaudeAgentConfig(cli_args="--verbose", check_installation=False),
    )

    command = agent.assemble_command(host=host, agent_args=("--model", "opus"), command_override=None)

    uuid = agent.id.get_uuid()
    prefix = temp_mngr_ctx.config.prefix
    session_name = f"{prefix}test-agent"
    activity_cmd = agent._build_activity_updater_command(session_name)
    assert command == CommandString(
        f"{activity_cmd} export MAIN_CLAUDE_SESSION_ID={uuid} && ( ( find ~/.claude/ -name '{uuid}' | grep . ) && claude --resume {uuid} --verbose --model opus ) || claude --session-id {uuid} --verbose --model opus"
    )


def test_claude_agent_assemble_command_with_command_override(
    local_provider: LocalProviderInstance, tmp_path: Path, temp_mngr_ctx: MngrContext
) -> None:
    """ClaudeAgent should use command override when provided."""
    agent, host = make_claude_agent(local_provider, tmp_path, temp_mngr_ctx)

    command = agent.assemble_command(
        host=host,
        agent_args=("--model", "opus"),
        command_override=CommandString("custom-claude"),
    )

    uuid = agent.id.get_uuid()
    prefix = temp_mngr_ctx.config.prefix
    session_name = f"{prefix}test-agent"
    activity_cmd = agent._build_activity_updater_command(session_name)
    assert command == CommandString(
        f"{activity_cmd} export MAIN_CLAUDE_SESSION_ID={uuid} && ( ( find ~/.claude/ -name '{uuid}' | grep . ) && custom-claude --resume {uuid} --model opus ) || custom-claude --session-id {uuid} --model opus"
    )


def test_claude_agent_assemble_command_raises_when_no_command(
    local_provider: LocalProviderInstance, tmp_path: Path, temp_mngr_ctx: MngrContext
) -> None:
    """ClaudeAgent should raise NoCommandDefinedError when no command defined."""
    agent, host = make_claude_agent(
        local_provider,
        tmp_path,
        temp_mngr_ctx,
        agent_config=AgentTypeConfig(),
        agent_type=AgentTypeName("custom"),
    )

    with pytest.raises(NoCommandDefinedError, match="No command defined"):
        agent.assemble_command(host=host, agent_args=(), command_override=None)


def test_claude_agent_assemble_command_sets_is_sandbox_for_remote_host(
    local_provider: LocalProviderInstance, tmp_path: Path, temp_mngr_ctx: MngrContext
) -> None:
    """ClaudeAgent should set IS_SANDBOX=1 only for remote (non-local) hosts."""
    agent, _ = make_claude_agent(local_provider, tmp_path, temp_mngr_ctx)

    # Use SimpleNamespace to simulate a non-local host. Creating a real remote host
    # requires SSH infrastructure that is not available in unit tests. The assemble_command
    # method only reads host.is_local to decide whether to set IS_SANDBOX.
    non_local_host = cast(OnlineHostInterface, SimpleNamespace(is_local=False))

    command = agent.assemble_command(host=non_local_host, agent_args=(), command_override=None)

    uuid = agent.id.get_uuid()
    prefix = temp_mngr_ctx.config.prefix
    session_name = f"{prefix}test-agent"
    activity_cmd = agent._build_activity_updater_command(session_name)
    # Remote hosts SHOULD have IS_SANDBOX set
    assert command == CommandString(
        f"{activity_cmd} export IS_SANDBOX=1 && export MAIN_CLAUDE_SESSION_ID={uuid} && ( ( find ~/.claude/ -name '{uuid}' | grep . ) && claude --resume {uuid} ) || claude --session-id {uuid}"
    )


# =============================================================================
# Activity Updater Tests
# =============================================================================


def test_build_activity_updater_command(
    local_provider: LocalProviderInstance, tmp_path: Path, temp_mngr_ctx: MngrContext
) -> None:
    """_build_activity_updater_command should generate a background activity updater."""
    agent, _ = make_claude_agent(local_provider, tmp_path, temp_mngr_ctx)

    prefix = temp_mngr_ctx.config.prefix
    session_name = f"{prefix}test-agent"
    cmd = agent._build_activity_updater_command(session_name)

    # Should be a background subshell
    assert cmd.startswith("(")
    assert cmd.endswith(") &")

    # Should use the correct session name for tmux check
    assert f"tmux has-session -t '{session_name}'" in cmd

    # Should use a pidfile for deduplication
    assert f"_MNGR_ACT_LOCK=/tmp/mngr_act_{session_name}.pid" in cmd

    # Should update the activity file
    assert "MNGR_AGENT_STATE_DIR/activity/agent" in cmd

    # Should only update activity when .claude/active exists
    assert ".claude/active" in cmd

    # Should check for existing instances via pidfile
    assert "kill -0" in cmd
    assert "exit 0" in cmd

    # Should set a trap for cleanup
    assert "trap" in cmd


def test_build_activity_updater_command_with_socket(mngr_test_prefix: str, temp_profile_dir: Path) -> None:
    """_build_activity_updater_command should use socket-aware tmux command when tmux_socket_name is set."""
    pm = pluggy.PluginManager("mngr")
    agent_id = AgentId.generate()

    agent = ClaudeAgent.model_construct(
        id=agent_id,
        name=AgentName("test-agent"),
        agent_type=AgentTypeName("claude"),
        work_dir=Path("/tmp/work"),
        create_time=datetime.now(timezone.utc),
        host_id=HostId.generate(),
        mngr_ctx=MngrContext(
            config=MngrConfig(prefix=mngr_test_prefix, tmux_socket_name="mngr-test"),
            pm=pm,
            profile_dir=temp_profile_dir,
        ),
        agent_config=ClaudeAgentConfig(),
        host=Mock(),
    )

    session_name = f"{mngr_test_prefix}test-agent"
    cmd = agent._build_activity_updater_command(session_name)

    # Should use -L flag with socket name
    assert f"tmux -L mngr-test has-session -t '{session_name}'" in cmd


# =============================================================================
# _get_claude_config Tests
# =============================================================================


def test_get_claude_config_returns_config_when_claude_agent_config(
    local_provider: LocalProviderInstance, tmp_path: Path, temp_mngr_ctx: MngrContext
) -> None:
    """_get_claude_config should return the config when it is a ClaudeAgentConfig."""
    config = ClaudeAgentConfig(cli_args="--verbose", check_installation=False)
    agent, _ = make_claude_agent(local_provider, tmp_path, temp_mngr_ctx, agent_config=config)

    result = agent._get_claude_config()

    assert result is config
    assert result.cli_args == "--verbose"


def test_get_claude_config_returns_default_when_not_claude_agent_config(
    local_provider: LocalProviderInstance, tmp_path: Path, temp_mngr_ctx: MngrContext
) -> None:
    """_get_claude_config should return default ClaudeAgentConfig when config is not ClaudeAgentConfig."""
    agent, _ = make_claude_agent(
        local_provider,
        tmp_path,
        temp_mngr_ctx,
        agent_config=AgentTypeConfig(),
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

    options = CreateAgentOptions(agent_type=AgentTypeName("claude"))

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

    options = CreateAgentOptions(agent_type=AgentTypeName("claude"))

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

    options = CreateAgentOptions(agent_type=AgentTypeName("claude"))

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

    options = CreateAgentOptions(agent_type=AgentTypeName("claude"))

    transfers = list(agent.get_provision_file_transfers(host=host, options=options, mngr_ctx=temp_mngr_ctx))

    # Should return empty since sync_repo_settings=False and no override folder
    assert transfers == []


# =============================================================================
# Readiness Hooks Tests
# =============================================================================


def test_build_readiness_hooks_config_has_session_start_hook() -> None:
    """build_readiness_hooks_config should include SessionStart hook that creates session_started file."""
    config = build_readiness_hooks_config()

    assert "hooks" in config
    assert "SessionStart" in config["hooks"]
    assert len(config["hooks"]["SessionStart"]) == 1
    hook = config["hooks"]["SessionStart"][0]["hooks"][0]
    assert hook["type"] == "command"
    # SessionStart creates session_started file for polling-based detection
    assert "touch" in hook["command"]
    assert "session_started" in hook["command"]


def test_build_readiness_hooks_config_has_user_prompt_submit_hook() -> None:
    """build_readiness_hooks_config should include UserPromptSubmit hook."""
    config = build_readiness_hooks_config()

    assert "UserPromptSubmit" in config["hooks"]
    assert len(config["hooks"]["UserPromptSubmit"]) == 1
    hook = config["hooks"]["UserPromptSubmit"][0]["hooks"][0]
    assert hook["type"] == "command"
    assert "rm -f" in hook["command"]
    assert "MNGR_AGENT_STATE_DIR" in hook["command"]


def test_build_readiness_hooks_config_has_stop_hook() -> None:
    """build_readiness_hooks_config should include Stop hook."""
    config = build_readiness_hooks_config()

    assert "Stop" in config["hooks"]
    assert len(config["hooks"]["Stop"]) == 1
    hook = config["hooks"]["Stop"][0]["hooks"][0]
    assert hook["type"] == "command"
    assert "touch" in hook["command"]
    assert "MNGR_AGENT_STATE_DIR" in hook["command"]


def test_build_readiness_hooks_config_uses_default_tmux_when_no_socket() -> None:
    """build_readiness_hooks_config should use bare tmux commands when tmux_socket_name is None."""
    config = build_readiness_hooks_config()

    submit_hooks = config["hooks"]["UserPromptSubmit"][0]["hooks"]
    signal_hook = submit_hooks[1]
    # With no socket, should use bare tmux (no -L flag)
    assert signal_hook["command"].startswith("tmux wait-for")
    assert "-L" not in signal_hook["command"]


def test_build_readiness_hooks_config_uses_socket_aware_tmux() -> None:
    """build_readiness_hooks_config should use -L flag when tmux_socket_name is set."""
    config = build_readiness_hooks_config(tmux_socket_name="mngr-test")

    submit_hooks = config["hooks"]["UserPromptSubmit"][0]["hooks"]
    signal_hook = submit_hooks[1]
    # With socket, should use tmux -L mngr-test
    assert "tmux -L mngr-test wait-for" in signal_hook["command"]
    assert "tmux -L mngr-test display-message" in signal_hook["command"]


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


def test_configure_readiness_hooks_raises_when_not_gitignored(
    local_provider: LocalProviderInstance, tmp_path: Path, temp_mngr_ctx: MngrContext
) -> None:
    """_configure_readiness_hooks should raise when .claude/settings.local.json is not gitignored."""
    host = local_provider.create_host(HostName("test-hooks-gitignore"))
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    # Init git but do NOT add .gitignore entry
    init_git_repo(work_dir, initial_commit=False)

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

    with pytest.raises(PluginMngrError, match="not gitignored"):
        agent._configure_readiness_hooks(host)


def test_configure_readiness_hooks_creates_settings_file(
    local_provider: LocalProviderInstance, tmp_path: Path, temp_mngr_ctx: MngrContext
) -> None:
    """_configure_readiness_hooks should create .claude/settings.local.json."""
    host = local_provider.create_host(HostName("test-hooks"))
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    _init_git_with_gitignore(work_dir)

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
    _init_git_with_gitignore(work_dir)

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


def test_provision_configures_readiness_hooks(
    local_provider: LocalProviderInstance, tmp_path: Path, temp_mngr_ctx: MngrContext
) -> None:
    """provision should configure readiness hooks."""
    # check_installation=False avoids running `claude --version` which would fail in test env
    agent, host = make_claude_agent(
        local_provider,
        tmp_path,
        temp_mngr_ctx,
        agent_config=ClaudeAgentConfig(check_installation=False),
    )
    _init_git_with_gitignore(agent.work_dir)

    options = CreateAgentOptions(agent_type=AgentTypeName("claude"))
    agent.provision(host=host, options=options, mngr_ctx=temp_mngr_ctx)

    # Verify the hooks file was actually created
    settings_path = agent.work_dir / ".claude" / "settings.local.json"
    assert settings_path.exists()
    settings = json.loads(settings_path.read_text())
    assert "hooks" in settings
    assert "SessionStart" in settings["hooks"]


# =============================================================================
# Trust Extension / Cleanup Tests
# =============================================================================


def test_provision_extends_trust_for_worktree(
    local_provider: LocalProviderInstance,
    tmp_path: Path,
    temp_mngr_ctx: MngrContext,
    setup_git_config: None,
) -> None:
    """provision should extend Claude trust when using worktree mode."""
    source_path, worktree_path = _setup_git_worktree(tmp_path)
    _write_claude_trust(source_path)

    agent, host = make_claude_agent(
        local_provider,
        tmp_path,
        temp_mngr_ctx,
        work_dir=worktree_path,
    )

    options = CreateAgentOptions(
        agent_type=AgentTypeName("claude"),
        git=AgentGitOptions(copy_mode=WorkDirCopyMode.WORKTREE),
    )

    agent.provision(host=host, options=options, mngr_ctx=temp_mngr_ctx)

    # Verify trust was extended to the worktree
    config_path = Path.home() / ".claude.json"
    config = json.loads(config_path.read_text())
    assert str(worktree_path.resolve()) in config["projects"]
    worktree_entry = config["projects"][str(worktree_path.resolve())]
    assert worktree_entry["hasTrustDialogAccepted"] is True
    assert worktree_entry["_mngrCreated"] is True


def test_provision_does_not_extend_trust_for_non_worktree(
    local_provider: LocalProviderInstance, tmp_path: Path, temp_mngr_ctx: MngrContext
) -> None:
    """provision should not extend trust when not using worktree mode."""
    agent, host = make_claude_agent(local_provider, tmp_path, temp_mngr_ctx)
    _init_git_with_gitignore(agent.work_dir)

    options = CreateAgentOptions(
        agent_type=AgentTypeName("claude"),
        git=AgentGitOptions(copy_mode=WorkDirCopyMode.COPY),
    )

    agent.provision(host=host, options=options, mngr_ctx=temp_mngr_ctx)

    # Trust should NOT have been extended since we're using COPY mode
    config_path = Path.home() / ".claude.json"
    assert not config_path.exists()


def test_provision_does_not_extend_trust_when_no_git_options(
    local_provider: LocalProviderInstance, tmp_path: Path, temp_mngr_ctx: MngrContext
) -> None:
    """provision should not extend trust when git options are None."""
    agent, host = make_claude_agent(local_provider, tmp_path, temp_mngr_ctx)
    _init_git_with_gitignore(agent.work_dir)

    options = CreateAgentOptions(agent_type=AgentTypeName("claude"))

    agent.provision(host=host, options=options, mngr_ctx=temp_mngr_ctx)

    # Trust should NOT have been extended since no git options provided
    config_path = Path.home() / ".claude.json"
    assert not config_path.exists()


def test_provision_skips_trust_when_git_common_dir_is_none(
    local_provider: LocalProviderInstance, tmp_path: Path, temp_mngr_ctx: MngrContext
) -> None:
    """provision should skip trust extension when find_git_common_dir returns None."""
    # Create agent with work_dir that is NOT a git repo
    agent, host = make_claude_agent(local_provider, tmp_path, temp_mngr_ctx)
    # Don't init git - work_dir is not a git repo

    options = CreateAgentOptions(
        agent_type=AgentTypeName("claude"),
        git=AgentGitOptions(copy_mode=WorkDirCopyMode.WORKTREE),
    )

    agent.provision(host=host, options=options, mngr_ctx=temp_mngr_ctx)

    # Trust should NOT have been extended since there's no git common dir
    config_path = Path.home() / ".claude.json"
    assert not config_path.exists()


def test_on_before_provisioning_raises_for_worktree_on_remote_host(
    local_provider: LocalProviderInstance, tmp_path: Path, temp_mngr_ctx: MngrContext
) -> None:
    """on_before_provisioning should raise PluginMngrError for worktree mode on remote hosts."""
    agent, _ = make_claude_agent(local_provider, tmp_path, temp_mngr_ctx)

    # Use SimpleNamespace to simulate a non-local host. Creating a real remote host
    # requires SSH infrastructure not available in unit tests. The method only reads
    # host.is_local before raising.
    non_local_host = cast(OnlineHostInterface, SimpleNamespace(is_local=False))

    options = CreateAgentOptions(
        agent_type=AgentTypeName("claude"),
        git=AgentGitOptions(copy_mode=WorkDirCopyMode.WORKTREE),
    )

    with pytest.raises(PluginMngrError, match="Worktree mode is not supported on remote hosts"):
        agent.on_before_provisioning(host=non_local_host, options=options, mngr_ctx=temp_mngr_ctx)


def test_on_before_provisioning_validates_trust_for_worktree(
    local_provider: LocalProviderInstance,
    tmp_path: Path,
    temp_mngr_ctx: MngrContext,
    setup_git_config: None,
) -> None:
    """on_before_provisioning should validate source directory is trusted for worktree mode."""
    source_path, worktree_path = _setup_git_worktree(tmp_path)
    _write_claude_trust(source_path)

    agent, host = make_claude_agent(
        local_provider,
        tmp_path,
        temp_mngr_ctx,
        work_dir=worktree_path,
    )

    options = CreateAgentOptions(
        agent_type=AgentTypeName("claude"),
        git=AgentGitOptions(copy_mode=WorkDirCopyMode.WORKTREE),
    )

    # Should succeed without error because the source directory is trusted
    agent.on_before_provisioning(host=host, options=options, mngr_ctx=temp_mngr_ctx)


def test_on_before_provisioning_skips_trust_check_when_git_common_dir_is_none(
    local_provider: LocalProviderInstance, tmp_path: Path, temp_mngr_ctx: MngrContext
) -> None:
    """on_before_provisioning should skip trust check when find_git_common_dir returns None."""
    # Create agent with work_dir that is NOT a git repo
    agent, host = make_claude_agent(local_provider, tmp_path, temp_mngr_ctx)

    options = CreateAgentOptions(
        agent_type=AgentTypeName("claude"),
        git=AgentGitOptions(copy_mode=WorkDirCopyMode.WORKTREE),
    )

    # Should succeed without error because find_git_common_dir returns None
    agent.on_before_provisioning(host=host, options=options, mngr_ctx=temp_mngr_ctx)


def test_on_destroy_removes_trust(
    local_provider: LocalProviderInstance, tmp_path: Path, temp_mngr_ctx: MngrContext
) -> None:
    """on_destroy should remove the Claude trust entry for the agent's work_dir."""
    agent, host = make_claude_agent(local_provider, tmp_path, temp_mngr_ctx)

    # Write a mngr-created trust entry for the agent's work_dir
    _write_mngr_trust_entry(agent.work_dir)

    # Verify the entry exists before destroy
    config_path = Path.home() / ".claude.json"
    config_before = json.loads(config_path.read_text())
    assert str(agent.work_dir.resolve()) in config_before["projects"]

    agent.on_destroy(host)

    # Verify the trust entry was removed
    config_after = json.loads(config_path.read_text())
    assert str(agent.work_dir.resolve()) not in config_after.get("projects", {})
