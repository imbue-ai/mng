"""Repro script: exercise pyinfra local command execution and monitor FD count.

Tests whether running commands via pyinfra's local connector leaks file descriptors.

Usage:
    uv run python scripts/qi/repro_local_host_commands_fd_leak.py [--iterations N]
"""

import argparse
import os
import stat
from pathlib import Path

from pyinfra.api.command import StringCommand
from pyinfra.api.inventory import Inventory
from pyinfra.api.state import State


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
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=20)
    args = parser.parse_args()

    initial_fds = count_open_fds()
    baseline = get_fd_set()
    print(f"Initial FDs: {initial_fds}")

    print("\n--- Test 1: Create host, run commands, disconnect (like get_host_and_agent_details) ---")
    for i in range(1, args.iterations + 1):
        pre = get_fd_set()

        # Create new host (like local provider get_host())
        names_data = (["@local"], {})
        inventory = Inventory(names_data)
        state = State(inventory=inventory)
        host = inventory.get_host("@local")
        host.init(state)

        # Connect
        if not host.connected:
            host.connect(raise_exceptions=True)

        # Run a few commands (like what get_host_and_agent_details does)
        host.run_shell_command(StringCommand("echo", "hello"))
        host.run_shell_command(StringCommand("uname", "-s"))
        host.run_shell_command(StringCommand("date"))

        # Disconnect
        host.disconnect()

        current = count_open_fds()
        new = describe_new_fds(pre)
        print(f"[{i:3d}] FDs: {current} (delta: {current - initial_fds:+d})  new: {new}")

    print(f"\nAfter test 1: FDs: {count_open_fds()} (delta: {count_open_fds() - initial_fds:+d})")

    print("\n--- Test 2: Create host, run commands, NO disconnect ---")
    baseline2 = get_fd_set()
    initial2 = count_open_fds()
    for i in range(1, args.iterations + 1):
        pre = get_fd_set()

        names_data = (["@local"], {})
        inventory = Inventory(names_data)
        state = State(inventory=inventory)
        host = inventory.get_host("@local")
        host.init(state)

        if not host.connected:
            host.connect(raise_exceptions=True)

        host.run_shell_command(StringCommand("echo", "hello"))
        host.run_shell_command(StringCommand("uname", "-s"))
        host.run_shell_command(StringCommand("date"))

        # NO disconnect

        current = count_open_fds()
        new = describe_new_fds(pre)
        print(f"[{i:3d}] FDs: {current} (delta: {current - initial2:+d})  new: {new}")

    print(f"\nAfter test 2: FDs: {count_open_fds()} (delta: {count_open_fds() - initial2:+d})")
    print(f"Total leaked: {describe_new_fds(baseline)}")


if __name__ == "__main__":
    main()
