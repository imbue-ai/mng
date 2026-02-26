#!/usr/bin/env bash
#
# run_reviewer.sh
#
# Triggers /autofix in a tmux reviewer window, waits for the result,
# and reports whether fixes were made.
#
# Usage: ./run_reviewer.sh <session> <window>
#
# Arguments:
#   session  - tmux session name
#   window   - tmux window name (e.g., reviewer_0)

set -euo pipefail

if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <session> <window>" >&2
    exit 1
fi

SESSION="$1"
WINDOW="$2"

STOP_HOOK_SCRIPT_NAME="run_reviewer:$WINDOW"
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/stop_hook_common.sh"

_log_to_file "INFO" "run_reviewer started (pid=$$, ppid=$PPID, session=$SESSION, window=$WINDOW)"

# Configuration
REVIEW_TIMEOUT=7200  # 120 minutes for autofix (iterative fix loop)
POLL_INTERVAL=5      # Check every 5 seconds

# Cache directory for skipping redundant reviews of the same commit
CACHE_DIR=".reviews/cache"
CACHE_COMMIT_FILE="$CACHE_DIR/$WINDOW.commit"
CACHE_RESULT_FILE="$CACHE_DIR/$WINDOW.result"
CACHE_EXIT_CODE_FILE="$CACHE_DIR/$WINDOW.exit_code"

# Check if the current commit has already been reviewed successfully
CURRENT_COMMIT=$(git rev-parse HEAD)
if [[ -f "$CACHE_COMMIT_FILE" && -f "$CACHE_RESULT_FILE" && -f "$CACHE_EXIT_CODE_FILE" ]]; then
    CACHED_COMMIT=$(cat "$CACHE_COMMIT_FILE")
    if [[ "$CURRENT_COMMIT" == "$CACHED_COMMIT" ]]; then
        CACHED_EXIT_CODE=$(cat "$CACHE_EXIT_CODE_FILE")
        # Restore the cached result file so callers can read it
        mkdir -p .autofix
        cp "$CACHE_RESULT_FILE" .autofix/result
        echo -e "[$WINDOW] Commit $CURRENT_COMMIT already reviewed -- using cached results (exit code $CACHED_EXIT_CODE)"
        _log_to_file "INFO" "Cache hit for commit $CURRENT_COMMIT, exiting with cached code $CACHED_EXIT_CODE"
        exit "$CACHED_EXIT_CODE"
    fi
fi

# Remove stale result file before sending the command (avoids race condition
# where the poll loop sees an old result before the skill starts)
rm -f .autofix/result

# Override console log functions to include window name prefix
log_error() {
    echo -e "${RED}[$WINDOW] ERROR: $1${NC}" >&2
    _log_to_file "ERROR" "$1"
}

log_warn() {
    echo -e "${YELLOW}[$WINDOW] WARN: $1${NC}" >&2
    _log_to_file "WARN" "$1"
}

log_info() {
    echo -e "${GREEN}[$WINDOW] $1${NC}"
    _log_to_file "INFO" "$1"
}

# Send the /autofix command to the tmux window
_log_to_file "INFO" "Sending /autofix to tmux $SESSION:$WINDOW"
log_info "Triggering autofix in $SESSION:$WINDOW..."
tmux send-keys -t "$SESSION:$WINDOW" "/clear"
sleep 1.0
tmux send-keys -t "$SESSION:$WINDOW" Enter
sleep 2.0
tmux send-keys -t "$SESSION:$WINDOW" "/autofix"
# These have to be separate - otherwise it's treated as a bracketed paste
# and irritatingly, we *do* require the sleep :(  I've seen claude fail
# without this (though even with zero sleep it only fails about 1 in 10
# times for me). It would clearly be better to have a more robust method
# for sending messages, but we don't quite have that yet.
sleep 1.0
tmux send-keys -t "$SESSION:$WINDOW" Enter

# Wait for .autofix/result to be written
log_info "Waiting for autofix to complete..."
START_TIME=$(date +%s)
END_TIME=$((START_TIME + REVIEW_TIMEOUT))

while true; do
    CURRENT_TIME=$(date +%s)

    if [[ $CURRENT_TIME -ge $END_TIME ]]; then
        log_error "Timeout waiting for autofix after ${REVIEW_TIMEOUT}s"
        _log_to_file "ERROR" "Timeout waiting for autofix after ${REVIEW_TIMEOUT}s, exiting with 3"
        exit 3
    fi

    if [[ -f .autofix/result ]]; then
        ELAPSED=$((CURRENT_TIME - START_TIME))
        log_info "Autofix completed in ${ELAPSED}s"
        _log_to_file "INFO" ".autofix/result found after ${ELAPSED}s"
        break
    fi

    sleep "$POLL_INTERVAL"
done

# Cache the results so we can skip re-reviewing the same commit
cache_results() {
    local exit_code="$1"
    mkdir -p "$CACHE_DIR"
    echo "$CURRENT_COMMIT" > "$CACHE_COMMIT_FILE"
    cp .autofix/result "$CACHE_RESULT_FILE"
    echo "$exit_code" > "$CACHE_EXIT_CODE_FILE"
}

# Parse the JSON result
AUTOFIX_STATUS=$(jq -r '.status // empty' .autofix/result 2>/dev/null || true)
AUTOFIX_NOTE=$(jq -r '.note // empty' .autofix/result 2>/dev/null || true)

if [[ "$AUTOFIX_STATUS" == "failed" ]]; then
    log_error "Autofix failed: $AUTOFIX_NOTE"
    _log_to_file "ERROR" "Autofix failed: $AUTOFIX_NOTE, exiting with 1"
    exit 1
fi

# Check if HEAD moved (fixes were made)
NEW_HEAD=$(git rev-parse HEAD)
if [[ "$NEW_HEAD" != "$CURRENT_COMMIT" ]]; then
    log_error "Autofix made changes. Present each fix to the user for Keep/Revert."
    log_error "Run: git log --reverse --format='%H %s' $CURRENT_COMMIT..HEAD"
    log_error "Check .autofix/config/auto-accept.md for auto-accept rules."
    log_error "Revert rejected commits in reverse order: git revert --no-edit <hash>"
    cache_results 2
    _log_to_file "INFO" "Autofix moved HEAD from $CURRENT_COMMIT to $NEW_HEAD, exiting with 2"
    exit 2
fi

log_info "Autofix found no issues"
cache_results 0
_log_to_file "INFO" "Autofix completed cleanly, exiting with 0"
exit 0
