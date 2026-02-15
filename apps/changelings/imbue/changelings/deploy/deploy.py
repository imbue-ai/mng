import json
import os
import sys
from collections.abc import Mapping
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from loguru import logger

from imbue.changelings.data_types import ChangelingDefinition
from imbue.changelings.errors import ChangelingDeployError
from imbue.changelings.mngr_commands import build_mngr_create_command
from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.imbue_common.logging import log_span
from imbue.imbue_common.pure import pure

_FALLBACK_TIMEZONE: Final[str] = "UTC"

AGENT_POLL_TIMEOUT_SECONDS: float = 900.0
AGENT_POLL_INTERVAL_SECONDS: float = 10.0


@pure
def get_modal_app_name(changeling_name: str) -> str:
    """Generate the Modal app name for a changeling.

    Each changeling gets its own Modal app so that it can be managed
    independently (stopped, redeployed, etc.).
    """
    return f"changeling-{changeling_name}"


@pure
def get_modal_secret_name(changeling_name: str) -> str:
    """Generate the Modal secret name for a changeling.

    The secret stores API keys and tokens needed by the changeling at runtime.
    """
    return f"changeling-{changeling_name}-secrets"


@pure
def get_modal_volume_name(changeling_name: str) -> str:
    """Generate the Modal volume name for a changeling.

    The volume persists the target repo across runs of the same changeling.
    """
    return f"changeling-{changeling_name}-vol"


@pure
def _resolve_timezone_from_paths(
    etc_timezone_path: Path,
    etc_localtime_path: Path,
) -> str:
    """Resolve the IANA timezone name from filesystem paths.

    Checks etc_timezone_path first (Debian/Ubuntu convention), then falls back
    to reading the etc_localtime_path symlink target. Returns 'UTC' if the
    timezone cannot be determined from either source.
    """
    # Try /etc/timezone (Debian/Ubuntu)
    if etc_timezone_path.exists():
        name = etc_timezone_path.read_text().strip()
        if name:
            return name

    # Try /etc/localtime symlink (most Linux distros, macOS)
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


@pure
def build_deploy_env(
    app_name: str,
    config_json: str,
    cron_schedule: str,
    secret_name: str,
    imbue_repo_url: str,
    imbue_commit_hash: str,
    volume_name: str,
    cron_timezone: str,
) -> dict[str, str]:
    """Build the environment variables needed for deploying the cron runner.

    These variables are read by cron_runner.py at deploy time and baked into the
    Modal image so the cron function has access to its configuration at runtime.

    The imbue_repo_url and imbue_commit_hash identify the monorepo containing the
    changeling/mngr tooling. This is distinct from the target repo (the repo the
    changeling operates on, which is specified in the changeling config).
    """
    return {
        "CHANGELING_MODAL_APP_NAME": app_name,
        "CHANGELING_CONFIG_JSON": config_json,
        "CHANGELING_CRON_SCHEDULE": cron_schedule,
        "CHANGELING_SECRET_NAME": secret_name,
        "CHANGELING_IMBUE_REPO_URL": imbue_repo_url,
        "CHANGELING_IMBUE_COMMIT_HASH": imbue_commit_hash,
        "CHANGELING_VOLUME_NAME": volume_name,
        "CHANGELING_CRON_TIMEZONE": cron_timezone,
    }


@pure
def build_modal_deploy_command(
    cron_runner_path: Path,
    environment_name: str | None,
) -> list[str]:
    """Build the modal deploy CLI command."""
    cmd = ["uv", "run", "modal", "deploy"]
    if environment_name:
        cmd.extend(["--env", environment_name])
    cmd.append(str(cron_runner_path))
    return cmd


@pure
def build_modal_run_command(
    cron_runner_path: Path,
    environment_name: str | None,
) -> list[str]:
    """Build the modal run CLI command for invoking the deployed function once."""
    cmd = ["uv", "run", "modal", "run"]
    if environment_name:
        cmd.extend(["--env", environment_name])
    cmd.append(str(cron_runner_path))
    return cmd


