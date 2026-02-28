from click.testing import CliRunner

from imbue.changelings.main import cli

_RUNNER = CliRunner()


def test_update_requires_agent_name() -> None:
    result = _RUNNER.invoke(cli, ["update"])

    assert result.exit_code != 0
    assert "Missing argument" in result.output


def test_update_help_shows_flags() -> None:
    result = _RUNNER.invoke(cli, ["update", "--help"])

    assert result.exit_code == 0
    assert "--snapshot" in result.output
    assert "--no-snapshot" in result.output
    assert "--push" in result.output
    assert "--no-push" in result.output
    assert "--provision" in result.output
    assert "--no-provision" in result.output


def test_update_help_describes_steps() -> None:
    result = _RUNNER.invoke(cli, ["update", "--help"])

    assert result.exit_code == 0
    assert "snapshot" in result.output.lower()
    assert "AGENT_NAME" in result.output


def test_update_shows_in_cli_help() -> None:
    result = _RUNNER.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "update" in result.output
