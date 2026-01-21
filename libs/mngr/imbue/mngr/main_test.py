"""Tests for the main CLI entry point."""

from unittest.mock import patch

import pytest

from imbue.mngr.errors import AgentNotFoundError
from imbue.mngr.errors import MngrError
from imbue.mngr.errors import UserInputError
from imbue.mngr.main import main
from imbue.mngr.primitives import AgentId


def test_main_catches_mngr_error_and_exits_with_code_1(capsys) -> None:
    """main() should catch MngrError and exit with code 1."""
    error = MngrError("Test error message")

    with patch("imbue.mngr.main.cli") as mock_cli:
        mock_cli.side_effect = error
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Error: Test error message" in captured.err


def test_main_displays_error_without_stack_trace(capsys) -> None:
    """main() should display error message without stack trace."""
    error = UserInputError("Invalid input provided")

    with patch("imbue.mngr.main.cli") as mock_cli:
        mock_cli.side_effect = error
        with pytest.raises(SystemExit):
            main()

    captured = capsys.readouterr()
    assert "Error: Invalid input provided" in captured.err
    # Stack trace should not be present
    assert "Traceback" not in captured.err
    assert "raise" not in captured.err


def test_main_displays_user_help_text_when_present(capsys) -> None:
    """main() should display user_help_text when the error has it."""
    agent_id = AgentId.generate()
    error = AgentNotFoundError(agent_id)

    with patch("imbue.mngr.main.cli") as mock_cli:
        mock_cli.side_effect = error
        with pytest.raises(SystemExit):
            main()

    captured = capsys.readouterr()
    assert f"Error: Agent not found: {agent_id}" in captured.err
    assert "mngr list" in captured.err


def test_main_does_not_catch_non_mngr_errors() -> None:
    """main() should let non-MngrError exceptions propagate."""
    error = ValueError("Some other error")

    with patch("imbue.mngr.main.cli") as mock_cli:
        mock_cli.side_effect = error
        with pytest.raises(ValueError) as exc_info:
            main()

    assert str(exc_info.value) == "Some other error"


def test_main_handles_error_without_user_help_text(capsys) -> None:
    """main() should handle errors that don't have user_help_text."""

    class CustomMngrError(MngrError):
        """A custom error without user_help_text."""

    error = CustomMngrError("Custom error")

    with patch("imbue.mngr.main.cli") as mock_cli:
        mock_cli.side_effect = error
        with pytest.raises(SystemExit):
            main()

    captured = capsys.readouterr()
    assert "Error: Custom error" in captured.err
    # Should only have the error line, no help text
    lines = [line for line in captured.err.strip().split("\n") if line]
    assert len(lines) == 1


def test_main_runs_cli_successfully_when_no_error() -> None:
    """main() should run cli() successfully when no error is raised."""
    with patch("imbue.mngr.main.cli") as mock_cli:
        mock_cli.return_value = None
        # Should not raise
        main()

    mock_cli.assert_called_once()
