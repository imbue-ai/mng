import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any
from typing import Final

from loguru import logger

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.imbue_common.logging import log_span
from imbue.imbue_common.pure import pure
from imbue.mng.config.data_types import MngContext
from imbue.mng.errors import MngError
from imbue.mng_schedule.data_types import ScheduleTriggerDefinition

_FALLBACK_TIMEZONE: Final[str] = "UTC"

# Default Dockerfile path relative to repo root (symlink to the real Dockerfile)
_DEFAULT_DOCKERFILE_PATH: Final[str] = ".mng/Dockerfile"


class ScheduleDeployError(MngError):
    """Raised when schedule deployment fails."""


def _forward_output(line: str, is_stdout: bool) -> None:
    stream = sys.stdout if is_stdout else sys.stderr
    stream.write(line)
    stream.flush()


@pure
def get_modal_app_name(trigger_name: str) -> str:
    return f"mng-schedule-{trigger_name}"


def get_modal_environment_name(mng_ctx: MngContext) -> str:
    """Derive the Modal environment name from the mng context.

    This matches the convention used by the Modal provider backend:
    environment_name = {prefix}{user_id}
    """
    prefix = mng_ctx.config.prefix
    user_id = mng_ctx.get_profile_user_id()
    environment_name = f"{prefix}{user_id}"
    # Modal has a 64-char limit on environment names
    if len(environment_name) > 64:
        environment_name = environment_name[:64]
    return environment_name


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


def stage_local_files(staging_dir: Path, repo_root: Path) -> None:
    """Stage local config files and secrets into a directory for baking into the Modal image.

    Stages:
    - ~/.claude.json (if exists)
    - ~/.claude/settings.json (if exists)
    - ~/.mng/config.toml (if exists)
    - ~/.mng/profiles/ (if exists)
    - .mng/dev/secrets/.env (if exists, from repo root)
    """
    staging_dir.mkdir(parents=True, exist_ok=True)
    user_home = Path.home()

    # User config files
    user_cfg_dir = staging_dir / "user_config"
    user_cfg_dir.mkdir()

    claude_json = user_home / ".claude.json"
    if claude_json.exists():
        shutil.copy2(claude_json, user_cfg_dir / "claude.json")

    claude_settings = user_home / ".claude" / "settings.json"
    if claude_settings.exists():
        (user_cfg_dir / "claude_dir").mkdir()
        shutil.copy2(claude_settings, user_cfg_dir / "claude_dir" / "settings.json")

    mng_config = user_home / ".mng" / "config.toml"
    if mng_config.exists():
        (user_cfg_dir / "mng").mkdir()
        shutil.copy2(mng_config, user_cfg_dir / "mng" / "config.toml")

    mng_profiles = user_home / ".mng" / "profiles"
    if mng_profiles.is_dir():
        (user_cfg_dir / "mng").mkdir(exist_ok=True)
        shutil.copytree(mng_profiles, user_cfg_dir / "mng" / "profiles", dirs_exist_ok=True)

    # Secrets env file
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


def deploy_schedule(trigger: ScheduleTriggerDefinition, mng_ctx: MngContext) -> str:
    """Deploy a scheduled trigger to Modal.

    Full deployment flow:
    1. Find repo root and derive Modal environment name
    2. Package repo at the specified commit into a tarball
    3. Stage local files (user config, secrets)
    4. Write deploy config as a single JSON file
    5. Run modal deploy cron_runner.py with --env for the correct Modal environment
    6. Return the Modal app name

    Raises ScheduleDeployError if any step fails.
    """
    repo_root = get_repo_root()
    app_name = get_modal_app_name(trigger.name)
    cron_timezone = detect_local_timezone()
    modal_env_name = get_modal_environment_name(mng_ctx)

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

        # Stage local files
        staging_dir = tmp_path / "staging"
        with log_span("Staging local files"):
            stage_local_files(staging_dir, repo_root)

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
    return app_name
