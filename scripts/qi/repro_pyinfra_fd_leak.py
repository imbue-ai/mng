"""Repro script: exercise pyinfra State/Inventory creation and monitor FD count.

Tests whether pyinfra leaks file descriptors when creating State/Inventory objects
(which happens every time the local provider's get_host() is called).

Usage:
    uv run python scripts/qi/repro_pyinfra_fd_leak.py [--iterations N]
"""

import argparse
import os
import stat
from pathlib import Path

from pyinfra.api.inventory import Inventory
from pyinfra.api.state import State


def count_open_fds() -> int:
    fd_dir = Path("/dev/fd")
    try:
        return len(list(fd_dir.iterdir()))
    except OSError:
        return -1


def get_fd_set() -> set[int]:
    fds: set[int] = set()
    for entry in Path("/dev/fd").iterdir():
        try:
            fds.add(int(entry.name))
        except ValueError:
            pass
    return fds


def describe_new_fds(baseline_fds: set[int]) -> str:
    current_fds: set[int] = set()
    for entry in Path("/dev/fd").iterdir():
        try:
            current_fds.add(int(entry.name))
        except ValueError:
            pass

    new_fds = sorted(current_fds - baseline_fds)
    if not new_fds:
        return "no new FDs"

    descriptions = []
    for fd in new_fds[:10]:
        try:
            st = os.fstat(fd)
            if stat.S_ISFIFO(st.st_mode):
                desc = "pipe"
            elif stat.S_ISSOCK(st.st_mode):
                desc = "socket"
            elif stat.S_ISREG(st.st_mode):
                desc = "file"
            elif stat.S_ISCHR(st.st_mode):
                desc = "chr"
            else:
                desc = f"mode={oct(st.st_mode)}"
        except OSError:
            desc = "closed?"
        descriptions.append(f"{fd}={desc}")

    suffix = f" (+{len(new_fds) - 10} more)" if len(new_fds) > 10 else ""
    return ", ".join(descriptions) + suffix


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=20)
    args = parser.parse_args()

    initial_fds = count_open_fds()
    baseline = get_fd_set()
    print(f"Initial FDs: {initial_fds}")

    for i in range(1, args.iterations + 1):
        pre_fds = get_fd_set()

        # Simulate what local provider's get_host() does:
        names_data = (["@local"], {})
        inventory = Inventory(names_data)
        state = State(inventory=inventory)
        pyinfra_host = inventory.get_host("@local")
        pyinfra_host.init(state)

        # Also simulate running a command (what get_host_and_agent_details does)
        if not pyinfra_host.connected:
            pyinfra_host.connect(raise_exceptions=True)

        # Simulate disconnect
        if pyinfra_host.connected:
            pyinfra_host.disconnect()

        current_fds = count_open_fds()
        delta = current_fds - initial_fds
        new_this_iter = describe_new_fds(pre_fds)
        print(f"[{i:3d}] FDs: {current_fds} (delta: {delta:+d})  new: {new_this_iter}")

    final_fds = count_open_fds()
    print(f"\nFinal FDs: {final_fds} (total delta: {final_fds - initial_fds:+d})")
    print(f"All leaked: {describe_new_fds(baseline)}")


if __name__ == "__main__":
    main()
