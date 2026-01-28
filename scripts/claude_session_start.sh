#!/bin/bash
# Session start hook script that manages the "active" file for detecting interrupted sessions

set -euo pipefail

ACTIVE_FILE=".claude/active"

# Ensure .claude directory exists
mkdir -p .claude

# Check if there's already an active file (previous session was interrupted)
if [[ -f "$ACTIVE_FILE" ]]; then
    # Touch the file to update its timestamp
    touch "$ACTIVE_FILE"

    # Check if we're in a tmux session
    if [[ -n "${TMUX:-}" ]]; then
        # Get the current tmux session name
        session=$(tmux display-message -p '#S' 2>/dev/null || true)
        if [[ -n "$session" ]]; then
            # Send a message to window 0 to notify about the interruption
            tmux send-keys -t "${session}:0" "You were interrupted. Please continue from where you left off" Enter 2>/dev/null || true
        fi
    fi
else
    # Create the active file
    touch "$ACTIVE_FILE"
fi

exit 0
