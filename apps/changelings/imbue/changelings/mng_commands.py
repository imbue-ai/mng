# Shared functions for building mng create commands and writing secrets env files.
# Both the cli and deploy packages import from here to avoid circular dependencies.

import os
import shlex
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from datetime import timezone
from pathlib import Path

from loguru import logger

from imbue.changelings.data_types import ChangelingDefinition


def build_mng_create_command(
    changeling: ChangelingDefinition,
    is_modal: bool,
    env_file_path: Path | None,
) -> list[str]:
    """Build the mng create command for a changeling.

    Constructs the full argument list for invoking mng create based on
    the changeling definition. When is_modal is True, the command targets
    Modal as the host provider. Secrets are passed via env_file_path
    (a path to a file containing KEY=VALUE pairs).
    """
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H-%M-%S")
    agent_name = f"{changeling.name}-{now_str}"
    branch_name = f"changelings/{changeling.name}-{now_str}"

    # format the initial message
    initial_message = changeling.initial_message.format(
        NAME=changeling.name,
        AGENT_TYPE=changeling.agent_type,
        RUN_NAME=changeling.name,
        BRANCH=changeling.branch,
    )

    cmd = [
        "uv",
        "run",
        "mng",
        "create",
        agent_name,
        changeling.agent_type,
        "-vv",
        "--no-connect",
        "--await-ready",
        "--yes",
        "--no-ensure-clean",
        "--tag",
        "CREATOR=changeling",
        "--tag",
        f"CHANGELING={changeling.name}",
        "--base-branch",
        changeling.branch,
        "--new-branch",
        branch_name,
        "--message",
        initial_message,
        # make another command window that tries to log us in
        "-c",
        "github_setup='mkdir -p ~/.ssh && ssh-keyscan github.com >> ~/.ssh/known_hosts && gh auth setup-git'",
    ]

    # When running on Modal, specify the provider and pass secrets via env file
    if is_modal:
        cmd.extend(["--in", "modal"])
        # Target path is the Modal volume mount point
        cmd.extend(["--target-path", "/code/mng"])
        if env_file_path is not None:
            cmd.extend(["--host-env-file", str(env_file_path)])

    # Pass explicit environment variables
    for key, value in changeling.env_vars.items():
        cmd.extend(["--host-env", f"{key}={value}"])

    # Pass custom mng options
    for key, value in changeling.mng_options.items():
        cmd.extend([f"--{key}", value])

    # Append any extra mng args
    if changeling.extra_mng_args:
        cmd.extend(shlex.split(changeling.extra_mng_args))

    # finally, the agent should run without any security prompts if in modal
    if is_modal:
        cmd.extend(["--", "--dangerously-skip-permissions"])

    return cmd


def get_agent_name_from_command(cmd: list[str]) -> str:
    """Extract the agent name from a mng create command.

    The agent name is the first positional argument after 'create'.
    """
    create_idx = cmd.index("create")
    return cmd[create_idx + 1]


def write_secrets_env_file(changeling: ChangelingDefinition) -> Path:
    """Write configured secrets from the local environment to a temporary env file.

    The caller is responsible for deleting the file when done.
    Prefer using secrets_env_file() context manager which handles cleanup automatically.
    """
    fd, path_str = tempfile.mkstemp(prefix="changeling-env-", suffix=".env")
    env_file_path = Path(path_str)
    with os.fdopen(fd, "wb") as f:
        lines: list[str] = []
        for secret_name in changeling.secrets:
            value = os.environ.get(secret_name, "")
            if value:
                lines.append(f"{secret_name}={value}\n")
            else:
                logger.warning("Secret '{}' not found in environment, skipping", secret_name)
        f.write("".join(lines).encode())
    # Restrict permissions to owner-only
    env_file_path.chmod(0o600)
    return env_file_path


@contextmanager
def secrets_env_file(changeling: ChangelingDefinition) -> Iterator[Path]:
    """Create a temporary env file with secrets, cleaned up on exit."""
    path = write_secrets_env_file(changeling)
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)
