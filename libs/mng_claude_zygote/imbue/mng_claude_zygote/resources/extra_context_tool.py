"""Extra context gathering tool for changeling conversations.

This file is passed to `llm live-chat` via `--functions` and provides
deeper context information beyond what gather_context() returns.

Use this when the conversation requires more detailed information about
the system state, agent status, or extended history.
"""

import json
import os
import subprocess
from pathlib import Path


def gather_extra_context() -> str:
    """Gather extra context including agent status and extended inner monologue history.

    Returns a formatted string with:
    - Current mng agent list (active agents and their states)
    - Extended inner monologue history (last 50 entries)
    - Full conversation list with metadata

    Use this when you need deeper context than gather_context() provides.
    """
    sections: list[str] = []

    # Current mng agent list
    try:
        result = subprocess.run(
            ["uv", "run", "mng", "list", "--json"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            sections.append(f"## Current Agents\n```\n{result.stdout.strip()}\n```")
        else:
            sections.append("## Current Agents\n(No agents or unable to retrieve)")
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        sections.append("## Current Agents\n(Unable to retrieve agent list)")

    agent_data_dir_str = os.environ.get("MNG_AGENT_STATE_DIR", "")
    if agent_data_dir_str:
        agent_data_dir = Path(agent_data_dir_str)

        # Extended inner monologue (last 50 entries)
        transcript = agent_data_dir / "logs" / "transcript.jsonl"
        if transcript.exists():
            try:
                lines = transcript.read_text().strip().split("\n")
                recent = lines[-50:] if len(lines) > 50 else lines
                if recent and recent[0]:
                    formatted = _format_jsonl_lines(recent)
                    sections.append(
                        f"## Extended Inner Monologue (last {len(recent)} of {len(lines)} entries)\n{formatted}"
                    )
            except OSError:
                pass

        # Full conversation list
        conversations_file = agent_data_dir / "logs" / "conversations.jsonl"
        if conversations_file.exists():
            try:
                lines = conversations_file.read_text().strip().split("\n")
                convs: dict[str, dict[str, str]] = {}
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        convs[record["id"]] = record
                    except (json.JSONDecodeError, KeyError):
                        continue
                if convs:
                    conv_lines = []
                    for cid, record in convs.items():
                        conv_lines.append(
                            f"  {cid}: model={record.get('model', '?')}, created={record.get('timestamp', '?')}"
                        )
                    sections.append("## All Conversations\n" + "\n".join(conv_lines))
            except OSError:
                pass

    return "\n\n".join(sections) if sections else "No extra context available."


def _format_jsonl_lines(lines: list[str]) -> str:
    """Format JSONL lines into a readable summary."""
    formatted_parts: list[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            if "role" in data and "content" in data:
                content = str(data["content"])[:300]
                formatted_parts.append(f"  [{data.get('role', '?')}] {content}")
            elif "type" in data:
                formatted_parts.append(f"  [{data['type']}] {json.dumps(data.get('data', {}))[:300]}")
            else:
                formatted_parts.append(f"  {line[:300]}")
        except json.JSONDecodeError:
            formatted_parts.append(f"  {line[:300]}")
    return "\n".join(formatted_parts)
