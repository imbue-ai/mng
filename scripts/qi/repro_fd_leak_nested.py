"""Bisect: reproduce the exact nesting pattern of list_agents.

Usage:
    uv run python scripts/qi/repro_fd_leak_nested.py
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
from imbue.mngr.api.list import _collect_and_emit_details_for_host
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


def main() -> None:
    gc.collect()
    initial = count_real_fds()
    print(f"Initial real FDs: {initial}")

    cg = ConcurrencyGroup(name="repro")
    with cg:
        pm = create_plugin_manager()
        mngr_ctx = load_config(pm, cg)

        for iteration in range(1, 6):
            before = count_real_fds()

            # Phase 1: discover (same as _list_agents_batch)
            agents_by_host, providers = discover_hosts_and_agents(
                mngr_ctx,
                provider_names=("local",),
                agent_identifiers=None,
                include_destroyed=True,
                reset_caches=False,
            )
            provider_map = {p.name: p for p in providers}

            gc.collect()
            after_discover = count_real_fds()

            # Phase 2: process hosts in ConcurrencyGroupExecutor (like _list_agents_batch)
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
                            _collect_and_emit_details_for_host,
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

            gc.collect()
            after_process = count_real_fds()

            print(
                f"[{iteration}] discover: {after_discover - before:+d}, "
                f"process: {after_process - after_discover:+d}, "
                f"total: {after_process - before:+d}, "
                f"cumulative: {after_process - initial:+d}"
            )

    gc.collect()
    print(f"\nFinal: {count_real_fds()} (delta: {count_real_fds() - initial:+d})")


if __name__ == "__main__":
    main()
