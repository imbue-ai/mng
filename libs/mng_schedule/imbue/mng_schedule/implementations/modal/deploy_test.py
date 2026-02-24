"""Unit tests for deploy.py and verification.py pure functions."""

from collections.abc import Callable
from pathlib import Path

import pluggy
import pytest

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mng import hookimpl
from imbue.mng.config.data_types import MngConfig
from imbue.mng.config.data_types import MngContext
from imbue.mng_schedule.data_types import MngInstallMode
from imbue.mng_schedule.data_types import ScheduleTriggerDefinition
from imbue.mng_schedule.data_types import ScheduledMngCommand
from imbue.mng_schedule.errors import ScheduleDeployError
from imbue.mng_schedule.implementations.modal.deploy import _build_full_commandline
from imbue.mng_schedule.implementations.modal.deploy import _collect_deploy_files
from imbue.mng_schedule.implementations.modal.deploy import _resolve_timezone_from_paths
from imbue.mng_schedule.implementations.modal.deploy import _stage_consolidated_env
from imbue.mng_schedule.implementations.modal.deploy import build_deploy_config
from imbue.mng_schedule.implementations.modal.deploy import build_mng_install_commands
from imbue.mng_schedule.implementations.modal.deploy import detect_mng_install_mode
from imbue.mng_schedule.implementations.modal.deploy import get_modal_app_name
from imbue.mng_schedule.implementations.modal.deploy import parse_upload_spec
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


def test_stage_deploy_files_creates_secrets_dir(
    run_staging: Callable[[Path | None], Path],
) -> None:
    """stage_deploy_files should always create the secrets/ directory."""
    staging_dir = run_staging(None)

    secrets_dir = staging_dir / "secrets"
    assert secrets_dir.exists()
    assert secrets_dir.is_dir()


