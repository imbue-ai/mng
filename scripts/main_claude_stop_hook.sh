#!/bin/bash
#
# main_claude_stop_hook.sh
#
# Orchestrator for stop hook scripts. Sources stop_hook_common.sh once for
# shared setup (precondition checks, fetch/merge/push), then launches
# stop_hook_pr_and_ci.sh and stop_hook_reviewer.sh in parallel.

set -euo pipefail

# Source shared logic (reads stdin, checks preconditions, sets up variables/functions,
# fetches/merges/pushes base branch, checks for informational session)
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/stop_hook_common.sh"

# Track the commit hash to detect stuck agents.
# Only track if this is the main agent and it's already trying to stop (stop_hook_active=true).
# Subagents (launched by claude itself) also trigger the stop hook, and we must not
# append to reviewed_commits for those, otherwise it looks like the main agent stopped
# again and can falsely trigger the "stuck agent" detection.
STOP_HOOK_ACTIVE=$(echo "$HOOK_INPUT" | jq -r '.stop_hook_active // false')
if [[ "$STOP_HOOK_ACTIVE" == "true" ]]; then
    ( git rev-parse HEAD || echo "conflict" ) >> .claude/reviewed_commits
fi

# Check if we've reviewed the same commit 3 times in a row (agent is stuck)
if [[ -f .claude/reviewed_commits ]]; then
    # Get the last 3 entries
    LAST_THREE=$(tail -n 3 .claude/reviewed_commits)
    ENTRY_COUNT=$(echo "$LAST_THREE" | wc -l)

    if [[ $ENTRY_COUNT -ge 3 ]]; then
        # Check if all 3 entries are identical
        UNIQUE_COUNT=$(echo "$LAST_THREE" | sort -u | wc -l)
        if [[ $UNIQUE_COUNT -eq 1 ]]; then
            echo "ERROR: This hook has been run 3 times at the same commit." >&2
            echo "ERROR: The agent appears to be stuck and unable to make progress." >&2
            echo "ERROR: Please investigate and resolve the issue manually." >&2
            exit 1
        fi
    fi
fi

# Export variables so the child scripts can skip the expensive common setup.
# Functions don't survive exec boundaries, but the child scripts' source of
# stop_hook_common.sh will redefine them when it sees this flag.
export STOP_HOOK_COMMON_SOURCED=1
export HOOK_INPUT TMUX_SESSION SCRIPT_DIR CURRENT_BRANCH BASE_BRANCH
export RED GREEN YELLOW NC

# Launch both scripts in parallel
"$SCRIPT_DIR/stop_hook_pr_and_ci.sh" &
PR_CI_PID=$!

"$SCRIPT_DIR/stop_hook_reviewer.sh" &
REVIEWER_PID=$!

# Wait for both and collect exit codes
FAILED=false

wait "$PR_CI_PID" && PR_CI_EXIT=0 || PR_CI_EXIT=$?
if [[ $PR_CI_EXIT -ne 0 ]]; then
    log_error "PR/CI hook failed (exit code $PR_CI_EXIT)"
    FAILED=true
fi

wait "$REVIEWER_PID" && REVIEWER_EXIT=0 || REVIEWER_EXIT=$?
if [[ $REVIEWER_EXIT -ne 0 ]]; then
    log_error "Reviewer hook failed (exit code $REVIEWER_EXIT)"
    FAILED=true
fi

if [[ "$FAILED" == true ]]; then
    # Propagate the first non-zero exit code
    if [[ $PR_CI_EXIT -ne 0 ]]; then
        exit $PR_CI_EXIT
    fi
    exit $REVIEWER_EXIT
fi

# Call local notification script if it exists
notify_user || echo "No notify_user function defined, skipping."

exit 0
