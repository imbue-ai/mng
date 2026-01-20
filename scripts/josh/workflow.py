#!/usr/bin/env python3
"""Simple workflow script that launches processes with incremented arguments."""

import subprocess
import time
from pathlib import Path

import click


def get_mtime(file_path: Path) -> float:
    """Get modification time of a file.

    Returns 0.0 if the file doesn't exist.
    """
    if not file_path.exists():
        return 0.0
    return file_path.stat().st_mtime


def wait_for_mtime_or_timeout(
    mtime_file: Path,
    initial_mtime: float,
    max_task_time: float,
) -> None:
    """Wait until mtime changes or timeout is reached.

    Polls every 0.1 seconds for mtime changes.
    """
    start_time = time.time()

    while True:
        elapsed = time.time() - start_time

        if elapsed >= max_task_time:
            return

        current_mtime = get_mtime(mtime_file)
        if current_mtime != initial_mtime:
            return

        time.sleep(0.1)


@click.command()
@click.option(
    "--command-template",
    required=True,
    help="Command template with {idx} and {prev_idx} placeholders",
)
@click.option(
    "--mtime-file",
    required=True,
    type=click.Path(path_type=Path),
    help="File to monitor for modification time changes",
)
@click.option(
    "--max-task-count",
    type=int,
    required=True,
    help="Maximum number of tasks to run",
)
@click.option(
    "--max-total-time",
    type=float,
    required=True,
    help="Maximum total time in seconds",
)
@click.option(
    "--max-task-time",
    type=float,
    required=True,
    help="Maximum time per task in seconds",
)
def main(
    command_template: str,
    mtime_file: Path,
    max_task_count: int,
    max_total_time: float,
    max_task_time: float,
) -> None:
    """Launch processes repeatedly with incremented arguments.

    Each process is given an index (idx) and previous index (prev_idx).
    The process runs until either max_task_time elapses or mtime_file
    is modified. The workflow continues until max_task_count tasks
    have been launched or max_total_time has elapsed.
    """
    start_time = time.time()
    idx = 1

    while idx <= max_task_count:
        elapsed_total = time.time() - start_time

        if elapsed_total >= max_total_time:
            click.echo(f"Reached max total time ({max_total_time}s), stopping")
            break

        prev_idx = idx - 1
        command = command_template.format(idx=idx, prev_idx=prev_idx)

        click.echo(f"Task {idx}: Launching command: {command}")

        initial_mtime = get_mtime(mtime_file)

        subprocess.run(command, shell=True)

        click.echo(f"Task {idx}: Waiting for mtime change or timeout")

        wait_for_mtime_or_timeout(
            mtime_file=mtime_file,
            initial_mtime=initial_mtime,
            max_task_time=max_task_time,
        )

        click.echo(f"Task {idx}: Complete")

        idx += 1


if __name__ == "__main__":
    main()
