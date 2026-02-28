from click.testing import CliRunner

from imbue.changelings.main import cli


def test_server_command_shows_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["server", "--help"])

    assert result.exit_code == 0
    assert "forwarding server" in result.output
    assert "--host" in result.output
    assert "--port" in result.output
