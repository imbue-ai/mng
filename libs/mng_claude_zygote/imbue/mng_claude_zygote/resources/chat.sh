#!/bin/bash
# Chat wrapper for changeling conversations.
#
# Manages conversation threads backed by the `llm` CLI tool. Each conversation
# gets a unique ID tracked in conversations.jsonl, and messages are synced to
# per-conversation JSONL files by the conversation watcher.
#
# Usage:
#   chat --new [message]              Create a new conversation (user-initiated)
#   chat --new --as-agent [message]   Create a new conversation (agent-initiated)
#   chat --resume <cid>              Resume an existing conversation
#   chat --list                      List all conversations
#   chat --help                      Show usage information
#   chat                             List conversations and show help hint
#
# Environment:
#   MNG_AGENT_STATE_DIR  - agent state directory (contains logs/)
#   MNG_HOST_DIR         - host data directory (contains commands/)

set -euo pipefail

AGENT_DATA_DIR="${MNG_AGENT_STATE_DIR:?MNG_AGENT_STATE_DIR must be set}"
CONVERSATIONS_FILE="$AGENT_DATA_DIR/logs/conversations.jsonl"
CONVERSATIONS_DIR="$AGENT_DATA_DIR/logs/conversations"
DEFAULT_MODEL_FILE="$AGENT_DATA_DIR/default_chat_model"
LLM_TOOLS_DIR="${MNG_HOST_DIR:?MNG_HOST_DIR must be set}/commands/llm_tools"
LOG_FILE="${MNG_HOST_DIR}/logs/chat.log"

# Nanosecond-precision UTC timestamp in ISO 8601 format.
# Used everywhere in this plugin for consistent, high-precision timestamps.
iso_timestamp_ns() {
    date -u +"%Y-%m-%dT%H:%M:%S.%NZ"
}

# Log a message to the log file (not to stdout, since chat is interactive)
log() {
    local ts
    ts=$(iso_timestamp_ns)
    mkdir -p "$(dirname "$LOG_FILE")"
    echo "[$ts] $*" >> "$LOG_FILE"
}

get_default_model() {
    if [ -f "$DEFAULT_MODEL_FILE" ]; then
        tr -d '[:space:]' < "$DEFAULT_MODEL_FILE"
    else
        echo "claude-opus-4-6"
    fi
}

generate_cid() {
    # Generate a short unique conversation ID using date + random hex
    echo "conv-$(date +%s)-$(head -c 4 /dev/urandom | xxd -p)"
}

get_updated_at() {
    local cid="$1"
    local conv_file="$CONVERSATIONS_DIR/$cid.jsonl"
    if [ -f "$conv_file" ]; then
        # Use file mtime as updated_at
        stat -c '%Y' "$conv_file" 2>/dev/null | xargs -I{} date -u -d @{} +"%Y-%m-%dT%H:%M:%S.%NZ" 2>/dev/null || echo "?"
    else
        echo "?"
    fi
}

append_conversation_record() {
    local cid="$1"
    local model="$2"
    local timestamp
    timestamp=$(iso_timestamp_ns)
    mkdir -p "$(dirname "$CONVERSATIONS_FILE")"
    printf '{"id":"%s","model":"%s","timestamp":"%s"}\n' "$cid" "$model" "$timestamp" >> "$CONVERSATIONS_FILE"
    log "Appended conversation record: cid=$cid model=$model timestamp=$timestamp"
}

build_tool_args() {
    local args=""
    if [ -f "$LLM_TOOLS_DIR/context_tool.py" ]; then
        args="$args --functions $LLM_TOOLS_DIR/context_tool.py"
    fi
    if [ -f "$LLM_TOOLS_DIR/extra_context_tool.py" ]; then
        args="$args --functions $LLM_TOOLS_DIR/extra_context_tool.py"
    fi
    echo "$args"
}

