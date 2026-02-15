# Modal app for running a changeling on a cron schedule.
#
# This file is deployed via `modal deploy` and runs as a cron-scheduled Modal
# Function. The module-level code handles deploy-time configuration (reading
# env vars, building the image). The runtime function clones the imbue repo,
# installs dependencies, and invokes the remote runner script.
#
# IMPORTANT: This file must NOT import anything from imbue.* packages.
# All changeling/mngr logic runs inside the cloned repo via remote_runner.py.
#
# There are two distinct repos involved:
#
#   1. The *imbue repo* -- the monorepo containing changeling/mngr tooling.
#      This is cloned on Modal at runtime so the tooling is available. This is
#      a development convenience that will go away once changeling is published
#      as a pip-installable package (at which point it will just be installed
#      into the image directly).
#
#   2. The *target repo* -- the repo the changeling operates on (e.g., the
#      user's project). This is specified in the changeling config (or defaults
#      to the imbue repo in development mode). The target repo is cloned onto
#      a persistent Modal Volume so it doesn't need to be re-cloned each run.
#
# The image includes system dependencies, GitHub CLI, uv, and Claude Code,
# all cached as image layers. The imbue repo is cloned at runtime so that
# the base image layers are reused across deployments.
#
# Required environment variables at deploy time:
# - CHANGELING_MODAL_APP_NAME: The Modal app name (e.g., "changeling-code-guardian")
# - CHANGELING_CONFIG_JSON: JSON-encoded changeling definition
# - CHANGELING_CRON_SCHEDULE: Cron schedule expression (e.g., "0 3 * * *")
# - CHANGELING_CRON_TIMEZONE: IANA timezone for the cron schedule (e.g., "America/Los_Angeles")
# - CHANGELING_IMBUE_REPO_URL: HTTPS clone URL for the imbue monorepo (tooling)
# - CHANGELING_IMBUE_COMMIT_HASH: Git commit hash to checkout in the imbue repo
# - CHANGELING_SECRET_NAME: Name of the Modal Secret containing API keys
# - CHANGELING_VOLUME_NAME: Name of the Modal Volume for persistent target repo storage

import json
import os
import shutil
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
    _CRON_TIMEZONE: str = _require_env("CHANGELING_CRON_TIMEZONE")
    _IMBUE_REPO_URL: str = _require_env("CHANGELING_IMBUE_REPO_URL")
    _IMBUE_COMMIT_HASH: str = _require_env("CHANGELING_IMBUE_COMMIT_HASH")
    _SECRET_NAME: str = _require_env("CHANGELING_SECRET_NAME")
    _VOLUME_NAME: str = _require_env("CHANGELING_VOLUME_NAME")

    # Assemble all deployment data + user config into a single staging directory.
    # This produces one mount instead of many separate file/dir mounts.
    _staging_dir = Path(".changelings/staging")
    if _staging_dir.exists():
        shutil.rmtree(_staging_dir)
    _staging_dir.mkdir(parents=True)

    # Deployment config files
    deploy_dir = _staging_dir / "deployment"
    deploy_dir.mkdir()
    (deploy_dir / "app_name").write_text(_APP_NAME)
    (deploy_dir / "config.json").write_text(_CONFIG_JSON)
    (deploy_dir / "cron_schedule").write_text(_CRON_SCHEDULE)
    (deploy_dir / "cron_timezone").write_text(_CRON_TIMEZONE)
    (deploy_dir / "imbue_repo_url").write_text(_IMBUE_REPO_URL)
    (deploy_dir / "imbue_commit_hash").write_text(_IMBUE_COMMIT_HASH)
    (deploy_dir / "secret_name").write_text(_SECRET_NAME)
    (deploy_dir / "volume_name").write_text(_VOLUME_NAME)

    # User config files needed by mngr at runtime
    _user_home = Path.home()
    user_cfg_dir = _staging_dir / "user_config"
    user_cfg_dir.mkdir()

    # ~/.claude.json
    _claude_json = _user_home / ".claude.json"
    if _claude_json.exists():
        shutil.copy2(_claude_json, user_cfg_dir / "claude.json")

    # ~/.claude/settings.json
    _claude_settings = _user_home / ".claude" / "settings.json"
    if _claude_settings.exists():
        (user_cfg_dir / "claude_dir").mkdir()
        shutil.copy2(_claude_settings, user_cfg_dir / "claude_dir" / "settings.json")

    # ~/.mngr/config.toml
    _mngr_config = _user_home / ".mngr" / "config.toml"
    if _mngr_config.exists():
        (user_cfg_dir / "mngr").mkdir()
        shutil.copy2(_mngr_config, user_cfg_dir / "mngr" / "config.toml")

    # ~/.mngr/profiles/
    _mngr_profiles = _user_home / ".mngr" / "profiles"
    if _mngr_profiles.is_dir():
        shutil.copytree(_mngr_profiles, user_cfg_dir / "mngr" / "profiles", dirs_exist_ok=True)
