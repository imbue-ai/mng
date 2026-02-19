"""Integration tests for the gc CLI command.

Note: Unit tests for gc API functions (CEL filters, resource conversion) are in api/gc_test.py
"""

import json
from datetime import datetime
from datetime import timezone
from pathlib import Path

import pluggy
from click.testing import CliRunner

from imbue.mng.cli.gc import gc
from imbue.mng.interfaces.data_types import CertifiedHostData
from imbue.mng.providers.local.instance import get_or_create_local_host_id


def _write_certified_data(per_host_dir: Path, temp_host_dir: Path, generated_work_dirs: tuple[str, ...]) -> Path:
    """Write CertifiedHostData to data.json in the per-host directory. Returns data_path."""
    host_id = get_or_create_local_host_id(temp_host_dir)
    now = datetime.now(timezone.utc)
    certified_data = CertifiedHostData(
        host_id=str(host_id),
        host_name="test-host",
        generated_work_dirs=generated_work_dirs,
        created_at=now,
        updated_at=now,
    )
    data_path = per_host_dir / "data.json"
    data_path.write_text(json.dumps(certified_data.model_dump(by_alias=True, mode="json"), indent=2))
    return data_path


def test_gc_work_dirs_dry_run(
    cli_runner: CliRunner,
    temp_host_dir: Path,
    per_host_dir: Path,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test gc --work-dirs --dry-run shows orphaned directories without removing them."""
    orphaned_dir = temp_host_dir / "worktrees" / "orphaned-agent-123"
    orphaned_dir.mkdir(parents=True)

    _write_certified_data(per_host_dir, temp_host_dir, (str(orphaned_dir),))

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
    per_host_dir: Path,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test gc --work-dirs removes orphaned directories and updates certified data."""
    orphaned_dir = temp_host_dir / "worktrees" / "orphaned-agent-456"
    orphaned_dir.mkdir(parents=True)

    test_file = orphaned_dir / "test.txt"
    test_file.write_text("test content")

    data_path = _write_certified_data(per_host_dir, temp_host_dir, (str(orphaned_dir),))

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
    per_host_dir: Path,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test gc --work-dirs with CEL filters."""
    orphaned_dir1 = temp_host_dir / "worktrees" / "temp-agent-123"
    orphaned_dir1.mkdir(parents=True)

    orphaned_dir2 = temp_host_dir / "worktrees" / "prod-agent-456"
    orphaned_dir2.mkdir(parents=True)

    _write_certified_data(per_host_dir, temp_host_dir, (str(orphaned_dir1), str(orphaned_dir2)))

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


def test_gc_work_dirs_with_provider_name_filter(
    cli_runner: CliRunner,
    temp_host_dir: Path,
    per_host_dir: Path,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """Test gc work-dirs with provider_name CEL filter.

    This test verifies that the documented CEL field name 'provider_name' works correctly.
    The gc CEL context is flat (no x. prefix needed), so filters use field names directly.
    """
    orphaned_dir = temp_host_dir / "worktrees" / "orphaned-provider-test"
    orphaned_dir.mkdir(parents=True, exist_ok=True)

    _write_certified_data(per_host_dir, temp_host_dir, (str(orphaned_dir),))

    # Filter by provider_name - should match local provider
    result = cli_runner.invoke(
        gc,
        ["--work-dirs", "--include", 'provider_name == "local"', "--dry-run"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "Work directories: 1" in result.output

    # Filter by non-matching provider_name - should find nothing
    result_no_match = cli_runner.invoke(
        gc,
        ["--work-dirs", "--include", 'provider_name == "docker"', "--dry-run"],
        obj=plugin_manager,
        catch_exceptions=False,
    )

    assert result_no_match.exit_code == 0
    assert "No resources found" in result_no_match.output
