"""Unit tests for the pi-coding plugin."""

from collections.abc import Mapping
from pathlib import Path
from unittest.mock import patch

import pluggy
import pytest

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mng.agents.base_agent import BaseAgent
from imbue.mng.api.testing import FakeHost
from imbue.mng.config.data_types import MngConfig
from imbue.mng.config.data_types import MngContext
from imbue.mng.errors import PluginMngError
from imbue.mng.errors import SendMessageError
from imbue.mng.interfaces.data_types import CommandResult
from imbue.mng.interfaces.host import AgentEnvironmentOptions
from imbue.mng.interfaces.host import CreateAgentOptions
from imbue.mng.primitives import AgentId
from imbue.mng.primitives import AgentName
from imbue.mng.primitives import AgentTypeName
from imbue.mng.utils.testing import make_mng_ctx
from imbue.mng_pi_coding.plugin import PiCodingAgent
from imbue.mng_pi_coding.plugin import PiCodingAgentConfig
from imbue.mng_pi_coding.plugin import register_agent_type

# =============================================================================
# Test helpers
# =============================================================================


class _StubHost(FakeHost):
    """FakeHost that stubs specific commands and provides get_env_var."""

    command_results: dict[str, CommandResult] = {}
    env_vars: dict[str, str] = {}

    def execute_command(
        self,
        command: str,
        user: str | None = None,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> CommandResult:
        for pattern, result in self.command_results.items():
            if pattern in command:
                return result
        return super().execute_command(command, user, cwd, env, timeout_seconds)

    def get_env_var(self, key: str) -> str | None:
        return self.env_vars.get(key)


def _make_options(tmp_path: Path) -> CreateAgentOptions:
    return CreateAgentOptions(
        name=AgentName("test"),
        agent_type=AgentTypeName("pi-coding"),
        environment=AgentEnvironmentOptions(),
    )


def _make_test_mng_ctx(tmp_path: Path, *, is_auto_approve: bool = False) -> MngContext:
    return make_mng_ctx(
        config=MngConfig(),
        pm=pluggy.PluginManager("mng"),
        profile_dir=tmp_path / "profile",
        is_interactive=False,
        is_auto_approve=is_auto_approve,
        concurrency_group=ConcurrencyGroup(name="test"),
    )


def _setup_home_pi(tmp_path: Path) -> Path:
    """Create a fake ~/.pi/agent/ directory and return the home path."""
    home_pi = tmp_path / "home" / ".pi" / "agent"
    home_pi.mkdir(parents=True)
    return tmp_path / "home"


def _run_local_setup(host: FakeHost, config: PiCodingAgentConfig, config_dir: Path, home: Path) -> None:
    """Call _setup_local_config_dir with patched home."""
    agent = PiCodingAgent.__new__(PiCodingAgent)
    with patch("imbue.mng_pi_coding.plugin.Path.home", return_value=home):
        agent._setup_local_config_dir(host, config, config_dir)


def _run_remote_setup(host: FakeHost, config: PiCodingAgentConfig, config_dir: Path, home: Path) -> None:
    """Call _setup_remote_config_dir with patched home."""
    agent = PiCodingAgent.__new__(PiCodingAgent)
    with patch("imbue.mng_pi_coding.plugin.Path.home", return_value=home):
        agent._setup_remote_config_dir(host, config, config_dir)


# =============================================================================
# PiCodingAgentConfig tests
# =============================================================================


def test_pi_coding_agent_config_has_correct_defaults() -> None:
    """Verify that PiCodingAgentConfig has the expected default values."""
    config = PiCodingAgentConfig()

    assert str(config.command) == "pi"
    assert config.cli_args == ()
    assert config.permissions == []
    assert config.parent_type is None
    assert config.sync_home_settings is True
    assert config.sync_auth is True
    assert config.check_installation is True


def test_pi_coding_agent_config_merge_with_override() -> None:
    """Verify that merge_with works correctly for PiCodingAgentConfig."""
    base = PiCodingAgentConfig()
    override = PiCodingAgentConfig(cli_args=("--verbose",))

    merged = base.merge_with(override)

    assert isinstance(merged, PiCodingAgentConfig)
    assert merged.cli_args == ("--verbose",)
    assert str(merged.command) == "pi"


# =============================================================================
# PiCodingAgent method tests
# =============================================================================


def test_pi_coding_agent_uses_paste_detection() -> None:
    assert PiCodingAgent.uses_paste_detection_send is not BaseAgent.uses_paste_detection_send


def test_pi_coding_agent_tui_ready_indicator() -> None:
    assert PiCodingAgent.get_tui_ready_indicator is not BaseAgent.get_tui_ready_indicator


def test_pi_coding_agent_expected_process_name() -> None:
    assert PiCodingAgent.get_expected_process_name is not BaseAgent.get_expected_process_name


def test_register_agent_type_returns_correct_tuple() -> None:
    name, agent_class, config_class = register_agent_type()

    assert name == "pi-coding"
    assert agent_class is PiCodingAgent
    assert config_class is PiCodingAgentConfig


# =============================================================================
# _has_api_credentials_available tests
# =============================================================================


def test_on_before_provisioning_warns_when_no_credentials(tmp_path: Path) -> None:
    """Verify on_before_provisioning warns when no API credentials are found."""
    agent = PiCodingAgent.__new__(PiCodingAgent)
    object.__setattr__(agent, "agent_config", PiCodingAgentConfig())
    options = _make_options(tmp_path)
    mng_ctx = _make_test_mng_ctx(tmp_path)

    with patch("imbue.mng_pi_coding.plugin._has_api_credentials_available", return_value=False):
        agent.on_before_provisioning(_StubHost(host_dir=tmp_path), options, mng_ctx)


# =============================================================================
# Provisioning tests
# =============================================================================


def test_setup_local_config_dir_symlinks_auth(tmp_path: Path) -> None:
    home = _setup_home_pi(tmp_path)
    (home / ".pi" / "agent" / "auth.json").write_text('{"anthropic": {}}')

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)

    host = FakeHost(host_dir=tmp_path, is_local=True)
    config = PiCodingAgentConfig()

    _run_local_setup(host, config, config_dir, home)

    assert (config_dir / "auth.json").is_symlink()


