# Tests for the changeling deployment logic.

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from imbue.changelings.conftest import make_test_changeling
from imbue.changelings.data_types import ChangelingDefinition
from imbue.changelings.data_types import DEFAULT_INITIAL_MESSAGE
from imbue.changelings.data_types import DEFAULT_SECRETS
from imbue.changelings.deploy.deploy import build_cron_mngr_command
from imbue.changelings.deploy.deploy import build_deploy_env
from imbue.changelings.deploy.deploy import build_modal_deploy_command
from imbue.changelings.deploy.deploy import build_modal_secret_command
from imbue.changelings.deploy.deploy import collect_secret_values
from imbue.changelings.deploy.deploy import create_modal_secret
from imbue.changelings.deploy.deploy import deploy_changeling
from imbue.changelings.deploy.deploy import find_repo_root
from imbue.changelings.deploy.deploy import get_modal_app_name
from imbue.changelings.deploy.deploy import get_modal_secret_name
from imbue.changelings.deploy.deploy import serialize_changeling_config
from imbue.changelings.errors import ChangelingDeployError
from imbue.changelings.primitives import ChangelingName
from imbue.changelings.primitives import ChangelingTemplateName

# -- get_modal_app_name tests --


def test_get_modal_app_name_prefixes_with_changeling() -> None:
    assert get_modal_app_name("code-guardian") == "changeling-code-guardian"


def test_get_modal_app_name_preserves_full_name() -> None:
    assert get_modal_app_name("my-fancy-fairy-bot") == "changeling-my-fancy-fairy-bot"


# -- get_modal_secret_name tests --


def test_get_modal_secret_name_includes_changeling_name() -> None:
    assert get_modal_secret_name("code-guardian") == "changeling-code-guardian-secrets"


def test_get_modal_secret_name_uses_secrets_suffix() -> None:
    result = get_modal_secret_name("test")
    assert result.endswith("-secrets")


# -- build_deploy_env tests --


def test_build_deploy_env_includes_all_required_vars() -> None:
    env = build_deploy_env(
        app_name="changeling-test",
        config_json='{"name": "test"}',
        cron_schedule="0 3 * * *",
        repo_root="/path/to/repo",
        secret_name="changeling-test-secrets",
    )

    assert env["CHANGELING_MODAL_APP_NAME"] == "changeling-test"
    assert env["CHANGELING_CONFIG_JSON"] == '{"name": "test"}'
    assert env["CHANGELING_CRON_SCHEDULE"] == "0 3 * * *"
    assert env["CHANGELING_REPO_ROOT"] == "/path/to/repo"
    assert env["CHANGELING_SECRET_NAME"] == "changeling-test-secrets"


def test_build_deploy_env_returns_exactly_five_keys() -> None:
    env = build_deploy_env(
        app_name="a",
        config_json="{}",
        cron_schedule="* * * * *",
        repo_root="/r",
        secret_name="s",
    )

    assert len(env) == 5


# -- build_modal_deploy_command tests --


def test_build_modal_deploy_command_basic() -> None:
    cmd = build_modal_deploy_command(
        cron_runner_path=Path("/deploy/cron_runner.py"),
        environment_name=None,
    )

    assert cmd == ["uv", "run", "modal", "deploy", "/deploy/cron_runner.py"]


def test_build_modal_deploy_command_with_environment() -> None:
    cmd = build_modal_deploy_command(
        cron_runner_path=Path("/deploy/cron_runner.py"),
        environment_name="test-env",
    )

    assert cmd == ["uv", "run", "modal", "deploy", "--env", "test-env", "/deploy/cron_runner.py"]


def test_build_modal_deploy_command_environment_comes_before_path() -> None:
    """The --env flag must come before the script path (Modal CLI requirement)."""
    cmd = build_modal_deploy_command(
        cron_runner_path=Path("/script.py"),
        environment_name="my-env",
    )

    env_idx = cmd.index("--env")
    path_idx = cmd.index("/script.py")
    assert env_idx < path_idx


