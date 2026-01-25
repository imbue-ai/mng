from imbue.concurrency_group.event_utils import ShutdownEvent
from imbue.concurrency_group.thread_utils import ObservableThread


def test_shutdown_event_can_be_waited_from_multiple_threads() -> None:
    shutdown_event = ShutdownEvent.build_root()
    child = ShutdownEvent.from_parent(shutdown_event)

    threads = [ObservableThread(target=lambda: child.wait()) for _ in range(4)]
    for thread in threads:
        thread.start()
    shutdown_event.set()
    for thread in threads:
        thread.join()
        thread.maybe_raise()
