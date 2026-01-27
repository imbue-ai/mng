from threading import Event


def wait_interval(timeout: float) -> None:
    """Wait for a specified interval using Event.wait instead of time.sleep."""
    Event().wait(timeout=timeout)