else:
    _APP_NAME = Path("/deployment/app_name").read_text().strip()
    _CONFIG_JSON = Path("/deployment/config.json").read_text().strip()
    _CRON_SCHEDULE = Path("/deployment/cron_schedule").read_text().strip()
    _CRON_TIMEZONE = Path("/deployment/cron_timezone").read_text().strip()
    _IMBUE_REPO_URL = Path("/deployment/imbue_repo_url").read_text().strip()
    _IMBUE_COMMIT_HASH = Path("/deployment/imbue_commit_hash").read_text().strip()
    _SECRET_NAME = Path("/deployment/secret_name").read_text().strip()
    _VOLUME_NAME = Path("/deployment/volume_name").read_text().strip()

# --- Image definition ---
# The image includes system dependencies, GitHub CLI, uv, and Claude Code.
# These layers are cached across deployments since they don't change.
# The imbue monorepo (tooling) is cloned at runtime, not baked in.
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

# Add the single staging directory containing all deployment + user config data
if modal.is_local():
    _image = _image.add_local_dir(str(_staging_dir / "deployment"), "/deployment", copy=True).add_local_dir(
        str(_staging_dir / "user_config"), "/staged_user_config", copy=True
    )

app = modal.App(name=_APP_NAME, image=_image)

# Persistent volume for target repo storage (reused across runs of the same changeling)
_volume = modal.Volume.from_name(_VOLUME_NAME, create_if_missing=True)

# Where the imbue monorepo (tooling) is stored on the persistent volume.
# By living on the volume, the imbue repo is cached between runs and only
# needs to be fetched (not fully cloned) on subsequent invocations.
_IMBUE_REPO_DIR = "/volume/imbue"

# Where the persistent volume is mounted
_VOLUME_DIR = "/volume"

# Target repo code lives under /volume/code/<repo_name>
_VOLUME_CODE_DIR = "/volume/code"


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


def _install_user_config() -> None:
    """Copy staged user config files to their expected locations in the container."""
    staged = Path("/staged_user_config")

    claude_json = staged / "claude.json"
    if claude_json.exists():
        shutil.copy2(claude_json, Path.home() / ".claude.json")

    claude_settings = staged / "claude_dir" / "settings.json"
    if claude_settings.exists():
        (Path.home() / ".claude").mkdir(parents=True, exist_ok=True)
        shutil.copy2(claude_settings, Path.home() / ".claude" / "settings.json")

    mngr_config = staged / "mngr" / "config.toml"
    if mngr_config.exists():
        (Path.home() / ".mngr").mkdir(parents=True, exist_ok=True)
        shutil.copy2(mngr_config, Path.home() / ".mngr" / "config.toml")

    mngr_profiles = staged / "mngr" / "profiles"
    if mngr_profiles.is_dir():
        shutil.copytree(mngr_profiles, Path.home() / ".mngr" / "profiles", dirs_exist_ok=True)


