import contextlib
import sys
from io import StringIO
from typing import Any
from typing import Generator
from typing import Sequence
from typing import TextIO
from typing import cast

import modal
from loguru import logger
from modal._output import OutputManager


def _write_to_multiple_files(
    files: Sequence[Any],
    text: str,
) -> int:
    """Write text to multiple file-like objects and return the length."""
    for file in files:
        file.write(text)
        file.flush()
    return len(text)


class _DeduplicatingWriter(StringIO):
    """StringIO buffer that deduplicates consecutive identical messages.

    This is useful for Modal output which often repeats the same status messages.
    """

    _last_message: str = ""

    def write(self, text: str) -> int:  # ty: ignore[invalid-method-override]
        """Write text to the buffer, skipping consecutive duplicates."""
        stripped = text.strip()
        if stripped == self._last_message or stripped == "":
            return len(text)
        self._last_message = stripped
        return super().write(text)


def _create_deduplicating_writer() -> _DeduplicatingWriter:
    """Create a new deduplicating writer instance."""
    writer = _DeduplicatingWriter()
    writer._last_message = ""
    return writer


class _MultiWriter:
    """File-like object that writes to multiple destinations.

    This is used to tee Modal output to multiple destinations (e.g., a buffer
    for programmatic inspection and loguru for logging).
    """

    _files: Sequence[Any] = ()

    def write(self, text: str) -> int:
        """Write text to all configured file-like objects."""
        return _write_to_multiple_files(self._files, text)

    def flush(self) -> None:
        """Flush all file-like objects."""
        for file in self._files:
            file.flush()

    def isatty(self) -> bool:
        """Report as not a tty to disable interactive features."""
        return False

    def __enter__(self) -> "_MultiWriter":
        """Enter context."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Exit context."""
        pass


def _create_multi_writer(files: Sequence[Any]) -> _MultiWriter:
    """Create a new multi-writer that writes to all provided files."""
    writer = _MultiWriter()
    writer._files = files
    return writer


class _ModalLoguruWriter:
    """Writer that sends Modal output to loguru with structured metadata.

    Supports setting app_id and app_name for structured logging.
    """

    _last_message: str = ""
    app_id: str | None = None
    app_name: str | None = None

    def write(self, text: str) -> int:
        """Write text to loguru, deduplicating consecutive identical messages."""
        stripped = text.strip()
        if stripped == self._last_message or stripped == "":
            return len(text)
        self._last_message = stripped
        extra = {
            "source": "modal",
            "app_id": self.app_id,
            "app_name": self.app_name,
        }
        logger.bind(**extra).debug("{}", stripped)
        return len(text)

    def flush(self) -> None:
        """Flush is a no-op for loguru."""
        pass

    def writable(self) -> bool:
        """Report as writable."""
        return True

    def readable(self) -> bool:
        """Report as not readable."""
        return False

    def seekable(self) -> bool:
        """Report as not seekable."""
        return False


def _create_modal_loguru_writer() -> _ModalLoguruWriter:
    """Create a new Modal loguru writer instance."""
    writer = _ModalLoguruWriter()
    writer._last_message = ""
    writer.app_id = None
    writer.app_name = None
    return writer


class _QuietOutputManager(OutputManager):
    """Modal OutputManager that suppresses interactive spinners and status updates.

    Modal's default OutputManager displays spinners and progress bars which don't
    work well when capturing output programmatically. This subclass disables those
    features while preserving the ability to capture log output.
    """

    @contextlib.contextmanager
    def show_status_spinner(self) -> Generator[None, None, None]:
        """Suppress the status spinner."""
        yield

    def update_app_page_url(self, app_page_url: str) -> None:
        """Log the app page URL instead of displaying it."""
        logger.debug("Modal app page: {}", app_page_url)
        self._app_page_url = app_page_url

    def update_task_state(self, task_id: str, state: int) -> None:
        """Suppress task state updates."""
        pass


class _TeeWriter:
    """File-like object that tees writes to both the original stream and a capture writer.

    This allows us to capture Modal output for logging while still displaying it
    to the user on the terminal. Modal writes build logs directly to sys.stdout/stderr,
    so we need to intercept at that level rather than through the OutputManager.
    """

    _original: TextIO
    _capture_writer: Any

    def write(self, text: str) -> int:
        """Write to both the original stream and the capture writer."""
        # Always write to original so user sees output
        self._original.write(text)
        # Also write to capture writer for logging
        self._capture_writer.write(text)
        return len(text)

    def flush(self) -> None:
        """Flush both streams."""
        self._original.flush()
        self._capture_writer.flush()

    def isatty(self) -> bool:
        """Delegate isatty to original stream."""
        return self._original.isatty()

    def fileno(self) -> int:
        """Delegate fileno to original stream."""
        return self._original.fileno()

    @property
    def encoding(self) -> str:
        """Delegate encoding to original stream."""
        return self._original.encoding

    @property
    def errors(self) -> str | None:
        """Delegate errors to original stream."""
        return self._original.errors


def _create_tee_writer(original: TextIO, capture_writer: Any) -> _TeeWriter:
    """Create a tee writer that writes to both the original stream and capture writer."""
    writer = _TeeWriter()
    writer._original = original
    writer._capture_writer = capture_writer
    return writer


@contextlib.contextmanager
def enable_modal_output_capture(
    is_logging_to_loguru: bool = True,
) -> Generator[tuple[StringIO, _ModalLoguruWriter | None], None, None]:
    """Context manager for capturing Modal app output.

    Intercepts Modal's output system and routes it to a StringIO buffer (for
    programmatic inspection) and optionally to loguru (for mngr's logging).
    The buffer can be used to detect build failures by inspecting the captured
    output after operations complete.

    Modal writes build logs directly to sys.stdout/stderr, so we intercept at
    that level using tee-style writers that write to both the original stream
    (so users see output) and to our capture mechanism (for logging).

    Set is_logging_to_loguru=False to disable routing to loguru.

    Yields a tuple of (output_buffer, loguru_writer) where loguru_writer contains
    app_id and app_name fields that can be set for structured logging, or is
    None if is_logging_to_loguru is False.
    """
    output_buffer = _create_deduplicating_writer()
    loguru_writer: _ModalLoguruWriter | None = (
        _create_modal_loguru_writer() if is_logging_to_loguru else None
    )

    # Build list of writers to tee output to
    writers: list[Any] = [output_buffer]
    if loguru_writer is not None:
        writers.append(loguru_writer)

    multi_writer = _create_multi_writer(writers)

    logger.debug("Enabling Modal output capture")

    # Save original stdout/stderr so we can restore them later
    original_stdout = sys.stdout
    original_stderr = sys.stderr

    # Create tee writers that write to both original streams and our capture mechanism
    tee_stdout = _create_tee_writer(original_stdout, multi_writer)
    tee_stderr = _create_tee_writer(original_stderr, multi_writer)

    with modal.enable_output(show_progress=True):
        OutputManager._instance = _QuietOutputManager(status_spinner_text="Running...")
        OutputManager._instance._stdout = multi_writer

        # Intercept sys.stdout and sys.stderr to capture Modal build output.
        # Modal writes build logs directly to these streams, not through OutputManager.
        sys.stdout = cast(TextIO, tee_stdout)
        sys.stderr = cast(TextIO, tee_stderr)

        try:
            yield output_buffer, loguru_writer
        finally:
            # Restore original stdout/stderr
            sys.stdout = original_stdout
            sys.stderr = original_stderr
