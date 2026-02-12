import shlex
import shutil
import sys
import tempfile
from datetime import datetime
from datetime import timezone
from pathlib import Path

import tomlkit
from croniter import croniter
from loguru import logger
from pydantic import Field

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.imbue_common.frozen_model import FrozenModel
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


def _save_schedules(path: Path, schedules: list[ScheduleDefinition]) -> None:
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


@pure
def _get_mngr_executable_path() -> str:
    """Discover the mngr executable path."""
    which_result = shutil.which("mngr")
    if which_result is not None:
        return which_result
    return sys.argv[0]


@pure
def _crontab_marker(name: ScheduleName) -> str:
    return f"# mngr-schedule:{name}"


@pure
def _build_crontab_command(schedule: ScheduleDefinition, mngr_path: str) -> str:
    """Build the full crontab line for a schedule."""
    parts = [schedule.cron, shlex.quote(mngr_path), "create"]

    if schedule.template is not None:
        parts.extend(["--template", shlex.quote(schedule.template)])

    parts.extend(["--no-connect", "--message", shlex.quote(schedule.message)])

    for arg in schedule.create_args:
        parts.append(shlex.quote(arg))

    # Log output to a schedule-specific log file
    log_path = f"~/.mngr/logs/schedule-{schedule.name}.log"
    parts.append(f">> {log_path} 2>&1")

    parts.append(_crontab_marker(schedule.name))

    return " ".join(parts)


def _read_current_crontab(cg: ConcurrencyGroup) -> str:
    """Read the current user's crontab. Returns empty string if none exists."""
    result = cg.run_process_to_completion(
        ["crontab", "-l"],
        is_checked_after=False,
    )
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
        result = cg.run_process_to_completion(
            ["crontab", temp_path],
            is_checked_after=False,
        )
        if result.returncode != 0:
            raise CrontabError(f"Failed to write crontab: {result.stderr}")
    finally:
        Path(temp_path).unlink(missing_ok=True)


def _add_crontab_entry(line: str, cg: ConcurrencyGroup) -> None:
    """Add a line to the user's crontab."""
    current = _read_current_crontab(cg)
    if current and not current.endswith("\n"):
        current += "\n"
    new_content = current + line + "\n"
    _write_crontab(new_content, cg)


def _remove_crontab_entry(name: ScheduleName, cg: ConcurrencyGroup) -> None:
    """Remove crontab entries matching the schedule name marker."""
    current = _read_current_crontab(cg)
    if not current:
        return
    marker = _crontab_marker(name)
    lines = current.splitlines()
    filtered_lines = [line for line in lines if not line.rstrip().endswith(marker)]
    new_content = "\n".join(filtered_lines)
    if new_content:
        new_content += "\n"
    _write_crontab(new_content, cg)


# === Public API Functions ===


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
    _add_crontab_entry(crontab_line, mngr_ctx.cg)

    return ScheduleAddResult(schedule=schedule, crontab_line=crontab_line)


def remove_schedule(
    name: ScheduleName,
    mngr_ctx: MngrContext,
) -> ScheduleRemoveResult:
    """Remove a schedule and its crontab entry."""
    schedules_path = _get_schedules_path(mngr_ctx)
    schedules = _load_schedules(schedules_path)

    # Find and remove the schedule
    found = False
    remaining: list[ScheduleDefinition] = []
    for schedule in schedules:
        if schedule.name == name:
            found = True
        else:
            remaining.append(schedule)

    if not found:
        raise ScheduleNotFoundError(str(name))

    # Save updated schedules
    _save_schedules(schedules_path, remaining)

    # Remove crontab entry
    logger.debug("Removing crontab entry for schedule: {}", name)
    _remove_crontab_entry(name, mngr_ctx.cg)

    return ScheduleRemoveResult(name=name)


def list_schedules(
    mngr_ctx: MngrContext,
) -> ScheduleListResult:
    """List all schedules."""
    schedules_path = _get_schedules_path(mngr_ctx)
    schedules = _load_schedules(schedules_path)
    return ScheduleListResult(schedules=tuple(schedules))


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
    mngr_ctx.cg.run_process_to_completion(
        command_parts,
        is_checked_after=True,
    )
