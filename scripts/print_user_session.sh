#!/bin/bash
# Print out Claude Code conversation history in a way that is easier to read and analyze.
# Prints all sessions in chronological order using the session ID history file.

set -euo pipefail

_process_session() {
    local session_id="$1"
    local jsonl_file
    jsonl_file=$(find ~/.claude/projects/ -name "$session_id.jsonl" 2>/dev/null | head -1)
    if [ -n "$jsonl_file" ] && [ -f "$jsonl_file" ]; then
        cat "$jsonl_file"
    fi
}

# Collect all session IDs in chronological order from the history file
_SESSION_IDS=()

if [ -n "${MNGR_AGENT_STATE_DIR:-}" ] && [ -f "$MNGR_AGENT_STATE_DIR/claude_session_id_history" ]; then
    while IFS= read -r sid; do
        if [ -n "$sid" ]; then
            _SESSION_IDS+=("$sid")
        fi
    done < "$MNGR_AGENT_STATE_DIR/claude_session_id_history"
fi

# Fall back to single current session ID if no history available
if [ ${#_SESSION_IDS[@]} -eq 0 ]; then
    _FALLBACK_SID="${MAIN_CLAUDE_SESSION_ID:-}"
    if [ -n "${MNGR_AGENT_STATE_DIR:-}" ] && [ -f "$MNGR_AGENT_STATE_DIR/claude_session_id" ]; then
        _MNGR_READ_SID=$(cat "$MNGR_AGENT_STATE_DIR/claude_session_id")
        if [ -n "$_MNGR_READ_SID" ]; then
            _FALLBACK_SID="$_MNGR_READ_SID"
        fi
    fi
    if [ -n "$_FALLBACK_SID" ]; then
        _SESSION_IDS+=("$_FALLBACK_SID")
    fi
fi

if [ ${#_SESSION_IDS[@]} -eq 0 ]; then
    echo "No session IDs found" >&2
    exit 1
fi

# Concatenate all session .jsonl files in order, then filter and format
(
    for sid in "${_SESSION_IDS[@]}"; do
        _process_session "$sid"
    done
) | \
  grep -v "tool_use_id" | \
  grep -v 'content":"<' | \
  grep -v '"type":"progress"' | \
  grep -v '"type":"thinking"' | \
  grep -v '"type":"tool_use"' | \
  grep -v '"type":"system"' | \
  grep user | \
  jq '{type: .type, content:  .message.content}' | \
  jq -s 'reduce .[] as $msg ([]; if length > 0 and .[-1].type == "assistant" and $msg.type == "assistant" then .[-1].content[0].text += "\n\n" + $msg.content[0].text else . + [$msg] end)'
