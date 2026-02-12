"""Unit tests for error handling utilities."""

import pytest

from imbue.mngr.errors import MngrError
from imbue.mngr.primitives import ErrorBehavior
from imbue.mngr.utils.error_handling import handle_error_with_behavior


def test_handle_error_with_behavior_abort_reraises_provided_exception() -> None:
    """handle_error_with_behavior should re-raise the provided exception when ABORT."""
    original_error = MngrError("something went wrong")
    with pytest.raises(MngrError, match="something went wrong"):
        handle_error_with_behavior("error message", ErrorBehavior.ABORT, exc=original_error)


def test_handle_error_with_behavior_abort_raises_mngr_error_when_no_exception() -> None:
    """handle_error_with_behavior should raise MngrError from the message when ABORT with no exc."""
    with pytest.raises(MngrError, match="provider failed"):
        handle_error_with_behavior("provider failed", ErrorBehavior.ABORT, exc=None)


def test_handle_error_with_behavior_continue_does_not_raise_with_exception() -> None:
    """handle_error_with_behavior should log but not raise when CONTINUE with an exception."""
    original_error = MngrError("something went wrong")
    handle_error_with_behavior("error message", ErrorBehavior.CONTINUE, exc=original_error)


def test_handle_error_with_behavior_continue_does_not_raise_without_exception() -> None:
    """handle_error_with_behavior should log but not raise when CONTINUE without an exception."""
    handle_error_with_behavior("error message", ErrorBehavior.CONTINUE, exc=None)
