#!/usr/bin/env bash
#
# run_reviewer.sh
#
# Triggers a code review in a tmux reviewer window, waits for completion,
# and sorts the results.
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

# Configuration
REVIEW_TIMEOUT=600  # 10 minutes max wait for review
POLL_INTERVAL=5     # Check every 5 seconds
REVIEW_OUTPUT_DIR=".reviews/final_issue_json"
REVIEW_OUTPUT_FILE="$REVIEW_OUTPUT_DIR/$WINDOW.json"
REVIEW_DONE_MARKER="$REVIEW_OUTPUT_FILE.done"

# Cache directory for skipping redundant reviews of the same commit
CACHE_DIR=".reviews/cache"
CACHE_COMMIT_FILE="$CACHE_DIR/$WINDOW.commit"
CACHE_OUTPUT_FILE="$CACHE_DIR/$WINDOW.json"
CACHE_EXIT_CODE_FILE="$CACHE_DIR/$WINDOW.exit_code"

# Check if the current commit has already been reviewed successfully
CURRENT_COMMIT=$(git rev-parse HEAD)
if [[ -f "$CACHE_COMMIT_FILE" && -f "$CACHE_OUTPUT_FILE" && -f "$CACHE_EXIT_CODE_FILE" ]]; then
    CACHED_COMMIT=$(cat "$CACHE_COMMIT_FILE")
    if [[ "$CURRENT_COMMIT" == "$CACHED_COMMIT" ]]; then
        CACHED_EXIT_CODE=$(cat "$CACHE_EXIT_CODE_FILE")
        # Restore the cached output file so callers can read it
        mkdir -p "$REVIEW_OUTPUT_DIR"
        cp "$CACHE_OUTPUT_FILE" "$REVIEW_OUTPUT_FILE"
        echo -e "[$WINDOW] Commit $CURRENT_COMMIT already reviewed -- using cached results (exit code $CACHED_EXIT_CODE)"
        exit "$CACHED_EXIT_CODE"
    fi
fi

# remove the old files
rm -rf $REVIEW_DONE_MARKER
rm -rf $REVIEW_OUTPUT_FILE

# Colors for output (disabled if not a terminal)
if [[ -t 2 ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    NC='\033[0m'
else
    RED=''
    GREEN=''
    YELLOW=''
    NC=''
fi

log_error() {
    echo -e "${RED}[$WINDOW] ERROR: $1${NC}" >&2
}

log_warn() {
    echo -e "${YELLOW}[$WINDOW] WARN: $1${NC}" >&2
}

log_info() {
    echo -e "${GREEN}[$WINDOW] $1${NC}"
}

# Send the review command to the tmux window
log_info "Triggering review in $SESSION:$WINDOW..."
tmux send-keys -t "$SESSION:$WINDOW" "/clear"
# see below note
sleep 1.0
tmux send-keys -t "$SESSION:$WINDOW" Enter
sleep 2.0
tmux send-keys -t "$SESSION:$WINDOW" "/verify-branch"
# These have to be separate - otherwise it's treated as a bracketed paste
# and irritatingly, we *do* require the sleep :(  I've seen claude fail without this (though even with zero sleep it only fails about 1 in 10 times for me)
# it would clearly be better to have a more robust method for sending messages, but we don't quite have that yet
sleep 1.0
tmux send-keys -t "$SESSION:$WINDOW" Enter

# Wait for the review done marker file to be created
log_info "Waiting for review to complete..."
START_TIME=$(date +%s)
END_TIME=$((START_TIME + REVIEW_TIMEOUT))

while true; do
    CURRENT_TIME=$(date +%s)

    if [[ $CURRENT_TIME -ge $END_TIME ]]; then
        log_error "Timeout waiting for review after ${REVIEW_TIMEOUT}s"
        exit 3
    fi

    if [[ -f "$REVIEW_DONE_MARKER" ]]; then
        ELAPSED=$((CURRENT_TIME - START_TIME))
        log_info "Review completed in ${ELAPSED}s"
        break
    fi

    sleep "$POLL_INTERVAL"
done

SORTED_OUTPUT=$(mktemp).json
trap "rm -f '$SORTED_OUTPUT'" EXIT

# if the output file doesn't exist or is empty:
if [[ ! -s "$REVIEW_OUTPUT_FILE" ]]; then
    log_info "Done marker exists but output file not found, creating empty file (no issues found)"
    mkdir -p "$REVIEW_OUTPUT_DIR"
    echo '[]' > "$SORTED_OUTPUT"
else
    # Sort the JSON by severity (most severe first), then by confidence (high to low)
    # Severity order: CRITICAL > MAJOR > MINOR > NITPICK > unknown
    # Confidence is a numeric value from 0.0 to 1.0 (higher = more confident)
    log_info "Sorting review results..."

    jq -s 'sort_by(
      (if .severity == "CRITICAL" then 0
       elif .severity == "MAJOR" then 1
       elif .severity == "MINOR" then 2
       elif .severity == "NITPICK" then 3
       else 4 end),
      (-.confidence)
    )' "$REVIEW_OUTPUT_FILE" > "$SORTED_OUTPUT"
fi

# Copy sorted output back to the review output file for callers to read
cp "$SORTED_OUTPUT" "$REVIEW_OUTPUT_FILE"

# Check for blocking issues (CRITICAL or MAJOR severity with confidence >= 0.7)
BLOCKING_ISSUES=$(jq '[.[] | select(
    (.severity == "CRITICAL" or .severity == "MAJOR") and
    (.confidence >= 0.7)
)] | length' "$SORTED_OUTPUT")

# Cache the results so we can skip re-reviewing the same commit
cache_results() {
    local exit_code="$1"
    mkdir -p "$CACHE_DIR"
    echo "$CURRENT_COMMIT" > "$CACHE_COMMIT_FILE"
    cp "$SORTED_OUTPUT" "$CACHE_OUTPUT_FILE"
    echo "$exit_code" > "$CACHE_EXIT_CODE_FILE"
}

if [[ "$BLOCKING_ISSUES" -gt 0 ]]; then
    log_error "Found $BLOCKING_ISSUES blocking issues (CRITICAL/MAJOR with confidence >= 0.7)"
    cache_results 2
    exit 2
fi

log_info "Reviewer $WINDOW completed successfully (no blocking issues)"
cache_results 0
exit 0
