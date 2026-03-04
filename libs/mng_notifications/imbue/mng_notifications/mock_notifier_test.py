"""Concrete mock implementation of Notifier for unit testing."""

from imbue.mng_notifications.notifier import Notifier


class RecordingNotifier(Notifier):
    """Test notifier that records calls instead of sending notifications."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []

    def notify(self, title: str, message: str, execute_command: str | None) -> None:
        self.calls.append((title, message, execute_command))
