#!/bin/bash
# Called by a hook when we start a response, to update the activity timestamp for the claude agent as long as it is replying
# While the file exists, we should continually update the activity timestamp for the claude agent, so that it doesn't get marked as inactive and killed while it's still replying
# When the .claude/active file no longer exists, this script should exit

set -euo pipefail

# Resolve mngr host dir from env var or default
HOST_DIR="${MNGR_HOST_DIR:-$HOME/.mngr}"

# Determine the agent ID (required to know where to write activity)
AGENT_ID="${MNGR_AGENT_ID:-}"
if [ -z "$AGENT_ID" ]; then
    # Not running inside a mngr-managed agent session, nothing to do
    exit 0
fi

# Build path to the agent activity file
ACTIVITY_DIR="$HOST_DIR/agents/$AGENT_ID/activity"
ACTIVITY_FILE="$ACTIVITY_DIR/agent"

# Ensure the activity directory exists
mkdir -p "$ACTIVITY_DIR"

# Update interval (seconds) -- the activity_watcher checks every 15s,
# so updating every 10s ensures we always appear active
UPDATE_INTERVAL=10

while [ -f .claude/active ]; do
    # Write JSON with timestamp and agent metadata (convention from idle_detection docs)
    TIME_MS=$(( $(date +%s) * 1000 ))
    printf '{\n  "time": %d,\n  "agent_id": "%s",\n  "source": "claude_response_hook"\n}\n' \
        "$TIME_MS" "$AGENT_ID" > "$ACTIVITY_FILE"

    sleep "$UPDATE_INTERVAL"
done
