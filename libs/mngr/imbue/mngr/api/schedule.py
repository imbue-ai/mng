import shlex
import shutil
import sys
import tempfile
from collections.abc import Sequence
from datetime import datetime
from datetime import timezone
from pathlib import Path

import tomlkit
from croniter import croniter
from loguru import logger
from pydantic import Field

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.imbue_common.frozen_model import FrozenModel
from imbue.imbue_common.logging import log_call
from imbue.imbue_common.pure import pure
from imbue.mngr.config.data_types import MngrContext
from imbue.mngr.errors import CrontabError
from imbue.mngr.errors import InvalidCronExpressionError
from imbue.mngr.errors import ScheduleAlreadyExistsError
from imbue.mngr.errors import ScheduleNotFoundError
from imbue.mngr.primitives import ScheduleName

# === Data Types ===


class ScheduleDefinition(FrozenModel):
    """A stored schedule definition."""

    name: ScheduleName = Field(description="Human-readable name for this schedule")
    template: str | None = Field(description="Create template to use")
    message: str = Field(description="Message to send to the agent")
    cron: str = Field(description="Cron expression for scheduling")
    create_args: tuple[str, ...] = Field(description="Additional args to pass to mngr create")
    created_at: datetime = Field(description="When this schedule was created")
    is_enabled: bool = Field(description="Whether this schedule is active")


class ScheduleAddResult(FrozenModel):
    """Result of adding a schedule."""

    schedule: ScheduleDefinition = Field(description="The created schedule")
    crontab_line: str = Field(description="The crontab entry that was installed")


class ScheduleRemoveResult(FrozenModel):
    """Result of removing a schedule."""

    name: ScheduleName = Field(description="Name of the removed schedule")


class ScheduleListResult(FrozenModel):
    """Result of listing schedules."""

    schedules: tuple[ScheduleDefinition, ...] = Field(description="All stored schedules")


# === Private Helpers ===


@pure
def _get_schedules_path(mngr_ctx: MngrContext) -> Path:
    return mngr_ctx.profile_dir / "schedules.toml"


def _load_schedules(path: Path) -> list[ScheduleDefinition]:
    """Load schedule definitions from a TOML file."""
    if not path.exists():
        return []
    with open(path) as f:
        doc = tomlkit.load(f)
    raw_schedules = doc.get("schedules", [])
    result: list[ScheduleDefinition] = []
    for raw in raw_schedules:
        result.append(
            ScheduleDefinition(
                name=ScheduleName(raw["name"]),
                template=raw.get("template"),
                message=raw["message"],
                cron=raw["cron"],
                create_args=tuple(raw.get("create_args", [])),
                created_at=datetime.fromisoformat(str(raw["created_at"])),
                is_enabled=raw.get("is_enabled", True),
            )
        )
    return result


def _save_schedules(path: Path, schedules: Sequence[ScheduleDefinition]) -> None:
    """Save schedule definitions to a TOML file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = tomlkit.document()
    schedules_array = tomlkit.aot()
    for schedule in schedules:
        table = tomlkit.table()
        table.add("name", str(schedule.name))
        if schedule.template is not None:
            table.add("template", schedule.template)
        table.add("message", schedule.message)
        table.add("cron", schedule.cron)
        table.add("create_args", list(schedule.create_args))
        table.add("created_at", schedule.created_at.isoformat())
        table.add("is_enabled", schedule.is_enabled)
        schedules_array.append(table)
    doc.add("schedules", schedules_array)
    with open(path, "w") as f:
        tomlkit.dump(doc, f)


def _get_mngr_executable_path() -> str:
    """Discover the absolute path to the mngr executable."""
    which_result = shutil.which("mngr")
    if which_result is not None:
        return str(Path(which_result).resolve())
    return str(Path(sys.argv[0]).resolve())


@pure
def _crontab_marker(name: ScheduleName) -> str:
    return f"# mngr-schedule:{name}"


@pure
def _build_crontab_command(schedule: ScheduleDefinition, mngr_path: str) -> str:
    """Build the full crontab line for a schedule."""
    # Build the mngr create command
    command_parts = [shlex.quote(mngr_path), "create"]

    if schedule.template is not None:
        command_parts.extend(["--template", shlex.quote(schedule.template)])

    command_parts.extend(["--no-connect", "--message", shlex.quote(schedule.message)])

    for arg in schedule.create_args:
        command_parts.append(shlex.quote(arg))

    # Log output to a schedule-specific log file.
    # Use $HOME instead of ~ because tilde is not expanded in crontab.
    # Quote the filename to prevent shell injection via schedule name.
    log_filename = shlex.quote(f"schedule-{schedule.name}.log")
    log_dir = "$HOME/.mngr/logs"
    redirect = f">> {log_dir}/{log_filename} 2>&1"

    # Ensure the log directory exists before running the command
    mngr_command = " ".join(command_parts)
    full_command = f"mkdir -p {log_dir} && {mngr_command} {redirect}"

    return f"{schedule.cron} {full_command} {_crontab_marker(schedule.name)}"


def _read_current_crontab(cg: ConcurrencyGroup) -> str:
    """Read the current user's crontab. Returns empty string if none exists."""
    result = cg.run_process_to_completion(["crontab", "-l"], is_checked_after=False)
    if result.returncode != 0:
        # crontab -l returns non-zero when no crontab exists
        return ""
    return result.stdout


