import json
import os
import time
from pathlib import Path

import click
import pytest
from click.shell_completion import CompletionItem

from imbue.mng.cli.completion import AGENT_COMPLETIONS_CACHE_FILENAME
from imbue.mng.cli.completion import COMMAND_COMPLETIONS_CACHE_FILENAME
from imbue.mng.cli.completion import _BACKGROUND_REFRESH_COOLDOWN_SECONDS
from imbue.mng.cli.completion import _read_agent_names_from_cache
from imbue.mng.cli.completion import _trigger_background_cache_refresh
from imbue.mng.cli.completion import complete_agent_name
from imbue.mng.cli.completion import read_cached_commands
from imbue.mng.cli.completion import read_cached_subcommands
from imbue.mng.cli.completion_writer import write_cli_completions_cache
from imbue.mng.cli.config import config as config_group
from imbue.mng.cli.plugin import plugin as plugin_group
from imbue.mng.cli.snapshot import snapshot as snapshot_group
from imbue.mng.cli.test_plugin_cli_commands import _PluginWithSimpleCommand
from imbue.mng.cli.test_plugin_cli_commands import _test_cli_with_plugin
from imbue.mng.main import cli


def _ensure_fresh_cache(host_dir: Path) -> None:
    """Write a fresh agent completions cache file if one doesn't already exist.

    The freshness check in _trigger_background_cache_refresh compares the
    cache file's mtime against a cooldown threshold. Writing a file with
    the current mtime guarantees the check returns early (no subprocess).
    """
    cache_path = host_dir / AGENT_COMPLETIONS_CACHE_FILENAME
    if not cache_path.is_file():
        cache_path.write_text(json.dumps({"names": [], "updated_at": ""}))


def _write_cache(host_dir: Path, names: list[str]) -> Path:
    """Write a completion cache file with the given names."""
    cache_path = host_dir / AGENT_COMPLETIONS_CACHE_FILENAME
    data = {"names": names, "updated_at": "2025-01-01T00:00:00+00:00"}
    cache_path.write_text(json.dumps(data))
    return cache_path


def _write_cli_completions(
    host_dir: Path,
    commands: list[str] | None = None,
    subcommand_by_command: dict[str, list[str]] | None = None,
) -> Path:
    """Write a CLI completions cache file for testing."""
    data: dict = {}
    if commands is not None:
        data["commands"] = commands
    if subcommand_by_command is not None:
        data["subcommand_by_command"] = subcommand_by_command
    cache_path = host_dir / COMMAND_COMPLETIONS_CACHE_FILENAME
    cache_path.write_text(json.dumps(data))
    return cache_path


@pytest.fixture
def no_background_cache_refresh(temp_host_dir: Path) -> None:
    """Prevent _trigger_background_cache_refresh from spawning a real subprocess.

    Ensures a fresh cache file exists so the mtime-based cooldown check in
    _trigger_background_cache_refresh returns early before reaching Popen.
    """
    _ensure_fresh_cache(temp_host_dir)


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
    cache_path = temp_host_dir / AGENT_COMPLETIONS_CACHE_FILENAME
    cache_path.write_text("not valid json {{{")

    result = _read_agent_names_from_cache()

    assert result == []


def test_read_agent_names_from_cache_returns_empty_when_names_not_list(
    temp_host_dir: Path,
) -> None:
    cache_path = temp_host_dir / AGENT_COMPLETIONS_CACHE_FILENAME
    cache_path.write_text(json.dumps({"names": "not-a-list"}))

    result = _read_agent_names_from_cache()

    assert result == []


def test_read_agent_names_from_cache_returns_empty_when_names_missing(
    temp_host_dir: Path,
) -> None:
    cache_path = temp_host_dir / AGENT_COMPLETIONS_CACHE_FILENAME
    cache_path.write_text(json.dumps({"other_key": "value"}))

    result = _read_agent_names_from_cache()

    assert result == []


