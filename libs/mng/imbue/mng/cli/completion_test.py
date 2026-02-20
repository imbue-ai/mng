import json
import os
import shutil
import time
from pathlib import Path

import click
import pytest
from click.shell_completion import CompletionItem

from imbue.mng.cli.completion import CLI_COMPLETIONS_FILENAME
from imbue.mng.cli.completion import COMPLETION_CACHE_FILENAME
from imbue.mng.cli.completion import _BACKGROUND_REFRESH_COOLDOWN_SECONDS
from imbue.mng.cli.completion import _read_agent_names_from_cache
from imbue.mng.cli.completion import _trigger_background_cache_refresh
from imbue.mng.cli.completion import complete_agent_name
from imbue.mng.cli.completion import read_cached_commands
from imbue.mng.cli.completion import read_cached_subcommands
from imbue.mng.cli.config import config as config_group
from imbue.mng.cli.plugin import plugin as plugin_group
from imbue.mng.cli.snapshot import snapshot as snapshot_group
from imbue.mng.main import cli


def _path_without_mng() -> str:
    """Return PATH with the directory containing `mng` removed.

    Used in tests to prevent _trigger_background_cache_refresh from spawning
    a real subprocess, without breaking other binaries (like tmux) that test
    fixtures need during teardown.
    """
    mng_path = shutil.which("mng")
    if mng_path is None:
        return os.environ.get("PATH", "")
    mng_dir = str(Path(mng_path).parent)
    current_path = os.environ.get("PATH", "")
    return os.pathsep.join(d for d in current_path.split(os.pathsep) if d != mng_dir)


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
    temp_host_dir: Path,
) -> None:
    _write_cache(temp_host_dir, ["beta-agent", "alpha-agent"])

    result = _read_agent_names_from_cache()

    assert result == ["alpha-agent", "beta-agent"]


def test_read_agent_names_from_cache_returns_empty_when_no_file(
    temp_host_dir: Path,
) -> None:
    result = _read_agent_names_from_cache()

    assert result == []


def test_read_agent_names_from_cache_returns_empty_when_dir_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MNG_HOST_DIR", str(tmp_path / "nonexistent"))

    result = _read_agent_names_from_cache()

    assert result == []


def test_read_agent_names_from_cache_returns_empty_for_malformed_json(
    temp_host_dir: Path,
) -> None:
    cache_path = temp_host_dir / COMPLETION_CACHE_FILENAME
    cache_path.write_text("not valid json {{{")

    result = _read_agent_names_from_cache()

    assert result == []


def test_read_agent_names_from_cache_returns_empty_when_names_not_list(
    temp_host_dir: Path,
) -> None:
    cache_path = temp_host_dir / COMPLETION_CACHE_FILENAME
    cache_path.write_text(json.dumps({"names": "not-a-list"}))

    result = _read_agent_names_from_cache()

    assert result == []


def test_read_agent_names_from_cache_returns_empty_when_names_missing(
    temp_host_dir: Path,
) -> None:
    cache_path = temp_host_dir / COMPLETION_CACHE_FILENAME
    cache_path.write_text(json.dumps({"other_key": "value"}))

    result = _read_agent_names_from_cache()

    assert result == []


def test_read_agent_names_from_cache_filters_non_string_and_empty_names(
    temp_host_dir: Path,
) -> None:
    cache_path = temp_host_dir / COMPLETION_CACHE_FILENAME
    cache_path.write_text(json.dumps({"names": ["good", "", 123, None, "also-good"]}))

    result = _read_agent_names_from_cache()

    assert result == ["also-good", "good"]


def test_read_agent_names_from_cache_uses_default_host_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MNG_HOST_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    host_dir = tmp_path / ".mng"
    host_dir.mkdir(parents=True, exist_ok=True)
    _write_cache(host_dir, ["home-agent"])

    result = _read_agent_names_from_cache()

    assert result == ["home-agent"]


# =============================================================================
# _trigger_background_cache_refresh tests
# =============================================================================


