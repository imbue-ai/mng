from typing import assert_never

from loguru import logger

from imbue.mngr.errors import MngrError
from imbue.mngr.primitives import ErrorBehavior


def handle_error_with_behavior(error_msg: str, error_behavior: ErrorBehavior, exc: Exception | None = None) -> None:
    """Handle an error according to the specified error behavior.

    If ABORT, re-raises the exception (or raises MngrError). If CONTINUE, logs
    the error and returns.
    """
    match error_behavior:
        case ErrorBehavior.ABORT:
            if exc:
                raise exc
            raise MngrError(error_msg)
        case ErrorBehavior.CONTINUE:
            if exc:
                logger.exception(exc)
            else:
                logger.error(error_msg)
        case _ as unreachable:
            assert_never(unreachable)
