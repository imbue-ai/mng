import json
import os
import sys
import time
from pathlib import Path

import psutil
import pytest

from imbue.mng.cli.complete import _AGENT_COMPLETIONS_CACHE_FILENAME
from imbue.mng.cli.complete import _BACKGROUND_REFRESH_COOLDOWN_SECONDS
from imbue.mng.cli.complete import _trigger_background_refresh
from imbue.mng.utils.polling import wait_for


def _write_cache(cache_dir: Path, names: list[str]) -> Path:
    """Write an agent completions cache file with the given names."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / _AGENT_COMPLETIONS_CACHE_FILENAME
    data = {"names": names, "updated_at": "2025-01-01T00:00:00+00:00"}
    cache_path.write_text(json.dumps(data))
    return cache_path


def _make_fast_refresh_command(cache_path: Path) -> list[str]:
    """Build a lightweight Python command that writes the cache directly.

    This avoids importing the full mng CLI, which can be slow under CI load.
    """
    script = (
        "import json; "
        "open({path!r}, 'w').write(json.dumps({{'names': [], 'updated_at': '2026-01-01T00:00:00+00:00'}}))"
    ).format(path=str(cache_path))
    return [sys.executable, "-c", script]


def _is_completion_refresh_process(proc: psutil.Process) -> bool:
    """Check if a process is a background completion refresh subprocess."""
    try:
        cmdline = " ".join(proc.cmdline())
        return "agent_completions" in cmdline or ("imbue.mng.main" in cmdline and "list" in cmdline)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False


@pytest.mark.timeout(30)
def test_trigger_background_refresh_throttles_spawning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stale cache triggers a refresh that updates the file; fresh cache does not."""
    cache_dir = tmp_path / "completions"
    cache_dir.mkdir()
    monkeypatch.setenv("MNG_COMPLETION_CACHE_DIR", str(cache_dir))

    cache_path = cache_dir / _AGENT_COMPLETIONS_CACHE_FILENAME

    # Build a fast command that writes the cache directly (no mng import needed)
    fast_command = _make_fast_refresh_command(cache_path)

    # -- Stale cache: the spawned subprocess should rewrite the cache file --
    _write_cache(cache_dir, ["agent"])
    old_time = time.time() - _BACKGROUND_REFRESH_COOLDOWN_SECONDS - 10
    os.utime(cache_path, (old_time, old_time))
    stale_mtime = cache_path.stat().st_mtime

    _trigger_background_refresh(command=fast_command)

    wait_for(
        lambda: cache_path.stat().st_mtime != stale_mtime,
        timeout=15.0,
        error_message="Stale cache should trigger a background refresh that updates the file",
    )

    # Wait for the stale-cache process to exit before testing the fresh-cache path.
    def _no_refresh_children() -> bool:
        return not any(_is_completion_refresh_process(c) for c in psutil.Process().children(recursive=True))

    wait_for(_no_refresh_children, timeout=10.0, error_message="Background refresh process did not exit")

    # -- Fresh cache: calling again immediately should be throttled --
    children_before = set(p.pid for p in psutil.Process().children(recursive=True))

    _trigger_background_refresh(command=fast_command)

    children_after = set(p.pid for p in psutil.Process().children(recursive=True))
    new_children = children_after - children_before
    assert new_children == set(), "Fresh cache should prevent spawning"
