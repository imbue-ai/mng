from click.testing import CliRunner

from imbue.changelings.main import cli


def test_cli_shows_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "deploy" in result.output
    assert "server" in result.output


def test_cli_deploy_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["deploy", "--help"])

    assert result.exit_code == 0
    assert "ZYGOTE_PATH" in result.output


def test_cli_server_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["server", "--help"])

    assert result.exit_code == 0
    assert "forwarding server" in result.output
