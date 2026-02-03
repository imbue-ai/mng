import time
from collections.abc import Callable


def poll_until(
    condition: Callable[[], bool],
    timeout: float = 5.0,
    poll_interval: float = 0.1,
) -> bool:
    """Poll until a condition becomes true or timeout expires.

    Returns True if the condition was met, False if timeout occurred.
    """
    start_time = time.time()
    elapsed_time = 0.0
    while elapsed_time < timeout:
        if condition():
            return True
        time.sleep(poll_interval)
        elapsed_time = time.time() - start_time
    return False


def wait_for(
    condition: Callable[[], bool],
    timeout: float = 5.0,
    poll_interval: float = 0.1,
    error_message: str = "Condition not met within timeout",
) -> None:
    """Wait for a condition to become true, polling at regular intervals.

    This is a general-purpose polling utility for production code.
    Raises TimeoutError if the condition is not met within the timeout period.
    """
    if not poll_until(condition, timeout, poll_interval):
        raise TimeoutError(error_message)