# -- build_modal_secret_command tests --


def test_build_modal_secret_command_basic() -> None:
    cmd = build_modal_secret_command(
        secret_name="my-secret",
        secret_values={"KEY": "val"},
        environment_name=None,
    )

    assert cmd[:6] == ["uv", "run", "modal", "secret", "create", "my-secret"]
    assert "KEY=val" in cmd
    assert "--force" in cmd


def test_build_modal_secret_command_with_multiple_values() -> None:
    cmd = build_modal_secret_command(
        secret_name="s",
        secret_values={"A": "1", "B": "2"},
        environment_name=None,
    )

    assert "A=1" in cmd
    assert "B=2" in cmd


def test_build_modal_secret_command_with_environment() -> None:
    cmd = build_modal_secret_command(
        secret_name="s",
        secret_values={"A": "1"},
        environment_name="test-env",
    )

    assert "--env" in cmd
    assert "test-env" in cmd


def test_build_modal_secret_command_force_flag_always_present() -> None:
    """The --force flag ensures the secret is updated if it already exists."""
    cmd = build_modal_secret_command(
        secret_name="s",
        secret_values={},
        environment_name=None,
    )

    assert "--force" in cmd


def test_build_modal_secret_command_empty_values() -> None:
    """An empty secret_values dict should still produce a valid command."""
    cmd = build_modal_secret_command(
        secret_name="empty-secret",
        secret_values={},
        environment_name=None,
    )

    assert "empty-secret" in cmd
    assert "--force" in cmd


# -- collect_secret_values tests --


def test_collect_secret_values_returns_matching_values() -> None:
    env = {"TOKEN": "abc", "KEY": "xyz", "OTHER": "ignored"}
    result = collect_secret_values(["TOKEN", "KEY"], env)

    assert result == {"TOKEN": "abc", "KEY": "xyz"}


def test_collect_secret_values_skips_missing() -> None:
    env = {"TOKEN": "abc"}
    result = collect_secret_values(["TOKEN", "MISSING_KEY"], env)

    assert result == {"TOKEN": "abc"}


def test_collect_secret_values_returns_empty_when_none_found() -> None:
    env = {"UNRELATED": "value"}
    result = collect_secret_values(["TOKEN", "KEY"], env)

    assert result == {}


def test_collect_secret_values_empty_names() -> None:
    env = {"TOKEN": "abc"}
    result = collect_secret_values([], env)

    assert result == {}


# -- serialize_changeling_config tests --


def test_serialize_changeling_config_produces_valid_json() -> None:
    changeling = ChangelingDefinition(
        name=ChangelingName("test"),
        template=ChangelingTemplateName("code-guardian"),
        agent_type="code-guardian",
    )

    config_json = serialize_changeling_config(changeling)
    parsed = json.loads(config_json)

    assert parsed["name"] == "test"
    assert parsed["template"] == "code-guardian"
    assert parsed["agent_type"] == "code-guardian"


def test_serialize_changeling_config_includes_all_fields() -> None:
    changeling = ChangelingDefinition(
        name=ChangelingName("my-fairy"),
        template=ChangelingTemplateName("fixme-fairy"),
        agent_type="claude",
        branch="develop",
        initial_message="Fix all the things",
        extra_mngr_args="--verbose",
        env_vars={"DEBUG": "true"},
        secrets=("MY_TOKEN",),
    )

    config_json = serialize_changeling_config(changeling)
    parsed = json.loads(config_json)

    assert parsed["name"] == "my-fairy"
    assert parsed["template"] == "fixme-fairy"
    assert parsed["agent_type"] == "claude"
    assert parsed["branch"] == "develop"
    assert parsed["initial_message"] == "Fix all the things"
    assert parsed["extra_mngr_args"] == "--verbose"
    assert parsed["env_vars"] == {"DEBUG": "true"}
    assert parsed["secrets"] == ["MY_TOKEN"]