def test_read_agent_names_from_cache_filters_non_string_and_empty_names(
    temp_host_dir: Path,
) -> None:
    cache_path = temp_host_dir / AGENT_COMPLETIONS_CACHE_FILENAME
    cache_path.write_text(json.dumps({"names": ["good", "", 123, None, "also-good"]}))

    result = _read_agent_names_from_cache()

    assert result == ["also-good", "good"]


def test_read_agent_names_from_cache_uses_default_host_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MNG_HOST_DIR", raising=False)
    monkeypatch.delenv("MNG_ROOT_NAME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    host_dir = tmp_path / ".mng"
    host_dir.mkdir(parents=True, exist_ok=True)
    _write_cache(host_dir, ["home-agent"])

    result = _read_agent_names_from_cache()

    assert result == ["home-agent"]


# =============================================================================
# _trigger_background_cache_refresh tests
# =============================================================================


def test_trigger_background_cache_refresh_does_not_corrupt_fresh_cache(
    temp_host_dir: Path,
    no_background_cache_refresh: None,
) -> None:
    _write_cache(temp_host_dir, ["agent"])

    _trigger_background_cache_refresh()

    cache_path = temp_host_dir / AGENT_COMPLETIONS_CACHE_FILENAME
    assert cache_path.is_file()


def test_trigger_background_cache_refresh_does_not_raise_with_stale_cache(
    temp_host_dir: Path,
    no_background_cache_refresh: None,
) -> None:
    cache_path = _write_cache(temp_host_dir, ["agent"])
    old_time = time.time() - _BACKGROUND_REFRESH_COOLDOWN_SECONDS - 10
    os.utime(cache_path, (old_time, old_time))

    _trigger_background_cache_refresh()


def test_trigger_background_cache_refresh_does_not_raise_with_no_cache(
    temp_host_dir: Path,
    no_background_cache_refresh: None,
) -> None:
    _trigger_background_cache_refresh()


# =============================================================================
# complete_agent_name tests
# =============================================================================


def test_complete_agent_name_filters_by_prefix(
    temp_host_dir: Path,
    no_background_cache_refresh: None,
) -> None:
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
    no_background_cache_refresh: None,
) -> None:
    _write_cache(temp_host_dir, ["alpha", "beta"])

    ctx = click.Context(click.Command("test"))
    param = click.Argument(["agent"])

    result = complete_agent_name(ctx, param, "")

    assert len(result) == 2
    names = [item.value for item in result]
    assert names == ["alpha", "beta"]


def test_complete_agent_name_returns_empty_when_no_match(
    temp_host_dir: Path,
    no_background_cache_refresh: None,
) -> None:
    _write_cache(temp_host_dir, ["alpha"])

    ctx = click.Context(click.Command("test"))
    param = click.Argument(["agent"])

    result = complete_agent_name(ctx, param, "zzz")

    assert result == []


def test_complete_agent_name_returns_empty_when_no_cache(
    temp_host_dir: Path,
    no_background_cache_refresh: None,
) -> None:
    ctx = click.Context(click.Command("test"))
    param = click.Argument(["agent"])

    result = complete_agent_name(ctx, param, "")

    assert result == []


# =============================================================================
# CLI completions cache tests
# =============================================================================


# -- write_cli_completions_cache tests --


def test_write_cli_completions_cache_writes_commands_and_subcommands(
    temp_host_dir: Path,
) -> None:
    """write_cli_completions_cache should write all commands and subcommands."""
    write_cli_completions_cache(cli)

    cache_path = temp_host_dir / COMMAND_COMPLETIONS_CACHE_FILENAME
    assert cache_path.is_file()
    data = json.loads(cache_path.read_text())

    assert "create" in data["commands"]
    assert "list" in data["commands"]
    assert "config" in data["subcommand_by_command"]
    assert "get" in data["subcommand_by_command"]["config"]
    assert "snapshot" in data["subcommand_by_command"]
    assert "plugin" in data["subcommand_by_command"]