def _repo_name_from_url(url: str) -> str:
    """Extract the repository name from a clone URL.

    e.g. "https://github.com/org/my-project.git" -> "my-project"
    """
    name = url.rstrip("/").rsplit("/", 1)[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name


def _clone_or_fetch_repo(repo_url: str, branch_or_commit: str, target_dir: str) -> str:
    """Clone a repo onto the volume, or fetch and checkout if it already exists.

    Returns the path to the repo directory.
    """
    git_dir = f"{target_dir}/.git"
    parent_dir = str(Path(target_dir).parent)
    os.makedirs(parent_dir, exist_ok=True)

    if os.path.isdir(git_dir):
        # Repo already exists on the volume -- just fetch and checkout
        print(f"Repo already on volume at {target_dir}, fetching updates...")
        _run_and_stream(["git", "fetch", "--all"], cwd=target_dir)
        _run_and_stream(["git", "checkout", branch_or_commit], cwd=target_dir)
        _run_and_stream(["git", "pull", "--ff-only"], cwd=target_dir, is_checked=False)
    else:
        # Fresh clone
        print(f"Cloning repo {repo_url} to {target_dir}...")
        _run_and_stream(["git", "clone", repo_url, target_dir])
        _run_and_stream(["git", "checkout", branch_or_commit], cwd=target_dir)

    return target_dir


def _clone_or_fetch_target_repo(repo_url: str, branch: str) -> str:
    """Clone the target repo onto the volume, or fetch if it already exists.

    Returns the path to the target repo directory.
    """
    repo_name = _repo_name_from_url(repo_url)
    target_dir = f"{_VOLUME_CODE_DIR}/{repo_name}"
    return _clone_or_fetch_repo(repo_url, branch, target_dir)


@app.function(
    secrets=[modal.Secret.from_name(_SECRET_NAME)],
    schedule=modal.Cron(_CRON_SCHEDULE, timezone=_CRON_TIMEZONE),
    timeout=3600,
    volumes={_VOLUME_DIR: _volume},
)
def run_changeling() -> None:
    """Run the changeling by cloning the imbue repo and invoking the remote runner.

    This function executes on the cron schedule and:
    1. Checks if the changeling is enabled
    2. Installs user config files (claude, mngr) to their expected locations
    3. Sets up GitHub authentication via gh CLI
    4. Clones/fetches the target repo onto the persistent volume
    5. Clones the imbue monorepo (tooling) and checks out the pinned commit
    6. Installs all dependencies via uv sync
    7. Invokes remote_runner.py which handles the mngr create command
    """
    # Check if enabled without importing imbue
    config = json.loads(_CONFIG_JSON)
    if not config.get("is_enabled", True):
        print("Changeling is disabled, skipping")
        return

    # Install user config files to their expected locations
    _install_user_config()

    # Set up GitHub authentication
    print("Setting up GitHub authentication...")
    os.makedirs(os.path.expanduser("~/.ssh"), mode=0o700, exist_ok=True)
    _run_and_stream(
        "ssh-keyscan github.com >> ~/.ssh/known_hosts && gh auth setup-git",
        is_shell=True,
    )

    # Clone or fetch the target repo onto the persistent volume.
    # If no target repo is configured, the imbue repo IS the target (dev mode).
    target_repo_url = config.get("repo")
    target_branch = config.get("branch", "main")
    target_repo_path = None

    if target_repo_url is not None:
        target_repo_path = _clone_or_fetch_target_repo(target_repo_url, target_branch)
        _volume.commit()
        print(f"Target repo persisted to volume at {target_repo_path}")

    # Clone or fetch the imbue monorepo (contains changeling/mngr tooling) at the pinned commit.
    # The imbue repo lives on the persistent volume so it is cached between runs.
    print(f"Fetching imbue repo from {_IMBUE_REPO_URL} at commit {_IMBUE_COMMIT_HASH}...")
    _clone_or_fetch_repo(_IMBUE_REPO_URL, _IMBUE_COMMIT_HASH, _IMBUE_REPO_DIR)
    _volume.commit()

    # Install all dependencies so changeling/mngr packages are available
    print("Installing dependencies via uv sync...")
    _run_and_stream(["uv", "sync", "--all-packages"], cwd=_IMBUE_REPO_DIR)

    # Invoke the remote runner script (which has full access to the imbue stack).
    # Pass the target repo path if we cloned it; otherwise remote_runner uses
    # the imbue repo cwd as the target (dev mode).
    runner_cmd = [
        "uv",
        "run",
        "python",
        "-m",
        "imbue.changelings.deploy.remote_runner",
        _CONFIG_JSON,
    ]
    if target_repo_path is not None:
        runner_cmd.append(target_repo_path)

    print("Running changeling via remote runner...")
    exit_code = _run_and_stream(
        runner_cmd,
        cwd=_IMBUE_REPO_DIR,
        is_checked=False,
    )
    if exit_code != 0:
        raise RuntimeError(f"Remote runner failed with exit code {exit_code}")