def test_trigger_background_cache_refresh_skips_when_cache_is_fresh(
    temp_host_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the cache was recently written, no subprocess should be spawned."""
    _write_cache(temp_host_dir, ["agent"])

    # Remove mng from PATH as a safety net against accidental process spawning.
    # If the freshness check works, we never reach shutil.which() anyway.
    monkeypatch.setenv("PATH", _path_without_mng())

    # Should return without spawning (cache is fresh)
    _trigger_background_cache_refresh()

    # Verify the cache still exists (was not corrupted)
    cache_path = temp_host_dir / COMPLETION_CACHE_FILENAME
    assert cache_path.is_file()


def test_trigger_background_cache_refresh_skips_when_mng_not_on_path(
    temp_host_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When mng is not found on PATH, no subprocess should be spawned."""
    # Make cache stale so the freshness check passes
    cache_path = _write_cache(temp_host_dir, ["agent"])
    old_time = time.time() - _BACKGROUND_REFRESH_COOLDOWN_SECONDS - 10
    os.utime(cache_path, (old_time, old_time))

    # Ensure mng is not findable
    monkeypatch.setenv("PATH", _path_without_mng())

    # Should return without spawning (mng not found)
    _trigger_background_cache_refresh()


def test_trigger_background_cache_refresh_skips_when_no_cache_and_no_mng(
    temp_host_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When no cache exists and mng is not on PATH, nothing happens."""
    monkeypatch.setenv("PATH", _path_without_mng())

    # Should return without error
    _trigger_background_cache_refresh()


# =============================================================================
# complete_agent_name tests
# =============================================================================


def test_complete_agent_name_filters_by_prefix(
    temp_host_dir: Path,
) -> None:
    # Cache is fresh (just written), so background refresh is throttled
    _write_cache(temp_host_dir, ["alpha-agent", "beta-agent", "alpha-other"])

    ctx = click.Context(click.Command("test"))
    param = click.Argument(["agent"])

    result = complete_agent_name(ctx, param, "alpha")

    assert len(result) == 2
    assert all(isinstance(item, CompletionItem) for item in result)
    names = [item.value for item in result]
    assert names == ["alpha-agent", "alpha-other"]


def test_complete_agent_name_returns_all_when_incomplete_is_empty(
    temp_host_dir: Path,
) -> None:
    # Cache is fresh (just written), so background refresh is throttled
    _write_cache(temp_host_dir, ["alpha", "beta"])

    ctx = click.Context(click.Command("test"))
    param = click.Argument(["agent"])

    result = complete_agent_name(ctx, param, "")

    assert len(result) == 2
    names = [item.value for item in result]
    assert names == ["alpha", "beta"]


def test_complete_agent_name_returns_empty_when_no_match(
    temp_host_dir: Path,
) -> None:
    # Cache is fresh (just written), so background refresh is throttled
    _write_cache(temp_host_dir, ["alpha"])

    ctx = click.Context(click.Command("test"))
    param = click.Argument(["agent"])

    result = complete_agent_name(ctx, param, "zzz")

    assert result == []


def test_complete_agent_name_returns_empty_when_no_cache(
    temp_host_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No cache exists, so background refresh would fire. Prevent it by removing mng from PATH.
    monkeypatch.setenv("PATH", _path_without_mng())

    ctx = click.Context(click.Command("test"))
    param = click.Argument(["agent"])

    result = complete_agent_name(ctx, param, "")

    assert result == []


# =============================================================================
# Static CLI completions tests
# =============================================================================


def _write_cli_completions(
    path: Path,
    commands: list[str] | None = None,
    subcommand_by_command: dict[str, list[str]] | None = None,
) -> Path:
    """Write a CLI completions file for testing."""
    data: dict = {}
    if commands is not None:
        data["commands"] = commands
    if subcommand_by_command is not None:
        data["subcommand_by_command"] = subcommand_by_command
    path.write_text(json.dumps(data))
    return path


# -- _read_cached_commands tests --


def test_read_cached_commands_returns_sorted_command_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completions_path = tmp_path / CLI_COMPLETIONS_FILENAME
    _write_cli_completions(completions_path, commands=["create", "ask", "list"])
    monkeypatch.setenv("MNG_CLI_COMPLETIONS_PATH", str(completions_path))

    result = read_cached_commands()

    assert result == ["ask", "create", "list"]


def test_read_cached_commands_returns_none_when_file_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MNG_CLI_COMPLETIONS_PATH", str(tmp_path / "nonexistent.json"))

    result = read_cached_commands()

    assert result is None


def test_read_cached_commands_returns_none_for_malformed_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completions_path = tmp_path / CLI_COMPLETIONS_FILENAME
    completions_path.write_text("not valid json {{{")
    monkeypatch.setenv("MNG_CLI_COMPLETIONS_PATH", str(completions_path))

    result = read_cached_commands()

    assert result is None


def test_read_cached_commands_returns_none_when_commands_key_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completions_path = tmp_path / CLI_COMPLETIONS_FILENAME
    completions_path.write_text(json.dumps({"other_key": "value"}))
    monkeypatch.setenv("MNG_CLI_COMPLETIONS_PATH", str(completions_path))

    result = read_cached_commands()

    assert result is None


def test_read_cached_commands_returns_none_when_commands_not_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completions_path = tmp_path / CLI_COMPLETIONS_FILENAME
    completions_path.write_text(json.dumps({"commands": "not-a-list"}))
    monkeypatch.setenv("MNG_CLI_COMPLETIONS_PATH", str(completions_path))

    result = read_cached_commands()

    assert result is None


def test_read_cached_commands_filters_non_string_and_empty_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completions_path = tmp_path / CLI_COMPLETIONS_FILENAME
    mixed_values: list = ["good", "", 123, None, "also-good"]
    _write_cli_completions(completions_path, commands=mixed_values)
    monkeypatch.setenv("MNG_CLI_COMPLETIONS_PATH", str(completions_path))

    result = read_cached_commands()

    assert result == ["also-good", "good"]


# -- _read_cached_subcommands tests --


def test_read_cached_subcommands_returns_sorted_subcommand_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completions_path = tmp_path / CLI_COMPLETIONS_FILENAME
    _write_cli_completions(
        completions_path,
        subcommand_by_command={"config": ["set", "get", "list"]},
    )
    monkeypatch.setenv("MNG_CLI_COMPLETIONS_PATH", str(completions_path))

    result = read_cached_subcommands("config")

    assert result == ["get", "list", "set"]


def test_read_cached_subcommands_returns_none_when_file_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MNG_CLI_COMPLETIONS_PATH", str(tmp_path / "nonexistent.json"))

    result = read_cached_subcommands("config")

    assert result is None


def test_read_cached_subcommands_returns_none_when_command_not_in_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completions_path = tmp_path / CLI_COMPLETIONS_FILENAME
    _write_cli_completions(
        completions_path,
        subcommand_by_command={"config": ["set", "get"]},
    )
    monkeypatch.setenv("MNG_CLI_COMPLETIONS_PATH", str(completions_path))

    result = read_cached_subcommands("nonexistent")

    assert result is None


def test_read_cached_subcommands_returns_none_when_subcommand_by_command_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completions_path = tmp_path / CLI_COMPLETIONS_FILENAME
    completions_path.write_text(json.dumps({"commands": ["create"]}))
    monkeypatch.setenv("MNG_CLI_COMPLETIONS_PATH", str(completions_path))

    result = read_cached_subcommands("config")

    assert result is None


def test_read_cached_subcommands_filters_non_string_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completions_path = tmp_path / CLI_COMPLETIONS_FILENAME
    mixed_values: list = ["good", "", 42, None, "also-good"]
    _write_cli_completions(
        completions_path,
        subcommand_by_command={"config": mixed_values},
    )
    monkeypatch.setenv("MNG_CLI_COMPLETIONS_PATH", str(completions_path))

    result = read_cached_subcommands("config")

    assert result == ["also-good", "good"]


# -- Real file integration tests --


def test_real_cli_completions_file_exists_and_has_expected_structure() -> None:
    """The generated cli_completions.json should be present and well-formed."""
    path = Path(__file__).parent.parent / "resources" / CLI_COMPLETIONS_FILENAME
    assert path.is_file(), f"Expected {path} to exist (run: uv run python scripts/make_cli_docs.py)"

    data = json.loads(path.read_text())
    assert isinstance(data, dict)
    assert isinstance(data.get("commands"), list)
    assert isinstance(data.get("subcommand_by_command"), dict)

    # Spot-check some expected commands
    commands = data["commands"]
    assert "create" in commands
    assert "list" in commands
    assert "destroy" in commands

    # Spot-check subcommands
    subcommands = data["subcommand_by_command"]
    assert "config" in subcommands
    assert "get" in subcommands["config"]
    assert "set" in subcommands["config"]
    assert "snapshot" in subcommands
    assert "create" in subcommands["snapshot"]
    assert "plugin" in subcommands
    assert "list" in subcommands["plugin"]


# -- shell_complete override tests --


def test_top_level_shell_complete_uses_cached_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AliasAwareGroup.shell_complete should read from the static cache."""
    completions_path = tmp_path / CLI_COMPLETIONS_FILENAME
    _write_cli_completions(completions_path, commands=["create", "list", "destroy"])
    monkeypatch.setenv("MNG_CLI_COMPLETIONS_PATH", str(completions_path))

    ctx = click.Context(cli)
    completions = cli.shell_complete(ctx, "cr")

    names = [item.value for item in completions]
    assert "create" in names


def test_top_level_shell_complete_falls_back_when_no_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the cache file is missing, shell_complete should fall back to live discovery."""
    monkeypatch.setenv("MNG_CLI_COMPLETIONS_PATH", str(tmp_path / "nonexistent.json"))

    ctx = click.Context(cli)
    completions = cli.shell_complete(ctx, "cr")

    names = [item.value for item in completions]
    assert "create" in names


def test_config_shell_complete_uses_cached_subcommands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The config group should read subcommand completions from the static cache."""
    completions_path = tmp_path / CLI_COMPLETIONS_FILENAME
    _write_cli_completions(
        completions_path,
        subcommand_by_command={"config": ["edit", "get", "list", "set"]},
    )
    monkeypatch.setenv("MNG_CLI_COMPLETIONS_PATH", str(completions_path))

    ctx = click.Context(config_group)
    completions = config_group.shell_complete(ctx, "")

    names = [item.value for item in completions]
    assert "get" in names
    assert "set" in names
    assert "edit" in names


def test_plugin_shell_complete_uses_cached_subcommands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The plugin group should read subcommand completions from the static cache."""
    completions_path = tmp_path / CLI_COMPLETIONS_FILENAME
    _write_cli_completions(
        completions_path,
        subcommand_by_command={"plugin": ["add", "list", "remove"]},
    )
    monkeypatch.setenv("MNG_CLI_COMPLETIONS_PATH", str(completions_path))

    ctx = click.Context(plugin_group)
    completions = plugin_group.shell_complete(ctx, "")

    names = [item.value for item in completions]
    assert "add" in names
    assert "list" in names
    assert "remove" in names


def test_snapshot_shell_complete_uses_cached_subcommands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The snapshot group should read subcommand completions from the static cache."""
    completions_path = tmp_path / CLI_COMPLETIONS_FILENAME
    _write_cli_completions(
        completions_path,
        subcommand_by_command={"snapshot": ["create", "destroy", "list"]},
    )
    monkeypatch.setenv("MNG_CLI_COMPLETIONS_PATH", str(completions_path))

    ctx = click.Context(snapshot_group)
    completions = snapshot_group.shell_complete(ctx, "cr")

    names = [item.value for item in completions]
    assert "create" in names
    assert "destroy" not in names


def test_subcommand_shell_complete_falls_back_when_no_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the cache file is missing, subcommand groups should fall back to live discovery."""
    monkeypatch.setenv("MNG_CLI_COMPLETIONS_PATH", str(tmp_path / "nonexistent.json"))

    ctx = click.Context(config_group)
    completions = config_group.shell_complete(ctx, "")

    names = [item.value for item in completions]
    assert "get" in names
    assert "set" in names
