"""Shared test utilities for forwarding server tests."""

import json
from pathlib import Path

from imbue.changelings.forwarding_server.backend_resolver import SERVERS_LOG_FILENAME
from imbue.mng.primitives import AgentId


def write_server_log(host_dir: Path, agent_id: AgentId, server: str, url: str) -> None:
    """Write a server log record for an agent, simulating what a zygote does on startup."""
    logs_dir = host_dir / "agents" / str(agent_id) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    with open(logs_dir / SERVERS_LOG_FILENAME, "a") as f:
        f.write(json.dumps({"server": server, "url": url}) + "\n")
