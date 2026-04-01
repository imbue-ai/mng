"""Repro script: check if GC resolves the FD leak.

Usage:
    uv run python scripts/qi/repro_fd_leak_gc.py
"""

import gc
import os
from pathlib import Path

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mngr.api.list import list_agents
from imbue.mngr.config.loader import load_config
from imbue.mngr.main import create_plugin_manager
from imbue.mngr.primitives import ErrorBehavior


def count_real_fds() -> int:
    """Count FDs that are actually accessible (not EBADF)."""
    count = 0
    for entry in Path("/dev/fd").iterdir():
        try:
            fd = int(entry.name)
            os.fstat(fd)  # Will raise OSError(EBADF) if not really open
            count += 1
        except (ValueError, OSError):
            pass
    return count


def count_devfd_entries() -> int:
    """Count all /dev/fd entries (including EBADF ones)."""
    return len(list(Path("/dev/fd").iterdir()))


def main() -> None:
    cg = ConcurrencyGroup(name="repro")
    with cg:
        pm = create_plugin_manager()
        mngr_ctx = load_config(pm, cg)

        gc.collect()
        initial_real = count_real_fds()
        initial_devfd = count_devfd_entries()
        print(f"Initial: real_fds={initial_real}, devfd_entries={initial_devfd}")

        for i in range(1, 11):
            list_agents(
                mngr_ctx=mngr_ctx,
                is_streaming=False,
                error_behavior=ErrorBehavior.CONTINUE,
                provider_names=("local",),
            )

            # Force garbage collection
            gc.collect()

            real = count_real_fds()
            devfd = count_devfd_entries()
            print(
                f"[{i:3d}] real_fds={real} (delta: {real - initial_real:+d}), "
                f"devfd_entries={devfd} (delta: {devfd - initial_devfd:+d})"
            )


if __name__ == "__main__":
    main()
