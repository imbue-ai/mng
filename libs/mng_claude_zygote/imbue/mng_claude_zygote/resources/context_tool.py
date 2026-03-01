"""Context gathering tool for changeling conversations.

This file is passed to `llm live-chat` via `--functions` and provides
the conversation agent with context about the current state of the changeling.

All event data follows the standard envelope format with timestamp, type,
event_id, and source fields. Events are read from logs/<source>/events.jsonl.
"""

import json
import os
from pathlib import Path


def gather_context() -> str:
    """Gather context from other conversations, inner monologue, and recent events.

    Returns a formatted string containing:
    - Recent messages from other active conversations (from logs/messages/events.jsonl)
    - Recent inner monologue entries (from logs/transcript/events.jsonl)
    - Recent entrypoint events (from logs/entrypoint/events.jsonl)

    Call this at the start of each conversation turn for situational awareness.
    """
    agent_data_dir_str = os.environ.get("MNG_AGENT_STATE_DIR", "")
    if not agent_data_dir_str:
        return "No agent data directory configured."

    agent_data_dir = Path(agent_data_dir_str)
    if not agent_data_dir.exists():
        return "Agent data directory does not exist."

    sections: list[str] = []

    # Recent inner monologue (last 10 entries from logs/transcript/events.jsonl)
    transcript = agent_data_dir / "logs" / "transcript" / "events.jsonl"
    if transcript.exists():
        try:
            lines = transcript.read_text().strip().split("\n")
            recent = lines[-10:] if len(lines) > 10 else lines
            if recent and recent[0]:
                formatted = _format_events(recent)
                sections.append(f"## Recent Inner Monologue (last {len(recent)} entries)\n{formatted}")
        except OSError:
            pass

    # Messages from other conversations (from logs/messages/events.jsonl)
    messages_file = agent_data_dir / "logs" / "messages" / "events.jsonl"
    current_cid = os.environ.get("LLM_CONVERSATION_ID", "")
    if messages_file.exists():
        try:
            lines = messages_file.read_text().strip().split("\n")
            # Group by conversation, show last 3 from each other conversation
            other_convs: dict[str, list[str]] = {}
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    cid = event.get("conversation_id", "")
                    if cid and cid != current_cid:
                        other_convs.setdefault(cid, []).append(line)
                except json.JSONDecodeError:
                    continue
            for cid, msgs in other_convs.items():
                recent = msgs[-3:]
                formatted = _format_events(recent)
                sections.append(f"## Conversation {cid} (last {len(recent)} messages)\n{formatted}")
        except OSError:
            pass

    # Recent entrypoint events (last 5 from logs/entrypoint/events.jsonl)
    events_file = agent_data_dir / "logs" / "entrypoint" / "events.jsonl"
    if events_file.exists():
        try:
            lines = events_file.read_text().strip().split("\n")
            recent = lines[-5:] if len(lines) > 5 else lines
            if recent and recent[0]:
                formatted = _format_events(recent)
                sections.append(f"## Recent Entrypoint Events (last {len(recent)})\n{formatted}")
        except OSError:
            pass

    return "\n\n".join(sections) if sections else "No context available."


def _format_events(lines: list[str]) -> str:
    """Format event JSONL lines into a readable summary."""
    formatted_parts: list[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            event_type = event.get("type", "?")
            ts = event.get("timestamp", "?")
            if "role" in event and "content" in event:
                cid = event.get("conversation_id", "?")
                content = str(event["content"])[:200]
                formatted_parts.append(f"  [{ts}] [{event.get('role', '?')}@{cid}] {content}")
            elif "data" in event:
                formatted_parts.append(f"  [{ts}] [{event_type}] {json.dumps(event.get('data', {}))[:200]}")
            else:
                formatted_parts.append(f"  [{ts}] [{event_type}] {line[:200]}")
        except json.JSONDecodeError:
            formatted_parts.append(f"  {line[:200]}")
    return "\n".join(formatted_parts)