def test_stage_deploy_files_creates_empty_subdirs_when_no_files(
    tmp_path: Path,
    plugin_manager: pluggy.PluginManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """stage_deploy_files should create empty home/ and project/ dirs when no plugin returns files."""
    # Use a clean temp CWD so that plugins don't pick up any existing project files
    clean_project = tmp_path / "empty_project"
    clean_project.mkdir()
    monkeypatch.chdir(clean_project)

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    staging_dir = tmp_path / "staging"
    mng_ctx = _make_test_mng_ctx(plugin_manager, tmp_path)
    stage_deploy_files(staging_dir, mng_ctx, repo_root)

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


# =============================================================================
# parse_upload_spec Tests
# =============================================================================


def test_parse_upload_spec_valid_file(tmp_path: Path) -> None:
    """parse_upload_spec should parse a valid SOURCE:DEST spec with an existing file."""
    source = tmp_path / "myfile.txt"
    source.write_text("content")

    result = parse_upload_spec(f"{source}:~/.config/myfile.txt")
    assert result == (source, "~/.config/myfile.txt")


def test_parse_upload_spec_valid_directory(tmp_path: Path) -> None:
    """parse_upload_spec should parse a valid SOURCE:DEST spec with an existing directory."""
    source_dir = tmp_path / "mydir"
    source_dir.mkdir()

    result = parse_upload_spec(f"{source_dir}:config/")
    assert result == (source_dir, "config/")


def test_parse_upload_spec_rejects_missing_colon() -> None:
    """parse_upload_spec should reject specs without a colon."""
    with pytest.raises(ValueError, match="SOURCE:DEST"):
        parse_upload_spec("/some/path")


def test_parse_upload_spec_rejects_nonexistent_source() -> None:
    """parse_upload_spec should reject specs where the source does not exist."""
    with pytest.raises(ValueError, match="does not exist"):
        parse_upload_spec("/nonexistent/file:dest")


def test_parse_upload_spec_rejects_absolute_dest(tmp_path: Path) -> None:
    """parse_upload_spec should reject absolute destinations."""
    source = tmp_path / "exists.txt"
    source.write_text("content")

    with pytest.raises(ValueError, match="must be relative or start with '~'"):
        parse_upload_spec(f"{source}:/absolute/path")


# =============================================================================
# _stage_consolidated_env Tests
# =============================================================================


def test_stage_consolidated_env_includes_env_files(tmp_path: Path) -> None:
    """_stage_consolidated_env should include vars from --env-file."""
    env_file = tmp_path / "custom.env"
    env_file.write_text("CUSTOM_VAR=hello\n")

    output_dir = tmp_path / "secrets"
    output_dir.mkdir()
    _stage_consolidated_env(output_dir, env_files=[env_file])

    result = (output_dir / ".env").read_text()
    assert "CUSTOM_VAR=hello" in result


def test_stage_consolidated_env_includes_pass_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_stage_consolidated_env should include vars from --pass-env."""
    monkeypatch.setenv("MY_PASS_VAR", "passed_value")

    output_dir = tmp_path / "secrets"
    output_dir.mkdir()
    _stage_consolidated_env(output_dir, pass_env=["MY_PASS_VAR"])

    result = (output_dir / ".env").read_text()
    assert "MY_PASS_VAR=passed_value" in result


def test_stage_consolidated_env_merges_env_files_and_pass_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_stage_consolidated_env should merge env files and pass-env vars."""
    env_file = tmp_path / "extra.env"
    env_file.write_text("FILE_KEY=from_file\n")

    monkeypatch.setenv("SHELL_KEY", "from_shell")

    output_dir = tmp_path / "secrets"
    output_dir.mkdir()
    _stage_consolidated_env(
        output_dir,
        pass_env=["SHELL_KEY"],
        env_files=[env_file],
    )

    result = (output_dir / ".env").read_text()
    assert "FILE_KEY=from_file" in result
    assert "SHELL_KEY=from_shell" in result


def test_stage_consolidated_env_skips_missing_pass_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_stage_consolidated_env should skip pass-env vars not in the environment."""
    monkeypatch.delenv("NONEXISTENT_VAR", raising=False)

    output_dir = tmp_path / "secrets"
    output_dir.mkdir()
    _stage_consolidated_env(output_dir, pass_env=["NONEXISTENT_VAR"])

    # No .env file should be created since there are no entries
    assert not (output_dir / ".env").exists()


def test_stage_consolidated_env_creates_no_file_when_empty(tmp_path: Path) -> None:
    """_stage_consolidated_env should not create .env when no env vars are available."""
    output_dir = tmp_path / "secrets"
    output_dir.mkdir()
    _stage_consolidated_env(output_dir)

    assert not (output_dir / ".env").exists()


# =============================================================================
# stage_deploy_files with uploads Tests
# =============================================================================


def test_stage_deploy_files_stages_upload_file(
    tmp_path: Path,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """stage_deploy_files should stage uploaded files to the correct destination."""
    source_file = tmp_path / "local_config.toml"
    source_file.write_text("[config]\nkey = true\n")

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    staging_dir = tmp_path / "staging"
    mng_ctx = _make_test_mng_ctx(plugin_manager, tmp_path)

    stage_deploy_files(
        staging_dir,
        mng_ctx,
        repo_root,
        uploads=[(source_file, "~/.config/myapp.toml")],
    )

    staged = staging_dir / "home" / ".config" / "myapp.toml"
    assert staged.exists()
    assert staged.read_text() == "[config]\nkey = true\n"


def test_stage_deploy_files_stages_upload_directory(
    tmp_path: Path,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """stage_deploy_files should stage uploaded directories recursively."""
    source_dir = tmp_path / "my_configs"
    source_dir.mkdir()
    (source_dir / "a.txt").write_text("file-a")
    sub_dir = source_dir / "sub"
    sub_dir.mkdir()
    (sub_dir / "b.txt").write_text("file-b")

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    staging_dir = tmp_path / "staging"
    mng_ctx = _make_test_mng_ctx(plugin_manager, tmp_path)

    stage_deploy_files(
        staging_dir,
        mng_ctx,
        repo_root,
        uploads=[(source_dir, "configs")],
    )

    # Relative dest should go under project/
    assert (staging_dir / "project" / "configs" / "a.txt").read_text() == "file-a"
    assert (staging_dir / "project" / "configs" / "sub" / "b.txt").read_text() == "file-b"


def test_stage_deploy_files_with_pass_env(
    tmp_path: Path,
    plugin_manager: pluggy.PluginManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """stage_deploy_files should include --pass-env vars in the consolidated env file."""
    monkeypatch.setenv("TEST_API_KEY", "sk-test-123")

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    staging_dir = tmp_path / "staging"
    mng_ctx = _make_test_mng_ctx(plugin_manager, tmp_path)

    stage_deploy_files(
        staging_dir,
        mng_ctx,
        repo_root,
        pass_env=["TEST_API_KEY"],
    )

    staged_env = staging_dir / "secrets" / ".env"
    assert staged_env.exists()
    assert "TEST_API_KEY=sk-test-123" in staged_env.read_text()


def test_stage_deploy_files_with_exclude_user_settings(
    tmp_path: Path,
    plugin_manager: pluggy.PluginManager,
) -> None:
    """stage_deploy_files with include_user_settings=False should skip home dir files."""
    # Create a home file that would normally be included
    mng_dir = Path.home() / ".mng"
    mng_dir.mkdir(parents=True, exist_ok=True)
    mng_config = mng_dir / "config.toml"
    mng_config.write_text("[test]\nvalue = 1\n")

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    staging_dir = tmp_path / "staging"
    mng_ctx = _make_test_mng_ctx(plugin_manager, tmp_path)

    stage_deploy_files(
        staging_dir,
        mng_ctx,
        repo_root,
        include_user_settings=False,
    )

    # home/ should be empty because we excluded user settings
    assert not any((staging_dir / "home").iterdir())


# =============================================================================
# mng install mode Tests
# =============================================================================


def test_build_mng_install_commands_skip() -> None:
    """build_mng_install_commands returns empty list for SKIP mode."""
    result = build_mng_install_commands(MngInstallMode.SKIP)
    assert result == []


def test_build_mng_install_commands_package() -> None:
    """build_mng_install_commands returns pip install from PyPI for PACKAGE mode."""
    result = build_mng_install_commands(MngInstallMode.PACKAGE)
    assert len(result) == 1
    assert "uv pip install --system mng mng-schedule" in result[0]


def test_build_mng_install_commands_editable() -> None:
    """build_mng_install_commands returns pip install from local source for EDITABLE mode."""
    result = build_mng_install_commands(MngInstallMode.EDITABLE)
    assert len(result) == 1
    assert "/staging/mng_schedule_src/" in result[0]


def test_detect_mng_install_mode_returns_valid_mode() -> None:
    """detect_mng_install_mode should return either PACKAGE or EDITABLE."""
    result = detect_mng_install_mode()
    assert result in (MngInstallMode.PACKAGE, MngInstallMode.EDITABLE)
