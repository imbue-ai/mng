from pathlib import Path

import pytest

from imbue.mngr.api.transcript import SessionTranscript
from imbue.mngr.api.transcript import TranscriptResult
from imbue.mngr.cli.transcript import TranscriptCliOptions
from imbue.mngr.cli.transcript import _emit_json_output
from imbue.mngr.cli.transcript import _emit_raw_output


def _make_result(sessions: tuple[SessionTranscript, ...]) -> TranscriptResult:
    return TranscriptResult(agent_name="test-agent", sessions=sessions)


def _make_session(session_id: str, content: str) -> SessionTranscript:
    return SessionTranscript(
        session_id=session_id,
        file_path=Path(f"/path/to/{session_id}.jsonl"),
        content=content,
    )


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


def test_emit_raw_output_writes_single_session_to_stdout(capsys: pytest.CaptureFixture) -> None:
    result = _make_result((_make_session("s1", '{"type":"user"}\n{"type":"assistant"}\n'),))

    _emit_raw_output(result)

    captured = capsys.readouterr()
    assert captured.out == '{"type":"user"}\n{"type":"assistant"}\n'


def test_emit_raw_output_concatenates_multiple_sessions(capsys: pytest.CaptureFixture) -> None:
    result = _make_result(
        (
            _make_session("s1", '{"type":"user","msg":"first"}\n'),
            _make_session("s2", '{"type":"user","msg":"second"}\n'),
        )
    )

    _emit_raw_output(result)

    captured = capsys.readouterr()
    assert captured.out == '{"type":"user","msg":"first"}\n{"type":"user","msg":"second"}\n'


def test_emit_raw_output_adds_trailing_newline_if_missing(capsys: pytest.CaptureFixture) -> None:
    result = _make_result((_make_session("s1", '{"type":"user"}'),))

    _emit_raw_output(result)

    captured = capsys.readouterr()
    assert captured.out == '{"type":"user"}\n'


def test_emit_json_output_includes_all_sessions(capsys: pytest.CaptureFixture) -> None:
    result = _make_result(
        (
            _make_session("s1", '{"type":"user"}\n'),
            _make_session("s2", '{"type":"assistant"}\n'),
        )
    )

    _emit_json_output(result)

    captured = capsys.readouterr()
    assert '"agent_name": "test-agent"' in captured.out
    assert '"session_id": "s1"' in captured.out
    assert '"session_id": "s2"' in captured.out
    assert '"sessions"' in captured.out
