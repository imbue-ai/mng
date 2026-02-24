import json
import os
import shutil
import time
from pathlib import Path

import psutil
import pytest

from imbue.mng.cli.completion import AGENT_COMPLETIONS_CACHE_FILENAME
from imbue.mng.cli.completion import _BACKGROUND_REFRESH_COOLDOWN_SECONDS
from imbue.mng.cli.completion import _trigger_background_cache_refresh
from imbue.mng.utils.polling import wait_for


def _write_cache(host_dir: Path, names: list[str]) -> Path:
    """Write a completion cache file with the given names."""
    cache_path = host_dir / AGENT_COMPLETIONS_CACHE_FILENAME
    data = {"names": names, "updated_at": "2025-01-01T00:00:00+00:00"}
    cache_path.write_text(json.dumps(data))
    return cache_path


@pytest.mark.timeout(30)
def test_trigger_background_cache_refresh_throttles_spawning(
    temp_host_dir: Path,
    disable_modal_for_subprocesses: Path,
) -> None:
    """Stale cache triggers a refresh that updates the file; fresh cache does not."""
    if shutil.which("mng") is None:
        pytest.skip("mng not on PATH")

    cache_path = temp_host_dir / AGENT_COMPLETIONS_CACHE_FILENAME

    # -- Stale cache: the spawned `mng list` should rewrite the cache file --
    _write_cache(temp_host_dir, ["agent"])
    old_time = time.time() - _BACKGROUND_REFRESH_COOLDOWN_SECONDS - 10
    os.utime(cache_path, (old_time, old_time))
    # Read back the mtime rather than using old_time directly, since some
    # filesystems round or truncate timestamps.
    stale_mtime = cache_path.stat().st_mtime

    _trigger_background_cache_refresh()

    wait_for(
        lambda: cache_path.stat().st_mtime != stale_mtime,
        timeout=15.0,
        error_message="Stale cache should trigger a background refresh that updates the file",
    )

    # Wait for the stale-cache process to exit before testing the fresh-cache path.
    def _no_mng_list_children() -> bool:
        for child in psutil.Process().children(recursive=True):
            try:
                if "mng" in " ".join(child.cmdline()) and "list" in " ".join(child.cmdline()):
                    return False
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        return True

    wait_for(_no_mng_list_children, timeout=10.0, error_message="Spawned mng list process did not exit")

    # -- Fresh cache: calling again immediately should be throttled --
    # _trigger_background_cache_refresh is synchronous up to the Popen call,
    # so if throttling fails, the child process exists immediately after return.
    children_before = set(p.pid for p in psutil.Process().children(recursive=True))

    _trigger_background_cache_refresh()

    children_after = set(p.pid for p in psutil.Process().children(recursive=True))
    new_children = children_after - children_before
    assert new_children == set(), "Fresh cache should prevent spawning"
