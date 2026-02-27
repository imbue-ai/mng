import math
import re
import sys
from collections.abc import Callable
from types import TracebackType
from typing import Any
from typing import Final
from typing import Self

from imbue.imbue_common.mutable_model import MutableModel
from imbue.imbue_common.pure import pure

ANSI_ERASE_LINE: Final[str] = "\r\x1b[K"
ANSI_ERASE_TO_END: Final[str] = "\x1b[J"
ANSI_DIM_GRAY: Final[str] = "\x1b[38;5;245m"
ANSI_RESET: Final[str] = "\x1b[0m"


def ansi_cursor_up(lines: int) -> str:
    """ANSI escape sequence to move the cursor up by the given number of lines."""
    return f"\x1b[{lines}A"


_ANSI_ESCAPE_PATTERN: Final[re.Pattern[str]] = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\r")


@pure
def count_visual_lines(text: str, terminal_width: int) -> int:
    """Count the number of visual terminal lines a text string occupies.

    Accounts for both explicit newlines and line wrapping at the terminal width.
    ANSI escape sequences are stripped before measuring visible length.
    """
    if not text:
        return 0

    if terminal_width <= 0:
        return text.count("\n")

    segments = text.split("\n")
    count = 0
    for segment in segments:
        visible_len = len(_ANSI_ESCAPE_PATTERN.sub("", segment))
        if visible_len == 0:
            count += 1
        else:
            count += math.ceil(visible_len / terminal_width)

    # The trailing empty segment from a final \n represents the cursor
    # position at the start of the next line, not an additional visual line
    if text.endswith("\n"):
        count -= 1

    return max(count, 0)


@pure
def hard_wrap_for_terminal(text: str, terminal_width: int) -> str:
    """Insert explicit newlines so no visual line exceeds terminal_width.

    ANSI escape sequences are passed through without affecting the column
    count. Because every wrap point is an explicit newline, the physical
    line count (text.count('\\n')) is immune to terminal re-wrapping when
    the terminal gets wider -- lines with explicit newlines never merge.
    """
    if terminal_width <= 0:
        return text

    result: list[str] = []
    visible_col = 0
    idx = 0
    while idx < len(text):
        char = text[idx]

        if char == "\n":
            result.append("\n")
            visible_col = 0
            idx += 1
        elif char == "\r":
            result.append("\r")
            visible_col = 0
            idx += 1
        elif char == "\x1b":
            # ANSI escape sequence -- pass through without advancing the column
            match = _ANSI_ESCAPE_PATTERN.match(text, idx)
            if match:
                result.append(match.group())
                idx = match.end()
            else:
                result.append(char)
                idx += 1
        else:
            if visible_col >= terminal_width:
                result.append("\n")
                visible_col = 0
            else:
                pass
            result.append(char)
            visible_col += 1
            idx += 1

    return "".join(result)


class StderrInterceptor(MutableModel):
    """Routes stderr writes through a callback function.

    Designed to be installed as sys.stderr to prevent external writes (e.g.
    loguru warnings) from interleaving with ANSI-managed output. The callback
    receives each non-empty write as a string.

    Use as a context manager to automatically install/restore sys.stderr.

    Falls back to writing directly to the original stderr if the callback
    raises OSError (e.g. broken pipe on the output stream), which avoids
    recursive writes through the interceptor.
    """

    model_config = {"arbitrary_types_allowed": True}

    callback: Callable[[str], None]
    original_stderr: Any

    def write(self, s: str, /) -> int:
        if s:
            try:
                self.callback(s)
            except OSError:
                self.original_stderr.write(s)
                self.original_stderr.flush()
        return len(s)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return self.original_stderr.isatty()

    def fileno(self) -> int:
        return self.original_stderr.fileno()

    def __enter__(self) -> Self:
        sys.stderr = self
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        sys.stderr = self.original_stderr

    @property
    def encoding(self) -> str:
        return getattr(self.original_stderr, "encoding", "utf-8")

    @property
    def errors(self) -> str:
        return getattr(self.original_stderr, "errors", "strict")
