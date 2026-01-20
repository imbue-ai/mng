"""Utilities for capturing and routing Modal app output.

Modal's output system uses rich console formatting which makes it difficult to capture
logs programmatically. This module provides utilities to intercept Modal's output and
route it to loguru while also capturing it in a buffer for inspection (e.g., to detect
build failures).
"""

import contextlib
from io import StringIO
from types import TracebackType
from typing import Any
from typing import Generator
from typing import Sequence

from loguru import logger
from modal._output import OutputManager


class _MultiWriter(StringIO):
    """Writes to multiple file-like objects simultaneously."""

    def __init__(self, files: Sequence[Any]) -> None:
        super().__init__()
        self._files = files

    def write(self, s: str, /) -> int:  # type: ignore[override]
        for file in self._files:
            file.write(s)
            file.flush()
        return len(s)

    def flush(self) -> None:
        for file in self._files:
            file.flush()

    def close(self) -> None:
        pass

    def isatty(self) -> bool:
        # Return False so rich.Console treats output as non-interactive.
        # This prevents progress bars and other interactive elements.
        return False

    def __enter__(self) -> "_MultiWriter":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()


class _DeduplicatingWriter(StringIO):
    """StringIO that deduplicates consecutive identical lines.

    Modal often logs the same message multiple times in rapid succession.
    This class filters out consecutive duplicates to reduce noise.
    """

    def __init__(self) -> None:
        super().__init__()
        self._last_message = ""

    def write(self, s: str, /) -> int:  # type: ignore[override]
        stripped = s.strip()
        if stripped == self._last_message or stripped == "":
            return len(s)
        self._last_message = stripped
        return super().write(s)


class _ModalLoguruWriter:
    """Routes Modal output to loguru logger with structured metadata.

    This class implements a file-like interface that forwards all writes to
    loguru.debug() with source metadata, allowing Modal logs to be captured
    in mngr's logging system.
    """

    def __init__(self) -> None:
        self._last_message = ""
        self.app_id: str | None = None
        self.app_name: str | None = None

    def write(self, text: str) -> int:
        stripped = text.strip()
        if stripped == self._last_message or stripped == "":
            return len(text)
        self._last_message = stripped
        extra = {
            "source": "modal",
            "app_id": self.app_id,
            "app_name": self.app_name,
        }
        logger.debug("{}", stripped, **extra)
        return len(text)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass

    def readable(self) -> bool:
        return False

    def writable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False


class _QuietOutputManager(OutputManager):
    """Modal OutputManager that suppresses interactive spinners and status updates.

    Modal's default OutputManager displays spinners and progress bars which don't
    work well when capturing output programmatically. This subclass disables those
    features while preserving the ability to capture log output.
    """

    @contextlib.contextmanager
    def show_status_spinner(self) -> Generator[None, None, None]:
        yield

    def update_app_page_url(self, app_page_url: str) -> None:
        logger.debug("Modal app page: {}", app_page_url)
        self._app_page_url = app_page_url

    def update_task_state(self, task_id: str, state: int) -> None:
        pass


@contextlib.contextmanager
def enable_modal_output_capture(
    is_logging_to_loguru: bool = True,
) -> Generator[tuple[StringIO, _ModalLoguruWriter | None], None, None]:
    """Context manager for capturing Modal app output.

    This context manager intercepts Modal's output system and routes it to:
    1. A StringIO buffer (always) - for programmatic inspection of logs
    2. Loguru (optional) - for integration with mngr's logging system

    The StringIO buffer can be used to detect build failures or other issues
    by inspecting the captured output after operations complete.

    Args:
        is_logging_to_loguru: If True, also logs Modal output to loguru at DEBUG level

    Yields:
        A tuple of (output_buffer, loguru_writer):
        - output_buffer: StringIO containing all Modal output
        - loguru_writer: The loguru writer (or None if not logging to loguru)
                        Can be used to set app_id and app_name for structured logging

    Example:
        with enable_modal_output_capture() as (output_buffer, loguru_writer):
            if loguru_writer:
                loguru_writer.app_id = app.app_id
                loguru_writer.app_name = app.name
            # ... perform modal operations ...
            if "error" in output_buffer.getvalue().lower():
                logger.warning("Potential error in Modal output")
    """
    output_buffer = _DeduplicatingWriter()

    writers: list[Any] = [output_buffer]
    loguru_writer: _ModalLoguruWriter | None = None

    if is_logging_to_loguru:
        loguru_writer = _ModalLoguruWriter()
        writers.append(loguru_writer)

    logger.debug("Enabling Modal output capture")

    with _MultiWriter(writers) as multi_writer:
        with contextlib.suppress(Exception):
            import modal

            with modal.enable_output(show_progress=True):
                # Monkeypatch the OutputManager to use our quiet version
                OutputManager._instance = _QuietOutputManager(status_spinner_text="Running...")
                OutputManager._instance._stdout = multi_writer

                yield output_buffer, loguru_writer
                return

        # Fallback if modal.enable_output fails
        yield output_buffer, loguru_writer
