#!/bin/bash
# Print the conversation transcript for the review commands.
# Reads the session ID from .claude/sessionid (written by the stop hook)
# and delegates to print_user_session.sh.
#
# This wrapper exists so that the !` ` expansion in command files
# does not need $() substitution, which is blocked by Claude Code's
# permission system when --dangerously-skip-permissions is not set.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ ! -f .claude/sessionid ]; then
    exit 0
fi

export MAIN_CLAUDE_SESSION_ID
MAIN_CLAUDE_SESSION_ID="$(cat .claude/sessionid)"

if [ -z "$MAIN_CLAUDE_SESSION_ID" ]; then
    exit 0
fi

exec "$SCRIPT_DIR/print_user_session.sh"
