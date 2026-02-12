"""Tests for the changeling run command."""

import sys
from pathlib import Path

import pytest

from imbue.changelings.cli.run import _write_secrets_env_file
from imbue.changelings.cli.run import build_mngr_create_command
from imbue.changelings.data_types import ChangelingDefinition
from imbue.changelings.data_types import DEFAULT_INITIAL_MESSAGE
from imbue.changelings.primitives import ChangelingName
from imbue.changelings.primitives import ChangelingTemplateName


def _make_changeling(
    name: str = "test-changeling",
    template: str = "code-guardian",
    agent_type: str = "code-guardian",
    branch: str = "main",
    initial_message: str = DEFAULT_INITIAL_MESSAGE,
    extra_mngr_args: str = "",
    env_vars: dict[str, str] | None = None,
    secrets: tuple[str, ...] | None = None,
) -> ChangelingDefinition:
    """Create a ChangelingDefinition for testing."""
    kwargs: dict = {
        "name": ChangelingName(name),
        "template": ChangelingTemplateName(template),
        "agent_type": agent_type,
        "branch": branch,
        "initial_message": initial_message,
        "extra_mngr_args": extra_mngr_args,
        "env_vars": env_vars or {},
    }
    if secrets is not None:
        kwargs["secrets"] = secrets
    return ChangelingDefinition(**kwargs)


# -- Local execution tests (is_modal=False) --


def test_build_command_includes_python_executable_and_mngr_module() -> None:
    """The command should invoke Python with the mngr main module."""
    changeling = _make_changeling()
    cmd = build_mngr_create_command(changeling, is_modal=False, env_file_path=None)

    assert cmd[0] == sys.executable
    assert cmd[1] == "-m"
    assert cmd[2] == "imbue.mngr.main"
    assert cmd[3] == "create"


def test_build_command_includes_agent_name_with_timestamp() -> None:
    """The agent name should include the changeling name and a timestamp."""
    changeling = _make_changeling(name="my-guardian")
    cmd = build_mngr_create_command(changeling, is_modal=False, env_file_path=None)

    # The agent name is the 5th element (index 4)
    agent_name = cmd[4]
    assert agent_name.startswith("my-guardian-")
    # Should have a timestamp suffix like YYYY-MM-DD-HH-MM-SS
    suffix = agent_name[len("my-guardian-") :]
    parts = suffix.split("-")
    assert len(parts) == 6  # year, month, day, hour, minute, second


def test_build_command_uses_agent_type_from_definition() -> None:
    """The command should use the agent type from the changeling definition."""
    changeling = _make_changeling(agent_type="code-guardian")
    cmd = build_mngr_create_command(changeling, is_modal=False, env_file_path=None)

    # The agent type is the 6th element (index 5)
    assert cmd[5] == "code-guardian"


def test_build_command_includes_no_connect_flag() -> None:
    """The command should include --no-connect since changelings run unattended."""
    changeling = _make_changeling()
    cmd = build_mngr_create_command(changeling, is_modal=False, env_file_path=None)

    assert "--no-connect" in cmd


def test_build_command_includes_await_agent_stopped_flag() -> None:
    """The command should include --await-agent-stopped to wait for completion."""
    changeling = _make_changeling()
    cmd = build_mngr_create_command(changeling, is_modal=False, env_file_path=None)

    assert "--await-agent-stopped" in cmd


def test_build_command_includes_creator_tag() -> None:
    """The command should tag the agent as created by changeling."""
    changeling = _make_changeling()
    cmd = build_mngr_create_command(changeling, is_modal=False, env_file_path=None)

    tag_idx = cmd.index("CREATOR=changeling")
    assert cmd[tag_idx - 1] == "--tag"


def test_build_command_includes_changeling_name_tag() -> None:
    """The command should tag the agent with the changeling name."""
    changeling = _make_changeling(name="my-guardian")
    cmd = build_mngr_create_command(changeling, is_modal=False, env_file_path=None)

    assert "CHANGELING=my-guardian" in cmd


def test_build_command_includes_base_branch() -> None:
    """The command should set --base-branch from the changeling definition."""
    changeling = _make_changeling(branch="develop")
    cmd = build_mngr_create_command(changeling, is_modal=False, env_file_path=None)

    branch_idx = cmd.index("--base-branch")
    assert cmd[branch_idx + 1] == "develop"


def test_build_command_includes_new_branch_with_changeling_name() -> None:
    """The command should create a new branch named after the changeling."""
    changeling = _make_changeling(name="my-guardian")
    cmd = build_mngr_create_command(changeling, is_modal=False, env_file_path=None)

    branch_idx = cmd.index("--new-branch")
    branch_name = cmd[branch_idx + 1]
    assert branch_name.startswith("changelings/my-guardian-")


def test_build_command_always_includes_message() -> None:
    """The command should always include --message with the initial_message."""
    changeling = _make_changeling()
    cmd = build_mngr_create_command(changeling, is_modal=False, env_file_path=None)

    assert "--message" in cmd
    message_idx = cmd.index("--message")
    assert cmd[message_idx + 1] == DEFAULT_INITIAL_MESSAGE


def test_build_command_uses_custom_initial_message() -> None:
    """A custom initial_message should be passed via --message."""
    changeling = _make_changeling(initial_message="Do something specific")
    cmd = build_mngr_create_command(changeling, is_modal=False, env_file_path=None)

    message_idx = cmd.index("--message")
    assert cmd[message_idx + 1] == "Do something specific"


def test_build_command_includes_env_vars() -> None:
    """Environment variables from the changeling should be passed via --host-env."""
    changeling = _make_changeling(env_vars={"API_KEY": "abc123", "DEBUG": "true"})
    cmd = build_mngr_create_command(changeling, is_modal=False, env_file_path=None)

    assert "--host-env" in cmd
    assert "API_KEY=abc123" in cmd
    assert "DEBUG=true" in cmd


