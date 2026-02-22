# Modal app for running a scheduled mng command on a cron schedule.
#
# This file is deployed via `modal deploy` and runs as a cron-scheduled Modal
# Function. The module-level code handles deploy-time configuration (reading
# env vars, building the image). The runtime function runs the configured mng
# command.
#
# IMPORTANT: This file must NOT import anything from imbue.* packages.
# It runs standalone on Modal via `modal deploy`.
#
# Unlike the changelings cron_runner, this version bakes the entire codebase
# (including mng tooling) into the Docker image at deploy time via the
# --git-image-hash approach. No runtime repo cloning is needed.
#
# The image is built from the Dockerfile at libs/mng/imbue/mng/resources/Dockerfile
# which installs system deps, uv, claude code, extracts the repo tarball, and
# runs `uv sync --all-packages`. The code lives at /code/mng/ in the image.
#
# A staging directory is added as the last image layer, containing:
# - /staging/trigger.json: The trigger definition
# - /staging/user_config/: User config files (claude.json, mng config, profiles)
# - /staging/secrets/.env: Secrets env file (GH_TOKEN, etc.)
#
# Required environment variables at deploy time:
# - SCHEDULE_APP_NAME: The Modal app name
# - SCHEDULE_TRIGGER_JSON: JSON-encoded trigger definition
# - SCHEDULE_CRON: Cron schedule expression (e.g., "0 3 * * *")
# - SCHEDULE_CRON_TIMEZONE: IANA timezone for the cron schedule
# - SCHEDULE_BUILD_CONTEXT_DIR: Path to the build context directory (contains current.tar.gz)
# - SCHEDULE_STAGING_DIR: Path to the staging directory (user config + secrets)
# - SCHEDULE_DOCKERFILE: Path to the Dockerfile to use for building the image

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import modal

# --- Deploy-time configuration ---


def _require_env(name: str) -> str:
    """Read a required environment variable, raising if missing."""
    value = os.environ.get(name)
    if value is None:
        raise RuntimeError(f"{name} must be set")
    return value


if modal.is_local():
    _APP_NAME: str = _require_env("SCHEDULE_APP_NAME")
    _TRIGGER_JSON: str = _require_env("SCHEDULE_TRIGGER_JSON")
    _CRON_SCHEDULE: str = _require_env("SCHEDULE_CRON")
    _CRON_TIMEZONE: str = _require_env("SCHEDULE_CRON_TIMEZONE")
    _BUILD_CONTEXT_DIR: str = _require_env("SCHEDULE_BUILD_CONTEXT_DIR")
    _STAGING_DIR: str = _require_env("SCHEDULE_STAGING_DIR")
    _DOCKERFILE: str = _require_env("SCHEDULE_DOCKERFILE")
else:
    _APP_NAME = "unknown"
    _TRIGGER_JSON = "{}"
    _CRON_SCHEDULE = "0 0 * * *"
    _CRON_TIMEZONE = "UTC"
    _BUILD_CONTEXT_DIR = ""
    _STAGING_DIR = ""
    _DOCKERFILE = ""


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


def _install_user_config() -> None:
    """Copy staged user config files to their expected locations in the container."""
    staged = Path("/staging/user_config")

    claude_json = staged / "claude.json"
    if claude_json.exists():
        shutil.copy2(claude_json, Path.home() / ".claude.json")

    claude_settings = staged / "claude_dir" / "settings.json"
    if claude_settings.exists():
        (Path.home() / ".claude").mkdir(parents=True, exist_ok=True)
        shutil.copy2(claude_settings, Path.home() / ".claude" / "settings.json")

    mng_config = staged / "mng" / "config.toml"
    if mng_config.exists():
        (Path.home() / ".mng").mkdir(parents=True, exist_ok=True)
        shutil.copy2(mng_config, Path.home() / ".mng" / "config.toml")

    mng_profiles = staged / "mng" / "profiles"
    if mng_profiles.is_dir():
        shutil.copytree(mng_profiles, Path.home() / ".mng" / "profiles", dirs_exist_ok=True)


@app.function(
    schedule=modal.Cron(_CRON_SCHEDULE, timezone=_CRON_TIMEZONE),
    timeout=3600,
)
def run_scheduled_trigger() -> None:
    """Run the scheduled mng command.

    This function executes on the cron schedule and:
    1. Checks if the trigger is enabled
    2. Installs user config files to their expected locations
    3. Sets up GitHub authentication
    4. Builds and runs the mng command with secrets env file
    """
    trigger = json.loads(Path("/staging/trigger.json").read_text())

    if not trigger.get("is_enabled", True):
        print("Schedule trigger is disabled, skipping")
        return

    # Install user config
    _install_user_config()

    # Set up GitHub authentication
    print("Setting up GitHub authentication...")
    os.makedirs(os.path.expanduser("~/.ssh"), mode=0o700, exist_ok=True)
    _run_and_stream(
        "ssh-keyscan github.com >> ~/.ssh/known_hosts 2>/dev/null && gh auth setup-git",
        is_shell=True,
    )

    # Build the mng command
    command = trigger["command"]
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