def test_setup_remote_config_dir_copies_auth(tmp_path: Path) -> None:
    home = _setup_home_pi(tmp_path)
    auth_content = '{"anthropic": {"type": "api_key"}}'
    (home / ".pi" / "agent" / "auth.json").write_text(auth_content)

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)

    host = FakeHost(host_dir=tmp_path, is_local=False)
    config = PiCodingAgentConfig()

    _run_remote_setup(host, config, config_dir, home)

    assert (config_dir / "auth.json").read_text() == auth_content


def test_setup_local_config_dir_symlinks_settings(tmp_path: Path) -> None:
    home = _setup_home_pi(tmp_path)
    (home / ".pi" / "agent" / "settings.json").write_text('{"defaultModel": "sonnet"}')

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)

    host = FakeHost(host_dir=tmp_path, is_local=True)
    config = PiCodingAgentConfig(sync_home_settings=True)

    _run_local_setup(host, config, config_dir, home)

    assert (config_dir / "settings.json").is_symlink()


def test_setup_local_config_dir_skips_settings_when_disabled(tmp_path: Path) -> None:
    home = _setup_home_pi(tmp_path)
    (home / ".pi" / "agent" / "settings.json").write_text('{"defaultModel": "sonnet"}')

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)

    host = FakeHost(host_dir=tmp_path, is_local=True)
    config = PiCodingAgentConfig(sync_home_settings=False)

    _run_local_setup(host, config, config_dir, home)

    assert not (config_dir / "settings.json").exists()


def test_setup_local_config_dir_symlinks_resource_dirs(tmp_path: Path) -> None:
    home = _setup_home_pi(tmp_path)
    (home / ".pi" / "agent" / "skills").mkdir()
    (home / ".pi" / "agent" / "prompts").mkdir()

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)

    host = FakeHost(host_dir=tmp_path, is_local=True)
    config = PiCodingAgentConfig(sync_home_settings=True)

    _run_local_setup(host, config, config_dir, home)

    assert (config_dir / "skills").is_symlink()
    assert (config_dir / "prompts").is_symlink()


