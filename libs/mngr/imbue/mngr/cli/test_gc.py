"""Integration tests for the gc CLI command.

Note: Unit tests for gc API functions (CEL filters, resource conversion) are in api/gc_test.py
"""

import json
from pathlib import Path

import pluggy
from click.testing import CliRunner

from imbue.mngr.cli.gc import gc
from imbue.mngr.interfaces.data_types import CertifiedHostData


def test_gc_work_dirs_dry_run(
    cli_runner: CliRunner,
    temp_host_dir: Path,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test gc --work-dirs --dry-run shows orphaned directories without removing them."""
    orphaned_dir = temp_host_dir / "worktrees" / "orphaned-agent-123"
    orphaned_dir.mkdir(parents=True)

    certified_data = CertifiedHostData(generated_work_dirs=(str(orphaned_dir),))
    data_path = temp_host_dir / "data.json"
    data_path.write_text(json.dumps(certified_data.model_dump(by_alias=True), indent=2))

    result = cli_runner.invoke(
        gc,
        ["--work-dirs", "--dry-run"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "Would destroy" in result.output
    assert str(orphaned_dir) in result.output
    assert orphaned_dir.exists(), "Directory should still exist after dry-run"


def test_gc_work_dirs_removes_orphaned_directory(
    cli_runner: CliRunner,
    temp_host_dir: Path,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test gc --work-dirs removes orphaned directories and updates certified data."""
    orphaned_dir = temp_host_dir / "worktrees" / "orphaned-agent-456"
    orphaned_dir.mkdir(parents=True)

    test_file = orphaned_dir / "test.txt"
    test_file.write_text("test content")

    certified_data = CertifiedHostData(generated_work_dirs=(str(orphaned_dir),))
    data_path = temp_host_dir / "data.json"
    data_path.write_text(json.dumps(certified_data.model_dump(by_alias=True), indent=2))

    result = cli_runner.invoke(
        gc,
        ["--work-dirs"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "Work directories: 1" in result.output
    assert "Destroyed 1 resource(s)" in result.output
    assert not orphaned_dir.exists(), "Orphaned directory should be removed"

    updated_data = CertifiedHostData.model_validate_json(data_path.read_text())
    assert str(orphaned_dir) not in updated_data.generated_work_dirs, "generated_work_dirs should be updated"


def test_gc_work_dirs_with_cel_filter(
    cli_runner: CliRunner,
    temp_host_dir: Path,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test gc --work-dirs with CEL filters."""
    orphaned_dir1 = temp_host_dir / "worktrees" / "temp-agent-123"
    orphaned_dir1.mkdir(parents=True)

    orphaned_dir2 = temp_host_dir / "worktrees" / "prod-agent-456"
    orphaned_dir2.mkdir(parents=True)

    certified_data = CertifiedHostData(generated_work_dirs=(str(orphaned_dir1), str(orphaned_dir2)))
    data_path = temp_host_dir / "data.json"
    data_path.write_text(json.dumps(certified_data.model_dump(by_alias=True), indent=2))

    result = cli_runner.invoke(
        gc,
        ["--work-dirs", "--exclude", "name.startsWith('temp')"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "Work directories: 1" in result.output
    assert orphaned_dir1.exists(), "temp directory should still exist (excluded)"
    assert not orphaned_dir2.exists(), "prod directory should be removed"
