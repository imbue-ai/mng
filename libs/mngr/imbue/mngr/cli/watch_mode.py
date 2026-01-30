"""Utility for running commands in watch mode (periodic refresh)."""

import time
from collections.abc import Callable

from loguru import logger

from imbue.mngr.errors import MngrError


def run_watch_loop(
    iteration_fn: Callable[[], None],
    interval_seconds: int,
    *,
    on_error_continue: bool = True,
) -> None:
    """Run a function repeatedly at a specified interval.

    This is used for watch mode in CLI commands like `mngr list --watch` and
    `mngr gc --watch`.

    Args:
        iteration_fn: The function to run each iteration. Should raise MngrError
            for recoverable errors (which will be logged and skipped if
            on_error_continue is True).
        interval_seconds: Number of seconds to wait between iterations.
        on_error_continue: If True, MngrError exceptions are logged but the loop
            continues. If False, MngrError will propagate and stop the loop.

    Raises:
        KeyboardInterrupt: Not caught, stops the loop cleanly.
        MngrError: Re-raised if on_error_continue is False.
        Exception: Other exceptions are re-raised immediately.
    """
    logger.info("Starting watch mode: refreshing every {} seconds", interval_seconds)
    logger.info("Press Ctrl+C to stop")

    while True:
        try:
            iteration_fn()
        except MngrError as e:
            if on_error_continue:
                logger.error("Error in iteration (continuing): {}", e)
            else:
                raise

        logger.info("\nWaiting {} seconds until next refresh...", interval_seconds)
        time.sleep(interval_seconds)
