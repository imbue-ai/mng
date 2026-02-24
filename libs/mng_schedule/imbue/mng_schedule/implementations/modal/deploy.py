import importlib.metadata
import json
import os
import platform
import shlex
import shutil
import sys
import tempfile
from collections.abc import Sequence
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any
from typing import Final
from typing import assert_never

import modal.exception
from loguru import logger
from pydantic import ValidationError

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.imbue_common.logging import log_span
from imbue.imbue_common.pure import pure
from imbue.mng.api.providers import get_provider_instance
from imbue.mng.config.data_types import MngContext
from imbue.mng.primitives import ProviderInstanceName
from imbue.mng.providers.modal.instance import ModalProviderInstance
from imbue.mng_schedule.data_types import MngInstallMode
from imbue.mng_schedule.data_types import ScheduleCreationRecord
from imbue.mng_schedule.data_types import ScheduleTriggerDefinition
from imbue.mng_schedule.data_types import VerifyMode
from imbue.mng_schedule.errors import ScheduleDeployError
from imbue.mng_schedule.implementations.modal.verification import verify_schedule_deployment

_FALLBACK_TIMEZONE: Final[str] = "UTC"

# Default Dockerfile path relative to repo root (symlink to the real Dockerfile)
_DEFAULT_DOCKERFILE_PATH: Final[str] = ".mng/Dockerfile"

# Path prefix on the state volume for schedule records
_SCHEDULE_RECORDS_PREFIX: Final[str] = "/scheduled_functions"


def _forward_output(line: str, is_stdout: bool) -> None:
    stream = sys.stdout if is_stdout else sys.stderr
    stream.write(line)
    stream.flush()


@pure
def get_modal_app_name(trigger_name: str) -> str:
    return f"mng-schedule-{trigger_name}"


def load_modal_provider_instance(
    provider_instance_name: str,
    mng_ctx: MngContext,
) -> ModalProviderInstance:
    """Load a provider instance and verify it is a Modal provider.

    Raises ScheduleDeployError if the provider cannot be loaded or is not a Modal provider.
    """
    try:
        provider = get_provider_instance(ProviderInstanceName(provider_instance_name), mng_ctx)
    except Exception as exc:
        raise ScheduleDeployError(f"Failed to load provider '{provider_instance_name}': {exc}") from exc
    if not isinstance(provider, ModalProviderInstance):
        raise ScheduleDeployError(
            f"Provider '{provider_instance_name}' is not a Modal provider. "
            "Only Modal providers are currently supported for schedules."
        ) from None
    return provider


@pure
def _resolve_timezone_from_paths(
    etc_timezone_path: Path,
    etc_localtime_path: Path,
) -> str:
    """Resolve the IANA timezone name from filesystem paths."""
    if etc_timezone_path.exists():
        name = etc_timezone_path.read_text().strip()
        if name:
            return name

    if etc_localtime_path.is_symlink():
        target = str(etc_localtime_path.resolve())
        if "zoneinfo/" in target:
            return target.split("zoneinfo/")[-1]

    return _FALLBACK_TIMEZONE


def detect_local_timezone() -> str:
    """Detect the user's local IANA timezone name (e.g. 'America/Los_Angeles')."""
    return _resolve_timezone_from_paths(
        etc_timezone_path=Path("/etc/timezone"),
        etc_localtime_path=Path("/etc/localtime"),
    )


def resolve_git_ref(ref: str) -> str:
    """Resolve a git ref (e.g. HEAD, branch name) to a full commit SHA.

    Raises ScheduleDeployError if the ref cannot be resolved.
    """
    with ConcurrencyGroup(name="git-rev-parse") as cg:
        result = cg.run_process_to_completion(
            ["git", "rev-parse", ref],
            is_checked_after=False,
        )
    if result.returncode != 0:
        raise ScheduleDeployError(f"Could not resolve git ref '{ref}': {result.stderr.strip()}") from None
    return result.stdout.strip()


def get_repo_root() -> Path:
    """Find the git repository root directory.

    Raises ScheduleDeployError if not inside a git repository.
    """
    with ConcurrencyGroup(name="git-toplevel") as cg:
        result = cg.run_process_to_completion(
            ["git", "rev-parse", "--show-toplevel"],
            is_checked_after=False,
        )
    if result.returncode != 0:
        raise ScheduleDeployError(
            "Could not find git repository root. Must be run from within a git repository."
        ) from None
    return Path(result.stdout.strip())


