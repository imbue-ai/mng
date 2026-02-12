from click.testing import CliRunner

from imbue.mngr.cli.completion_command import completion_command


def test_completion_command_bash_outputs_bash_script() -> None:
    runner = CliRunner()
    result = runner.invoke(completion_command, ["bash"])

    assert result.exit_code == 0
    assert "_MNGR_COMPLETE" in result.output
    assert "bash_complete" in result.output
    assert "COMPREPLY" in result.output


def test_completion_command_zsh_outputs_zsh_script() -> None:
    runner = CliRunner()
    result = runner.invoke(completion_command, ["zsh"])

    assert result.exit_code == 0
    assert "_MNGR_COMPLETE" in result.output
    assert "zsh_complete" in result.output
    assert "compdef" in result.output


def test_completion_command_fish_outputs_fish_script() -> None:
    runner = CliRunner()
    result = runner.invoke(completion_command, ["fish"])

    assert result.exit_code == 0
    assert "_MNGR_COMPLETE" in result.output
    assert "fish_complete" in result.output
    assert "complete --no-files --command mngr" in result.output


def test_completion_command_invalid_shell_fails() -> None:
    runner = CliRunner()
    result = runner.invoke(completion_command, ["powershell"])

    assert result.exit_code != 0


def test_completion_command_no_arg_fails() -> None:
    runner = CliRunner()
    result = runner.invoke(completion_command, [])

    assert result.exit_code != 0
