#!/bin/bash
# Event watcher for changeling agents.
#
# Watches event log files (logs/<source>/events.jsonl) for new entries and
# sends unhandled events to the primary agent via `mng message`.
#
# Watched sources:
#   logs/messages/events.jsonl     - conversation messages
#   logs/entrypoint/events.jsonl   - entrypoint triggers (scheduled, sub-agent, etc.)
#
# Each event in these files includes the standard envelope (timestamp, type,
# event_id, source) so the watcher can format meaningful messages.
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
MESSAGES_EVENTS="$AGENT_DATA_DIR/logs/messages/events.jsonl"
ENTRYPOINT_EVENTS="$AGENT_DATA_DIR/logs/entrypoint/events.jsonl"
OFFSETS_DIR="$AGENT_DATA_DIR/logs/.event_offsets"
LOG_FILE="$HOST_DIR/logs/event_watcher.log"
POLL_INTERVAL=3

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

# Check for new lines in an events.jsonl file and send them to the primary agent.
# The offset file uses the parent directory name as key (the source name).
check_and_send_new_events() {
    local file="$1"
    # Use the parent directory name as the source identifier
    local source_dir
    source_dir=$(basename "$(dirname "$file")")
    local offset_file="$OFFSETS_DIR/$source_dir.offset"

    local current_offset=0
    if [ -f "$offset_file" ]; then
        current_offset=$(cat "$offset_file")
    fi

    if [ ! -f "$file" ]; then
        return
    fi

    local total_lines
    total_lines=$(wc -l < "$file" 2>/dev/null || echo 0)
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

    log "Found $new_count new event(s) from source '$source_dir' (offset $current_offset -> $total_lines)"
    log_debug "New events from $source_dir: $(echo "$new_lines" | head -c 500)"

    local message
    message="New $source_dir event(s):
$new_lines"

    log "Sending $new_count event(s) from '$source_dir' to agent '$AGENT_NAME'"
    local send_stderr
    send_stderr=$(mktemp)
    if uv run mng message "$AGENT_NAME" -m "$message" 2>"$send_stderr"; then
        echo "$total_lines" > "$offset_file"
        log "Events sent successfully, offset updated to $total_lines"
    else
        log "ERROR: failed to send events from $source_dir to $AGENT_NAME: $(cat "$send_stderr")"
    fi
    rm -f "$send_stderr"
}

check_all_sources() {
    # Check messages events (conversation messages synced from llm DB)
    if [ -f "$MESSAGES_EVENTS" ]; then
        check_and_send_new_events "$MESSAGES_EVENTS"
    fi

    # Check entrypoint events (scheduled triggers, sub-agent state changes, etc.)
    if [ -f "$ENTRYPOINT_EVENTS" ]; then
        check_and_send_new_events "$ENTRYPOINT_EVENTS"
    fi
}

main() {
    mkdir -p "$OFFSETS_DIR"

    log "Event watcher started"
    log "  Agent data dir: $AGENT_DATA_DIR"
    log "  Agent name: $AGENT_NAME"
    log "  Messages events: $MESSAGES_EVENTS"
    log "  Entrypoint events: $ENTRYPOINT_EVENTS"
    log "  Offsets dir: $OFFSETS_DIR"
    log "  Log file: $LOG_FILE"
    log "  Poll interval: ${POLL_INTERVAL}s"

    if command -v inotifywait &>/dev/null; then
        log "Using inotifywait for file watching"
        while true; do
            local watch_dirs=()
            # Watch parent directories of event files
            watch_dirs+=("$(dirname "$MESSAGES_EVENTS")")
            watch_dirs+=("$(dirname "$ENTRYPOINT_EVENTS")")

            log_debug "Waiting for file changes in: ${watch_dirs[*]}"
            inotifywait -q -r -t "$POLL_INTERVAL" -e modify,create "${watch_dirs[@]}" 2>/dev/null || true
            check_all_sources
        done
    else
        log "inotifywait not available, using polling"
        while true; do
            check_all_sources
            sleep "$POLL_INTERVAL"
        done
    fi
}

main
