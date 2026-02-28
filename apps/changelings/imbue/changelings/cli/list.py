import json
from pathlib import Path
from typing import Any

import click
from loguru import logger
from tabulate import tabulate

from imbue.changelings.config.data_types import ChangelingPaths
from imbue.changelings.config.data_types import MNG_BINARY
from imbue.changelings.config.data_types import get_default_data_dir
from imbue.concurrency_group.concurrency_group import ConcurrencyExceptionGroup
from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.mng.primitives import AgentId

_DEFAULT_DISPLAY_FIELDS = (
    "name",
    "id",
    "state",
    "host.state",
)

_HEADER_LABELS: dict[str, str] = {
    "name": "NAME",
    "id": "ID",
    "state": "STATE",
    "host.state": "HOST STATE",
    "host.name": "HOST",
    "host.provider_name": "PROVIDER",
}


def _discover_changeling_ids(paths: ChangelingPaths) -> list[AgentId]:
    """Scan the data directory for changeling directories named by agent ID.

    Directories whose name starts with the AgentId prefix ("agent-") are
    considered changeling directories. Hidden directories and the auth
    directory are skipped.
    """
    if not paths.data_dir.exists():
        return []

    ids: list[AgentId] = []
    for entry in sorted(paths.data_dir.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.startswith(".") or entry.name == "auth":
            continue
        if entry.name.startswith("agent-"):
            ids.append(AgentId(entry.name))

    return ids


def _fetch_mng_agents_json() -> list[dict[str, Any]]:
    """Call `mng list --json --quiet` and return the agents list.

    Returns an empty list on failure.
    """
    cg = ConcurrencyGroup(name="changeling-list")
    try:
        with cg:
            result = cg.run_process_to_completion(
                command=[MNG_BINARY, "list", "--json", "--quiet"],
                timeout=10.0,
                is_checked_after=False,
            )
    except ConcurrencyExceptionGroup as e:
        logger.warning("Failed to run mng list: {}", e)
        return []

    if result.returncode != 0:
        logger.warning("mng list failed: {}", result.stderr.strip())
        return []

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse mng list output: {}", e)
        return []

    return data.get("agents", [])


def _get_field_value(agent: dict[str, Any], field: str) -> str:
    """Extract a field value from a mng agent dict, supporting dotted paths."""
    parts = field.split(".")
    value: Any = agent
    for part in parts:
        if isinstance(value, dict):
            value = value.get(part)
        else:
            value = None
            break

    if value is None:
        return ""
    return str(value)


def _build_table(
    changeling_ids: list[AgentId],
    mng_agents: list[dict[str, Any]],
    fields: tuple[str, ...],
) -> list[list[str]]:
    """Build table rows by matching changeling IDs against mng agent data.

    Returns one row per changeling. If a changeling's agent ID is not found in
    the mng agent list (e.g. the agent was destroyed but the directory remains),
    fields other than "id" are left blank.
    """
    agents_by_id: dict[str, dict[str, Any]] = {}
    for agent in mng_agents:
        agent_id = agent.get("id")
        if agent_id is not None:
            agents_by_id[str(agent_id)] = agent

    rows: list[list[str]] = []
    for cid in changeling_ids:
        agent_data = agents_by_id.get(str(cid))
        row: list[str] = []
        for field in fields:
            if field == "id":
                row.append(str(cid))
            elif agent_data is not None:
                row.append(_get_field_value(agent_data, field))
            else:
                row.append("")
        rows.append(row)

    return rows


def _emit_human_output(
    changeling_ids: list[AgentId],
    mng_agents: list[dict[str, Any]],
    fields: tuple[str, ...],
) -> None:
    """Print a human-readable table of changelings."""
    if not changeling_ids:
        click.echo("No changelings found")
        return

    headers = [_HEADER_LABELS.get(f, f.upper()) for f in fields]
    rows = _build_table(changeling_ids, mng_agents, fields)
    table = tabulate(rows, headers=headers, tablefmt="plain")
    click.echo(table)


def _emit_json_output(
    changeling_ids: list[AgentId],
    mng_agents: list[dict[str, Any]],
) -> None:
    """Print JSON output with changeling info."""
    agents_by_id: dict[str, dict[str, Any]] = {}
    for agent in mng_agents:
        agent_id = agent.get("id")
        if agent_id is not None:
            agents_by_id[str(agent_id)] = agent

    changelings_data: list[dict[str, Any]] = []
    for cid in changeling_ids:
        agent_data = agents_by_id.get(str(cid))
        if agent_data is not None:
            changelings_data.append(agent_data)
        else:
            changelings_data.append({"id": str(cid)})

    click.echo(json.dumps({"changelings": changelings_data}, indent=2))


@click.command(name="list")
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    default=False,
    help="Output in JSON format",
)
@click.option(
    "--data-dir",
    type=click.Path(resolve_path=True),
    default=None,
    help="Data directory for changelings state (default: ~/.changelings)",
)
def list_command(
    output_json: bool,
    data_dir: str | None,
) -> None:
    """List deployed changelings.

    Scans the changelings data directory for deployed changeling directories
    and cross-references with mng to show the current state of each one.

    Example:

    \b
        changeling list
        changeling list --json
    """
    data_directory = Path(data_dir) if data_dir else get_default_data_dir()
    paths = ChangelingPaths(data_dir=data_directory)

    changeling_ids = _discover_changeling_ids(paths)
    mng_agents = _fetch_mng_agents_json()

    if output_json:
        _emit_json_output(changeling_ids, mng_agents)
    else:
        _emit_human_output(changeling_ids, mng_agents, _DEFAULT_DISPLAY_FIELDS)
