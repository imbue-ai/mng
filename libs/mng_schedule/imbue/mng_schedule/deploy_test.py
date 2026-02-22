"""Unit tests for deploy.py pure functions."""

from pathlib import Path

from imbue.mng_schedule.deploy import _resolve_timezone_from_paths
from imbue.mng_schedule.deploy import build_deploy_env
from imbue.mng_schedule.deploy import get_modal_app_name


def test_get_modal_app_name() -> None:
    assert get_modal_app_name("my-trigger") == "mng-schedule-my-trigger"
    assert get_modal_app_name("nightly") == "mng-schedule-nightly"


def test_build_deploy_env_returns_all_keys() -> None:
    result = build_deploy_env(
        app_name="test-app",
        trigger_json='{"name": "test"}',
        cron_schedule="0 3 * * *",
        cron_timezone="America/Los_Angeles",
        build_context_dir="/tmp/build",
        staging_dir="/tmp/staging",
        dockerfile="/path/to/Dockerfile",
    )
    assert result == {
        "SCHEDULE_APP_NAME": "test-app",
        "SCHEDULE_TRIGGER_JSON": '{"name": "test"}',
        "SCHEDULE_CRON": "0 3 * * *",
        "SCHEDULE_CRON_TIMEZONE": "America/Los_Angeles",
        "SCHEDULE_BUILD_CONTEXT_DIR": "/tmp/build",
        "SCHEDULE_STAGING_DIR": "/tmp/staging",
        "SCHEDULE_DOCKERFILE": "/path/to/Dockerfile",
    }


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