def test_build_command_includes_extra_mngr_args() -> None:
    """Extra mngr args from the changeling should be appended to the command."""
    changeling = _make_changeling(extra_mngr_args="--verbose --timeout 300")
    cmd = build_mngr_create_command(changeling, is_modal=False, env_file_path=None)

    assert "--verbose" in cmd
    assert "--timeout" in cmd
    assert "300" in cmd


def test_build_command_local_does_not_include_modal_flag() -> None:
    """Local execution should not include --in modal."""
    changeling = _make_changeling()
    cmd = build_mngr_create_command(changeling, is_modal=False, env_file_path=None)

    assert "--in" not in cmd
    assert "modal" not in cmd


def test_build_command_local_does_not_include_host_env_file() -> None:
    """Local execution should not include --host-env-file."""
    changeling = _make_changeling()
    cmd = build_mngr_create_command(changeling, is_modal=False, env_file_path=None)

    assert "--host-env-file" not in cmd


# -- Modal execution tests (is_modal=True) --


def test_build_command_modal_includes_in_modal_flag() -> None:
    """Modal execution should include --in modal."""
    changeling = _make_changeling()
    cmd = build_mngr_create_command(changeling, is_modal=True, env_file_path=None)

    in_idx = cmd.index("--in")
    assert cmd[in_idx + 1] == "modal"


def test_build_command_modal_includes_env_file_path() -> None:
    """Modal execution should include --host-env-file when a path is provided."""
    changeling = _make_changeling()
    env_file = Path("/tmp/test-secrets.env")
    cmd = build_mngr_create_command(changeling, is_modal=True, env_file_path=env_file)

    file_idx = cmd.index("--host-env-file")
    assert cmd[file_idx + 1] == str(env_file)


def test_build_command_modal_omits_env_file_when_none() -> None:
    """Modal execution should not include --host-env-file when no path is given."""
    changeling = _make_changeling()
    cmd = build_mngr_create_command(changeling, is_modal=True, env_file_path=None)

    assert "--host-env-file" not in cmd


def test_build_command_modal_does_not_include_pass_host_env() -> None:
    """Modal execution should not use --pass-host-env (secrets go via env file)."""
    changeling = _make_changeling()
    cmd = build_mngr_create_command(changeling, is_modal=True, env_file_path=None)

    assert "--pass-host-env" not in cmd


def test_build_command_modal_still_includes_env_vars() -> None:
    """Modal execution should still pass explicit env vars via --host-env."""
    changeling = _make_changeling(env_vars={"DEBUG": "true"})
    cmd = build_mngr_create_command(changeling, is_modal=True, env_file_path=None)

    assert "--host-env" in cmd
    assert "DEBUG=true" in cmd


def test_build_command_modal_still_includes_core_flags() -> None:
    """Modal execution should still include core flags like --no-connect and tags."""
    changeling = _make_changeling()
    cmd = build_mngr_create_command(changeling, is_modal=True, env_file_path=None)

    assert "--no-connect" in cmd
    assert "--await-agent-stopped" in cmd
    assert "--no-ensure-clean" in cmd
    assert "CREATOR=changeling" in cmd


def test_build_command_modal_includes_extra_mngr_args() -> None:
    """Modal execution should still append extra mngr args."""
    changeling = _make_changeling(extra_mngr_args="--gpu a10g --timeout 600")
    cmd = build_mngr_create_command(changeling, is_modal=True, env_file_path=None)

    assert "--gpu" in cmd
    assert "a10g" in cmd
    assert "--timeout" in cmd
    assert "600" in cmd


# -- _write_secrets_env_file tests --


def test_write_secrets_env_file_writes_secrets_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Secrets present in the environment should be written as KEY=VALUE lines."""
    monkeypatch.setenv("TEST_SECRET_A", "value_a")
    monkeypatch.setenv("TEST_SECRET_B", "value_b")
    changeling = _make_changeling(secrets=("TEST_SECRET_A", "TEST_SECRET_B"))

    env_file = _write_secrets_env_file(changeling)
    try:
        content = env_file.read_text()
        assert "TEST_SECRET_A=value_a\n" in content
        assert "TEST_SECRET_B=value_b\n" in content
    finally:
        env_file.unlink()


def test_write_secrets_env_file_skips_missing_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Secrets not present in the environment should be skipped."""
    monkeypatch.setenv("TEST_SECRET_PRESENT", "here")
    monkeypatch.delenv("TEST_SECRET_MISSING", raising=False)
    changeling = _make_changeling(secrets=("TEST_SECRET_PRESENT", "TEST_SECRET_MISSING"))

    env_file = _write_secrets_env_file(changeling)
    try:
        content = env_file.read_text()
        assert "TEST_SECRET_PRESENT=here\n" in content
        assert "TEST_SECRET_MISSING" not in content
    finally:
        env_file.unlink()


def test_write_secrets_env_file_creates_file_with_restricted_permissions() -> None:
    """The env file should have 0o600 permissions (owner read/write only)."""
    changeling = _make_changeling(secrets=())

    env_file = _write_secrets_env_file(changeling)
    try:
        permissions = oct(env_file.stat().st_mode & 0o777)
        assert permissions == oct(0o600)
    finally:
        env_file.unlink()


def test_write_secrets_env_file_produces_empty_file_when_no_secrets() -> None:
    """An empty secrets tuple should produce an empty env file."""
    changeling = _make_changeling(secrets=())

    env_file = _write_secrets_env_file(changeling)
    try:
        content = env_file.read_text()
        assert content == ""
    finally:
        env_file.unlink()
