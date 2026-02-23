"""Unit tests for deploy.py pure functions."""

import json
import os
import shutil
from pathlib import Path

import pluggy

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mng.config.data_types import MngConfig
from imbue.mng.config.data_types import MngContext
from imbue.mng_schedule.data_types import ScheduleTriggerDefinition
from imbue.mng_schedule.data_types import ScheduledMngCommand
from imbue.mng_schedule.implementations.modal.deploy import _resolve_timezone_from_paths
from imbue.mng_schedule.implementations.modal.deploy import build_deploy_config
from imbue.mng_schedule.implementations.modal.deploy import get_modal_app_name
from imbue.mng_schedule.implementations.modal.deploy import stage_deploy_files


def test_get_modal_app_name() -> None:
    assert get_modal_app_name("my-trigger") == "mng-schedule-my-trigger"
    assert get_modal_app_name("nightly") == "mng-schedule-nightly"


def test_build_deploy_config_returns_all_keys() -> None:
    trigger = ScheduleTriggerDefinition(
        name="test",
        command=ScheduledMngCommand.CREATE,
        args="--message hello",
        schedule_cron="0 3 * * *",
        provider="modal",
        is_enabled=True,
        git_image_hash="abc123",
    )
    result = build_deploy_config(
        app_name="test-app",
        trigger=trigger,
        cron_schedule="0 3 * * *",
        cron_timezone="America/Los_Angeles",
    )
    assert result["app_name"] == "test-app"
    assert result["cron_schedule"] == "0 3 * * *"
    assert result["cron_timezone"] == "America/Los_Angeles"
    assert result["trigger"]["name"] == "test"
    assert result["trigger"]["command"] == "CREATE"
    assert result["trigger"]["args"] == "--message hello"


def test_resolve_timezone_reads_etc_timezone(tmp_path: Path) -> None:
    etc_timezone = tmp_path / "timezone"
    etc_timezone.write_text("America/New_York\n")
    etc_localtime = tmp_path / "localtime"

    result = _resolve_timezone_from_paths(etc_timezone, etc_localtime)
    assert result == "America/New_York"


def test_resolve_timezone_falls_back_to_localtime_symlink(tmp_path: Path) -> None:
    etc_timezone = tmp_path / "timezone"
    etc_localtime = tmp_path / "localtime"
    # Create a symlink that looks like a zoneinfo path
    zoneinfo_dir = tmp_path / "usr" / "share" / "zoneinfo" / "Europe" / "London"
    zoneinfo_dir.parent.mkdir(parents=True)
    zoneinfo_dir.touch()
    etc_localtime.symlink_to(zoneinfo_dir)

    result = _resolve_timezone_from_paths(etc_timezone, etc_localtime)
    assert result == "Europe/London"


def test_resolve_timezone_returns_utc_when_nothing_found(tmp_path: Path) -> None:
    etc_timezone = tmp_path / "timezone"
    etc_localtime = tmp_path / "localtime"

    result = _resolve_timezone_from_paths(etc_timezone, etc_localtime)
    assert result == "UTC"


def test_resolve_timezone_skips_empty_etc_timezone(tmp_path: Path) -> None:
    etc_timezone = tmp_path / "timezone"
    etc_timezone.write_text("  \n")
    etc_localtime = tmp_path / "localtime"

    result = _resolve_timezone_from_paths(etc_timezone, etc_localtime)
    assert result == "UTC"


# =============================================================================
# stage_deploy_files Tests
# =============================================================================


def _simulate_install_deploy_files(staging_dir: Path) -> None:
    """Simulate what _install_deploy_files does in the cron_runner.

    Reads the manifest and copies files to their destinations.
    This duplicates the cron_runner logic for testing (since cron_runner.py
    cannot be imported due to module-level Modal configuration).
    """
    manifest_path = staging_dir / "deploy_files_manifest.json"
    if not manifest_path.exists():
        return

    manifest: dict[str, str] = json.loads(manifest_path.read_text())
    files_dir = staging_dir / "deploy_files"

    for filename, dest_path_str in manifest.items():
        source = files_dir / filename
        if not source.exists():
            continue
        if dest_path_str.startswith("~"):
            dest_path = Path(os.path.expanduser(dest_path_str))
        else:
            dest_path = Path(dest_path_str)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest_path)


