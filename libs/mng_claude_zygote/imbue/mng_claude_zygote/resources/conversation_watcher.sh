#!/bin/bash
# Conversation watcher for changeling agents.
#
# Watches the llm database for changes and syncs new messages to per-conversation
# JSONL files. Uses inotifywait when available for efficient file watching,
# falling back to polling.
#
# The watcher reads conversation IDs from conversations.jsonl, then queries
# the llm SQLite database for new messages and appends them to individual
# conversation files at logs/conversations/<cid>.jsonl.
#
# Usage: conversation_watcher.sh
#
# Environment:
#   MNG_AGENT_STATE_DIR  - agent state directory (contains logs/)

set -euo pipefail

AGENT_DATA_DIR="${MNG_AGENT_STATE_DIR:?MNG_AGENT_STATE_DIR must be set}"
CONVERSATIONS_FILE="$AGENT_DATA_DIR/logs/conversations.jsonl"
CONVERSATIONS_DIR="$AGENT_DATA_DIR/logs/conversations"
SYNC_STATE_DIR="$AGENT_DATA_DIR/logs/.conv_sync_state"
POLL_INTERVAL=5

# Determine the llm database path
get_llm_db_path() {
    local db_path
    db_path=$(llm logs path 2>/dev/null || echo "")
    if [ -z "$db_path" ]; then
        # Fallback to common default locations
        local llm_user_path="${LLM_USER_PATH:-$HOME/.config/io.datasette.llm}"
        db_path="$llm_user_path/logs.db"
    fi
    echo "$db_path"
}

# Get all tracked conversation IDs from conversations.jsonl
get_conversation_ids() {
    if [ ! -f "$CONVERSATIONS_FILE" ]; then
        return
    fi
    python3 -c "
import json, sys
seen = set()
for line in open('$CONVERSATIONS_FILE'):
    line = line.strip()
    if not line:
        continue
    try:
        record = json.loads(line)
        cid = record['id']
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
# the assistant's response. We use UNION ALL to produce separate user and
# assistant message records from each row, preserving both sides of the
# conversation.
#
# We track sync state via the datetime of the last synced response, rather
# than by ID, since datetime comparison is universally correct regardless
# of the ID format.
sync_conversation() {
    local cid="$1"
    local db_path="$2"
    local conv_file="$CONVERSATIONS_DIR/$cid.jsonl"
    local state_file="$SYNC_STATE_DIR/$cid.last_ts"

    # Read last synced timestamp (empty string if no state yet)
    local last_ts=""
    if [ -f "$state_file" ]; then
        last_ts=$(cat "$state_file")
    fi

    # Build datetime filter for incremental sync
    local ts_filter=""
    if [ -n "$last_ts" ]; then
        ts_filter="AND datetime_utc > '${last_ts}'"
    fi

    # Query produces two rows per response: one for the user prompt,
    # one for the assistant response. Rows without a prompt (injected
    # assistant messages) produce only the assistant row.
    #
    # We use a subquery with explicit sort_ts and sort_order columns to
    # ensure correct chronological ordering: messages are sorted by
    # timestamp, with user messages before assistant messages at the same
    # timestamp (sort_order 0 < 1).
    local query="
    SELECT msg FROM (
        SELECT json_object(
            'role', 'user',
            'content', prompt,
            'timestamp', datetime_utc,
            'conversation_id', conversation_id
        ) AS msg, datetime_utc AS sort_ts, 0 AS sort_order
        FROM responses
        WHERE conversation_id = '${cid}'
        AND prompt IS NOT NULL AND prompt != ''
        ${ts_filter}
        UNION ALL
        SELECT json_object(
            'role', 'assistant',
            'content', response,
            'timestamp', datetime_utc,
            'conversation_id', conversation_id
        ) AS msg, datetime_utc AS sort_ts, 1 AS sort_order
        FROM responses
        WHERE conversation_id = '${cid}'
        AND response IS NOT NULL AND response != ''
        ${ts_filter}
    ) ORDER BY sort_ts ASC, sort_order ASC;"

    local new_messages
    new_messages=$(sqlite3 "$db_path" "$query" 2>/dev/null || echo "")

    if [ -z "$new_messages" ]; then
        return
    fi

    # Append new messages to the conversation file
    echo "$new_messages" >> "$conv_file"

    # Save the latest timestamp for next sync
    local new_last_ts
    new_last_ts=$(sqlite3 "$db_path" "
        SELECT MAX(datetime_utc) FROM responses
        WHERE conversation_id = '${cid}'
        ${ts_filter};
    " 2>/dev/null || echo "")
    if [ -n "$new_last_ts" ]; then
        echo "$new_last_ts" > "$state_file"
    fi
}

# Sync all tracked conversations
sync_all_conversations() {
    local db_path="$1"

    if [ ! -f "$db_path" ]; then
        return
    fi

    local cids
    cids=$(get_conversation_ids)
    if [ -z "$cids" ]; then
        return
    fi

    while IFS= read -r cid; do
        sync_conversation "$cid" "$db_path"
    done <<< "$cids"
}

# Main loop
main() {
    mkdir -p "$CONVERSATIONS_DIR" "$SYNC_STATE_DIR"

    local db_path
    db_path=$(get_llm_db_path)

    echo "Conversation watcher started"
    echo "  Agent data dir: $AGENT_DATA_DIR"
    echo "  LLM database: $db_path"
    echo "  Poll interval: ${POLL_INTERVAL}s"

    # Check if inotifywait is available for efficient watching
    if command -v inotifywait &>/dev/null && [ -f "$db_path" ]; then
        echo "  Using inotifywait for file watching"
        # Watch both the llm database and the conversations file for changes
        while true; do
            # Wait for either file to be modified (with timeout for new conversations)
            inotifywait -q -t "$POLL_INTERVAL" -e modify,create "$db_path" "$CONVERSATIONS_FILE" 2>/dev/null || true
            # Re-resolve db_path in case it was created after we started
            db_path=$(get_llm_db_path)
            sync_all_conversations "$db_path"
        done
    else
        echo "  Using polling (inotifywait not available)"
        while true; do
            # Re-resolve db_path in case it was created after we started
            db_path=$(get_llm_db_path)
            sync_all_conversations "$db_path"
            sleep "$POLL_INTERVAL"
        done
    fi
}

main
