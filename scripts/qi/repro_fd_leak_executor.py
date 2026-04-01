"""Bisect: is the FD leak from ConcurrencyGroupExecutor thread creation?

Usage:
    uv run python scripts/qi/repro_fd_leak_executor.py
"""

import gc
import os
from pathlib import Path

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.concurrency_group.executor import ConcurrencyGroupExecutor


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


def noop() -> int:
    return 42


def main() -> None:
    gc.collect()
    initial = count_real_fds()
    print(f"Initial real FDs: {initial}")

    cg = ConcurrencyGroup(name="repro")
    with cg:
        for i in range(1, 11):
            with ConcurrencyGroupExecutor(parent_cg=cg, name=f"test_{i}", max_workers=32) as executor:
                future = executor.submit(noop)
            result = future.result()
            gc.collect()
            current = count_real_fds()
            print(f"[{i:3d}] real_fds={current} (delta: {current - initial:+d})")

    gc.collect()
    final = count_real_fds()
    print(f"\nFinal: real_fds={final} (delta: {final - initial:+d})")


if __name__ == "__main__":
    main()
