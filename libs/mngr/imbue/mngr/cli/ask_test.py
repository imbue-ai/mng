import pytest

from imbue.mngr.cli.ask import AskCliOptions
from imbue.mngr.cli.ask import _emit_response
from imbue.mngr.primitives import OutputFormat


def test_ask_cli_options_has_expected_fields() -> None:
    opts = AskCliOptions(
        query=("how", "do", "I", "create", "an", "agent?"),
        execute=False,
        output_format="human",
        quiet=False,
        verbose=0,
        log_file=None,
        log_commands=None,
        log_command_output=None,
        log_env_vars=None,
        project_context_path=None,
        plugin=(),
        disable_plugin=(),
    )
    assert opts.query == ("how", "do", "I", "create", "an", "agent?")
    assert opts.execute is False


def test_query_tuple_joins_correctly() -> None:
    query = ("start", "a", "container")
    assert " ".join(query) == "start a container"


def test_empty_query_joins_to_empty_string() -> None:
    query: tuple[str, ...] = ()
    assert " ".join(query) == ""


def test_single_word_query_joins_correctly() -> None:
    query = ("hello",)
    assert " ".join(query) == "hello"


def test_emit_response_human_format() -> None:
    """Human format uses loguru, so we just verify no exception."""
    _emit_response(response="Use mngr create", output_format=OutputFormat.HUMAN)


def test_emit_response_json_format(capsys: pytest.CaptureFixture) -> None:
    _emit_response(response="Use mngr create", output_format=OutputFormat.JSON)
    captured = capsys.readouterr()
    assert '"response": "Use mngr create"' in captured.out


def test_emit_response_jsonl_format(capsys: pytest.CaptureFixture) -> None:
    _emit_response(response="Use mngr create", output_format=OutputFormat.JSONL)
    captured = capsys.readouterr()
    assert '"event": "response"' in captured.out
    assert '"response": "Use mngr create"' in captured.out


def test_execute_flag_stored_correctly() -> None:
    opts = AskCliOptions(
        query=("test",),
        execute=True,
        output_format="human",
        quiet=False,
        verbose=0,
        log_file=None,
        log_commands=None,
        log_command_output=None,
        log_env_vars=None,
        project_context_path=None,
        plugin=(),
        disable_plugin=(),
    )
    assert opts.execute is True
