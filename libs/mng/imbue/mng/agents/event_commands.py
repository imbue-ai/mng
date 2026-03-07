from typing import Final

from imbue.imbue_common.pure import pure

AGENT_EVENTS_SOURCE: Final[str] = "mng_agents"
AGENT_EVENTS_FILENAME: Final[str] = "events.jsonl"


@pure
def build_state_transition_command(from_state: str, to_state: str) -> str:
    """Build a shell command that appends an agent state transition event.

    The command writes a single JSONL line to
    $MNG_AGENT_STATE_DIR/events/{AGENT_EVENTS_SOURCE}/{AGENT_EVENTS_FILENAME}
    with an AgentStateTransitionEvent-compatible schema.

    Requires MNG_AGENT_STATE_DIR, MNG_AGENT_ID, and MNG_AGENT_NAME
    to be set in the environment.
    """
    return (
        '_MNG_TS=$(date -u +"%Y-%m-%dT%H:%M:%S.%NZ");'
        ' _MNG_EID="evt-$(head -c 16 /dev/urandom | xxd -p)";'
        f' mkdir -p "$MNG_AGENT_STATE_DIR/events/{AGENT_EVENTS_SOURCE}";'
        " printf"
        ' \'{"timestamp":"%s","type":"agent_state_transition","event_id":"%s",'
        f'"source":"{AGENT_EVENTS_SOURCE}","agent_id":"%s","agent_name":"%s",'
        f'"from_state":"{from_state}","to_state":"{to_state}"}}\\n\''
        ' "$_MNG_TS" "$_MNG_EID" "$MNG_AGENT_ID" "$MNG_AGENT_NAME"'
        f' >> "$MNG_AGENT_STATE_DIR/events/{AGENT_EVENTS_SOURCE}/{AGENT_EVENTS_FILENAME}"'
    )
