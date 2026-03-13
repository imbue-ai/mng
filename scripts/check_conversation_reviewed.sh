#!/usr/bin/env bash
# Gate check: requires /verify-conversation to be run before the agent can stop.
# Called by main_claude_stop_hook.sh in parallel with other checks.
# Stuck agent tracking is handled by the caller.
set -euo pipefail

HASH=$(git rev-parse HEAD 2>/dev/null) || exit 0

if [ -f ".reviews/conversation/${HASH}.json" ]; then
    exit 0
fi

echo "Run /verify-conversation to review the conversation before finishing." >&2
exit 2