def test_stage_deploy_files_creates_manifest_and_files(
    tmp_path: Path,
    plugin_manager: "pluggy.PluginManager",
) -> None:
    """stage_deploy_files should create a manifest and stage files from plugins."""
    # Create claude config files so the hook finds them
    claude_json = Path.home() / ".claude.json"
    claude_json.write_text('{"staged": true}')

    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    staging_dir = tmp_path / "staging"
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    config = MngConfig(default_host_dir=tmp_path / ".mng")
    with ConcurrencyGroup(name="test-staging") as cg:
        mng_ctx = MngContext(
            config=config,
            pm=plugin_manager,
            profile_dir=profile_dir,
            concurrency_group=cg,
        )
        stage_deploy_files(staging_dir, mng_ctx, repo_root)

    # Verify manifest exists and has entries
    manifest_path = staging_dir / "deploy_files_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert any("~/.claude.json" == v for v in manifest.values())

    # Verify deploy_files directory exists with numbered files
    files_dir = staging_dir / "deploy_files"
    assert files_dir.exists()
    assert any(files_dir.iterdir())


def test_stage_deploy_files_roundtrip_restores_files(
    tmp_path: Path,
    plugin_manager: "pluggy.PluginManager",
) -> None:
    """Files staged by stage_deploy_files can be installed back to their destinations."""
    # Create config files so the hooks find them
    claude_json = Path.home() / ".claude.json"
    claude_json.write_text('{"roundtrip": true}')
    mng_dir = Path.home() / ".mng"
    mng_dir.mkdir(parents=True, exist_ok=True)
    mng_config = mng_dir / "config.toml"
    mng_config.write_text("[test]\nroundtrip = true\n")

    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    staging_dir = tmp_path / "staging"
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    config = MngConfig(default_host_dir=tmp_path / ".mng_host")
    with ConcurrencyGroup(name="test-roundtrip") as cg:
        mng_ctx = MngContext(
            config=config,
            pm=plugin_manager,
            profile_dir=profile_dir,
            concurrency_group=cg,
        )
        stage_deploy_files(staging_dir, mng_ctx, repo_root)

    # Delete the originals to prove the install recreates them
    claude_json.unlink()
    mng_config.unlink()

    # Simulate what _install_deploy_files does
    _simulate_install_deploy_files(staging_dir)

    # Verify files were restored
    assert claude_json.exists()
    assert claude_json.read_text() == '{"roundtrip": true}'
    assert mng_config.exists()
    assert mng_config.read_text() == "[test]\nroundtrip = true\n"


def test_stage_deploy_files_stages_secrets_env(tmp_path: Path, plugin_manager: "pluggy.PluginManager") -> None:
    """stage_deploy_files should stage the secrets .env file when present."""
    repo_root = tmp_path / "repo"
    secrets_dir = repo_root / ".mng" / "dev" / "secrets"
    secrets_dir.mkdir(parents=True)
    (secrets_dir / ".env").write_text("GH_TOKEN=test123")

    staging_dir = tmp_path / "staging"
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    config = MngConfig(default_host_dir=tmp_path / ".mng")
    with ConcurrencyGroup(name="test-secrets") as cg:
        mng_ctx = MngContext(
            config=config,
            pm=plugin_manager,
            profile_dir=profile_dir,
            concurrency_group=cg,
        )
        stage_deploy_files(staging_dir, mng_ctx, repo_root)

    # Verify secrets were staged
    staged_secrets = staging_dir / "secrets" / ".env"
    assert staged_secrets.exists()
    assert staged_secrets.read_text() == "GH_TOKEN=test123"


def test_stage_deploy_files_creates_empty_manifest_when_no_files(
    tmp_path: Path, plugin_manager: "pluggy.PluginManager"
) -> None:
    """stage_deploy_files should create an empty manifest when no plugin returns files."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    staging_dir = tmp_path / "staging"
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    config = MngConfig(default_host_dir=tmp_path / ".mng")
    with ConcurrencyGroup(name="test-empty") as cg:
        mng_ctx = MngContext(
            config=config,
            pm=plugin_manager,
            profile_dir=profile_dir,
            concurrency_group=cg,
        )
        stage_deploy_files(staging_dir, mng_ctx, repo_root)

    manifest_path = staging_dir / "deploy_files_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest == {}
