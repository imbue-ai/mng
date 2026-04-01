"""Repro script: test both providers with per-phase FD tracking.

Usage:
    uv run python scripts/qi/repro_fd_leak_both_providers.py
"""

import gc
import os
from pathlib import Path
from threading import Lock

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.concurrency_group.executor import ConcurrencyGroupExecutor
from imbue.mngr.api.discover import discover_hosts_and_agents
from imbue.mngr.api.list import ListResult
from imbue.mngr.api.list import _ListAgentsParams
from imbue.mngr.api.list import _maybe_write_full_discovery_snapshot
from imbue.mngr.api.list import _process_host_with_error_handling
from imbue.mngr.config.loader import load_config
from imbue.mngr.main import create_plugin_manager
from imbue.mngr.primitives import ErrorBehavior


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


def checkpoint(label: str, initial: int) -> int:
    gc.collect()
    current = count_real_fds()
    print(f"  {label}: {current} (delta from start: {current - initial:+d})")
    return current


def main() -> None:
    gc.collect()
    initial = count_real_fds()
    print(f"Initial real FDs: {initial}")

    cg = ConcurrencyGroup(name="repro")
    with cg:
        pm = create_plugin_manager()
        mngr_ctx = load_config(pm, cg)

        for iteration in range(1, 4):
            before = count_real_fds()
            print(f"\n=== Iteration {iteration} (before: {before}) ===")

            # Phase 1: discover
            agents_by_host, providers = discover_hosts_and_agents(
                mngr_ctx,
                provider_names=None,  # ALL providers
                agent_identifiers=None,
                include_destroyed=True,
                reset_caches=False,
            )
            checkpoint("After discover", before)
            provider_map = {p.name: p for p in providers}

            # Phase 2: process hosts in executor (matching _list_agents_batch)
            result = ListResult()
            results_lock = Lock()
            params = _ListAgentsParams(
                compiled_include_filters=[],
                compiled_exclude_filters=[],
                error_behavior=ErrorBehavior.CONTINUE,
                on_agent=None,
                on_error=None,
            )

            futures = []
            with ConcurrencyGroupExecutor(
                parent_cg=mngr_ctx.concurrency_group, name="list_agents_process_hosts", max_workers=32
            ) as executor:
                for host_ref, agent_refs in agents_by_host.items():
                    if not agent_refs:
                        continue
                    provider = provider_map.get(host_ref.provider_name)
                    if not provider:
                        continue
                    futures.append(
                        executor.submit(
                            _process_host_with_error_handling,
                            host_ref,
                            agent_refs,
                            provider,
                            params,
                            result,
                            results_lock,
                        )
                    )
            for f in futures:
                f.result()

            checkpoint("After process hosts", before)

            # Phase 3: write snapshot
            _maybe_write_full_discovery_snapshot(mngr_ctx, result, None, (), ())
            checkpoint("After write snapshot", before)

            print(f"  Agents: {len(result.agents)}, Errors: {len(result.errors)}")
            if result.errors:
                for err in result.errors:
                    print(f"    Error: {err}")


if __name__ == "__main__":
    main()