def test_setup_remote_config_dir_copies_settings(tmp_path: Path) -> None:
    home = _setup_home_pi(tmp_path)
    settings_content = '{"defaultModel": "sonnet"}'
    (home / ".pi" / "agent" / "settings.json").write_text(settings_content)

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)

    host = FakeHost(host_dir=tmp_path, is_local=False)
    config = PiCodingAgentConfig(sync_home_settings=True, sync_auth=False)

    _run_remote_setup(host, config, config_dir, home)

    assert (config_dir / "settings.json").read_text() == settings_content


def test_setup_remote_config_dir_copies_resource_files(tmp_path: Path) -> None:
    home = _setup_home_pi(tmp_path)
    skills_dir = home / ".pi" / "agent" / "skills"
    skills_dir.mkdir()
    (skills_dir / "test-skill.md").write_text("# Test Skill")

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)

    host = FakeHost(host_dir=tmp_path, is_local=False)
    config = PiCodingAgentConfig(sync_home_settings=True, sync_auth=False)

    _run_remote_setup(host, config, config_dir, home)

    assert (config_dir / "skills" / "test-skill.md").read_text() == "# Test Skill"


def test_setup_skips_sync_when_disabled(tmp_path: Path) -> None:
    home = _setup_home_pi(tmp_path)
    (home / ".pi" / "agent" / "auth.json").write_text('{"test": true}')
    (home / ".pi" / "agent" / "settings.json").write_text('{"test": true}')

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)

    host = FakeHost(host_dir=tmp_path, is_local=True)
    config = PiCodingAgentConfig(sync_home_settings=False, sync_auth=False)

    _run_local_setup(host, config, config_dir, home)

    assert not (config_dir / "auth.json").exists()
    assert not (config_dir / "settings.json").exists()


def test_modify_env_vars_sets_pi_dir() -> None:
    agent = PiCodingAgent.__new__(PiCodingAgent)
    agent_dir = Path("/fake/agents/agent-123")

    object.__setattr__(agent, "host", FakeHost(host_dir=Path("/fake")))

    with patch.object(PiCodingAgent, "_get_agent_dir", return_value=agent_dir):
        env_vars: dict[str, str] = {}
        agent.modify_env_vars(FakeHost(), env_vars)
        assert "PI_CODING_AGENT_DIR" in env_vars
        assert "plugin/pi_coding" in env_vars["PI_CODING_AGENT_DIR"]


def test_get_expected_process_name_returns_pi() -> None:
    agent = PiCodingAgent.__new__(PiCodingAgent)
    assert agent.get_expected_process_name() == "pi"


def test_uses_paste_detection_returns_true() -> None:
    agent = PiCodingAgent.__new__(PiCodingAgent)
    assert agent.uses_paste_detection_send() is True


def test_get_tui_ready_indicator_returns_pi_v() -> None:
    agent = PiCodingAgent.__new__(PiCodingAgent)
    assert agent.get_tui_ready_indicator() == "pi v"


def test_on_destroy_is_noop(tmp_path: Path) -> None:
    agent = PiCodingAgent.__new__(PiCodingAgent)
    host = FakeHost(host_dir=tmp_path)
    agent.on_destroy(host)


def test_on_after_provisioning_is_noop(tmp_path: Path) -> None:
    agent = PiCodingAgent.__new__(PiCodingAgent)
    host = FakeHost(host_dir=tmp_path)
    options = _make_options(tmp_path)
    mng_ctx = _make_test_mng_ctx(tmp_path)
    agent.on_after_provisioning(host, options, mng_ctx)


def test_get_provision_file_transfers_returns_empty(tmp_path: Path) -> None:
    agent = PiCodingAgent.__new__(PiCodingAgent)
    host = FakeHost(host_dir=tmp_path)
    options = _make_options(tmp_path)
    mng_ctx = _make_test_mng_ctx(tmp_path)
    assert agent.get_provision_file_transfers(host, options, mng_ctx) == []


def test_on_before_provisioning_skips_when_check_disabled(tmp_path: Path) -> None:
    agent = PiCodingAgent.__new__(PiCodingAgent)
    object.__setattr__(agent, "agent_config", PiCodingAgentConfig(check_installation=False))
    host = FakeHost(host_dir=tmp_path, is_local=True)
    options = _make_options(tmp_path)
    mng_ctx = _make_test_mng_ctx(tmp_path)

    agent.on_before_provisioning(host, options, mng_ctx)


