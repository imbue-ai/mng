"""Isolation step 6: Only modal provider's discover_hosts_and_agents in executor.

If modal alone in an executor does NOT leak, but modal + local does,
then the leak requires both providers to run concurrently.

Also tests: modal discover called directly (no executor) vs in executor.

Usage:
    uv run python scripts/qi/fd_leak/isolate_06_parallel_only_modal_discover.py
"""

import gc
import os
from pathlib import Path
from threading import Lock

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.concurrency_group.executor import ConcurrencyGroupExecutor
from imbue.mngr.api.providers import get_all_provider_instances
from imbue.mngr.config.loader import load_config
from imbue.mngr.main import create_plugin_manager
from imbue.mngr.primitives import DiscoveredAgent
from imbue.mngr.primitives import DiscoveredHost
from imbue.mngr.primitives import ProviderInstanceName
from imbue.mngr.providers.base_provider import BaseProviderInstance


def count_real_fds() -> int:
    count = 0
    for entry in Path("/dev/fd").iterdir():
        try:
            os.fstat(int(entry.name))
            count += 1
        except (ValueError, OSError):
            pass
    return count


def discover_one_provider(
    provider: BaseProviderInstance,
    results: dict[DiscoveredHost, list[DiscoveredAgent]],
    lock: Lock,
    cg: ConcurrencyGroup,
) -> None:
    provider_results = provider.discover_hosts_and_agents(cg=cg, include_destroyed=True)
    with lock:
        results.update(provider_results)


def main() -> None:
    cg = ConcurrencyGroup(name="repro")
    with cg:
        pm = create_plugin_manager()
        mngr_ctx = load_config(pm, cg)
        providers = get_all_provider_instances(mngr_ctx, None)
        provider_map = {p.name: p for p in providers}

        gc.collect()
        base = count_real_fds()
        print(f"Baseline FDs: {base}")

        modal_provider = provider_map.get(ProviderInstanceName("modal"))
        if modal_provider is None:
            print("No modal provider found, exiting")
            return

        print("\n--- Test 1: modal discover directly (no executor) ---")
        test_base = count_real_fds()
        for i in range(1, 6):
            modal_provider.discover_hosts_and_agents(
                cg=mngr_ctx.concurrency_group,
                include_destroyed=True,
            )
            gc.collect()
            current = count_real_fds()
            print(f"[{i}] FDs: {current} (delta: {current - test_base:+d})")

        print("\n--- Test 2: modal discover alone in executor ---")
        test_base = count_real_fds()
        for i in range(1, 6):
            results: dict[DiscoveredHost, list[DiscoveredAgent]] = {}
            lock = Lock()
            with ConcurrencyGroupExecutor(
                parent_cg=mngr_ctx.concurrency_group,
                name="test_modal_only",
                max_workers=32,
            ) as executor:
                executor.submit(
                    discover_one_provider,
                    modal_provider,
                    results,
                    lock,
                    mngr_ctx.concurrency_group,
                )
            gc.collect()
            current = count_real_fds()
            print(f"[{i}] FDs: {current} (delta: {current - test_base:+d})")


if __name__ == "__main__":
    main()