new_conversation() {
    local as_agent=false
    local message=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --as-agent) as_agent=true; shift ;;
            *) message="$1"; shift ;;
        esac
    done

    local model
    model=$(get_default_model)
    local cid
    cid=$(generate_cid)

    log "Creating new conversation: cid=$cid model=$model as_agent=$as_agent message_len=${#message}"

    append_conversation_record "$cid" "$model"

    if [ "$as_agent" = true ]; then
        # Agent-initiated: inject the message as an assistant response
        if [ -n "$message" ]; then
            log "Injecting agent message into conversation $cid"
            llm inject --cid "$cid" -m "$model" "$message"
            log "Agent message injected successfully"
        fi
        echo "$cid"
    else
        # User-initiated: start an interactive live-chat session
        local tool_args
        tool_args=$(build_tool_args)
        log "Starting live-chat session: cid=$cid model=$model tool_args='$tool_args'"
        if [ -n "$message" ]; then
            # shellcheck disable=SC2086
            exec llm live-chat --cid "$cid" -m "$model" $tool_args "$message"
        else
            # shellcheck disable=SC2086
            exec llm live-chat --cid "$cid" -m "$model" $tool_args
        fi
    fi
}

resume_conversation() {
    local cid="$1"
    shift

    log "Resuming conversation: cid=$cid"

    # Get the model from the latest entry for this conversation
    local model
    model=$(grep "\"id\":\"$cid\"" "$CONVERSATIONS_FILE" 2>/dev/null \
        | tail -1 \
        | jq -r '.model' 2>/dev/null \
        || get_default_model)

    log "Resolved model for conversation $cid: $model"

    local tool_args
    tool_args=$(build_tool_args)
    log "Starting live-chat session (resume): cid=$cid model=$model tool_args='$tool_args'"
    # shellcheck disable=SC2086
    exec llm live-chat --show-history -c --cid "$cid" -m "$model" $tool_args
}

list_conversations() {
    if [ ! -f "$CONVERSATIONS_FILE" ]; then
        echo "No conversations yet."
        return 0
    fi

    log "Listing conversations from $CONVERSATIONS_FILE"

    echo "Conversations:"
    echo "=============="
    # Show unique conversation IDs with their latest model, sorted by updated_at desc
    uv run python3 -c "
import json, os, sys
from pathlib import Path

convs_file = '$CONVERSATIONS_FILE'
convs_dir = '$CONVERSATIONS_DIR'
convs = {}
line_num = 0
for line in open(convs_file):
    line_num += 1
    line = line.strip()
    if not line:
        continue
    try:
        record = json.loads(line)
        convs[record['id']] = record
    except (json.JSONDecodeError, KeyError) as e:
        print(f'  WARNING: malformed line {line_num} in {convs_file}: {e}', file=sys.stderr)
        print(f'    line content: {line[:200]}', file=sys.stderr)
        continue

# Add updated_at from conversation file mtimes
for cid, record in convs.items():
    conv_file = Path(convs_dir) / f'{cid}.jsonl'
    if conv_file.exists():
        mtime = conv_file.stat().st_mtime
        from datetime import datetime, timezone
        record['updated_at'] = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    else:
        record['updated_at'] = record.get('timestamp', '?')

# Sort by updated_at descending (most recent first)
sorted_convs = sorted(convs.values(), key=lambda r: r.get('updated_at', ''), reverse=True)

for record in sorted_convs:
    print(f\"  {record['id']}  model={record.get('model', '?')}  created_at={record.get('timestamp', '?')}  updated_at={record.get('updated_at', '?')}\")
"

    log "Listed $(wc -l < "$CONVERSATIONS_FILE" | tr -d '[:space:]') conversation records"
}

show_help() {
    echo "chat - manage changeling conversations"
    echo ""
    echo "Usage:"
    echo "  chat --new [--as-agent] [message]   Create a new conversation"
    echo "  chat --resume <conversation-id>     Resume an existing conversation"
    echo "  chat --list                         List all conversations"
    echo "  chat --help                         Show this help message"
    echo ""
    echo "With no arguments, lists conversations (same as --list)."
}

log "Invoked with args: $*"

# Parse top-level arguments
case "${1:-}" in
    --new)
        shift
        new_conversation "$@"
        ;;
    --resume)
        shift
        if [ -z "${1:-}" ]; then
            echo "Usage: chat --resume <conversation-id>" >&2
            exit 1
        fi
        resume_conversation "$@"
        ;;
    --list)
        list_conversations
        ;;
    --help|-h)
        show_help
        ;;
    "")
        list_conversations
        echo ""
        echo "Run 'chat --help' for more options."
        ;;
    *)
        echo "Unknown option: $1" >&2
        echo "Run 'chat --help' for usage information." >&2
        exit 1
        ;;
esac
