import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from typing import Final

import deal
from loguru import logger

from imbue.mngr.errors import UserInputError


FALLBACK_EDITORS: Final[tuple[str, ...]] = ("vim", "vi", "nano", "notepad")


@deal.has()
def get_editor_command() -> str:
    """Get the editor command from environment variables or use a fallback.

    Checks $VISUAL first (for full-screen editors), then $EDITOR,
    then falls back to common editors.
    """
    # Check VISUAL first (preferred for interactive editors)
    editor = os.environ.get("VISUAL")
    if editor:
        return editor

    # Check EDITOR next
    editor = os.environ.get("EDITOR")
    if editor:
        return editor

    # Try to find a fallback editor
    for fallback in FALLBACK_EDITORS:
        # Check if the editor is available in PATH
        result = subprocess.run(
            ["which", fallback],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return fallback

    # Last resort: just try vim
    return "vim"


class EditorSession:
    """Manages an interactive editor session for message editing.

    The editor runs in a subprocess while allowing other work to continue.
    The result is retrieved when wait_for_result() is called.

    Use the create() factory method to instantiate.
    """

    # Class attributes with type hints (not instance attributes)
    temp_file_path: Path
    editor_command: str
    _process: subprocess.Popen[Any] | None
    _is_started: bool
    _is_finished: bool
    _result_content: str | None
    _exit_code: int | None

    @classmethod
    def create(cls, initial_content: str | None = None) -> "EditorSession":
        """Create a new editor session with optional initial content."""
        # Create a temp file with the initial content
        temp_fd, temp_path = tempfile.mkstemp(suffix=".txt", prefix="mngr-message-")
        temp_file_path = Path(temp_path)

        if initial_content:
            temp_file_path.write_text(initial_content)
        else:
            # Write empty file
            temp_file_path.write_text("")

        # Close the file descriptor (we'll access via path)
        os.close(temp_fd)

        editor_command = get_editor_command()
        logger.debug("Using editor: {}", editor_command)

        # Create instance using object.__new__ and set attributes directly
        instance = object.__new__(cls)
        instance.temp_file_path = temp_file_path
        instance.editor_command = editor_command
        instance._process = None
        instance._is_started = False
        instance._is_finished = False
        instance._result_content = None
        instance._exit_code = None
        return instance

    def start(self) -> None:
        """Start the editor subprocess.

        The editor process inherits stdin/stdout/stderr from the parent,
        giving it full terminal access.
        """
        if self._is_started:
            raise UserInputError("Editor session already started")

        logger.debug("Starting editor {} with file {}", self.editor_command, self.temp_file_path)

        # Start the editor process
        # The editor inherits the terminal (stdin/stdout/stderr) from parent
        self._process = subprocess.Popen(
            [self.editor_command, str(self.temp_file_path)],
            stdin=None,
            stdout=None,
            stderr=None,
        )
        self._is_started = True
        logger.trace("Editor process started with PID {}", self._process.pid)

    def is_running(self) -> bool:
        """Check if the editor process is still running."""
        if not self._is_started or self._process is None:
            return False
        if self._is_finished:
            return False
        # Poll to check if process has finished
        return self._process.poll() is None

    def wait_for_result(self, timeout_seconds: float | None = None) -> str | None:
        """Wait for the editor to finish and return the edited content.

        Returns the content of the edited file, or None if:
        - The editor exited with a non-zero code
        - The file was empty after editing
        """
        if not self._is_started or self._process is None:
            raise UserInputError("Editor session not started")

        if self._is_finished:
            return self._result_content

        logger.debug("Waiting for editor to finish...")

        # Wait for the editor process to complete
        try:
            self._exit_code = self._process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            logger.warning("Editor timeout expired, terminating")
            self._process.terminate()
            self._process.wait()
            self._exit_code = -1

        self._is_finished = True
        logger.trace("Editor exited with code {}", self._exit_code)

        # Check exit code
        if self._exit_code != 0:
            logger.warning("Editor exited with non-zero code: {}", self._exit_code)
            return None

        # Read the edited content
        if not self.temp_file_path.exists():
            logger.debug("Editor temp file no longer exists")
            return None

        content = self.temp_file_path.read_text()

        # Strip trailing whitespace but preserve intentional content
        self._result_content = content.rstrip()

        if not self._result_content:
            logger.debug("Editor content is empty")
            return None

        logger.trace("Read {} characters from edited file", len(self._result_content))
        return self._result_content

    def cleanup(self) -> None:
        """Clean up the temporary file and terminate the editor process if running.

        Should be called when done with the session, regardless of outcome.
        """
        # Terminate the editor process if it's still running
        if self._process is not None and self._process.poll() is None:
            logger.debug("Terminating editor process")
            self._process.terminate()
            try:
                self._process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                logger.warning("Editor process did not terminate gracefully, killing")
                self._process.kill()
                self._process.wait()

        # Clean up the temp file
        if self.temp_file_path.exists():
            logger.trace("Cleaning up temp file {}", self.temp_file_path)
            self.temp_file_path.unlink()
