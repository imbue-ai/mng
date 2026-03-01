from click.testing import CliRunner

from imbue.changelings.main import cli

_RUNNER = CliRunner()


def test_forward_command_shows_help() -> None:
    result = _RUNNER.invoke(cli, ["forward", "--help"])

    assert result.exit_code == 0
    assert "forwarding server" in result.output
    assert "--host" in result.output
    assert "--port" in result.output


def test_forward_help_shows_data_dir_option() -> None:
    result = _RUNNER.invoke(cli, ["forward", "--help"])

    assert result.exit_code == 0
    assert "--data-dir" in result.output


def test_forward_help_shows_default_host() -> None:
    result = _RUNNER.invoke(cli, ["forward", "--help"])

    assert result.exit_code == 0
    assert "127.0.0.1" in result.output


def test_forward_help_shows_default_port() -> None:
    result = _RUNNER.invoke(cli, ["forward", "--help"])

    assert result.exit_code == 0
    assert "8420" in result.output
