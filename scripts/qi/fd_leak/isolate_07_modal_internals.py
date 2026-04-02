"""Isolation step 7: Break down modal's discover_hosts_and_agents.

The modal provider's discover_hosts_and_agents does:
1. _list_running_host_ids (Modal API: Sandbox.list + get_tags)
2. _list_all_host_and_agent_records (Modal API: Volume.listdir + read_file)

This script calls these individually (in and out of executors) to find
which Modal API call creates the leaking sockets.

Usage:
    uv run python scripts/qi/fd_leak/isolate_07_modal_internals.py
"""

import gc
import os
from pathlib import Path

import modal

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.concurrency_group.executor import ConcurrencyGroupExecutor
from imbue.mngr.api.providers import get_all_provider_instances
from imbue.mngr.config.loader import load_config
from imbue.mngr.main import create_plugin_manager
from imbue.mngr.primitives import ProviderInstanceName


def count_real_fds() -> int:
    count = 0
    for entry in Path("/dev/fd").iterdir():
        try:
            os.fstat(int(entry.name))
            count += 1
        except (ValueError, OSError):
            pass
    return count


def main() -> None:
    cg = ConcurrencyGroup(name="repro")
    with cg:
        pm = create_plugin_manager()
        mngr_ctx = load_config(pm, cg)
        providers = get_all_provider_instances(mngr_ctx, None)
        provider_map = {p.name: p for p in providers}

        modal_provider = provider_map.get(ProviderInstanceName("modal"))
        if modal_provider is None:
            print("No modal provider found, exiting")
            return

        gc.collect()
        base = count_real_fds()
        print(f"Baseline FDs: {base}")

        # Get the app_id and volume for direct Modal SDK calls
        app_id = modal_provider._app.app_id  # noqa: SLF001
        volume = modal_provider.get_state_volume()

        print("\n--- Test 1: Sandbox.list (direct, no executor) ---")
        test_base = count_real_fds()
        for i in range(1, 6):
            list(modal.Sandbox.list(app_id=app_id))
            gc.collect()
            current = count_real_fds()
            print(f"[{i}] FDs: {current} (delta: {current - test_base:+d})")

        print("\n--- Test 2: Volume.listdir (direct, no executor) ---")
        test_base = count_real_fds()
        for i in range(1, 6):
            try:
                list(volume.listdir("/hosts/"))
            except Exception:
                pass
            gc.collect()
            current = count_real_fds()
            print(f"[{i}] FDs: {current} (delta: {current - test_base:+d})")

        print("\n--- Test 3: Sandbox.list in executor thread ---")
        test_base = count_real_fds()
        for i in range(1, 6):
            with ConcurrencyGroupExecutor(
                parent_cg=mngr_ctx.concurrency_group,
                name="test",
                max_workers=32,
            ) as executor:
                executor.submit(lambda: list(modal.Sandbox.list(app_id=app_id)))
            gc.collect()
            current = count_real_fds()
            print(f"[{i}] FDs: {current} (delta: {current - test_base:+d})")

        print("\n--- Test 4: Volume.listdir in executor thread ---")
        test_base = count_real_fds()
        for i in range(1, 6):

            def vol_work() -> None:
                try:
                    list(volume.listdir("/hosts/"))
                except Exception:
                    pass

            with ConcurrencyGroupExecutor(
                parent_cg=mngr_ctx.concurrency_group,
                name="test",
                max_workers=32,
            ) as executor:
                executor.submit(vol_work)
            gc.collect()
            current = count_real_fds()
            print(f"[{i}] FDs: {current} (delta: {current - test_base:+d})")

        print("\n--- Test 5: Both Modal calls in executor (like modal discover) ---")
        test_base = count_real_fds()
        for i in range(1, 6):

            def both_calls() -> None:
                list(modal.Sandbox.list(app_id=app_id))
                try:
                    list(volume.listdir("/hosts/"))
                except Exception:
                    pass

            with ConcurrencyGroupExecutor(
                parent_cg=mngr_ctx.concurrency_group,
                name="test",
                max_workers=32,
            ) as executor:
                executor.submit(both_calls)
            gc.collect()
            current = count_real_fds()
            print(f"[{i}] FDs: {current} (delta: {current - test_base:+d})")

        print("\n--- Test 6: Both Modal calls + noop in parallel (2 threads) ---")
        test_base = count_real_fds()
        for i in range(1, 6):

            def both_calls2() -> None:
                list(modal.Sandbox.list(app_id=app_id))
                try:
                    list(volume.listdir("/hosts/"))
                except Exception:
                    pass

            with ConcurrencyGroupExecutor(
                parent_cg=mngr_ctx.concurrency_group,
                name="test",
                max_workers=32,
            ) as executor:
                executor.submit(both_calls2)
                executor.submit(lambda: None)
            gc.collect()
            current = count_real_fds()
            print(f"[{i}] FDs: {current} (delta: {current - test_base:+d})")


if __name__ == "__main__":
    main()
