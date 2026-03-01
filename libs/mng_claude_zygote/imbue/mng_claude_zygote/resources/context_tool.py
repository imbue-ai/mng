"""Context gathering tool for changeling conversations.

This file is passed to `llm live-chat` via `--functions` and provides
the conversation agent with context about the current state of the changeling.

All event data follows the standard envelope format with timestamp, type,
event_id, and source fields. Events are read from logs/<source>/events.jsonl.

The tool tracks which events have already been returned, so each call only
returns new events since the last invocation. This makes conversations more
efficient by avoiding redundant context.

NOTE: _format_events() is duplicated in extra_context_tool.py because these
files are deployed as standalone scripts to the agent host via --functions,
where they cannot import from each other or from the mng_claude_zygote package.
"""

import json
import os
from pathlib import Path

_MAX_CONTENT_LENGTH = 200

# State that persists between calls within the same llm live-chat session.
# llm loads the module once via exec() and keeps function objects in memory,
# so module-level state survives across invocations.
_last_line_counts: dict[str, int] = {}


def _get_new_lines(file_path: Path) -> list[str]:
    """Read new lines from a file since the last call, updating the offset."""
    key = str(file_path)
    last_count = _last_line_counts.get(key, 0)

    if not file_path.exists():
        return []

    try:
        all_lines = file_path.read_text().strip().split("\n")
    except OSError:
        return []

    if not all_lines or not all_lines[0]:
        return []

    total = len(all_lines)
    if total <= last_count:
        return []

    new_lines = all_lines[last_count:]
    _last_line_counts[key] = total
    return new_lines


def gather_context() -> str:
    """Gather NEW context since the last call for this conversation.

    On the first call, returns recent events from all sources. On subsequent
    calls, returns only events that appeared since the previous invocation.

    Returns context from:
    - New messages from other active conversations (from logs/messages/events.jsonl)
    - New inner monologue entries (from logs/claude_transcript/events.jsonl)
    - New trigger events (from logs/scheduled/, mng_agents/, stop/, monitor/)

    Call this at the start of each conversation turn for situational awareness.
    If it returns "No new context", nothing has changed since the last call.
    """
    agent_data_dir_str = os.environ.get("MNG_AGENT_STATE_DIR", "")
    if not agent_data_dir_str:
        return "No agent data directory configured."

    agent_data_dir = Path(agent_data_dir_str)
    if not agent_data_dir.exists():
        return "Agent data directory does not exist."

    sections: list[str] = []
    is_first_call = len(_last_line_counts) == 0

    # Inner monologue (from logs/claude_transcript/events.jsonl)
    transcript = agent_data_dir / "logs" / "claude_transcript" / "events.jsonl"
    if is_first_call:
        # On first call, show last 10 lines for initial context
        if transcript.exists():
            try:
                lines = transcript.read_text().strip().split("\n")
                if lines and lines[0]:
                    recent = lines[-10:] if len(lines) > 10 else lines
                    formatted = _format_events(recent)
                    sections.append(f"## Recent Inner Monologue ({len(recent)} entries)\n{formatted}")
                    _last_line_counts[str(transcript)] = len(lines)
            except OSError:
                pass
    else:
        new_lines = _get_new_lines(transcript)
        if new_lines:
            formatted = _format_events(new_lines)
            sections.append(f"## New Inner Monologue ({len(new_lines)} entries)\n{formatted}")

    # Messages from other conversations (from logs/messages/events.jsonl)
    messages_file = agent_data_dir / "logs" / "messages" / "events.jsonl"
    current_cid = os.environ.get("LLM_CONVERSATION_ID", "")
    new_msg_lines = _get_new_lines(messages_file) if not is_first_call else []
    if is_first_call and messages_file.exists():
        try:
            all_lines = messages_file.read_text().strip().split("\n")
            if all_lines and all_lines[0]:
                _last_line_counts[str(messages_file)] = len(all_lines)
                # Show last 3 per other conversation for initial context
                other_convs: dict[str, list[str]] = {}
                for line in all_lines:
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
    elif new_msg_lines:
        # Filter to only other conversations' messages
        other_msgs = []
        for line in new_msg_lines:
            try:
                event = json.loads(line.strip())
                if event.get("conversation_id", "") != current_cid:
                    other_msgs.append(line)
            except json.JSONDecodeError:
                continue
        if other_msgs:
            formatted = _format_events(other_msgs)
            sections.append(f"## New messages from other conversations ({len(other_msgs)})\n{formatted}")

    # Trigger events from all sources
    for source in ("scheduled", "mng_agents", "stop", "monitor"):
        events_file = agent_data_dir / "logs" / source / "events.jsonl"
        if is_first_call:
            if events_file.exists():
                try:
                    lines = events_file.read_text().strip().split("\n")
                    if lines and lines[0]:
                        recent = lines[-5:] if len(lines) > 5 else lines
                        formatted = _format_events(recent)
                        sections.append(f"## Recent {source} events ({len(recent)})\n{formatted}")
                        _last_line_counts[str(events_file)] = len(lines)
                except OSError:
                    pass
        else:
            new_lines = _get_new_lines(events_file)
            if new_lines:
                formatted = _format_events(new_lines)
                sections.append(f"## New {source} events ({len(new_lines)})\n{formatted}")

    if not sections:
        return "No new context since last call." if not is_first_call else "No context available."

    return "\n\n".join(sections)


def _format_events(lines: list[str]) -> str:
    """Format event JSONL lines into a readable summary.

    NOTE: This function is intentionally duplicated in extra_context_tool.py.
    These files are deployed as standalone scripts and cannot share imports.
    """
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
                content = str(event["content"])[:_MAX_CONTENT_LENGTH]
                cid = event.get("conversation_id", "?")
                formatted_parts.append(f"  [{ts}] [{event.get('role', '?')}@{cid}] {content}")
            elif "data" in event:
                formatted_parts.append(
                    f"  [{ts}] [{event_type}] {json.dumps(event.get('data', {}))[:_MAX_CONTENT_LENGTH]}"
                )
            else:
                formatted_parts.append(f"  [{ts}] [{event_type}] {line[:_MAX_CONTENT_LENGTH]}")
        except json.JSONDecodeError:
            formatted_parts.append(f"  {line[:_MAX_CONTENT_LENGTH]}")
    return "\n".join(formatted_parts)
