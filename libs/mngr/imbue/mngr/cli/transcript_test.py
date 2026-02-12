from pathlib import Path

import pytest

from imbue.mngr.api.transcript import TranscriptResult
from imbue.mngr.cli.transcript import TranscriptCliOptions
from imbue.mngr.cli.transcript import _emit_json_output
from imbue.mngr.cli.transcript import _emit_raw_output


def test_transcript_cli_options_has_expected_fields() -> None:
    opts = TranscriptCliOptions(
        agent="my-agent",
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
    assert opts.agent == "my-agent"


def test_emit_raw_output_writes_content_to_stdout(capsys: pytest.CaptureFixture) -> None:
    result = TranscriptResult(
        agent_name="test-agent",
        content='{"type":"user"}\n{"type":"assistant"}\n',
        session_file_path=Path("/path/to/session.jsonl"),
    )

    _emit_raw_output(result)

    captured = capsys.readouterr()
    assert captured.out == '{"type":"user"}\n{"type":"assistant"}\n'


def test_emit_raw_output_adds_trailing_newline_if_missing(capsys: pytest.CaptureFixture) -> None:
    result = TranscriptResult(
        agent_name="test-agent",
        content='{"type":"user"}',
        session_file_path=Path("/path/to/session.jsonl"),
    )

    _emit_raw_output(result)

    captured = capsys.readouterr()
    assert captured.out == '{"type":"user"}\n'


def test_emit_json_output_includes_all_fields(capsys: pytest.CaptureFixture) -> None:
    result = TranscriptResult(
        agent_name="test-agent",
        content='{"type":"user"}\n',
        session_file_path=Path("/path/to/session.jsonl"),
    )

    _emit_json_output(result)

    captured = capsys.readouterr()
    assert '"agent_name": "test-agent"' in captured.out
    assert '"session_file_path": "/path/to/session.jsonl"' in captured.out
    assert '"content"' in captured.out