def test_send_enter_and_wait_sends_enter(tmp_path: Path) -> None:
    agent = PiCodingAgent.__new__(PiCodingAgent)
    host = _StubHost(
        host_dir=tmp_path,
        is_local=True,
        command_results={"tmux send-keys": CommandResult(stdout="", stderr="", success=True)},
    )
    object.__setattr__(agent, "host", host)
    object.__setattr__(agent, "name", AgentName("test"))

    agent._send_enter_and_wait("mng-test:0")


def test_send_enter_and_wait_raises_on_failure(tmp_path: Path) -> None:
    agent = PiCodingAgent.__new__(PiCodingAgent)
    host = _StubHost(
        host_dir=tmp_path,
        is_local=True,
        command_results={"tmux send-keys": CommandResult(stdout="", stderr="session not found", success=False)},
    )
    object.__setattr__(agent, "host", host)
    object.__setattr__(agent, "name", AgentName("test"))

    with pytest.raises(SendMessageError):
        agent._send_enter_and_wait("mng-test:0")


def test_get_pi_config_dir(tmp_path: Path) -> None:
    agent = PiCodingAgent.__new__(PiCodingAgent)
    agent_dir = tmp_path / "agents" / "agent-123"
    object.__setattr__(agent, "host", FakeHost(host_dir=tmp_path))

    with patch.object(PiCodingAgent, "_get_agent_dir", return_value=agent_dir):
        config_dir = agent.get_pi_config_dir()
        assert config_dir == agent_dir / "plugin" / "pi_coding"


def test_provision_auto_installs_on_remote(tmp_path: Path) -> None:
    host = _StubHost(
        host_dir=tmp_path,
        is_local=False,
        command_results={
            "command -v pi": CommandResult(stdout="", stderr="", success=False),
            "npm install -g": CommandResult(stdout="installed", stderr="", success=True),
            "mkdir -p": CommandResult(stdout="", stderr="", success=True),
        },
    )
    config = PiCodingAgentConfig(check_installation=True, sync_auth=False, sync_home_settings=False)
    options = _make_options(tmp_path)
    mng_ctx = _make_test_mng_ctx(tmp_path, is_auto_approve=True)

    agent = PiCodingAgent.__new__(PiCodingAgent)
    object.__setattr__(agent, "agent_config", config)
    object.__setattr__(agent, "host", host)
    object.__setattr__(agent, "id", AgentId.generate())

    with patch("imbue.mng_pi_coding.plugin.Path.home", return_value=tmp_path / "home"):
        agent.provision(host, options, mng_ctx)


def test_provision_raises_when_remote_install_disabled(tmp_path: Path) -> None:
    host = _StubHost(
        host_dir=tmp_path,
        is_local=False,
        command_results={"command -v pi": CommandResult(stdout="", stderr="", success=False)},
    )
    config = PiCodingAgentConfig(check_installation=True)
    options = _make_options(tmp_path)
    mng_ctx = make_mng_ctx(
        config=MngConfig(is_remote_agent_installation_allowed=False),
        pm=pluggy.PluginManager("mng"),
        profile_dir=tmp_path / "profile",
        is_interactive=False,
        is_auto_approve=False,
        concurrency_group=ConcurrencyGroup(name="test"),
    )

    agent = PiCodingAgent.__new__(PiCodingAgent)
    object.__setattr__(agent, "agent_config", config)

    with pytest.raises(PluginMngError, match="automatic remote installation is disabled"):
        agent.provision(host, options, mng_ctx)


def test_provision_raises_when_pi_not_installed_locally(tmp_path: Path) -> None:
    host = _StubHost(
        host_dir=tmp_path,
        is_local=True,
        command_results={"command -v pi": CommandResult(stdout="", stderr="", success=False)},
    )
    config = PiCodingAgentConfig(check_installation=True)
    options = _make_options(tmp_path)
    mng_ctx = _make_test_mng_ctx(tmp_path, is_auto_approve=False)

    agent = PiCodingAgent.__new__(PiCodingAgent)
    object.__setattr__(agent, "agent_config", config)

    with pytest.raises(PluginMngError, match="pi is not installed"):
        agent.provision(host, options, mng_ctx)
