"""Tests for the changeling deployment logic."""

import json
from pathlib import Path

from imbue.changelings.data_types import ChangelingDefinition
from imbue.changelings.data_types import DEFAULT_INITIAL_MESSAGE
from imbue.changelings.data_types import DEFAULT_SECRETS
from imbue.changelings.deploy.deploy import build_deploy_env
from imbue.changelings.deploy.deploy import build_modal_deploy_command
from imbue.changelings.deploy.deploy import build_modal_secret_command
from imbue.changelings.deploy.deploy import collect_secret_values
from imbue.changelings.deploy.deploy import get_modal_app_name
from imbue.changelings.deploy.deploy import get_modal_secret_name
from imbue.changelings.deploy.deploy import serialize_changeling_config
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
