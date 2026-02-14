# Modal app for running a changeling on a cron schedule.
#
# This file is deployed via `modal deploy` and runs as a cron-scheduled Modal
# Function. The module-level code handles deploy-time configuration (reading
# env vars, building the image). The runtime function clones the repo,
# installs dependencies, and invokes the remote runner script.
#
# IMPORTANT: This file must NOT import anything from imbue.* packages.
# All changeling/mngr logic runs inside the cloned repo via remote_runner.py.
#
# The image includes system dependencies, GitHub CLI, uv, and Claude Code,
# all cached as image layers. The actual repo is cloned at runtime so that
# the base image layers are reused across deployments.
#
# Required environment variables at deploy time:
# - CHANGELING_MODAL_APP_NAME: The Modal app name (e.g., "changeling-code-guardian")
# - CHANGELING_CONFIG_JSON: JSON-encoded changeling definition
# - CHANGELING_CRON_SCHEDULE: Cron schedule expression (e.g., "0 3 * * *")
# - CHANGELING_REPO_CLONE_URL: HTTPS clone URL for the monorepo
# - CHANGELING_COMMIT_HASH: Git commit hash to checkout
# - CHANGELING_SECRET_NAME: Name of the Modal Secret containing API keys

import json
import os
import subprocess
import sys
from pathlib import Path

import modal

# --- Deploy-time configuration ---
# When modal.is_local() is True, we are running at deploy time on the user's machine.
# We read configuration from environment variables and write it to build files that
# get baked into the Modal image. At runtime (in Modal's cloud), we read from the
# baked-in files.


def _require_env(name: str) -> str:
    """Read a required environment variable, raising if missing."""
    value = os.environ.get(name)
    if value is None:
        raise Exception(f"{name} must be set")
    return value


if modal.is_local():
    _APP_NAME: str = _require_env("CHANGELING_MODAL_APP_NAME")
    _CONFIG_JSON: str = _require_env("CHANGELING_CONFIG_JSON")
    _CRON_SCHEDULE: str = _require_env("CHANGELING_CRON_SCHEDULE")
    _REPO_CLONE_URL: str = _require_env("CHANGELING_REPO_CLONE_URL")
    _COMMIT_HASH: str = _require_env("CHANGELING_COMMIT_HASH")
    _SECRET_NAME: str = _require_env("CHANGELING_SECRET_NAME")

    # Write config to build directory so it can be baked into the image
    _build_dir = Path(".changelings/build")
    _build_dir.mkdir(parents=True, exist_ok=True)
    (_build_dir / "app_name").write_text(_APP_NAME)
    (_build_dir / "config.json").write_text(_CONFIG_JSON)
    (_build_dir / "cron_schedule").write_text(_CRON_SCHEDULE)
    (_build_dir / "repo_clone_url").write_text(_REPO_CLONE_URL)
    (_build_dir / "commit_hash").write_text(_COMMIT_HASH)
    (_build_dir / "secret_name").write_text(_SECRET_NAME)
else:
    _APP_NAME = Path("/deployment/app_name").read_text().strip()
    _CONFIG_JSON = Path("/deployment/config.json").read_text().strip()
    _CRON_SCHEDULE = Path("/deployment/cron_schedule").read_text().strip()
    _REPO_CLONE_URL = Path("/deployment/repo_clone_url").read_text().strip()
    _COMMIT_HASH = Path("/deployment/commit_hash").read_text().strip()
    _SECRET_NAME = Path("/deployment/secret_name").read_text().strip()

