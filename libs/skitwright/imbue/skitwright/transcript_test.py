from imbue.skitwright.data_types import CommandResult
from imbue.skitwright.transcript import Transcript


def test_empty_transcript_formats_as_empty_string() -> None:
    t = Transcript()
    assert t.format() == ""


def test_single_command_transcript() -> None:
    t = Transcript()
    t.record(CommandResult(command="echo hello", exit_code=0, stdout="hello\n", stderr=""))
    assert t.format() == "$ echo hello\n  hello\n? 0\n"


def test_command_with_stderr() -> None:
    t = Transcript()
    t.record(CommandResult(command="bad-cmd", exit_code=1, stdout="", stderr="not found\n"))
    assert t.format() == "$ bad-cmd\n! not found\n? 1\n"


def test_multiline_stdout() -> None:
    t = Transcript()
    t.record(CommandResult(command="ls", exit_code=0, stdout="a\nb\nc", stderr=""))
    assert t.format() == "$ ls\n  a\n  b\n  c\n? 0\n"


def test_multiple_commands() -> None:
    t = Transcript()
    t.record(CommandResult(command="cmd1", exit_code=0, stdout="out1", stderr=""))
    t.record(CommandResult(command="cmd2", exit_code=1, stdout="", stderr="err2"))
    expected = "$ cmd1\n  out1\n? 0\n$ cmd2\n! err2\n? 1\n"
    assert t.format() == expected


def test_command_with_both_stdout_and_stderr() -> None:
    t = Transcript()
    t.record(CommandResult(command="mixed", exit_code=0, stdout="output", stderr="warning"))
    assert t.format() == "$ mixed\n  output\n! warning\n? 0\n"
