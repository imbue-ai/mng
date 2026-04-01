"""Repro script: exercise Modal SDK calls and monitor FD count.

Tests whether Modal SDK itself leaks file descriptors when making
repeated API calls (volume.listdir, volume.read_file, Sandbox.list, etc.).

Usage:
    uv run python scripts/qi/repro_modal_fd_leak.py [--iterations N]
"""

import argparse
import os
import stat
from pathlib import Path

import modal


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
    parser.add_argument("--app-name", type=str, default="mngr-modal")
    parser.add_argument("--volume-name", type=str, default="mngr-modal-state")
    parser.add_argument("--environment", type=str, default="mngr-Qi")
    args = parser.parse_args()

    print(f"Looking up app={args.app_name}, volume={args.volume_name}, env={args.environment}")

    # One-time setup
    app = modal.App.lookup(args.app_name, create_if_missing=False, environment_name=args.environment)
    app_id = app.app_id
    volume = modal.Volume.from_name(args.volume_name, environment_name=args.environment, version=2)
    print(f"App ID: {app_id}")

    initial_fds = count_open_fds()
    baseline = get_fd_set()
    print(f"Initial FDs: {initial_fds}")

    for i in range(1, args.iterations + 1):
        pre_fds = get_fd_set()

        # Simulate what discover_hosts_and_agents does:
        # 1. List sandboxes
        sandboxes = list(modal.Sandbox.list(app_id=app_id))

        # 2. List hosts on volume
        try:
            entries = list(volume.listdir("/hosts/"))
        except Exception:
            entries = []

        # 3. Read host records
        for entry in entries:
            if entry.path.endswith(".json"):
                try:
                    volume.read_file(entry.path)
                except Exception:
                    pass

        current_fds = count_open_fds()
        delta = current_fds - initial_fds
        new_this_iter = describe_new_fds(pre_fds)
        print(
            f"[{i:3d}] FDs: {current_fds} (delta: {delta:+d}, "
            f"sandboxes: {len(sandboxes)}, entries: {len(entries)})  "
            f"new: {new_this_iter}"
        )

    final_fds = count_open_fds()
    print(f"\nFinal FDs: {final_fds} (total delta: {final_fds - initial_fds:+d})")
    print(f"All leaked: {describe_new_fds(baseline)}")


if __name__ == "__main__":
    main()