# --- Image definition ---
# The image includes system dependencies, GitHub CLI, uv, and Claude Code.
# These layers are cached across deployments since they don't change.
# The actual monorepo is cloned at runtime (not baked in).
_image = (
    modal.Image.from_registry("python:3.11-slim")
    .run_commands(
        # System dependencies
        "apt-get update && apt-get install -y --no-install-recommends "
        "bash build-essential curl fd-find git git-lfs jq nano "
        "openssh-server ripgrep rsync tini tmux unison wget "
        "&& rm -rf /var/lib/apt/lists/*",
    )
    .run_commands(
        # GitHub CLI
        "mkdir -p -m 755 /etc/apt/keyrings "
        "&& out=$(mktemp) && wget -nv -O$out https://cli.github.com/packages/githubcli-archive-keyring.gpg "
        "&& cat $out | tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null "
        "&& chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg "
        "&& mkdir -p -m 755 /etc/apt/sources.list.d "
        '&& echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] '
        'https://cli.github.com/packages stable main" '
        "| tee /etc/apt/sources.list.d/github-cli.list > /dev/null "
        "&& apt update && apt install gh -y",
    )
    .run_commands(
        # Install uv
        "curl -LsSf https://astral.sh/uv/install.sh | sh",
    )
    .env({"PATH": "/root/.local/bin:/usr/local/bin:/usr/local/sbin:/usr/bin:/usr/sbin:/bin:/sbin"})
    .run_commands(
        # Install Claude Code
        "curl -fsSL https://claude.ai/install.sh > /tmp/install_claude.sh "
        "&& ( cat /tmp/install_claude.sh | bash ) || ( cat /tmp/install_claude.sh && exit 1 )",
    )
    .env(
        {
            "PATH": "/root/.claude/local/bin:/root/.local/bin:"
            "/usr/local/bin:/usr/local/sbin:/usr/bin:/usr/sbin:/bin:/sbin"
        }
    )
)

# Add deployment config files (these are the only layers that change per deployment)
_image = (
    _image.add_local_file(".changelings/build/app_name", "/deployment/app_name", copy=True)
    .add_local_file(".changelings/build/config.json", "/deployment/config.json", copy=True)
    .add_local_file(".changelings/build/cron_schedule", "/deployment/cron_schedule", copy=True)
    .add_local_file(".changelings/build/repo_clone_url", "/deployment/repo_clone_url", copy=True)
    .add_local_file(".changelings/build/commit_hash", "/deployment/commit_hash", copy=True)
    .add_local_file(".changelings/build/secret_name", "/deployment/secret_name", copy=True)
)

app = modal.App(name=_APP_NAME, image=_image)

_REPO_DIR = "/workspace/repo"


def _run_and_stream(
    cmd: list[str] | str,
    *,
    is_checked: bool = True,
    cwd: str | None = None,
    is_shell: bool = False,
) -> int:
    """Run a command, streaming output to stdout in real time.

    Returns the process exit code. Raises RuntimeError if is_checked is True
    and the exit code is non-zero.
    """
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
    secrets=[modal.Secret.from_name(_SECRET_NAME)],
    schedule=modal.Cron(_CRON_SCHEDULE),
    timeout=3600,
)
def run_changeling() -> None:
    """Run the changeling by cloning the repo and invoking the remote runner.

    This function executes on the cron schedule and:
    1. Checks if the changeling is enabled
    2. Sets up GitHub authentication via gh CLI
    3. Clones the monorepo and checks out the pinned commit
    4. Installs all dependencies via uv sync
    5. Invokes remote_runner.py which handles the mngr create command
    """
    # Check if enabled without importing imbue
    config = json.loads(_CONFIG_JSON)
    if not config.get("is_enabled", True):
        print("Changeling is disabled, skipping")
        return

    # Set up GitHub authentication
    print("Setting up GitHub authentication...")
    os.makedirs(os.path.expanduser("~/.ssh"), mode=0o700, exist_ok=True)
    _run_and_stream(
        "ssh-keyscan github.com >> ~/.ssh/known_hosts && gh auth setup-git",
        is_shell=True,
    )

    # Clone the repository at the pinned commit
    print(f"Cloning repository from {_REPO_CLONE_URL} at commit {_COMMIT_HASH}...")
    _run_and_stream(["git", "clone", _REPO_CLONE_URL, _REPO_DIR])
    _run_and_stream(["git", "checkout", _COMMIT_HASH], cwd=_REPO_DIR)

    # Install all dependencies
    print("Installing dependencies via uv sync...")
    _run_and_stream(["uv", "sync", "--all-packages"], cwd=_REPO_DIR)

    # Invoke the remote runner script (which has full access to the imbue stack)
    print("Running changeling via remote runner...")
    exit_code = _run_and_stream(
        ["uv", "run", "python", "-m", "imbue.changelings.deploy.remote_runner", _CONFIG_JSON],
        cwd=_REPO_DIR,
        is_checked=False,
    )
    if exit_code != 0:
        raise RuntimeError(f"Remote runner failed with exit code {exit_code}")
