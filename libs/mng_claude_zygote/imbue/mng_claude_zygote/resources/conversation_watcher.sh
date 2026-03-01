#!/bin/bash
# Conversation watcher for changeling agents.
#
# Watches the llm database for changes and syncs new messages to the
# standard event log at logs/messages/events.jsonl. Each message event
# includes the full envelope (timestamp, type, event_id, source) plus
# conversation_id and role, making every line self-describing.
#
# Usage: conversation_watcher.sh
#
# Environment:
#   MNG_AGENT_STATE_DIR  - agent state directory (contains logs/)
#   MNG_HOST_DIR         - host data directory (contains logs/ for log output)

set -euo pipefail

AGENT_DATA_DIR="${MNG_AGENT_STATE_DIR:?MNG_AGENT_STATE_DIR must be set}"
HOST_DIR="${MNG_HOST_DIR:?MNG_HOST_DIR must be set}"
CONVERSATIONS_EVENTS="$AGENT_DATA_DIR/logs/conversations/events.jsonl"
MESSAGES_EVENTS="$AGENT_DATA_DIR/logs/messages/events.jsonl"
SYNC_STATE_DIR="$AGENT_DATA_DIR/logs/.conv_sync_state"
LOG_FILE="$HOST_DIR/logs/conversation_watcher.log"
POLL_INTERVAL=5

log() {
    local ts
    ts=$(date -u +"%Y-%m-%dT%H:%M:%S.%NZ")
    local msg="[$ts] $*"
    echo "$msg"
    mkdir -p "$(dirname "$LOG_FILE")"
    echo "$msg" >> "$LOG_FILE"
}

log_debug() {
    local ts
    ts=$(date -u +"%Y-%m-%dT%H:%M:%S.%NZ")
    mkdir -p "$(dirname "$LOG_FILE")"
    echo "[$ts] [debug] $*" >> "$LOG_FILE"
}

get_llm_db_path() {
    local db_path
    db_path=$(llm logs path 2>/dev/null || echo "")
    if [ -z "$db_path" ]; then
        local llm_user_path="${LLM_USER_PATH:-$HOME/.config/io.datasette.llm}"
        db_path="$llm_user_path/logs.db"
    fi
    echo "$db_path"
}

# Get all tracked conversation IDs from logs/conversations/events.jsonl
get_conversation_ids() {
    if [ ! -f "$CONVERSATIONS_EVENTS" ]; then
        return
    fi
    python3 -c "
import json, sys
seen = set()
for line in open('$CONVERSATIONS_EVENTS'):
    line = line.strip()
    if not line:
        continue
    try:
        event = json.loads(line)
        cid = event['conversation_id']
        if cid not in seen:
            seen.add(cid)
            print(cid)
    except (json.JSONDecodeError, KeyError):
        continue
"
}

