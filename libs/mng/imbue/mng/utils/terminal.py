import sys
from collections.abc import Callable
from typing import Any
from typing import Final

ANSI_ERASE_LINE: Final[str] = "\r\x1b[K"
ANSI_DIM: Final[str] = "\x1b[2m"
ANSI_DIM_GRAY: Final[str] = "\x1b[38;5;245m"
ANSI_RESET: Final[str] = "\x1b[0m"


def write_dim_stderr(text: str) -> None:
    """Write dim-formatted text to stderr. No-op if text is empty."""
    if not text:
        return
    is_tty = hasattr(sys.stderr, "isatty") and sys.stderr.isatty()
    if is_tty:
        sys.stderr.write(f"{ANSI_DIM}{text}{ANSI_RESET}\n")
    else:
        sys.stderr.write(f"{text}\n")
    sys.stderr.flush()


class StderrInterceptor:
    """Routes stderr writes through a callback function.

    Designed to be installed as sys.stderr to prevent external writes (e.g.
    loguru warnings) from interleaving with ANSI-managed output. The callback
    receives each non-empty write as a string.

    Falls back to writing directly to the original stderr if the callback
    raises OSError (e.g. broken pipe on the output stream), which avoids
    recursive writes through the interceptor.
    """

    def __init__(self, callback: Callable[[str], None], original_stderr: Any) -> None:
        self._callback = callback
        self._original_stderr = original_stderr

    def write(self, s: str) -> int:
        if s:
            try:
                self._callback(s)
            except OSError:
                self._original_stderr.write(s)
                self._original_stderr.flush()
        return len(s)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return self._original_stderr.isatty()

    def fileno(self) -> int:
        return self._original_stderr.fileno()

    @property
    def encoding(self) -> str:
        return getattr(self._original_stderr, "encoding", "utf-8")

    @property
    def errors(self) -> str:
        return getattr(self._original_stderr, "errors", "strict")
