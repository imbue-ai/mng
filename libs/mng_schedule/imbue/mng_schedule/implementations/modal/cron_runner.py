# Modal app for running a scheduled mng command on a cron schedule.
#
# This file is deployed via `modal deploy` and runs as a cron-scheduled Modal
# Function. The module-level code handles deploy-time configuration (reading
# env vars, building the image). The runtime function runs the configured mng
# command.
#
# IMPORTANT: This file must NOT import from imbue.* packages that depend on
# the mng framework. It runs standalone on Modal via `modal deploy`.
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
# - /staging/project/: Files destined for the project working directory
# - /staging/secrets/.env: Consolidated env vars (from --pass-env and --env-file)
#
# Files from /staging/home/ and /staging/project/ are baked into their final
# locations ($HOME and WORKDIR respectively) during the image build via
# dockerfile_commands, so no runtime file installation is needed.
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

# Dockerfile commands for installing mng, computed by deploy.py's
# build_mng_install_commands() and passed via the deploy config JSON.
# This ensures a single source of truth for the install logic.
_MNG_INSTALL_COMMANDS: list[str] = _deploy_config.get("mng_install_commands", [])


# --- Image definition ---
# The image is built from the project's Dockerfile, which already installs
# system dependencies, uv, claude code, extracts the repo tarball, and runs
# `uv sync --all-packages`. We add the staging directory on top and then
# bake user/project files into their final locations via dockerfile_commands.
# The Dockerfile's WORKDIR must be set to the project directory (e.g.
# /code/mng/) so that project files are copied to the correct location.
#
# If mng_install_commands is non-empty, additional dockerfile commands are
# appended to install mng and mng-schedule into the image (so that
# `uv run mng` works at runtime even if the base image does not include mng).

if modal.is_local():
    _image = (
        modal.Image.from_dockerfile(
            _DOCKERFILE,
            context_dir=_BUILD_CONTEXT_DIR,
        )
        .add_local_dir(
            _STAGING_DIR,
            "/staging",
            copy=True,
        )
        .dockerfile_commands(
            [
                "RUN cp -a /staging/home/. $HOME/",
                "RUN cp -a /staging/project/. .",
            ]
            + _MNG_INSTALL_COMMANDS
        )
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


def _load_env_file(env_file_path: Path) -> None:
    """Load environment variables from a .env file into os.environ.

    Lines starting with '#' are treated as comments. Empty lines are skipped.
    Lines without '=' are skipped. The 'export ' prefix is stripped if present
    (to support shell-compatible env files). Values are not shell-unquoted
    (quotes are kept as-is to match dotenv conventions for the subprocess
    environment).
    """
    if not env_file_path.exists():
        return
    for line in env_file_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Strip optional 'export ' prefix for shell-compatible env files
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :]
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ[key.strip()] = value.strip()


@app.function(
    schedule=modal.Cron(_CRON_SCHEDULE, timezone=_CRON_TIMEZONE),
    timeout=3600,
)
def run_scheduled_trigger() -> None:
    """Run the scheduled mng command.

    This function executes on the cron schedule and:
    1. Checks if the trigger is enabled
    2. Loads consolidated environment variables from the secrets env file
    3. Sets up GitHub authentication
    4. Builds and runs the mng command with secrets env file

    Deploy files (config, settings, etc.) are already baked into $HOME and
    WORKDIR during the image build via dockerfile_commands.
    """
    trigger = _deploy_config["trigger"]

    if not trigger.get("is_enabled", True):
        print("Schedule trigger is disabled, skipping")
        return

    # Load consolidated env vars into the process environment so that the
    # mng CLI and any subprocesses it spawns have access to them.
    secrets_env = Path("/staging/secrets/.env")
    if secrets_env.exists():
        print("Loading environment variables from secrets env file...")
        _load_env_file(secrets_env)

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

    # Also pass the secrets env file via --host-env-file for create/start commands
    # so the agent host inherits these environment variables.
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
