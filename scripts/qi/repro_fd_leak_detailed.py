"""Repro script: detailed FD leak investigation.

Tracks FDs at a very granular level within the list_agents pipeline.

Usage:
    uv run python scripts/qi/repro_fd_leak_detailed.py
"""

import os
import stat
from pathlib import Path

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mngr.api.list import list_agents
from imbue.mngr.config.loader import load_config
from imbue.mngr.main import create_plugin_manager
from imbue.mngr.primitives import ErrorBehavior


def get_fd_details() -> dict[int, str]:
    """Get details of all currently open FDs."""
    details = {}
    for entry in Path("/dev/fd").iterdir():
        try:
            fd = int(entry.name)
        except ValueError:
            continue
        try:
            # Try to read the symlink target
            target = os.readlink(f"/dev/fd/{fd}")
            st = os.fstat(fd)
            if stat.S_ISFIFO(st.st_mode):
                kind = "pipe"
            elif stat.S_ISSOCK(st.st_mode):
                kind = "socket"
            elif stat.S_ISREG(st.st_mode):
                kind = f"file({target})"
            elif stat.S_ISCHR(st.st_mode):
                kind = f"chr({target})"
            else:
                kind = f"mode={oct(st.st_mode)}({target})"
            details[fd] = kind
        except OSError:
            details[fd] = "closed/inaccessible"
    return details


def diff_fds(before: dict[int, str], after: dict[int, str]) -> tuple[dict[int, str], dict[int, str]]:
    """Return (new FDs, closed FDs)."""
    new_fds = {fd: desc for fd, desc in after.items() if fd not in before}
    closed_fds = {fd: desc for fd, desc in before.items() if fd not in after}
    return new_fds, closed_fds


def main() -> None:
    cg = ConcurrencyGroup(name="repro")
    with cg:
        pm = create_plugin_manager()
        mngr_ctx = load_config(pm, cg)

        print(f"Initial FDs: {len(get_fd_details())}")
        print()

        for i in range(1, 6):
            before = get_fd_details()

            result = list_agents(
                mngr_ctx=mngr_ctx,
                is_streaming=False,
                error_behavior=ErrorBehavior.CONTINUE,
                provider_names=("local",),
            )

            after = get_fd_details()
            new_fds, closed_fds = diff_fds(before, after)

            print(f"--- Iteration {i} (agents: {len(result.agents)}) ---")
            if new_fds:
                print(f"  NEW FDs:")
                for fd, desc in sorted(new_fds.items()):
                    print(f"    fd={fd}: {desc}")
            if closed_fds:
                print(f"  CLOSED FDs:")
                for fd, desc in sorted(closed_fds.items()):
                    print(f"    fd={fd}: {desc}")
            if not new_fds and not closed_fds:
                print("  No FD changes")
            print()


if __name__ == "__main__":
    main()