@pure
def build_modal_secret_command(
    secret_name: str,
    secret_values: Mapping[str, str],
    environment_name: str | None,
) -> list[str]:
    """Build the modal secret create CLI command.

    The --force flag ensures the secret is created or updated if it already exists.
    """
    cmd = ["uv", "run", "modal", "secret", "create", secret_name]
    for key, value in secret_values.items():
        cmd.append(f"{key}={value}")
    cmd.append("--force")
    if environment_name:
        cmd.extend(["--env", environment_name])
    return cmd


@pure
def collect_secret_values(
    secret_names: Sequence[str],
    env: Mapping[str, str],
) -> dict[str, str]:
    """Collect secret values from the given environment mapping.

    Returns a dict of secret_name -> value for secrets that exist in the
    environment. Secrets not found are silently skipped.
    """
    return {name: env[name] for name in secret_names if name in env}


@pure
def serialize_changeling_config(changeling: ChangelingDefinition) -> str:
    """Serialize a changeling definition to JSON for embedding in the Modal image."""
    return changeling.model_dump_json()


@pure
def parse_agent_name_from_list_json(
    json_output: str,
    changeling_name: str,
) -> str | None:
    """Parse mngr list JSON output to find an agent created by the given changeling.

    Returns the agent name if found, None otherwise.
    """
    try:
        data = json.loads(json_output)
        for agent in data.get("agents", []):
            name = agent.get("name", "")
            if name.startswith(f"{changeling_name}-"):
                return name
    except json.JSONDecodeError:
        pass

    return None


def _forward_output(line: str, is_stdout: bool) -> None:
    """Forward subprocess output to the console in real time."""
    stream = sys.stdout if is_stdout else sys.stderr
    stream.write(line)
    stream.flush()


def build_cron_mngr_command(
    changeling: ChangelingDefinition,
    env_file_path: Path,
) -> list[str]:
    """Build the mngr create command for use inside the cron runner.

    Not pure: delegates to build_mngr_create_command which reads datetime.now().
    """
    return build_mngr_create_command(changeling, is_modal=True, env_file_path=env_file_path)


def find_repo_root() -> Path:
    """Find the git repository root directory.

    Raises ChangelingDeployError if not inside a git repository.
    """
    with ConcurrencyGroup(name="find-repo-root") as cg:
        result = cg.run_process_to_completion(
            ["git", "rev-parse", "--show-toplevel"],
            is_checked_after=False,
        )

    if result.returncode != 0:
        raise ChangelingDeployError(
            "Could not find git repository root. Changeling deployment must be run from within a git repository."
        ) from None
    return Path(result.stdout.strip())


def get_imbue_commit_hash() -> str:
    """Get the commit hash of the imbue monorepo (the repo containing changeling/mngr).

    This is used to pin the exact version of the tooling that gets cloned on
    Modal at runtime. This is a development convenience -- once the changeling
    package is published, the tooling will be installed via pip instead.

    Raises ChangelingDeployError if not inside a git repository.
    """
    with ConcurrencyGroup(name="get-commit-hash") as cg:
        result = cg.run_process_to_completion(
            ["git", "rev-parse", "HEAD"],
            is_checked_after=False,
        )

    if result.returncode != 0:
        raise ChangelingDeployError("Could not get current commit hash") from None
    return result.stdout.strip()


