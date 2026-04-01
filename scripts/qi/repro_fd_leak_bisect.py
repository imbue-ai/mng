"""Bisect the FD leak by calling individual steps of the list_agents pipeline.

Usage:
    uv run python scripts/qi/repro_fd_leak_bisect.py
"""

import gc
import os
from pathlib import Path

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mngr.api.discover import discover_hosts_and_agents
from imbue.mngr.api.list import ListResult
from imbue.mngr.api.list import _ListAgentsParams
from imbue.mngr.api.list import _collect_and_emit_details_for_host
from imbue.mngr.api.list import _maybe_write_full_discovery_snapshot
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
    delta = current - initial
    print(f"  {label}: real_fds={current} (delta: {delta:+d})")
    return current


def main() -> None:
    cg = ConcurrencyGroup(name="repro")
    with cg:
        pm = create_plugin_manager()
        mngr_ctx = load_config(pm, cg)

        gc.collect()
        initial = count_real_fds()
        print(f"Initial real FDs: {initial}")

        for iteration in range(1, 4):
            print(f"\n=== Iteration {iteration} ===")
            before = count_real_fds()

            # Step 1: discover_hosts_and_agents
            agents_by_host, providers = discover_hosts_and_agents(
                mngr_ctx,
                provider_names=("local",),
                agent_identifiers=None,
                include_destroyed=True,
                reset_caches=False,
            )
            after_discover = checkpoint("After discover_hosts_and_agents", before)
            provider_map = {p.name: p for p in providers}

            # Step 2: get_host_and_agent_details for each host
            from threading import Lock

            result = ListResult()
            results_lock = Lock()
            params = _ListAgentsParams(
                compiled_include_filters=[],
                compiled_exclude_filters=[],
                error_behavior=ErrorBehavior.CONTINUE,
                on_agent=None,
                on_error=None,
            )

            for host_ref, agent_refs in agents_by_host.items():
                if not agent_refs:
                    continue
                provider = provider_map.get(host_ref.provider_name)
                if not provider:
                    continue

                before_host = count_real_fds()
                _collect_and_emit_details_for_host(host_ref, agent_refs, provider, params, result, results_lock)
                checkpoint(f"After host {host_ref.host_id}", before_host)

            after_details = checkpoint("After all get_host_and_agent_details", before)

            # Step 3: _maybe_write_full_discovery_snapshot
            _maybe_write_full_discovery_snapshot(mngr_ctx, result, ("local",), (), ())
            after_snapshot = checkpoint("After write_full_discovery_snapshot", before)

            print(f"  TOTAL delta this iteration: {count_real_fds() - before:+d}")


if __name__ == "__main__":
    main()