def _ensure_modal_environment(environment_name: str) -> None:
    """Ensure a Modal environment exists, creating it if necessary."""
    with ConcurrencyGroup(name="modal-env-create") as cg:
        result = cg.run_process_to_completion(
            ["uv", "run", "modal", "environment", "create", environment_name],
            is_checked_after=False,
        )
    # Exit code 0 = created. Non-zero with "same name" = already exists (OK).
    if result.returncode != 0 and "same name" not in result.stderr:
        raise ScheduleDeployError(
            f"Failed to create Modal environment '{environment_name}': {result.stderr.strip()}"
        ) from None


def package_repo_at_commit(commit_hash: str, dest_dir: Path, repo_root: Path) -> None:
    """Package the repo at a specific commit into a tarball using make_tar_of_repo.sh.

    The script creates <dest_dir>/current.tar.gz containing the repo at the specified commit.
    Raises ScheduleDeployError if packaging fails.
    """
    script_path = repo_root / "scripts" / "make_tar_of_repo.sh"
    if not script_path.exists():
        raise ScheduleDeployError(f"Packaging script not found at {script_path}") from None

    dest_dir.mkdir(parents=True, exist_ok=True)

    with ConcurrencyGroup(name="package-repo") as cg:
        result = cg.run_process_to_completion(
            ["bash", str(script_path), commit_hash, str(dest_dir)],
            is_checked_after=False,
            on_output=_forward_output,
            cwd=repo_root,
        )
    if result.returncode != 0:
        raise ScheduleDeployError(
            f"Failed to package repo at commit {commit_hash}: {(result.stdout + result.stderr).strip()}"
        ) from None


def detect_mng_install_mode() -> MngInstallMode:
    """Detect how mng-schedule is currently installed.

    Returns EDITABLE if the package is installed in editable (development) mode,
    PACKAGE if installed as a normal package, or raises ScheduleDeployError if
    the package is not installed at all.
    """
    try:
        dist = importlib.metadata.distribution("mng-schedule")
    except importlib.metadata.PackageNotFoundError:
        raise ScheduleDeployError("mng-schedule package is not installed. Cannot determine install mode.") from None

    # Check if the package is installed in editable mode by looking for a
    # direct_url.json with "editable": true, which is the standard way PEP 610
    # marks editable installs.
    direct_url_text = dist.read_text("direct_url.json")
    if direct_url_text is not None:
        try:
            direct_url = json.loads(direct_url_text)
            if direct_url.get("dir_info", {}).get("editable", False):
                return MngInstallMode.EDITABLE
        except (json.JSONDecodeError, AttributeError) as exc:
            logger.debug("Could not parse direct_url.json for mng-schedule: {}", exc)

    return MngInstallMode.PACKAGE


def resolve_mng_install_mode(mode: MngInstallMode) -> MngInstallMode:
    """Resolve AUTO mode to a concrete install mode, or pass through others."""
    if mode == MngInstallMode.AUTO:
        resolved = detect_mng_install_mode()
        logger.info("Auto-detected mng install mode: {}", resolved.value.lower())
        return resolved
    return mode


def _get_mng_schedule_source_dir() -> Path:
    """Get the source directory for an editable install of mng-schedule.

    Returns the directory containing pyproject.toml for mng-schedule.
    Raises ScheduleDeployError if it cannot be determined.
    """
    # In editable mode, the source files are at their original location.
    # We can find the package root by walking up from the plugin module file.
    plugin_file = Path(__file__).resolve()
    # __file__ is at: .../libs/mng_schedule/imbue/mng_schedule/implementations/modal/deploy.py
    # We need: .../libs/mng_schedule/
    candidate = plugin_file.parent.parent.parent.parent.parent
    if (candidate / "pyproject.toml").exists():
        return candidate
    raise ScheduleDeployError(f"Could not find mng-schedule source directory (tried {candidate})")


