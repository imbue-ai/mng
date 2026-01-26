"""Unit tests for the editor module."""

import os
import subprocess
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from imbue.mngr.errors import UserInputError
from imbue.mngr.utils.editor import EditorSession
from imbue.mngr.utils.editor import get_editor_command


class TestGetEditorCommand:
    """Tests for get_editor_command()."""

    def test_uses_visual_env_var_first(self) -> None:
        """Test that $VISUAL is preferred over $EDITOR."""
        with patch.dict(os.environ, {"VISUAL": "code", "EDITOR": "vim"}):
            assert get_editor_command() == "code"

    def test_uses_editor_when_visual_not_set(self) -> None:
        """Test that $EDITOR is used when $VISUAL is not set."""
        with patch.dict(os.environ, {"EDITOR": "nano"}, clear=True):
            # Clear VISUAL
            os.environ.pop("VISUAL", None)
            assert get_editor_command() == "nano"

    def test_falls_back_to_default_when_no_env_vars(self) -> None:
        """Test that a fallback editor is used when env vars are not set."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("VISUAL", None)
            os.environ.pop("EDITOR", None)
            # Mock 'which' to find vim
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                result = get_editor_command()
                # Should find one of the fallback editors
                assert result in ("vim", "vi", "nano", "notepad")


class TestEditorSession:
    """Tests for EditorSession class."""

    def test_create_with_no_initial_content(self) -> None:
        """Test creating a session with no initial content."""
        session = EditorSession.create()
        try:
            assert session.temp_file_path.exists()
            assert session.temp_file_path.read_text() == ""
        finally:
            session.cleanup()

    def test_create_with_initial_content(self) -> None:
        """Test creating a session with initial content."""
        session = EditorSession.create(initial_content="Hello World")
        try:
            assert session.temp_file_path.exists()
            assert session.temp_file_path.read_text() == "Hello World"
        finally:
            session.cleanup()

    def test_start_raises_if_already_started(self) -> None:
        """Test that start() raises if session was already started."""
        session = EditorSession.create()
        try:
            # Mock subprocess to avoid actually starting an editor
            with patch("subprocess.Popen") as mock_popen:
                mock_popen.return_value = MagicMock(pid=12345)
                session.start()

                with pytest.raises(UserInputError, match="already started"):
                    session.start()
        finally:
            session.cleanup()

    def test_is_running_returns_false_before_start(self) -> None:
        """Test that is_running() returns False before session is started."""
        session = EditorSession.create()
        try:
            assert session.is_running() is False
        finally:
            session.cleanup()

    def test_is_running_returns_true_when_process_running(self) -> None:
        """Test that is_running() returns True when process is running."""
        session = EditorSession.create()
        try:
            with patch("subprocess.Popen") as mock_popen:
                mock_process = MagicMock()
                # Process still running (poll returns None)
                mock_process.poll.return_value = None
                mock_popen.return_value = mock_process

                session.start()

                assert session.is_running() is True
        finally:
            session.cleanup()

    def test_wait_for_result_raises_if_not_started(self) -> None:
        """Test that wait_for_result() raises if session not started."""
        session = EditorSession.create()
        try:
            with pytest.raises(UserInputError, match="not started"):
                session.wait_for_result()
        finally:
            session.cleanup()

    def test_wait_for_result_returns_content_on_success(self) -> None:
        """Test that wait_for_result() returns content when editor exits successfully."""
        session = EditorSession.create()
        try:
            # Write some content to the temp file (simulating user edit)
            session.temp_file_path.write_text("Edited content")

            with patch("subprocess.Popen") as mock_popen:
                mock_process = MagicMock()
                # Exit code 0 indicates success
                mock_process.wait.return_value = 0
                mock_popen.return_value = mock_process

                session.start()
                result = session.wait_for_result()

                assert result == "Edited content"
        finally:
            session.cleanup()

    def test_wait_for_result_returns_none_on_non_zero_exit(self) -> None:
        """Test that wait_for_result() returns None when editor exits with error."""
        session = EditorSession.create()
        try:
            with patch("subprocess.Popen") as mock_popen:
                mock_process = MagicMock()
                # Non-zero exit code indicates failure
                mock_process.wait.return_value = 1
                mock_popen.return_value = mock_process

                session.start()
                result = session.wait_for_result()

                assert result is None
        finally:
            session.cleanup()

    def test_wait_for_result_returns_none_on_empty_content(self) -> None:
        """Test that wait_for_result() returns None when content is empty."""
        session = EditorSession.create()
        try:
            # Leave file empty (already is after create)
            with patch("subprocess.Popen") as mock_popen:
                mock_process = MagicMock()
                mock_process.wait.return_value = 0
                mock_popen.return_value = mock_process

                session.start()
                result = session.wait_for_result()

                assert result is None
        finally:
            session.cleanup()

    def test_wait_for_result_strips_trailing_whitespace(self) -> None:
        """Test that wait_for_result() strips trailing whitespace."""
        session = EditorSession.create()
        try:
            session.temp_file_path.write_text("Content with whitespace  \n\n")

            with patch("subprocess.Popen") as mock_popen:
                mock_process = MagicMock()
                mock_process.wait.return_value = 0
                mock_popen.return_value = mock_process

                session.start()
                result = session.wait_for_result()

                assert result == "Content with whitespace"
        finally:
            session.cleanup()

    def test_cleanup_removes_temp_file(self) -> None:
        """Test that cleanup() removes the temp file."""
        session = EditorSession.create()
        temp_path = session.temp_file_path
        assert temp_path.exists()

        session.cleanup()

        assert not temp_path.exists()

    def test_cleanup_terminates_running_process(self) -> None:
        """Test that cleanup() terminates a running editor process."""
        session = EditorSession.create()
        try:
            with patch("subprocess.Popen") as mock_popen:
                mock_process = MagicMock()
                # Process still running (poll returns None)
                mock_process.poll.return_value = None
                mock_process.wait.return_value = 0
                mock_popen.return_value = mock_process

                session.start()
                session.cleanup()

                mock_process.terminate.assert_called_once()
        finally:
            # Cleanup already done, but make sure temp file is gone
            if session.temp_file_path.exists():
                session.temp_file_path.unlink()

    def test_cleanup_handles_timeout_with_kill(self) -> None:
        """Test that cleanup() kills process if terminate times out."""
        session = EditorSession.create()
        try:
            with patch("subprocess.Popen") as mock_popen:
                mock_process = MagicMock()
                # Process still running (poll returns None)
                mock_process.poll.return_value = None
                # First wait (after terminate) times out
                mock_process.wait.side_effect = [subprocess.TimeoutExpired("cmd", 1), 0]
                mock_popen.return_value = mock_process

                session.start()
                session.cleanup()

                mock_process.terminate.assert_called_once()
                mock_process.kill.assert_called_once()
        finally:
            # Cleanup already done, but make sure temp file is gone
            if session.temp_file_path.exists():
                session.temp_file_path.unlink()