def test_write_cli_completions_cache_includes_aliases(
    temp_host_dir: Path,
) -> None:
    """write_cli_completions_cache should include command aliases."""
    write_cli_completions_cache(cli)

    cache_path = temp_host_dir / COMMAND_COMPLETIONS_CACHE_FILENAME
    data = json.loads(cache_path.read_text())
    commands = data["commands"]

    assert "c" in commands
    assert "ls" in commands
    assert "rm" in commands


def test_write_cli_completions_cache_includes_plugin_commands(
    temp_host_dir: Path,
) -> None:
    """Plugin-registered commands should appear in the completions cache."""
    with _test_cli_with_plugin(_PluginWithSimpleCommand()) as test_cli:
        write_cli_completions_cache(test_cli)

    cache_path = temp_host_dir / COMMAND_COMPLETIONS_CACHE_FILENAME
    data = json.loads(cache_path.read_text())

    assert "greet" in data["commands"]


def test_write_cli_completions_cache_includes_plugin_group_subcommands(
    temp_host_dir: Path,
) -> None:
    """Plugin-registered group commands should have their subcommands cached."""

    @click.group()
    def test_cli() -> None:
        pass

    @click.group(name="myplugin")
    def plugin_group_cmd() -> None:
        pass

    @plugin_group_cmd.command(name="run")
    def run_cmd() -> None:
        pass

    @plugin_group_cmd.command(name="status")
    def status_cmd() -> None:
        pass

    test_cli.add_command(plugin_group_cmd)
    write_cli_completions_cache(test_cli)

    cache_path = temp_host_dir / COMMAND_COMPLETIONS_CACHE_FILENAME
    data = json.loads(cache_path.read_text())

    assert "myplugin" in data["commands"]
    assert "myplugin" in data["subcommand_by_command"]
    assert "run" in data["subcommand_by_command"]["myplugin"]
    assert "status" in data["subcommand_by_command"]["myplugin"]


# -- read_cached_commands tests --


def test_read_cached_commands_returns_sorted_command_names(
    temp_host_dir: Path,
) -> None:
    _write_cli_completions(temp_host_dir, commands=["create", "ask", "list"])

    result = read_cached_commands()

    assert result == ["ask", "create", "list"]


def test_read_cached_commands_returns_none_when_file_missing(
    temp_host_dir: Path,
) -> None:
    result = read_cached_commands()

    assert result is None


def test_read_cached_commands_returns_none_for_malformed_json(
    temp_host_dir: Path,
) -> None:
    cache_path = temp_host_dir / COMMAND_COMPLETIONS_CACHE_FILENAME
    cache_path.write_text("not valid json {{{")

    result = read_cached_commands()

    assert result is None


def test_read_cached_commands_returns_none_when_commands_key_missing(
    temp_host_dir: Path,
) -> None:
    cache_path = temp_host_dir / COMMAND_COMPLETIONS_CACHE_FILENAME
    cache_path.write_text(json.dumps({"other_key": "value"}))

    result = read_cached_commands()

    assert result is None


def test_read_cached_commands_returns_none_when_commands_not_list(
    temp_host_dir: Path,
) -> None:
    cache_path = temp_host_dir / COMMAND_COMPLETIONS_CACHE_FILENAME
    cache_path.write_text(json.dumps({"commands": "not-a-list"}))

    result = read_cached_commands()

    assert result is None


def test_read_cached_commands_filters_non_string_and_empty_entries(
    temp_host_dir: Path,
) -> None:
    mixed_values: list = ["good", "", 123, None, "also-good"]
    _write_cli_completions(temp_host_dir, commands=mixed_values)

    result = read_cached_commands()

    assert result == ["also-good", "good"]


# -- read_cached_subcommands tests --


def test_read_cached_subcommands_returns_sorted_subcommand_names(
    temp_host_dir: Path,
) -> None:
    _write_cli_completions(
        temp_host_dir,
        subcommand_by_command={"config": ["set", "get", "list"]},
    )

    result = read_cached_subcommands("config")

    assert result == ["get", "list", "set"]


