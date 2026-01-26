"""Unit tests for the editor module."""

import os
import tempfile
from pathlib import Path

import pytest

from imbue.mngr.errors import UserInputError
from imbue.mngr.utils.editor import EditorSession
from imbue.mngr.utils.editor import get_editor_command
from imbue.mngr.utils.testing import restore_env_var


class TestGetEditorCommand:
    """Tests for get_editor_command()."""

    def test_uses_visual_env_var_first(self) -> None:
        """Test that $VISUAL is preferred over $EDITOR."""
        original_visual = os.environ.get("VISUAL")
        original_editor = os.environ.get("EDITOR")
        try:
            os.environ["VISUAL"] = "code"
            os.environ["EDITOR"] = "vim"
            assert get_editor_command() == "code"
        finally:
            restore_env_var("VISUAL", original_visual)
            restore_env_var("EDITOR", original_editor)

    def test_uses_editor_when_visual_not_set(self) -> None:
        """Test that $EDITOR is used when $VISUAL is not set."""
        original_visual = os.environ.get("VISUAL")
        original_editor = os.environ.get("EDITOR")
        try:
            os.environ.pop("VISUAL", None)
            os.environ["EDITOR"] = "nano"
            assert get_editor_command() == "nano"
        finally:
            restore_env_var("VISUAL", original_visual)
            restore_env_var("EDITOR", original_editor)

    def test_falls_back_to_default_when_no_env_vars(self) -> None:
        """Test that a fallback editor is used when env vars are not set."""
        original_visual = os.environ.get("VISUAL")
        original_editor = os.environ.get("EDITOR")
        try:
            os.environ.pop("VISUAL", None)
            os.environ.pop("EDITOR", None)
            result = get_editor_command()
            # Should find one of the fallback editors or return vim as last resort
            assert result in ("vim", "vi", "nano", "notepad")
        finally:
            restore_env_var("VISUAL", original_visual)
            restore_env_var("EDITOR", original_editor)


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
        original_editor = os.environ.get("EDITOR")
        try:
            # Use sleep so the process doesn't exit immediately
            os.environ["EDITOR"] = "sleep"
            session = EditorSession.create(initial_content="1")
            try:
                session.start()
                with pytest.raises(UserInputError, match="already started"):
                    session.start()
            finally:
                session.cleanup()
        finally:
            restore_env_var("EDITOR", original_editor)

    def test_is_running_returns_false_before_start(self) -> None:
        """Test that is_running() returns False before session is started."""
        session = EditorSession.create()
        try:
            assert session.is_running() is False
        finally:
            session.cleanup()

    def test_is_running_returns_true_when_process_running(self) -> None:
        """Test that is_running() returns True when process is running."""
        original_editor = os.environ.get("EDITOR")
        try:
            # Use sleep so the process stays running
            os.environ["EDITOR"] = "sleep"
            session = EditorSession.create(initial_content="5")
            try:
                session.start()
                assert session.is_running() is True
            finally:
                session.cleanup()
        finally:
            restore_env_var("EDITOR", original_editor)

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
        original_editor = os.environ.get("EDITOR")
        try:
            # Use 'true' which exits immediately with code 0
            os.environ["EDITOR"] = "true"
            session = EditorSession.create()
            try:
                # Write content to temp file before starting
                # (simulates what the user would do in the editor)
                session.temp_file_path.write_text("Edited content")
                session.start()
                result = session.wait_for_result()
                assert result == "Edited content"
            finally:
                session.cleanup()
        finally:
            restore_env_var("EDITOR", original_editor)

    def test_wait_for_result_returns_none_on_non_zero_exit(self) -> None:
        """Test that wait_for_result() returns None when editor exits with error."""
        original_editor = os.environ.get("EDITOR")
        try:
            # Use 'false' which exits with code 1
            os.environ["EDITOR"] = "false"
            session = EditorSession.create()
            try:
                session.start()
                result = session.wait_for_result()
                assert result is None
            finally:
                session.cleanup()
        finally:
            restore_env_var("EDITOR", original_editor)

    def test_wait_for_result_returns_none_on_empty_content(self) -> None:
        """Test that wait_for_result() returns None when content is empty."""
        original_editor = os.environ.get("EDITOR")
        try:
            # Use 'true' which exits with code 0 but doesn't modify the file
            os.environ["EDITOR"] = "true"
            session = EditorSession.create()
            try:
                # File is empty by default after create
                session.start()
                result = session.wait_for_result()
                assert result is None
            finally:
                session.cleanup()
        finally:
            restore_env_var("EDITOR", original_editor)

    def test_wait_for_result_strips_trailing_whitespace(self) -> None:
        """Test that wait_for_result() strips trailing whitespace."""
        original_editor = os.environ.get("EDITOR")
        try:
            # Use 'true' which exits with code 0 but doesn't modify the file
            os.environ["EDITOR"] = "true"
            session = EditorSession.create()
            try:
                # Write content with trailing whitespace
                session.temp_file_path.write_text("Content with whitespace  \n\n")
                session.start()
                result = session.wait_for_result()
                assert result == "Content with whitespace"
            finally:
                session.cleanup()
        finally:
            restore_env_var("EDITOR", original_editor)

    def test_cleanup_removes_temp_file(self) -> None:
        """Test that cleanup() removes the temp file."""
        session = EditorSession.create()
        temp_path = session.temp_file_path
        assert temp_path.exists()

        session.cleanup()

        assert not temp_path.exists()

    def test_cleanup_terminates_running_process(self) -> None:
        """Test that cleanup() terminates a running editor process."""
        original_editor = os.environ.get("EDITOR")
        try:
            # Use sleep so the process stays running
            os.environ["EDITOR"] = "sleep"
            session = EditorSession.create(initial_content="100")
            try:
                session.start()
                # Verify process is running
                assert session.is_running() is True
                # Cleanup should terminate it
                session.cleanup()
                # Process should no longer be running
                assert session.is_running() is False
            finally:
                # Cleanup already done, but make sure temp file is gone
                if session.temp_file_path.exists():
                    session.temp_file_path.unlink()
        finally:
            restore_env_var("EDITOR", original_editor)

    def test_cleanup_handles_stubborn_process(self) -> None:
        """Test that cleanup() can handle a process that requires killing."""
        # Create a script that ignores SIGTERM
        script_content = """#!/bin/bash
trap "" SIGTERM
sleep 100
"""
        original_editor = os.environ.get("EDITOR")
        script_path: str | None = None
        try:
            # Create temp script file
            with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
                f.write(script_content)
                script_path = f.name
            Path(script_path).chmod(0o755)

            os.environ["EDITOR"] = script_path
            session = EditorSession.create()
            try:
                session.start()
                # Verify process is running
                assert session.is_running() is True
                # Cleanup should kill it after terminate fails
                session.cleanup()
                # Process should no longer be running (was killed)
                assert session.is_running() is False
            finally:
                if session.temp_file_path.exists():
                    session.temp_file_path.unlink()
        finally:
            restore_env_var("EDITOR", original_editor)
            if script_path is not None:
                Path(script_path).unlink(missing_ok=True)

    def test_is_finished_returns_false_before_wait(self) -> None:
        """Test that is_finished() returns False before waiting for result."""
        original_editor = os.environ.get("EDITOR")
        try:
            os.environ["EDITOR"] = "true"
            session = EditorSession.create()
            try:
                session.start()
                # Process might have finished but we haven't called wait_for_result yet
                assert session.is_finished() is False
            finally:
                session.cleanup()
        finally:
            restore_env_var("EDITOR", original_editor)

    def test_is_finished_returns_true_after_wait(self) -> None:
        """Test that is_finished() returns True after waiting for result."""
        original_editor = os.environ.get("EDITOR")
        try:
            os.environ["EDITOR"] = "true"
            session = EditorSession.create()
            try:
                session.start()
                session.wait_for_result()
                assert session.is_finished() is True
            finally:
                session.cleanup()
        finally:
            restore_env_var("EDITOR", original_editor)
