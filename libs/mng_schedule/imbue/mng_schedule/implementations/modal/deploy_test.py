"""Unit tests for deploy.py pure functions."""

from pathlib import Path

from imbue.mng_schedule.data_types import ScheduleTriggerDefinition
from imbue.mng_schedule.data_types import ScheduledMngCommand
from imbue.mng_schedule.implementations.modal.deploy import _resolve_timezone_from_paths
from imbue.mng_schedule.implementations.modal.deploy import build_deploy_config
from imbue.mng_schedule.implementations.modal.deploy import get_modal_app_name


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
