import json
import os
import shutil
import time
from collections.abc import Generator
from pathlib import Path

import click
import pytest
from click.shell_completion import CompletionItem

from imbue.mngr.cli.completion import COMPLETION_CACHE_FILENAME
from imbue.mngr.cli.completion import _BACKGROUND_REFRESH_COOLDOWN_SECONDS
from imbue.mngr.cli.completion import _read_agent_names_from_cache
from imbue.mngr.cli.completion import _trigger_background_cache_refresh
from imbue.mngr.cli.completion import complete_agent_name


def _path_without_mngr() -> str:
    """Return PATH with the directory containing `mngr` removed.

    Used in tests to prevent _trigger_background_cache_refresh from spawning
    a real subprocess, without breaking other binaries (like tmux) that test
    fixtures need during teardown.
    """
    mngr_path = shutil.which("mngr")
    if mngr_path is None:
        return os.environ.get("PATH", "")
    mngr_dir = str(Path(mngr_path).parent)
    current_path = os.environ.get("PATH", "")
    return os.pathsep.join(d for d in current_path.split(os.pathsep) if d != mngr_dir)


@pytest.fixture()
def completion_host_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[Path, None, None]:
    """Set up a temporary MNGR_HOST_DIR and return the host directory path."""
    host_dir = tmp_path / ".mngr"
    host_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MNGR_HOST_DIR", str(host_dir))
    yield host_dir


def _write_cache(host_dir: Path, names: list[str]) -> Path:
    """Write a completion cache file with the given names."""
    cache_path = host_dir / COMPLETION_CACHE_FILENAME
    data = {"names": names, "updated_at": "2025-01-01T00:00:00+00:00"}
    cache_path.write_text(json.dumps(data))
    return cache_path


# =============================================================================
# _read_agent_names_from_cache tests
# =============================================================================


def test_read_agent_names_from_cache_returns_names(
    completion_host_dir: Path,
) -> None:
    _write_cache(completion_host_dir, ["beta-agent", "alpha-agent"])

    result = _read_agent_names_from_cache()

    assert result == ["alpha-agent", "beta-agent"]


def test_read_agent_names_from_cache_returns_empty_when_no_file(
    completion_host_dir: Path,
) -> None:
    result = _read_agent_names_from_cache()

    assert result == []


def test_read_agent_names_from_cache_returns_empty_when_dir_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MNGR_HOST_DIR", str(tmp_path / "nonexistent"))

    result = _read_agent_names_from_cache()

    assert result == []


def test_read_agent_names_from_cache_returns_empty_for_malformed_json(
    completion_host_dir: Path,
) -> None:
    cache_path = completion_host_dir / COMPLETION_CACHE_FILENAME
    cache_path.write_text("not valid json {{{")

    result = _read_agent_names_from_cache()

    assert result == []


def test_read_agent_names_from_cache_returns_empty_when_names_not_list(
    completion_host_dir: Path,
) -> None:
    cache_path = completion_host_dir / COMPLETION_CACHE_FILENAME
    cache_path.write_text(json.dumps({"names": "not-a-list"}))

    result = _read_agent_names_from_cache()

    assert result == []


def test_read_agent_names_from_cache_returns_empty_when_names_missing(
    completion_host_dir: Path,
) -> None:
    cache_path = completion_host_dir / COMPLETION_CACHE_FILENAME
    cache_path.write_text(json.dumps({"other_key": "value"}))

    result = _read_agent_names_from_cache()

    assert result == []


def test_read_agent_names_from_cache_filters_non_string_and_empty_names(
    completion_host_dir: Path,
) -> None:
    cache_path = completion_host_dir / COMPLETION_CACHE_FILENAME
    cache_path.write_text(json.dumps({"names": ["good", "", 123, None, "also-good"]}))

    result = _read_agent_names_from_cache()

    assert result == ["also-good", "good"]


def test_read_agent_names_from_cache_uses_default_host_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MNGR_HOST_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    host_dir = tmp_path / ".mngr"
    host_dir.mkdir(parents=True, exist_ok=True)
    _write_cache(host_dir, ["home-agent"])

    result = _read_agent_names_from_cache()

    assert result == ["home-agent"]


# =============================================================================
# _trigger_background_cache_refresh tests
# =============================================================================


def test_trigger_background_cache_refresh_skips_when_cache_is_fresh(
    completion_host_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the cache was recently written, no subprocess should be spawned."""
    _write_cache(completion_host_dir, ["agent"])

    # Remove mngr from PATH as a safety net against accidental process spawning.
    # If the freshness check works, we never reach shutil.which() anyway.
    monkeypatch.setenv("PATH", _path_without_mngr())

    # Should return without spawning (cache is fresh)
    _trigger_background_cache_refresh()

    # Verify the cache still exists (was not corrupted)
    cache_path = completion_host_dir / COMPLETION_CACHE_FILENAME
    assert cache_path.is_file()


def test_trigger_background_cache_refresh_skips_when_mngr_not_on_path(
    completion_host_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When mngr is not found on PATH, no subprocess should be spawned."""
    # Make cache stale so the freshness check passes
    cache_path = _write_cache(completion_host_dir, ["agent"])
    old_time = time.time() - _BACKGROUND_REFRESH_COOLDOWN_SECONDS - 10
    os.utime(cache_path, (old_time, old_time))

    # Ensure mngr is not findable
    monkeypatch.setenv("PATH", _path_without_mngr())

    # Should return without spawning (mngr not found)
    _trigger_background_cache_refresh()


def test_trigger_background_cache_refresh_skips_when_no_cache_and_no_mngr(
    completion_host_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When no cache exists and mngr is not on PATH, nothing happens."""
    monkeypatch.setenv("PATH", _path_without_mngr())

    # Should return without error
    _trigger_background_cache_refresh()


# =============================================================================
# complete_agent_name tests
# =============================================================================


def test_complete_agent_name_filters_by_prefix(
    completion_host_dir: Path,
) -> None:
    # Cache is fresh (just written), so background refresh is throttled
    _write_cache(completion_host_dir, ["alpha-agent", "beta-agent", "alpha-other"])

    ctx = click.Context(click.Command("test"))
    param = click.Argument(["agent"])

    result = complete_agent_name(ctx, param, "alpha")

    assert len(result) == 2
    assert all(isinstance(item, CompletionItem) for item in result)
    names = [item.value for item in result]
    assert names == ["alpha-agent", "alpha-other"]


def test_complete_agent_name_returns_all_when_incomplete_is_empty(
    completion_host_dir: Path,
) -> None:
    # Cache is fresh (just written), so background refresh is throttled
    _write_cache(completion_host_dir, ["alpha", "beta"])

    ctx = click.Context(click.Command("test"))
    param = click.Argument(["agent"])

    result = complete_agent_name(ctx, param, "")

    assert len(result) == 2
    names = [item.value for item in result]
    assert names == ["alpha", "beta"]


def test_complete_agent_name_returns_empty_when_no_match(
    completion_host_dir: Path,
) -> None:
    # Cache is fresh (just written), so background refresh is throttled
    _write_cache(completion_host_dir, ["alpha"])

    ctx = click.Context(click.Command("test"))
    param = click.Argument(["agent"])

    result = complete_agent_name(ctx, param, "zzz")

    assert result == []


def test_complete_agent_name_returns_empty_when_no_cache(
    completion_host_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No cache exists, so background refresh would fire. Prevent it by removing mngr from PATH.
    monkeypatch.setenv("PATH", _path_without_mngr())

    ctx = click.Context(click.Command("test"))
    param = click.Argument(["agent"])

    result = complete_agent_name(ctx, param, "")

    assert result == []
