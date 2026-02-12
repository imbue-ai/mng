import contextlib
from io import StringIO
from typing import Any
from typing import Generator
from typing import Sequence

import modal
from loguru import logger
from modal._output.manager import DisabledOutputManager
from modal._output.manager import OutputManager

from imbue.imbue_common.logging import log_span
from imbue.mngr.primitives import LogLevel
from imbue.mngr.utils.logging import register_build_level

# Ensure BUILD level is registered (in case this module is imported before logging.py)
register_build_level()


def _write_to_multiple_files(
    files: Sequence[Any],
    text: str,
) -> int:
    """Write text to multiple file-like objects and return the length."""
    for file in files:
        file.write(text)
        file.flush()
    return len(text)


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


class ModalLoguruWriter:
    """Writer that sends Modal output to loguru with structured metadata.

    Supports setting app_id and app_name for structured logging.
    """

    app_id: str | None = None
    app_name: str | None = None

    def write(self, text: str) -> int:
        """Write text to loguru, deduplicating consecutive identical messages."""
        stripped = text.strip()
        if stripped == "":
            return len(text)
        logger.log(LogLevel.BUILD.value, "{}", stripped, source="modal", app_id=self.app_id, app_name=self.app_name)
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


def _create_modal_loguru_writer() -> ModalLoguruWriter:
    """Create a new Modal loguru writer instance."""
    writer = ModalLoguruWriter()
    writer.app_id = None
    writer.app_name = None
    return writer


class _QuietOutputManager(DisabledOutputManager):
    """Modal OutputManager that suppresses interactive spinners, status updates, and duplicate logs.

    Extends DisabledOutputManager (which provides no-op implementations for all abstract
    methods) and overrides only put_log_content to capture build logs, with timestamp-based
    deduplication since Modal sometimes emits the same log line multiple times during
    image builds.
    """

    def __init__(self, stdout: _MultiWriter) -> None:
        self._stdout = stdout
        self._timestamps: set[float] = set()
        self._app_page_url: str | None = None

    async def put_log_content(self, log: Any) -> None:
        """Capture build logs, deduplicating by timestamp."""
        if log.timestamp not in self._timestamps:
            self._timestamps.add(log.timestamp)
            self._stdout.write(log.data)

    def update_app_page_url(self, app_page_url: str) -> None:
        """Log the app page URL instead of displaying it."""
        logger.debug("Modal app page: {}", app_page_url)
        self._app_page_url = app_page_url


@contextlib.contextmanager
def enable_modal_output_capture(
    is_logging_to_loguru: bool = True,
) -> Generator[tuple[StringIO, ModalLoguruWriter | None], None, None]:
    """Context manager for capturing Modal app output.

    Intercepts Modal's output system and routes it to a StringIO buffer for
    programmatic inspection. The buffer can be used to detect build failures
    by inspecting the captured output after operations complete.

    When is_logging_to_loguru is True (default), Modal output is also logged
    to loguru with deduplication to avoid spam from repeated status messages.

    Yields a tuple of (output_buffer, loguru_writer) where loguru_writer contains
    app_id and app_name fields that can be set for structured logging, or is
    None if is_logging_to_loguru is False.
    """
    output_buffer = StringIO()
    loguru_writer: ModalLoguruWriter | None = _create_modal_loguru_writer() if is_logging_to_loguru else None

    # Build list of writers to tee output to
    writers: list[Any] = [output_buffer]
    if loguru_writer is not None:
        writers.append(loguru_writer)

    multi_writer = _create_multi_writer(writers)

    with modal.enable_output():
        with log_span("enabling Modal output capture"):
            output_manager = _QuietOutputManager(stdout=multi_writer)
            OutputManager._set(output_manager)

        yield output_buffer, loguru_writer
