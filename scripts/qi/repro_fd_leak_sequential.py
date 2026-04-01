"""Repro: run providers sequentially vs in parallel.

Usage:
    uv run python scripts/qi/repro_fd_leak_sequential.py
"""

import gc
import os
from pathlib import Path

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mngr.api.providers import get_all_provider_instances
from imbue.mngr.config.loader import load_config
from imbue.mngr.main import create_plugin_manager


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


def main() -> None:
    gc.collect()
    initial = count_real_fds()
    print(f"Initial real FDs: {initial}")

    cg = ConcurrencyGroup(name="repro")
    with cg:
        pm = create_plugin_manager()
        mngr_ctx = load_config(pm, cg)
        providers = get_all_provider_instances(mngr_ctx, None)

        print("\n--- Test: discover providers SEQUENTIALLY (no ConcurrencyGroupExecutor) ---")
        base = count_real_fds()
        for i in range(1, 6):
            for provider in providers:
                provider.discover_hosts_and_agents(cg=mngr_ctx.concurrency_group, include_destroyed=True)
            gc.collect()
            current = count_real_fds()
            print(f"[{i}] FDs: {current} (delta: {current - base:+d})")


if __name__ == "__main__":
    main()
