from collections.abc import Sequence
from pathlib import Path

import click

from imbue.mng import hookimpl
from imbue.mng.config.data_types import MngContext
from imbue.mng_schedule.cli import schedule


@hookimpl
def register_cli_commands() -> Sequence[click.Command] | None:
    """Register the schedule command with mng."""
    return [schedule]


@hookimpl
def get_files_for_deploy(mng_ctx: MngContext) -> dict[Path, Path | str] | None:
    """Register mng-specific config files for scheduled deployments."""
    files: dict[Path, Path | str] = {}
    user_home = Path.home()

    mng_config = user_home / ".mng" / "config.toml"
    if mng_config.exists():
        files[Path("~/.mng/config.toml")] = mng_config

    mng_profiles = user_home / ".mng" / "profiles"
    if mng_profiles.is_dir():
        for file_path in mng_profiles.rglob("*"):
            if file_path.is_file():
                relative = file_path.relative_to(user_home)
                files[Path(f"~/{relative}")] = file_path

    return files or None
