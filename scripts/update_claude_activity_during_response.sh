#!/bin/bash
# Updates the agent activity timestamp continuously while a tmux session exists.
#
# Usage: update_claude_activity_during_response.sh <tmux_session_name>
#
# This script:
# 1. Prevents duplicate instances for the same session (via pidfile)
# 2. Continuously updates the activity file ($MNGR_AGENT_STATE_DIR/activity/agent)
# 3. Exits only when the tmux session no longer exists
#
# Environment variables (must be set):
#   MNGR_AGENT_STATE_DIR - path to the agent's state directory
#
# The activity file format matches what base_agent.py record_activity() writes.
# The file's mtime is the authoritative activity timestamp.

set -euo pipefail

TMUX_SESSION_NAME="${1:-}"

if [ -z "$TMUX_SESSION_NAME" ]; then
    echo "Usage: update_claude_activity_during_response.sh <tmux_session_name>" >&2
    exit 1
fi

if [ -z "${MNGR_AGENT_STATE_DIR:-}" ]; then
    echo "Error: MNGR_AGENT_STATE_DIR is not set" >&2
    exit 1
fi

# Use a pidfile to prevent duplicate instances for the same session
LOCK_FILE="/tmp/mngr_act_${TMUX_SESSION_NAME}.pid"

# Check if another instance is already running
if [ -f "$LOCK_FILE" ] && kill -0 "$(cat "$LOCK_FILE" 2>/dev/null)" 2>/dev/null; then
    exit 0
fi

# Write our PID and set up cleanup
echo $$ > "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"' EXIT

ACTIVITY_FILE="${MNGR_AGENT_STATE_DIR}/activity/agent"
UPDATE_INTERVAL=15

# Ensure the activity directory exists
mkdir -p "$(dirname "$ACTIVITY_FILE")"

while true; do
    # Check if the tmux session still exists
    if ! tmux has-session -t "$TMUX_SESSION_NAME" 2>/dev/null; then
        break
    fi

    # Update the activity file (mtime is authoritative per idle_detection.md)
    CURRENT_TIME_MS=$(( $(date +%s) * 1000 ))
    printf '{"time": %d, "source": "activity_updater"}' "$CURRENT_TIME_MS" > "$ACTIVITY_FILE"

    sleep "$UPDATE_INTERVAL"
done
