import json
import os
from pathlib import Path

import click
from click.shell_completion import CompletionItem


def _read_agent_names_from_disk() -> list[str]:
    """Read agent names directly from the host directory's agent data files.

    Reads {host_dir}/agents/*/data.json and extracts the "name" field from each.
    Respects the MNGR_HOST_DIR environment variable for the host directory location,
    defaulting to ~/.mngr.

    Returns an empty list if the directory does not exist or any error occurs.
    This function is designed to never raise -- shell completion must not crash.
    """
    try:
        env_host_dir = os.environ.get("MNGR_HOST_DIR")
        host_dir = Path(env_host_dir) if env_host_dir else Path.home() / ".mngr"

        agents_dir = host_dir / "agents"
        if not agents_dir.is_dir():
            return []

        names: list[str] = []
        for agent_dir in agents_dir.iterdir():
            if not agent_dir.is_dir():
                continue
            data_path = agent_dir / "data.json"
            if not data_path.is_file():
                continue
            try:
                data = json.loads(data_path.read_text())
                name = data.get("name")
                if isinstance(name, str) and name:
                    names.append(name)
            except (json.JSONDecodeError, OSError):
                continue

        return sorted(names)
    except OSError:
        return []


def complete_agent_name(
    ctx: click.Context,
    param: click.Parameter,
    incomplete: str,
) -> list[CompletionItem]:
    """Click shell_complete callback that provides agent name completions."""
    names = _read_agent_names_from_disk()
    return [CompletionItem(name) for name in names if name.startswith(incomplete)]
