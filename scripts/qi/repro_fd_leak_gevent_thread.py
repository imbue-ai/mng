"""Bisect: is the leak from gevent.spawn in a thread?

Usage:
    uv run python scripts/qi/repro_fd_leak_gevent_thread.py
"""

import gc
import os
import threading
from pathlib import Path

import gevent


def count_real_fds() -> int:
    count = 0
    for entry in Path("/dev/fd").iterdir():
        try:
            fd = int(entry.name)
            os.fstat(fd)
            count += 1
        except (ValueError, OSError):
            pass
    return count


def noop() -> None:
    pass


def use_gevent_in_thread() -> None:
    """Spawn a gevent greenlet inside a thread."""
    g = gevent.spawn(noop)
    gevent.wait([g])


def main() -> None:
    gc.collect()
    initial = count_real_fds()
    print(f"Initial real FDs: {initial}")

    print("\n--- Test 1: gevent.spawn in a thread ---")
    for i in range(1, 11):
        t = threading.Thread(target=use_gevent_in_thread)
        t.start()
        t.join()
        gc.collect()
        current = count_real_fds()
        print(f"[{i:3d}] real_fds={current} (delta: {current - initial:+d})")

    print("\n--- Test 2: gevent.spawn on main thread ---")
    mid = count_real_fds()
    for i in range(1, 11):
        g = gevent.spawn(noop)
        gevent.wait([g])
        gc.collect()
        current = count_real_fds()
        print(f"[{i:3d}] real_fds={current} (delta: {current - mid:+d})")


if __name__ == "__main__":
    main()
