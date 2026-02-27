from io import StringIO

from imbue.mng.utils.terminal import StderrInterceptor
from imbue.mng.utils.terminal import count_visual_lines


def test_interceptor_routes_writes_through_callback() -> None:
    captured: list[str] = []
    interceptor = StderrInterceptor(callback=captured.append, original_stderr=StringIO())
    interceptor.write("hello")
    assert captured == ["hello"]


def test_interceptor_skips_empty_writes() -> None:
    captured: list[str] = []
    interceptor = StderrInterceptor(callback=captured.append, original_stderr=StringIO())
    interceptor.write("")
    assert captured == []


def test_interceptor_returns_length_of_input() -> None:
    interceptor = StderrInterceptor(callback=lambda s: None, original_stderr=StringIO())
    assert interceptor.write("hello") == 5
    assert interceptor.write("") == 0


class _SimulatedBrokenPipe(OSError):
    """Simulates a broken-pipe error from the underlying stream."""


def test_interceptor_falls_back_to_original_on_oserror() -> None:
    original = StringIO()

    def failing_callback(s: str) -> None:
        raise _SimulatedBrokenPipe("broken pipe")

    interceptor = StderrInterceptor(callback=failing_callback, original_stderr=original)
    interceptor.write("fallback text")
    assert "fallback text" in original.getvalue()


def test_interceptor_isatty_delegates_to_original() -> None:
    original = StringIO()
    interceptor = StderrInterceptor(callback=lambda s: None, original_stderr=original)
    assert interceptor.isatty() is False


def test_interceptor_encoding_fallback() -> None:
    """encoding falls back to 'utf-8' when the original has no encoding attribute."""

    class _NoEncoding:
        pass

    interceptor = StderrInterceptor(callback=lambda s: None, original_stderr=_NoEncoding())
    assert interceptor.encoding == "utf-8"


def test_interceptor_encoding_from_original() -> None:
    """encoding returns the original stderr's encoding when it has one."""

    class _WithEncoding:
        encoding = "ascii"

    interceptor = StderrInterceptor(callback=lambda s: None, original_stderr=_WithEncoding())
    assert interceptor.encoding == "ascii"


def test_interceptor_errors_fallback() -> None:
    """errors falls back to 'strict' when the original has no errors attribute."""

    class _NoErrors:
        pass

    interceptor = StderrInterceptor(callback=lambda s: None, original_stderr=_NoErrors())
    assert interceptor.errors == "strict"


def test_interceptor_errors_from_original() -> None:
    """errors returns the original stderr's errors when it has one."""

    class _WithErrors:
        errors = "replace"

    interceptor = StderrInterceptor(callback=lambda s: None, original_stderr=_WithErrors())
    assert interceptor.errors == "replace"


# =============================================================================
# Tests for count_visual_lines
# =============================================================================


def test_count_visual_lines_short_line() -> None:
    """A short line that fits in the terminal is 1 visual line."""
    assert count_visual_lines("hello\n", terminal_width=80) == 1


def test_count_visual_lines_wrapping_line() -> None:
    """A line longer than terminal width wraps to multiple visual lines."""
    assert count_visual_lines("x" * 150 + "\n", terminal_width=100) == 2


def test_count_visual_lines_exact_width() -> None:
    """A line exactly at terminal width occupies 1 visual line."""
    assert count_visual_lines("x" * 100 + "\n", terminal_width=100) == 1


def test_count_visual_lines_multiple_lines() -> None:
    """Multiple short lines are counted individually."""
    assert count_visual_lines("line1\nline2\n", terminal_width=80) == 2


def test_count_visual_lines_long_and_short_mixed() -> None:
    """Mix of wrapping and non-wrapping lines."""
    text = "x" * 150 + "\nshort\n"
    assert count_visual_lines(text, terminal_width=100) == 3


def test_count_visual_lines_strips_ansi_codes() -> None:
    """ANSI escape codes should not count toward visible length."""
    text = "\x1b[38;5;245m" + "x" * 50 + "\x1b[0m\n"
    assert count_visual_lines(text, terminal_width=100) == 1


def test_count_visual_lines_long_with_ansi_codes() -> None:
    """A visually-long line with ANSI codes should still wrap correctly."""
    text = "\x1b[31m" + "x" * 150 + "\x1b[0m\n"
    assert count_visual_lines(text, terminal_width=100) == 2


def test_count_visual_lines_no_trailing_newline() -> None:
    """Text without a trailing newline."""
    assert count_visual_lines("hello", terminal_width=80) == 1


def test_count_visual_lines_empty_string() -> None:
    assert count_visual_lines("", terminal_width=80) == 0


def test_count_visual_lines_just_newline() -> None:
    assert count_visual_lines("\n", terminal_width=80) == 1
