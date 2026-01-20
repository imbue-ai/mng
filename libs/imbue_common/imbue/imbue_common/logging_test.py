"""Tests for logging module."""

from imbue.imbue_common.logging import setup_logging


def test_setup_logging_does_not_raise() -> None:
    """setup_logging should configure logging without raising."""
    setup_logging()


def test_setup_logging_with_custom_level() -> None:
    """setup_logging should accept custom log levels."""
    setup_logging(level="DEBUG")
    setup_logging(level="info")
