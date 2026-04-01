"""Repro script: use lsof and thread counts to investigate FD leak.

Usage:
    uv run python scripts/qi/repro_fd_leak_lsof.py
"""

import errno
import os
import threading
from pathlib import Path

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mngr.api.list import list_agents
from imbue.mngr.config.loader import load_config
from imbue.mngr.main import create_plugin_manager
from imbue.mngr.primitives import ErrorBehavior


def count_open_fds() -> int:
    return len(list(Path("/dev/fd").iterdir()))


def get_fd_numbers() -> set[int]:
    fds: set[int] = set()
    for entry in Path("/dev/fd").iterdir():
        try:
            fds.add(int(entry.name))
        except ValueError:
            pass
    return fds


def classify_fds(fds: set[int]) -> dict[str, list[int]]:
    """Classify FDs by what fstat returns, including EBADF."""
    import stat

    classes: dict[str, list[int]] = {}
    for fd in sorted(fds):
        try:
            st = os.fstat(fd)
            if stat.S_ISFIFO(st.st_mode):
                kind = "pipe"
            elif stat.S_ISSOCK(st.st_mode):
                kind = "socket"
            elif stat.S_ISREG(st.st_mode):
                kind = "file"
            elif stat.S_ISCHR(st.st_mode):
                kind = "char_device"
            else:
                kind = f"other(mode={oct(st.st_mode)})"
        except OSError as e:
            if e.errno == errno.EBADF:
                kind = "EBADF"
            else:
                kind = f"OSError({e.errno})"
        classes.setdefault(kind, []).append(fd)
    return classes


def main() -> None:
    pid = os.getpid()
    cg = ConcurrencyGroup(name="repro")
    with cg:
        pm = create_plugin_manager()
        mngr_ctx = load_config(pm, cg)

        baseline_fds = get_fd_numbers()
        print(f"PID: {pid}")
        print(f"Initial FDs: {len(baseline_fds)}")
        print(f"Initial threads: {threading.active_count()}")
        print(f"Initial FD classes: {classify_fds(baseline_fds)}")
        print()

        for i in range(1, 6):
            list_agents(
                mngr_ctx=mngr_ctx,
                is_streaming=False,
                error_behavior=ErrorBehavior.CONTINUE,
                provider_names=("local",),
            )

            current_fds = get_fd_numbers()
            new_fds = current_fds - baseline_fds
            print(f"--- Iteration {i} ---")
            print(f"  Total FDs: {len(current_fds)}  New: {sorted(new_fds)}")
            print(f"  Threads: {threading.active_count()} ({[t.name for t in threading.enumerate()]})")
            if new_fds:
                print(f"  New FD classes: {classify_fds(new_fds)}")
            print()


if __name__ == "__main__":
    main()
