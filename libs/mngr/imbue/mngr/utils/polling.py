import time
from collections.abc import Callable


def poll_until_counted(
    condition: Callable[[], bool],
    timeout: float = 5.0,
    poll_interval: float = 0.1,
) -> tuple[bool, int, float]:
    """Poll until a condition becomes true or timeout expires.

    Returns (success, poll_count, elapsed_seconds):
    - success: True if the condition was met, False if timeout occurred
    - poll_count: Number of times the condition was checked
    - elapsed_seconds: Total time spent polling
    """
    start_time = time.time()
    poll_count = 0
    elapsed = 0.0
    while elapsed < timeout:
        poll_count += 1
        if condition():
            return True, poll_count, time.time() - start_time
        time.sleep(poll_interval)
        elapsed = time.time() - start_time
    # One final check after timeout in case condition became true during last sleep
    poll_count += 1
    if condition():
        return True, poll_count, time.time() - start_time
    return False, poll_count, time.time() - start_time


def poll_until(
    condition: Callable[[], bool],
    timeout: float = 5.0,
    poll_interval: float = 0.1,
) -> bool:
    """Poll until a condition becomes true or timeout expires.

    Returns True if the condition was met, False if timeout occurred.
    """
    success, _, _ = poll_until_counted(condition, timeout, poll_interval)
    return success


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
