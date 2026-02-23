"""Unit tests for deploy.py and verification.py pure functions."""

from collections.abc import Callable
from pathlib import Path

import pluggy
import pytest

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mng import hookimpl
from imbue.mng.config.data_types import MngConfig
from imbue.mng.config.data_types import MngContext
from imbue.mng_schedule.data_types import ScheduleTriggerDefinition
from imbue.mng_schedule.data_types import ScheduledMngCommand
from imbue.mng_schedule.errors import ScheduleDeployError
from imbue.mng_schedule.implementations.modal.deploy import _build_full_commandline
from imbue.mng_schedule.implementations.modal.deploy import _collect_deploy_files
from imbue.mng_schedule.implementations.modal.deploy import _resolve_timezone_from_paths
from imbue.mng_schedule.implementations.modal.deploy import build_deploy_config
from imbue.mng_schedule.implementations.modal.deploy import get_modal_app_name
from imbue.mng_schedule.implementations.modal.deploy import stage_deploy_files
from imbue.mng_schedule.implementations.modal.verification import build_modal_run_command


def test_get_modal_app_name() -> None:
    assert get_modal_app_name("my-trigger") == "mng-schedule-my-trigger"
    assert get_modal_app_name("nightly") == "mng-schedule-nightly"


def test_build_modal_run_command() -> None:
    cmd = build_modal_run_command(
        cron_runner_path=Path("/deploy/cron_runner.py"),
        modal_env_name="test-env",
    )
    assert cmd == ["uv", "run", "modal", "run", "--env", "test-env", "/deploy/cron_runner.py"]


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


def test_build_full_commandline_joins_argv_with_spaces() -> None:
    argv = ["uv", "run", "mng", "schedule", "add", "--command", "create"]
    result = _build_full_commandline(argv)
    assert result == "uv run mng schedule add --command create"


def test_build_full_commandline_handles_empty_argv() -> None:
    result = _build_full_commandline([])
    assert result == ""


def test_build_full_commandline_handles_single_element() -> None:
    result = _build_full_commandline(["mng"])
    assert result == "mng"


def test_build_full_commandline_shell_escapes_spaces_in_arguments() -> None:
    argv = ["mng", "schedule", "add", "--args", "hello world"]
    result = _build_full_commandline(argv)
    assert result == "mng schedule add --args 'hello world'"


# =============================================================================
# Shared test helpers
# =============================================================================


def _make_test_mng_ctx(
    plugin_manager: pluggy.PluginManager,
    tmp_path: Path,
) -> MngContext:
    """Create a MngContext for testing with the given plugin manager.

    Uses a bare ConcurrencyGroup (not as a context manager) since these tests
    only exercise hook calls, not process execution.
    """
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir(exist_ok=True)
    config = MngConfig(default_host_dir=tmp_path / ".mng_host")
    return MngContext(
        config=config,
        pm=plugin_manager,
        profile_dir=profile_dir,
        concurrency_group=ConcurrencyGroup(name="test"),
    )


# =============================================================================
# stage_deploy_files Tests
# =============================================================================


@pytest.fixture()
def run_staging(
    tmp_path: Path,
    plugin_manager: pluggy.PluginManager,
) -> Callable[[Path | None], Path]:
    """Return a callable that runs stage_deploy_files and returns the staging dir.

    Accepts an optional repo_root (creates an empty one if not provided).
    The caller should create any files they want staged BEFORE calling this.
    """

    def _run(repo_root: Path | None = None) -> Path:
        if repo_root is None:
            repo_root = tmp_path / "repo"
            repo_root.mkdir(exist_ok=True)
        staging_dir = tmp_path / "staging"
        mng_ctx = _make_test_mng_ctx(plugin_manager, tmp_path)
        stage_deploy_files(staging_dir, mng_ctx, repo_root)
        return staging_dir

    return _run


def test_stage_deploy_files_creates_home_directory_structure(
    run_staging: Callable[[Path | None], Path],
) -> None:
    """stage_deploy_files should stage files into home/ mirroring their destination paths."""
    claude_json = Path.home() / ".claude.json"
    claude_json.write_text('{"staged": true}')

    staging_dir = run_staging(None)

    # Files should be staged under home/ with their natural paths
    staged_file = staging_dir / "home" / ".claude.json"
    assert staged_file.exists()
    assert staged_file.read_text() == '{"staged": true}'


def test_stage_deploy_files_stages_multiple_home_files(
    run_staging: Callable[[Path | None], Path],
) -> None:
    """stage_deploy_files stages multiple home files preserving directory structure."""
    claude_json = Path.home() / ".claude.json"
    claude_json.write_text('{"roundtrip": true}')
    mng_dir = Path.home() / ".mng"
    mng_dir.mkdir(parents=True, exist_ok=True)
    mng_config = mng_dir / "config.toml"
    mng_config.write_text("[test]\nroundtrip = true\n")

    staging_dir = run_staging(None)

    # Both files should be staged under home/ with their natural paths
    staged_claude = staging_dir / "home" / ".claude.json"
    assert staged_claude.exists()
    assert staged_claude.read_text() == '{"roundtrip": true}'
    staged_config = staging_dir / "home" / ".mng" / "config.toml"
    assert staged_config.exists()
    assert staged_config.read_text() == "[test]\nroundtrip = true\n"


