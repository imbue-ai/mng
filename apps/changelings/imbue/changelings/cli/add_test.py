# Tests for the changeling add CLI command.

from pathlib import Path

import pytest
from click.testing import CliRunner

from imbue.changelings.cli.add import add
from imbue.changelings.config import get_changeling
from imbue.changelings.config import load_config
from imbue.changelings.data_types import DEFAULT_INITIAL_MESSAGE
from imbue.changelings.primitives import ChangelingName


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate config operations to a temporary home directory."""
    monkeypatch.setenv("HOME", str(tmp_path))


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


_REQUIRED_ARGS = [
    "test-guardian",
    "--disabled",
]


def test_add_disabled_saves_to_config_without_deploying(cli_runner: CliRunner) -> None:
    """Adding with --disabled should save to config but not deploy to Modal."""
    result = cli_runner.invoke(add, _REQUIRED_ARGS)

    assert result.exit_code == 0
    assert "added to config (disabled, not deployed to Modal)" in result.output


def test_add_disabled_changeling_is_in_config(cli_runner: CliRunner) -> None:
    """A disabled changeling should be persisted in the config file."""
    cli_runner.invoke(add, _REQUIRED_ARGS)

    changeling = get_changeling(ChangelingName("test-guardian"))
    assert changeling.name == ChangelingName("test-guardian")
    assert changeling.is_enabled is False


def test_add_disabled_uses_correct_fields(cli_runner: CliRunner) -> None:
    """A disabled changeling should have all the CLI args stored correctly."""
    cli_runner.invoke(
        add,
        [
            "my-fairy",
            "--repo",
            "https://github.com/org/repo.git",
            "--schedule",
            "0 4 * * 1",
            "--branch",
            "develop",
            "--agent-type",
            "claude",
            "--message",
            "Fix all the things",
            "--disabled",
        ],
    )

    changeling = get_changeling(ChangelingName("my-fairy"))
    assert str(changeling.repo) == "https://github.com/org/repo.git"
    assert str(changeling.schedule) == "0 4 * * 1"
    assert changeling.branch == "develop"
    assert changeling.agent_type == "claude"
    assert changeling.initial_message == "Fix all the things"
    assert changeling.is_enabled is False


def test_add_disabled_uses_default_message_when_not_specified(cli_runner: CliRunner) -> None:
    """When --message is not specified, the default initial message should be used."""
    cli_runner.invoke(add, _REQUIRED_ARGS)

    changeling = get_changeling(ChangelingName("test-guardian"))
    assert changeling.initial_message == DEFAULT_INITIAL_MESSAGE


def test_add_duplicate_name_exits_with_error(cli_runner: CliRunner) -> None:
    """Adding a changeling with a name that already exists should fail."""
    cli_runner.invoke(add, _REQUIRED_ARGS)

    result = cli_runner.invoke(add, _REQUIRED_ARGS)

    assert result.exit_code == 1


def test_add_duplicate_name_does_not_overwrite(cli_runner: CliRunner) -> None:
    """A failed duplicate add should leave the original config unchanged."""
    cli_runner.invoke(
        add,
        ["test-guardian", "--branch", "original", "--disabled"],
    )

    cli_runner.invoke(
        add,
        ["test-guardian", "--branch", "replacement", "--disabled"],
    )

    changeling = get_changeling(ChangelingName("test-guardian"))
    assert changeling.branch == "original"


def test_add_enabled_exits_with_error_when_deploy_fails(cli_runner: CliRunner) -> None:
    """Adding an enabled changeling should fail gracefully when deploy fails.

    Without Modal credentials, deploy_changeling will raise ChangelingDeployError.
    The add command should catch this and exit with code 1.
    """
    result = cli_runner.invoke(add, ["test-guardian"])

    assert result.exit_code == 1


def test_add_enabled_still_saves_to_config_before_deploy_attempt(cli_runner: CliRunner) -> None:
    """Even if deploy fails, the changeling should be saved to config.

    This is by design -- the user can fix the deploy issue and retry.
    """
    cli_runner.invoke(add, ["test-guardian"])

    config = load_config()
    assert ChangelingName("test-guardian") in config.changeling_by_name


def test_add_with_secrets_stores_them(cli_runner: CliRunner) -> None:
    """Custom --secret options should be stored in the config."""
    cli_runner.invoke(
        add,
        ["my-fairy", "--disabled", "--secret", "MY_TOKEN", "--secret", "OTHER_KEY"],
    )

    changeling = get_changeling(ChangelingName("my-fairy"))
    assert changeling.secrets == ("MY_TOKEN", "OTHER_KEY")


def test_add_with_env_vars_stores_them(cli_runner: CliRunner) -> None:
    """Custom --env-var options should be stored in the config."""
    cli_runner.invoke(
        add,
        ["my-fairy", "--disabled", "--env-var", "DEBUG=true", "--env-var", "LOG_LEVEL=debug"],
    )

    changeling = get_changeling(ChangelingName("my-fairy"))
    assert changeling.env_vars == {"DEBUG": "true", "LOG_LEVEL": "debug"}


def test_add_with_mngr_options_stores_them(cli_runner: CliRunner) -> None:
    """Custom -o/--option options should be stored in the config."""
    cli_runner.invoke(
        add,
        ["my-fairy", "--disabled", "-o", "gpu=a10g", "-o", "timeout=600"],
    )

    changeling = get_changeling(ChangelingName("my-fairy"))
    assert changeling.mngr_options == {"gpu": "a10g", "timeout": "600"}


def test_add_with_extra_mngr_args_stores_them(cli_runner: CliRunner) -> None:
    """Custom --extra-mngr-args should be stored in the config."""
    cli_runner.invoke(
        add,
        ["my-fairy", "--disabled", "--extra-mngr-args", "--verbose --timeout 300"],
    )

    changeling = get_changeling(ChangelingName("my-fairy"))
    assert changeling.extra_mngr_args == "--verbose --timeout 300"
