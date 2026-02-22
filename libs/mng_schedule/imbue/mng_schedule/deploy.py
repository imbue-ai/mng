import os
import shutil
import sys
from pathlib import Path
from typing import Final

from loguru import logger

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.imbue_common.logging import log_span
from imbue.imbue_common.pure import pure
from imbue.mng.errors import MngError
from imbue.mng_schedule.data_types import ScheduleTriggerDefinition

_FALLBACK_TIMEZONE: Final[str] = "UTC"


class ScheduleDeployError(MngError):
    """Raised when schedule deployment fails."""


def _forward_output(line: str, is_stdout: bool) -> None:
    stream = sys.stdout if is_stdout else sys.stderr
    stream.write(line)
    stream.flush()


@pure
def get_modal_app_name(trigger_name: str) -> str:
    return f"mng-schedule-{trigger_name}"


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
def build_deploy_env(
    app_name: str,
    trigger_json: str,
    cron_schedule: str,
    cron_timezone: str,
) -> dict[str, str]:
    """Build the environment variables needed for deploying the cron runner."""
    return {
        "SCHEDULE_APP_NAME": app_name,
        "SCHEDULE_TRIGGER_JSON": trigger_json,
        "SCHEDULE_CRON": cron_schedule,
        "SCHEDULE_CRON_TIMEZONE": cron_timezone,
    }


def deploy_schedule(trigger: ScheduleTriggerDefinition) -> str:
    """Deploy a scheduled trigger to Modal.

    Full deployment flow:
    1. Resolve commit hash and find repo root
    2. Package repo at that commit into a tarball
    3. Stage local files (user config, secrets)
    4. Build deploy env vars
    5. Run modal deploy cron_runner.py
    6. Return the Modal app name

    Raises ScheduleDeployError if any step fails.
    """
    import tempfile

    repo_root = get_repo_root()
    app_name = get_modal_app_name(trigger.name)
    cron_timezone = detect_local_timezone()

    logger.info("Deploying schedule '{}' (app: {})", trigger.name, app_name)
    logger.info("Using commit {} for code packaging", trigger.git_image_hash)

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

        # Write trigger config for the cron runner
        trigger_json = trigger.model_dump_json()
        (staging_dir / "trigger.json").write_text(trigger_json)

        # Build deploy env vars
        deploy_env_vars = build_deploy_env(
            app_name=app_name,
            trigger_json=trigger_json,
            cron_schedule=trigger.schedule_cron,
            cron_timezone=cron_timezone,
        )

        # Also tell the cron_runner where the build context and staging are
        deploy_env_vars["SCHEDULE_BUILD_CONTEXT_DIR"] = str(build_dir)
        deploy_env_vars["SCHEDULE_STAGING_DIR"] = str(staging_dir)
        deploy_env_vars["SCHEDULE_DOCKERFILE"] = str(
            repo_root / "libs" / "mng" / "imbue" / "mng" / "resources" / "Dockerfile"
        )

        env = {**os.environ, **deploy_env_vars}

        cron_runner_path = Path(__file__).parent / "cron_runner.py"
        cmd = ["uv", "run", "modal", "deploy", str(cron_runner_path)]

        with log_span("Deploying to Modal as app '{}'", app_name):
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
