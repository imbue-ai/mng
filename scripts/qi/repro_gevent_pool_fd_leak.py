"""Repro script: test whether gevent.pool.Pool leaks FDs.

Usage:
    uv run python scripts/qi/repro_gevent_pool_fd_leak.py
"""

import os
import stat
from pathlib import Path

from gevent.pool import Pool


def count_open_fds() -> int:
    return len(list(Path("/dev/fd").iterdir()))


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
            else:
                desc = f"mode={oct(st.st_mode)}"
        except OSError:
            desc = "closed?"
        descriptions.append(f"{fd}={desc}")
    suffix = f" (+{len(new_fds) - 10} more)" if len(new_fds) > 10 else ""
    return ", ".join(descriptions) + suffix


def main() -> None:
    initial_fds = count_open_fds()
    baseline = get_fd_set()
    print(f"Initial FDs: {initial_fds}")

    print("\n--- Test 1: Create gevent Pools ---")
    for i in range(1, 11):
        pre = get_fd_set()
        pool = Pool(20)
        fact_pool = Pool(20)
        del pool, fact_pool
        current = count_open_fds()
        new = describe_new_fds(pre)
        print(f"[{i:3d}] FDs: {current} (delta: {current - initial_fds:+d})  new: {new}")

    print(f"\nAfter pools: FDs: {count_open_fds()} (delta: {count_open_fds() - initial_fds:+d})")
    print(f"All leaked: {describe_new_fds(baseline)}")

    print("\n--- Test 2: Create pyinfra State/Inventory ---")
    from pyinfra.api.inventory import Inventory
    from pyinfra.api.state import State

    baseline2 = get_fd_set()
    initial2 = count_open_fds()
    for i in range(1, 11):
        pre = get_fd_set()
        names_data = (["@local"], {})
        inventory = Inventory(names_data)
        state = State(inventory=inventory)
        host = inventory.get_host("@local")
        host.init(state)
        del state, inventory, host
        current = count_open_fds()
        new = describe_new_fds(pre)
        print(f"[{i:3d}] FDs: {current} (delta: {current - initial2:+d})  new: {new}")

    print(f"\nAfter states: FDs: {count_open_fds()} (delta: {count_open_fds() - initial2:+d})")
    print(f"All leaked: {describe_new_fds(baseline2)}")


if __name__ == "__main__":
    main()