def get_imbue_repo_url() -> str:
    """Get the HTTPS clone URL for the imbue monorepo (changeling/mngr tooling).

    This URL is used to clone the tooling onto Modal at runtime so that
    the changeling and mngr packages are available. This is a development
    convenience -- once the changeling package is published, the tooling
    will be installed via pip instead and this will no longer be needed.

    This is distinct from the *target* repo (changeling.repo) which is the
    repo the changeling operates on.

    Converts SSH URLs to HTTPS format since gh auth setup-git works with HTTPS.
    Raises ChangelingDeployError if the remote URL cannot be determined.
    """
    with ConcurrencyGroup(name="get-repo-url") as cg:
        result = cg.run_process_to_completion(
            ["git", "remote", "get-url", "origin"],
            is_checked_after=False,
        )

    if result.returncode != 0:
        raise ChangelingDeployError(
            "Could not get repository clone URL. Make sure the 'origin' remote is configured."
        ) from None
    url = result.stdout.strip()
    # Convert SSH URL to HTTPS (gh auth setup-git works with HTTPS)
    if url.startswith("git@github.com:"):
        url = "https://github.com/" + url[len("git@github.com:") :]
    return url


def list_mngr_profiles() -> list[str]:
    """List available mngr profile IDs from ~/.mngr/profiles/.

    Returns the profile directory names (UUID hex strings) sorted alphabetically.
    """
    profiles_dir = Path.home() / ".mngr" / "profiles"
    if not profiles_dir.is_dir():
        return []
    return sorted(p.name for p in profiles_dir.iterdir() if p.is_dir())


def read_profile_user_id(profile_id: str) -> str:
    """Read the user_id from a mngr profile directory.

    Raises ChangelingDeployError if the user_id file does not exist.
    """
    user_id_path = Path.home() / ".mngr" / "profiles" / profile_id / "user_id"
    if not user_id_path.exists():
        raise ChangelingDeployError(
            f"user_id file not found at {user_id_path}. Make sure the mngr profile is set up correctly."
        )
    return user_id_path.read_text().strip()


@pure
def get_modal_environment_name(user_id: str) -> str:
    """Compute the Modal environment name from a mngr user_id."""
    return f"mngr-{user_id}"


def create_modal_secret(
    changeling: ChangelingDefinition,
    environment_name: str | None = None,
) -> str:
    """Create or update a Modal secret with the changeling's API keys.

    Reads secret values from the current process environment and creates
    a persistent Modal secret that the cron function references at runtime.

    Returns the secret name.
    Raises ChangelingDeployError if the secret cannot be created.
    """
    secret_name = get_modal_secret_name(str(changeling.name))
    secret_values = collect_secret_values(changeling.secrets, os.environ)

    missing = [name for name in changeling.secrets if name not in secret_values]
    if missing:
        logger.warning("Secrets not found in environment (skipping): {}", ", ".join(missing))

    if not secret_values:
        logger.warning(
            "No secret values found in environment for changeling '{}'. "
            "The deployed function will not have any secrets available.",
            changeling.name,
        )

    cmd = build_modal_secret_command(secret_name, secret_values, environment_name)
    with ConcurrencyGroup(name=f"modal-secret-{changeling.name}") as cg:
        result = cg.run_process_to_completion(cmd, is_checked_after=False, on_output=_forward_output)

    if result.returncode != 0:
        raise ChangelingDeployError(
            f"Failed to create Modal secret '{secret_name}' "
            f"(exit code {result.returncode}). See streamed output above for details."
        ) from None

    logger.info("Created Modal secret '{}'", secret_name)
    return secret_name


def _create_modal_volume(volume_name: str, environment_name: str | None) -> None:
    """Create a Modal volume if it doesn't already exist."""
    cmd = ["uv", "run", "modal", "volume", "create", volume_name]
    if environment_name:
        cmd.extend(["--env", environment_name])
    with ConcurrencyGroup(name=f"modal-volume-{volume_name}") as cg:
        result = cg.run_process_to_completion(cmd, is_checked_after=False, on_output=_forward_output)

    # Exit code 1 with "already exists" is fine
    if result.returncode != 0 and "already exists" not in result.stderr:
        raise ChangelingDeployError(
            f"Failed to create Modal volume '{volume_name}' "
            f"(exit code {result.returncode}). See streamed output above for details."
        )


