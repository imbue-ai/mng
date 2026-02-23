import json
import os
import platform
import shlex
import shutil
import sys
import tempfile
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any
from typing import Final

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


def _collect_deploy_files(mng_ctx: MngContext) -> dict[Path, Path | str]:
    """Collect all files for deployment by calling the get_files_for_deploy hook."""
    all_results: list[dict[Path, Path | str]] = mng_ctx.pm.hook.get_files_for_deploy(mng_ctx=mng_ctx)
    merged: dict[Path, Path | str] = {}
    for result in all_results:
        for dest_path, source in result.items():
            if not str(dest_path).startswith("~"):
                raise ScheduleDeployError(f"Deploy file destination path must start with '~', got: {dest_path}")
            if dest_path in merged:
                logger.warning(
                    "Deploy file collision: {} registered by multiple plugins, overwriting previous value",
                    dest_path,
                )
            merged[dest_path] = source
    return merged


def stage_deploy_files(staging_dir: Path, mng_ctx: MngContext, repo_root: Path) -> None:
    """Stage files for deployment into a directory for baking into the Modal image.

    Collects files from all plugins via the get_files_for_deploy hook and stages
    them into a directory structure that mirrors their destination layout. All
    destination paths start with "~", so they are placed under a "home/"
    subdirectory with the "~/" prefix stripped (e.g. "~/.claude.json" becomes
    "home/.claude.json"). Also stages the secrets .env file if present.

    Stages:
    - home/: Files destined for the user's home directory, mirroring their paths
    - secrets/.env (if exists, from repo root)
    """
    staging_dir.mkdir(parents=True, exist_ok=True)

    # Collect files from all plugins via the hook
    deploy_files = _collect_deploy_files(mng_ctx)

    # Stage files into home/ with their natural path structure
    home_dir = staging_dir / "home"
    home_dir.mkdir()

    for dest_path, source in deploy_files.items():
        # Strip the "~/" prefix to get the relative path within home
        relative_path = str(dest_path).removeprefix("~/")
        staged_path = home_dir / relative_path
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(source, Path):
            shutil.copy2(source, staged_path)
        else:
            staged_path.write_text(source)

    if deploy_files:
        logger.info("Staged {} deploy files from plugins", len(deploy_files))

    # Secrets env file (project-specific, not from hook)
    secrets_dir = staging_dir / "secrets"
    secrets_dir.mkdir()
    secrets_env = repo_root / ".mng" / "dev" / "secrets" / ".env"
    if secrets_env.exists():
        shutil.copy2(secrets_env, secrets_dir / ".env")
        logger.info("Staged secrets from {}", secrets_env)
    else:
        logger.warning("No secrets file found at {}; agents may not have required API keys", secrets_env)


@pure
def build_deploy_config(
    app_name: str,
    trigger: ScheduleTriggerDefinition,
    cron_schedule: str,
    cron_timezone: str,
) -> dict[str, Any]:
    """Build the deploy configuration dict that gets baked into the Modal image."""
    return {
        "app_name": app_name,
        "trigger": json.loads(trigger.model_dump_json()),
        "cron_schedule": cron_schedule,
        "cron_timezone": cron_timezone,
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
) -> str:
    """Deploy a scheduled trigger to Modal, optionally verifying it works.

    Full deployment flow:
    1. Find repo root and derive Modal environment name
    2. Package repo at the specified commit into a tarball
    3. Stage deploy files (collected from plugins via hook) and secrets
    4. Write deploy config as a single JSON file
    5. Run modal deploy cron_runner.py with --env for the correct Modal environment
    6. If verify_mode is not NONE, invoke the function once via modal run to verify
    7. Save creation record to the provider's state volume
    8. Return the Modal app name

    Verification must happen inside this function (before the temp directory is
    cleaned up) because modal run requires the same build-time env vars that
    point to local filesystem paths within the temp directory.

    Raises ScheduleDeployError if any step fails.
    """
    repo_root = get_repo_root()
    app_name = get_modal_app_name(trigger.name)
    cron_timezone = detect_local_timezone()
    modal_env_name = provider.environment_name

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
            stage_deploy_files(staging_dir, mng_ctx, repo_root)

        # Write deploy config as a single JSON file into the staging dir
        deploy_config = build_deploy_config(
            app_name=app_name,
            trigger=trigger,
            cron_schedule=trigger.schedule_cron,
            cron_timezone=cron_timezone,
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
