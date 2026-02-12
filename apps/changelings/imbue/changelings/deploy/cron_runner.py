"""Modal app for running a changeling on a cron schedule.

This file is deployed via `modal deploy` and runs independently of the main
changelings codebase. It is intentionally self-contained (no imports from
changelings or mngr) so that deployment is simple and reliable.

The mngr CLI is installed in the image and invoked as a subprocess to run
the agent. This mirrors the pattern used in mngr's own Modal route files.

Required environment variables at deploy time:
- CHANGELING_MODAL_APP_NAME: The Modal app name (e.g., "changeling-code-guardian")
- CHANGELING_CONFIG_JSON: JSON-encoded changeling definition
- CHANGELING_CRON_SCHEDULE: Cron schedule expression (e.g., "0 3 * * *")
- CHANGELING_REPO_ROOT: Absolute path to the repository root
- CHANGELING_SECRET_NAME: Name of the Modal Secret containing API keys
"""

import json
import os
import shlex
import subprocess
import tempfile
from datetime import datetime
from datetime import timezone
from pathlib import Path

import modal


class _ConfigurationError(RuntimeError):
    """Raised when required configuration is missing at deploy time."""


# --- Deploy-time configuration ---
# When modal.is_local() is True, we are running at deploy time on the user's machine.
# We read configuration from environment variables and write it to build files that
# get baked into the Modal image. At runtime (in Modal's cloud), we read from the
# baked-in files.

if modal.is_local():
    _APP_NAME = os.environ.get("CHANGELING_MODAL_APP_NAME")
    if _APP_NAME is None:
        raise _ConfigurationError("CHANGELING_MODAL_APP_NAME must be set")

    _CONFIG_JSON = os.environ.get("CHANGELING_CONFIG_JSON")
    if _CONFIG_JSON is None:
        raise _ConfigurationError("CHANGELING_CONFIG_JSON must be set")

    _CRON_SCHEDULE = os.environ.get("CHANGELING_CRON_SCHEDULE")
    if _CRON_SCHEDULE is None:
        raise _ConfigurationError("CHANGELING_CRON_SCHEDULE must be set")

    _REPO_ROOT = os.environ.get("CHANGELING_REPO_ROOT")
    if _REPO_ROOT is None:
        raise _ConfigurationError("CHANGELING_REPO_ROOT must be set")

    _SECRET_NAME = os.environ.get("CHANGELING_SECRET_NAME")
    if _SECRET_NAME is None:
        raise _ConfigurationError("CHANGELING_SECRET_NAME must be set")

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

_config = json.loads(_CONFIG_JSON)

# --- Image definition ---
# The image includes the full repository so that mngr is available as a CLI tool.
# At deploy time, the repo root is copied into /repo and packages are installed.
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
    1. Reads the baked-in changeling configuration
    2. Writes secrets from the Modal Secret to a temporary env file
    3. Builds and runs the mngr create command
    4. Cleans up the temporary env file
    """
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H-%M-%S")
    name = _config["name"]
    agent_name = f"{name}-{now_str}"
    branch_name = f"changelings/{name}-{now_str}"

    # Write secrets to a temporary env file for mngr
    fd, env_path_str = tempfile.mkstemp(prefix="changeling-env-", suffix=".env")
    try:
        lines: list[str] = []
        for secret_var in _config.get("secrets", ["GITHUB_TOKEN", "ANTHROPIC_API_KEY"]):
            value = os.environ.get(secret_var, "")
            if value:
                lines.append(f"{secret_var}={value}\n")
        os.write(fd, "".join(lines).encode())
        os.close(fd)
        os.chmod(env_path_str, 0o600)

        # Build the mngr create command
        cmd = [
            "uv",
            "run",
            "mngr",
            "create",
            agent_name,
            _config.get("agent_type", "claude"),
            "--no-connect",
            "--await-agent-stopped",
            "--no-ensure-clean",
            "--tag",
            "CREATOR=changeling",
            "--tag",
            f"CHANGELING={name}",
            "--base-branch",
            _config.get("branch", "main"),
            "--new-branch",
            branch_name,
            "--message",
            _config.get("initial_message", "Please use your primary skill"),
            "--in",
            "modal",
            "--host-env-file",
            env_path_str,
        ]

        # Add explicit environment variables
        for key, value in _config.get("env_vars", {}).items():
            cmd.extend(["--host-env", f"{key}={value}"])

        # Add extra mngr arguments
        extra_args = _config.get("extra_mngr_args", "")
        if extra_args:
            cmd.extend(shlex.split(extra_args))

        result = subprocess.run(cmd, cwd="/repo")
        if result.returncode != 0:
            raise RuntimeError(f"Changeling '{name}' failed with exit code {result.returncode}")
    finally:
        Path(env_path_str).unlink(missing_ok=True)