@pure
def build_mng_install_commands(mode: MngInstallMode) -> list[str]:
    """Build Dockerfile RUN commands to install mng in the deployed image.

    Returns an empty list for SKIP mode (mng is already available).
    """
    match mode:
        case MngInstallMode.SKIP:
            return []
        case MngInstallMode.PACKAGE:
            # Install mng and mng-schedule from the configured package index.
            # Uses the uv already present in the base image.
            return [
                "RUN uv pip install --system mng mng-schedule",
            ]
        case MngInstallMode.EDITABLE:
            # The local source is staged under /staging/mng_schedule_src/ by
            # the deploy flow. Install both mng (as a dependency) and
            # mng-schedule from the staged source.
            return [
                "RUN uv pip install --system /staging/mng_schedule_src/",
            ]
        case MngInstallMode.AUTO:
            raise ScheduleDeployError("AUTO mode must be resolved before building install commands")
        case _ as unreachable:
            assert_never(unreachable)


def parse_upload_spec(spec: str) -> tuple[Path, str]:
    """Parse an upload spec in SOURCE:DEST format.

    Raises ValueError if the spec is malformed or the source does not exist.
    """
    if ":" not in spec:
        raise ValueError(f"Upload spec must be in SOURCE:DEST format, got: {spec}")
    source_str, dest = spec.split(":", 1)
    source_path = Path(source_str)
    if not source_path.exists():
        raise ValueError(f"Upload source does not exist: {source_str}")
    if dest.startswith("/"):
        raise ValueError(f"Upload destination must be relative or start with '~', got: {dest}")
    return source_path, dest


def _collect_deploy_files(
    mng_ctx: MngContext,
    repo_root: Path,
    include_user_settings: bool = True,
    include_project_settings: bool = True,
) -> dict[Path, Path | str]:
    """Collect all files for deployment by calling the get_files_for_deploy hook.

    Destination paths must either start with "~" (user home files) or be
    relative paths (project files copied to the image WORKDIR).  Absolute
    paths that do not start with "~" are rejected.
    """
    all_results: list[dict[Path, Path | str]] = mng_ctx.pm.hook.get_files_for_deploy(
        mng_ctx=mng_ctx,
        include_user_settings=include_user_settings,
        include_project_settings=include_project_settings,
        repo_root=repo_root,
    )
    merged: dict[Path, Path | str] = {}
    for result in all_results:
        for dest_path, source in result.items():
            dest_str = str(dest_path)
            if dest_str.startswith("/"):
                raise ScheduleDeployError(
                    f"Deploy file destination path must be relative or start with '~', got: {dest_path}"
                )
            if dest_path in merged:
                logger.warning(
                    "Deploy file collision: {} registered by multiple plugins, overwriting previous value",
                    dest_path,
                )
            merged[dest_path] = source
    return merged