def test_serialize_changeling_config_roundtrip_preserves_defaults() -> None:
    """Serialized config should include default values for completeness."""
    changeling = ChangelingDefinition(
        name=ChangelingName("test"),
        template=ChangelingTemplateName("code-guardian"),
    )

    config_json = serialize_changeling_config(changeling)
    parsed = json.loads(config_json)

    assert parsed["branch"] == "main"
    assert parsed["initial_message"] == DEFAULT_INITIAL_MESSAGE
    assert parsed["secrets"] == list(DEFAULT_SECRETS)
    assert parsed["is_enabled"] is True


# -- build_cron_mngr_command tests --


def test_build_cron_mngr_command_starts_with_uv_run_mngr() -> None:
    """The cron command should use `uv run mngr` instead of python -m."""
    changeling = make_test_changeling()
    env_file = Path("/tmp/test.env")
    cmd = build_cron_mngr_command(changeling, env_file)

    assert cmd[0] == "uv"
    assert cmd[1] == "run"
    assert cmd[2] == "mngr"
    assert cmd[3] == "create"


def test_build_cron_mngr_command_does_not_include_python_executable() -> None:
    """The cron command should NOT include sys.executable or -m flag."""
    changeling = make_test_changeling()
    env_file = Path("/tmp/test.env")
    cmd = build_cron_mngr_command(changeling, env_file)

    assert sys.executable not in cmd
    assert "-m" not in cmd
    assert "imbue.mngr.main" not in cmd


def test_build_cron_mngr_command_includes_modal_flag() -> None:
    """The cron command should always target Modal."""
    changeling = make_test_changeling()
    env_file = Path("/tmp/test.env")
    cmd = build_cron_mngr_command(changeling, env_file)

    in_idx = cmd.index("--in")
    assert cmd[in_idx + 1] == "modal"


def test_build_cron_mngr_command_includes_env_file() -> None:
    """The cron command should include the env file path."""
    changeling = make_test_changeling()
    env_file = Path("/tmp/my-secrets.env")
    cmd = build_cron_mngr_command(changeling, env_file)

    file_idx = cmd.index("--host-env-file")
    assert cmd[file_idx + 1] == "/tmp/my-secrets.env"


def test_build_cron_mngr_command_includes_core_flags() -> None:
    """The cron command should include all core changeling flags."""
    changeling = make_test_changeling()
    env_file = Path("/tmp/test.env")
    cmd = build_cron_mngr_command(changeling, env_file)

    assert "--no-connect" in cmd
    assert "--await-agent-stopped" in cmd
    assert "--no-ensure-clean" in cmd
    assert "CREATOR=changeling" in cmd


def test_build_cron_mngr_command_includes_agent_name_with_timestamp() -> None:
    """The agent name should include the changeling name and a timestamp."""
    changeling = make_test_changeling(name="my-guardian")
    env_file = Path("/tmp/test.env")
    cmd = build_cron_mngr_command(changeling, env_file)

    agent_name = cmd[4]
    assert agent_name.startswith("my-guardian-")


def test_build_cron_mngr_command_uses_agent_type() -> None:
    """The cron command should use the configured agent type."""
    changeling = make_test_changeling(agent_type="code-guardian")
    env_file = Path("/tmp/test.env")
    cmd = build_cron_mngr_command(changeling, env_file)

    assert cmd[5] == "code-guardian"


def test_build_cron_mngr_command_includes_extra_mngr_args() -> None:
    """Extra mngr args should be appended to the cron command."""
    changeling = make_test_changeling(extra_mngr_args="--verbose --timeout 300")
    env_file = Path("/tmp/test.env")
    cmd = build_cron_mngr_command(changeling, env_file)

    assert "--verbose" in cmd
    assert "--timeout" in cmd
    assert "300" in cmd


# -- find_repo_root tests --


@patch("imbue.changelings.deploy.deploy.subprocess.run")
def test_find_repo_root_returns_path_on_success(mock_run: MagicMock) -> None:
    """A successful git rev-parse should return the repo root path."""
    mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="/home/user/repo\n", stderr="")

    result = find_repo_root()

    assert result == Path("/home/user/repo")


