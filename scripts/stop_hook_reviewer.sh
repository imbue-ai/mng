#!/bin/bash
#
# stop_hook_reviewer.sh
#
# Ensures all reviewers have not found any major or critical issues.
#
# Normally launched in parallel by main_claude_stop_hook.sh (which handles
# common setup once). Can also be run standalone -- in that case,
# stop_hook_common.sh performs the full setup automatically.

set -euo pipefail

# Source shared logic. When launched from main_claude_stop_hook.sh this is a
# fast no-op (variables already exported, just redefines functions). When run
# standalone it performs the full setup (stdin, preconditions, fetch/merge/push).
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/stop_hook_common.sh"

# Find all windows named reviewer_* and start review processes as background jobs
REVIEWER_PIDS=()
for window in $(tmux list-windows -t "$TMUX_SESSION" -F '#W' 2>/dev/null | grep '^reviewer_' || true); do
    "$SCRIPT_DIR/run_reviewer.sh" "$TMUX_SESSION" "$window" &
    REVIEWER_PIDS+=($!)
done

if [[ ${#REVIEWER_PIDS[@]} -eq 0 ]]; then
    log_info "No reviewer windows found, skipping review"
    exit 0
fi

# Wait for all reviewer background jobs to complete
log_info "Waiting for ${#REVIEWER_PIDS[@]} reviewer(s) to complete..."
REVIEWER_FAILED=false

for pid in "${REVIEWER_PIDS[@]}"; do
    wait "$pid" && EXIT_CODE=0 || EXIT_CODE=$?
    if [[ $EXIT_CODE -ne 0 ]]; then
        if [[ $EXIT_CODE -eq 2 ]]; then
            # Exit code 2 means the reviewer found blocking issues (CRITICAL/MAJOR with confidence >= 0.7)
            # This is expected behavior - we'll surface it to the user after all reviewers complete
            log_warn "Reviewer process $pid found blocking issues (exit code 2)"
            REVIEWER_FAILED=true
        else
            # Other exit codes indicate internal errors that should be surfaced immediately
            log_error "Reviewer process $pid failed with internal error (exit code $EXIT_CODE)"
            log_error "This indicates a problem with the review infrastructure, not code issues."
            log_error "Exit code 3 = timeout waiting for review"
            exit $EXIT_CODE
        fi
    fi
done

if [[ "$REVIEWER_FAILED" == true ]]; then
    log_error "Some issues were identified by the review agent!"
    log_error "Run 'cat .reviews/final_issue_json/*.json' to see the issues."
    log_error "You MUST fix any CRITICAL or MAJOR issues (with confidence >= 0.7) before trying again."
    exit 2
else
    log_info "All reviewers completed successfully"
fi

exit 0
