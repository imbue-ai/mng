"""Integration tests for the tab completion cache.

These tests run write_cli_completions_cache against the real CLI group to
verify that hand-maintained completion constants reference options that
actually exist. This catches renames (e.g. --base-branch -> --branch)
that unit tests with hand-crafted data miss.
"""

import json
from pathlib import Path

import click

from imbue.mng.config.completion_cache import COMPLETION_CACHE_FILENAME
from imbue.mng.config.completion_cache import CompletionCacheData
from imbue.mng.config.completion_writer import write_cli_completions_cache
from imbue.mng.config.data_types import MngContext
from imbue.mng.main import cli


def _read_cache(cache_dir: Path) -> CompletionCacheData:
    data = json.loads((cache_dir / COMPLETION_CACHE_FILENAME).read_text())
    return CompletionCacheData(**{k: v for k, v in data.items() if k in CompletionCacheData._fields})


def _assert_option_exists_on_cli(dotted_key: str, label: str) -> None:
    """Assert that a dotted key like "create.--host" references a real CLI option."""
    parts = dotted_key.split(".")
    option_name = parts[-1]
    assert option_name.startswith("--"), f"Unexpected key format in {label}: {dotted_key}"

    cmd: click.BaseCommand = cli
    for part in parts[:-1]:
        assert isinstance(cmd, click.Group) and part in cmd.commands, (
            f"{label} key {dotted_key!r} references command {part!r} which does not exist"
        )
        cmd = cmd.commands[part]

    option_names = set()
    for param in cmd.params:
        if hasattr(param, "opts"):
            option_names.update(param.opts)
            option_names.update(param.secondary_opts)
    assert option_name in option_names, (
        f"{label} key {dotted_key!r} references {option_name!r} "
        f"which does not exist. Available: {sorted(option_names)}"
    )


def test_option_choices_reference_real_options(
    completion_cache_dir: Path,
    temp_mng_ctx: MngContext,
) -> None:
    """Every option_choices key must reference an option that exists on the real CLI."""
    write_cli_completions_cache(cli_group=cli, mng_ctx=temp_mng_ctx)
    cache = _read_cache(completion_cache_dir)

    for choice_key in cache.option_choices:
        _assert_option_exists_on_cli(choice_key, "option_choices")


def test_git_branch_options_reference_real_options(completion_cache_dir: Path) -> None:
    """Every git_branch_options key must reference an option that exists on the real CLI."""
    write_cli_completions_cache(cli_group=cli)
    cache = _read_cache(completion_cache_dir)

    for key in cache.git_branch_options:
        _assert_option_exists_on_cli(key, "git_branch_options")


def test_host_name_options_reference_real_options(completion_cache_dir: Path) -> None:
    """Every host_name_options key must reference an option that exists on the real CLI."""
    write_cli_completions_cache(cli_group=cli)
    cache = _read_cache(completion_cache_dir)

    for key in cache.host_name_options:
        _assert_option_exists_on_cli(key, "host_name_options")


def test_plugin_name_options_reference_real_options(completion_cache_dir: Path) -> None:
    """Every plugin_name_options key must reference an option that exists on the real CLI."""
    write_cli_completions_cache(cli_group=cli)
    cache = _read_cache(completion_cache_dir)

    for key in cache.plugin_name_options:
        _assert_option_exists_on_cli(key, "plugin_name_options")
