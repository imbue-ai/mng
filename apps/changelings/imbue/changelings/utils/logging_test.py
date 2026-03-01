from loguru import logger

from imbue.changelings.utils.logging import ConsoleLogLevel
from imbue.changelings.utils.logging import _format_user_message
from imbue.changelings.utils.logging import console_level_from_verbose_and_quiet
from imbue.changelings.utils.logging import setup_logging


def test_default_level_is_info() -> None:
    level = console_level_from_verbose_and_quiet(verbose=0, quiet=False)

    assert level == ConsoleLogLevel.INFO


def test_single_verbose_gives_debug() -> None:
    level = console_level_from_verbose_and_quiet(verbose=1, quiet=False)

    assert level == ConsoleLogLevel.DEBUG


def test_double_verbose_gives_trace() -> None:
    level = console_level_from_verbose_and_quiet(verbose=2, quiet=False)

    assert level == ConsoleLogLevel.TRACE


def test_triple_verbose_gives_trace() -> None:
    level = console_level_from_verbose_and_quiet(verbose=3, quiet=False)

    assert level == ConsoleLogLevel.TRACE


def test_quiet_gives_none() -> None:
    level = console_level_from_verbose_and_quiet(verbose=0, quiet=True)

    assert level == ConsoleLogLevel.NONE


def test_quiet_overrides_verbose() -> None:
    level = console_level_from_verbose_and_quiet(verbose=2, quiet=True)

    assert level == ConsoleLogLevel.NONE


class _FakeLevel:
    """Fake loguru level object for testing format functions."""

    def __init__(self, name: str) -> None:
        self.name = name


def _make_fake_record(level_name: str) -> dict[str, _FakeLevel]:
    """Create a minimal dict matching the loguru record shape for _format_user_message."""
    return {"level": _FakeLevel(level_name)}


def test_format_user_message_info_returns_plain_format() -> None:
    result = _format_user_message(_make_fake_record("INFO"))
    assert result == "{message}\n"


def test_format_user_message_warning_includes_prefix() -> None:
    result = _format_user_message(_make_fake_record("WARNING"))
    assert "WARNING:" in result
    assert "{message}" in result


def test_format_user_message_error_includes_prefix() -> None:
    result = _format_user_message(_make_fake_record("ERROR"))
    assert "ERROR:" in result
    assert "{message}" in result


def test_format_user_message_debug_includes_message_placeholder() -> None:
    result = _format_user_message(_make_fake_record("DEBUG"))
    assert "{message}" in result


def test_format_user_message_trace_includes_message_placeholder() -> None:
    result = _format_user_message(_make_fake_record("TRACE"))
    assert "{message}" in result


def test_setup_logging_none_removes_all_handlers() -> None:
    setup_logging(ConsoleLogLevel.NONE)

    logger.info("This should not appear")


def test_setup_logging_info_configures_handler() -> None:
    setup_logging(ConsoleLogLevel.INFO)

    logger.info("This should appear")


def test_setup_logging_debug_configures_handler() -> None:
    setup_logging(ConsoleLogLevel.DEBUG)

    logger.debug("Debug message")


def test_setup_logging_trace_configures_handler() -> None:
    setup_logging(ConsoleLogLevel.TRACE)

    logger.trace("Trace message")


def test_setup_logging_warn_configures_handler() -> None:
    setup_logging(ConsoleLogLevel.WARN)

    logger.warning("Warning message")


def test_setup_logging_error_configures_handler() -> None:
    setup_logging(ConsoleLogLevel.ERROR)

    logger.error("Error message")