def _write_crontab(content: str, cg: ConcurrencyGroup) -> None:
    """Write new crontab content via a temporary file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".crontab", delete=False) as f:
        f.write(content)
        temp_path = f.name
    try:
        result = cg.run_process_to_completion(["crontab", temp_path], is_checked_after=False)
        if result.returncode != 0:
            raise CrontabError(f"Failed to write crontab: {result.stderr}")
    finally:
        Path(temp_path).unlink(missing_ok=True)


def _add_crontab_entry(line: str, cg: ConcurrencyGroup) -> None:
    """Add a line to the user's crontab."""
    current = _read_current_crontab(cg)
    current_with_newline = current + "\n" if current and not current.endswith("\n") else current
    new_content = current_with_newline + line + "\n"
    _write_crontab(new_content, cg)


def _remove_crontab_entry(name: ScheduleName, cg: ConcurrencyGroup) -> None:
    """Remove crontab entries matching the schedule name marker."""
    current = _read_current_crontab(cg)
    if not current:
        return
    marker = _crontab_marker(name)
    lines = current.splitlines()
    filtered_lines = [line for line in lines if not line.rstrip().endswith(marker)]
    joined_content = "\n".join(filtered_lines)
    final_content = joined_content + "\n" if joined_content else joined_content
    _write_crontab(final_content, cg)


# === Public API Functions ===


@log_call
def add_schedule(
    name: ScheduleName,
    message: str,
    cron: str,
    template: str | None,
    create_args: tuple[str, ...],
    mngr_ctx: MngrContext,
) -> ScheduleAddResult:
    """Add a new schedule and install a crontab entry."""
    # Validate cron expression
    if not croniter.is_valid(cron):
        raise InvalidCronExpressionError(cron)

    # Load existing schedules and check for duplicates
    schedules_path = _get_schedules_path(mngr_ctx)
    schedules = _load_schedules(schedules_path)
    for existing in schedules:
        if existing.name == name:
            raise ScheduleAlreadyExistsError(str(name))

    # Create the schedule definition
    schedule = ScheduleDefinition(
        name=name,
        template=template,
        message=message,
        cron=cron,
        create_args=create_args,
        created_at=datetime.now(timezone.utc),
        is_enabled=True,
    )

    # Save to TOML
    schedules.append(schedule)
    _save_schedules(schedules_path, schedules)

    # Build and install crontab entry
    mngr_path = _get_mngr_executable_path()
    crontab_line = _build_crontab_command(schedule, mngr_path)

    logger.debug("Installing crontab entry: {}", crontab_line)
    _add_crontab_entry(crontab_line, mngr_ctx.concurrency_group)

    return ScheduleAddResult(schedule=schedule, crontab_line=crontab_line)


@log_call
def remove_schedule(
    name: ScheduleName,
    mngr_ctx: MngrContext,
) -> ScheduleRemoveResult:
    """Remove a schedule and its crontab entry."""
    schedules_path = _get_schedules_path(mngr_ctx)
    schedules = _load_schedules(schedules_path)

    # Verify the schedule exists
    is_found = any(schedule.name == name for schedule in schedules)
    if not is_found:
        raise ScheduleNotFoundError(str(name))

    # Filter out the schedule to remove
    remaining = [schedule for schedule in schedules if schedule.name != name]

    # Save updated schedules
    _save_schedules(schedules_path, remaining)

    # Remove crontab entry
    logger.debug("Removing crontab entry for schedule: {}", name)
    _remove_crontab_entry(name, mngr_ctx.concurrency_group)

    return ScheduleRemoveResult(name=name)


@log_call
def list_schedules(
    mngr_ctx: MngrContext,
) -> ScheduleListResult:
    """List all schedules."""
    schedules_path = _get_schedules_path(mngr_ctx)
    schedules = _load_schedules(schedules_path)
    return ScheduleListResult(schedules=tuple(schedules))


@log_call
def run_schedule_now(
    name: ScheduleName,
    mngr_ctx: MngrContext,
) -> None:
    """Execute a schedule's create command immediately."""
    schedules_path = _get_schedules_path(mngr_ctx)
    schedules = _load_schedules(schedules_path)

    target_schedule: ScheduleDefinition | None = None
    for schedule in schedules:
        if schedule.name == name:
            target_schedule = schedule
            break

    if target_schedule is None:
        raise ScheduleNotFoundError(str(name))

    # Build the command
    mngr_path = _get_mngr_executable_path()
    command_parts = [mngr_path, "create"]

    if target_schedule.template is not None:
        command_parts.extend(["--template", target_schedule.template])

    command_parts.extend(["--no-connect", "--message", target_schedule.message])

    for arg in target_schedule.create_args:
        command_parts.append(arg)

    logger.debug("Running schedule command: {}", " ".join(command_parts))
    mngr_ctx.concurrency_group.run_process_to_completion(
        command_parts,
        is_checked_after=True,
    )
