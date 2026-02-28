"""Unit tests for deploy_utils shared utilities."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from imbue.mng.providers.deploy_utils import collect_deploy_files


def test_collect_deploy_files_merges_results() -> None:
    """collect_deploy_files should merge results from multiple plugins."""
    ctx = MagicMock()
    ctx.pm.hook.get_files_for_deploy.return_value = [
        {Path("~/.mng/config.toml"): Path("/local/config.toml")},
        {Path("~/.claude.json"): '{"key": "value"}'},
    ]

    result = collect_deploy_files(ctx, repo_root=Path("/repo"))

    assert len(result) == 2
    assert Path("~/.mng/config.toml") in result
    assert Path("~/.claude.json") in result


def test_collect_deploy_files_rejects_absolute_paths() -> None:
    """collect_deploy_files should reject absolute destination paths."""
    ctx = MagicMock()
    ctx.pm.hook.get_files_for_deploy.return_value = [
        {Path("/etc/config"): "content"},
    ]

    with pytest.raises(ValueError, match="must be relative or start with '~'"):
        collect_deploy_files(ctx, repo_root=Path("/repo"))


def test_collect_deploy_files_allows_tilde_paths() -> None:
    """collect_deploy_files should allow paths starting with ~."""
    ctx = MagicMock()
    ctx.pm.hook.get_files_for_deploy.return_value = [
        {Path("~/.mng/config.toml"): "content"},
    ]

    result = collect_deploy_files(ctx, repo_root=Path("/repo"))
    assert Path("~/.mng/config.toml") in result


def test_collect_deploy_files_allows_relative_paths() -> None:
    """collect_deploy_files should allow relative paths."""
    ctx = MagicMock()
    ctx.pm.hook.get_files_for_deploy.return_value = [
        {Path(".mng/settings.local.toml"): "content"},
    ]

    result = collect_deploy_files(ctx, repo_root=Path("/repo"))
    assert Path(".mng/settings.local.toml") in result


def test_collect_deploy_files_last_plugin_wins_on_collision() -> None:
    """When multiple plugins return the same path, last one wins."""
    ctx = MagicMock()
    ctx.pm.hook.get_files_for_deploy.return_value = [
        {Path("~/.mng/config.toml"): "first"},
        {Path("~/.mng/config.toml"): "second"},
    ]

    result = collect_deploy_files(ctx, repo_root=Path("/repo"))
    assert result[Path("~/.mng/config.toml")] == "second"


def test_collect_deploy_files_empty_results() -> None:
    """collect_deploy_files should handle no results gracefully."""
    ctx = MagicMock()
    ctx.pm.hook.get_files_for_deploy.return_value = []

    result = collect_deploy_files(ctx, repo_root=Path("/repo"))
    assert result == {}
