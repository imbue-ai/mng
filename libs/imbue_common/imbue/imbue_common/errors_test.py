"""Tests for errors module."""

from imbue.imbue_common.errors import SwitchError


def test_switch_error_can_be_raised() -> None:
    """SwitchError should be raisable as an exception."""
    error = SwitchError("unexpected branch")
    assert str(error) == "unexpected branch"
