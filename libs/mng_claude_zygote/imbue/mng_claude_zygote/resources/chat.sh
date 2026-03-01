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
#   chat                             List all conversations
#
# Environment:
#   MNG_AGENT_STATE_DIR  - agent state directory (contains logs/)
#   MNG_HOST_DIR         - host data directory (contains commands/)

set -euo pipefail

AGENT_DATA_DIR="${MNG_AGENT_STATE_DIR:?MNG_AGENT_STATE_DIR must be set}"
CONVERSATIONS_FILE="$AGENT_DATA_DIR/logs/conversations.jsonl"
DEFAULT_MODEL_FILE="$AGENT_DATA_DIR/default_chat_model"
LLM_TOOLS_DIR="${MNG_HOST_DIR:?MNG_HOST_DIR must be set}/commands/llm_tools"

get_default_model() {
    if [ -f "$DEFAULT_MODEL_FILE" ]; then
        cat "$DEFAULT_MODEL_FILE" | tr -d '[:space:]'
    else
        echo "claude-sonnet-4-6"
    fi
}

generate_cid() {
    # Generate a short unique conversation ID using date + random hex
    echo "conv-$(date +%s)-$(head -c 4 /dev/urandom | xxd -p)"
}

append_conversation_record() {
    local cid="$1"
    local model="$2"
    local timestamp
    timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    mkdir -p "$(dirname "$CONVERSATIONS_FILE")"
    printf '{"id":"%s","model":"%s","timestamp":"%s"}\n' "$cid" "$model" "$timestamp" >> "$CONVERSATIONS_FILE"
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

    append_conversation_record "$cid" "$model"

    if [ "$as_agent" = true ]; then
        # Agent-initiated: inject the message as an assistant response
        if [ -n "$message" ]; then
            llm inject --cid "$cid" -m "$model" "$message"
        fi
        echo "$cid"
    else
        # User-initiated: start an interactive live-chat session
        local tool_args
        tool_args=$(build_tool_args)
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

    # Get the model from the latest entry for this conversation
    local model
    model=$(grep "\"id\":\"$cid\"" "$CONVERSATIONS_FILE" 2>/dev/null | tail -1 | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['model'])" 2>/dev/null || get_default_model)

    local tool_args
    tool_args=$(build_tool_args)
    # shellcheck disable=SC2086
    exec llm live-chat --show-history -c --cid "$cid" -m "$model" $tool_args
}

list_conversations() {
    if [ ! -f "$CONVERSATIONS_FILE" ]; then
        echo "No conversations yet."
        return 0
    fi

    echo "Conversations:"
    echo "=============="
    # Show unique conversation IDs with their latest model
    python3 -c "
import json, sys
convs = {}
for line in open('$CONVERSATIONS_FILE'):
    line = line.strip()
    if not line:
        continue
    try:
        record = json.loads(line)
        convs[record['id']] = record
    except (json.JSONDecodeError, KeyError):
        continue
for cid, record in convs.items():
    print(f\"  {record['id']}  model={record.get('model', '?')}  created={record.get('timestamp', '?')}\")
" 2>/dev/null || echo "  (error reading conversations)"
}

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
    "")
        list_conversations
        ;;
    *)
        echo "Usage: chat [--new [--as-agent] [message]] [--resume <cid>]" >&2
        exit 1
        ;;
esac
