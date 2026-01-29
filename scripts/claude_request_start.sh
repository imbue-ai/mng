#!/bin/bash
# Session start hook script that manages the "active" file for detecting interrupted sessions

set -euo pipefail

ACTIVE_FILE=".claude/active"

# Read JSON input from stdin
input=$(cat)

# Parse the source field using jq
# source=$(echo "$input" | jq -r '.source // ""')
# or we could just avoid that dependency entirely via this disgusting grep/sed combo:
source=$(echo "$input" | grep -o '"source"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/')

# Ensure .claude directory exists
mkdir -p .claude

# Check if there's already an active file (previous session was interrupted)
if [[ -f "$ACTIVE_FILE" ]]; then
    # Touch the file to update its timestamp
    touch "$ACTIVE_FILE"

    # Only notify for new or resumed sessions (not clear or compact)
    if [[ "$source" == "startup" || "$source" == "resume" ]]; then
        # Check if we're in a tmux session
        if [[ -n "${TMUX:-}" ]]; then
            # Get the current tmux session name
            session=$(tmux display-message -p '#S' 2>/dev/null || true)
            if [[ -n "$session" ]]; then
                # Send a message to window 0 to notify about the interruption so that the agent can keep working.
                tmux send-keys -t "${session}:0" "You were interrupted. Please continue from where you left off" 2>/dev/null || true
                sleep 2
                tmux send-keys -t "${session}:0" Enter 2>/dev/null || true
            fi
        fi
    fi
else
    # Create the active file
    touch "$ACTIVE_FILE"
fi

exit 0