def stage_deploy_files(
    staging_dir: Path,
    mng_ctx: MngContext,
    repo_root: Path,
    include_user_settings: bool = True,
    include_project_settings: bool = True,
    pass_env: Sequence[str] = (),
    env_files: Sequence[Path] = (),
    uploads: Sequence[tuple[Path, str]] = (),
    mng_install_mode: MngInstallMode = MngInstallMode.SKIP,
) -> None:
    """Stage files for deployment into a directory for baking into the Modal image.

    Collects files from all plugins via the get_files_for_deploy hook and stages
    them into a directory structure that mirrors their destination layout:

    - Paths starting with "~" are user home files, placed under "home/" with
      the "~/" prefix stripped (e.g. "~/.claude.json" -> "home/.claude.json").
    - Relative paths (no "~" prefix) are project files, placed under "project/"
      (e.g. "config/settings.toml" -> "project/config/settings.toml").

    These are then baked into their final locations during the image build via
    dockerfile_commands (home/ -> $HOME, project/ -> WORKDIR).

    Also consolidates environment variables from multiple sources into a single
    secrets/.env file, and stages any user-specified uploads.

    Stages:
    - home/: Files destined for the user's home directory
    - project/: Files destined for the project working directory
    - secrets/.env: Consolidated environment variables from all sources
    """
    staging_dir.mkdir(parents=True, exist_ok=True)

    # Collect files from all plugins via the hook
    deploy_files = _collect_deploy_files(
        mng_ctx,
        repo_root,
        include_user_settings=include_user_settings,
        include_project_settings=include_project_settings,
    )

    # Create both staging subdirectories unconditionally
    home_dir = staging_dir / "home"
    home_dir.mkdir()
    project_dir = staging_dir / "project"
    project_dir.mkdir()

    def resolve_staged_path(dest_str: str) -> Path:
        """Resolve a destination string to a staged path under home/ or project/."""
        if dest_str.startswith("~"):
            return home_dir / dest_str.removeprefix("~/")
        return project_dir / dest_str

    for dest_path, source in deploy_files.items():
        staged_path = resolve_staged_path(str(dest_path))
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(source, Path):
            shutil.copy2(source, staged_path)
        else:
            staged_path.write_text(source)

    if deploy_files:
        logger.info("Staged {} deploy files from plugins", len(deploy_files))

    # Stage user-specified uploads
    for source_path, dest in uploads:
        staged_path = resolve_staged_path(str(dest))
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        if source_path.is_dir():
            shutil.copytree(source_path, staged_path, dirs_exist_ok=True)
        else:
            shutil.copy2(source_path, staged_path)
        logger.debug("Staged upload {} -> {}", source_path, dest)

    if uploads:
        logger.info("Staged {} user-specified uploads", len(uploads))

    # Consolidate environment variables from all sources into a single .env file.
    # Precedence (lowest to highest): --env-file < --pass-env
    secrets_dir = staging_dir / "secrets"
    secrets_dir.mkdir()
    _stage_consolidated_env(secrets_dir, pass_env=pass_env, env_files=env_files)

    # For editable installs, stage the mng-schedule source tree so it can be
    # pip-installed inside the deployed image. Only source code and
    # pyproject.toml are needed; skip build artifacts and test caches.
    if mng_install_mode == MngInstallMode.EDITABLE:
        mng_schedule_src = _get_mng_schedule_source_dir()
        staged_src = staging_dir / "mng_schedule_src"
        shutil.copytree(
            mng_schedule_src,
            staged_src,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(
                "__pycache__",
                "*.pyc",
                ".pytest_cache",
                "*.egg-info",
                ".test_output",
                "htmlcov",
            ),
        )
        logger.info("Staged mng-schedule source from {} for editable install", mng_schedule_src)


def _stage_consolidated_env(
    secrets_dir: Path,
    pass_env: Sequence[str] = (),
    env_files: Sequence[Path] = (),
) -> None:
    """Consolidate env vars from multiple sources into secrets/.env.

    Sources are merged in order of increasing precedence:
    1. User-specified --env-file entries (in order)
    2. User-specified --pass-env variables from the current process environment
    """
    env_lines: list[str] = []

    # 1. User-specified env files
    for env_file_path in env_files:
        env_lines.extend(env_file_path.read_text().splitlines())
        logger.info("Including env file {}", env_file_path)

    # 2. Pass-through env vars from current process
    for var_name in pass_env:
        value = os.environ.get(var_name)
        if value is not None:
            env_lines.append(f"{var_name}={value}")
            logger.debug("Passing through env var {}", var_name)
        else:
            logger.warning("Environment variable '{}' not set in current environment, skipping", var_name)

    if env_lines:
        (secrets_dir / ".env").write_text("\n".join(env_lines) + "\n")
        var_count = sum(1 for line in env_lines if line.strip() and not line.strip().startswith("#") and "=" in line)
        logger.info("Staged consolidated env file with {} variable entries", var_count)


@pure
def build_deploy_config(
    app_name: str,
    trigger: ScheduleTriggerDefinition,
    cron_schedule: str,
    cron_timezone: str,
    mng_install_commands: list[str],
) -> dict[str, Any]:
    """Build the deploy configuration dict that gets baked into the Modal image."""
    return {
        "app_name": app_name,
        "trigger": json.loads(trigger.model_dump_json()),
        "cron_schedule": cron_schedule,
        "cron_timezone": cron_timezone,
        "mng_install_commands": mng_install_commands,
    }


def _get_current_mng_git_hash() -> str:
    """Get the git commit hash of the current mng codebase."""
    try:
        return resolve_git_ref("HEAD")
    except ScheduleDeployError:
        logger.warning("Could not determine mng git hash (not in a git repository?)")
        return "unknown"


