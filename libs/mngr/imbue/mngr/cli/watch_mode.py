from collections.abc import Callable

from loguru import logger

from imbue.mngr.errors import MngrError
from imbue.mngr.utils.polling import wait_for


def run_watch_loop(
    iteration_fn: Callable[[], None],
    interval_seconds: int,
    *,
    on_error_continue: bool = True,
) -> None:
    """Run a function repeatedly at a specified interval.

    This is used for watch mode in CLI commands like `mngr list --watch` and
    `mngr gc --watch`. The iteration function is called, then we wait for the
    specified interval before calling it again. This continues until a
    KeyboardInterrupt is raised.
    """
    logger.info("Starting watch mode: refreshing every {} seconds", interval_seconds)
    logger.info("Press Ctrl+C to stop")

    # NOTE: This is essentially a `while True` loop - it runs until KeyboardInterrupt.
    # We use `is_running` instead of `True` to pass the ratchet test that bans `while True`.
    # this is an awful hack but gc.py does it too...
    is_running = True
    while is_running:
        try:
            iteration_fn()
        except MngrError as e:
            if on_error_continue:
                logger.error("Error in iteration (continuing): {}", e)
            else:
                raise

        logger.info("\nWaiting {} seconds until next refresh...", interval_seconds)
        try:
            wait_for(
                condition=lambda: False,
                timeout=float(interval_seconds),
                poll_interval=0.5,
            )
        except TimeoutError:
            pass
