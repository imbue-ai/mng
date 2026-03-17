"""CLI command for updating an existing mind with the latest parent code.

The ``mind update <agent-name>`` command:

1. Stops the mind (via ``mng stop``)
2. Fetches and merges the latest code from the parent repository
3. Updates all vendored git subtrees
4. Starts the mind back up (via ``mng start``)
"""

import json
from pathlib import Path
from typing import Final

import click
from loguru import logger

from imbue.concurrency_group.concurrency_group import ConcurrencyGroup
from imbue.minds.config.data_types import MNG_BINARY
from imbue.minds.errors import MindError
from imbue.minds.errors import MngCommandError
from imbue.minds.forwarding_server.agent_creator import load_creation_settings
from imbue.minds.forwarding_server.parent_tracking import fetch_and_merge_parent
from imbue.minds.forwarding_server.parent_tracking import read_parent_info
from imbue.minds.forwarding_server.vendor_mng import default_vendor_configs
from imbue.minds.forwarding_server.vendor_mng import find_mng_repo_root
from imbue.minds.forwarding_server.vendor_mng import update_vendor_repos
from imbue.mng.primitives import AgentId

_MNG_COMMAND_TIMEOUT_SECONDS: Final[float] = 120.0


def find_mind_agent(agent_name: str) -> dict[str, object]:
    """Find a mind agent by name using ``mng list``.

    Searches for agents with the label ``mind=<agent_name>``.
    Returns the full agent record dict from the JSON output.

    Raises MindError if the agent cannot be found.
    """
    cg = ConcurrencyGroup(name="mng-list")
    with cg:
        result = cg.run_process_to_completion(
            command=[MNG_BINARY, "list", "--label", "mind={}".format(agent_name), "--format=json"],
            is_checked_after=False,
        )
    if result.returncode != 0:
        raise MindError(
            "Failed to list agents: {}".format(
                result.stderr.strip() if result.stderr.strip() else result.stdout.strip()
            )
        )

    agents = _parse_agents_from_output(result.stdout)
    if not agents:
        raise MindError("No mind found with name '{}'".format(agent_name))

    return agents[0]


def _parse_agents_from_output(stdout: str) -> list[dict[str, object]]:
    """Parse agent records from ``mng list --format json`` output.

    Handles the case where stdout may contain non-JSON lines
    (e.g. SSH error tracebacks) mixed with the JSON output.
    """
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("{"):
            try:
                data = json.loads(stripped)
                return list(data.get("agents", []))
            except json.JSONDecodeError:
                continue
    return []


def run_mng_stop(agent_id: AgentId) -> None:
    """Stop a mind agent via ``mng stop``.

    Raises MngCommandError if the command fails.
    """
    logger.info("Stopping agent {}...", agent_id)
    cg = ConcurrencyGroup(name="mng-stop")
    with cg:
        result = cg.run_process_to_completion(
            command=[MNG_BINARY, "stop", str(agent_id)],
            is_checked_after=False,
        )
    if result.returncode != 0:
        raise MngCommandError(
            "mng stop failed (exit code {}):\n{}".format(
                result.returncode,
                result.stderr.strip() if result.stderr.strip() else result.stdout.strip(),
            )
        )


def run_mng_start(agent_id: AgentId) -> None:
    """Start a mind agent via ``mng start``.

    Raises MngCommandError if the command fails.
    """
    logger.info("Starting agent {}...", agent_id)
    cg = ConcurrencyGroup(name="mng-start")
    with cg:
        result = cg.run_process_to_completion(
            command=[MNG_BINARY, "start", str(agent_id)],
            is_checked_after=False,
        )
    if result.returncode != 0:
        raise MngCommandError(
            "mng start failed (exit code {}):\n{}".format(
                result.returncode,
                result.stderr.strip() if result.stderr.strip() else result.stdout.strip(),
            )
        )


@click.command()
@click.argument("agent_name")
def update(agent_name: str) -> None:
    """Update a mind with the latest code from its parent repository.

    Stops the mind, merges the latest parent code, updates vendored
    subtrees, and starts the mind back up.
    """
    logger.info("Looking up mind '{}'...", agent_name)
    agent_record = find_mind_agent(agent_name)
    agent_id = AgentId(str(agent_record["id"]))
    work_dir = Path(str(agent_record["work_dir"]))

    logger.info("Found mind '{}' (agent_id={}, work_dir={})", agent_name, agent_id, work_dir)

    run_mng_stop(agent_id)

    logger.info("Merging latest code from parent repository...")
    parent_info = read_parent_info(work_dir)
    new_hash = fetch_and_merge_parent(work_dir, parent_info)
    logger.info("Merged parent changes (new hash: {})", new_hash[:12])

    logger.info("Updating vendored subtrees...")
    settings = load_creation_settings(work_dir)
    mng_repo_root = find_mng_repo_root()
    vendor_configs = settings.vendor if settings.vendor else default_vendor_configs(mng_repo_root)
    update_vendor_repos(work_dir, vendor_configs)
    logger.info("Vendored subtrees updated ({} configured)", len(vendor_configs))

    run_mng_start(agent_id)

    logger.info("Mind '{}' updated successfully.", agent_name)
