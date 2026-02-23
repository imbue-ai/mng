# Modal app for running a scheduled mng command on a cron schedule.
#
# This file is deployed via `modal deploy` and runs as a cron-scheduled Modal
# Function. The module-level code handles deploy-time configuration (reading
# env vars, building the image). The runtime function runs the configured mng
# command.
#
# IMPORTANT: This file must NOT import from imbue.* packages that depend on
# the mng framework. It runs standalone on Modal via `modal deploy`. The only
# exception is staging.py, which has no framework dependencies.
#
# Unlike the changelings cron_runner, this version bakes the entire codebase
# (including mng tooling) into the Docker image at deploy time via the
# --git-image-hash approach. No runtime repo cloning is needed.
#
# The image is built from the project's Dockerfile (typically .mng/Dockerfile)
# which installs system deps, uv, claude code, extracts the repo tarball, and
# runs `uv sync --all-packages`. The code lives at /code/mng/ in the image.
#
# A staging directory is added as the last image layer, containing:
# - /staging/deploy_config.json: All deploy-time configuration as a single JSON
# - /staging/home/: Files destined for ~/  (mirrors home directory structure)
# - /staging/secrets/.env: Secrets env file (GH_TOKEN, etc.)
#
# Required environment variables at deploy time:
# - SCHEDULE_DEPLOY_CONFIG: JSON string with all deploy configuration
# - SCHEDULE_BUILD_CONTEXT_DIR: Local path to build context (contains current.tar.gz)
# - SCHEDULE_STAGING_DIR: Local path to staging directory (deploy files + secrets)
# - SCHEDULE_DOCKERFILE: Local path to Dockerfile for image build

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import modal

# --- Deploy-time configuration ---
# At deploy time (modal.is_local() == True), we read configuration from a
# single JSON env var and write it to /staging/deploy_config.json. At runtime,
# we read from that baked-in file. Local filesystem paths (build context,
# staging dir, dockerfile) are separate env vars since they're only needed
# at deploy time for image building.


def _require_env(name: str) -> str:
    """Read a required environment variable, raising if missing."""
    value = os.environ.get(name)
    if value is None:
        raise RuntimeError(f"{name} must be set")
    return value


if modal.is_local():
    _deploy_config_json: str = _require_env("SCHEDULE_DEPLOY_CONFIG")
    _deploy_config: dict[str, Any] = json.loads(_deploy_config_json)

    # Local filesystem paths only needed at deploy time for image building
    _BUILD_CONTEXT_DIR: str = _require_env("SCHEDULE_BUILD_CONTEXT_DIR")
    _STAGING_DIR: str = _require_env("SCHEDULE_STAGING_DIR")
    _DOCKERFILE: str = _require_env("SCHEDULE_DOCKERFILE")
else:
    _deploy_config: dict[str, Any] = json.loads(Path("/staging/deploy_config.json").read_text())

    _BUILD_CONTEXT_DIR = ""
    _STAGING_DIR = ""
    _DOCKERFILE = ""

# Extract config values used by both deploy-time image building and runtime scheduling
_APP_NAME: str = _deploy_config["app_name"]
_CRON_SCHEDULE: str = _deploy_config["cron_schedule"]
_CRON_TIMEZONE: str = _deploy_config["cron_timezone"]


# --- Image definition ---
# The image is built from the project's Dockerfile, which already installs
# system dependencies, uv, claude code, extracts the repo tarball, and runs
# `uv sync --all-packages`. We add the staging directory on top.

if modal.is_local():
    _image = modal.Image.from_dockerfile(
        _DOCKERFILE,
        context_dir=_BUILD_CONTEXT_DIR,
    ).add_local_dir(
        _STAGING_DIR,
        "/staging",
        copy=True,
    )
else:
    # At runtime, the image is already built
    _image = modal.Image.debian_slim()

app = modal.App(name=_APP_NAME, image=_image)


# --- Runtime functions ---


def _run_and_stream(
    cmd: list[str] | str,
    *,
    is_checked: bool = True,
    cwd: str | None = None,
    is_shell: bool = False,
) -> int:
    """Run a command, streaming output to stdout in real time."""
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=cwd,
        shell=is_shell,
    )
    assert process.stdout is not None
    for line in process.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
    process.wait()
    if is_checked and process.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {process.returncode}: {cmd}")
    return process.returncode


@app.function(
    schedule=modal.Cron(_CRON_SCHEDULE, timezone=_CRON_TIMEZONE),
    timeout=3600,
)
def run_scheduled_trigger() -> None:
    """Run the scheduled mng command.

    This function executes on the cron schedule and:
    1. Checks if the trigger is enabled
    2. Installs deploy files (config, settings, etc.) from staged manifest
    3. Sets up GitHub authentication
    4. Builds and runs the mng command with secrets env file
    """
    trigger = _deploy_config["trigger"]

    if not trigger.get("is_enabled", True):
        print("Schedule trigger is disabled, skipping")
        return

    # Install deploy files (config, settings, etc.) from staged manifest
    # Late import: staging.py is only available at runtime (after the image is built),
    # not at deploy time when this file's module-level code runs.
    from imbue.mng_schedule.implementations.modal.staging import install_deploy_files

    install_deploy_files()

    # Set up GitHub authentication
    print("Setting up GitHub authentication...")
    os.makedirs(os.path.expanduser("~/.ssh"), mode=0o700, exist_ok=True)
    _run_and_stream(
        "ssh-keyscan github.com >> ~/.ssh/known_hosts 2>/dev/null && gh auth setup-git",
        is_shell=True,
    )

    # Build the mng command (command is stored uppercase from the enum, mng CLI expects lowercase)
    command = trigger["command"].lower()
    args_str = trigger.get("args", "")

    cmd = ["uv", "run", "mng", command]
    if args_str:
        cmd.extend(shlex.split(args_str))

    # Add secrets env file if it exists and the command supports it.
    # --host-env-file is only valid for create (and start) commands.
    secrets_env = Path("/staging/secrets/.env")
    if secrets_env.exists() and command in ("create", "start"):
        cmd.extend(["--host-env-file", str(secrets_env)])

    print(f"Running: {' '.join(cmd)}")
    exit_code = _run_and_stream(
        cmd,
        cwd="/code/mng",
        is_checked=False,
    )
    if exit_code != 0:
        raise RuntimeError(f"mng {command} failed with exit code {exit_code}")