@patch("imbue.changelings.deploy.deploy.subprocess.run")
def test_find_repo_root_raises_when_not_in_git_repo(mock_run: MagicMock) -> None:
    """When git rev-parse fails, ChangelingDeployError should be raised."""
    mock_run.return_value = subprocess.CompletedProcess(
        args=[], returncode=128, stdout="", stderr="fatal: not a git repository"
    )

    with pytest.raises(ChangelingDeployError, match="Could not find git repository root"):
        find_repo_root()


# -- create_modal_secret tests --


@patch("imbue.changelings.deploy.deploy.subprocess.run")
def test_create_modal_secret_returns_secret_name_on_success(mock_run: MagicMock) -> None:
    """A successful modal secret create should return the secret name."""
    mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    changeling = make_test_changeling(name="my-guardian", secrets=())

    result = create_modal_secret(changeling)

    assert result == "changeling-my-guardian-secrets"


@patch("imbue.changelings.deploy.deploy.subprocess.run")
def test_create_modal_secret_raises_on_failure(mock_run: MagicMock) -> None:
    """A failed modal secret create should raise ChangelingDeployError."""
    mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="permission denied")
    changeling = make_test_changeling(secrets=())

    with pytest.raises(ChangelingDeployError, match="Failed to create Modal secret"):
        create_modal_secret(changeling)


@patch("imbue.changelings.deploy.deploy.subprocess.run")
def test_create_modal_secret_passes_environment_name(mock_run: MagicMock) -> None:
    """The environment name should be forwarded to the modal CLI."""
    mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    changeling = make_test_changeling(secrets=())

    create_modal_secret(changeling, environment_name="test-env")

    cmd = mock_run.call_args[0][0]
    assert "--env" in cmd
    assert "test-env" in cmd


# -- deploy_changeling tests --


@patch("imbue.changelings.deploy.deploy.subprocess.run")
@patch("imbue.changelings.deploy.deploy.find_repo_root")
def test_deploy_changeling_returns_app_name_on_success(
    mock_find_root: MagicMock,
    mock_run: MagicMock,
) -> None:
    """A successful deploy should return the Modal app name."""
    mock_find_root.return_value = Path("/repo")
    mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    changeling = make_test_changeling(name="my-guardian", secrets=())

    result = deploy_changeling(changeling)

    assert result == "changeling-my-guardian"


@patch("imbue.changelings.deploy.deploy.subprocess.run")
@patch("imbue.changelings.deploy.deploy.find_repo_root")
def test_deploy_changeling_raises_on_deploy_failure(
    mock_find_root: MagicMock,
    mock_run: MagicMock,
) -> None:
    """A failed modal deploy should raise ChangelingDeployError."""
    mock_find_root.return_value = Path("/repo")
    # First call (secret create) succeeds, second call (deploy) fails
    mock_run.side_effect = [
        subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
        subprocess.CompletedProcess(args=[], returncode=1, stdout="error output", stderr="deploy failed"),
    ]
    changeling = make_test_changeling(secrets=())

    with pytest.raises(ChangelingDeployError, match="Failed to deploy changeling"):
        deploy_changeling(changeling)


@patch("imbue.changelings.deploy.deploy.subprocess.run")
@patch("imbue.changelings.deploy.deploy.find_repo_root")
def test_deploy_changeling_creates_secret_and_deploys(
    mock_find_root: MagicMock,
    mock_run: MagicMock,
) -> None:
    """Deploy should create a secret first, then deploy the cron runner."""
    mock_find_root.return_value = Path("/repo")
    mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    changeling = make_test_changeling(secrets=())

    deploy_changeling(changeling)

    # Should have been called twice: once for secret creation, once for deploy
    assert mock_run.call_count == 2
    secret_cmd = mock_run.call_args_list[0][0][0]
    deploy_cmd = mock_run.call_args_list[1][0][0]
    assert "secret" in secret_cmd
    assert "deploy" in deploy_cmd