def test_stage_deploy_files_stages_secrets_env(
    tmp_path: Path,
    run_staging: Callable[[Path | None], Path],
) -> None:
    """stage_deploy_files should stage the secrets .env file when present."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir(exist_ok=True)
    secrets_dir = repo_root / ".mng" / "dev" / "secrets"
    secrets_dir.mkdir(parents=True)
    (secrets_dir / ".env").write_text("GH_TOKEN=test123")

    staging_dir = run_staging(repo_root)

    staged_secrets = staging_dir / "secrets" / ".env"
    assert staged_secrets.exists()
    assert staged_secrets.read_text() == "GH_TOKEN=test123"


def test_stage_deploy_files_creates_empty_subdirs_when_no_files(
    run_staging: Callable[[Path | None], Path],
) -> None:
    """stage_deploy_files should create empty home/ and project/ dirs when no plugin returns files."""
    staging_dir = run_staging(None)

    home_dir = staging_dir / "home"
    assert home_dir.exists()
    assert not any(home_dir.iterdir())

    project_dir = staging_dir / "project"
    assert project_dir.exists()
    assert not any(project_dir.iterdir())


def test_stage_deploy_files_stages_project_files(
    tmp_path: Path,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """stage_deploy_files should stage relative paths under project/."""

    class _ProjectFilePlugin:
        @staticmethod
        @hookimpl
        def get_files_for_deploy(mng_ctx: MngContext) -> dict[Path, Path | str]:
            return {Path("config/settings.toml"): "[settings]\nkey = 1\n"}

    plugin_manager.register(_ProjectFilePlugin())
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    staging_dir = tmp_path / "staging"
    mng_ctx = _make_test_mng_ctx(plugin_manager, tmp_path)
    stage_deploy_files(staging_dir, mng_ctx, repo_root)

    staged_file = staging_dir / "project" / "config" / "settings.toml"
    assert staged_file.exists()
    assert staged_file.read_text() == "[settings]\nkey = 1\n"

    # home/ should be empty since no home files were registered
    assert not any((staging_dir / "home").iterdir())


# =============================================================================
# _collect_deploy_files validation Tests
# =============================================================================


def _make_mng_ctx_with_hook_returning(
    plugin_manager: pluggy.PluginManager,
    tmp_path: Path,
    files: dict[Path, Path | str],
) -> MngContext:
    """Create a MngContext with an extra plugin that returns the given files."""

    class _TestPlugin:
        @staticmethod
        @hookimpl
        def get_files_for_deploy(mng_ctx: MngContext) -> dict[Path, Path | str]:
            return files

    plugin_manager.register(_TestPlugin())
    return _make_test_mng_ctx(plugin_manager, tmp_path)


def test_collect_deploy_files_accepts_relative_path(
    plugin_manager: pluggy.PluginManager,
    tmp_path: Path,
) -> None:
    """_collect_deploy_files should accept relative paths as project files."""
    mng_ctx = _make_mng_ctx_with_hook_returning(
        plugin_manager,
        tmp_path,
        {Path("relative/config.toml"): "content"},
    )

    result = _collect_deploy_files(mng_ctx)
    assert Path("relative/config.toml") in result


def test_collect_deploy_files_rejects_absolute_path(
    plugin_manager: pluggy.PluginManager,
    tmp_path: Path,
) -> None:
    """_collect_deploy_files should raise ScheduleDeployError for absolute paths."""
    mng_ctx = _make_mng_ctx_with_hook_returning(
        plugin_manager,
        tmp_path,
        {Path("/etc/config.toml"): "content"},
    )

    with pytest.raises(ScheduleDeployError, match="must be relative or start with '~'"):
        _collect_deploy_files(mng_ctx)


def test_collect_deploy_files_resolves_collision(
    plugin_manager: pluggy.PluginManager,
    tmp_path: Path,
) -> None:
    """_collect_deploy_files should resolve collisions when two plugins register the same path."""

    class _PluginA:
        @staticmethod
        @hookimpl
        def get_files_for_deploy(mng_ctx: MngContext) -> dict[Path, Path | str]:
            return {Path("~/.config/test.toml"): "content-a"}

    class _PluginB:
        @staticmethod
        @hookimpl
        def get_files_for_deploy(mng_ctx: MngContext) -> dict[Path, Path | str]:
            return {Path("~/.config/test.toml"): "content-b"}

    plugin_manager.register(_PluginA())
    plugin_manager.register(_PluginB())

    mng_ctx = _make_test_mng_ctx(plugin_manager, tmp_path)
    result = _collect_deploy_files(mng_ctx)

    # Should still succeed, with one entry (last one wins)
    assert Path("~/.config/test.toml") in result
