import contextlib
from io import StringIO
from typing import Any
from typing import Generator
from typing import Sequence

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

    Modal's default OutputManager displays spinners, progress bars, and completion
    messages which don't work well when capturing output programmatically. This
    subclass disables those features while logging to loguru at debug level.
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

    def print(self, renderable) -> None:  # ty: ignore[invalid-method-override]
        """Log print messages to loguru instead of console."""
        if renderable is None:
            return
        # Modal passes Rich objects (like Tree) as well as strings
        # Convert to string for logging
        message_str = str(renderable).strip() if hasattr(renderable, "__str__") else ""
        if message_str:
            logger.debug("Modal: {}", message_str)

    @contextlib.contextmanager
    def step_progress(self, message: str) -> Generator[None, None, None]:
        """Suppress step progress spinner, log to debug."""
        logger.debug("Modal step: {}", message)
        yield

    def step_completed(self, message: str, is_substep: bool = False) -> str:
        """Log step completion to debug instead of console, return empty string."""
        logger.debug("Modal completed: {}", message)
        # Return empty string since Modal may pass this to print()
        return ""

    def substep_completed(self, message: str) -> str:
        """Log substep completion to debug instead of console, return empty string."""
        logger.debug("Modal substep: {}", message)
        # Return empty string since Modal may pass this to print()
        return ""


@contextlib.contextmanager
def enable_modal_output_capture(
    is_logging_to_loguru: bool = True,
) -> Generator[tuple[StringIO, _ModalLoguruWriter | None], None, None]:
    """Context manager for capturing Modal app output.

    Intercepts Modal's output system and routes it to a StringIO buffer (for
    programmatic inspection) and optionally to loguru (for mngr's logging).
    The buffer can be used to detect build failures by inspecting the captured
    output after operations complete.

    Modal's console output (progress messages like "Initialized", "Created objects",
    etc.) is suppressed by using show_progress=False. These messages are still
    captured and logged at debug level via loguru if is_logging_to_loguru=True.

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

    # Use show_progress=False to suppress console output ("Initialized", "Created
    # objects", etc). Output is still captured and logged to loguru at debug level.
    with modal.enable_output(show_progress=False):
        OutputManager._instance = _QuietOutputManager(status_spinner_text="Running...")
        OutputManager._instance._stdout = multi_writer

        yield output_buffer, loguru_writer
