# Modal app for running a changeling on a cron schedule.
#
# This file is deployed via `modal deploy` and runs as a cron-scheduled Modal
# Function. The module-level code handles deploy-time configuration (reading
# env vars, building the image). The runtime function uses shared logic from
# the changelings package to build and execute the mngr create command.
#
# The image includes the full repository with all packages installed via
# `uv sync --all-packages`, so changelings and mngr are both available.
#
# Required environment variables at deploy time:
# - CHANGELING_MODAL_APP_NAME: The Modal app name (e.g., "changeling-code-guardian")
# - CHANGELING_CONFIG_JSON: JSON-encoded changeling definition
# - CHANGELING_CRON_SCHEDULE: Cron schedule expression (e.g., "0 3 * * *")
# - CHANGELING_REPO_ROOT: Absolute path to the repository root
# - CHANGELING_SECRET_NAME: Name of the Modal Secret containing API keys

import os
from pathlib import Path

import modal

from imbue.changelings.errors import ChangelingError


class _ConfigurationError(ChangelingError, RuntimeError):
    """Raised when required configuration is missing at deploy time."""

    ...


# --- Deploy-time configuration ---
# When modal.is_local() is True, we are running at deploy time on the user's machine.
# We read configuration from environment variables and write it to build files that
# get baked into the Modal image. At runtime (in Modal's cloud), we read from the
# baked-in files.


def _require_env(name: str) -> str:
    """Read a required environment variable, raising if missing."""
    value = os.environ.get(name)
    if value is None:
        raise _ConfigurationError(f"{name} must be set")
    return value


if modal.is_local():
    _APP_NAME: str = _require_env("CHANGELING_MODAL_APP_NAME")
    _CONFIG_JSON: str = _require_env("CHANGELING_CONFIG_JSON")
    _CRON_SCHEDULE: str = _require_env("CHANGELING_CRON_SCHEDULE")
    _REPO_ROOT: str | None = _require_env("CHANGELING_REPO_ROOT")
    _SECRET_NAME: str = _require_env("CHANGELING_SECRET_NAME")

    # Write config to build directory so it can be baked into the image
    _build_dir = Path(".changelings/build")
    _build_dir.mkdir(parents=True, exist_ok=True)
    (_build_dir / "app_name").write_text(_APP_NAME)
    (_build_dir / "config.json").write_text(_CONFIG_JSON)
    (_build_dir / "cron_schedule").write_text(_CRON_SCHEDULE)
    (_build_dir / "secret_name").write_text(_SECRET_NAME)
else:
    _APP_NAME = Path("/deployment/app_name").read_text().strip()
    _CONFIG_JSON = Path("/deployment/config.json").read_text().strip()
    _CRON_SCHEDULE = Path("/deployment/cron_schedule").read_text().strip()
    _SECRET_NAME = Path("/deployment/secret_name").read_text().strip()
    _REPO_ROOT = None

# --- Image definition ---
# The image includes the full repository so that mngr and changelings are
# available as installed packages at runtime.
_image = modal.Image.debian_slim(python_version="3.12").apt_install("git", "curl", "openssh-client").pip_install("uv")

if _REPO_ROOT is not None:
    _image = _image.add_local_dir(
        _REPO_ROOT,
        remote_path="/repo",
        copy=True,
        ignore=[
            ".git",
            ".venv",
            "__pycache__",
            "*.pyc",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            "node_modules",
            ".claude",
            "htmlcov",
            ".changelings",
        ],
    )
    _image = _image.run_commands("cd /repo && uv sync --all-packages --no-dev --frozen")

_image = (
    _image.add_local_file(".changelings/build/app_name", "/deployment/app_name", copy=True)
    .add_local_file(".changelings/build/config.json", "/deployment/config.json", copy=True)
    .add_local_file(".changelings/build/cron_schedule", "/deployment/cron_schedule", copy=True)
    .add_local_file(".changelings/build/secret_name", "/deployment/secret_name", copy=True)
)

app = modal.App(name=_APP_NAME, image=_image)


@app.function(
    secrets=[modal.Secret.from_name(_SECRET_NAME)],
    schedule=modal.Cron(_CRON_SCHEDULE),
    timeout=3600,
)
def run_changeling() -> None:
    """Run the changeling by invoking mngr create on Modal.

    This function executes on the cron schedule and:
    1. Deserializes the baked-in changeling configuration
    2. Checks if the changeling is enabled
    3. Writes secrets to a temporary env file and builds the mngr command
    4. Runs the command and cleans up
    """
    from imbue.changelings.data_types import ChangelingDefinition
    from imbue.changelings.deploy.deploy import build_cron_mngr_command
    from imbue.changelings.errors import ChangelingRunError
    from imbue.changelings.mngr_commands import write_secrets_env_file
    from imbue.concurrency_group.concurrency_group import ConcurrencyGroup

    changeling = ChangelingDefinition.model_validate_json(_CONFIG_JSON)

    if not changeling.is_enabled:
        return

    def _log_output(line: str, is_stderr: bool) -> None:
        """Forward subprocess output to Modal logs via print."""
        import sys

        stream = sys.stderr if is_stderr else sys.stdout
        stream.write(line)
        stream.flush()

    env_file_path = write_secrets_env_file(changeling)
    try:
        cmd = build_cron_mngr_command(changeling, env_file_path)
        with ConcurrencyGroup(name=f"cron-{changeling.name}") as cg:
            result = cg.run_process_to_completion(
                cmd,
                is_checked_after=False,
                cwd=Path("/repo"),
                on_output=_log_output,
            )

        if result.returncode != 0:
            output = (result.stdout + "\n" + result.stderr).strip()
            raise ChangelingRunError(
                f"Changeling '{changeling.name}' failed with exit code {result.returncode}:\n{output}"
            )
    finally:
        env_file_path.unlink(missing_ok=True)
