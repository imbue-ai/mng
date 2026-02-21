from io import StringIO
from unittest.mock import patch

from imbue.mng.utils.terminal import ANSI_DIM
from imbue.mng.utils.terminal import ANSI_RESET
from imbue.mng.utils.terminal import StderrInterceptor
from imbue.mng.utils.terminal import write_dim_stderr


class TestStderrInterceptor:
    def test_routes_writes_through_callback(self) -> None:
        captured: list[str] = []
        interceptor = StderrInterceptor(callback=captured.append, original_stderr=StringIO())
        interceptor.write("hello")
        assert captured == ["hello"]

    def test_skips_empty_writes(self) -> None:
        captured: list[str] = []
        interceptor = StderrInterceptor(callback=captured.append, original_stderr=StringIO())
        interceptor.write("")
        assert captured == []

    def test_returns_length_of_input(self) -> None:
        interceptor = StderrInterceptor(callback=lambda s: None, original_stderr=StringIO())
        assert interceptor.write("hello") == 5
        assert interceptor.write("") == 0

    def test_falls_back_to_original_stderr_on_oserror(self) -> None:
        original = StringIO()

        def failing_callback(s: str) -> None:
            raise OSError("broken pipe")

        interceptor = StderrInterceptor(callback=failing_callback, original_stderr=original)
        interceptor.write("fallback text")
        assert "fallback text" in original.getvalue()

    def test_isatty_delegates_to_original(self) -> None:
        original = StringIO()
        interceptor = StderrInterceptor(callback=lambda s: None, original_stderr=original)
        assert interceptor.isatty() is False

    def test_encoding_delegates_to_original(self) -> None:
        """encoding falls back to 'utf-8' when the original has no encoding attribute."""

        class _NoEncoding:
            pass

        interceptor = StderrInterceptor(callback=lambda s: None, original_stderr=_NoEncoding())
        assert interceptor.encoding == "utf-8"

    def test_encoding_reads_from_original(self) -> None:
        """encoding returns the original stderr's encoding when it has one."""

        class _WithEncoding:
            encoding = "ascii"

        interceptor = StderrInterceptor(callback=lambda s: None, original_stderr=_WithEncoding())
        assert interceptor.encoding == "ascii"

    def test_errors_delegates_to_original(self) -> None:
        """errors falls back to 'strict' when the original has no errors attribute."""

        class _NoErrors:
            pass

        interceptor = StderrInterceptor(callback=lambda s: None, original_stderr=_NoErrors())
        assert interceptor.errors == "strict"

    def test_errors_reads_from_original(self) -> None:
        """errors returns the original stderr's errors when it has one."""

        class _WithErrors:
            errors = "replace"

        interceptor = StderrInterceptor(callback=lambda s: None, original_stderr=_WithErrors())
        assert interceptor.errors == "replace"


class TestWriteDimStderr:
    def test_no_op_for_empty_text(self) -> None:
        stderr = StringIO()
        with patch("sys.stderr", stderr):
            write_dim_stderr("")
        assert stderr.getvalue() == ""

    def test_writes_dim_text_on_tty(self) -> None:
        stderr = StringIO()
        stderr.isatty = lambda: True  # type: ignore[assignment]
        with patch("sys.stderr", stderr):
            write_dim_stderr("hello")
        output = stderr.getvalue()
        assert ANSI_DIM in output
        assert ANSI_RESET in output
        assert "hello" in output

    def test_writes_plain_text_on_non_tty(self) -> None:
        stderr = StringIO()
        with patch("sys.stderr", stderr):
            write_dim_stderr("hello")
        output = stderr.getvalue()
        assert "\x1b" not in output
        assert "hello\n" == output
