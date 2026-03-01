"""Context gathering tool for changeling conversations.

This file is passed to `llm live-chat` via `--functions` and provides
the conversation agent with context about the current state of the changeling.

The tool is designed to be called at the start of every conversation turn
so the chat agent has awareness of the broader system state.
"""

import json
import os
from pathlib import Path


def gather_context() -> str:
    """Gather context from other conversations, inner monologue, and recent events.

    Returns a formatted string containing:
    - Recent messages from other active conversations (last 3 messages each)
    - Recent inner monologue entries from the primary agent's transcript
    - Recent entrypoint events (scheduled triggers, sub-agent state changes, etc.)

    Call this at the start of each conversation turn for situational awareness.
    """
    agent_data_dir_str = os.environ.get("MNG_AGENT_STATE_DIR", "")
    if not agent_data_dir_str:
        return "No agent data directory configured."

    agent_data_dir = Path(agent_data_dir_str)
    if not agent_data_dir.exists():
        return "Agent data directory does not exist."

    sections: list[str] = []

    # Recent inner monologue (last 10 entries of transcript.jsonl)
    transcript = agent_data_dir / "logs" / "transcript.jsonl"
    if transcript.exists():
        try:
            lines = transcript.read_text().strip().split("\n")
            recent = lines[-10:] if len(lines) > 10 else lines
            if recent and recent[0]:
                formatted = _format_jsonl_lines(recent)
                sections.append(f"## Recent Inner Monologue (last {len(recent)} entries)\n{formatted}")
        except OSError:
            pass

    # Messages from other conversations (last 3 messages from each)
    conv_dir = agent_data_dir / "logs" / "conversations"
    current_cid = os.environ.get("LLM_CONVERSATION_ID", "")
    if conv_dir.exists():
        try:
            for conv_file in sorted(conv_dir.glob("*.jsonl")):
                cid = conv_file.stem
                if cid == current_cid:
                    continue
                lines = conv_file.read_text().strip().split("\n")
                recent = lines[-3:] if len(lines) > 3 else lines
                if recent and recent[0]:
                    formatted = _format_jsonl_lines(recent)
                    sections.append(f"## Conversation {cid} (last {len(recent)} messages)\n{formatted}")
        except OSError:
            pass

    # Recent entrypoint events (last 5)
    events_file = agent_data_dir / "logs" / "entrypoint_events.jsonl"
    if events_file.exists():
        try:
            lines = events_file.read_text().strip().split("\n")
            recent = lines[-5:] if len(lines) > 5 else lines
            if recent and recent[0]:
                formatted = _format_jsonl_lines(recent)
                sections.append(f"## Recent Events (last {len(recent)})\n{formatted}")
        except OSError:
            pass

    return "\n\n".join(sections) if sections else "No context available."


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
                content = str(data["content"])[:200]
                formatted_parts.append(f"  [{data.get('role', '?')}] {content}")
            elif "type" in data:
                formatted_parts.append(f"  [{data['type']}] {json.dumps(data.get('data', {}))[:200]}")
            else:
                formatted_parts.append(f"  {line[:200]}")
        except json.JSONDecodeError:
            formatted_parts.append(f"  {line[:200]}")
    return "\n".join(formatted_parts)