def _save_schedule_creation_record(
    record: ScheduleCreationRecord,
    provider: ModalProviderInstance,
) -> None:
    """Save a schedule creation record to the provider's state volume."""
    volume = provider.get_state_volume()
    path = f"{_SCHEDULE_RECORDS_PREFIX}/{record.trigger.name}.json"
    data = record.model_dump_json(indent=2).encode("utf-8")
    volume.write_files({path: data})
    logger.debug("Saved schedule creation record to {}", path)


def list_schedule_creation_records(
    provider: ModalProviderInstance,
) -> list[ScheduleCreationRecord]:
    """Read all schedule creation records from the provider's state volume.

    Returns an empty list if no schedules directory exists on the volume.
    """
    volume = provider.get_state_volume()

    try:
        entries = volume.listdir(_SCHEDULE_RECORDS_PREFIX)
    except (modal.exception.NotFoundError, FileNotFoundError):
        return []

    records: list[ScheduleCreationRecord] = []
    for entry in entries:
        if not entry.path.endswith(".json"):
            continue
        file_path = f"{_SCHEDULE_RECORDS_PREFIX}/{entry.path}"
        try:
            data = volume.read_file(file_path)
        except (modal.exception.NotFoundError, FileNotFoundError, OSError) as exc:
            logger.warning("Skipped unreadable schedule record at {}: {}", file_path, exc)
            continue
        try:
            record = ScheduleCreationRecord.model_validate_json(data)
        except (ValidationError, ValueError) as exc:
            logger.warning("Skipped invalid schedule record at {}: {}", file_path, exc)
            continue
        records.append(record)
    return records


@pure
def _build_full_commandline(sys_argv: list[str]) -> str:
    """Reconstruct the full command line from sys.argv with proper shell escaping."""
    return shlex.join(sys_argv)