def deploy_changeling(
    changeling: ChangelingDefinition,
    is_finish_initial_run: bool = False,
) -> str:
    """Deploy a changeling to Modal as a cron-scheduled function.

    The Modal environment name is derived from the changeling's mngr_profile.
    The profile must be set before calling this function (see cli/add.py).

    This performs the full deployment and verification:
    1. Creates/updates a Modal secret with the changeling's API keys
    2. Deploys the cron runner function with the changeling's configuration
    3. Invokes the function once via `modal run` to verify it works
    4. Polls `mngr list` to confirm an agent is created
    5. Destroys the test agent (or waits for it to finish if is_finish_initial_run)

    Returns the Modal app name.
    Raises ChangelingDeployError if deployment or verification fails.
    """
    from imbue.changelings.deploy.verification import verify_deployment

    if changeling.mngr_profile is None:
        raise ChangelingDeployError(
            "mngr_profile must be set before deploying. Use 'changeling add' to auto-detect it."
        )

    # Derive Modal environment name from the profile's user_id
    user_id = read_profile_user_id(changeling.mngr_profile)
    environment_name = get_modal_environment_name(user_id)
    logger.info("Using Modal environment '{}' (profile: {})", environment_name, changeling.mngr_profile)

    app_name = get_modal_app_name(str(changeling.name))
    volume_name = get_modal_volume_name(str(changeling.name))

    # The imbue repo URL and commit hash identify where the changeling/mngr
    # tooling lives. This is cloned on Modal at runtime so the tooling is
    # available. This is separate from the target repo (changeling.repo)
    # which is the repo the changeling operates on.
    imbue_repo_url = get_imbue_repo_url()
    imbue_commit_hash = get_imbue_commit_hash()

    with log_span("Creating Modal secret for changeling '{}'", changeling.name):
        secret_name = create_modal_secret(changeling, environment_name)

    # Create the persistent volume for target repo storage (before deploy so
    # it exists when the deployed function references it)
    with log_span("Creating Modal volume '{}' for changeling '{}'", volume_name, changeling.name):
        _create_modal_volume(volume_name, environment_name)

    cron_runner_path = Path(__file__).parent / "cron_runner.py"
    config_json = serialize_changeling_config(changeling)

    # Detect the user's local timezone so the cron schedule runs in their timezone
    cron_timezone = detect_local_timezone()
    logger.info("Detected local timezone '{}' for cron schedule", cron_timezone)

    deploy_env_vars = build_deploy_env(
        app_name=app_name,
        config_json=config_json,
        cron_schedule=str(changeling.schedule),
        secret_name=secret_name,
        imbue_repo_url=imbue_repo_url,
        imbue_commit_hash=imbue_commit_hash,
        volume_name=volume_name,
        cron_timezone=cron_timezone,
    )

    env = {**os.environ, **deploy_env_vars}

    with log_span("Deploying changeling '{}' to Modal app '{}'", changeling.name, app_name):
        cmd = build_modal_deploy_command(cron_runner_path, environment_name)

        with ConcurrencyGroup(name=f"modal-deploy-{changeling.name}") as cg:
            result = cg.run_process_to_completion(
                cmd, timeout=600.0, env=env, is_checked_after=False, on_output=_forward_output
            )

        if result.returncode != 0:
            raise ChangelingDeployError(
                f"Failed to deploy changeling '{changeling.name}' to Modal "
                f"(exit code {result.returncode}). See streamed output above for details."
            ) from None

    logger.info("Changeling '{}' deployed to Modal app '{}'", changeling.name, app_name)

    with log_span("Verifying deployment of changeling '{}'", changeling.name):
        verify_deployment(
            changeling=changeling,
            environment_name=environment_name,
            is_finish_initial_run=is_finish_initial_run,
            env=env,
            cron_runner_path=cron_runner_path,
        )

    return app_name