def test_read_cached_subcommands_returns_none_when_file_missing(
    temp_host_dir: Path,
) -> None:
    result = read_cached_subcommands("config")

    assert result is None


def test_read_cached_subcommands_returns_none_when_command_not_in_cache(
    temp_host_dir: Path,
) -> None:
    _write_cli_completions(
        temp_host_dir,
        subcommand_by_command={"config": ["set", "get"]},
    )

    result = read_cached_subcommands("nonexistent")

    assert result is None


def test_read_cached_subcommands_returns_none_when_subcommand_by_command_missing(
    temp_host_dir: Path,
) -> None:
    cache_path = temp_host_dir / COMMAND_COMPLETIONS_CACHE_FILENAME
    cache_path.write_text(json.dumps({"commands": ["create"]}))

    result = read_cached_subcommands("config")

    assert result is None


def test_read_cached_subcommands_filters_non_string_entries(
    temp_host_dir: Path,
) -> None:
    mixed_values: list = ["good", "", 42, None, "also-good"]
    _write_cli_completions(
        temp_host_dir,
        subcommand_by_command={"config": mixed_values},
    )

    result = read_cached_subcommands("config")

    assert result == ["also-good", "good"]


# -- shell_complete override tests --


def test_top_level_shell_complete_uses_cached_commands(
    temp_host_dir: Path,
) -> None:
    """AliasAwareGroup.shell_complete should read from the cache."""
    _write_cli_completions(temp_host_dir, commands=["create", "list", "destroy"])

    ctx = click.Context(cli)
    completions = cli.shell_complete(ctx, "cr")

    names = [item.value for item in completions]
    assert "create" in names


def test_top_level_shell_complete_falls_back_when_no_cache(
    temp_host_dir: Path,
) -> None:
    """When the cache file is missing, shell_complete should fall back to live discovery."""
    ctx = click.Context(cli)
    completions = cli.shell_complete(ctx, "cr")

    names = [item.value for item in completions]
    assert "create" in names


def test_config_shell_complete_uses_cached_subcommands(
    temp_host_dir: Path,
) -> None:
    """The config group should read subcommand completions from the cache."""
    _write_cli_completions(
        temp_host_dir,
        subcommand_by_command={"config": ["edit", "get", "list", "set"]},
    )

    ctx = click.Context(config_group)
    completions = config_group.shell_complete(ctx, "")

    names = [item.value for item in completions]
    assert "get" in names
    assert "set" in names
    assert "edit" in names


def test_plugin_shell_complete_uses_cached_subcommands(
    temp_host_dir: Path,
) -> None:
    """The plugin group should read subcommand completions from the cache."""
    _write_cli_completions(
        temp_host_dir,
        subcommand_by_command={"plugin": ["add", "list", "remove"]},
    )

    ctx = click.Context(plugin_group)
    completions = plugin_group.shell_complete(ctx, "")

    names = [item.value for item in completions]
    assert "add" in names
    assert "list" in names
    assert "remove" in names


def test_snapshot_shell_complete_uses_cached_subcommands(
    temp_host_dir: Path,
) -> None:
    """The snapshot group should read subcommand completions from the cache."""
    _write_cli_completions(
        temp_host_dir,
        subcommand_by_command={"snapshot": ["create", "destroy", "list"]},
    )

    ctx = click.Context(snapshot_group)
    completions = snapshot_group.shell_complete(ctx, "cr")

    names = [item.value for item in completions]
    assert "create" in names
    assert "destroy" not in names


def test_subcommand_shell_complete_falls_back_when_no_cache(
    temp_host_dir: Path,
) -> None:
    """When the cache file is missing, subcommand groups should fall back to live discovery."""
    ctx = click.Context(config_group)
    completions = config_group.shell_complete(ctx, "")

    names = [item.value for item in completions]
    assert "get" in names
    assert "set" in names
