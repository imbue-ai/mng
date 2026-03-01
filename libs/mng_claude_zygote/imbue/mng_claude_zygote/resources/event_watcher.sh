#!/bin/bash
# Event watcher for changeling agents.
#
# Watches conversation JSONL files and entrypoint_events.jsonl for new entries,
# then sends unhandled events to the primary agent via `mng message`.
#
# Uses inotifywait when available for efficient file watching, falling back
# to polling. Tracks handled events via line counts stored in offset files.
#
# Usage: event_watcher.sh
#
# Environment:
#   MNG_AGENT_STATE_DIR  - agent state directory (contains logs/)
#   MNG_AGENT_NAME       - name of the primary agent to send messages to
#   MNG_HOST_DIR         - host data directory (contains logs/ for log output)

set -euo pipefail

AGENT_DATA_DIR="${MNG_AGENT_STATE_DIR:?MNG_AGENT_STATE_DIR must be set}"
AGENT_NAME="${MNG_AGENT_NAME:?MNG_AGENT_NAME must be set}"
HOST_DIR="${MNG_HOST_DIR:?MNG_HOST_DIR must be set}"
CONVERSATIONS_DIR="$AGENT_DATA_DIR/logs/conversations"
EVENTS_FILE="$AGENT_DATA_DIR/logs/entrypoint_events.jsonl"
OFFSETS_DIR="$AGENT_DATA_DIR/logs/.event_offsets"
LOG_FILE="$HOST_DIR/logs/event_watcher.log"
POLL_INTERVAL=3

# Log to both stdout (visible in tmux window) and log file
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

# Check for new lines in a file and send them to the primary agent
check_and_send_new_events() {
    local file="$1"
    local basename
    basename=$(basename "$file")
    local offset_file="$OFFSETS_DIR/$basename.offset"

    local current_offset=0
    if [ -f "$offset_file" ]; then
        current_offset=$(cat "$offset_file")
    fi

    if [ ! -f "$file" ]; then
        return
    fi

    local total_lines
    total_lines=$(wc -l < "$file" 2>/dev/null || echo 0)
    # trim whitespace from wc output
    total_lines=$(echo "$total_lines" | tr -d '[:space:]')

    if [ "$total_lines" -le "$current_offset" ]; then
        return
    fi

    local new_count=$((total_lines - current_offset))
    local new_lines
    new_lines=$(tail -n +"$((current_offset + 1))" "$file" | head -n "$new_count")

    if [ -z "$new_lines" ]; then
        return
    fi

    # Format the message based on the file type
    local source_label
    if [[ "$basename" == "entrypoint_events.jsonl" ]]; then
        source_label="entrypoint event"
    else
        # Conversation file: extract conversation ID from filename
        local cid="${basename%.jsonl}"
        source_label="conversation $cid"
    fi

    log "Found $new_count new line(s) in $basename (offset $current_offset -> $total_lines)"
    log_debug "New lines from $basename: $(echo "$new_lines" | head -c 500)"

    local message
    message="New $source_label:
$new_lines"

    # Send to the primary agent via mng message
    log "Sending event to agent '$AGENT_NAME' from $basename ($new_count line(s))"
    local send_stderr
    send_stderr=$(mktemp)
    if uv run mng message "$AGENT_NAME" -m "$message" 2>"$send_stderr"; then
        echo "$total_lines" > "$offset_file"
        log "Event sent successfully, offset updated to $total_lines"
    else
        log "ERROR: failed to send event from $basename to $AGENT_NAME: $(cat "$send_stderr")"
    fi
    rm -f "$send_stderr"
}

# Check all watched files for new events
check_all_files() {
    # Check entrypoint events
    if [ -f "$EVENTS_FILE" ]; then
        check_and_send_new_events "$EVENTS_FILE"
    fi

    # Check conversation files
    if [ -d "$CONVERSATIONS_DIR" ]; then
        local file_count=0
        for conv_file in "$CONVERSATIONS_DIR"/*.jsonl; do
            if [ -f "$conv_file" ]; then
                check_and_send_new_events "$conv_file"
                file_count=$((file_count + 1))
            fi
        done
        log_debug "Checked $file_count conversation file(s)"
    fi
}

# Main loop
main() {
    mkdir -p "$OFFSETS_DIR"

    log "Event watcher started"
    log "  Agent data dir: $AGENT_DATA_DIR"
    log "  Agent name: $AGENT_NAME"
    log "  Events file: $EVENTS_FILE"
    log "  Conversations dir: $CONVERSATIONS_DIR"
    log "  Offsets dir: $OFFSETS_DIR"
    log "  Log file: $LOG_FILE"
    log "  Poll interval: ${POLL_INTERVAL}s"

    # Check if inotifywait is available
    if command -v inotifywait &>/dev/null; then
        log "Using inotifywait for file watching"
        while true; do
            # Build the watch list: conversations dir + events file
            local watch_targets=("$CONVERSATIONS_DIR")
            if [ -f "$EVENTS_FILE" ]; then
                watch_targets+=("$EVENTS_FILE")
            fi

            log_debug "Waiting for file changes (targets: ${watch_targets[*]})"
            # Wait for changes (with timeout to pick up new files)
            inotifywait -q -r -t "$POLL_INTERVAL" -e modify,create "${watch_targets[@]}" 2>/dev/null || true
            check_all_files
        done
    else
        log "inotifywait not available, using polling"
        while true; do
            check_all_files
            sleep "$POLL_INTERVAL"
        done
    fi
}

main