# Sync new messages for a single conversation from the llm database.
#
# Each row in the llm responses table contains BOTH the user's prompt and
# the assistant's response. We produce separate message events for each,
# written to logs/messages/events.jsonl with the standard envelope fields.
sync_conversation() {
    local cid="$1"
    local db_path="$2"
    local state_file="$SYNC_STATE_DIR/$cid.last_ts"

    local last_ts=""
    if [ -f "$state_file" ]; then
        last_ts=$(cat "$state_file")
    fi

    local ts_filter=""
    if [ -n "$last_ts" ]; then
        ts_filter="AND datetime_utc > '${last_ts}'"
    fi

    # Each message event has the full envelope: timestamp, type, event_id, source,
    # plus conversation_id, role, content. event_id is constructed from the
    # response id + role suffix to be unique and deterministic.
    local query="
    SELECT msg FROM (
        SELECT json_object(
            'timestamp', datetime_utc,
            'type', 'message',
            'event_id', id || '-user',
            'source', 'messages',
            'conversation_id', conversation_id,
            'role', 'user',
            'content', prompt
        ) AS msg, datetime_utc AS sort_ts, 0 AS sort_order
        FROM responses
        WHERE conversation_id = '${cid}'
        AND prompt IS NOT NULL AND prompt != ''
        ${ts_filter}
        UNION ALL
        SELECT json_object(
            'timestamp', datetime_utc,
            'type', 'message',
            'event_id', id || '-assistant',
            'source', 'messages',
            'conversation_id', conversation_id,
            'role', 'assistant',
            'content', response
        ) AS msg, datetime_utc AS sort_ts, 1 AS sort_order
        FROM responses
        WHERE conversation_id = '${cid}'
        AND response IS NOT NULL AND response != ''
        ${ts_filter}
    ) ORDER BY sort_ts ASC, sort_order ASC;"

    log_debug "Querying conversation $cid (last_ts=$last_ts)"

    local new_messages
    local query_stderr
    query_stderr=$(mktemp)
    new_messages=$(sqlite3 "$db_path" "$query" 2>"$query_stderr" || true)

    if [ -s "$query_stderr" ]; then
        log "WARNING: sqlite3 query error for conversation $cid: $(cat "$query_stderr")"
    fi
    rm -f "$query_stderr"

    if [ -z "$new_messages" ]; then
        log_debug "No new messages for conversation $cid"
        return
    fi

    local msg_count
    msg_count=$(echo "$new_messages" | wc -l | tr -d '[:space:]')
    log "Synced $msg_count new message(s) for conversation $cid -> logs/messages/events.jsonl"

    mkdir -p "$(dirname "$MESSAGES_EVENTS")"
    echo "$new_messages" >> "$MESSAGES_EVENTS"

    local new_last_ts
    new_last_ts=$(sqlite3 "$db_path" "
        SELECT MAX(datetime_utc) FROM responses
        WHERE conversation_id = '${cid}'
        ${ts_filter};
    " 2>/dev/null || echo "")
    if [ -n "$new_last_ts" ]; then
        echo "$new_last_ts" > "$state_file"
        log_debug "Updated sync state for $cid: last_ts=$new_last_ts"
    fi
}

sync_all_conversations() {
    local db_path="$1"

    if [ ! -f "$db_path" ]; then
        log_debug "LLM database not found at $db_path"
        return
    fi

    local cids
    cids=$(get_conversation_ids)
    if [ -z "$cids" ]; then
        log_debug "No tracked conversations found"
        return
    fi

    local cid_count
    cid_count=$(echo "$cids" | wc -l | tr -d '[:space:]')
    log_debug "Checking $cid_count tracked conversation(s)"

    while IFS= read -r cid; do
        sync_conversation "$cid" "$db_path"
    done <<< "$cids"
}

main() {
    mkdir -p "$SYNC_STATE_DIR" "$(dirname "$MESSAGES_EVENTS")"

    local db_path
    db_path=$(get_llm_db_path)

    log "Conversation watcher started"
    log "  Agent data dir: $AGENT_DATA_DIR"
    log "  LLM database: $db_path"
    log "  Conversations events: $CONVERSATIONS_EVENTS"
    log "  Messages events: $MESSAGES_EVENTS"
    log "  Log file: $LOG_FILE"
    log "  Poll interval: ${POLL_INTERVAL}s"

    if command -v inotifywait &>/dev/null && [ -f "$db_path" ]; then
        log "Using inotifywait for file watching"
        while true; do
            inotifywait -q -t "$POLL_INTERVAL" -e modify,create "$db_path" "$CONVERSATIONS_EVENTS" 2>/dev/null || true
            db_path=$(get_llm_db_path)
            sync_all_conversations "$db_path"
        done
    else
        if ! command -v inotifywait &>/dev/null; then
            log "inotifywait not available, using polling"
        elif [ ! -f "$db_path" ]; then
            log "LLM database not yet created at $db_path, using polling"
        fi
        while true; do
            db_path=$(get_llm_db_path)
            sync_all_conversations "$db_path"
            sleep "$POLL_INTERVAL"
        done
    fi
}

main
