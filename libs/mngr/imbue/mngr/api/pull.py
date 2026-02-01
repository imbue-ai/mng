from pathlib import Path

from loguru import logger
from pydantic import Field

from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.pure import pure
from imbue.mngr.errors import MngrError
from imbue.mngr.interfaces.agent import AgentInterface
from imbue.mngr.interfaces.data_types import CommandResult
from imbue.mngr.interfaces.host import OnlineHostInterface


class PullResult(FrozenModel):
    """Result of a pull operation."""

    files_transferred: int = Field(
        default=0,
        description="Number of files transferred",
    )
    bytes_transferred: int = Field(
        default=0,
        description="Total bytes transferred",
    )
    source_path: Path = Field(
        description="Source path on the agent",
    )
    destination_path: Path = Field(
        description="Destination path on local machine",
    )
    is_dry_run: bool = Field(
        default=False,
        description="Whether this was a dry run",
    )


def pull_files(
    agent: AgentInterface,
    host: OnlineHostInterface,
    destination: Path,
    # Source path within agent's work_dir (defaults to work_dir itself)
    source_path: Path | None = None,
    # If True, only show what would be transferred
    dry_run: bool = False,
    # If True, delete files in destination that don't exist in source
    delete: bool = False,
) -> PullResult:
    """Pull files from an agent's work directory to a local directory using rsync."""
    # Determine source path
    actual_source_path = source_path if source_path is not None else agent.work_dir
    logger.debug("Pulling files from {} to {}", actual_source_path, destination)

    # Build rsync command
    # -a: archive mode (recursive, preserves permissions, etc.)
    # -v: verbose
    # -z: compress during transfer
    # --progress: show progress
    rsync_cmd = ["rsync", "-avz", "--progress"]

    if dry_run:
        rsync_cmd.append("--dry-run")

    if delete:
        rsync_cmd.append("--delete")

    # Add trailing slash to source to copy contents, not the directory itself
    source_str = str(actual_source_path)
    if not source_str.endswith("/"):
        source_str += "/"

    rsync_cmd.append(source_str)
    rsync_cmd.append(str(destination))

    # Execute rsync on the host
    cmd_str = " ".join(rsync_cmd)
    logger.debug("Running rsync command: {}", cmd_str)

    result: CommandResult = host.execute_command(cmd_str)

    if not result.success:
        raise MngrError(f"rsync failed: {result.stderr}")

    # Parse rsync output to extract statistics
    files_transferred, bytes_transferred = _parse_rsync_output(result.stdout)

    logger.info(
        "Pull complete: {} files, {} bytes transferred{}",
        files_transferred,
        bytes_transferred,
        " (dry run)" if dry_run else "",
    )

    return PullResult(
        files_transferred=files_transferred,
        bytes_transferred=bytes_transferred,
        source_path=actual_source_path,
        destination_path=destination,
        is_dry_run=dry_run,
    )


@pure
def _parse_rsync_output(
    # stdout from rsync command
    output: str,
    # Tuple of (files_transferred, bytes_transferred)
) -> tuple[int, int]:
    """Parse rsync output to extract transfer statistics."""
    files_transferred = 0
    bytes_transferred = 0

    lines = output.strip().split("\n")

    # Count files from the output (non-empty, non-stat lines)
    for line in lines:
        line = line.strip()
        # Skip empty lines and stat summary lines
        if not line:
            continue
        if line.startswith("sending incremental file list"):
            continue
        if line.startswith("sent "):
            # Parse "sent X bytes  received Y bytes" line
            parts = line.split()
            for i, part in enumerate(parts):
                if part == "bytes" and i > 0:
                    try:
                        bytes_transferred = int(parts[i - 1].replace(",", ""))
                    except (ValueError, IndexError):
                        pass
                    break
            continue
        if line.startswith("total size"):
            continue
        # This is a file being transferred
        if not line.startswith(" "):
            files_transferred += 1

    return files_transferred, bytes_transferred