def deploy_schedule(
    trigger: ScheduleTriggerDefinition,
    mng_ctx: MngContext,
    provider: ModalProviderInstance,
    verify_mode: VerifyMode = VerifyMode.NONE,
    sys_argv: list[str] | None = None,
    include_user_settings: bool = True,
    include_project_settings: bool = True,
    pass_env: Sequence[str] = (),
    env_files: Sequence[Path] = (),
    uploads: Sequence[tuple[Path, str]] = (),
    mng_install_mode: MngInstallMode = MngInstallMode.AUTO,
) -> str:
    """Deploy a scheduled trigger to Modal, optionally verifying it works.

    Full deployment flow:
    1. Find repo root and derive Modal environment name
    2. Resolve mng install mode (auto-detect if needed)
    3. Package repo at the specified commit into a tarball
    4. Stage deploy files (collected from plugins via hook), env vars, and mng source
    5. Write deploy config as a single JSON file
    6. Run modal deploy cron_runner.py with --env for the correct Modal environment
    7. If verify_mode is not NONE, invoke the function once via modal run to verify
    8. Save creation record to the provider's state volume
    9. Return the Modal app name

    Verification must happen inside this function (before the temp directory is
    cleaned up) because modal run requires the same build-time env vars that
    point to local filesystem paths within the temp directory.

    Raises ScheduleDeployError if any step fails.
    """
    repo_root = get_repo_root()
    app_name = get_modal_app_name(trigger.name)
    cron_timezone = detect_local_timezone()
    modal_env_name = provider.environment_name

    # Resolve mng install mode (auto-detect if needed)
    resolved_install_mode = resolve_mng_install_mode(mng_install_mode)
    logger.info("mng install mode: {}", resolved_install_mode.value.lower())

    logger.info("Deploying schedule '{}' (app: {}, env: {})", trigger.name, app_name, modal_env_name)
    logger.info("Using commit {} for code packaging", trigger.git_image_hash)

    # Ensure the Modal environment exists (modal deploy does not auto-create it)
    _ensure_modal_environment(modal_env_name)

    with tempfile.TemporaryDirectory(prefix="mng-schedule-") as tmpdir:
        tmp_path = Path(tmpdir)

        # Package repo into build context
        build_dir = tmp_path / "build"
        with log_span("Packaging repo at commit {}", trigger.git_image_hash):
            package_repo_at_commit(trigger.git_image_hash, build_dir, repo_root)

        tarball = build_dir / "current.tar.gz"
        if not tarball.exists():
            raise ScheduleDeployError(f"Expected tarball at {tarball} after packaging, but it was not found") from None

        # Stage deploy files (collected from plugins via hook)
        staging_dir = tmp_path / "staging"
        with log_span("Staging deploy files"):
            stage_deploy_files(
                staging_dir,
                mng_ctx,
                repo_root,
                include_user_settings=include_user_settings,
                include_project_settings=include_project_settings,
                pass_env=pass_env,
                env_files=env_files,
                uploads=uploads,
                mng_install_mode=resolved_install_mode,
            )

        # Write deploy config as a single JSON file into the staging dir
        mng_install_cmds = build_mng_install_commands(resolved_install_mode)
        deploy_config = build_deploy_config(
            app_name=app_name,
            trigger=trigger,
            cron_schedule=trigger.schedule_cron,
            cron_timezone=cron_timezone,
            mng_install_commands=mng_install_cmds,
        )
        deploy_config_json = json.dumps(deploy_config)
        (staging_dir / "deploy_config.json").write_text(deploy_config_json)

        # Resolve the Dockerfile path (default: .mng/Dockerfile)
        dockerfile_path = repo_root / _DEFAULT_DOCKERFILE_PATH
        if not dockerfile_path.exists():
            raise ScheduleDeployError(
                f"Dockerfile not found at {dockerfile_path}. "
                "Expected a Dockerfile (or symlink) at .mng/Dockerfile in the repo root."
            ) from None

        # Build env vars: deploy config as single JSON + local-only paths for image building
        env = os.environ.copy()
        env["SCHEDULE_DEPLOY_CONFIG"] = deploy_config_json
        env["SCHEDULE_BUILD_CONTEXT_DIR"] = str(build_dir)
        env["SCHEDULE_STAGING_DIR"] = str(staging_dir)
        env["SCHEDULE_DOCKERFILE"] = str(dockerfile_path)

        cron_runner_path = Path(__file__).parent / "cron_runner.py"
        cmd = ["uv", "run", "modal", "deploy", "--env", modal_env_name, str(cron_runner_path)]

        with log_span("Deploying to Modal as app '{}' in env '{}'", app_name, modal_env_name):
            with ConcurrencyGroup(name=f"modal-deploy-{trigger.name}") as cg:
                result = cg.run_process_to_completion(
                    cmd,
                    timeout=600.0,
                    env=env,
                    is_checked_after=False,
                    on_output=_forward_output,
                )
            if result.returncode != 0:
                raise ScheduleDeployError(
                    f"Failed to deploy schedule '{trigger.name}' to Modal "
                    f"(exit code {result.returncode}). See output above for details."
                ) from None

        logger.info("Schedule '{}' deployed to Modal app '{}'", trigger.name, app_name)

        # Post-deploy verification (must happen while temp dir is still alive)
        if verify_mode != VerifyMode.NONE:
            is_finish = verify_mode == VerifyMode.FULL
            with log_span("Verifying deployment of schedule '{}'", trigger.name):
                verify_schedule_deployment(
                    trigger_name=trigger.name,
                    modal_env_name=modal_env_name,
                    is_finish_initial_run=is_finish,
                    env=env,
                    cron_runner_path=cron_runner_path,
                )

    # Save the creation record to the provider's state volume.
    # This is best-effort: the deploy already succeeded, so a failure here
    # should not cause the command to report failure.
    effective_sys_argv = sys_argv if sys_argv is not None else []
    with log_span("Saving schedule creation record"):
        creation_record = ScheduleCreationRecord(
            trigger=trigger,
            full_commandline=_build_full_commandline(effective_sys_argv),
            hostname=platform.node(),
            working_directory=str(Path.cwd()),
            mng_git_hash=_get_current_mng_git_hash(),
            created_at=datetime.now(timezone.utc),
            modal_app_name=app_name,
            modal_environment=modal_env_name,
        )
        try:
            _save_schedule_creation_record(creation_record, provider)
        except (modal.exception.Error, OSError) as exc:
            logger.warning(
                "Schedule '{}' was deployed successfully but failed to save creation record: {}",
                trigger.name,
                exc,
            )

    return app_name
